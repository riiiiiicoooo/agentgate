# AgentGate — Incident Runbooks

**Last Updated:** March 2026
**Severity Levels:** P0 (credential exposed externally), P1 (policy bypass / SLO breach), P2 (degraded performance)

---

## Incident Runbook 1: Credential Exposure (Plaintext Secret Leaked to Logs or External System)

**Likelihood:** Low (goal is zero; historical baseline was 4-6/month before AgentGate)
**Severity:** P0 (immediate customer notification required)
**Detection Symptoms:** Secret scanning alert, customer report, or external security researcher finding

### Detection

**Automated triggers:**
- Code commit blocked by pre-commit hook (detected plaintext API key)
- CloudWatch log scan finds plaintext AWS key format: `AKIA[0-9A-Z]{16}`
- S3 bucket scan detects unencrypted secret in backup
- External party reports: "We found your API key in a GitHub issue"

**Manual triggers:**
- Customer: "One of our developers accidentally pasted a token in an error report"
- Security team: "Attacker used leaked token to access customer data"

### Diagnosis (First 15 minutes)

1. **Confirm exposure scope:**
   ```bash
   # Search application logs
   grep -r "AKIA" /var/log/agentgate/ | head -20

   # Search database logs
   aws logs filter-log-events \
     --log-group-name /aws/rds/instance/agentgate-primary \
     --filter-pattern "[A-Z0-9]{20,}" \
     --start-time $(date -d '24 hours ago' +%s)000
   ```

2. **Determine what was exposed:**
   - Which credential? (Stripe API key, AWS access key, database password, etc.)
   - How long was it exposed? (When first leaked? When discovered?)
   - Who had access? (Just logs? External system? Public internet?)
   - Which customer(s) affected?

3. **Check if credential was used maliciously:**
   ```bash
   # If AWS key: Check CloudTrail for usage
   aws cloudtrail lookup-events --lookup-attributes AttributeKey=AccessKeyId,AttributeValue=AKIA... \
     --start-time 2024-01-15T00:00:00Z

   # If database password: Check audit logs for unauthorized access
   SELECT * FROM audit_logs WHERE connection_user = 'exposed_password_user'
     AND created_at > NOW() - INTERVAL '7 days';
   ```

4. **Scope the blast radius:**
   - What can this credential access? (Production database? Payment processor? All customer data?)
   - Did attacker use it? (Check CloudTrail / audit logs)
   - Are other secrets also exposed in the same location? (Check for patterns)

### Remediation (First 1 hour)

**Immediate (within 5 min):**
1. **Rotate the credential:**
   ```bash
   # Example: AWS access key rotation
   aws iam create-access-key --user-name agentgate-service
   # Result: get new access key pair

   # Update application secret store
   aws secretsmanager update-secret --secret-id agentgate/aws-creds \
     --secret-string '{"access_key": "NEW_KEY", "secret_key": "NEW_SECRET"}'

   # Delete old access key
   aws iam delete-access-key --user-name agentgate-service --access-key-id AKIA...OLD
   ```

2. **Contain the blast:**
   - If database password: Kill all active connections from old password user
   - If API key: Revoke API key from provider (Stripe, AWS, etc.)
   - If encryption key: Re-encrypt all data encrypted with old key

3. **Purge exposed credential:**
   - Delete from logs: `aws logs delete-log-group --log-group-name /aws/rds/instance/agentgate-primary` (only if very fresh)
   - Delete from backups: If found in S3 backup, mark backup as destroyed for compliance
   - Database: If in database column, update to NULL or redact

**Within 1 hour:**
1. **Determine exposure timeline:**
   - When was credential first logged/exposed?
   - When was it discovered?
   - How long was it accessible to attackers?

2. **Assess customer impact:**
   - Which customer's credentials were affected?
   - If attacker used it: Which customer data was accessed?
   - Generate list of potentially-compromised records

3. **Notify customer:**
   - What credential was exposed
   - When it was discovered
   - What was accessed
   - What we did to prevent recurrence

### Investigation (First 24 hours)

1. **Root cause:**
   - Why was the credential logged? (error message included full secret? debug logging left on?)
   - Why wasn't pre-commit hook / log scanning catching it?
   - Was this a code path we test? Or an edge case?

2. **Prevention:**
   - Deploy code fix to prevent logging this credential type
   - Add pre-commit hook for this pattern
   - Add integration test: "Verify no credentials in error logs"

