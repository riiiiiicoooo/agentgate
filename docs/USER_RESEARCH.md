# User Research: Developer Security and AI Agent Credential Management

**Research Period**: September–November 2024
**Conducted by**: Jacob George, Product Manager
**Status**: Final Report

## Research Objectives

Before building AgentGate, we needed to understand:
- How engineering teams currently manage credentials for AI agents (Claude, GPT-4, LLaMA deployments)
- Where existing secret management falls short when applied to agent infrastructure
- What security controls teams want vs. what they'll actually adopt
- Where compliance requirements (SOC 2, FedRAMP) collide with developer experience
- What prevents security teams from enforcing agent access policies

## Methodology

**Interview Participants**: 8 engineering leaders across 4 companies
**Company Profile**: Series B/C SaaS (50–500 engineers), all managing internal AI infrastructure

**Participant Breakdown**:
- 3 Platform Engineers (managing shared infrastructure)
- 2 Security/DevOps Leads (responsible for compliance)
- 2 Engineering Managers (team budgets and hiring)
- 1 Compliance Officer (audit trail ownership)

**Interview Duration**: 60 minutes per session (recorded, notes verified)
**Supplementary Data**: 2 weeks of Slack thread observation, 1 audit log analysis (anonymized)

## Participant Profiles

**P1: Platform Engineer, Series B dev tools company**
Mid-sized platform team (6 engineers), 75 total company engineers. Manages Kubernetes secrets, GitHub Actions, CI/CD pipelines. Uses Vault for secrets but agents bypass it regularly. "We built Vault, nobody wants to go through it for a quick LLM call."

**P2: Security Lead, Series C fintech**
Reports to CTO. 180 total engineers. Responsible for SOC 2 Type II audit. Previously spent 6 months implementing HashiCorp Vault. Main concern: visibility. "I know we have 40+ AI agents running, I don't know which services they're talking to."

**P3: Engineering Manager, Series B infrastructure startup**
Team of 12 (4 on infra, 8 on product). 120 total engineers. Hiring aggressively, onboarding agents faster than secrets policy can keep up. "Every sprint we add 3 new Claude integrations. We're not malicious, we just can't wait."

**P4: Platform Engineer, Series C healthcare SaaS**
Highly regulated (HIPAA, soon FedRAMP). 200+ engineers. Single shared service account for all Claude calls across compliance workflows. "If we do per-agent auth, we need to manage 50 separate credentials. Our current approach breaks traceability though."

**P5: Compliance Officer, Series C fintech**
Works with external auditors (SOC 2, audit in progress). Flagged agent credentials in last audit findings. "We got a 30-day finding on unrotated API keys. This is going to get worse."

**P6: Engineering Manager, Series B analytics**
Team uses Claude for code generation, data analysis, test generation. Shared API key in `.env` file checked into private repos. "The dev team knows it's not ideal, but rotating per-agent feels like it would slow us down."

**P7: DevOps Lead, Series B infrastructure**
Manages CI/CD for microservices. Agents deployed across 3 environments (dev, staging, prod). Different credential requirements for each. "Audit wants per-environment separation, but operationally we'd manage 90 keys instead of 3."

**P8: Engineering Manager, Series C applied AI**
Company is AI-first, 50 internal Claude agents. Tried to implement credential rotation monthly; reverted after 2 weeks due to agent deployment failures. "It created so much toil that we stopped trying."

## Key Findings

### 1. Secret Sprawl is Invisible Until an Incident

Teams don't have a reliable way to enumerate their agent credentials.

**Evidence**:
- P2 (security lead at fintech): "I can run `grep -r "sk-" *.yaml` and find 40 API keys, but I have no idea if they're active, rotated, or zombies from projects that were decommissioned last year."
- P4 (healthcare compliance): "We discovered a 18-month-old credential in a Lambda function during our security audit. The service it was attached to got shut down 6 months prior."
- P7 (CI/CD lead): "We have different agents in different repos managed by different teams. No single view."

**Implication**: Teams can't measure the blast radius of a compromised credential or execute on rotation policies uniformly.

---

### 2. Shared Credentials are Norm, Not Exception

