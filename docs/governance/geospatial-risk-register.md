# Geospatial Risk Register

Updated: 2026-03-08  
Primary owner: Governance owner  
Reporting owner: Program owner

## 1. Purpose

This register is the live control system for geospatial program risk. Every active risk must have:

- quantified score;
- trigger signal;
- named owner;
- mitigation plan with due date;
- current status;
- next review date.

## 2. Scoring model

Likelihood scale:

- 1 = rare
- 2 = unlikely
- 3 = possible
- 4 = likely
- 5 = very likely

Impact scale:

- 1 = low
- 2 = moderate
- 3 = material
- 4 = high
- 5 = severe

Priority score formula:

`priority = likelihood * impact`

Priority bands:

- 1-5 `Low`
- 6-10 `Medium`
- 11-15 `High`
- 16-25 `Critical`

## 3. Active risk register (operational table)

| ID | Risk | Category | L | I | Score | Status | Trigger | Mitigation owner | Next review | Target close |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GEO-R01 | Stale source data causes misleading anomalies | Data quality | 4 | 5 | 20 | Mitigating | freshness compliance < 95% for 2 days | Data quality lead | 2026-03-15 | 2026-04-15 |
| GEO-R02 | Unauthorized access to sensitive AOI/exports | Security/governance | 3 | 5 | 15 | Monitoring | failed RBAC control test or suspicious auth event | Governance owner | 2026-03-15 | 2026-04-30 |
| GEO-R03 | Missing audit records for privileged actions | Governance | 3 | 5 | 15 | Monitoring | audit completeness < 100% for controlled actions | Governance owner | 2026-03-15 | 2026-04-15 |
| GEO-R04 | Connector outage creates monitoring blind spots | Integration/operations | 4 | 4 | 16 | Mitigating | connector failures > threshold for 2 cycles | Technical owner | 2026-03-12 | 2026-04-10 |
| GEO-R05 | Review queue exceeds analyst capacity | Operations | 4 | 4 | 16 | Mitigating | backlog beyond SLA for 2 consecutive days | Operations lead | 2026-03-12 | 2026-03-31 |
| GEO-R06 | Slow field verification reduces trust | Field operations | 3 | 4 | 12 | Monitoring | field turnaround > 72h median | Field operations lead | 2026-03-19 | 2026-04-30 |
| GEO-R07 | Model/threshold drift increases false positives/misses | Model governance | 4 | 4 | 16 | Mitigating | anomaly precision below threshold for 2 weeks | Program owner | 2026-03-19 | 2026-04-20 |
| GEO-R08 | Unsafe report/export distribution | Reporting/governance | 3 | 5 | 15 | Monitoring | export policy violation or failed signing check | Reporting owner | 2026-03-15 | 2026-04-30 |
| GEO-R09 | Infra degradation causes repeat run failures | Platform reliability | 3 | 4 | 12 | Monitoring | job success rate < 95% weekly | Technical owner | 2026-03-12 | 2026-04-30 |
| GEO-R10 | Offline sync conflicts create duplicate evidence | Mobile/offline | 3 | 4 | 12 | Monitoring | sync conflict rate > 5% weekly | Field operations lead | 2026-03-19 | 2026-05-15 |
| GEO-R11 | Low adoption limits operational impact | Adoption/change | 4 | 4 | 16 | Mitigating | municipality adoption rate < 75% | Program owner | 2026-03-26 | 2026-05-31 |
| GEO-R12 | Expansion starts without readiness evidence | Rollout/governance | 3 | 4 | 12 | Monitoring | gate signoff incomplete but rollout request raised | Program owner | 2026-03-26 | 2026-04-30 |
| GEO-R13 | Single-person dependency in key workflows | Staffing/sustainability | 3 | 4 | 12 | Open | no backup owner for critical process | Program owner | 2026-03-26 | 2026-05-15 |
| GEO-R14 | Retention or legal-hold controls fail | Compliance | 2 | 5 | 10 | Monitoring | failed quarterly control test | Governance owner | 2026-04-01 | 2026-06-15 |
| GEO-R15 | KPI comparability breaks after model changes | Program measurement | 3 | 3 | 9 | Monitoring | KPI definition change without baseline versioning | Program owner | 2026-03-26 | 2026-05-01 |

Status values:

- `Open`
- `Monitoring`
- `Mitigating`
- `Accepted exception`
- `Closed`

## 4. Escalation rules

| Condition | Required escalation |
| --- | --- |
| Any `Critical` risk | Same-day review with program owner and governance owner |
| `High` risk unresolved for > 14 days | Escalate to executive sponsor |
| New governance/security risk with score >= 12 | Trigger incident process and freeze sensitive changes |
| Risk marked `Accepted exception` | Must include approver, expiry date, compensating controls |

## 5. Risk board cadence

Weekly risk board (30 minutes):

1. New risks since last review.
2. Trigger events and score changes.
3. Overdue mitigations.
4. Risks requiring escalation.

Monthly governance board (60 minutes):

1. High/Critical risk trend.
2. Exception approvals/expirations.
3. Rollout risk readiness for next wave.
4. Closure approvals.

## 6. Risk update workflow

1. Identify risk and assign ID (`GEO-RXX`).
2. Score likelihood and impact.
3. Define trigger and mitigation owner.
4. Set next review and target close dates.
5. Record evidence and status transitions.
6. Close only after control verification.

## 7. Required fields per risk entry

Each risk must include:

- ID and short title;
- category;
- likelihood and impact;
- score and band;
- status;
- trigger condition;
- mitigation plan summary;
- owner and backup owner;
- next review date;
- target close date;
- evidence links.

## 8. Evidence and archive structure

```text
docs/governance/records/geospatial-risk/
  YYYY-MM/
    risk-board-notes.md
    risk-snapshot.csv
    exceptions.md
    closures.md
```

For a closed risk, include:

- closure date;
- residual risk note;
- control verification evidence;
- approver name.

## 9. Current focus risks (next 30 days)

- GEO-R01 source freshness and completeness.
- GEO-R04 connector reliability stabilization.
- GEO-R05 review queue capacity and staffing.
- GEO-R07 drift management and threshold governance.
- GEO-R11 municipality adoption during expansion.
