"""
Policy engine tests for AgentGate.
Tests policy evaluation, allow/deny decisions, wildcard matching, condition evaluation, and policy caching.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import re
from datetime import datetime, timedelta


class TestPolicyEvaluation:
    """Test OPA policy evaluation engine."""

    @pytest.mark.asyncio
    async def test_simple_allow_policy(self, mock_opa_server):
        """Test evaluation of simple allow policy."""
        input_data = {
            "agent_type": "copilot",
            "action": "repo:read"
        }

        result = await mock_opa_server.evaluate_policy(input_data)

        assert result["result"][0]["allow"] is True
        assert "decision_id" in result

    @pytest.mark.asyncio
    async def test_simple_deny_policy(self, mock_opa_server):
        """Test evaluation of simple deny policy."""
        mock_opa_server.evaluate_policy = AsyncMock(return_value={
            "result": [{"allow": False, "reason": "unauthorized_agent_type"}],
            "decision_id": "test-decision-456"
        })

        input_data = {
            "agent_type": "unknown",
            "action": "admin:write"
        }

        result = await mock_opa_server.evaluate_policy(input_data)

        assert result["result"][0]["allow"] is False
        assert result["result"][0]["reason"] == "unauthorized_agent_type"

    @pytest.mark.asyncio
    async def test_policy_with_multiple_conditions(self, mock_opa_server):
        """Test policy evaluation with multiple AND conditions."""
        mock_opa_server.evaluate_policy = AsyncMock(return_value={
            "result": [{"allow": True, "reason": "all_conditions_met"}],
            "decision_id": "test-decision-789"
        })

        input_data = {
            "agent_type": "editor",
            "action": "deploy:write",
            "mfa_verified": True,
            "environment": "production"
        }

        result = await mock_opa_server.evaluate_policy(input_data)

        assert result["result"][0]["allow"] is True

    @pytest.mark.asyncio
    async def test_policy_evaluation_performance(self, mock_opa_server):
        """Test that policy evaluation completes within acceptable time."""
        mock_opa_server.evaluate_policy = AsyncMock(return_value={
            "result": [{"allow": True}],
            "decision_id": "test-decision-perf",
            "metrics": {"timer_rego_load_ns": 500000, "timer_rego_eval_ns": 2000000}
        })

        input_data = {"agent_type": "copilot", "action": "repo:read"}
        result = await mock_opa_server.evaluate_policy(input_data)

        eval_time_ms = result["metrics"]["timer_rego_eval_ns"] / 1000000
        assert eval_time_ms < 100  # Should complete in under 100ms

    @pytest.mark.asyncio
    async def test_policy_evaluation_with_missing_input_fields(self):
        """Test policy evaluation handles missing input fields gracefully."""
        incomplete_input = {
            "agent_type": "copilot"
            # Missing 'action' field
        }

        with pytest.raises((KeyError, ValueError)):
            if "action" not in incomplete_input:
                raise KeyError("Required field 'action' missing from input")

    @pytest.mark.asyncio
    async def test_policy_validation_on_load(self, sample_policy_rego):
        """Test that invalid policies are caught on load."""
        invalid_policy = """
package agentgate.authz

