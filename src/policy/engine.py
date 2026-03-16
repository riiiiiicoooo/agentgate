"""
Policy Engine

OPA/Rego-inspired policy evaluation engine with caching, compilation, and decision support.
"""

import logging
import hashlib
import json
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timezone
from functools import lru_cache
from collections import OrderedDict

logger = logging.getLogger(__name__)


class PolicyCompilationError(Exception):
    """Policy compilation failed."""
    pass


class PolicyEvaluationError(Exception):
    """Policy evaluation failed."""
    pass


class PolicyDecision:
    """Result of policy evaluation."""

    def __init__(
        self,
        effect: str,
        matched_policies: List[str],
        conditions_met: bool,
        reason: str,
        evaluation_time_ms: float,
    ):
        self.effect = effect
        self.matched_policies = matched_policies
        self.conditions_met = conditions_met
        self.reason = reason
        self.evaluation_time_ms = evaluation_time_ms

    def is_allowed(self) -> bool:
        """Check if decision allows the action."""
        return self.effect == "allow"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "effect": self.effect,
            "matched_policies": self.matched_policies,
            "conditions_met": self.conditions_met,
            "reason": self.reason,
            "evaluation_time_ms": self.evaluation_time_ms,
        }


class CompiledPolicy:
    """A compiled policy ready for evaluation."""

    def __init__(
        self,
        policy_id: str,
        name: str,
        rules: List[Dict[str, Any]],
        checksum: str,
    ):
        self.policy_id = policy_id
        self.name = name
        self.rules = rules
        self.checksum = checksum
        self.compiled_at = datetime.now(timezone.utc)

    def get_cache_key(self, input_data: Dict[str, Any]) -> str:
        """Generate cache key for input."""
        data_str = json.dumps(input_data, sort_keys=True)
        return hashlib.md5(data_str.encode()).hexdigest()


