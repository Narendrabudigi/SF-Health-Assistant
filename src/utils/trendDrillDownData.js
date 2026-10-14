const VALUE_KEYS = ['average', 'value', 'actual', 'actualValue', 'metricValue', 'score', 'result', 'amount'];
const CONTAINER_KEYS = ['periods', 'points', 'data', 'values', 'yearly', 'annual', 'years', 'quarterly', 'quarters', 'monthly', 'months'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function numeric(value) {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value !== 'string') return null;
  const match = value.replace(/,/g, '').match(/[-+]?[0-9]*\.?[0-9]+/);
  return match ? Number(match[0]) : null;
}

function parseValue(value) {
  const num = numeric(value);
  const text = String(value ?? '');
  const unit = text.includes('%') ? '%' : /day/i.test(text) ? ' Days' : /hr/i.test(text) ? ' Hrs' : text.includes('$') ? '$' : '';
  const decimals = (text.match(/\.([0-9]+)/)?.[1] || '').length || 1;
  return { num, unit, decimals };
}

function parsePeriod(record, inherited = {}) {
  const period = String(record.period ?? record.label ?? record.date ?? record.name ?? record.month ?? record.quarter ?? record.year ?? '');
  const granularity = String(record.granularity ?? record.interval ?? record.level ?? record.frequency ?? inherited.granularity ?? '').toLowerCase();
  let year = Number(record.year ?? inherited.year) || null;
  let quarter = String(record.quarter ?? inherited.quarter ?? '').toUpperCase().match(/Q[1-4]/)?.[0] || null;
  let month = Number(record.monthNumber ?? record.month_index ?? (typeof record.month === 'number' ? record.month : null)) || null;
  let monthName = String(record.monthName ?? (typeof record.month === 'string' ? record.month : '')).toLowerCase();

  const yearMatch = period.match(/(?:FY\s*)?(20\d{2})/i);
  if (!year && yearMatch) year = Number(yearMatch[1]);
  const quarterMatch = period.match(/Q([1-4])/i);
  if (!quarter && quarterMatch) quarter = `Q${quarterMatch[1]}`;
  const monthDate = period.match(/(?:^|\D)(20\d{2})[-/](\d{1,2})(?:[-/]\d{1,2})?/);
  if (monthDate) {
    year ||= Number(monthDate[1]);
    month ||= Number(monthDate[2]);
  }
  if (!month && monthName) {
    const idx = MONTHS.findIndex((m) => m.toLowerCase() === monthName.slice(0, 3));
    if (idx >= 0) month = idx + 1;
  }
  if (!month) {
    const names = ['january','february','march','april','may','june','july','august','september','october','november','december'];
    const shortNames = MONTHS.map((name) => name.toLowerCase());
    const idx = names.findIndex((name, index) => period.toLowerCase().includes(name) || new RegExp(`\\b${shortNames[index]}\\b`, 'i').test(period));
    if (idx >= 0) month = idx + 1;
  }
  if (!quarter && month) quarter = `Q${Math.ceil(month / 3)}`;

  let value;
  let hasValue = false;
  for (const key of VALUE_KEYS) {
    if (record[key] !== undefined) {
      value = numeric(record[key]);
      hasValue = value !== null;
      if (hasValue) break;
    }
  }
  if (!VALUE_KEYS.some((key) => Object.prototype.hasOwnProperty.call(record, key))) return null;
  const isMonthly = month || /month|monthly/i.test(granularity);
  const isQuarterly = quarter || /quarter|quarterly/i.test(granularity);
  const isYearly = year && !isMonthly && !isQuarterly || /year|annual|yearly/i.test(granularity);
  if (!year) return null;
  return { year: String(year), quarter: isMonthly ? quarter : isQuarterly ? quarter : null, month: isMonthly ? month : null, value: hasValue ? value : null, hasValue, isYearly: Boolean(isYearly), raw: record };
}

