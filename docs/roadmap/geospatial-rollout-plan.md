# Geospatial Rollout Plan

Updated: 2026-03-08  
Primary owner: Program owner  
Supporting owners: Technical owner, Governance owner, Operations lead

Related documents:

- `docs/roadmap/geospatial-feature-backlog.md`
- `docs/roadmap/geospatial-kpi-scorecard.md`
- `docs/ops/geospatial-incident-runbook.md`
- `docs/governance/geospatial-validation-and-assurance.md`
- `docs/governance/geospatial-risk-register.md`

## 1. Purpose

This plan is the operational launch playbook for geospatial surveillance capabilities in Phil Onion Watch. It defines:

- phased rollout sequence;
- gate checks and signoff requirements;
- evidence and audit artifacts per wave;
- rollback triggers and recovery actions;
- transition criteria from supervised rollout to steady-state.

## 2. Operating assumptions

- Access is fail-closed for all geospatial and export routes.
- Rollout happens by wave, never by full-scope cutover.
- A wave is not complete until KPI, governance, and incident checks are signed.
- Exceptions are time-bound and logged in the risk register.

## 3. Rollout control board (who approves what)

| Area | Decision owner | Required co-signers | Approval artifact |
| --- | --- | --- | --- |
| Launch go/no-go | Program owner | Technical owner, Governance owner | Go/No-Go memo |
| Security and access | Governance owner | Technical owner | Access validation report |
| Data readiness | Data quality lead | Operations lead | Data readiness checklist |
| Ops staffing readiness | Operations lead | Program owner | Staffing and on-call roster |
| Rollback invocation | Incident commander | Program owner, Governance owner (if policy impact) | Incident command log |

## 4. Wave tracker (live table)

| Wave | Scope | Planned start | Planned end | Actual start | Actual end | Status | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- |
| W0 | Pre-launch readiness | 2026-03-10 | 2026-03-16 |  |  | Planned |  |
| W1 | Pilot (2 municipalities) | 2026-03-17 | 2026-03-31 |  |  | Planned |  |
| W2 | Controlled expansion | 2026-04-01 | 2026-04-30 |  |  | Planned |  |
| W3 | Province-wide | 2026-05-01 | 2026-05-31 |  |  | Planned |  |

Status values:

- `Planned`
- `In progress`
- `Blocked`
- `Completed`
- `Rolled back`

## 5. Readiness gates and mandatory evidence

### Gate A: Technical readiness

Checks:

- [ ] `/health` is `ok` or accepted `degraded` with mitigation
- [ ] `/metrics` reachable
- [ ] Scheduler runs and retry settings validated
- [ ] Geospatial operations-center endpoint returns data
- [ ] Report distribution queue process is healthy

Evidence commands:

```powershell
$env:API_BASE = "http://localhost:8000"
Invoke-RestMethod "$env:API_BASE/health"
Invoke-WebRequest "$env:API_BASE/metrics" -UseBasicParsing | Select-Object -ExpandProperty StatusCode
python scripts/run_worker.py
```

Signoff:

- Technical owner:
- Date:
- Notes:

### Gate B: Data readiness

Checks:

- [ ] AOI boundaries validated for pilot municipalities
- [ ] Source freshness and completeness in threshold
- [ ] Known source gaps documented with mitigations
- [ ] Baseline run reproducibility checks pass

Evidence commands:

```powershell
# After obtaining token
Invoke-RestMethod "$env:API_BASE/api/v1/geospatial/aois"
Invoke-RestMethod "$env:API_BASE/api/v1/geospatial/dashboard/operations-center" -Headers @{Authorization="Bearer $token"}
Invoke-RestMethod "$env:API_BASE/api/v1/geospatial/dashboard/config-health" -Headers @{Authorization="Bearer $token"}
```

Signoff:

- Data quality lead:
- Date:
- Notes:

### Gate C: Governance readiness

Checks:

- [ ] RBAC smoke checks pass across privileged and non-privileged roles
- [ ] Audit events created for key mutation routes
- [ ] Export restrictions and signed package validation tested
- [ ] Legal hold and retention controls reviewed

Evidence commands:

```powershell
Invoke-RestMethod "$env:API_BASE/api/v1/audit/events?limit=50" -Headers @{Authorization="Bearer $token"}
Invoke-RestMethod "$env:API_BASE/api/v1/reports/distribution/deliveries?limit=25" -Headers @{Authorization="Bearer $token"}
```

Signoff:

- Governance owner:
- Date:
- Notes:

### Gate D: Operational readiness

Checks:

- [ ] Weekly ops review calendar invites accepted
- [ ] Incident commander and on-call rota confirmed
- [ ] Analyst and supervisor SOP signoff complete
- [ ] Field verification staffing assigned for pilot AOIs

Signoff:

- Operations lead:
- Date:
- Notes:

## 6. Phase sequence (execution model)

### Phase 0: Pre-launch readiness

Entry criteria:

- All Gate A-D checks are complete.

Required actions:

- Freeze config and threshold changes except P1 incident fixes.
- Capture baseline KPI snapshot (see scorecard doc).
- Run smoke E2E for seeded roles and core geospatial workflows.

Exit criteria:

- Signed go/no-go memo archived.

### Phase 1: Supervised pilot

Scope:

- Limited AOIs and municipalities only.

Required actions:

- Daily triage of anomaly queue and false-positive review.
- Daily review of report delivery logs.
- Incident summary update at end of each day.

Exit criteria:

- No unresolved critical risk items blocking expansion.
- KPI thresholds meet pilot minimums for 2 consecutive weeks.

### Phase 2: Controlled expansion

Required actions:

- Expand municipality coverage in approved batches.
- Enforce threshold/config changes through approval workflow only.
- Validate queue saturation and worker capacity.

Exit criteria:

- Stable KPI and incident profile across expanded scope.

### Phase 3: Province-wide operation

Required actions:

- Transition from supervised daily review to weekly operational cadence.
- Maintain monthly governance and model-threshold reviews.

Exit criteria:

- Accepted by program review board for steady-state.

## 7. Go-live checklist (must be attached to memo)

- [ ] Migration hash and deploy artifact recorded
- [ ] Worker scheduler running with expected cron entries
- [ ] Current threshold version and model versions documented
- [ ] Distribution recipient groups reviewed
- [ ] Rollback package tested in non-production
- [ ] Communications sent to rollout cohort
- [ ] KPI baseline snapshot exported and archived

## 8. Rollback criteria and action matrix

| Trigger | Severity | Immediate action | Follow-up |
| --- | --- | --- | --- |
| Access-control failure | Critical | Disable affected privileged workflow | Audit review and role map validation |
| Audit trail gaps | Critical | Pause privileged mutations | Incident RCA and control patch |
| Connector blind spot | High | Mark outputs degraded and pause dependent exports | Source fallback or scope reduction |
| Queue saturation > SLA for 2 cycles | High | Pause non-critical jobs, prioritize review queue | Capacity tune and staffing adjustment |
| Export policy breach | Critical | Stop distribution, revoke affected artifact | Governance notification and compliance review |
| Anomaly precision collapse | High | Roll back threshold/model set | Run validation set and retune |

## 9. Required artifact structure

Store rollout evidence in:

```text
docs/ops/records/geospatial-rollout/
  YYYY-MM-DD-wave-WX/
    01-readiness-checklist.md
    02-kpi-baseline.csv
    03-go-no-go-memo.md
    04-incident-summary.md
    05-retro-actions.md
```

Required naming convention:

- Prefix with two-digit order for deterministic review.
- Include date in `YYYY-MM-DD` format.
- Include wave code in folder name.

## 10. Meeting templates

### Weekly ops review agenda (45 minutes)

1. KPI status since last review.
2. Incident summary and unresolved actions.
3. Queue backlog and staffing pressure.
4. Risk register updates.
5. Go/no-go decisions for scope expansion.

### Wave closure retro template

| Item | Notes |
| --- | --- |
| What worked |  |
| What did not work |  |
| Top 3 blockers |  |
| Corrective actions |  |
| Owner and due date |  |
| Decision for next wave |  |

## 11. Authentication quickstart for rollout checks

Use seeded admin account:

- Email: `super_admin@onionwatch.ph`
- Password: `ChangeMe123!`

Token request:

```powershell
$body = @{ email = "super_admin@onionwatch.ph"; password = "ChangeMe123!" } | ConvertTo-Json
$login = Invoke-RestMethod -Method Post -Uri "$env:API_BASE/api/v1/auth/login" -ContentType "application/json" -Body $body
$token = $login.access_token
```

## 12. Exit to steady-state definition of done

A rollout is considered complete only when all conditions are true:

- wave tracker status is `Completed`;
- no open critical risks in risk register;
- no unresolved P1 incidents tied to geospatial workflows;
- KPI scorecard is green/amber within approved tolerance;
- governance owner signs monthly access and audit review;
- program owner signs wave closure memo.
