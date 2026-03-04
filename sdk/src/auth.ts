/**
 * Authentication Helpers
 *
 * Client credentials, API key, and token refresh flows.
 */

import { TokenResponse, TokenPayload, AuthRequest } from './types';
import type { AgentGateClient } from './index';
import * as jwt from 'jsonwebtoken';

/**
 * Authentication Client
 */
export class AuthClient {
  private client: AgentGateClient;

  constructor(client: AgentGateClient) {
    this.client = client;
  }

  /**
   * Exchange client credentials for access token
   */
  async getToken(
    clientId: string,
    clientSecret: string,
    scopes?: string[],
  ): Promise<TokenResponse> {
    const request: AuthRequest = {
      grant_type: 'client_credentials',
      client_id: clientId,
      client_secret: clientSecret,
      scope: scopes,
    };

    const response = await this.client.request<TokenResponse>(
      'POST',
      '/api/v1/auth/token',
      request,
    );

    // Store token
    this.client.setAccessToken(response.access_token);

    return response;
  }

  /**
   * Refresh access token using refresh token
   */
  async refreshToken(refreshToken: string): Promise<TokenResponse> {
    const request: AuthRequest = {
      grant_type: 'refresh_token',
      client_id: '',
      refresh_token: refreshToken,
    };

    const response = await this.client.request<TokenResponse>(
      'POST',
      '/api/v1/auth/refresh',
      request,
    );

    // Store new token
    this.client.setAccessToken(response.access_token);

    return response;
  }

  /**
   * Get current token payload (decoded)
   */
  getTokenPayload(): TokenPayload | null {
    const token = this.client.getAccessToken();
    if (!token) return null;

    try {
      const decoded = jwt.decode(token) as TokenPayload;
      return decoded;
    } catch {
      return null;
    }
  }

  /**
   * Check if token is expired
   */
  isTokenExpired(): boolean {
    const payload = this.getTokenPayload();
    if (!payload) return true;

    const now = Math.floor(Date.now() / 1000);
    return payload.exp < now;
  }

  /**
   * Get time until token expires (in seconds)
   */
  getTokenExpiresIn(): number {
    const payload = this.getTokenPayload();
    if (!payload) return 0;

    const now = Math.floor(Date.now() / 1000);
    return Math.max(0, payload.exp - now);
  }

  /**
   * Check if token has required scope
   */
  hasScope(scope: string): boolean {
    const payload = this.getTokenPayload();
    if (!payload) return false;

    return (
      payload.scopes.includes(scope) ||
      payload.scopes.includes('*')
    );
  }

  /**
   * Get all token scopes
   */
  getScopes(): string[] {
    const payload = this.getTokenPayload();
    return payload?.scopes || [];
  }
}

/**
 * Automatically refresh token when expiring
 */
export class AutoRefreshTokenManager {
  private refreshToken: string;
  private refreshThresholdSeconds: number = 300; // Refresh 5 min before expiry
  private refreshTimeoutId?: NodeJS.Timeout;

  constructor(
    private authClient: AuthClient,
    refreshToken: string,
  ) {
    this.refreshToken = refreshToken;
  }

  /**
   * Start auto-refresh
   */
  start(): void {
    this.scheduleRefresh();
  }

  /**
   * Stop auto-refresh
   */
  stop(): void {
    if (this.refreshTimeoutId) {
      clearTimeout(this.refreshTimeoutId);
    }
  }

  private scheduleRefresh(): void {
    const expiresIn = this.authClient.getTokenExpiresIn();

    if (expiresIn <= 0) {
      // Token already expired, refresh immediately
      this.refresh();
      return;
    }

    // Schedule refresh before expiry
    const refreshTime = Math.max(
      1000, // At least 1 second
      (expiresIn - this.refreshThresholdSeconds) * 1000,
    );

    this.refreshTimeoutId = setTimeout(() => this.refresh(), refreshTime);
  }

  private async refresh(): Promise<void> {
    try {
      const response = await this.authClient.refreshToken(this.refreshToken);
      this.refreshToken = response.refresh_token || this.refreshToken;
      this.scheduleRefresh();
    } catch (error) {
      console.error('Token refresh failed:', error);
      // Retry in 1 minute
      this.refreshTimeoutId = setTimeout(() => this.refresh(), 60000);
    }
  }
}