function collectPeriods(source) {
  const records = [];
  const visited = new Set();
  const walk = (node, context = {}) => {
    if (!node || typeof node !== 'object' || visited.has(node)) return;
    visited.add(node);
    if (Array.isArray(node)) { node.forEach((item) => walk(item, context)); return; }

    const period = parsePeriod(node, context);
    if (period) records.push(period);
    const inheritedContext = { ...context };
    if (period?.year) inheritedContext.year = Number(period.year);
    else if (Number(node.year)) inheritedContext.year = Number(node.year);
    if (period?.quarter) inheritedContext.quarter = period.quarter;

    for (const [key, value] of Object.entries(node)) {
      const lower = key.toLowerCase();
      if (!CONTAINER_KEYS.includes(lower) && !Array.isArray(value) && (value === null || typeof value !== 'object')) continue;
      const next = { ...inheritedContext };
      if (/^20\d{2}$/.test(key)) next.year = Number(key);
      if (/^q[1-4]$/i.test(key)) next.quarter = key.toUpperCase();
      if (['yearly', 'annual', 'years'].includes(lower)) next.granularity = 'yearly';
      if (['quarterly', 'quarters'].includes(lower)) next.granularity = 'quarterly';
      if (['monthly', 'months'].includes(lower)) next.granularity = 'monthly';
      if (CONTAINER_KEYS.includes(lower) || typeof value === 'object') walk(value, next);
    }
  };
  walk(source);
  return records;
}

function formatValue(value, unit, decimals) {
  if (unit === '$') return `$${value.toLocaleString()}`;
  return `${Number(value.toFixed(decimals))}${unit}`;
}

function evaluateStatus(value, standard, lowerIsBetter) {
  if (lowerIsBetter) return value <= standard ? 'Healthy' : value <= standard * 1.35 ? 'At Risk' : 'Critical';
  return value >= standard ? 'Healthy' : value >= standard * 0.94 ? 'At Risk' : 'Critical';
}

