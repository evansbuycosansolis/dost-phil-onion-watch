export const rolloutTemplateCriteria = {
  gate_a_data_sources_connected: false,
  gate_b_quality_passed: false,
  gate_c_training_complete: false,
  gate_d_governance_signed_off: false,
  gate_e_ops_readiness: false,
};

export const kpiTemplateMetrics = {
  "GEO-KPI-001": 0.0,
  "GEO-KPI-002": 0.0,
  "GEO-KPI-003": 0.0,
  "GEO-KPI-004": 0.0,
  "GEO-KPI-005": 0.0,
  "GEO-KPI-006": 0.0,
  "GEO-KPI-007": 0.0,
  "GEO-KPI-008": 0.0,
  "GEO-KPI-009": 0.0,
  "GEO-KPI-010": 0.0,
};

export const incidentTemplate = {
  summary: "Geospatial incident requiring rapid triage and mitigation.",
  impact: "Potential degradation in anomaly detection and reporting confidence.",
  root_cause: "",
  corrective_actions: [{ owner: "operations", action: "Investigate and mitigate", due: "" }],
  evidence_pack: { links: [], notes: "Attach links to logs, screenshots, and reports." },
};

export const riskTemplate = {
  title: "Operational geospatial risk",
  description: "Describe the risk and potential impact on geospatial program outcomes.",
  trigger: "Early warning trigger condition",
  mitigation: "Primary mitigation plan",
  board_notes: "Board review notes",
  metadata: { playbook_template: "RISK_BOARD_TEMPLATE" },
};

export const validationEvidenceTemplate = {
  report_summary: "Validation run evidence package",
  links: [],
};

export function parseJsonInput(value: string, fallback: Record<string, unknown> | unknown[] = {}) {
  const trimmed = value.trim();
  if (!trimmed) {
    return fallback;
  }
  return JSON.parse(trimmed);
}

export function toPrettyJson(value: unknown) {
  return JSON.stringify(value ?? {}, null, 2);
}
