"""
OpenTelemetry Instrumentation for AgentGate
Provides tracing for auth flows, policy evaluation, secret leasing, and audit logging.
"""

from opentelemetry import trace, metrics, logs as otel_logs
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.api.metrics import Counter, Histogram
from datetime import datetime
from typing import Optional, Dict, Any
import logging
import time


# Configure resource
def create_resource():
    """Create OpenTelemetry resource with service information."""
    return Resource.create({
        "service.name": "agentgate",
        "service.version": "1.0.0",
        "service.instance.id": "agentgate-001",
        "deployment.environment": "production",
        "deployment.region": "us-east-1",
    })


# Initialize tracer
def init_tracing():
    """Initialize OpenTelemetry tracing."""
    resource = create_resource()

    # OTLP exporter
    otlp_exporter = OTLPSpanExporter(
        endpoint="localhost:4317",
        insecure=True
    )

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

    trace.set_tracer_provider(tracer_provider)

    return trace.get_tracer(__name__)


# Initialize metrics
def init_metrics():
    """Initialize OpenTelemetry metrics."""
    resource = create_resource()

    # Prometheus reader for scraping
    prometheus_reader = PrometheusMetricReader()

    # OTLP exporter
    otlp_exporter = OTLPMetricExporter(
        endpoint="localhost:4317",
        insecure=True
    )

    metric_reader = PeriodicExportingMetricReader(otlp_exporter, interval_millis=5000)

    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[prometheus_reader, metric_reader]
    )

    metrics.set_meter_provider(meter_provider)

    return metrics.get_meter(__name__)


class AuthenticationInstrumentation:
    """Instrumentation for authentication flows."""

    def __init__(self, tracer):
        self.tracer = tracer
        self.meter = metrics.get_meter(__name__)

        # Metrics
        self.auth_requests = self.meter.create_counter(
            "auth.requests.total",
            description="Total authentication requests",
            unit="1"
        )
        self.auth_failures = self.meter.create_counter(
            "auth.failures.total",
            description="Total authentication failures",
            unit="1"
        )
        self.auth_latency = self.meter.create_histogram(
            "auth.latency.milliseconds",
            description="Authentication latency in milliseconds",
            unit="ms"
        )
        self.token_issued = self.meter.create_counter(
            "auth.tokens.issued.total",
            description="Total tokens issued",
            unit="1"
        )
        self.token_expired = self.meter.create_counter(
            "auth.tokens.expired.total",
            description="Total expired tokens",
            unit="1"
        )

    def trace_oauth_flow(self, client_id: str, scopes: list):
        """Trace OAuth client credentials flow."""
        with self.tracer.start_as_current_span("oauth_client_credentials_flow") as span:
            span.set_attribute("client_id", client_id)
            span.set_attribute("scopes_requested", len(scopes))
            span.set_attribute("scopes", ",".join(scopes))

            start_time = time.time()

            try:
                # Simulate token validation
                span.add_event("token_validation_started")
                time.sleep(0.01)  # Simulate work
                span.add_event("token_validation_completed", {"status": "valid"})

                # Simulate scope validation
                span.add_event("scope_validation_started")
                time.sleep(0.01)
                span.add_event("scope_validation_completed", {"status": "valid"})

                # Token issued
                self.token_issued.add(1, {"client_id": client_id})
                self.auth_requests.add(1, {"status": "success"})

                latency_ms = (time.time() - start_time) * 1000
                self.auth_latency.record(latency_ms)

                span.set_attribute("status", "success")
                span.set_attribute("latency_ms", latency_ms)

            except Exception as e:
                span.set_attribute("status", "failed")
                span.set_attribute("error", str(e))
                self.auth_failures.add(1, {"client_id": client_id})
                raise

    def trace_jwt_validation(self, token: str):
        """Trace JWT token validation."""
        with self.tracer.start_as_current_span("jwt_validation") as span:
            span.set_attribute("token_length", len(token))

            try:
                # Validate signature
                span.add_event("signature_validation")
                time.sleep(0.005)

                # Validate claims
                span.add_event("claims_validation")
                time.sleep(0.005)

                # Validate expiry
                span.add_event("expiry_validation")
                time.sleep(0.005)

                span.set_attribute("status", "valid")

            except Exception as e:
                if "expired" in str(e).lower():
                    self.token_expired.add(1)
                    span.set_attribute("expiry_status", "expired")
                span.set_attribute("status", "invalid")
                raise


