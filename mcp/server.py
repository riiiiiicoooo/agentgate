"""
MCP Server for AgentGate

Model Context Protocol server exposing AgentGate capabilities as tools:
- authenticate_agent
- request_secret
- check_policy
- query_audit_log
- register_agent
"""

import logging
from typing import Any, Dict, Optional
from datetime import datetime, timezone
import json

logger = logging.getLogger(__name__)


class AgentGateMCPServer:
    """MCP Server for AgentGate integration."""

    def __init__(self, api_base_url: str = "http://localhost:8000"):
        self.api_base_url = api_base_url
        self.tools = self._define_tools()

    def _define_tools(self) -> list[Dict[str, Any]]:
        """Define MCP tools."""
        return [
            {
                "name": "authenticate_agent",
                "description": "Authenticate an agent using OAuth 2.0 client credentials",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "client_id": {
                            "type": "string",
                            "description": "OAuth client ID",
                        },
                        "client_secret": {
                            "type": "string",
                            "description": "OAuth client secret",
                        },
                        "scopes": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Requested scopes",
                        },
                    },
                    "required": ["client_id", "client_secret"],
                },
            },
            {
                "name": "request_secret",
                "description": "Request access to a secret with automatic expiration",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "secret_name": {
                            "type": "string",
                            "description": "Name of the secret to request",
                        },
                        "ttl_seconds": {
                            "type": "integer",
                            "description": "Time-to-live in seconds",
                        },
                        "justification": {
                            "type": "string",
                            "description": "Business justification",
                        },
                    },
                    "required": ["secret_name"],
                },
            },
            {
                "name": "check_policy",
                "description": "Check if an agent action is allowed by policy",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "agent_id": {
                            "type": "string",
                            "description": "Agent ID",
                        },
                        "action": {
                            "type": "string",
                            "description": "Action to check",
                        },
                        "resource": {
                            "type": "string",
                            "description": "Resource being accessed",
                        },
                        "policies": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Policy IDs to evaluate",
                        },
                    },
                    "required": ["agent_id", "action", "resource", "policies"],
                },
            },
            {
                "name": "query_audit_log",
                "description": "Query audit logs for compliance and investigation",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "event_type": {
                            "type": "string",
                            "description": "Filter by event type",
                        },
                        "actor_agent_id": {
                            "type": "string",
                            "description": "Filter by actor",
                        },
                        "resource_id": {
                            "type": "string",
                            "description": "Filter by resource",
                        },
                        "severity": {
                            "type": "string",
                            "enum": ["info", "warning", "error", "critical"],
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max results",
                        },
                    },
                },
            },
            {
                "name": "register_agent",
                "description": "Register a new AI agent",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Agent name",
                        },
                        "description": {
                            "type": "string",
                            "description": "Agent description",
                        },
                        "scopes": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Authorized scopes",
                        },
                    },
                    "required": ["name"],
                },
            },
        ]

    async def handle_authenticate_agent(
        self,
        client_id: str,
        client_secret: str,
        scopes: Optional[list[str]] = None,
    ) -> Dict[str, Any]:
        """
        Authenticate an agent.

        Args:
            client_id: OAuth client ID
            client_secret: OAuth client secret
            scopes: Requested scopes

        Returns:
            dict: Token response
        """
        # In production, call actual API
        # For demo, return mock response
        return {
            "access_token": f"YOUR_AGENTGATE_TOKEN_{datetime.now(timezone.utc).isoformat()}",
            "refresh_token": f"YOUR_AGENTGATE_REFRESH_{datetime.now(timezone.utc).isoformat()}",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scopes": scopes or ["default"],
        }

    async def handle_request_secret(
        self,
        secret_name: str,
        ttl_seconds: int = 3600,
        justification: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Request a secret lease.

        Args:
            secret_name: Name of secret
            ttl_seconds: Time-to-live
            justification: Business justification

        Returns:
            dict: Secret lease
        """
        # In production, call actual API
        return {
            "lease_id": f"lease_{datetime.now(timezone.utc).timestamp()}",
            "secret_name": secret_name,
            "secret_value": f"YOUR_SECRET_VALUE_FOR_{secret_name}",
            "ttl_seconds": ttl_seconds,
            "issued_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": (
                datetime.now(timezone.utc).isoformat()
            ),
            "renewable": True,
        }

    async def handle_check_policy(
        self,
        agent_id: str,
        action: str,
        resource: str,
        policies: list[str],
    ) -> Dict[str, Any]:
        """
        Check if action is allowed by policy.

        Args:
            agent_id: Agent ID
            action: Action to check
            resource: Resource being accessed
            policies: Policy IDs to evaluate

        Returns:
            dict: Policy decision
        """
        # In production, call actual API
        return {
            "agent_id": agent_id,
            "action": action,
            "resource": resource,
            "decision": "allow",
            "reason": "Policy evaluation passed",
            "matching_rules": 1,
        }

    async def handle_query_audit_log(
        self,
        event_type: Optional[str] = None,
        actor_agent_id: Optional[str] = None,
        resource_id: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """
        Query audit logs.

        Args:
            event_type: Filter by event type
            actor_agent_id: Filter by actor
            resource_id: Filter by resource
            severity: Filter by severity
            limit: Max results

        Returns:
            dict: Audit events
        """
        # In production, call actual API
        return {
            "events": [
                {
                    "event_id": f"evt_{i}",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "event_type": event_type or "access",
                    "actor_agent_id": actor_agent_id or "agent_000",
                    "action": "read",
                    "status": "success",
                    "severity": severity or "info",
                }
                for i in range(min(3, limit))
            ],
            "total": 3,
            "offset": 0,
            "limit": limit,
        }

    async def handle_register_agent(
        self,
        name: str,
        description: Optional[str] = None,
        scopes: Optional[list[str]] = None,
    ) -> Dict[str, Any]:
        """
        Register a new agent.

        Args:
            name: Agent name
            description: Agent description
            scopes: Authorized scopes

        Returns:
            dict: Agent details with credentials
        """
        # In production, call actual API
        return {
            "agent_id": f"agent_{datetime.now(timezone.utc).timestamp()}",
            "name": name,
            "description": description,
            "client_id": f"YOUR_AGENTGATE_CLIENT_ID_{datetime.now(timezone.utc).timestamp()}",
            "status": "active",
            "scopes": scopes or ["default"],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "message": "Agent registered successfully. Store credentials securely.",
        }

    async def handle_tool_call(self, tool_name: str, **kwargs) -> str:
        """
        Handle a tool call from MCP.

        Args:
            tool_name: Name of tool to call
            **kwargs: Tool arguments

        Returns:
            str: JSON response
        """
        try:
            if tool_name == "authenticate_agent":
                result = await self.handle_authenticate_agent(**kwargs)
            elif tool_name == "request_secret":
                result = await self.handle_request_secret(**kwargs)
            elif tool_name == "check_policy":
                result = await self.handle_check_policy(**kwargs)
            elif tool_name == "query_audit_log":
                result = await self.handle_query_audit_log(**kwargs)
            elif tool_name == "register_agent":
                result = await self.handle_register_agent(**kwargs)
            else:
                result = {"error": f"Unknown tool: {tool_name}"}

            logger.info(f"Tool call handled: {tool_name}")
            return json.dumps(result)

        except Exception as e:
            logger.error(f"Tool call failed: {tool_name}: {e}", exc_info=True)
            return json.dumps({"error": str(e)})


# Create global server instance
mcp_server = AgentGateMCPServer()


def get_tools() -> list[Dict[str, Any]]:
    """Get list of available tools."""
    return mcp_server.tools


async def call_tool(tool_name: str, **kwargs) -> str:
    """Call a tool."""
    return await mcp_server.handle_tool_call(tool_name, **kwargs)