class PolicyEngine:
    """
    Policy evaluation engine.

    Evaluates policies against input data, handles caching, and supports multiple
    evaluation strategies (allow-list, deny-list, attribute-based).
    """

    def __init__(self, cache_size: int = 1000):
        self.compiled_policies: Dict[str, CompiledPolicy] = {}
        self.cache_size = cache_size
        # Use OrderedDict for LRU-like behavior (replaces unbounded dict)
        # In production, use Redis for distributed caching
        self.decision_cache: OrderedDict = OrderedDict()
        logger.info(f"PolicyEngine initialized with cache size {cache_size}")

    async def load_default_policies(self) -> None:
        """Load default baseline policies."""
        from src.policy.defaults import DEFAULT_POLICIES

        for policy in DEFAULT_POLICIES:
            try:
                self.compile_policy(
                    policy_id=policy.get("id"),
                    name=policy.get("name"),
                    rules=policy.get("rules"),
                )
                logger.info(f"Default policy loaded: {policy.get('name')}")
            except Exception as e:
                logger.error(f"Failed to load default policy: {e}")

    def compile_policy(
        self,
        policy_id: str,
        name: str,
        rules: List[Dict[str, Any]],
    ) -> CompiledPolicy:
        """
        Compile a policy into optimized form.

        Validates rule syntax and pre-processes for evaluation.

        Args:
            policy_id: Policy identifier
            name: Human-readable policy name
            rules: List of policy rules

        Returns:
            CompiledPolicy: Compiled policy object

        Raises:
            PolicyCompilationError: If compilation fails
        """
        try:
            # Validate rules
            for i, rule in enumerate(rules):
                if "effect" not in rule:
                    raise PolicyCompilationError(
                        f"Rule {i} missing 'effect' field"
                    )
                if rule["effect"] not in ["allow", "deny"]:
                    raise PolicyCompilationError(
                        f"Rule {i} invalid effect: {rule['effect']}"
                    )
                if "actions" not in rule or not rule["actions"]:
                    raise PolicyCompilationError(
                        f"Rule {i} missing or empty 'actions' field"
                    )
                if "resources" not in rule or not rule["resources"]:
                    raise PolicyCompilationError(
                        f"Rule {i} missing or empty 'resources' field"
                    )

            # Calculate checksum
            rules_json = json.dumps(rules, sort_keys=True)
            checksum = hashlib.sha256(rules_json.encode()).hexdigest()

            # Create compiled policy
            compiled = CompiledPolicy(
                policy_id=policy_id,
                name=name,
                rules=rules,
                checksum=checksum,
            )

            self.compiled_policies[policy_id] = compiled

            logger.info(
                f"Policy compiled: {name} ({policy_id}) checksum={checksum[:8]}"
            )

            return compiled

        except PolicyCompilationError:
            raise
        except Exception as e:
            logger.error(f"Policy compilation error: {e}")
            raise PolicyCompilationError(f"Failed to compile policy: {e}")

    async def evaluate(
        self,
        agent_id: str,
        action: str,
        resource: str,
        policies: List[str],
        context: Optional[Dict[str, Any]] = None,
        use_cache: bool = True,
    ) -> PolicyDecision:
        """
        Evaluate policies for a request.

        Args:
            agent_id: Agent requesting access
            action: Action being performed (read, write, delete, etc.)
            resource: Resource being accessed
            policies: List of policy IDs to evaluate
            context: Additional context (agent attributes, environment, etc.)
            use_cache: Whether to use cached decisions

        Returns:
            PolicyDecision: Allow/deny decision with details

        Raises:
            PolicyEvaluationError: If evaluation fails
        """
        import time

        start_time = time.time()

        try:
            # Build cache key
            cache_input = {
                "agent_id": agent_id,
                "action": action,
                "resource": resource,
                "policies": policies,
                "context": context,
            }

            cache_key = None
            if use_cache:
                cache_key = self._generate_cache_key(cache_input)
                if cache_key in self.decision_cache:
                    logger.debug(f"Cache hit for {cache_key}")
                    return self.decision_cache[cache_key]

            # Evaluate each policy
            matched_policies = []
            final_effect = "deny"  # Default deny
            conditions_met = False

            for policy_id in policies:
                if policy_id not in self.compiled_policies:
                    logger.warning(f"Policy not found: {policy_id}")
                    continue

                policy = self.compiled_policies[policy_id]

                # Evaluate policy rules
                for rule in policy.rules:
                    if self._match_rule(agent_id, action, resource, rule, context):
                        matched_policies.append(policy_id)
                        final_effect = rule["effect"]
                        conditions_met = True
                        break  # Use first matching rule

            decision = PolicyDecision(
                effect=final_effect,
                matched_policies=matched_policies,
                conditions_met=conditions_met,
                reason=f"Policy evaluation: {len(matched_policies)} policies matched",
                evaluation_time_ms=(time.time() - start_time) * 1000,
            )

            # Cache decision
            if use_cache and cache_key:
                self._cache_decision(cache_key, decision)

            logger.info(
                f"Policy evaluation: {agent_id}:{action}:{resource} -> {final_effect} "
                f"({len(matched_policies)} policies matched, {decision.evaluation_time_ms:.2f}ms)"
            )

            return decision

        except Exception as e:
            logger.error(f"Policy evaluation error: {e}", exc_info=True)
            raise PolicyEvaluationError(f"Failed to evaluate policies: {e}")

    def _match_rule(
        self,
        agent_id: str,
        action: str,
        resource: str,
        rule: Dict[str, Any],
        context: Optional[Dict[str, Any]],
    ) -> bool:
        """
        Check if a rule matches the request.

        Args:
            agent_id: Agent ID
            action: Action
            resource: Resource
            rule: Rule to match
            context: Additional context

        Returns:
            bool: True if rule matches
        """
        # Match actions
        if action not in rule.get("actions", []):
            return False

        # Match resources (support wildcards)
        resource_match = False
        for pattern in rule.get("resources", []):
            if self._match_pattern(resource, pattern):
                resource_match = True
                break

        if not resource_match:
            return False

        # Match conditions if present
        conditions = rule.get("conditions", [])
        if conditions:
            if not self._match_conditions(agent_id, conditions, context):
                return False

        return True

    def _match_pattern(self, resource: str, pattern: str) -> bool:
        """
        Match resource against pattern with wildcard support.

        Args:
            resource: Resource path
            pattern: Pattern with optional wildcards (*)

        Returns:
            bool: True if matches
        """
        if "*" not in pattern:
            return resource == pattern

        # Convert to regex
        import fnmatch
        return fnmatch.fnmatch(resource, pattern)

    def _match_conditions(
        self,
        agent_id: str,
        conditions: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]],
    ) -> bool:
        """
        Evaluate condition expressions.

        Args:
            agent_id: Agent ID
            conditions: Conditions to evaluate
            context: Context data

        Returns:
            bool: True if all conditions match
        """
        if not context:
            context = {}

        for condition in conditions:
            field = condition.get("field")
            operator = condition.get("operator")
            value = condition.get("value")

            # Get field value from context or agent_id
            if field == "agent_id":
                field_value = agent_id
            else:
                field_value = context.get(field)

            if field_value is None:
                return False

            # Evaluate operator
            field_str = str(field_value)

            if operator == "eq":
                if field_str != str(value):
                    return False
            elif operator == "neq":
                if field_str == str(value):
                    return False
            elif operator == "in":
                if field_str not in str(value).split(","):
                    return False
            elif operator == "contains":
                if str(value) not in field_str:
                    return False
            elif operator == "matches":
                import re
                if not re.search(value, field_str):
                    return False

        return True

    @lru_cache(maxsize=1000)
    def _generate_cache_key(self, input_data: str) -> str:
        """Generate cache key for input."""
        return hashlib.md5(input_data.encode()).hexdigest()

    def _cache_decision(self, key: str, decision: PolicyDecision) -> None:
        """
        Cache a policy decision with LRU eviction.

        Replaces unbounded dict with OrderedDict for bounded memory.
        In production, use Redis for distributed caching.
        """
        if len(self.decision_cache) >= self.cache_size:
            # LRU: remove oldest (first) item
            self.decision_cache.popitem(last=False)

        self.decision_cache[key] = decision

    def clear_cache(self) -> None:
        """Clear decision cache."""
        self.decision_cache.clear()
        logger.info("Policy decision cache cleared")

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            "cached_decisions": len(self.decision_cache),
            "compiled_policies": len(self.compiled_policies),
            "cache_size": self.cache_size,
        }
