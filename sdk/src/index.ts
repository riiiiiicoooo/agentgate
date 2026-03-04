/**
 * AgentGate SDK
 *
 * TypeScript/JavaScript SDK for interacting with AgentGate API.
 */

import { AuthClient } from './auth';
import { SecretsClient } from './secrets';
import { PoliciesClient } from './policies';
import * as types from './types';

export { types };

/**
 * AgentGate Client
 *
 * Main entry point for SDK usage.
 */
export class AgentGateClient {
  private baseUrl: string;
  private apiKey?: string;
  private accessToken?: string;
  public auth: AuthClient;
  public secrets: SecretsClient;
  public policies: PoliciesClient;

  constructor(baseUrl: string, apiKey?: string) {
    this.baseUrl = baseUrl;
    this.apiKey = apiKey;

    this.auth = new AuthClient(this);
    this.secrets = new SecretsClient(this);
    this.policies = new PoliciesClient(this);
  }

  /**
   * Make authenticated HTTP request
   */
  async request<T>(
    method: string,
    path: string,
    body?: unknown,
    headers?: Record<string, string>,
  ): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    const defaultHeaders: Record<string, string> = {
      'Content-Type': 'application/json',
    };

    // Add authentication
    if (this.accessToken) {
      defaultHeaders['Authorization'] = `Bearer ${this.accessToken}`;
    } else if (this.apiKey) {
      defaultHeaders['X-API-Key'] = this.apiKey;
    }

    const response = await fetch(url, {
      method,
      headers: { ...defaultHeaders, ...headers },
      body: body ? JSON.stringify(body) : undefined,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(`API Error: ${response.status} - ${error.detail || response.statusText}`);
    }

    return response.json() as Promise<T>;
  }

  /**
   * Set access token for authentication
   */
  setAccessToken(token: string): void {
    this.accessToken = token;
  }

  /**
   * Get current access token
   */
  getAccessToken(): string | undefined {
    return this.accessToken;
  }

  /**
   * Check server health
   */
  async health(): Promise<{ status: string; version: string }> {
    return this.request('GET', '/health');
  }

  /**
   * Check readiness
   */
  async readiness(): Promise<Record<string, unknown>> {
    return this.request('GET', '/health/ready');
  }
}

// Export everything
export default AgentGateClient;
