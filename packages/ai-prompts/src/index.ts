export const alertNarrativePrompt = `
You are drafting a government operations alert summary.
Input: alert type, severity, scope metrics, and relevant contextual signals.
Output: concise operational narrative with neutral language and recommended actions.
`;

export const executiveSummaryPrompt = `
Draft an executive monthly onion supply chain summary for provincial leadership.
Include production, stock, prices, imports, forecast outlook, and major risks.
Use factual tone and clear action priorities.
`;

export const policySummaryPrompt = `
Summarize the provided policy/report text into:
1) key directives
2) operational implications
3) compliance checks for local implementers.
`;

export const anomalyExplanationPrompt = `
Explain the anomaly event in plain operational language.
Describe supporting metrics, confidence, and non-accusatory interpretation.
`;
