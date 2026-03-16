"""
AgentGate FastAPI Application

Main application entry point with middleware configuration, startup/shutdown events,
health checks, and request lifecycle management.
"""

import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Callable, Optional

import redis.asyncio as aioredis
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from opentelemetry import trace, metrics
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

from src.api import auth, endpoints
from src.db import connection
from src.audit import logger as audit_logger

# ============================================================================
# PRODUCTION NOTES
# This is a portfolio demonstration. In a production deployment:
# - JWT signing keys would be managed via HashiCorp Vault or AWS Secrets Manager
# - Agent-to-gateway communication would use mTLS with SPIFFE/SPIRE identities
# - Rate limiting would use Redis Sentinel/Cluster for high availability
# - OpenTelemetry traces would export to Datadog/Grafana Cloud, not local Jaeger
# ============================================================================

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Redis client for rate limiting (initialized at startup)
redis_client: Optional[aioredis.Redis] = None

# OpenTelemetry setup
def setup_observability() -> None:
    """Initialize OpenTelemetry tracing and metrics."""
    trace_exporter = OTLPSpanExporter(
        endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "localhost:4317")
    )
    trace_provider = TracerProvider()
    trace_provider.add_span_processor(BatchSpanProcessor(trace_exporter))
    trace.set_tracer_provider(trace_provider)

    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(
            endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "localhost:4317")
        )
    )
    metrics.set_meter_provider(MeterProvider(metric_readers=[metric_reader]))

    FastAPIInstrumentor.instrument_app(app)
    SQLAlchemyInstrumentor().instrument()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager for startup/shutdown events.

    Startup:
    - Initialize database connections
    - Set up observability (tracing, metrics)
    - Start background workers (secret rotation, token cleanup)

    Shutdown:
    - Close database connections
    - Flush audit logs
    - Clean up resources
    """
    # Startup
    logger.info("Starting AgentGate server")

    try:
        # Initialize database
        await connection.init_db()
        logger.info("Database initialized")

        # Setup observability
        setup_observability()
        logger.info("Observability initialized")

        # Initialize Redis for rate limiting
        global redis_client
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        try:
            redis_client = aioredis.from_url(redis_url, decode_responses=True)
            await redis_client.ping()
            logger.info("Redis connected for rate limiting")
        except Exception as e:
            logger.warning(f"Redis unavailable, rate limiting disabled: {e}")
            redis_client = None

        # Initialize audit logger
        await audit_logger.init()
        logger.info("Audit system initialized")

        # Pre-load policies to cache
        from src.policy.engine import PolicyEngine
        policy_engine = PolicyEngine()
        await policy_engine.load_default_policies()
        logger.info("Policies cached")

        yield

    except Exception as e:
        logger.error(f"Startup failed: {e}", exc_info=True)
        raise

    # Shutdown
    finally:
        logger.info("Shutting down AgentGate server")
        try:
            await audit_logger.flush()
            await connection.close_db()
            if redis_client:
                await redis_client.close()
            logger.info("Graceful shutdown completed")
        except Exception as e:
            logger.error(f"Shutdown error: {e}", exc_info=True)


# Create FastAPI app
app = FastAPI(
    title="AgentGate",
    description="AI Agent Authentication & Authorization Gateway",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)


# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-RateLimit-Remaining"],
)


# Custom middleware for request/response tracking
@app.middleware("http")
async def request_logging_middleware(request: Request, call_next: Callable) -> JSONResponse:
    """
    Log request details and measure response time.

    Adds X-Request-ID header, measures latency, and logs to structured audit system.
    """
    request_id = request.headers.get("X-Request-ID", str(int(time.time() * 1000)))
    request.state.request_id = request_id

    start_time = time.time()

    try:
        response = await call_next(request)
        duration = time.time() - start_time

        # Log request
        logger.info(
            f"Request completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": f"{duration * 1000:.2f}",
            }
        )

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = str(duration)

        return response

    except Exception as e:
        duration = time.time() - start_time
        logger.error(
            f"Request failed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "error": str(e),
                "duration_ms": f"{duration * 1000:.2f}",
            },
            exc_info=True,
        )
        raise


# Rate limiting middleware
RATE_LIMIT_PER_MINUTE = 1000
RATE_LIMIT_WINDOW_SECONDS = 60


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next: Callable) -> JSONResponse:
    """
    Apply per-agent rate limiting using Redis sliding window counter.

    Limits: 1000 requests per 60-second window per agent identity.
    Health endpoints are exempt. Falls back to no limiting if Redis is unavailable.
    """
    # Skip rate limiting for health endpoints
    if request.url.path.startswith("/health"):
        return await call_next(request)

    # Skip if Redis is unavailable
    if not redis_client:
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(RATE_LIMIT_PER_MINUTE)
        response.headers["X-RateLimit-Remaining"] = "unknown"
        return response

    agent_id = getattr(request.state, "agent_id", "anonymous")
    rate_key = f"ratelimit:{agent_id}"

    try:
        current = await redis_client.incr(rate_key)
        if current == 1:
            await redis_client.expire(rate_key, RATE_LIMIT_WINDOW_SECONDS)

        remaining = max(0, RATE_LIMIT_PER_MINUTE - current)
        ttl = await redis_client.ttl(rate_key)

        if current > RATE_LIMIT_PER_MINUTE:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "detail": f"Limit: {RATE_LIMIT_PER_MINUTE} requests per {RATE_LIMIT_WINDOW_SECONDS}s",
                    "retry_after": max(ttl, 1),
                },
                headers={
                    "X-RateLimit-Limit": str(RATE_LIMIT_PER_MINUTE),
                    "X-RateLimit-Remaining": "0",
                    "Retry-After": str(max(ttl, 1)),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(RATE_LIMIT_PER_MINUTE)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response

    except Exception as e:
        logger.warning(f"Rate limiting error, allowing request: {e}")
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(RATE_LIMIT_PER_MINUTE)
        response.headers["X-RateLimit-Remaining"] = "unknown"
        return response


# Include routers
app.include_router(endpoints.agents.router, prefix="/api/v1/agents", tags=["agents"])
app.include_router(endpoints.policies.router, prefix="/api/v1/policies", tags=["policies"])
app.include_router(endpoints.secrets.router, prefix="/api/v1/secrets", tags=["secrets"])
app.include_router(endpoints.audit.router, prefix="/api/v1/audit", tags=["audit"])
app.include_router(endpoints.gateway.router, prefix="/api/v1/gateway", tags=["gateway"])


# Health check endpoints
@app.get("/health", status_code=status.HTTP_200_OK, tags=["health"])
async def health_check() -> dict:
    """
    Basic health check endpoint.

    Returns:
        dict: Server status
    """
    return {"status": "healthy", "version": "1.0.0"}


@app.get("/health/ready", status_code=status.HTTP_200_OK, tags=["health"])
async def readiness_check() -> dict:
    """
    Readiness probe - checks if all dependencies are healthy.

    Returns:
        dict: Readiness status with dependency checks
    """
    try:
        # Check database connectivity
        db_healthy = await connection.health_check()

        return {
            "status": "ready" if db_healthy else "not_ready",
            "database": "healthy" if db_healthy else "unhealthy",
            "timestamp": int(time.time()),
        }
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return {
            "status": "not_ready",
            "database": "unhealthy",
            "error": str(e),
        }, status.HTTP_503_SERVICE_UNAVAILABLE


@app.get("/health/live", status_code=status.HTTP_200_OK, tags=["health"])
async def liveness_check() -> dict:
    """
    Liveness probe - checks if service is running.

    Returns:
        dict: Liveness status
    """
    return {"status": "alive", "timestamp": int(time.time())}


# Exception handlers
@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """Handle validation errors."""
    logger.warning(f"Validation error: {exc}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc), "type": "validation_error"},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions."""
    request_id = getattr(request.state, "request_id", "unknown")
    logger.error(f"Unhandled exception [{request_id}]: {exc}", exc_info=True)

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Internal server error",
            "request_id": request_id,
        },
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=os.getenv("ENV", "production") == "development",
        log_level="info",
    )