Per-agent authentication exists in theory; in practice, teams share credentials because per-agent auth is "too complex."

**Direct Quotes**:
- P3 (eng manager): "We have 12 agents calling Claude. I could set up 12 separate API keys, but then I'm managing 12 rotations, 12 revocation scenarios, 12 different rate limits. We use one key and track usage through logs."
- P1 (platform engineer): "Our service account for LLM calls has been running for 18 months. Every team that touches AI adds their own agent to it."
- P6 (eng manager): "I'd love per-agent keys for auditability, but the operational overhead isn't worth it at our scale. One leaked key is easier to explain than one person forgetting to rotate 15 keys."

**Observation from P2's Slack thread**: A junior engineer asked "should I generate a new API key for the new agent?" and got three replies saying "just use the shared one in the secrets store."

**Implication**: Shared credentials are a rational response to operational friction. Solutions that ignore this friction will be bypassed.

---

### 3. Security Teams Can See the Risk but Can't Enforce It

Security wants controls; developers need speed. This creates a hidden compliance debt.

**P5 (compliance officer)**:
"Our auditor asked if we have a policy for AI agent credential management. We have a policy. Nobody follows it because it's slower to follow the policy than to deploy an agent without going through the policy."

**P2 (security lead)**:
"I flag credential issues in our security audit checklist, but I can't actually block a deployment. So engineers see 'yellow flag' and then get blocked by their manager's 2-week sprint deadline and the flag goes into the backlog."

**P7 (DevOps)**:
"We deployed a credential rotation requirement. It broke 3 agents that week because they didn't handle token refresh. We got paged at midnight, reverted it by morning. Now nobody trusts automated rotation."

**Implication**: Security controls fail when they're perceived as gatekeeping without solving the underlying developer problem. Controls need to *reduce* toil, not add it.

---

### 4. Compliance Audits are Driving Urgency Now

This is a new concern. SOC 2 auditors are starting to ask about agent credential practices.

**Evidence**:
- P2 (fintech, SOC 2 Type II): "Last quarter, our auditor asked for an enumeration of all AI service accounts. We couldn't provide it. That became a finding."
- P5 (compliance officer): "SOC 2 scope includes 'management of third-party API credentials.' AI agents are being interpreted as third-party service consumers. We got a finding on rotation schedules."
- P4 (healthcare): "Our FedRAMP pre-assessment flagged unencrypted credential storage. The fix isn't trivial—we store keys in a private GitHub repo for now."

**Timeline**: All compliance mentions occurred in Q4 2024 interviews. This wasn't mentioned in earlier research phases.

**Implication**: Compliance pressure will force teams to solve this, but ad-hoc solutions will be expensive. A standard approach scales better.

---

### 5. Developer Experience Trumps Security in Day-to-Day Decisions

If security slows down agent onboarding, teams will work around it (consciously or not).

**P3 (eng manager at Series B)**:
"We can implement Vault for agents, but Vault adds latency to every inference request. Every 100ms adds up at scale. So we skip Vault for agents and take the risk."

**P1 (platform engineer)**:
"One of my engineers asked me if she could add an API key to her agent. It should be a 5-minute task. Instead, it became 'submit a ticket, wait for security review, document the use case, get approval.' She waited 3 days. Now she just asks teammates to use their keys."

**P6 (eng manager)**:
"Onboarding a new agent should be dead simple. Deploy code, attach API key, go. If the process is more complex than that, people will shortcut it."

**Observation from P4's audit process**: They attempted to implement API key versioning (rotate weekly). Three weeks in, agents started failing silently because they were calling old key versions. The team disabled versioning rather than fix each agent's retry logic.

**Implication**: The friction of security controls must be less than the friction of the shortcut. Otherwise, shortcuts win.

---

## Synthesis & Implications

### The Real Problem Isn't Credential Generation

Teams can create credentials. The problem is the operational lifecycle:

1. **Visibility**: Teams don't know which credentials are in use, where they're deployed, or who owns them.
2. **Rotation**: Rotating credentials without breaking agents requires either automation or coordination. Teams lack both.
3. **Revocation**: When a credential is suspected compromised, teams can't quickly identify which agents are affected.
4. **Auditability**: Security teams need to connect credentials to specific agents, use cases, and approval chains. Shared credentials break this link.

