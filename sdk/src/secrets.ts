/**
 * Secrets Management Helpers
 *
 * Secret request, lease renewal, and revocation.
 */

import {
  SecretLeaseRequest,
  SecretLease,
  SecretRenewalRequest,
  SecretStatus,
} from './types';
import type { AgentGateClient } from './index';

/**
 * Secrets Client
 */
export class SecretsClient {
  private client: AgentGateClient;

  constructor(client: AgentGateClient) {
    this.client = client;
  }

  /**
   * Request a new secret lease
   */
  async request(request: SecretLeaseRequest): Promise<SecretLease> {
    return this.client.request<SecretLease>(
      'POST',
      '/api/v1/secrets/request',
      request,
    );
  }

  /**
   * Renew a secret lease
   */
  async renew(leaseId: string, additionalTtl?: number): Promise<SecretLease> {
    const request: SecretRenewalRequest = {
      lease_id: leaseId,
      additional_ttl_seconds: additionalTtl || 3600,
    };

    return this.client.request<SecretLease>(
      'POST',
      `/api/v1/secrets/${leaseId}/renew`,
      request,
    );
  }

  /**
   * Revoke a secret lease
   */
  async revoke(leaseId: string): Promise<void> {
    return this.client.request<void>(
      'POST',
      `/api/v1/secrets/${leaseId}/revoke`,
    );
  }

  /**
   * Get secret status (metadata only, not the value)
   */
  async getStatus(secretName: string): Promise<SecretStatus> {
    return this.client.request<SecretStatus>(
      'GET',
      `/api/v1/secrets/${secretName}/status`,
    );
  }

  /**
   * Rotate a secret
   */
  async rotate(
    secretName: string,
    newValue?: string,
    strategy: string = 'random',
  ): Promise<{ secret_name: string; rotated_at: string; new_version: string }> {
    return this.client.request(
      'POST',
      `/api/v1/secrets/${secretName}/rotate`,
      {
        secret_name: secretName,
        new_value: newValue,
        rotation_strategy: strategy,
      },
    );
  }

  /**
   * Get audit log for secret
   */
  async getAuditLog(secretName: string, limit: number = 100): Promise<unknown[]> {
    return this.client.request(
      'GET',
      `/api/v1/secrets/audit?secret_name=${secretName}&limit=${limit}`,
    );
  }
}

/**
 * Utility for auto-renewing secrets before expiry
 */
export class AutoRenewingSecretLease {
  private leaseId: string;
  private expiresAt: Date;
  private renewalThresholdSeconds: number = 300; // Renew 5 min before expiry
  private renewalTimeoutId?: NodeJS.Timeout;
  private secretsClient: SecretsClient;

  constructor(
    secretsClient: SecretsClient,
    lease: SecretLease,
  ) {
    this.secretsClient = secretsClient;
    this.leaseId = lease.lease_id;
    this.expiresAt = new Date(lease.expires_at);
  }

  /**
   * Start auto-renewal
   */
  start(): void {
    this.scheduleRenewal();
  }

  /**
   * Stop auto-renewal
   */
  stop(): void {
    if (this.renewalTimeoutId) {
      clearTimeout(this.renewalTimeoutId);
    }
  }

  /**
   * Renew lease
   */
  async renew(additionalTtl: number = 3600): Promise<SecretLease> {
    const renewed = await this.secretsClient.renew(this.leaseId, additionalTtl);
    this.expiresAt = new Date(renewed.expires_at);
    this.scheduleRenewal();
    return renewed;
  }

  /**
   * Get time until expiry (seconds)
   */
  getTimeRemaining(): number {
    const now = Date.now();
    const expiryTime = this.expiresAt.getTime();
    return Math.max(0, Math.floor((expiryTime - now) / 1000));
  }

  /**
   * Check if lease is expired
   */
  isExpired(): boolean {
    return this.getTimeRemaining() === 0;
  }

  private scheduleRenewal(): void {
    const timeRemaining = this.getTimeRemaining();

    if (timeRemaining <= 0) {
      // Already expired
      return;
    }

    // Schedule renewal before expiry
    const renewalTime = Math.max(
      1000, // At least 1 second
      (timeRemaining - this.renewalThresholdSeconds) * 1000,
    );

    this.renewalTimeoutId = setTimeout(() => this.performRenewal(), renewalTime);
  }

  private async performRenewal(): Promise<void> {
    try {
      await this.renew();
    } catch (error) {
      console.error('Secret renewal failed:', error);
      // Retry in 1 minute
      this.renewalTimeoutId = setTimeout(() => this.performRenewal(), 60000);
    }
  }
}