/** Build a hierarchy only from ML Insights periods. Aggregations use stored child periods. */
export function getTrendDrillDownData(metric) {
  if (!metric) return null;
  const standard = metric.standard ?? '0';
  const company = metric.company ?? '0';
  const std = parseValue(standard);
  const current = parseValue(company);
  const unit = current.unit || std.unit || '%';
  const decimals = current.decimals || std.decimals || 1;
  const lowerIsBetter = /[≤<]/.test(String(standard)) || (metric.status === 'Critical' && current.num > std.num);
  const source = { ...(metric.detailedAnalysis?.trendAnalysis || {}), ...(metric.trendAnalysis || {}) };
  const currentYear = new Date().getFullYear();
  const records = collectPeriods(source).filter((record) => Number(record.year) >= 2024 && Number(record.year) <= currentYear);
  if (!records.length) return { years: [], standard, standardNumeric: std.num ?? 0, company, unit, isLowerBetter: lowerIsBetter, decimals, defaultYear: null, defaultQuarter: null };

  const yearMap = new Map();
  const addYear = (year) => {
    if (!yearMap.has(year)) yearMap.set(year, { year, annualValues: [], quarterMap: new Map() });
    return yearMap.get(year);
  };
  records.forEach((record) => {
    const y = addYear(record.year);
    if (record.isYearly && record.hasValue) y.annualValues.push(record.value);
    else if (record.quarter) {
      if (!y.quarterMap.has(record.quarter)) y.quarterMap.set(record.quarter, { values: [], monthMap: new Map(), monthMeta: new Map(), hasQuarterRecord: false });
      const q = y.quarterMap.get(record.quarter);
      if (record.month) { q.monthMap.set(record.month, record.value); q.monthMeta.set(record.month, record.raw); }
      else {
        q.hasQuarterRecord = true;
        if (record.hasValue) q.values.push(record.value);
      }
    }
  });

  const years = [...yearMap.values()].sort((a, b) => Number(a.year) - Number(b.year)).map((yearData, yearIndex, allYears) => {
    const quarterEntries = [...yearData.quarterMap.entries()].sort((a, b) => Number(a[0].slice(1)) - Number(b[0].slice(1)));
    const quarters = quarterEntries.map(([quarter, qData], quarterIndex) => {
      const storedMonths = [...qData.monthMap.entries()].sort((a, b) => a[0] - b[0]);
      const qValues = qData.values.length ? qData.values : storedMonths.map(([, value]) => value).filter(Number.isFinite);
      const qValue = qValues.length ? qValues.reduce((sum, value) => sum + value, 0) / qValues.length : null;
      const months = storedMonths.map(([monthNum, value], index) => ({
        id: `${yearData.year}-${monthNum}`, month: MONTHS[monthNum - 1], fullName: `${MONTHS[monthNum - 1]} ${yearData.year}`,
        period: `${MONTHS[monthNum - 1]} ${yearData.year}`, value: value === null ? 'Data Gap' : formatValue(value, unit, decimals), numericValue: value,
        status: value === null ? 'Data Gap' : evaluateStatus(value, std.num ?? 0, lowerIsBetter), variance: value === null ? 'Data Gap' : `${value - (std.num ?? 0) > 0 ? '+' : ''}${Number((value - (std.num ?? 0)).toFixed(decimals))}${unit}`,
        momChange: index && value !== null && storedMonths[index - 1][1] !== null ? `${(((value - storedMonths[index - 1][1]) / (storedMonths[index - 1][1] || 1)) * 100).toFixed(1)}%` : '-', isCurrent: false, notes: qData.monthMeta?.get(monthNum)?.isPartial ? 'Partial period from ML Insights' : 'Value from ML Insights'
      }));
      if (qValue === null && !qData.hasQuarterRecord && !storedMonths.length) return null;
      const prev = quarterEntries[quarterIndex - 1]?.[1];
      const prevMonths = prev ? [...prev.monthMap.values()].filter(Number.isFinite) : [];
      const prevValue = prev && (prev.values.length ? prev.values.reduce((s, v) => s + v, 0) / prev.values.length : prevMonths.length ? prevMonths.reduce((s, v) => s + v, 0) / prevMonths.length : null);
      return { quarter, label: `${quarter} ${yearData.year}`, period: quarter, year: yearData.year, value: qValue === null ? 'Data Gap' : formatValue(qValue, unit, decimals), numericValue: qValue,
        status: qValue === null ? 'Data Gap' : evaluateStatus(qValue, std.num ?? 0, lowerIsBetter), variance: qValue === null ? 'Data Gap' : `${qValue - (std.num ?? 0) > 0 ? '+' : ''}${Number((qValue - (std.num ?? 0)).toFixed(decimals))}${unit}`,
        qoqChange: prevValue && qValue !== null ? `${qValue >= prevValue ? '+' : ''}${(((qValue - prevValue) / prevValue) * 100).toFixed(1)}%` : '-', isCurrent: false, months,
        summary: source.summary || 'Quarterly value from ML Insights.' };
    }).filter(Boolean);

    const quarterlyValues = quarters.map((q) => q.numericValue).filter(Number.isFinite);
    const yearlyValue = yearData.annualValues.length ? yearData.annualValues.reduce((sum, value) => sum + value, 0) / yearData.annualValues.length
      : quarterlyValues.length ? quarterlyValues.reduce((sum, value) => sum + value, 0) / quarterlyValues.length : null;
    if (yearlyValue === null) return null;
    const previous = allYears[yearIndex - 1];
    const previousAnnual = previous?.annualValues.length ? previous.annualValues.reduce((s, v) => s + v, 0) / previous.annualValues.length : null;
    const yoy = previousAnnual ? `${yearlyValue >= previousAnnual ? '+' : ''}${(((yearlyValue - previousAnnual) / previousAnnual) * 100).toFixed(1)}%` : '-';
    return { year: yearData.year, label: `FY ${yearData.year}`, period: yearData.year, value: formatValue(yearlyValue, unit, decimals), numericValue: yearlyValue,
      status: evaluateStatus(yearlyValue, std.num ?? 0, lowerIsBetter), variance: `${yearlyValue - (std.num ?? 0) > 0 ? '+' : ''}${Number((yearlyValue - (std.num ?? 0)).toFixed(decimals))}${unit}`,
      yoyChange: yoy, isCurrent: false, quarters, summary: source.summary || 'Yearly value from ML Insights.' };
  }).filter(Boolean);
  const latest = years.find((year) => Number(year.year) === currentYear);
  const defaultYear = latest?.year ?? years[years.length - 1]?.year ?? null;
  const latestQuarter = latest?.quarters[latest.quarters.length - 1];
  if (latest) latest.isCurrent = true;
  if (latestQuarter) latestQuarter.isCurrent = true;
  return { metricName: metric.metric, standard, standardNumeric: std.num ?? 0, company, unit, isLowerBetter: lowerIsBetter, decimals, years,
    defaultYear, defaultQuarter: latestQuarter?.quarter ?? null };
}
