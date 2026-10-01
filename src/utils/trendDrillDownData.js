// Comprehensive Multi-Tier Trend Drill-Down Data Engine (Yearly -> Quarterly -> Monthly)
// Generates realistic, mathematically consistent and domain-accurate hierarchical data for SF Health metrics.

/**
 * Parses numeric value and suffix unit from a formatted string (e.g. "91.4%", "6.8 Days", "14.2 Hrs", "≤ 2.5 Days")
 */
function parseMetricValue(str) {
  if (typeof str !== 'string') {
    const num = Number(str) || 0;
    return { num, unit: '', isLowerBetter: false, decimals: 1 };
  }

  const isLowerBetter = str.includes('≤') || str.includes('<');
  // Match digits, optional minus/plus and decimal
  const match = str.replace(/[≤≥<>~]/g, '').trim().match(/[-+]?[0-9]*\.?[0-9]+/);
  const num = match ? parseFloat(match[0]) : 0;

  // Extract unit
  let unit = '';
  if (str.includes('%')) unit = '%';
  else if (str.toLowerCase().includes('day')) unit = ' Days';
  else if (str.toLowerCase().includes('hr')) unit = ' Hrs';
  else if (str.includes('$')) unit = '$';

  const decimals = (match && match[0].includes('.')) ? match[0].split('.')[1].length : 1;

  return { num, unit, isLowerBetter, decimals };
}

/**
 * Determines health status based on value, standard, and variance
 */
function evaluateStatus(valNum, standardNum, isLowerBetter) {
  if (isLowerBetter) {
    if (valNum <= standardNum) return 'Healthy';
    if (valNum <= standardNum * 1.35) return 'At Risk';
    return 'Critical';
  } else {
    if (valNum >= standardNum) return 'Healthy';
    if (valNum >= standardNum * 0.94) return 'At Risk';
    return 'Critical';
  }
}

/**
 * Formats a number with its unit
 */
function formatVal(num, unit, decimals = 1) {
  const rounded = Number(num.toFixed(decimals));
  if (unit === '$') return `$${rounded.toLocaleString()}`;
  return `${rounded}${unit}`;
}

const MONTH_NAMES = {
  Q1: [
    { short: 'Jan', full: 'January' },
    { short: 'Feb', full: 'February' },
    { short: 'Mar', full: 'March' }
  ],
  Q2: [
    { short: 'Apr', full: 'April' },
    { short: 'May', full: 'May' },
    { short: 'Jun', full: 'June' }
  ],
  Q3: [
    { short: 'Jul', full: 'July' },
    { short: 'Aug', full: 'August' },
    { short: 'Sep', full: 'September' }
  ],
  Q4: [
    { short: 'Oct', full: 'October' },
    { short: 'Nov', full: 'November' },
    { short: 'Dec', full: 'December' }
  ]
};

/**
 * Builds the complete 3-tier hierarchy (Yearly -> Quarterly -> Monthly) for a metric
 */
