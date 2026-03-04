#!/usr/bin/env python3
"""
AgentGate Interactive Demo Script
Demonstrates agent registration, policy evaluation, secret leasing, and audit logging.
"""

import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any
from pathlib import Path
import sys


class AgentGateDemo:
    """Interactive demo of AgentGate functionality."""

    def __init__(self):
        """Initialize demo with sample data."""
        self.agents: Dict[str, Any] = {}
        self.policies: str = ""
        self.secrets: Dict[str, Any] = {}
        self.leases: Dict[str, Any] = {}
        self.audit_log: List[Dict[str, Any]] = []
        self.demo_directory = Path(__file__).parent

        self.load_sample_data()

    def load_sample_data(self) -> None:
        """Load sample agents and policies from JSON files."""
        try:
            agents_file = self.demo_directory / "sample_agents.json"
            with open(agents_file, 'r') as f:
                data = json.load(f)
                for agent in data["agents"]:
                    self.agents[agent["agent_id"]] = agent

            print(f"✓ Loaded {len(self.agents)} agents from sample_agents.json")

            policies_file = self.demo_directory / "sample_policies.rego"
            with open(policies_file, 'r') as f:
                self.policies = f.read()
            print("✓ Loaded policies from sample_policies.rego")

        except FileNotFoundError as e:
            print(f"✗ Error loading sample data: {e}")
            sys.exit(1)

    def print_header(self, title: str) -> None:
        """Print a formatted section header."""
        print(f"\n{'='*70}")
        print(f"  {title}")
        print(f"{'='*70}\n")

    def print_success(self, message: str) -> None:
        """Print success message."""
        print(f"✓ {message}")

    def print_error(self, message: str) -> None:
        """Print error message."""
        print(f"✗ {message}")

    def print_info(self, message: str) -> None:
        """Print info message."""
        print(f"ℹ {message}")

    def log_audit_event(self, agent_id: str, action: str, resource: str,
                       decision: str, details: Dict[str, Any] = None) -> None:
        """Log an audit event."""
        event = {
            "event_id": f"event-{len(self.audit_log)+1:04d}",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "agent_id": agent_id,
            "action": action,
            "resource": resource,
            "decision": decision,
            "details": details or {}
        }
        self.audit_log.append(event)

    # ========================================================================
    # SCENARIO 1: Agent Registration and Details
    # ========================================================================

    def scenario_1_agent_registration(self) -> None:
        """Scenario 1: Register and view agent details."""
        self.print_header("SCENARIO 1: Agent Registration & Details")

        self.print_info("Registered Agents:")
        print()

        for agent_id, agent_data in self.agents.items():
            status_icon = "🟢" if agent_data["status"] == "active" else "🔴"
            print(f"{status_icon} {agent_data['agent_name']} ({agent_data['agent_id']})")
            print(f"   Type: {agent_data['agent_type']}")
            print(f"   Scopes: {', '.join(agent_data['scopes'][:3])}...")
            print(f"   MFA Required: {agent_data['mfa_required']}")
            print(f"   Rotation Interval: {agent_data['rotation_interval_days']} days")
            print()

        self.print_success("All agents loaded and ready")

        # Detailed view of one agent
        selected_agent_id = "copilot-github-001"
        agent = self.agents[selected_agent_id]

        self.print_info(f"\nDetailed view: {agent['agent_name']}")
        print(json.dumps(agent, indent=2))

        self.log_audit_event(
            agent_id=selected_agent_id,
            action="AGENT_DETAILS_VIEWED",
            resource="agent_info",
            decision="ALLOW"
        )

    # ========================================================================
    # SCENARIO 2: Policy Evaluation
    # ========================================================================

    def scenario_2_policy_evaluation(self) -> None:
        """Scenario 2: Evaluate policies for different agent actions."""
        self.print_header("SCENARIO 2: Policy Evaluation")

        test_cases = [
            {
                "name": "GitHub Copilot reading repository",
                "agent_type": "copilot",
                "action": "repo:read",
                "environment": "development",
                "expected": "ALLOW"
            },
            {
                "name": "Pipeline agent writing to production",
                "agent_type": "pipeline",
                "action": "repo:write",
                "environment": "production",
                "expected": "DENY"
            },
            {
                "name": "Cursor editor deploying with MFA",
                "agent_type": "editor",
                "action": "deploy:write",
                "environment": "production",
                "mfa_verified": True,
                "expected": "ALLOW"
            },
            {
                "name": "Pipeline accessing dev resources",
                "agent_type": "pipeline",
                "action": "repo:write",
                "environment": "development",
                "resource": "dev-database",
                "expected": "ALLOW"
            },
            {
                "name": "Custom agent reading secrets",
                "agent_type": "custom",
                "action": "secrets:read",
                "secret_id": "analytics_api_key",
                "expected": "ALLOW"
            }
        ]

        for i, test_case in enumerate(test_cases, 1):
            name = test_case.pop("name")
            expected = test_case.pop("expected")

            print(f"Test {i}: {name}")
            print(f"  Input: {json.dumps(test_case)}")

            # Simulate policy evaluation
            decision = self.evaluate_policy(test_case)

            if decision == expected:
                self.print_success(f"Decision: {decision} (as expected)")
            else:
                self.print_error(f"Decision: {decision} (expected {expected})")

            agent_id = self.agents.get(
                [k for k, v in self.agents.items() if v["agent_type"] == test_case["agent_type"]][0],
                "unknown"
            )
            self.log_audit_event(
                agent_id=agent_id,
                action="POLICY_EVALUATION",
                resource=test_case.get("resource", "unknown"),
                decision=decision,
                details=test_case
            )
            print()

    def evaluate_policy(self, context: Dict[str, Any]) -> str:
        """Simulate policy evaluation based on rules."""
        agent_type = context.get("agent_type", "")
        action = context.get("action", "")
        environment = context.get("environment", "")
        mfa_verified = context.get("mfa_verified", False)

        # Simplified policy logic
        if agent_type == "copilot" and action.startswith("repo"):
            return "ALLOW"

        if agent_type == "pipeline":
            if action == "repo:read":
                return "ALLOW"
            if action == "repo:write" and environment in ["development", "staging"]:
                return "ALLOW"

        if agent_type == "editor":
            if action.startswith("repo") and mfa_verified:
                return "ALLOW"
            if action == "deploy:write" and mfa_verified:
                return "ALLOW"

        if agent_type == "custom" and action == "secrets:read":
            return "ALLOW"

        return "DENY"

    # ========================================================================
    # SCENARIO 3: Secret Leasing
    # ========================================================================

    def scenario_3_secret_leasing(self) -> None:
        """Scenario 3: Request and manage secret leases."""
        self.print_header("SCENARIO 3: Secret Leasing & Management")

        secrets_catalog = {
            "db_password": {
                "name": "Production Database Password",
                "ttl_default": 3600,
                "rotation_interval": 30
            },
            "api_key_github": {
                "name": "GitHub API Key",
                "ttl_default": 7200,
                "rotation_interval": 90
            },
            "aws_credentials": {
                "name": "AWS IAM Credentials",
                "ttl_default": 3600,
                "rotation_interval": 7
            }
        }

        self.print_info("Available Secrets Catalog:")
        for secret_id, secret_info in secrets_catalog.items():
            print(f"  • {secret_info['name']} ({secret_id})")
            print(f"    Default TTL: {secret_info['ttl_default']}s | Rotation: every {secret_info['rotation_interval']} days")
        print()

        # Lease secrets for agents
        lease_requests = [
            {"agent_id": "copilot-github-001", "secret_id": "api_key_github"},
            {"agent_id": "ci-pipeline-deploy-001", "secret_id": "aws_credentials"},
            {"agent_id": "custom-internal-agent-001", "secret_id": "db_password"}
        ]

        for request in lease_requests:
            lease_id = self.lease_secret(request["agent_id"], request["secret_id"])
            if lease_id:
                self.print_success(
                    f"Leased {request['secret_id']} to {request['agent_id']}: {lease_id}"
                )
                self.log_audit_event(
                    agent_id=request["agent_id"],
                    action="SECRET_LEASE_REQUESTED",
                    resource=request["secret_id"],
                    decision="ALLOW"
                )

        # Show active leases
        self.print_info("\nActive Leases:")
        for lease_id, lease_data in self.leases.items():
            remaining = max(0, int((lease_data["expires_at"] - datetime.utcnow()).total_seconds()))
            print(f"  • {lease_id}")
            print(f"    Secret: {lease_data['secret_id']}")
            print(f"    Agent: {lease_data['agent_id']}")
            print(f"    Expires in: {remaining}s")

    def lease_secret(self, agent_id: str, secret_id: str) -> str:
        """Create a secret lease for an agent."""
        lease_id = f"lease-{len(self.leases)+1:04d}"
        self.leases[lease_id] = {
            "lease_id": lease_id,
            "agent_id": agent_id,
            "secret_id": secret_id,
            "created_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + timedelta(hours=1)
        }
        return lease_id

    # ========================================================================
    # SCENARIO 4: Audit Log Review
    # ========================================================================

    def scenario_4_audit_log_review(self) -> None:
        """Scenario 4: Query and analyze audit logs."""
        self.print_header("SCENARIO 4: Audit Log Review & Analysis")

        if not self.audit_log:
            self.print_info("No audit events recorded yet")
            return

        # Summary statistics
        total_events = len(self.audit_log)
        allowed_events = sum(1 for e in self.audit_log if e["decision"] == "ALLOW")
        denied_events = sum(1 for e in self.audit_log if e["decision"] == "DENY")

        print(f"Total Events: {total_events}")
        print(f"  ✓ Allowed: {allowed_events}")
        print(f"  ✗ Denied: {denied_events}")
        print()

        # Events by agent
        events_by_agent = {}
        for event in self.audit_log:
            agent_id = event["agent_id"]
            events_by_agent[agent_id] = events_by_agent.get(agent_id, 0) + 1

        self.print_info("Events by Agent:")
        for agent_id, count in sorted(events_by_agent.items(), key=lambda x: x[1], reverse=True):
            agent_name = self.agents.get(agent_id, {}).get("agent_name", agent_id)
            print(f"  • {agent_name}: {count} events")

        # Recent events
        self.print_info("\nRecent Events:")
        for event in self.audit_log[-5:]:
            print(f"  [{event['timestamp']}] {event['agent_id']}: {event['action']} on {event['resource']} -> {event['decision']}")

    # ========================================================================
    # SCENARIO 5: Credential Rotation
    # ========================================================================

    def scenario_5_credential_rotation(self) -> None:
        """Scenario 5: Demonstrate credential rotation workflow."""
        self.print_header("SCENARIO 5: Credential Rotation Workflow")

        rotation_candidates = [
            agent for agent in self.agents.values()
            if agent["credential_rotation_required"]
        ]

        self.print_info(f"Agents with rotation required: {len(rotation_candidates)}")
        print()

        for agent in rotation_candidates[:3]:
            self.print_info(f"Rotating credentials for {agent['agent_name']}")

            # Check last rotation
            last_rotated = datetime.fromisoformat(agent["last_rotated"].replace("Z", "+00:00"))
            days_since = (datetime.utcnow() - last_rotated.replace(tzinfo=None)).days

            print(f"  Last rotated: {days_since} days ago")
            print(f"  Rotation interval: {agent['rotation_interval_days']} days")

            if days_since >= agent["rotation_interval_days"]:
                print(f"  Status: OVERDUE FOR ROTATION")
            else:
                print(f"  Status: OK (next rotation in {agent['rotation_interval_days'] - days_since} days)")

            # Simulate rotation
            new_secret = "YOUR_NEW_CLIENT_SECRET_" + agent["agent_id"].replace("-", "_").upper()
            self.print_success(f"New credentials generated for {agent['agent_name']}")

            self.log_audit_event(
                agent_id=agent["agent_id"],
                action="CREDENTIAL_ROTATED",
                resource=f"credentials_{agent['agent_id']}",
                decision="ALLOW",
                details={"rotation_reason": "scheduled_rotation"}
            )
            print()

    # ========================================================================
    # Main Demo Flow
    # ========================================================================

    def run(self) -> None:
        """Run the complete interactive demo."""
        self.print_header("AgentGate Authentication & Authorization Gateway - Demo")

        print("This demo showcases AgentGate capabilities:")
        print("  1. Agent Registration & Management")
        print("  2. Policy Evaluation Engine")
        print("  3. Secret Leasing & TTL Management")
        print("  4. Audit Logging & Compliance")
        print("  5. Credential Rotation Workflow")
        print()

        time.sleep(1)

        # Run scenarios
        try:
            self.scenario_1_agent_registration()
            time.sleep(1)

            self.scenario_2_policy_evaluation()
            time.sleep(1)

            self.scenario_3_secret_leasing()
            time.sleep(1)

            self.scenario_4_audit_log_review()
            time.sleep(1)

            self.scenario_5_credential_rotation()

        except KeyboardInterrupt:
            print("\n\nDemo interrupted by user")
            return

        # Export audit log
        self.print_header("Audit Log Export")
        audit_file = self.demo_directory / "audit_log_demo.json"
        with open(audit_file, 'w') as f:
            json.dump(self.audit_log, f, indent=2)

        self.print_success(f"Audit log exported to {audit_file}")

        # Final summary
        self.print_header("Demo Summary")
        print(f"Total agents: {len(self.agents)}")
        print(f"Total audit events: {len(self.audit_log)}")
        print(f"Active leases: {len(self.leases)}")
        print()
        self.print_success("Demo completed successfully!")


def main():
    """Entry point for demo script."""
    demo = AgentGateDemo()
    demo.run()


if __name__ == "__main__":
    main()
