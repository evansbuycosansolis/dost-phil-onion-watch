# Geospatial KPI Scorecard

Updated: 2026-03-08  
Primary owner: Program owner  
Publishing owner: Operations lead  
Data owner: Technical owner + Governance owner

## 1. Purpose

This document defines a decision-grade KPI system for geospatial operations. It includes formulas, thresholds, data contracts, and reporting cadence so every score can be reproduced from system records.

## 2. KPI governance rules

- KPI definitions are versioned and changed only in monthly governance review.
- Every KPI result must map to at least one API output or SQL query.
- KPI reports are published weekly and monthly with named approvers.
- Red KPIs require an action ticket with owner and due date.

## 3. Scorecard publication schedule

| Report | Due date | Coverage window | Publisher | Required approvers |
| --- | --- | --- | --- | --- |
| Weekly scorecard | Every Monday 10:00 PHT | Previous Mon-Sun | Operations lead | Program owner |
| Monthly scorecard | 2nd business day of month | Previous calendar month | Operations lead | Program owner, Governance owner |
| Quarterly impact review | 5th business day after quarter close | Previous quarter | Program owner | Executive sponsor |

## 4. Core KPI formulas (mandatory)

| KPI ID | KPI | Formula | Null/edge handling | Target |
| --- | --- | --- | --- | --- |
| GEO-KPI-001 | Anomaly precision | `confirmed_anomalies / reviewed_anomalies` | If denominator = 0, mark `N/A` | >= 0.75 |
| GEO-KPI-002 | Review turnaround (hours) | `avg(review_started_at - anomaly_created_at)` | Exclude canceled records | <= 24h |
| GEO-KPI-003 | Field verification turnaround (hours) | `avg(field_closed_at - field_requested_at)` | Exclude deferred cases | <= 72h |
| GEO-KPI-004 | Intervention completion rate | `completed_interventions / approved_interventions` | If denominator = 0, `N/A` | >= 0.85 |
| GEO-KPI-005 | Report usage rate | `active_report_readers / targeted_recipients` | Use unique users per period | >= 0.60 |
| GEO-KPI-006 | Executive action follow-through | `completed_exec_actions / committed_exec_actions` | If denominator = 0, `N/A` | >= 0.80 |
| GEO-KPI-007 | Municipality adoption rate | `active_municipalities / onboarded_municipalities` | Based on approved rollout scope | >= 0.90 |
| GEO-KPI-008 | Run schedule compliance | `runs_completed_on_time / runs_scheduled` | Late runs count as failed | >= 0.95 |
| GEO-KPI-009 | Job success rate | `successful_jobs / total_jobs` | Include retries as same job id | >= 0.98 |
| GEO-KPI-010 | Audit completeness | `audited_controlled_actions / controlled_actions` | Missing audit event is failure | = 1.00 |

## 5. Data source mapping

| KPI ID | Primary API source | Primary table source | Owner |
| --- | --- | --- | --- |
| GEO-KPI-001 | `GET /api/v1/geospatial/dashboard/executive` | `anomaly_events`, `risk_scores` | Data quality lead |
| GEO-KPI-002 | `GET /api/v1/geospatial/dashboard/operations-center` | `anomaly_events`, `geospatial_aoi_notes` | Operations lead |
| GEO-KPI-003 | `GET /api/v1/geospatial/dashboard/operations-center` | `intervention_actions`, `source_submissions` | Field operations lead |
| GEO-KPI-004 | `GET /api/v1/geospatial/dashboard/executive` | `intervention_actions` | Operations lead |
| GEO-KPI-005 | `GET /api/v1/reports/{id}/deliveries` | `report_delivery_logs` | Reporting owner |
| GEO-KPI-006 | `GET /api/v1/geospatial/dashboard/executive/anomaly-brief/latest` | `approval_workflows`, `alerts` | Program owner |
| GEO-KPI-007 | `GET /api/v1/geospatial/dashboard/provincial` | `municipalities`, `source_submissions` | Program owner |
| GEO-KPI-008 | `GET /api/v1/geospatial/runs` | `satellite_pipeline_runs` | Technical owner |
| GEO-KPI-009 | `GET /api/v1/admin/jobs` | `job_runs` | Platform operations |
| GEO-KPI-010 | `GET /api/v1/audit/events` | `audit_logs` | Governance owner |

