/**
 * Policy Management Helpers
 *
 * Policy CRUD and simulation utilities.
 */

import {
  PolicyCreateRequest,
  Policy,
  PolicySimulationRequest,
  PolicySimulationResult,
} from './types';
import type { AgentGateClient } from './index';

/**
 * Policies Client
 */
export class PoliciesClient {
  private client: AgentGateClient;

  constructor(client: AgentGateClient) {
    this.client = client;
  }

  /**
   * Create a new policy
   */
  async create(request: PolicyCreateRequest): Promise<Policy> {
    return this.client.request<Policy>(
      'POST',
      '/api/v1/policies',
      request,
    );
  }

  /**
   * Get policy by ID
   */
  async get(policyId: string): Promise<Policy> {
    return this.client.request<Policy>(
      'GET',
      `/api/v1/policies/${policyId}`,
    );
  }

  /**
   * List policies with pagination
   */
  async list(
    offset: number = 0,
    limit: number = 50,
    tag?: string,
  ): Promise<{ policies: Policy[]; total: number; offset: number; limit: number }> {
    let url = `/api/v1/policies?offset=${offset}&limit=${limit}`;
    if (tag) {
      url += `&tag=${encodeURIComponent(tag)}`;
    }

    return this.client.request(
      'GET',
      url,
    );
  }

  /**
   * Update a policy
   */
  async update(policyId: string, request: PolicyCreateRequest): Promise<Policy> {
    return this.client.request<Policy>(
      'PUT',
      `/api/v1/policies/${policyId}`,
      request,
    );
  }

  /**
   * Delete a policy
   */
  async delete(policyId: string): Promise<void> {
    return this.client.request<void>(
      'DELETE',
      `/api/v1/policies/${policyId}`,
    );
  }

  /**
   * Simulate policy evaluation (dry-run)
   */
  async simulate(
    policyId: string,
    request: PolicySimulationRequest,
  ): Promise<PolicySimulationResult> {
    return this.client.request<PolicySimulationResult>(
      'POST',
      `/api/v1/policies/${policyId}/simulate`,
      request,
    );
  }

  /**
   * Bind policy to agent
   */
  async bindToAgent(policyId: string, agentId: string): Promise<void> {
    return this.client.request<void>(
      'POST',
      `/api/v1/policies/${policyId}/bind/${agentId}`,
    );
  }
}

/**
 * Policy evaluation helper for client-side testing
 */
export class PolicyEvaluator {
  /**
   * Check if action is allowed by policy rules
   */
  static evaluate(
    action: string,
    resource: string,
    rules: Array<{
      effect: string;
      actions: string[];
      resources: string[];
      conditions?: Array<{ field: string; operator: string; value: string }>;
    }>,
    context?: Record<string, unknown>,
  ): { allowed: boolean; reason: string } {
    for (const rule of rules) {
      // Check action match
      if (!rule.actions.includes(action) && !rule.actions.includes('*')) {
        continue;
      }

      // Check resource match (with wildcard support)
      let resourceMatch = false;
      for (const pattern of rule.resources) {
        if (this.matchPattern(resource, pattern)) {
          resourceMatch = true;
          break;
        }
      }

      if (!resourceMatch) {
        continue;
      }

      // Check conditions
      if (rule.conditions) {
        let conditionsMet = true;
        for (const condition of rule.conditions) {
          if (!this.evaluateCondition(condition, context)) {
            conditionsMet = false;
            break;
          }
        }
        if (!conditionsMet) {
          continue;
        }
      }

      // Rule matched
      if (rule.effect === 'allow') {
        return {
          allowed: true,
          reason: `Action '${action}' allowed by policy`,
        };
      } else if (rule.effect === 'deny') {
        return {
          allowed: false,
          reason: `Action '${action}' denied by policy`,
        };
      }
    }

    // No matching rules
    return {
      allowed: false,
      reason: 'No matching policy rules (default deny)',
    };
  }

  /**
   * Match resource against pattern with wildcard support
   */
  private static matchPattern(resource: string, pattern: string): boolean {
    if (pattern === '*') {
      return true;
    }

    if (pattern.includes('*')) {
      const regex = new RegExp(
        `^${pattern.replace(/\*/g, '.*')}$`,
      );
      return regex.test(resource);
    }

    return resource === pattern;
  }

  /**
   * Evaluate a single condition
   */
  private static evaluateCondition(
    condition: { field: string; operator: string; value: string },
    context?: Record<string, unknown>,
  ): boolean {
    if (!context) {
      return false;
    }

    const fieldValue = context[condition.field];
    if (fieldValue === undefined) {
      return false;
    }

    const strValue = String(fieldValue);

    switch (condition.operator) {
      case 'eq':
        return strValue === condition.value;
      case 'neq':
        return strValue !== condition.value;
      case 'in':
        return condition.value.split(',').includes(strValue);
      case 'contains':
        return strValue.includes(condition.value);
      case 'matches':
        try {
          return new RegExp(condition.value).test(strValue);
        } catch {
          return false;
        }
      default:
        return false;
    }
  }
}
