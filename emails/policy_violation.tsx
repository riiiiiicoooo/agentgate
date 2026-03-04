import React from 'react';
import {
  Body,
  Button,
  Container,
  Head,
  Html,
  Link,
  Preview,
  Row,
  Section,
  Text,
} from '@react-email/components';

interface PolicyViolationEmailProps {
  violationType: 'DENIED_ACCESS' | 'INJECTION_DETECTED' | 'RATE_LIMIT_EXCEEDED' | 'MFA_FAILURE';
  agentId: string;
  agentName: string;
  action: string;
  resource: string;
  timestamp: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  details: Record<string, any>;
  auditLogUrl: string;
  dashboardUrl: string;
  responseAction?: string;
}

const PolicyViolationEmail: React.FC<PolicyViolationEmailProps> = ({
  violationType,
  agentId,
  agentName,
  action,
  resource,
  timestamp,
  severity,
  details,
  auditLogUrl,
  dashboardUrl,
  responseAction,
}) => {
  const year = new Date().getFullYear();

  const severityColors = {
    low: { background: '#dcfce7', border: '#86efac', text: '#15803d' },
    medium: { background: '#fef3c7', border: '#fcd34d', text: '#92400e' },
    high: { background: '#fee2e2', border: '#fca5a5', text: '#991b1b' },
    critical: { background: '#7f1d1d', border: '#dc2626', text: '#fecaca' },
  };

  const severityColor = severityColors[severity];
  const severityEmoji = severity === 'critical' ? '🚨' : severity === 'high' ? '⚠️' : severity === 'medium' ? '⚡' : 'ℹ️';

  const violationTypeLabels = {
    DENIED_ACCESS: 'Unauthorized Access Attempt',
    INJECTION_DETECTED: 'Prompt Injection Detected',
    RATE_LIMIT_EXCEEDED: 'Rate Limit Exceeded',
    MFA_FAILURE: 'MFA Verification Failed',
  };

  return (
    <Html>
      <Head>
        <title>AgentGate - Policy Violation Alert</title>
      </Head>
      <Preview>{severityEmoji} {violationTypeLabels[violationType]} - {agentName}</Preview>
      <Body style={main}>
        <Container style={container}>
          {/* Severity Header */}
          <Section
            style={{
              ...header,
              backgroundColor: severity === 'critical' ? '#7f1d1d' : severity === 'high' ? '#991b1b' : severity === 'medium' ? '#92400e' : '#155e75',
            }}
          >
            <Row>
              <Text style={headerTitle}>
                {severityEmoji} {violationTypeLabels[violationType]}
              </Text>
            </Row>
            <Text
              style={{
                ...headerSubtitle,
                fontSize: '18px',
                color: severity === 'critical' ? '#fecaca' : '#fca5a5',
              }}
            >
              Security Alert - Severity: {severity.toUpperCase()}
            </Text>
          </Section>

          {/* Main Content */}
          <Section style={content}>
            <Text style={greeting}>Security Team,</Text>

            <Text style={body}>
              A policy violation has been detected in AgentGate. Please review the details below and take appropriate action.
            </Text>

            {/* Violation Summary Card */}
            <Section style={{ ...violationCard, borderLeftColor: severityColor.border }}>
              <Row>
                <Text style={violationLabel}>Violation Type</Text>
                <Text style={violationValue}>{violationTypeLabels[violationType]}</Text>
              </Row>
              <Row>
                <Text style={violationLabel}>Severity</Text>
                <Text
                  style={{
                    ...violationValue,
                    color: severityColor.text,
                    backgroundColor: severityColor.background,
                    padding: '4px 8px',
                    borderRadius: '4px',
                    fontWeight: '600',
                    textTransform: 'uppercase',
                    fontSize: '12px',
                  }}
                >
                  {severity}
                </Text>
              </Row>
              <Row>
                <Text style={violationLabel}>Time</Text>
                <Text style={violationValue}>{new Date(timestamp).toLocaleString()}</Text>
              </Row>
            </Section>

            {/* Agent Details */}
            <Text style={subheading}>Agent Information</Text>
            <Section style={detailsBox}>
              <Row>
                <Text style={detailLabel}>Agent Name</Text>
                <Text style={detailValue}>{agentName}</Text>
              </Row>
              <Row>
                <Text style={detailLabel}>Agent ID</Text>
                <Text style={detailValueMonospace}>{agentId}</Text>
              </Row>
              <Row>
                <Text style={detailLabel}>Attempted Action</Text>
                <Text style={detailValue}>{action}</Text>
              </Row>
              <Row>
                <Text style={detailLabel}>Target Resource</Text>
                <Text style={detailValue}>{resource}</Text>
              </Row>
            </Section>

            {/* Additional Details */}
            {Object.keys(details).length > 0 && (
              <>
                <Text style={subheading}>Additional Details</Text>
                <Section style={detailsBox}>
                  {Object.entries(details).map(([key, value], idx) => (
                    <Row key={idx}>
                      <Text style={detailLabel}>{formatKey(key)}</Text>
                      <Text style={detailValue}>{JSON.stringify(value)}</Text>
                    </Row>
                  ))}
                </Section>
              </>
            )}

            {/* Recommended Actions */}
            <Text style={subheading}>Recommended Actions</Text>
            <Section style={actionsBox}>
              {severity === 'critical' && (
                <>
                  <Row style={actionItem}>
                    <Text style={actionNumber}>1</Text>
                    <Text style={actionText}>
                      <strong>Immediate Review:</strong> Review the violation details in the audit log
                    </Text>
                  </Row>
                  <Row style={actionItem}>
                    <Text style={actionNumber}>2</Text>
                    <Text style={actionText}>
                      <strong>Isolate Agent:</strong> Consider temporarily suspending the agent if compromise is suspected
                    </Text>
                  </Row>
                  <Row style={actionItem}>
                    <Text style={actionNumber}>3</Text>
                    <Text style={actionText}>
                      <strong>Rotate Credentials:</strong> Force credential rotation for the affected agent
                    </Text>
                  </Row>
                  <Row style={actionItem}>
                    <Text style={actionNumber}>4</Text>
                    <Text style={actionText}>
                      <strong>Forensic Analysis:</strong> Review historical access logs for this agent
                    </Text>
                  </Row>
                  <Row style={actionItem}>
                    <Text style={actionNumber}>5</Text>
                    <Text style={actionText}>
                      <strong>Incident Report:</strong> Escalate to incident management team
                    </Text>
                  </Row>
                </>
              )}
              {severity === 'high' && (
                <>
                  <Row style={actionItem}>
                    <Text style={actionNumber}>1</Text>
                    <Text style={actionText}>
                      Review the full context in the audit log within the hour
                    </Text>
                  </Row>
                  <Row style={actionItem}>
                    <Text style={actionNumber}>2</Text>
                    <Text style={actionText}>
                      Verify agent credentials and permissions are still appropriate
                    </Text>
                  </Row>
                  <Row style={actionItem}>
                    <Text style={actionNumber}>3</Text>
                    <Text style={actionText}>
                      Consider additional monitoring or alerts for this agent
                    </Text>
                  </Row>
                </>
              )}
              {severity === 'medium' && (
                <>
                  <Row style={actionItem}>
                    <Text style={actionNumber}>1</Text>
                    <Text style={actionText}>
                      Review the violation details when convenient
                    </Text>
                  </Row>
                  <Row style={actionItem}>
                    <Text style={actionNumber}>2</Text>
                    <Text style={actionText}>
                      Monitor for patterns or repeated violations
                    </Text>
                  </Row>
                </>
              )}
              {severity === 'low' && (
                <Row style={actionItem}>
                  <Text style={actionText}>
                    This is for informational purposes. No immediate action required unless patterns emerge.
                  </Text>
                </Row>
              )}
            </Section>

            {/* Response Status */}
            {responseAction && (
              <Section style={responseBox}>
                <Text style={responseLabel}>Response Taken</Text>
                <Text style={responseValue}>{responseAction}</Text>
              </Section>
            )}

            {/* CTA Buttons */}
            <Section style={buttonContainer}>
              <Button style={primaryButton} href={auditLogUrl}>
                View in Audit Log
              </Button>
              <Button style={secondaryButton} href={dashboardUrl}>
                View Dashboard
              </Button>
            </Section>

            {/* Additional Info */}
            <Text style={body}>
              For more information about this violation, please check the audit log and security dashboard.
              Multiple violations may indicate a security incident that requires investigation.
            </Text>
          </Section>

          {/* Footer */}
          <Section style={footer}>
            <Row>
              <Text style={footerText}>
                Questions? Contact your security team or system administrator.
              </Text>
            </Row>
            <Row>
              <Text style={footerSubtle}>
                This is an automated alert from AgentGate. Do not reply to this email.
              </Text>
            </Row>
            <Row>
              <Text style={footerCopyright}>
                © {year} AgentGate. All rights reserved.
              </Text>
            </Row>
          </Section>
        </Container>
      </Body>
    </Html>
  );
};

export default PolicyViolationEmail;

// Helper function to format object keys
function formatKey(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase());
}

// Styles
const main = {
  backgroundColor: '#f5f5f5',
  fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif',
  padding: '20px 0',
};

const container = {
  backgroundColor: '#ffffff',
  maxWidth: '600px',
  margin: '0 auto',
  marginBottom: '20px',
};

const header = {
  color: '#ffffff',
  padding: '32px 24px',
  textAlign: 'center' as const,
};

const headerTitle = {
  fontSize: '28px',
  fontWeight: 'bold',
  margin: '0',
  color: '#ffffff',
};

const headerSubtitle = {
  fontSize: '16px',
  margin: '0',
  marginTop: '8px',
};

const content = {
  padding: '32px 24px',
};

const greeting = {
  fontSize: '16px',
  fontWeight: '600',
  marginBottom: '16px',
  marginTop: '0',
};

const body = {
  fontSize: '14px',
  lineHeight: '1.6',
  color: '#374151',
  marginBottom: '16px',
};

const subheading = {
  fontSize: '16px',
  fontWeight: '600',
  color: '#1f2937',
  marginTop: '24px',
  marginBottom: '12px',
};

const violationCard = {
  backgroundColor: '#f9fafb',
  border: '1px solid #e5e7eb',
  borderLeft: '4px solid #ef4444',
  borderRadius: '8px',
  padding: '16px',
  marginBottom: '20px',
  marginTop: '16px',
};

const violationLabel = {
  fontSize: '12px',
  fontWeight: '600',
  color: '#6b7280',
  textTransform: 'uppercase' as const,
  letterSpacing: '0.5px',
  marginBottom: '4px',
};

const violationValue = {
  fontSize: '14px',
  color: '#111827',
  fontWeight: '500',
  marginBottom: '12px',
};

const detailsBox = {
  backgroundColor: '#f9fafb',
  border: '1px solid #e5e7eb',
  borderRadius: '8px',
  padding: '16px',
  marginBottom: '20px',
};

const detailLabel = {
  fontSize: '12px',
  fontWeight: '600',
  color: '#6b7280',
  textTransform: 'uppercase' as const,
  letterSpacing: '0.5px',
  marginBottom: '4px',
  width: '30%',
};

const detailValue = {
  fontSize: '14px',
  color: '#111827',
  marginBottom: '12px',
  width: '70%',
};

const detailValueMonospace = {
  fontSize: '13px',
  fontFamily: 'monospace',
  backgroundColor: '#f3f4f6',
  padding: '4px 8px',
  borderRadius: '4px',
  color: '#1f2937',
  marginBottom: '12px',
  wordBreak: 'break-all' as const,
};

const actionsBox = {
  backgroundColor: '#eff6ff',
  border: '1px solid #bfdbfe',
  borderRadius: '8px',
  padding: '16px',
  marginBottom: '20px',
};

const actionItem = {
  display: 'flex' as const,
  marginBottom: '12px',
  gap: '12px',
};

const actionNumber = {
  backgroundColor: '#3b82f6',
  color: '#ffffff',
  width: '24px',
  height: '24px',
  borderRadius: '50%',
  textAlign: 'center' as const,
  fontWeight: 'bold',
  lineHeight: '24px',
  fontSize: '12px',
  flexShrink: 0,
};

const actionText = {
  fontSize: '14px',
  color: '#1e40af',
  margin: '0',
  paddingTop: '2px',
};

const responseBox = {
  backgroundColor: '#ecfdf5',
  border: '1px solid #a7f3d0',
  borderRadius: '8px',
  padding: '16px',
  marginBottom: '20px',
};

const responseLabel = {
  fontSize: '12px',
  fontWeight: '600',
  color: '#047857',
  textTransform: 'uppercase' as const,
  marginBottom: '8px',
};

const responseValue = {
  fontSize: '14px',
  color: '#065f46',
  margin: '0',
};

const buttonContainer = {
  marginTop: '20px',
  marginBottom: '20px',
  display: 'flex' as const,
  gap: '12px',
  justifyContent: 'center' as const,
};

const primaryButton = {
  backgroundColor: '#ef4444',
  color: '#ffffff',
  padding: '12px 32px',
  borderRadius: '6px',
  textDecoration: 'none',
  fontSize: '14px',
  fontWeight: '600',
  display: 'inline-block' as const,
};

const secondaryButton = {
  backgroundColor: '#e5e7eb',
  color: '#111827',
  padding: '12px 32px',
  borderRadius: '6px',
  textDecoration: 'none',
  fontSize: '14px',
  fontWeight: '600',
  display: 'inline-block' as const,
};

const footer = {
  backgroundColor: '#f9fafb',
  borderTop: '1px solid #e5e7eb',
  padding: '24px',
  textAlign: 'center' as const,
};

const footerText = {
  fontSize: '13px',
  color: '#6b7280',
  margin: '4px 0',
};

const footerSubtle = {
  fontSize: '12px',
  color: '#9ca3af',
  margin: '8px 0',
  fontStyle: 'italic' as const,
};

const footerCopyright = {
  fontSize: '12px',
  color: '#d1d5db',
  margin: '8px 0',
};