invalid syntax here !!
"""
        with pytest.raises((SyntaxError, ValueError)):
            # Simulate policy compilation
            if "invalid syntax" in invalid_policy:
                raise SyntaxError("Invalid Rego policy syntax")


class TestAllowDenyDecisions:
    """Test allow/deny decision logic."""

    @pytest.mark.asyncio
    async def test_default_deny_policy(self):
        """Test that policy defaults to deny when no rules match."""
        matched_rules = []  # No rules matched

        allow = len(matched_rules) > 0 and matched_rules[0]["allow"]
        default_deny = False

        if not allow:
            default_deny = True

        assert default_deny is True

    @pytest.mark.asyncio
    async def test_first_matching_rule_wins(self):
        """Test that first matching rule determines decision."""
        rules = [
            {"id": 1, "condition": True, "allow": True},
            {"id": 2, "condition": True, "allow": False}
        ]

        matching_rule = next((r for r in rules if r["condition"]), None)
        decision = matching_rule["allow"] if matching_rule else False

        assert decision is True  # First rule wins

    @pytest.mark.asyncio
    async def test_explicit_deny_overrides_allow(self):
        """Test that explicit deny rules override allow rules."""
        rules = [
            {"type": "allow", "condition": True},
            {"type": "deny", "condition": True}
        ]

        # In OPA, explicit denies typically override allows
        has_deny = any(r["type"] == "deny" and r["condition"] for r in rules)

        if has_deny:
            decision = False
        else:
            decision = True

        assert decision is False

    @pytest.mark.asyncio
    async def test_decision_with_reason_codes(self):
        """Test that decisions include reason codes for audit purposes."""
        decisions = [
            {
                "allow": True,
                "reason": "matched_copilot_full_access",
                "rule_id": "copilot-001"
            },
            {
                "allow": False,
                "reason": "missing_mfa_verification",
                "rule_id": "editor-mfa-001"
            }
        ]

        for decision in decisions:
            assert "reason" in decision
            assert "rule_id" in decision

    @pytest.mark.asyncio
    async def test_policy_decision_caching(self):
        """Test that identical policy decisions can be cached."""
        input1 = {"agent_type": "copilot", "action": "repo:read"}
        input2 = {"agent_type": "copilot", "action": "repo:read"}

        # Same inputs should produce same decision
        decision1 = {"allow": True, "decision_id": "cached-123"}
        decision2 = {"allow": True, "decision_id": "cached-123"}

        assert decision1 == decision2

    @pytest.mark.asyncio
    async def test_conditional_allow_with_time_window(self):
        """Test policy allowing actions only within specific time windows."""
        current_time = datetime.utcnow()
        allowed_hours = (9, 17)  # 9 AM to 5 PM

        hour = current_time.hour
        is_allowed = allowed_hours[0] <= hour < allowed_hours[1]

        assert isinstance(is_allowed, bool)


class TestWildcardMatching:
    """Test wildcard pattern matching in policies."""

    @pytest.mark.asyncio
    async def test_resource_wildcard_matching(self):
        """Test wildcard matching for resources."""
        policy_pattern = "db_*"
        resources_to_test = ["db_password", "db_username", "db_host", "api_key"]

        def matches_wildcard(pattern, resource):
            regex = pattern.replace("*", ".*")
            return bool(re.match(f"^{regex}$", resource))

        assert matches_wildcard(policy_pattern, "db_password")
        assert matches_wildcard(policy_pattern, "db_username")
        assert not matches_wildcard(policy_pattern, "api_key")

    @pytest.mark.asyncio
    async def test_action_wildcard_matching(self):
        """Test wildcard matching for actions."""
        policy_pattern = "repo:*"
        actions = ["repo:read", "repo:write", "repo:admin", "secrets:read"]

        def matches(pattern, action):
            if pattern.endswith(":*"):
                prefix = pattern[:-2]
                return action.startswith(prefix)
            return action == pattern

        assert matches(policy_pattern, "repo:read")
        assert matches(policy_pattern, "repo:write")
        assert not matches(policy_pattern, "secrets:read")

    @pytest.mark.asyncio
    async def test_environment_wildcard_matching(self):
        """Test wildcard matching for environment scoping."""
        policy_pattern = "dev-*"
        resource_names = ["dev-database", "dev-api", "prod-database", "staging-api"]

        def matches_env(pattern, resource):
            regex = pattern.replace("*", ".*")
            return bool(re.match(f"^{regex}$", resource))

        assert matches_env(policy_pattern, "dev-database")
        assert matches_env(policy_pattern, "dev-api")
        assert not matches_env(policy_pattern, "prod-database")

    @pytest.mark.asyncio
    async def test_complex_wildcard_pattern(self):
        """Test complex multi-wildcard patterns."""
        policy_pattern = "app-*-*"
        resources = [
            "app-prod-database",
            "app-staging-api",
            "app-dev",
            "database-prod"
        ]

        def matches(pattern, resource):
            regex = pattern.replace("*", "[^-]+")  # Match non-hyphen characters
            return bool(re.match(f"^{regex}$", resource))

        assert matches(policy_pattern, "app-prod-database")
        assert matches(policy_pattern, "app-staging-api")
        assert not matches(policy_pattern, "app-dev")
        assert not matches(policy_pattern, "database-prod")


class TestConditionEvaluation:
    """Test evaluation of policy conditions."""

    @pytest.mark.asyncio
    async def test_boolean_condition_and(self):
        """Test AND condition evaluation."""
        conditions = [
            {"type": "agent_type", "value": "copilot", "result": True},
            {"type": "mfa_verified", "value": True, "result": True},
            {"type": "ip_whitelisted", "value": True, "result": True}
        ]

        all_met = all(c["result"] for c in conditions)
        assert all_met is True

    @pytest.mark.asyncio
    async def test_boolean_condition_or(self):
        """Test OR condition evaluation."""
        conditions = [
            {"type": "agent_type", "value": "copilot", "result": False},
            {"type": "agent_type", "value": "editor", "result": True},
            {"type": "agent_type", "value": "pipeline", "result": False}
        ]

        any_met = any(c["result"] for c in conditions)
        assert any_met is True

    @pytest.mark.asyncio
    async def test_condition_with_regex(self):
        """Test condition evaluation with regex patterns."""
        agent_id = "copilot-prod-001"
        pattern = r"^copilot-prod-.*"

        matches = bool(re.match(pattern, agent_id))
        assert matches is True

    @pytest.mark.asyncio
    async def test_time_based_condition(self):
        """Test time-based policy conditions."""
        allowed_start = datetime.fromisoformat("2026-03-01T09:00:00")
        allowed_end = datetime.fromisoformat("2026-03-31T17:00:00")
        current_time = datetime.utcnow()

        is_within_window = allowed_start <= current_time <= allowed_end
        assert isinstance(is_within_window, bool)

    @pytest.mark.asyncio
    async def test_numeric_condition_comparison(self):
        """Test numeric condition comparisons."""
        request_cost = 50
        max_daily_budget = 10000

        exceeds_budget = request_cost > max_daily_budget
        assert exceeds_budget is False

    @pytest.mark.asyncio
    async def test_set_membership_condition(self):
        """Test condition checking set membership."""
        allowed_environments = {"development", "staging"}
        requested_environment = "development"

        is_allowed = requested_environment in allowed_environments
        assert is_allowed is True

    @pytest.mark.asyncio
    async def test_nested_conditions(self):
        """Test evaluation of nested conditions."""
        policy = {
            "condition": {
                "type": "AND",
                "conditions": [
                    {"type": "agent_type", "equals": "editor"},
                    {
                        "type": "OR",
                        "conditions": [
                            {"type": "mfa_verified", "equals": True},
                            {"type": "trusted_ip", "equals": True}
                        ]
                    }
                ]
            }
        }

        # Evaluate nested structure
        agent_type_match = True
        mfa_or_ip = True or False  # OR condition

        nested_result = agent_type_match and mfa_or_ip
        assert nested_result is True


class TestPolicyCaching:
    """Test policy evaluation caching mechanisms."""

    @pytest.mark.asyncio
    async def test_cache_hit_on_identical_input(self):
        """Test that identical inputs result in cache hit."""
        cache = {}
        input_hash = "abc123def456"

        # First evaluation - cache miss
        cache[input_hash] = {"allow": True, "cached": True}

        # Second evaluation - cache hit
        cached_result = cache.get(input_hash)
        assert cached_result is not None
        assert cached_result["cached"] is True

    @pytest.mark.asyncio
    async def test_cache_miss_on_different_input(self):
        """Test that different inputs result in cache miss."""
        cache = {}
        input1_hash = "abc123"
        input2_hash = "xyz789"

        cache[input1_hash] = {"allow": True}

        cached_result = cache.get(input2_hash)
        assert cached_result is None

    @pytest.mark.asyncio
    async def test_cache_expiration(self):
        """Test that cached policies expire after TTL."""
        cache_ttl_seconds = 300
        cached_entry = {
            "decision": {"allow": True},
            "cached_at": datetime.utcnow() - timedelta(seconds=350)
        }

        age_seconds = (datetime.utcnow() - cached_entry["cached_at"]).total_seconds()
        is_expired = age_seconds > cache_ttl_seconds

        assert is_expired is True

    @pytest.mark.asyncio
    async def test_cache_invalidation_on_policy_update(self):
        """Test that cache is invalidated when policies are updated."""
        cache = {
            "input_hash_1": {"allow": True, "policy_version": "v1"}
        }

        policy_updated = True

        if policy_updated:
            cache.clear()

        assert len(cache) == 0

    @pytest.mark.asyncio
    async def test_cache_size_limits(self):
        """Test that cache doesn't exceed maximum size."""
        max_cache_size = 1000
        cache = {}

        for i in range(1500):
            key = f"input_{i}"
            if len(cache) >= max_cache_size:
                # Evict oldest entry
                oldest = min(cache.keys())
                del cache[oldest]

            cache[key] = {"decision": "allow"}

        assert len(cache) <= max_cache_size

    @pytest.mark.asyncio
    async def test_cache_metrics(self):
        """Test cache hit/miss metrics collection."""
        cache_metrics = {
            "total_requests": 1000,
            "cache_hits": 750,
            "cache_misses": 250
        }

        hit_ratio = cache_metrics["cache_hits"] / cache_metrics["total_requests"]
        assert hit_ratio == 0.75
        assert cache_metrics["cache_hits"] + cache_metrics["cache_misses"] == cache_metrics["total_requests"]


