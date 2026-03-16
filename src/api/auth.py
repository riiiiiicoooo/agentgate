"""
Authentication Module

Implements OAuth 2.0 client credentials flow, JWT token issuance/validation,
API key authentication, and agent identity verification.
"""

import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from enum import Enum

import jwt
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)

# Configuration
JWT_ALGORITHM = "HS256"
JWT_SECRET = os.getenv("JWT_SECRET", "YOUR_JWT_SECRET_KEY_CHANGE_IN_PRODUCTION")
JWT_EXPIRATION_MINUTES = int(os.getenv("JWT_EXPIRATION_MINUTES", "60"))
API_KEY_PREFIX = "YOUR_AGENTGATE_KEY_"


class TokenType(str, Enum):
    """Token types."""
    ACCESS = "access"
    REFRESH = "refresh"
    API_KEY = "api_key"


class AuthenticationError(Exception):
    """Base authentication exception."""
    pass


class TokenInvalidError(AuthenticationError):
    """Token validation failed."""
    pass


class APIKeyValidationError(AuthenticationError):
    """API key validation failed."""
    pass


class AgentCredentials:
    """Represents authenticated agent credentials."""

    def __init__(
        self,
        agent_id: str,
        client_id: str,
        auth_type: str,
        scopes: list[str],
        issued_at: datetime,
        expires_at: datetime,
    ):
        self.agent_id = agent_id
        self.client_id = client_id
        self.auth_type = auth_type
        self.scopes = scopes
        self.issued_at = issued_at
        self.expires_at = expires_at

    def is_expired(self) -> bool:
        """Check if credentials are expired."""
        return datetime.now(timezone.utc) > self.expires_at

    def has_scope(self, required_scope: str) -> bool:
        """Check if credentials have required scope."""
        return required_scope in self.scopes or "*" in self.scopes


class TokenManager:
    """Manages JWT token creation and validation."""

    def __init__(self, secret: str = JWT_SECRET, algorithm: str = JWT_ALGORITHM):
        self.secret = secret
        self.algorithm = algorithm
        self.expiration_minutes = JWT_EXPIRATION_MINUTES

    def create_access_token(
        self,
        agent_id: str,
        client_id: str,
        scopes: list[str],
        expires_delta: Optional[timedelta] = None,
    ) -> str:
        """
        Create a JWT access token.

        Args:
            agent_id: Unique agent identifier
            client_id: OAuth client ID
            scopes: List of authorized scopes
            expires_delta: Custom expiration delta (default: JWT_EXPIRATION_MINUTES)

        Returns:
            str: Signed JWT token

        Raises:
            ValueError: If invalid parameters provided
        """
        if not agent_id or not client_id:
            raise ValueError("agent_id and client_id are required")

        if expires_delta is None:
            expires_delta = timedelta(minutes=self.expiration_minutes)

        now = datetime.now(timezone.utc)
        expires_at = now + expires_delta

        payload = {
            "agent_id": agent_id,
            "client_id": client_id,
            "scopes": scopes,
            "token_type": TokenType.ACCESS.value,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }

        try:
            token = jwt.encode(payload, self.secret, algorithm=self.algorithm)
            logger.info(f"Access token created for agent: {agent_id}")
            return token
        except Exception as e:
            logger.error(f"Failed to create access token: {e}")
            raise TokenInvalidError(f"Token creation failed: {e}")

    def create_refresh_token(self, agent_id: str, client_id: str) -> str:
        """
        Create a refresh token with longer expiration.

        Args:
            agent_id: Unique agent identifier
            client_id: OAuth client ID

        Returns:
            str: Signed refresh JWT token
        """
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=30)  # 30 day refresh token lifetime

        payload = {
            "agent_id": agent_id,
            "client_id": client_id,
            "token_type": TokenType.REFRESH.value,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }

        try:
            token = jwt.encode(payload, self.secret, algorithm=self.algorithm)
            logger.info(f"Refresh token created for agent: {agent_id}")
            return token
        except Exception as e:
            logger.error(f"Failed to create refresh token: {e}")
            raise TokenInvalidError(f"Refresh token creation failed: {e}")

    def validate_token(self, token: str) -> Dict[str, Any]:
        """
        Validate and decode a JWT token.

        Args:
            token: JWT token string

        Returns:
            dict: Decoded token payload

        Raises:
            TokenInvalidError: If token is invalid or expired
        """
        try:
            payload = jwt.decode(
                token,
                self.secret,
                algorithms=[self.algorithm],
            )
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning(f"Token expired")
            raise TokenInvalidError("Token has expired")
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            raise TokenInvalidError(f"Invalid token: {e}")

    def get_token_expiration(self, token: str) -> Optional[datetime]:
        """
        Get token expiration time without validation.

        Args:
            token: JWT token string

        Returns:
            datetime: Expiration timestamp or None
        """
        try:
            payload = jwt.decode(
                token,
                self.secret,
                algorithms=[self.algorithm],
                options={"verify_signature": False},
            )
            exp = payload.get("exp")
            return datetime.fromtimestamp(exp, tz=timezone.utc) if exp else None
        except Exception as e:
            logger.warning(f"Failed to extract expiration: {e}")
            return None