## 6. Traffic-light thresholds

| KPI ID | Green | Amber | Red |
| --- | --- | --- | --- |
| GEO-KPI-001 | >= 0.75 | 0.65 to 0.74 | < 0.65 |
| GEO-KPI-002 | <= 24h | 24h to 36h | > 36h |
| GEO-KPI-003 | <= 72h | 72h to 96h | > 96h |
| GEO-KPI-004 | >= 0.85 | 0.70 to 0.84 | < 0.70 |
| GEO-KPI-005 | >= 0.60 | 0.40 to 0.59 | < 0.40 |
| GEO-KPI-006 | >= 0.80 | 0.60 to 0.79 | < 0.60 |
| GEO-KPI-007 | >= 0.90 | 0.75 to 0.89 | < 0.75 |
| GEO-KPI-008 | >= 0.95 | 0.90 to 0.94 | < 0.90 |
| GEO-KPI-009 | >= 0.98 | 0.95 to 0.97 | < 0.95 |
| GEO-KPI-010 | 1.00 | 0.98 to 0.99 | < 0.98 |

## 7. Example extraction queries (PostgreSQL)

### GEO-KPI-009: job success rate

```sql
SELECT
  COUNT(*) FILTER (WHERE status = 'completed')::numeric
  / NULLIF(COUNT(*), 0) AS job_success_rate
FROM job_runs
WHERE started_at >= date_trunc('month', CURRENT_DATE);
```

### GEO-KPI-010: audit completeness sample

```sql
WITH controlled_actions AS (
  SELECT 'report.export.download' AS action_type
  UNION ALL SELECT 'geospatial.run.approval_gate'
  UNION ALL SELECT 'geospatial.run.manual_override'
),
events AS (
  SELECT action_type, COUNT(*) AS cnt
  FROM audit_logs
  WHERE created_at >= date_trunc('month', CURRENT_DATE)
  GROUP BY action_type
)
SELECT
  c.action_type,
  COALESCE(e.cnt, 0) AS audited_events
FROM controlled_actions c
LEFT JOIN events e ON e.action_type = c.action_type;
```

### GEO-KPI-008: run schedule compliance

```sql
SELECT
  COUNT(*) FILTER (WHERE status = 'completed')::numeric
  / NULLIF(COUNT(*), 0) AS run_completion_ratio
FROM satellite_pipeline_runs
WHERE started_at >= date_trunc('week', CURRENT_DATE);
```

## 8. Collection workflow

1. Pull API snapshots for dashboards and operations-center.
2. Run SQL validation checks for denominator and null handling.
3. Populate weekly or monthly scorecard CSV.
4. Validate sample metrics against API output.
5. Publish scorecard and file action tickets for red KPIs.

Artifact convention:

```text
docs/ops/records/geospatial-kpi/
  YYYY-MM-DD-weekly/
    scorecard.csv
    variance-notes.md
    actions.md
  YYYY-MM-monthly/
    scorecard.csv
    management-summary.md
```

## 9. Escalation policy for red KPIs

| Condition | Escalation deadline | Owner | Required output |
| --- | --- | --- | --- |
| 1 red KPI | 2 business days | KPI owner | Corrective action note |
| 2-3 red KPIs | 1 business day | Program owner | Mitigation plan + due dates |
| 4+ red KPIs or any governance KPI red | Same day | Governance owner + Executive sponsor | Incident-level review and freeze decision |

## 10. Segmentation requirements

All KPI reports should include segmentation by:

- municipality;
- AOI risk band;
- run type (`ingest`, `feature_refresh`);
- role cohort;
- rollout wave;
- model/threshold version where applicable.

## 11. Scorecard release checklist

- [ ] Coverage window and timezone are correct.
- [ ] Formula version matches this document.
- [ ] Denominator edge cases are explicitly marked.
- [ ] Red KPIs have linked actions and owners.
- [ ] Publisher and approver names are recorded.
- [ ] CSV and summary markdown are archived.

## 12. Approval block

Weekly report:

- Prepared by:
- Date:
- Approved by:

Monthly report:

- Prepared by:
- Date:
- Approved by Program owner:
- Approved by Governance owner:
