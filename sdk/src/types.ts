/**
 * Type Definitions
 *
 * TypeScript interfaces for AgentGate API
 */

// Authentication

export interface AuthRequest {
  grant_type: 'client_credentials' | 'refresh_token';
  client_id: string;
  client_secret?: string;
  refresh_token?: string;
  scope?: string[];
}

export interface TokenResponse {
  access_token: string;
  refresh_token?: string;
  token_type: string;
  expires_in: number;
}

export interface TokenPayload {
  agent_id: string;
  client_id: string;
  scopes: string[];
  token_type: string;
  iat: number;
  exp: number;
}

// Agents

export interface AgentCreateRequest {
  name: string;
  description?: string;
  scopes: string[];
  metadata?: Record<string, unknown>;
}

export interface Agent {
  agent_id: string;
  name: string;
  description?: string;
  scopes: string[];
  client_id: string;
  status: 'active' | 'inactive' | 'suspended' | 'archived';
  created_at: string;
  updated_at: string;
  last_auth_at?: string;
  metadata: Record<string, unknown>;
}

export interface CredentialRotationRequest {
  rotate_client_secret: boolean;
  rotate_api_keys: boolean;
}

export interface CredentialRotationResponse {
  agent_id: string;
  client_secret?: string;
  api_key?: string;
  rotated_at: string;
  message: string;
}

// Policies

export interface PolicyCondition {
  field: string;
  operator: 'eq' | 'neq' | 'in' | 'contains' | 'matches';
  value: string;
}

export interface PolicyRule {
  effect: 'allow' | 'deny';
  actions: string[];
  resources: string[];
  conditions?: PolicyCondition[];
}

export interface PolicyCreateRequest {
  name: string;
  description?: string;
  rules: PolicyRule[];
  tags?: string[];
}

export interface Policy {
  policy_id: string;
  name: string;
  description?: string;
  rules: PolicyRule[];
  tags?: string[];
  created_at: string;
  updated_at: string;
  created_by: string;
}

export interface PolicySimulationRequest {
  agent_id: string;
  action: string;
  resource: string;
  context?: Record<string, unknown>;
}

export interface PolicySimulationResult {
  agent_id: string;
  action: string;
  resource: string;
  decision: 'allow' | 'deny' | 'no_match';
  matching_rules: PolicyRule[];
  reason: string;
}

// Secrets

export interface SecretLeaseRequest {
  secret_name: string;
  ttl_seconds?: number;
  justification?: string;
}

export interface SecretLease {
  lease_id: string;
  secret_name: string;
  secret_value: string;
  ttl_seconds: number;
  issued_at: string;
  expires_at: string;
  renewable: boolean;
}

export interface SecretRenewalRequest {
  lease_id: string;
  additional_ttl_seconds?: number;
  justification?: string;
}

export interface SecretRotationRequest {
  secret_name: string;
  new_value?: string;
  rotation_strategy?: 'random' | 'incremental' | 'custom';
}

export interface SecretRotationResponse {
  secret_name: string;
  rotated_at: string;
  new_version: string;
  old_version_revoked_at?: string;
  reason: string;
}

export interface SecretStatus {
  secret_name: string;
  latest_version: string;
  created_at: string;
  last_rotated?: string;
  rotation_enabled: boolean;
  rotation_interval_days?: number;
}

// Audit

export interface AuditEvent {
  event_id: string;
  timestamp: string;
  event_type: string;
  actor_agent_id: string;
  actor_ip?: string;
  resource_type: string;
  resource_id: string;
  action: string;
  status: 'success' | 'failure';
  details: Record<string, unknown>;
  severity: 'info' | 'warning' | 'error' | 'critical';
}

export interface AuditQueryRequest {
  start_time?: string;
  end_time?: string;
  event_type?: string;
  actor_agent_id?: string;
  resource_type?: string;
  resource_id?: string;
  status?: string;
  severity?: string;
  limit?: number;
  offset?: number;
}

export interface AuditQueryResponse {
  events: AuditEvent[];
  total: number;
  offset: number;
  limit: number;
  query_time_ms: number;
}

export interface ComplianceReport {
  report_id: string;
  generated_at: string;
  compliance_framework: string;
  organization: string;
  period_start: string;
  period_end: string;
  findings: Record<string, unknown>;
  evidence_count: number;
  summary: string;
}

// Gateway / LLM

export interface LLMRequest {
  model: string;
  messages: Array<{ role: string; content: string }>;
  temperature?: number;
  max_tokens?: number;
  top_p?: number;
}

export interface LLMResponse {
  request_id: string;
  model: string;
  content: string;
  tokens_used: number;
  tokens_remaining: number;
  cost_estimate: number;
}

export interface TokenBudgetInfo {
  agent_id: string;
  budget_limit: number;
  tokens_used: number;
  tokens_remaining: number;
  reset_at: string;
}

// Error

export class AgentGateError extends Error {
  constructor(
    public statusCode: number,
    public detail: string,
  ) {
    super(detail);
    this.name = 'AgentGateError';
  }
}

// Pagination

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  offset: number;
  limit: number;
}