class PolicyEngineInstrumentation:
    """Instrumentation for policy evaluation."""

    def __init__(self, tracer):
        self.tracer = tracer
        self.meter = metrics.get_meter(__name__)

        # Metrics
        self.policy_evals = self.meter.create_counter(
            "policy.evaluations.total",
            description="Total policy evaluations",
            unit="1"
        )
        self.policy_allows = self.meter.create_counter(
            "policy.allows.total",
            description="Total policy allows",
            unit="1"
        )
        self.policy_denies = self.meter.create_counter(
            "policy.denies.total",
            description="Total policy denies",
            unit="1"
        )
        self.policy_eval_latency = self.meter.create_histogram(
            "policy.evaluation.latency.milliseconds",
            description="Policy evaluation latency",
            unit="ms"
        )
        self.cache_hits = self.meter.create_counter(
            "policy.cache.hits.total",
            description="Policy cache hits",
            unit="1"
        )
        self.cache_misses = self.meter.create_counter(
            "policy.cache.misses.total",
            description="Policy cache misses",
            unit="1"
        )

    def trace_policy_evaluation(self, agent_type: str, action: str, resource: str):
        """Trace policy evaluation."""
        with self.tracer.start_as_current_span("policy_evaluation") as span:
            span.set_attribute("agent_type", agent_type)
            span.set_attribute("action", action)
            span.set_attribute("resource", resource)

            start_time = time.time()

            try:
                # Check cache
                span.add_event("cache_lookup")
                cache_hit = True  # Simulate cache hit 80% of time
                span.set_attribute("cache_hit", cache_hit)

                if cache_hit:
                    self.cache_hits.add(1)
                else:
                    self.cache_misses.add(1)
                    # Compile policy
                    span.add_event("policy_compilation")
                    time.sleep(0.002)

                # Evaluate policy
                span.add_event("policy_evaluation_started")
                time.sleep(0.005)

                # Determine decision
                decision = "ALLOW"  # Simulate logic
                span.add_event("policy_decision", {"decision": decision})

                if decision == "ALLOW":
                    self.policy_allows.add(1, {"action": action})
                else:
                    self.policy_denies.add(1, {"action": action})

                self.policy_evals.add(1)

                latency_ms = (time.time() - start_time) * 1000
                self.policy_eval_latency.record(latency_ms)

                span.set_attribute("decision", decision)
                span.set_attribute("latency_ms", latency_ms)

            except Exception as e:
                span.set_attribute("error", str(e))
                raise


class SecretsBrokerInstrumentation:
    """Instrumentation for secret leasing."""

    def __init__(self, tracer):
        self.tracer = tracer
        self.meter = metrics.get_meter(__name__)

        # Metrics
        self.secret_leases = self.meter.create_counter(
            "secrets.leases.total",
            description="Total secret leases",
            unit="1"
        )
        self.secret_lease_failures = self.meter.create_counter(
            "secrets.lease.failures.total",
            description="Total secret lease failures",
            unit="1"
        )
        self.secret_access_denied = self.meter.create_counter(
            "secrets.access.denied.total",
            description="Total denied secret accesses",
            unit="1"
        )
        self.secret_rotation_latency = self.meter.create_histogram(
            "secrets.rotation.latency.milliseconds",
            description="Secret rotation latency",
            unit="ms"
        )
        self.active_leases = self.meter.create_up_down_counter(
            "secrets.active_leases",
            description="Currently active secret leases",
            unit="1"
        )

    def trace_secret_lease(self, agent_id: str, secret_id: str, ttl_seconds: int):
        """Trace secret lease request."""
        with self.tracer.start_as_current_span("secret_lease") as span:
            span.set_attribute("agent_id", agent_id)
            span.set_attribute("secret_id", secret_id)
            span.set_attribute("ttl_seconds", ttl_seconds)

            try:
                # Authorization check
                span.add_event("authorization_check")
                time.sleep(0.003)

                # Retrieve secret
                span.add_event("secret_retrieval")
                time.sleep(0.010)

                # Create lease
                span.add_event("lease_creation")
                lease_id = "lease-001"
                span.set_attribute("lease_id", lease_id)

                self.secret_leases.add(1, {"secret_id": secret_id})
                self.active_leases.add(1)

                span.set_attribute("status", "success")

            except PermissionError as e:
                span.set_attribute("status", "denied")
                self.secret_access_denied.add(1)
                raise
            except Exception as e:
                span.set_attribute("status", "failed")
                span.set_attribute("error", str(e))
                self.secret_lease_failures.add(1)
                raise

    def trace_secret_rotation(self, secret_id: str):
        """Trace secret rotation."""
        with self.tracer.start_as_current_span("secret_rotation") as span:
            span.set_attribute("secret_id", secret_id)

            start_time = time.time()

            # Generate new version
            span.add_event("new_version_generation")
            time.sleep(0.015)

            # Validate new version
            span.add_event("validation")
            time.sleep(0.010)

            # Store new version
            span.add_event("storage")
            time.sleep(0.020)

            # Invalidate old leases
            span.add_event("lease_invalidation")
            self.active_leases.add(-1)

            latency_ms = (time.time() - start_time) * 1000
            self.secret_rotation_latency.record(latency_ms)

            span.set_attribute("latency_ms", latency_ms)


