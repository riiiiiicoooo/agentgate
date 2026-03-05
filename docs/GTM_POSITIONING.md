# GTM Positioning: AgentGate

## Market Context

15M+ developers globally now use AI agents (Claude, GPT, local models) in production. Agents are becoming standard—they run deployments, debug code, query databases, generate content. But security teams are starting to ask: *Who is this agent? What can it access? Can we audit where it went?*

The problem: Developers currently own the buying decision for agent tooling. They need access control, but they're not security experts. Existing enterprise tools address infrastructure or secrets, but not agent identity.

This is a category gap, and category gaps are where platforms get built.

## Competitive Positioning

**vs. HashiCorp Vault (infrastructure-first)**
- Vault: Manages secrets, not identity; assumes infrastructure-centric security model
- Us: Agent-first; each agent is a principal with policies and audit trails

**vs. 1Password Service Accounts (secrets-only)**
- 1Password: Rotates secrets, no policy engine, no audit of what agents do with secrets
- Us: Full IAM for agents; policy engine governs agent actions, audit shows exactly what happened

**vs. Homegrown Solutions (custom monitoring)**
- DIY: Months to build, covers only specific use cases, no compliance tooling, vendor risk on team
- Us: Open-source core + enterprise features, works with any agent, compliance-ready

**Category Creation**: "AI Agent IAM" — Identity and Access Management purpose-built for AI agents, not legacy infrastructure.

**Positioning Statement**: "Every agent should have an identity, a policy, and an audit trail. AgentGate makes it easy."

## Target Buyer Journey

**Phase 1: Discovery**
- Developer finds open-source core on GitHub, tries it with their agent
- Low friction; MIT license, 5-minute setup

**Phase 2: Scaling Friction**
- Org now has 10+ agents deployed across multiple teams
- No way to audit agent behavior across the org
- Developer hits scaling wall; security team asks questions

**Phase 3: Enterprise Conversation**
- Developer escalates to platform engineering lead or security team
- Security leader wants: policy engine, SSO integration, audit logging, compliance evidence
- Commercial deal triggered

**Phase 4: Procurement**
- Security team validates compliance (SOC 2, audit trail, role-based access)
- Deal moves through procurement

## Open-Source Strategy

**Core Open-Source**: Gateway + basic policy engine (MIT license)
- Authentication and agent identity
- Whitelist/blacklist permissions
- Basic audit logging
- Works with Copilot, Cursor, Claude, local models

**Why?**: Open-source removes adoption friction and builds community trust. Developers try it for free. Enterprise features become obvious at scale.

**Enterprise Features** (commercial, not open-source):
- Advanced audit logging (cloud-based, searchable, compliance-grade retention)
- SSO integration (Okta, Azure AD, Google Workspace)
- Role-based access control (RBAC) with policy templates
- Compliance reports (SOC 2, FedRAMP, HIPAA audit trails)
- SLA-backed support

## Developer-First Adoption Motion

**CLI-First, Not Dashboard-First**
- Developers don't start with dashboards. They start with commands.
- AgentGate CLI: `agent init`, `agent add permission`, `agent audit log`

**5-Minute Quickstart**
- Developers should go from zero to running in 5 minutes
- Pre-built integrations with Copilot, Cursor, Claude (no custom code required)
- Proxy pattern: AgentGate sits between agent and resources; no agent code changes

**Works with Existing Tools**
- Not asking developers to rip-and-replace their stack
- Drop-in integration with popular agent frameworks
- Existing environment variables and secrets still work

## Enterprise Sales Motion

**Security-Triggered, Not Proactive**
- Conversion happens when a trigger fires:
  1. SOC 2 auditor asks: "Who has access to what APIs?"
  2. Security incident: Agent credentials were over-permissioned
  3. Platform team decides to standardize agent tooling org-wide

**Sales Playbook**
- Content marketing: Blog posts on "agent security incidents" (anonymized), case studies
- In-bound from security teams finding us
- Direct sales team focuses on $50K+ ARR accounts (20+ agents)

## Pricing Model

**Free Tier**
- Up to 10 agents
- Basic audit logging (30-day retention)
- No SSO, no advanced policies
- Converts to paid when org scales agents

**Team Plan** ($15/agent/month)
- Up to 100 agents
- Advanced policy engine
- 90-day audit logging
- SSO integration
- Minimum 10 agents = $1,800/month

**Enterprise** (custom pricing)
- Unlimited agents
- Compliance reporting (SOC 2, FedRAMP)
- Dedicated support
- Custom SLAs
- Typical: $5-10K/month

## Channel Strategy

**Developer Conferences**
- DefCon AI Village, Black Hat, OWASP meetings
- Sponsor developer security talks (not vendor booths)
- Demo the CLI, not the enterprise dashboard

**Security Community Content**
- Blog posts on "5 ways agent security incidents happen" (and how to prevent them)
- Webinars with security teams on agent governance
- Podcast appearances on security and AI

**Integration Partnerships**
- GitHub Marketplace listing
- Cursor Extensions
- Anthropic Marketplace (for Claude-specific agent security)
- Work with Hugging Face on model card security

## Key Metrics

- **Developer Downloads**: Open-source adoption velocity
- **Upgrade Rate**: % of free users that convert to Team or Enterprise
- **Average Agents per Account**: Growth in agent density per customer
- **Time to Enterprise**: Days from open-source first use to enterprise sales conversation
- **Net Expansion**: Revenue growth from existing customers adding agents

## PM Role: Strategic Influence

Scope: Shaped the open-source-first go-to-market strategy, target buyer journey (developer → platform engineer → security), and enterprise conversion triggers. Influenced pricing tier structure and channel prioritization. Did not own execution—advised on product-market fit positioning while consulting firm built the commercial motion.