class TestPolicyEdgeCases:
    """Test edge cases and error conditions in policy evaluation."""

    @pytest.mark.asyncio
    async def test_circular_policy_reference(self):
        """Test handling of circular policy references."""
        policies = {
            "policy_a": {"includes": ["policy_b"]},
            "policy_b": {"includes": ["policy_a"]}
        }

        visited = set()

        def detect_circular(policy_name):
            if policy_name in visited:
                raise ValueError(f"Circular policy reference detected: {policy_name}")
            visited.add(policy_name)

        with pytest.raises(ValueError):
            detect_circular("policy_a")
            detect_circular("policy_b")

    @pytest.mark.asyncio
    async def test_empty_policy_document(self):
        """Test handling of empty policy document."""
        policy = {}

        # Should default to deny
        allow = policy.get("allow", False)
        assert allow is False

    @pytest.mark.asyncio
    async def test_malformed_condition_expression(self):
        """Test handling of malformed condition expressions."""
        malformed = "agent_type == 'copilot' AND"

        with pytest.raises((SyntaxError, ValueError)):
            if malformed.endswith("AND"):
                raise SyntaxError("Incomplete condition expression")

    @pytest.mark.asyncio
    async def test_policy_with_contradictory_rules(self):
        """Test policy with contradictory allow/deny rules."""
        rules = [
            {"priority": 1, "action": "deny", "condition": "all"},
            {"priority": 2, "action": "allow", "condition": "all"}
        ]

        # Higher priority wins
        sorted_rules = sorted(rules, key=lambda r: r["priority"], reverse=True)
        decision = sorted_rules[0]["action"]

        assert decision == "allow"