3. **Regulatory check:**
   - Was this a HIPAA PHI credential? → Regulatory notification may be required
   - Was this customer data exposed via the credential? → Breach notification may be required
   - If yes → Notify legal/compliance within 2 hours

### Communication Template

**Internal (Slack #incident-ops):**
```
🚨 P0: Credential Exposure — [CREDENTIAL_TYPE]

Timeline:
- [TIME 1]: Credential logged to [LOCATION: app logs / S3 / error message]
- [TIME 2]: Issue discovered by [DETECTOR]
- [TIME 3]: Credential rotated

Scope:
- Credential type: [e.g., AWS access key, Stripe API key]
- Duration exposed: [TIME_PERIOD]
- Access: [Public internet / Logs only / Customer-visible error]
- Blast radius: [Customer A, B; affects X data]

Actions taken:
- [x] Credential rotated
- [x] Malicious usage checked (CloudTrail / audit logs)
- [ ] Root cause fix deployed
- [ ] Customer notification sent
- [ ] Regulatory notification [if needed]

Regulatory impact: [ASSESS NOW]
```

**Customer notification (Email):**
```
Subject: Security Incident Notification — AgentGate

Dear [CUSTOMER],

We are writing to inform you of a security incident affecting your AgentGate account.

On [DATE], we discovered that a [CREDENTIAL_TYPE] was inadvertently logged in our
application error logs. We immediately:
- Rotated the exposed credential
- Verified that the credential was not used to access customer data
- Fixed the code path to prevent this in the future

What you should do:
- No action required on your part; we have secured the credential
- Monitor your account for any unusual activity
- Contact us if you have questions: security@agentgate.io

We regret this incident and have enhanced our credential protection measures.
```

---

## Incident Runbook 2: Policy Evaluation Bypass (Agent Accesses Secret They Shouldn't)

**Likelihood:** Low (goal is zero; would indicate product defect)
**Severity:** P0 (security model failure)
**Detection Symptoms:** Audit log shows policy DENY but agent got secret anyway; or manual report: "Agent got production database password despite deny policy"

### Detection

**Automated triggers:**
- Audit log anomaly: `policy_decision = 'DENY'` but `secret_delivered = true` for same request (indicates bypass)
- Security test: Automated adversarial test agent tries to access forbidden secret; succeeds when should fail

**Manual triggers:**
- Customer report: "We have a policy that should deny access to secret X for agent Y, but the agent got the secret anyway"
- Compliance review: Auditor tries to bypass policy; succeeds

### Diagnosis (First 30 minutes)

1. **Confirm bypass occurred:**
   ```sql
   SELECT * FROM audit_logs
   WHERE policy_decision = 'DENY'
   AND secret_delivered = true
   AND created_at > NOW() - INTERVAL '7 days'
   ORDER BY created_at DESC;
   ```
   If result is non-empty, bypass confirmed.

2. **Determine scope of bypass:**
   - How many agents affected?
   - How many secrets were accessed via bypass?
   - How long has this been happening?

3. **Identify root cause (likely scenarios):**
   - **Code path bug:** Policy evaluation code has conditional that's wrong (e.g., `if policy.allow OR policy.admin` instead of `if policy.allow AND policy.admin`)
   - **Caching issue:** Stale policy in cache; new deny policy not picked up
   - **Logic error:** Policy evaluation skipped for certain secret types
   - **Race condition:** Policy updated mid-request; old version used

4. **Check code:**
   ```python
   # Example: bug pattern to look for
   if policy.allow:  # BUG: Should be "if policy.allow AND policy.owner == agent"
       return SECRET
   return DENY
   ```

### Remediation (First 2 hours)

**Immediate:**
1. **Revoke access:** Any secret that was bypassed, rotate immediately
2. **Block bypass:** If code path is identified, add emergency guard:
   ```python
   if policy_decision == 'DENY' and agent.has_secret_access:
       ALERT("Policy bypass detected")
       force_deny()
   ```

3. **Determine damage:**
   - Which secrets were accessed via bypass?
   - Were they used? (Check access logs on those systems)
   - Which customer's data was exposed?

**Within 2 hours:**
1. **Fix the bug:**
   - Find exact code location of bypass
   - Write failing test case: "Verify agent with DENY policy gets nothing"
   - Deploy fix
   - Verify with manual test: Try to bypass again; should fail

2. **Prevent recurrence:**
   - Add regression test to CI
   - Add security test to automated suite
   - Code review policy for similar patterns

3. **Audit trail review:**
   - Generate report: All secrets accessed via bypass
   - Cross-reference against customer data
   - Determine if customer notification required

### Communication Template

**Internal (Slack #incident-ops):**
```
🚨 P0: Policy Evaluation Bypass

Timeline:
- [TIME]: Bypass first detected by [METHOD]
- [TIME]: Root cause identified (code path bug / cache issue / etc.)
- [TIME]: Fix deployed and verified

Impact:
- Affected agents: [N]
- Secrets accessed via bypass: [LIST]
- Customer(s) affected: [LIST]
- Estimated harm: [ASSESS NOW]

Actions:
- [x] Bypass guarded (emergency code deployed)
- [x] Bug fixed and deployed
- [ ] Root cause analysis complete
- [ ] Customer notification [if needed]
- [ ] Security test added to CI

Next: Audit review and customer notification at [TIME]
```

---

## Incident Runbook 3: Audit Log Loss or Integrity Failure

**Likelihood:** Very low (goal is 99.99%)
**Severity:** P1 (compliance violation, not customer harm but legal exposure)
**Detection Symptoms:** Audit log gap (no entries for 1+ hour); or S3 Object Lock validation fails

### Detection

**Automated triggers:**
- `audit-log-health-check` job finds gap: No audit entries in database for >1 hour
- S3 Object Lock validation: Audit log objects should be immutable; validation finds they can be deleted
- CloudWatch alarm: Audit log ingestion rate drops to zero

**Manual triggers:**
- Compliance officer: "I'm trying to review activity from [TIME] but there are no audit logs"
- Security team: "S3 object for audit logs was deleted" (should be immutable)

### Diagnosis (First 30 minutes)

1. **Verify logging is working now:**
   ```sql
   SELECT COUNT(*), MAX(created_at) FROM audit_logs
   WHERE created_at > NOW() - INTERVAL '5 minutes';
   ```
   If count is normal, logging resumed; issue is historical.

2. **Identify the gap:**
   ```sql
   SELECT
     DATE_TRUNC('hour', created_at) as hour,
     COUNT(*) as entry_count
   FROM audit_logs
   WHERE created_at > NOW() - INTERVAL '7 days'
   GROUP BY DATE_TRUNC('hour', created_at)
   ORDER BY hour DESC;
   ```
   Look for hours with 0 or very low counts.

3. **Check S3 Object Lock:**
   ```bash
   aws s3api get-object-lock-configuration \
     --bucket agentgate-audit-logs \
     --key audit-2026-03-15.json.gz

   # Should show: "ObjectLockConfiguration": {"Enabled": "Enabled"}
   # If not, Object Lock is disabled
   ```

4. **Determine root cause:**
   - Is audit logging service running? (Check `kubectl get pods`)
   - Is S3 write succeeding? (Check CloudWatch logs for `audit-log-archiver`)
   - Is database still running? (Check RDS status)
   - Was data deleted? (Check CloudTrail for S3 DELETE operations)

### Remediation (First 2 hours)

1. **Restore audit logging:**
   - If service is down: `kubectl restart deployment/audit-log-processor`
   - If S3 write failing: Check credentials, retry
   - If database down: Restore from backup

2. **Verify S3 Object Lock:**
   ```bash
   aws s3api get-object-retention \
     --bucket agentgate-audit-logs \
     --key audit-2026-03-15.json.gz
   ```
   Should show GOVERNANCE or COMPLIANCE mode retention. If missing, apply it.

3. **Attempt recovery:**
   - Check PostgreSQL WAL (write-ahead log) for lost audit entries
   - If found, replay to recover entries:
     ```bash
     pg_wal_archive=$(find /var/lib/postgresql/pg_wal -name "*.backup" -newer ...)
     pg_dump --wal-method=stream > recover.sql
     ```

4. **Notify compliance:**
   - Scope of loss: How many hours? How many events?
   - Can it be recovered? (WAL available, etc.)
   - Regulatory notification required? (Audit logs required by SOC 2)

### Communication Template

**Internal (Slack #incident-ops):**
```
🚨 P1: Audit Log Loss — Gap from [TIME] to [TIME]

Scope:
- Hours lost: [N]
- Estimated events: ~[N*100-1000]
- Recovery status: Attempting recovery from WAL / Recovered from backup / Unrecoverable

Root cause:
- [ ] Service crashed
- [ ] Database unavailable
- [ ] S3 write failed
- [ ] Manual deletion (security incident)

Actions:
- [x] Logging resumed
- [ ] WAL recovery attempted
- [ ] S3 Object Lock verified
- [ ] Regulatory notification assessment

Regulatory impact: [ASSESS NOW]
```