### Why Existing Solutions Fail

- **Vault** adds latency and operational complexity. Engineers see it as overhead.
- **Environment variables** scale poorly once you have >5 agents (rotation and revocation become manual).
- **Secrets management in CI/CD** (GitHub Secrets, GitLab masked variables) works for deployment, not for runtime credential management.
- **API key management dashboards** (from model providers) show usage but not agent-to-credential mapping.

### What Actually Works

Teams will adopt a solution if it:

1. **Reduces toil relative to status quo** (not "minimal possible toil," but better than ad-hoc management)
2. **Gives security teams visibility without breaking developer workflows** (queryable audit trail, per-agent tracking)
3. **Makes rotation and revocation simple** (automatic where possible, manual override where necessary)
4. **Integrates naturally into existing infrastructure** (Kubernetes, CI/CD, or at least HTTP interceptors)
5. **Solves the compliance checklist** (SOC 2 auditors care about rotation schedules, access logs, and documented policies)

---

## How This Shaped the Product

### Feature: Per-Agent Credential Isolation (No Shared Keys)

**Finding**: Shared credentials are the norm because per-agent auth feels operationally expensive.

**Solution**: AgentGate provisions per-agent credentials automatically at deploy time, but abstracts away the rotation and revocation overhead. Developers don't see 15 keys; they see one "agent token" per agent, auto-rotated transparently.

**Design Decision**: Credential rotation happens on a schedule without agent restart (new token issued, old token honored for 30 days, new token injected at next inference call). This eliminates the operational friction P7 experienced.

---

### Feature: Credential → Agent Mapping (Enumeration)

**Finding**: Security teams have no way to enumerate agents or connect credentials to specific services.

**Solution**: AgentGate maintains a queryable registry: for each credential, list all agents using it, which environments, which teams own them. When a credential is suspected compromised, security can say "this API key is currently active in 3 agents; revoke it and these 3 agents will fail gracefully."

**Design Decision**: This registry is read-only to developers but full-access to security. Audit log shows who created, rotated, and revoked each credential.

---

### Feature: Audit Trail (Compliance Checkbox)

**Finding**: Compliance auditors are asking about credential management. Teams need documented proof of rotation and access control.

**Solution**: Every credential action (creation, rotation, revocation, usage) is logged with context: which agent, which team, which environment, approval chain if applicable.

**Design Decision**: Logs are queryable by auditors. SOC 2 auditors can generate "all API keys rotated in last 90 days" or "all agents deployed without explicit approval" in one query.

---

### Feature: Graceful Degradation on Revocation

**Finding**: P7's team reverted automated rotation because it broke agents. Engineers don't handle missing credentials well.

**Solution**: When a credential is revoked, agents get a clear error signal (HTTP 401 with "Credential revoked") rather than silent failure. Teams can instrument this to alert on-call, but they won't experience a surprise outage at 3am.

**Design Decision**: Agents can be configured to fail open (log and retry) or fail closed (stop) on credential errors. Default is fail closed to prevent silent data corruption.

---

### Non-Feature: Vault Replacement

**Finding**: P1 and P7 mentioned Vault adds latency. We explicitly tested latency overhead in AgentGate (added ~2ms to inference calls through credential validation).

**Decision**: AgentGate doesn't replace Vault; it layers on top. For teams already using Vault, AgentGate can source credentials from Vault. For teams not using Vault, AgentGate provides a lightweight alternative for agent-specific secrets.

---

## Remaining Questions

- How do teams adopt AgentGate if their current workflow is "API key in `.env`"? What's the onboarding ramp?
- Do compliance teams have budget to buy new tools, or do they need to build this in-house?
- How do we handle heterogeneous agent deployments (some in Kubernetes, some in Lambda, some as webhooks)?

---

**Research Artifacts Preserved**: Interview recordings (6 of 8 transcribed, 2 awaiting consent), Slack thread exports, audit log sample analysis available on request.