export function getTrendDrillDownData(metric) {
  if (!metric) return null;

  const {
    company = '0',
    standard = '0',
    status = 'At Risk',
    variance = '0',
    detailedAnalysis = {}
  } = metric;

  const parsedCompany = parseMetricValue(company);
  const parsedStandard = parseMetricValue(standard);
  const unit = parsedCompany.unit || parsedStandard.unit || '%';
  const isLowerBetter = parsedStandard.isLowerBetter || standard.includes('≤') || status === 'Critical' && parsedCompany.num > parsedStandard.num;
  const decimals = parsedCompany.decimals || 1;

  // Check if existing trend points exist in detailedAnalysis
  const existingPoints = detailedAnalysis?.trendAnalysis?.points || [];
  const qVals2026 = {};

  if (existingPoints.length >= 4) {
    existingPoints.forEach((pt, i) => {
      const qKey = `Q${i + 1}`;
      const p = parseMetricValue(pt.value);
      qVals2026[qKey] = p.num;
    });
  } else {
    // Generate realistic 2026 quarters leading to current company value
    const cur = parsedCompany.num;
    if (isLowerBetter) {
      // Typically deteriorating (increasing)
      qVals2026.Q1 = Number((cur * 0.86).toFixed(decimals));
      qVals2026.Q2 = Number((cur * 0.91).toFixed(decimals));
      qVals2026.Q3 = Number((cur * 0.96).toFixed(decimals));
      qVals2026.Q4 = cur;
    } else {
      // Typically deteriorating (decreasing)
      qVals2026.Q1 = Number((cur * 1.04).toFixed(decimals));
      qVals2026.Q2 = Number((cur * 1.025).toFixed(decimals));
      qVals2026.Q3 = Number((cur * 1.01).toFixed(decimals));
      qVals2026.Q4 = cur;
    }
  }

  // Generate 2025 quarters (historical prior year)
  const qVals2025 = {};
  if (isLowerBetter) {
    qVals2025.Q1 = Number((qVals2026.Q1 * 0.82).toFixed(decimals));
    qVals2025.Q2 = Number((qVals2026.Q1 * 0.88).toFixed(decimals));
    qVals2025.Q3 = Number((qVals2026.Q1 * 0.93).toFixed(decimals));
    qVals2025.Q4 = Number((qVals2026.Q1 * 0.98).toFixed(decimals));
  } else {
    qVals2025.Q1 = Number((qVals2026.Q1 * 1.04).toFixed(decimals));
    qVals2025.Q2 = Number((qVals2026.Q1 * 1.03).toFixed(decimals));
    qVals2025.Q3 = Number((qVals2026.Q1 * 1.015).toFixed(decimals));
    qVals2025.Q4 = Number((qVals2026.Q1 * 1.005).toFixed(decimals));
  }

  // Generate 2024 quarters (historical baseline year)
  const qVals2024 = {};
  if (isLowerBetter) {
    qVals2024.Q1 = Number((qVals2025.Q1 * 0.85).toFixed(decimals));
    qVals2024.Q2 = Number((qVals2025.Q1 * 0.89).toFixed(decimals));
    qVals2024.Q3 = Number((qVals2025.Q1 * 0.94).toFixed(decimals));
    qVals2024.Q4 = Number((qVals2025.Q1 * 0.97).toFixed(decimals));
  } else {
    qVals2024.Q1 = Number((qVals2025.Q1 * 1.03).toFixed(decimals));
    qVals2024.Q2 = Number((qVals2025.Q1 * 1.02).toFixed(decimals));
    qVals2024.Q3 = Number((qVals2025.Q1 * 1.01).toFixed(decimals));
    qVals2024.Q4 = Number((qVals2025.Q1 * 1.002).toFixed(decimals));
  }

  const rawQuarterSets = {
    '2024': qVals2024,
    '2025': qVals2025,
    '2026': qVals2026
  };

  // Helper to build 3 months for a given year and quarter
  const buildMonths = (year, qKey, qTargetVal, isCurQuarter) => {
    const monthsMeta = MONTH_NAMES[qKey];
    // Slightly vary the 3 months around the quarter value
    const deltas = isLowerBetter ? [-0.03, 0.0, 0.03] : [0.015, -0.0, -0.015];

    return monthsMeta.map((mMeta, mIdx) => {
      let mVal;
      if (year === '2026' && qKey === 'Q4' && mIdx === 2) {
        // Last month of 2026 Q4 is exactly current company value
        mVal = parsedCompany.num;
      } else {
        const delta = qTargetVal * deltas[mIdx];
        mVal = Number((qTargetVal + delta).toFixed(decimals));
      }

      const mStatus = evaluateStatus(mVal, parsedStandard.num, isLowerBetter);
      const isCurMonth = isCurQuarter && mIdx === 2;

      // Variance vs Standard
      const varDiff = Number((mVal - parsedStandard.num).toFixed(decimals));
      const varSign = varDiff > 0 ? '+' : '';
      const varDisplay = `${varSign}${varDiff}${unit}`;

      // MoM movement
      const momSign = deltas[mIdx] >= 0 ? '+' : '';
      const momChange = `${momSign}${(deltas[mIdx] * 100).toFixed(1)}%`;

      return {
        id: `${year}-${qKey}-${mMeta.short.toLowerCase()}`,
        month: mMeta.short,
        fullName: `${mMeta.full} ${year}`,
        period: `${mMeta.short} ${year}${isCurMonth ? ' (Current)' : ''}`,
        value: formatVal(mVal, unit, decimals),
        numericValue: mVal,
        status: mStatus,
        variance: varDisplay,
        momChange,
        isCurrent: isCurMonth,
        notes: isCurMonth
          ? 'Latest monthly audit scan from active SuccessFactors instance'
          : `Validated operational cycle cadence for ${mMeta.full}`
      };
    });
  };

  // Build the years and quarters
  const yearsList = ['2024', '2025', '2026'].map((year) => {
    const isCurrentYear = year === '2026';
    const qVals = rawQuarterSets[year];

    // Compute quarters for this year
    const quarters = ['Q1', 'Q2', 'Q3', 'Q4'].map((qKey) => {
      const qNum = qVals[qKey];
      const isCurQuarter = isCurrentYear && qKey === 'Q4';
      const qStatus = evaluateStatus(qNum, parsedStandard.num, isLowerBetter);
      const months = buildMonths(year, qKey, qNum, isCurQuarter);

      // QoQ change
      let qoqChange = '-';
      if (qKey === 'Q2') qoqChange = `${(((qNum - qVals.Q1) / (qVals.Q1 || 1)) * 100).toFixed(1)}%`;
      else if (qKey === 'Q3') qoqChange = `${(((qNum - qVals.Q2) / (qVals.Q2 || 1)) * 100).toFixed(1)}%`;
      else if (qKey === 'Q4') qoqChange = `${(((qNum - qVals.Q3) / (qVals.Q3 || 1)) * 100).toFixed(1)}%`;
      if (qoqChange !== '-' && !qoqChange.startsWith('-') && !qoqChange.startsWith('+')) {
        qoqChange = `+${qoqChange}`;
      }

      // Variance vs Standard
      const varDiff = Number((qNum - parsedStandard.num).toFixed(decimals));
      const varSign = varDiff > 0 ? '+' : '';
      const varDisplay = `${varSign}${varDiff}${unit}`;

      return {
        quarter: qKey,
        label: `${qKey} ${year}`,
        period: isCurQuarter ? `${qKey} (Current)` : qKey,
        year,
        value: formatVal(qNum, unit, decimals),
        numericValue: qNum,
        status: qStatus,
        variance: varDisplay,
        qoqChange,
        isCurrent: isCurQuarter,
        months,
        summary: isCurQuarter
          ? (detailedAnalysis?.trendAnalysis?.summary || `Current operating quarter performance against the ${standard} standard.`)
          : `Quarterly operational review for ${qKey} ${year}.`
      };
    });

    // Compute year average
    const yearAvg = Number(
      (quarters.reduce((acc, q) => acc + q.numericValue, 0) / quarters.length).toFixed(decimals)
    );
    const yearStatus = evaluateStatus(yearAvg, parsedStandard.num, isLowerBetter);

    let yoyChange = '-';
    if (year === '2025') {
      const y24Avg = quarters.reduce((acc, q) => acc + qVals2024[q.quarter], 0) / 4;
      const pct = (((yearAvg - y24Avg) / (y24Avg || 1)) * 100).toFixed(1);
      yoyChange = pct > 0 ? `+${pct}%` : `${pct}%`;
    } else if (year === '2026') {
      const y25Avg = quarters.reduce((acc, q) => acc + qVals2025[q.quarter], 0) / 4;
      const pct = (((yearAvg - y25Avg) / (y25Avg || 1)) * 100).toFixed(1);
      yoyChange = pct > 0 ? `+${pct}%` : `${pct}%`;
    }

    const varDiff = Number((yearAvg - parsedStandard.num).toFixed(decimals));
    const varSign = varDiff > 0 ? '+' : '';
    const varDisplay = `${varSign}${varDiff}${unit}`;

    return {
      year,
      label: `FY ${year}`,
      period: isCurrentYear ? `${year} (Current FY)` : year,
      value: formatVal(yearAvg, unit, decimals),
      numericValue: yearAvg,
      status: yearStatus,
      variance: varDisplay,
      yoyChange,
      isCurrent: isCurrentYear,
      quarters,
      summary: isCurrentYear
        ? `FY 2026 Year-to-Date: ${detailedAnalysis?.trendAnalysis?.summary || 'Persistent variance observed across core operating quarters.'}`
        : year === '2025'
          ? `FY 2025 Historical Baseline: Preceding annual cycle before major organizational changes.`
          : `FY 2024 Historical Benchmark: Standard enterprise baseline performance.`
    };
  });

  return {
    metricName: metric.metric,
    standard,
    standardNumeric: parsedStandard.num,
    company,
    unit,
    isLowerBetter,
    decimals,
    years: yearsList,
    defaultYear: '2026',
    defaultQuarter: 'Q4'
  };
}
