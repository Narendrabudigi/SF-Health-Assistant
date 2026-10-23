/** Resolve one display status for metric rows and every module's status totals. */
export function normalizeMetricStatus(status) {
  const value = String(status || '').toLowerCase().trim();

  if (/process[s_-]*gaps?/.test(value)) return 'Process Gaps';
  if (/^(?:n\s*\/\s*a|na)$/.test(value)) return 'Process Gaps';
  if (/not yet fetched|data not yet fetched|^--$|^pending$/.test(value)) return 'Not yet fetched';
  if (/critical|\bcrit\b/.test(value)) return 'Critical';
  if (/at[\s_-]*risk|\brisk\b|warn|breach/.test(value)) return 'At Risk';
  if (/\bhealthy\b|on[\s_-]*track|on target|\bgood\b/.test(value)) return 'Healthy';

  return 'Not yet fetched';
}
