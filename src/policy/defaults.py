"""
Default Baseline Policies

Provides least-privilege, break-glass, and read-only agent policies.
"""

# Default policies included with AgentGate
DEFAULT_POLICIES = [
    {
        "id": "policy_least_privilege",
        "name": "Least Privilege Baseline",
        "description": "Default deny-all policy requiring explicit allow rules",
        "rules": [
            {
                "effect": "deny",
                "actions": ["*"],
                "resources": ["*"],
                "conditions": [
                    {
                        "field": "action",
                        "operator": "eq",
                        "value": "*",
                    }
                ],
            }
        ],
    },
    {
        "id": "policy_read_only",
        "name": "Read-Only Agent Policy",
        "description": "Allow read-only access to resources",
        "rules": [
            {
                "effect": "allow",
                "actions": ["read", "list"],
                "resources": ["secret:*", "policy:*"],
                "conditions": [],
            },
            {
                "effect": "deny",
                "actions": ["write", "delete", "rotate"],
                "resources": ["*"],
                "conditions": [],
            },
        ],
    },
    {
        "id": "policy_break_glass",
        "name": "Emergency Break-Glass",
        "description": "Temporary elevated access for incident response",
        "rules": [
            {
                "effect": "allow",
                "actions": ["*"],
                "resources": ["*"],
                "conditions": [
                    {
                        "field": "emergency_mode",
                        "operator": "eq",
                        "value": "true",
                    },
                    {
                        "field": "approval_id",
                        "operator": "matches",
                        "value": "^approval_.*",
                    },
                ],
            }
        ],
    },
    {
        "id": "policy_secret_access",
        "name": "Secret Access Policy",
        "description": "Control secret leasing and rotation",
        "rules": [
            {
                "effect": "allow",
                "actions": ["read", "request", "renew"],
                "resources": ["secret:*"],
                "conditions": [
                    {
                        "field": "agent.tier",
                        "operator": "in",
                        "value": "trusted,premium",
                    }
                ],
            },
            {
                "effect": "allow",
                "actions": ["rotate"],
                "resources": ["secret:*"],
                "conditions": [
                    {
                        "field": "agent.role",
                        "operator": "eq",
                        "value": "admin",
                    }
                ],
            },
            {
                "effect": "deny",
                "actions": ["*"],
                "resources": ["secret:password/*", "secret:key/*"],
                "conditions": [
                    {
                        "field": "agent.tier",
                        "operator": "eq",
                        "value": "basic",
                    }
                ],
            },
        ],
    },
    {
        "id": "policy_audit_access",
        "name": "Audit Log Access",
        "description": "Control who can access audit logs",
        "rules": [
            {
                "effect": "allow",
                "actions": ["read", "query"],
                "resources": ["audit:*"],
                "conditions": [
                    {
                        "field": "agent.role",
                        "operator": "in",
                        "value": "admin,auditor,security",
                    }
                ],
            },
        ],
    },
    {
        "id": "policy_api_rate_limit",
        "name": "API Rate Limiting",
        "description": "Restrict request rates by tier",
        "rules": [
            {
                "effect": "allow",
                "actions": ["api_call"],
                "resources": ["api:*"],
                "conditions": [
                    {
                        "field": "rate_limit",
                        "operator": "lt",
                        "value": "1000_per_hour",
                    }
                ],
            },
        ],
    },
]


# Policy templates for common use cases
POLICY_TEMPLATES = {
    "backend_service": {
        "name": "Backend Service",
        "rules": [
            {
                "effect": "allow",
                "actions": ["read", "write"],
                "resources": ["secret:database/*", "secret:cache/*"],
                "conditions": [
                    {
                        "field": "agent.team",
                        "operator": "eq",
                        "value": "backend",
                    }
                ],
            }
        ],
    },
    "ml_model": {
        "name": "ML Model Access",
        "rules": [
            {
                "effect": "allow",
                "actions": ["read"],
                "resources": ["secret:ml/model/*", "secret:ml/key/*"],
                "conditions": [
                    {
                        "field": "agent.service",
                        "operator": "eq",
                        "value": "ml_inference",
                    }
                ],
            },
            {
                "effect": "allow",
                "actions": ["write"],
                "resources": ["secret:ml/results/*"],
                "conditions": [],
            },
        ],
    },
    "data_pipeline": {
        "name": "Data Pipeline",
        "rules": [
            {
                "effect": "allow",
                "actions": ["read", "write"],
                "resources": ["secret:data/*", "secret:warehouse/*"],
                "conditions": [
                    {
                        "field": "agent.team",
                        "operator": "eq",
                        "value": "data",
                    }
                ],
            }
        ],
    },
    "third_party_integration": {
        "name": "Third-Party Integration",
        "rules": [
            {
                "effect": "allow",
                "actions": ["read"],
                "resources": ["secret:public_api_key"],
                "conditions": [
                    {
                        "field": "agent.source",
                        "operator": "eq",
                        "value": "external",
                    }
                ],
            }
        ],
    },
}
