"""
Agent Identity Manager

Manages agent registration, credential lifecycle, and OAuth client management.
"""

import logging
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Tuple
from uuid import uuid4

logger = logging.getLogger(__name__)


class AgentIdentity:
    """Represents an agent's identity and credentials."""

    def __init__(
        self,
        agent_id: str,
        name: str,
        client_id: str,
        client_secret_hash: str,
    ):
        self.agent_id = agent_id
        self.name = name
        self.client_id = client_id
        self.client_secret_hash = client_secret_hash
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)
        self.last_auth = None
        self.api_keys: list[str] = []
        self.is_active = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "client_id": self.client_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "last_auth": self.last_auth.isoformat() if self.last_auth else None,
            "is_active": self.is_active,
            "api_key_count": len(self.api_keys),
        }


class IdentityManager:
    """
    Manages agent identities and credentials.

    Handles:
    - Agent registration and deregistration
    - Client secret management
    - API key lifecycle
    - OAuth client configuration
    """

    def __init__(self):
        self.agents: Dict[str, AgentIdentity] = {}
        self.client_id_to_agent: Dict[str, str] = {}  # client_id -> agent_id

        logger.info("IdentityManager initialized")

    async def register_agent(
        self,
        name: str,
        scopes: list[str],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, str, str]:
        """
        Register a new agent.

        Args:
            name: Agent name
            scopes: Authorized scopes
            metadata: Agent metadata

        Returns:
            tuple: (agent_id, client_id, client_secret)

        Raises:
            ValueError: If agent already exists
        """
        agent_id = f"agent_{uuid4()}"
        client_id = f"YOUR_AGENTGATE_CLIENT_ID_{uuid4().hex[:12]}"
        client_secret = f"YOUR_AGENTGATE_SECRET_{uuid4().hex[:32]}"

        # Hash secret for storage
        client_secret_hash = hashlib.sha256(client_secret.encode()).hexdigest()

        agent = AgentIdentity(
            agent_id=agent_id,
            name=name,
            client_id=client_id,
            client_secret_hash=client_secret_hash,
        )

        self.agents[agent_id] = agent
        self.client_id_to_agent[client_id] = agent_id

        logger.info(
            f"Agent registered: {agent_id} (name={name}, client_id={client_id})"
        )

        return agent_id, client_id, client_secret

    async def verify_client_secret(
        self,
        client_id: str,
        client_secret: str,
    ) -> Optional[str]:
        """
        Verify client credentials.

        Args:
            client_id: OAuth client ID
            client_secret: OAuth client secret

        Returns:
            str: Agent ID if valid, None otherwise
        """
        agent_id = self.client_id_to_agent.get(client_id)

        if not agent_id:
            logger.warning(f"Client ID not found: {client_id}")
            return None

        agent = self.agents.get(agent_id)

        if not agent:
            logger.error(f"Agent not found for client: {client_id}")
            return None

        # Verify secret hash
        secret_hash = hashlib.sha256(client_secret.encode()).hexdigest()

        if secret_hash != agent.client_secret_hash:
            logger.warning(f"Invalid client secret for: {client_id}")
            return None

        # Update last auth
        agent.last_auth = datetime.now(timezone.utc)
        agent.updated_at = datetime.now(timezone.utc)

        logger.debug(f"Client verified: {client_id}")

        return agent_id

    async def rotate_client_secret(self, agent_id: str) -> str:
        """
        Rotate client secret for an agent.

        Args:
            agent_id: Agent whose secret to rotate

        Returns:
            str: New client secret

        Raises:
            ValueError: If agent not found
        """
        agent = self.agents.get(agent_id)

        if not agent:
            raise ValueError(f"Agent not found: {agent_id}")

        new_secret = f"YOUR_AGENTGATE_SECRET_{uuid4().hex[:32]}"
        agent.client_secret_hash = hashlib.sha256(new_secret.encode()).hexdigest()
        agent.updated_at = datetime.now(timezone.utc)

        logger.info(f"Client secret rotated for: {agent_id}")

        return new_secret

    async def generate_api_key(self, agent_id: str) -> str:
        """
        Generate a new API key for an agent.

        Args:
            agent_id: Agent to generate key for

        Returns:
            str: New API key

        Raises:
            ValueError: If agent not found
        """
        agent = self.agents.get(agent_id)

        if not agent:
            raise ValueError(f"Agent not found: {agent_id}")

        api_key = f"YOUR_AGENTGATE_KEY_{uuid4().hex[:32]}"

        # Store key hash
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        agent.api_keys.append(key_hash)
        agent.updated_at = datetime.now(timezone.utc)

        logger.info(f"API key generated for: {agent_id}")

        return api_key

    async def verify_api_key(self, api_key: str) -> Optional[str]:
        """
        Verify an API key and return agent ID.

        Args:
            api_key: API key to verify

        Returns:
            str: Agent ID if valid, None otherwise
        """
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()

        for agent_id, agent in self.agents.items():
            if key_hash in agent.api_keys:
                logger.debug(f"API key verified for: {agent_id}")
                agent.last_auth = datetime.now(timezone.utc)
                return agent_id

        logger.warning("Invalid API key")
        return None

    async def revoke_api_key(self, agent_id: str, api_key: str) -> bool:
        """
        Revoke an API key.

        Args:
            agent_id: Agent owning the key
            api_key: Key to revoke

        Returns:
            bool: True if revoked, False if not found
        """
        agent = self.agents.get(agent_id)

        if not agent:
            raise ValueError(f"Agent not found: {agent_id}")

        key_hash = hashlib.sha256(api_key.encode()).hexdigest()

        if key_hash in agent.api_keys:
            agent.api_keys.remove(key_hash)
            agent.updated_at = datetime.now(timezone.utc)

            logger.info(f"API key revoked for: {agent_id}")
            return True

        return False

    async def deactivate_agent(self, agent_id: str) -> None:
        """
        Deactivate an agent (revoke all credentials).

        Args:
            agent_id: Agent to deactivate

        Raises:
            ValueError: If agent not found
        """
        agent = self.agents.get(agent_id)

        if not agent:
            raise ValueError(f"Agent not found: {agent_id}")

        agent.is_active = False
        agent.api_keys.clear()
        agent.updated_at = datetime.now(timezone.utc)

        logger.warning(f"Agent deactivated: {agent_id}")

    async def get_agent_info(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get agent information."""
        agent = self.agents.get(agent_id)
        return agent.to_dict() if agent else None

    async def list_agents(self) -> list[Dict[str, Any]]:
        """List all agents."""
        return [agent.to_dict() for agent in self.agents.values()]

    def get_stats(self) -> Dict[str, Any]:
        """Get identity manager statistics."""
        active_count = sum(1 for a in self.agents.values() if a.is_active)

        return {
            "total_agents": len(self.agents),
            "active_agents": active_count,
            "total_api_keys": sum(len(a.api_keys) for a in self.agents.values()),
        }