class AuditInstrumentation:
    """Instrumentation for audit logging."""

    def __init__(self, tracer):
        self.tracer = tracer
        self.meter = metrics.get_meter(__name__)

        # Metrics
        self.audit_events = self.meter.create_counter(
            "audit.events.total",
            description="Total audit events",
            unit="1"
        )
        self.audit_allowed = self.meter.create_counter(
            "audit.decisions.allowed.total",
            description="Total allowed decisions",
            unit="1"
        )
        self.audit_denied = self.meter.create_counter(
            "audit.decisions.denied.total",
            description="Total denied decisions",
            unit="1"
        )
        self.audit_write_latency = self.meter.create_histogram(
            "audit.write.latency.milliseconds",
            description="Audit event write latency",
            unit="ms"
        )

    def trace_audit_event(self, agent_id: str, action: str, decision: str):
        """Trace audit event logging."""
        with self.tracer.start_as_current_span("audit_event_logging") as span:
            span.set_attribute("agent_id", agent_id)
            span.set_attribute("action", action)
            span.set_attribute("decision", decision)

            start_time = time.time()

            try:
                # Enrich event
                span.add_event("event_enrichment")
                time.sleep(0.005)

                # Serialize event
                span.add_event("event_serialization")
                time.sleep(0.002)

                # Write to database
                span.add_event("database_write")
                time.sleep(0.020)

                # Write to stream
                span.add_event("stream_write")
                time.sleep(0.010)

                self.audit_events.add(1)

                if decision == "ALLOW":
                    self.audit_allowed.add(1, {"action": action})
                else:
                    self.audit_denied.add(1, {"action": action})

                latency_ms = (time.time() - start_time) * 1000
                self.audit_write_latency.record(latency_ms)

                span.set_attribute("latency_ms", latency_ms)

            except Exception as e:
                span.set_attribute("error", str(e))
                raise


class GatewayInstrumentation:
    """Instrumentation for gateway operations."""

    def __init__(self, tracer):
        self.tracer = tracer
        self.meter = metrics.get_meter(__name__)

        # Metrics
        self.requests_total = self.meter.create_counter(
            "gateway.requests.total",
            description="Total gateway requests",
            unit="1"
        )
        self.request_latency = self.meter.create_histogram(
            "gateway.request.latency.milliseconds",
            description="Request latency",
            unit="ms"
        )
        self.rate_limit_exceeded = self.meter.create_counter(
            "gateway.rate_limit.exceeded.total",
            description="Rate limit exceeded",
            unit="1"
        )
        self.injections_detected = self.meter.create_counter(
            "gateway.injections.detected.total",
            description="Prompt injections detected",
            unit="1"
        )

    def trace_request(self, method: str, path: str):
        """Trace incoming request."""
        with self.tracer.start_as_current_span("http_request") as span:
            span.set_attribute("http.method", method)
            span.set_attribute("http.url", path)

            start_time = time.time()

            try:
                # Request processing
                span.add_event("authentication")
                time.sleep(0.010)

                span.add_event("authorization")
                time.sleep(0.008)

                span.add_event("execution")
                time.sleep(0.020)

                self.requests_total.add(1)

                latency_ms = (time.time() - start_time) * 1000
                self.request_latency.record(latency_ms)

                span.set_attribute("status", "success")
                span.set_attribute("latency_ms", latency_ms)

            except Exception as e:
                span.set_attribute("error", str(e))
                raise


# Global instrumentation instances
tracer = None
auth_instrumentation = None
policy_instrumentation = None
secrets_instrumentation = None
audit_instrumentation = None
gateway_instrumentation = None


def initialize_instrumentation():
    """Initialize all instrumentation."""
    global tracer
    global auth_instrumentation
    global policy_instrumentation
    global secrets_instrumentation
    global audit_instrumentation
    global gateway_instrumentation

    tracer = init_tracing()
    init_metrics()

    # Initialize instrumentation classes
    auth_instrumentation = AuthenticationInstrumentation(tracer)
    policy_instrumentation = PolicyEngineInstrumentation(tracer)
    secrets_instrumentation = SecretsBrokerInstrumentation(tracer)
    audit_instrumentation = AuditInstrumentation(tracer)
    gateway_instrumentation = GatewayInstrumentation(tracer)

    # Auto-instrument libraries
    FastAPIInstrumentor().instrument()
    RequestsInstrumentor().instrument()
    SQLAlchemyInstrumentor().instrument()
    RedisInstrumentor().instrument()
    Psycopg2Instrumentor().instrument()

    logging.info("OpenTelemetry instrumentation initialized")
