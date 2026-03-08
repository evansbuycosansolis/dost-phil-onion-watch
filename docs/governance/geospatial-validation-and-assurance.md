# Geospatial Validation and Assurance

Updated: 2026-03-08  
Primary owner: Governance owner  
Program signoff owner: Program owner

## 1. Purpose

This document defines the execution model for validating geospatial outputs, controls, and operational value before and after rollout. It is a pass/fail system, not a narrative reference.

## 2. Assurance scope

Validation covers:

- technical service correctness;
- data and lineage quality;
- review and field workflow quality;
- security and governance controls;
- outcome and program impact;
- independent assurance activities.

## 3. Assurance calendar (mandatory cadence)

| Cadence | Activity | Owner | Output artifact |
| --- | --- | --- | --- |
| Weekly | Ops quality review | Operations lead | Weekly validation notes |
| Monthly | Model and threshold review | Data quality lead | Model-threshold review memo |
| Monthly | Security and access review | Governance owner | Access and audit review record |
| Quarterly | DR drill and resilience test | Technical owner | DR drill report |
| Quarterly | Program health review | Program owner | Quarterly assurance summary |
| Semi-annual | Independent assurance bundle | Governance owner | External assurance report package |

## 4. Validation test matrix (pass/fail)

| Test ID | Layer | Test | Pass condition | Failure action |
| --- | --- | --- | --- | --- |
| VA-T01 | API | Geospatial route smoke tests | Critical routes return valid responses | Block rollout gate |
| VA-T02 | Worker | Scheduled jobs execute with retries | No critical job class stuck/failing | Open P1/P2 incident |
| VA-T03 | Data quality | Freshness and completeness checks | >= configured threshold coverage | Mark scope degraded |
| VA-T04 | Lineage | Run and artifact traceability | Input-output lineage available for sampled runs | Block publish |
| VA-T05 | Human workflow | Review and approval flow | SLA and mandatory fields satisfied | Retrain + corrective action |
| VA-T06 | Field workflow | Field verification closure quality | Evidence checklist completion >= target | Increase supervision |
| VA-T07 | Governance | RBAC and audit control tests | No unauthorized access, full audit coverage | Freeze privileged mutations |
| VA-T08 | Export safety | Signed package and redaction checks | 100% policy-compliant exports | Pause distribution |
| VA-T09 | KPI integrity | Metric reproducibility | KPI recompute matches published values | Invalidate report |
| VA-T10 | Drift | Source/model drift detection | Drift below approved limits | Trigger model/threshold review |

## 5. Launch gate requirements

A rollout gate may pass only if all are true:

- all required VA-T* tests are green;
- unresolved exceptions have approved compensating controls and expiry date;
- signoff is captured from technical, governance, and program owners.

Gate signoff template:

| Gate | Date | Technical owner | Governance owner | Program owner | Result | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Pre-launch |  |  |  |  | Pass/Fail |  |
| Pilot expansion |  |  |  |  | Pass/Fail |  |
| Province-wide |  |  |  |  | Pass/Fail |  |

## 6. Model and threshold assurance workflow

1. Capture baseline metrics for active model and thresholds.
2. Run candidate settings on validation sample.
3. Compare false positives, misses, and turnaround impact.
4. Approve only if quality and governance thresholds are met.
5. Record version, rationale, and rollback reference.

Required artifacts:

- validation sample manifest;
- before/after KPI comparison;
- risk impact note;
- approval decision and reviewer names.

## 7. Independent assurance plan

### A. External security review

- Frequency: semi-annual.
- Scope: auth, RBAC, export controls, audit integrity.
- Output: findings list with remediation deadlines.

### B. Independent data-quality audit

- Frequency: quarterly.
- Scope: source freshness, completeness, normalization fidelity.
- Output: quality score and nonconformance list.

### C. Model validation audit

- Frequency: quarterly.
- Scope: precision proxy, drift, threshold behavior, explainability.
- Output: model assurance memo and approval decision.

### D. Export and compliance review

- Frequency: quarterly.
- Scope: redaction, legal hold, retention policy execution.
- Output: compliance attestation and exception register.

### E. Field-process audit

- Frequency: quarterly.
- Scope: field verification process, evidence quality, sync correctness.
- Output: field operations conformance report.

## 8. Validation datasets and sampling

### Gold-label set requirements

- Minimum 100 cases per quarter.
- Coverage across municipalities and seasons.
- Evidence-backed label for each case.
- Immutable version tags.

### Production sampling requirements

- Weekly random sample of reviewed anomalies.
- Monthly stratified sample by AOI risk band.
- Sample includes low-confidence and high-impact cases.

## 9. Assurance evidence repository

Store all assurance artifacts in:

```text
docs/governance/records/geospatial-assurance/
  YYYY-MM/
    validation-matrix-results.csv
    model-threshold-review.md
    access-audit-review.md
    drift-summary.md
    exceptions.md
```

## 10. Validation report template

Use this for monthly and quarterly reports:

```text
Report period:
Prepared by:
Approved by:

1) Validation summary
2) Failed tests and root causes
3) Exceptions and expiration dates
4) Corrective actions with owner and due date
5) Recommendation: pass / conditional pass / fail
```

## 11. Known limitations register (must be maintained)

Track:

- source blind spots;
- seasonal anomalies and edge cases;
- unresolved workflow bottlenecks;
- governance exceptions;
- pending remediation actions.

Any limitation marked `high` must have an owner and deadline.

## 12. Roles and accountability

| Area | Primary owner | Backup owner |
| --- | --- | --- |
| Technical validation | Technical owner | Platform operations |
| Data quality validation | Data quality lead | Integration owner |
| Human workflow validation | Operations lead | Supervisor lead |
| Field validation | Field operations lead | Program owner |
| Governance assurance | Governance owner | Auditor |
| Program assurance summary | Program owner | Executive sponsor |
