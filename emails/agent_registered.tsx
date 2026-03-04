import React from 'react';
import {
  Body,
  Button,
  Container,
  Head,
  Html,
  Img,
  Link,
  Preview,
  Row,
  Section,
  Text,
} from '@react-email/components';

interface AgentRegisteredEmailProps {
  agentName: string;
  agentType: string;
  agentId: string;
  clientId: string;
  dashboardUrl: string;
  documentationUrl: string;
  supportEmail: string;
}

const AgentRegisteredEmail: React.FC<AgentRegisteredEmailProps> = ({
  agentName,
  agentType,
  agentId,
  clientId,
  dashboardUrl,
  documentationUrl,
  supportEmail,
}) => {
  const year = new Date().getFullYear();

  return (
    <Html>
      <Head>
        <title>AgentGate - Agent Registration Confirmation</title>
      </Head>
      <Preview>Your agent "{agentName}" has been successfully registered with AgentGate</Preview>
      <Body style={main}>
        <Container style={container}>
          {/* Header */}
          <Section style={header}>
            <Row style={headerContent}>
              <Text style={headerTitle}>🔐 AgentGate</Text>
            </Row>
            <Text style={headerSubtitle}>Agent Registration Confirmation</Text>
          </Section>

          {/* Main Content */}
          <Section style={content}>
            <Text style={greeting}>
              Hello,
            </Text>

            <Text style={body}>
              Your agent <strong>{agentName}</strong> has been successfully registered with AgentGate.
            </Text>

            {/* Agent Details Card */}
            <Section style={detailsCard}>
              <Row>
                <Text style={detailsLabel}>Agent Name</Text>
                <Text style={detailsValue}>{agentName}</Text>
              </Row>
              <Row>
                <Text style={detailsLabel}>Agent Type</Text>
                <Text style={detailsValue}>{agentType}</Text>
              </Row>
              <Row>
                <Text style={detailsLabel}>Agent ID</Text>
                <Text style={detailsValueMonospace}>{agentId}</Text>
              </Row>
              <Row>
                <Text style={detailsLabel}>Client ID</Text>
                <Text style={detailsValueMonospace}>{clientId}</Text>
              </Row>
              <Row>
                <Text style={detailsLabel}>Registration Date</Text>
                <Text style={detailsValue}>{new Date().toISOString().split('T')[0]}</Text>
              </Row>
            </Section>

            {/* Next Steps */}
            <Text style={subheading}>What's Next?</Text>

            <Section style={stepsContainer}>
              <Row style={step}>
                <Text style={stepNumber}>1</Text>
                <Text style={stepText}>
                  <strong>Generate Credentials:</strong> Your new client credentials are ready in your AgentGate dashboard
                </Text>
              </Row>
              <Row style={step}>
                <Text style={stepNumber}>2</Text>
                <Text style={stepText}>
                  <strong>Configure Agent:</strong> Update your agent configuration with the provided client ID and secret
                </Text>
              </Row>
              <Row style={step}>
                <Text style={stepNumber}>3</Text>
                <Text style={stepText}>
                  <strong>Set Token TTL:</strong> Configure appropriate token time-to-live values for your use case
                </Text>
              </Row>
              <Row style={step}>
                <Text style={stepNumber}>4</Text>
                <Text style={stepText}>
                  <strong>Test Connection:</strong> Verify connectivity to AgentGate from your agent
                </Text>
              </Row>
              <Row style={step}>
                <Text style={stepNumber}>5</Text>
                <Text style={stepText}>
                  <strong>Enable Monitoring:</strong> Start monitoring agent activity in the audit log
                </Text>
              </Row>
            </Section>

            {/* Important Info */}
            <Section style={warningBox}>
              <Text style={warningTitle}>⚠️ Important Security Notes</Text>
              <ul style={warningList}>
                <li style={warningItem}>
                  <strong>Never share</strong> your client credentials with anyone
                </li>
                <li style={warningItem}>
                  <strong>Rotate credentials</strong> regularly (every {
                    agentType === 'pipeline' ? '14 days' :
                    agentType === 'editor' ? '60 days' : '90 days'
                  })
                </li>
                <li style={warningItem}>
                  <strong>Enable MFA</strong> if your agent type requires it
                </li>
                <li style={warningItem}>
                  <strong>Monitor audit logs</strong> for any unusual activity
                </li>
                <li style={warningItem}>
                  <strong>Follow scoping rules</strong> in your policies
                </li>
              </ul>
            </Section>

            {/* CTA Buttons */}
            <Section style={buttonContainer}>
              <Button style={primaryButton} href={dashboardUrl}>
                View in Dashboard
              </Button>
              <Button style={secondaryButton} href={documentationUrl}>
                View Documentation
              </Button>
            </Section>

            {/* Additional Info */}
            <Text style={body}>
              For more information about configuring your agent, managing credentials, and best practices,
              please visit the <Link href={documentationUrl} style={link}>AgentGate documentation</Link>.
            </Text>

            <Text style={body}>
              If you have any questions or need assistance, please don't hesitate to reach out to our support team.
            </Text>
          </Section>

          {/* Footer */}
          <Section style={footer}>
            <Row>
              <Text style={footerText}>
                Questions? <Link href={`mailto:${supportEmail}`} style={link}>{supportEmail}</Link>
              </Text>
            </Row>
            <Row>
              <Text style={footerText}>
                Dashboard: <Link href={dashboardUrl} style={link}>agentgate.yourcompany.com</Link>
              </Text>
            </Row>
            <Row>
              <Text style={footerSubtle}>
                This is an automated message from AgentGate. Please do not reply to this email.
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

export default AgentRegisteredEmail;

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
  backgroundColor: '#1e40af',
  color: '#ffffff',
  padding: '32px 24px',
  textAlign: 'center' as const,
};

const headerContent = {
  marginBottom: '12px',
};

const headerTitle = {
  fontSize: '32px',
  fontWeight: 'bold',
  margin: '0',
  color: '#ffffff',
};

const headerSubtitle = {
  fontSize: '18px',
  color: '#e0e7ff',
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
  color: '#1e40af',
  marginTop: '24px',
  marginBottom: '12px',
};

const detailsCard = {
  backgroundColor: '#f9fafb',
  border: '1px solid #e5e7eb',
  borderRadius: '8px',
  padding: '16px',
  marginBottom: '20px',
  marginTop: '16px',
};

const detailsLabel = {
  fontSize: '12px',
  fontWeight: '600',
  color: '#6b7280',
  textTransform: 'uppercase' as const,
  letterSpacing: '0.5px',
  marginBottom: '4px',
};

const detailsValue = {
  fontSize: '14px',
  color: '#111827',
  fontWeight: '500',
  marginBottom: '12px',
};

const detailsValueMonospace = {
  fontSize: '13px',
  fontFamily: 'monospace',
  backgroundColor: '#f3f4f6',
  padding: '4px 8px',
  borderRadius: '4px',
  color: '#1f2937',
  marginBottom: '12px',
  wordBreak: 'break-all' as const,
};

const stepsContainer = {
  marginTop: '16px',
  marginBottom: '20px',
};

const step = {
  display: 'flex' as const,
  marginBottom: '12px',
  gap: '12px',
};

const stepNumber = {
  backgroundColor: '#1e40af',
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

const stepText = {
  fontSize: '14px',
  color: '#374151',
  margin: '0',
  paddingTop: '2px',
};

const warningBox = {
  backgroundColor: '#fef3c7',
  border: '1px solid #fcd34d',
  borderRadius: '8px',
  padding: '16px',
  marginBottom: '20px',
};

const warningTitle = {
  fontSize: '14px',
  fontWeight: '600',
  color: '#92400e',
  marginTop: '0',
  marginBottom: '8px',
};

const warningList = {
  fontSize: '13px',
  color: '#78350f',
  paddingLeft: '20px',
  margin: '0',
};

const warningItem = {
  marginBottom: '6px',
  lineHeight: '1.5',
};

const buttonContainer = {
  marginTop: '20px',
  marginBottom: '20px',
  display: 'flex' as const,
  gap: '12px',
  justifyContent: 'center' as const,
};

const primaryButton = {
  backgroundColor: '#1e40af',
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

const link = {
  color: '#1e40af',
  textDecoration: 'underline',
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
