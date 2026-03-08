# Geospatial Incident Runbook

Updated: 2026-03-08  
Primary owner: Support lead  
Escalation owner: Incident commander on duty

## 1. Purpose

This is the executable response runbook for geospatial incidents affecting:

- API availability and correctness;
- background jobs and queues;
- connectors and source freshness;
- report/export safety;
- RBAC and audit integrity;
- mobile/offline sync paths.

## 2. Severity matrix and SLOs

| Severity | Definition | Acknowledge SLO | Stakeholder update SLO | Recovery target |
| --- | --- | --- | --- | --- |
| P1 | Critical service or governance breach | <= 10 minutes | <= 20 minutes | <= 4 hours |
| P2 | Major degradation with workaround | <= 30 minutes | <= 60 minutes | <= 1 business day |
| P3 | Localized defect, low operational impact | <= 4 hours | <= 1 business day | <= 5 business days |

## 3. Response team roles

| Role | Minimum action |
| --- | --- |
| Incident commander | Own timeline, decisions, containment, and closure criteria |
| Technical lead | Diagnose API, DB, queue, scheduler, and connector internals |
| Operations lead | Assess analyst, field, and executive workflow impact |
| Governance lead | Evaluate access, audit, export, and compliance impact |
| Communications lead | Send status updates and closure note |

## 4. First 15-minute checklist

- [ ] Create incident record with UTC timestamp.
- [ ] Classify incident severity.
- [ ] Assign incident commander and technical lead.
- [ ] Record current blast radius (routes, roles, municipalities, AOIs).
- [ ] Freeze risky workflows if governance/security may be affected.
- [ ] Capture first evidence set (health, metrics, jobs, traces).

## 5. Command center quick commands

Set environment:

```powershell
$env:API_BASE = "http://localhost:8000"
$body = @{ email = "super_admin@onionwatch.ph"; password = "ChangeMe123!" } | ConvertTo-Json
$login = Invoke-RestMethod -Method Post -Uri "$env:API_BASE/api/v1/auth/login" -Body $body -ContentType "application/json"
$token = $login.access_token
$headers = @{ Authorization = "Bearer $token" }
```

Health and platform checks:

```powershell
Invoke-RestMethod "$env:API_BASE/health"
Invoke-WebRequest "$env:API_BASE/metrics" -UseBasicParsing | Select-Object -ExpandProperty StatusCode
Invoke-RestMethod "$env:API_BASE/api/v1/admin/jobs?limit=50" -Headers $headers
Invoke-RestMethod "$env:API_BASE/api/v1/admin/observability/overview" -Headers $headers
Invoke-RestMethod "$env:API_BASE/api/v1/geospatial/dashboard/operations-center" -Headers $headers
Invoke-RestMethod "$env:API_BASE/api/v1/reports/distribution/deliveries?status=failed&limit=50" -Headers $headers
```

Geospatial run checks:

```powershell
Invoke-RestMethod "$env:API_BASE/api/v1/geospatial/runs?limit=20" -Headers $headers
Invoke-RestMethod "$env:API_BASE/api/v1/geospatial/dashboard/config-health" -Headers $headers
Invoke-RestMethod "$env:API_BASE/api/v1/geospatial/dashboard/self-test" -Headers $headers
```

## 6. Standard containment actions

Use only approved controls:

- pause distribution processing;
- pause connector ingestion;
- reduce rollout scope to unaffected municipalities;
- block high-risk export endpoints;
- revert threshold/model/config version;
- move affected views to read-only degraded mode.

All containment actions must create an incident log entry with:

- actor;
- timestamp;
- reason;
- expected rollback condition.

## 7. Incident playbooks by scenario

### Scenario A: Geospatial API degraded or down

1. Run `/health`, `/metrics`, and observability overview.
2. Check recent deploy, migration, and config deltas.
3. Limit high-cost requests and run smoke checks.
4. Recover service, then validate key geospatial routes.

### Scenario B: Worker backlog or stuck jobs

1. Inspect `admin/jobs` and failed delivery logs.
2. Confirm worker process status.
3. Pause non-critical schedules and clear bottleneck class.
4. Re-run queue processing once stable.

### Scenario C: Connector outage or stale source

1. Confirm affected connector and municipality scope.
2. Mark related outputs as degraded.
3. Use approved fallback source path if available.
4. Document data-quality exception with expiration date.

### Scenario D: Export/report safety incident

1. Stop report delivery queue immediately.
2. Preserve distributed artifacts and recipient logs.
3. Notify governance owner for compliance review.
4. Reissue corrected artifacts after explicit approval.

### Scenario E: RBAC or audit integrity issue

1. Treat as P1.
2. Disable affected privileged routes.
3. Capture auth/audit evidence for impacted window.
4. Execute security review before restoring write paths.

## 8. Required evidence pack

Store in:

```text
docs/ops/records/geospatial-incidents/INC-YYYYMMDD-XXX/
  timeline.md
  health-and-metrics.txt
  api-samples.json
  job-snapshots.json
  audit-samples.json
  comms-log.md
  corrective-actions.md
```

Minimum mandatory evidence:

- first detected time and source;
- correlation IDs and run IDs;
- failed job IDs;
- impacted municipalities/AOIs;
- comms timeline;
- closure validation proof.

## 9. Communications templates

### Initial update (send within SLO)

```text
Incident: <ID>
Severity: <P1/P2/P3>
Started: <UTC timestamp>
Scope: <routes/workflows/regions>
Current impact: <user and business effect>
Containment in progress: <yes/no + action>
Next update: <timestamp>
```

### Governance/security update

```text
Incident: <ID>
Control impact: <access/audit/export/data handling>
Potential exposure: <none/suspected/confirmed>
Containment actions: <list>
Approvals needed: <list>
```

### Resolution update

```text
Incident: <ID>
Root cause: <short summary>
Fix: <applied change>
Validation: <checks passed>
Residual risk: <none/list>
Follow-ups: <ticket IDs + owners + due dates>
```

## 10. Recovery validation checklist

- [ ] `/health` stable and no new degraded spikes.
- [ ] geospatial dashboard endpoints respond correctly.
- [ ] run queue and report distribution are back within SLA.
- [ ] affected exports regenerated and validated.
- [ ] audit events present for containment and recovery actions.
- [ ] stakeholder closure notice sent.

## 11. Post-incident review (required within 3 business days for P1/P2)

Required fields:

- incident summary;
- precise timeline;
- technical root cause;
- control impact assessment;
- what failed in detection/prevention;
- corrective actions with owner and due date;
- prevention controls and verification date.

## 12. Drill cadence

- Monthly: one tabletop incident drill.
- Quarterly: one live recovery simulation.
- Quarterly: one governance breach simulation (audit/export/access).

A drill is complete only when:

- evidence pack is archived;
- action items are assigned;
- runbook improvements are applied.
