"""
Token Management

JWT creation, validation, and refresh token flow.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
import os

import jwt

logger = logging.getLogger(__name__)

JWT_SECRET = os.getenv("JWT_SECRET", "YOUR_JWT_SECRET_KEY_CHANGE_IN_PRODUCTION")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRY = 3600  # 1 hour
REFRESH_TOKEN_EXPIRY = 2592000  # 30 days


class TokenPayload:
    """JWT token payload."""

    def __init__(
        self,
        agent_id: str,
        client_id: str,
        scopes: list[str],
        token_type: str,
        iat: int,
        exp: int,
    ):
        self.agent_id = agent_id
        self.client_id = client_id
        self.scopes = scopes
        self.token_type = token_type
        self.iat = iat
        self.exp = exp

    def is_expired(self) -> bool:
        """Check if token is expired."""
        import time
        return time.time() > self.exp

    def has_scope(self, scope: str) -> bool:
        """Check if token has scope."""
        return scope in self.scopes or "*" in self.scopes


class TokenProvider:
    """JWT token provider."""

    def __init__(
        self,
        secret: str = JWT_SECRET,
        algorithm: str = JWT_ALGORITHM,
        access_ttl: int = ACCESS_TOKEN_EXPIRY,
        refresh_ttl: int = REFRESH_TOKEN_EXPIRY,
    ):
        self.secret = secret
        self.algorithm = algorithm
        self.access_ttl = access_ttl
        self.refresh_ttl = refresh_ttl

        logger.info("TokenProvider initialized")

    def create_access_token(
        self,
        agent_id: str,
        client_id: str,
        scopes: list[str],
    ) -> str:
        """
        Create access token.

        Args:
            agent_id: Agent ID
            client_id: Client ID
            scopes: Token scopes

        Returns:
            str: JWT token
        """
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=self.access_ttl)

        payload = {
            "agent_id": agent_id,
            "client_id": client_id,
            "scopes": scopes,
            "token_type": "access",
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }

        token = jwt.encode(payload, self.secret, algorithm=self.algorithm)

        logger.debug(f"Access token created for: {agent_id}")

        return token

    def create_refresh_token(
        self,
        agent_id: str,
        client_id: str,
    ) -> str:
        """
        Create refresh token.

        Args:
            agent_id: Agent ID
            client_id: Client ID

        Returns:
            str: JWT refresh token
        """
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=self.refresh_ttl)

        payload = {
            "agent_id": agent_id,
            "client_id": client_id,
            "token_type": "refresh",
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }

        token = jwt.encode(payload, self.secret, algorithm=self.algorithm)

        logger.debug(f"Refresh token created for: {agent_id}")

        return token

    def verify_token(self, token: str) -> Optional[TokenPayload]:
        """
        Verify and decode token.

        Args:
            token: JWT token

        Returns:
            TokenPayload if valid, None otherwise
        """
        try:
            payload = jwt.decode(
                token,
                self.secret,
                algorithms=[self.algorithm],
            )

            token_payload = TokenPayload(
                agent_id=payload["agent_id"],
                client_id=payload["client_id"],
                scopes=payload.get("scopes", []),
                token_type=payload.get("token_type", "access"),
                iat=payload["iat"],
                exp=payload["exp"],
            )

            logger.debug(f"Token verified for: {token_payload.agent_id}")

            return token_payload

        except jwt.ExpiredSignatureError:
            logger.warning("Token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            return None

    def refresh_access_token(self, refresh_token: str) -> Optional[str]:
        """
        Create new access token from refresh token.

        Args:
            refresh_token: Valid refresh token

        Returns:
            str: New access token or None
        """
        payload = self.verify_token(refresh_token)

        if not payload:
            logger.warning("Refresh token verification failed")
            return None

        if payload.token_type != "refresh":
            logger.warning("Token is not a refresh token")
            return None

        new_token = self.create_access_token(
            agent_id=payload.agent_id,
            client_id=payload.client_id,
            scopes=payload.scopes,
        )

        logger.info(f"Access token refreshed for: {payload.agent_id}")

        return new_token

    def get_token_info(self, token: str) -> Optional[Dict[str, Any]]:
        """Get information about token without verification."""
        try:
            payload = jwt.decode(
                token,
                self.secret,
                algorithms=[self.algorithm],
                options={"verify_signature": False},
            )

            return {
                "agent_id": payload.get("agent_id"),
                "client_id": payload.get("client_id"),
                "scopes": payload.get("scopes", []),
                "token_type": payload.get("token_type"),
                "issued_at": datetime.fromtimestamp(
                    payload.get("iat"), tz=timezone.utc
                ).isoformat(),
                "expires_at": datetime.fromtimestamp(
                    payload.get("exp"), tz=timezone.utc
                ).isoformat(),
            }

        except Exception as e:
            logger.warning(f"Failed to decode token: {e}")
            return None