class APIKeyManager:
    """Manages API key generation and validation."""

    def __init__(self, prefix: str = API_KEY_PREFIX):
        self.prefix = prefix

    def generate_api_key(self, agent_id: str) -> str:
        """
        Generate a secure API key.

        Args:
            agent_id: Agent identifier for which key is generated

        Returns:
            str: Generated API key with prefix

        Raises:
            ValueError: If agent_id is invalid
        """
        if not agent_id:
            raise ValueError("agent_id is required")

        # Generate random component using HMAC
        timestamp = str(int(datetime.now(timezone.utc).timestamp()))
        random_component = hmac.new(
            JWT_SECRET.encode(),
            f"{agent_id}:{timestamp}".encode(),
            hashlib.sha256,
        ).hexdigest()[:32]

        api_key = f"{self.prefix}{random_component}"
        logger.info(f"API key generated for agent: {agent_id}")
        return api_key

    def validate_api_key(self, api_key: str) -> bool:
        """
        Validate API key format and existence.

        Args:
            api_key: API key to validate

        Returns:
            bool: True if valid format

        Raises:
            APIKeyValidationError: If key is invalid
        """
        if not api_key or not api_key.startswith(self.prefix):
            raise APIKeyValidationError("Invalid API key format")

        # Check length (prefix + 32 char hash)
        if len(api_key) != len(self.prefix) + 32:
            raise APIKeyValidationError("Invalid API key length")

        return True

    def hash_api_key(self, api_key: str) -> str:
        """
        Hash API key for storage.

        Args:
            api_key: Plain text API key

        Returns:
            str: SHA256 hash of API key
        """
        return hashlib.sha256(api_key.encode()).hexdigest()


class ClientCredentialsFlow:
    """
    OAuth 2.0 Client Credentials Flow Implementation.

    Used for agent-to-service authentication.
    """

    def __init__(self, token_manager: TokenManager):
        self.token_manager = token_manager

    async def exchange_credentials(
        self,
        client_id: str,
        client_secret: str,
        agent_id: str,
        scopes: list[str],
    ) -> Dict[str, Any]:
        """
        Exchange client credentials for access token.

        Args:
            client_id: OAuth client identifier
            client_secret: Client secret (must be verified before calling)
            agent_id: Agent identifier
            scopes: Requested scopes

        Returns:
            dict: Token response with access_token, refresh_token, expires_in

        Raises:
            AuthenticationError: If credentials are invalid
        """
        if not all([client_id, client_secret, agent_id]):
            raise AuthenticationError("Missing required credentials")

        # TODO: In production, verify client_secret against stored hash
        # For now, this would be done at the endpoint level

        try:
            access_token = self.token_manager.create_access_token(
                agent_id=agent_id,
                client_id=client_id,
                scopes=scopes or ["default"],
            )

            refresh_token = self.token_manager.create_refresh_token(
                agent_id=agent_id,
                client_id=client_id,
            )

            logger.info(f"Credentials exchanged for agent: {agent_id}")

            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "Bearer",
                "expires_in": JWT_EXPIRATION_MINUTES * 60,
            }

        except Exception as e:
            logger.error(f"Credentials exchange failed: {e}")
            raise AuthenticationError(f"Token exchange failed: {e}")

    async def refresh_access_token(
        self,
        refresh_token: str,
    ) -> Dict[str, Any]:
        """
        Refresh an access token using refresh token.

        Args:
            refresh_token: Valid refresh token

        Returns:
            dict: New token response

        Raises:
            AuthenticationError: If refresh token is invalid
        """
        try:
            payload = self.token_manager.validate_token(refresh_token)

            if payload.get("token_type") != TokenType.REFRESH.value:
                raise AuthenticationError("Token is not a refresh token")

            agent_id = payload.get("agent_id")
            client_id = payload.get("client_id")

            if not agent_id or not client_id:
                raise AuthenticationError("Invalid refresh token payload")

            new_access_token = self.token_manager.create_access_token(
                agent_id=agent_id,
                client_id=client_id,
                scopes=payload.get("scopes", ["default"]),
            )

            logger.info(f"Access token refreshed for agent: {agent_id}")

            return {
                "access_token": new_access_token,
                "token_type": "Bearer",
                "expires_in": JWT_EXPIRATION_MINUTES * 60,
            }

        except TokenInvalidError as e:
            logger.warning(f"Token refresh failed: {e}")
            raise AuthenticationError(f"Invalid refresh token: {e}")


# Dependency for FastAPI security
security = HTTPBearer()


async def get_current_agent(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> AgentCredentials:
    """
    FastAPI dependency to extract and validate agent credentials.

    Args:
        credentials: HTTP Bearer token from Authorization header

    Returns:
        AgentCredentials: Validated agent credentials

    Raises:
        HTTPException: If authentication fails
    """
    token_manager = TokenManager()

    try:
        payload = token_manager.validate_token(credentials.credentials)

        agent_id = payload.get("agent_id")
        client_id = payload.get("client_id")
        scopes = payload.get("scopes", [])
        iat = payload.get("iat")
        exp = payload.get("exp")

        if not agent_id or not client_id:
            raise TokenInvalidError("Missing required token claims")

        issued_at = datetime.fromtimestamp(iat, tz=timezone.utc)
        expires_at = datetime.fromtimestamp(exp, tz=timezone.utc)

        agent = AgentCredentials(
            agent_id=agent_id,
            client_id=client_id,
            auth_type="jwt",
            scopes=scopes,
            issued_at=issued_at,
            expires_at=expires_at,
        )

        logger.debug(f"Agent authenticated: {agent_id}")
        return agent

    except TokenInvalidError as e:
        logger.warning(f"Authentication failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_agent_with_scope(required_scope: str):
    """
    Factory for scope-based agent authentication.

    Args:
        required_scope: Required scope for endpoint

    Returns:
        Async function that validates agent has required scope
    """
    async def _get_agent(agent: AgentCredentials = Depends(get_current_agent)) -> AgentCredentials:
        if not agent.has_scope(required_scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required scope: {required_scope}",
            )
        return agent

    return _get_agent
