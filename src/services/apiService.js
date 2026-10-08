import { APP_CONFIG } from '../config/env';
import { SF_MODULES } from '../data/modulesData';

const BASE_URL = APP_CONFIG.apiBaseUrl || 'http://localhost:8000/api/v1';

/**
 * Helper to execute fetch with timeout
 */
async function fetchWithTimeout(resource, options = {}, timeoutMs = 20000) {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(resource, {
      ...options,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...(options.headers || {})
      }
    });
    clearTimeout(id);
    return response;
  } catch (error) {
    clearTimeout(id);
    throw error;
  }
}

const CANONICAL_MODULE_NAMES = {
  ec: 'Employee Central',
  rcm: 'Recruitment',
  onb: 'Onboarding',
  ofb: 'Offboarding',
  ecp: 'Employee Central Payroll'
};

function normalizeAlphaKey(text) {
  if (!text) return '';
  const clean = String(text).replace(/\(.*?\)/g, '');
  return clean.replace(/[^a-zA-Z0-9]/g, '').toLowerCase();
}

function normalizeStatus(status, variance = '') {
  const s = String(status || '').toLowerCase().trim();
  const v = String(variance || '').toLowerCase().trim();
  if (s.includes('crit')) return 'Critical';
  if (s.includes('risk') || s.includes('warn') || s.includes('succeed')) return 'At Risk';
  if (s.includes('health') || v.includes('on target')) return 'Healthy';
  if (v.includes('+') || v.includes('-')) return 'At Risk';
  return 'Healthy';
}

function sanitizeAndMergeModules(rawModules) {
  if (!Array.isArray(rawModules) || rawModules.length === 0) {
    return SF_MODULES;
  }

  const defaultModulesMap = new Map();
  SF_MODULES.forEach(mod => {
    defaultModulesMap.set(mod.id.toLowerCase(), mod);
  });

  return rawModules.map(rawMod => {
    const modId = (rawMod.id || '').toLowerCase();
    const defaultMod = defaultModulesMap.get(modId);
    const modName = CANONICAL_MODULE_NAMES[modId] || defaultMod?.name || rawMod.name || 'Module';

    const defaultBenchmarkMap = new Map();
    if (defaultMod && Array.isArray(defaultMod.benchmarks)) {
      defaultMod.benchmarks.forEach(b => {
        defaultBenchmarkMap.set(normalizeAlphaKey(b.metric), b);
        defaultBenchmarkMap.set(normalizeAlphaKey(b.code), b);
      });
    }

    const mergedBenchmarks = [];
    const seenAlphaKeys = new Set();
    const incomingBenchmarks = Array.isArray(rawMod.benchmarks) ? rawMod.benchmarks : [];

    for (const b of incomingBenchmarks) {
      const alphaKey = normalizeAlphaKey(b.metric || b.code || '');
      if (!alphaKey) continue;

      const defaultB = defaultBenchmarkMap.get(alphaKey);

      if (seenAlphaKeys.has(alphaKey)) {
        const existingIdx = mergedBenchmarks.findIndex(item => normalizeAlphaKey(item.metric) === alphaKey);
        if (existingIdx !== -1) {
          const existing = mergedBenchmarks[existingIdx];
          if ((existing.company === '0%' || !existing.company) && b.company && b.company !== '0%') {
            existing.company = b.company;
            existing.standard = b.standard || existing.standard;
            existing.variance = b.variance || existing.variance;
          }
        }
        continue;
      }

      seenAlphaKeys.add(alphaKey);

      const metricName = defaultB?.metric || b.metric || b.code;
      const category = b.category || defaultB?.category || 'Operational KPI';

      // Check if this metric is live from Supabase Storage or Table
      const isFromSupabase = Boolean(
        b._source === 'supabase_storage_metric_folder' ||
        b._source === 'supabase_llm_reports_table' ||
        b._source === 'supabase_ml_notebook_insights_table' ||
        b._source === 'supabase_table' ||
        b._source === 'supabase' ||
        b._storage_path ||
        b.isSupabaseLive ||
        (b.company && !['not yet fetched', 'data not yet fetched from supabase', '--', '-'].includes(String(b.company).toLowerCase().trim()))
      );

      let companyVal = isFromSupabase ? (b.company || 'Not yet fetched') : 'Not yet fetched';
      let standardVal = isFromSupabase ? (b.standard || 'Not yet fetched') : 'Not yet fetched';
      let varianceVal = isFromSupabase ? (b.variance || 'Not yet fetched') : 'Not yet fetched';

      let statusVal = isFromSupabase ? (b.status || 'At Risk') : 'Not yet fetched';
      if (statusVal === 'succeeded' || statusVal === 'completed') {
        statusVal = normalizeStatus(null, varianceVal);
      }

      // Direct extraction of moduleOverview if provided in Supabase JSON
      const overview = (
        b.moduleOverview ||
        extractSectionValue(b, 'moduleOverview', 'module_overview', 'overview') ||
        {}
      );

      const liveRootCause = (
        extractSectionValue(overview, 'rootCause', 'root_cause') ||
        extractSectionValue(b, 'rootCause', 'root_cause') ||
        (isFromSupabase ? b.whyItHappens : null)
      );

      const liveAffectedArea = (
        extractSectionValue(overview, 'affectedArea', 'affected_area') ||
        extractSectionValue(b, 'affectedArea', 'affected_area') ||
        (isFromSupabase ? b.whereItHappens : null)
      );

      const rawBWorkstreams = b.workstreams || overview.workstreams || [];
      let bWsSteps = [];
      if (Array.isArray(rawBWorkstreams) && rawBWorkstreams.length > 0) {
        bWsSteps = rawBWorkstreams
          .filter(w => w && (w.step || w.remediationStep || w.title) && w.kind !== 'data')
          .map(w => w.step || w.remediationStep || w.title);
        if (bWsSteps.length === 0) {
          bWsSteps = rawBWorkstreams
            .filter(w => w && (w.step || w.remediationStep || w.title))
            .map(w => w.step || w.remediationStep || w.title);
        }
      }

      const rawLiveSuggestions = (
        (bWsSteps.length > 0 ? bWsSteps : null) ||
        (overview.suggestions && overview.suggestions.length > 0 ? overview.suggestions : null) ||
        (b.moduleOverview?.suggestions && b.moduleOverview.suggestions.length > 0 ? b.moduleOverview.suggestions : null) ||
        (b.suggestions && b.suggestions.length > 0 ? b.suggestions : null) ||
        extractSectionValue(overview, 'suggestions') ||
        extractSectionValue(b, 'suggestions') ||
        (isFromSupabase ? b.howToOvercome : null)
      );
      const liveSuggestions = Array.isArray(rawLiveSuggestions)
        ? rawLiveSuggestions
        : (typeof rawLiveSuggestions === 'string' ? [rawLiveSuggestions] : (rawLiveSuggestions ? [rawLiveSuggestions] : null));

      const finalWhyItHappens = liveRootCause || (isFromSupabase ? b.whyItHappens : null) || 'Data not yet fetched from Supabase';
      const finalWhereItHappens = liveAffectedArea || (isFromSupabase ? b.whereItHappens : null) || 'Data not yet fetched from Supabase';
      const finalSuggestions = liveSuggestions !== null ? liveSuggestions : (isFromSupabase ? [] : []);

      const finalModuleOverview = {
        rootCause: liveRootCause || finalWhyItHappens,
        affectedArea: liveAffectedArea || finalWhereItHappens,
        suggestions: finalSuggestions
      };

      const detailedAnalysis = {
        ...(defaultB?.detailedAnalysis || {}),
        ...(b.detailedAnalysis || {}),
        whyItHappens: finalWhyItHappens,
        whereItHappens: finalWhereItHappens,
        howToOvercome: finalSuggestions
      };

      mergedBenchmarks.push({
        ...defaultB,
        ...b,
        code: b.code || defaultB?.code || `${modId}_${alphaKey}`,
        metric: metricName,
        category,
        company: companyVal,
        standard: standardVal,
        status: statusVal,
        variance: varianceVal,
        _source: isFromSupabase ? (b._source || 'supabase_table') : 'static_baseline',
        isSupabaseLive: isFromSupabase,
        diagnosis: b.diagnosis || defaultB?.diagnosis || {},
        moduleOverview: finalModuleOverview,
        detailedAnalysis
      });
    }

    if (defaultMod && Array.isArray(defaultMod.benchmarks)) {
      for (const defB of defaultMod.benchmarks) {
        const defKey = normalizeAlphaKey(defB.metric);
        if (!seenAlphaKeys.has(defKey)) {
          seenAlphaKeys.add(defKey);
          mergedBenchmarks.push({
            ...defB,
            company: 'Not yet fetched',
            standard: 'Not yet fetched',
            status: 'Not yet fetched',
            variance: 'Not yet fetched',
            moduleOverview: {
              rootCause: 'Data not yet fetched from Supabase',
              affectedArea: 'Data not yet fetched from Supabase',
              suggestions: []
            },
            detailedAnalysis: {
              whyItHappens: 'Data not yet fetched from Supabase',
              whereItHappens: 'Data not yet fetched from Supabase',
              trendAnalysis: { summary: 'Data not yet fetched from Supabase', points: [] },
              missingConfigurations: [],
              howItEffects: 'Data not yet fetched from Supabase',
              howToOvercome: []
            },
            _source: 'static_baseline',
            isSupabaseLive: false
          });
        }
      }
    }

    const critCount = mergedBenchmarks.filter(b => b.status === 'Critical').length;
    const atRiskCount = mergedBenchmarks.filter(b => b.status === 'At Risk').length;
    const healthyCount = mergedBenchmarks.filter(b => b.status === 'Healthy').length;
    const hasLive = mergedBenchmarks.some(b => b.isSupabaseLive);

    let computedModuleStatus = 'Not yet fetched';
    if (hasLive) {
      if (critCount > 0) computedModuleStatus = 'Critical';
      else if (atRiskCount > 0) computedModuleStatus = 'At Risk';
      else computedModuleStatus = 'Healthy';
    }

    const computedAiReport = hasLive
      ? (rawMod.aiReport || { summary: `${modName} health status is ${computedModuleStatus}.` })
      : { summary: 'Data not yet fetched from Supabase.' };

    return {
      ...defaultMod,
      ...rawMod,
      id: modId,
      name: modName,
      status: computedModuleStatus,
      aiReport: computedAiReport,
      benchmarks: mergedBenchmarks,
      benchmarksCount: mergedBenchmarks.length,
      criticalCount: critCount,
      atRiskCount: atRiskCount,
      healthyCount: healthyCount
    };
  });
}

function extractSectionValue(obj, ...candidateKeys) {
  if (!obj || typeof obj !== 'object') return null;
  const normalized = candidateKeys.map(k => k.toLowerCase().replace(/[_-]/g, ''));

  for (const [k, v] of Object.entries(obj)) {
    const cleanK = k.toLowerCase().replace(/[_-]/g, '');
    if (normalized.includes(cleanK) && v !== null && v !== undefined && v !== '') {
      return v;
    }
  }

  const containers = ['moduleOverview', 'module_overview', 'overview', 'report', 'detailedAnalysis', 'detailed_analysis'];
  for (const c of containers) {
    if (obj[c] && typeof obj[c] === 'object' && !Array.isArray(obj[c])) {
      const res = extractSectionValue(obj[c], ...candidateKeys);
      if (res !== null && res !== undefined && res !== '') return res;
    }
  }

  for (const v of Object.values(obj)) {
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      const res = extractSectionValue(v, ...candidateKeys);
      if (res !== null && res !== undefined && res !== '') return res;
    }
  }
  return null;
}

/**
 * Direct fetch from Supabase Storage REST API
 * Bypasses any in-memory backend cache so user edits in Supabase reflect immediately!
 */
async function fetchDirectSupabaseStorageMetric(moduleFolder = 'rcm', metricName = 'TimeToHire') {
  if (!APP_CONFIG.supabaseUrl || !APP_CONFIG.supabaseKey) return null;
  const bucket = APP_CONFIG.supabaseBucket || 'Insights and Reports';

  const modClean = String(moduleFolder).toLowerCase().trim();
  const folders = Array.from(new Set([moduleFolder, modClean, modClean.toUpperCase()])).filter(Boolean);
  const prefixes = ['reports/latest', 'report/latest', 'latest', 'reports', 'report'];

  const rawName = String(metricName || '').replace(/\.json$/i, '').trim();
  const alphaName = normalizeAlphaKey(rawName);
  const snakeName = rawName.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
  const pascalName = rawName.replace(/(?:^\w|[A-Z]|\b\w)/g, (letter) => letter.toUpperCase()).replace(/[\s_-]+/g, '');

  const metricAliases = Array.from(new Set([rawName, alphaName, snakeName, pascalName])).filter(Boolean);

  const candidateUrls = [];
  for (const p of prefixes) {
    for (const f of folders) {
      for (const m of metricAliases) {
        candidateUrls.push(`${APP_CONFIG.supabaseUrl}/storage/v1/object/${encodeURIComponent(bucket)}/${p}/${f}/${m}.json`);
        candidateUrls.push(`${APP_CONFIG.supabaseUrl}/storage/v1/object/public/${encodeURIComponent(bucket)}/${p}/${f}/${m}.json`);
        candidateUrls.push(`${APP_CONFIG.supabaseUrl}/storage/v1/object/authenticated/${encodeURIComponent(bucket)}/${p}/${f}/${m}.json`);
      }
    }
  }

  for (const url of candidateUrls) {
    try {
      const res = await fetchWithTimeout(url, {
        method: 'GET',
        headers: {
          'apikey': APP_CONFIG.supabaseKey,
          'Authorization': `Bearer ${APP_CONFIG.supabaseKey}`
        }
      }, 1500);
      if (res.ok) {
        const json = await res.json();
        if (json && typeof json === 'object') {
          json._storage_path = url;
          json._source = 'supabase_storage_metric_folder';
          return json;
        }
      }
    } catch {
      // try next candidate
    }
  }
  return null;
}

/**
 * Direct fetch from Supabase REST Database Table API
 */
async function fetchDirectSupabaseTable(tableName) {
  if (!APP_CONFIG.supabaseUrl || !APP_CONFIG.supabaseKey) return [];
  try {
    const res = await fetchWithTimeout(
      `${APP_CONFIG.supabaseUrl}/rest/v1/${tableName}?select=*&limit=50`,
      {
        method: 'GET',
        headers: {
          'apikey': APP_CONFIG.supabaseKey,
          'Authorization': `Bearer ${APP_CONFIG.supabaseKey}`
        }
      },
      3000
    );
    if (res.ok) {
      const data = await res.json();
      if (Array.isArray(data)) return data;
    }
  } catch (err) {
    console.warn(`Direct fetch of Supabase table ${tableName} failed:`, err.message);
  }
  return [];
}

/**
 * Completely normalizes any Supabase payload (from Table or Storage) into the 8-section BRD schema
 */
function normalizeSupabaseInsightPayload(rawData, metricCode, metricName = null) {
  if (!rawData || typeof rawData !== 'object') return null;

  const repNested = (rawData.report && typeof rawData.report === 'object') ? rawData.report : {};
  const rep = { ...repNested, ...rawData };
  const overview = rawData.moduleOverview || rawData.module_overview || rep.moduleOverview || rep.module_overview || {};

  const rootCause = (
    overview.rootCause ||
    overview.root_cause ||
    extractSectionValue(rawData, 'rootCause', 'root_cause') ||
    rawData.whyItHappens ||
    rep.diagnosis?.headline ||
    rep.diagnosis?.narrative
  );

  const affectedArea = (
    overview.affectedArea ||
    overview.affected_area ||
    extractSectionValue(rawData, 'affectedArea', 'affected_area') ||
    rawData.whereItHappens
  );

  const diagObj = rep.diagnosis && typeof rep.diagnosis === 'object' ? rep.diagnosis : {};

  // Extract dynamic workstreams from Supabase
  const rawWs = rawData.workstreams || rep.workstreams || [];
  let wsSteps = [];
  if (Array.isArray(rawWs) && rawWs.length > 0) {
    wsSteps = rawWs
      .filter(w => w && (w.step || w.remediationStep || w.title) && w.kind !== 'data')
      .map(w => w.step || w.remediationStep || w.title);
    if (wsSteps.length === 0) {
      wsSteps = rawWs
        .filter(w => w && (w.step || w.remediationStep || w.title))
        .map(w => w.step || w.remediationStep || w.title);
    }
  }

  const rawSug = (
    (wsSteps.length > 0 ? wsSteps : null) ||
    (Array.isArray(rawData.suggestions) && rawData.suggestions.length > 0 ? rawData.suggestions : null) ||
    (Array.isArray(repNested.suggestions) && repNested.suggestions.length > 0 ? repNested.suggestions : null) ||
    (Array.isArray(diagObj.suggestions) && diagObj.suggestions.length > 0 ? diagObj.suggestions : null) ||
    (Array.isArray(overview.suggestions) && overview.suggestions.length > 0 ? overview.suggestions : null) ||
    extractSectionValue(rawData, 'suggestions') ||
    extractSectionValue(rawData, 'howToOvercome', 'how_to_overcome') ||
    rawData.howToOvercome ||
    rep.recommendations
  );
  const suggestionsList = Array.isArray(rawSug) ? rawSug : (typeof rawSug === 'string' ? [rawSug] : (rawSug ? [rawSug] : []));

  const modOverviewObj = {
    rootCause: rootCause || 'Diagnostic variance detected against benchmark standard.',
    affectedArea: affectedArea || 'SuccessFactors workflow touchpoints',
    suggestions: suggestionsList
  };
  const headlineText = String(diagObj.headline || '');
  const narrativeText = String(diagObj.narrative || '');
  const impactText = String(rep.businessImpact?.overview || rawData.businessImpact?.overview || '');
  const fullText = `${headlineText} ${narrativeText} ${impactText}`.trim();

  const cleanStr = (v) => {
    if (!v) return null;
    const s = String(v).trim();
    if (['not yet fetched', 'data not yet fetched from supabase', '--', '-', 'none', 'null', ''].includes(s.toLowerCase())) {
      return null;
    }
    return s;
  };

  let companyVal = cleanStr(
    rawData.company || rep.company || rawData.company_actual || rep.company_actual ||
    rawData.current_value || rep.current_value || diagObj.current_value || diagObj.actual
  );
  if (!companyVal && fullText) {
    const m1 = fullText.match(/(?:stands\s+at|actual\s+is|is\s+at|reaching|reaches)\s+([0-9.]+\s*(?:days|hours|weeks|months|%|\$|k)?)/i);
    if (m1) {
      companyVal = m1[1].trim();
    } else {
      const m2 = fullText.match(/(?:current\s+[a-zA-Z\s_-]+?\s+(?:stands\s+at|is|at))\s+([0-9.]+\s*(?:days|hours|weeks|months|%|\$|k)?)/i);
      if (m2) {
        companyVal = m2[1].trim();
      } else {
        const m3 = fullText.match(/(?:stands\s+at|at)\s+([0-9.]+\s*(?:days|hours|weeks|months|%|\$|k)?)/i);
        if (m3) companyVal = m3[1].trim();
      }
    }
  }

  let standardVal = cleanStr(
    rawData.standard || rep.standard || rawData.benchmark_target || rep.benchmark_target ||
    diagObj.standard || diagObj.target
  );
  if (!standardVal && fullText) {
    const mT = fullText.match(/(?:industry\s+standard|standard|benchmark|target)\s*(?:of|is|at|≤|≥)?\s*([≤≥<>~]?\s*[0-9.]+\s*(?:days|hours|weeks|months|%|\$|k)?)/i);
    if (mT) {
      const rawT = mT[1].trim();
      if (!/^[≤≥<>~]/.test(rawT)) {
        standardVal = /(?:day|hour|week|month|turnaround|latency|attrition)/i.test(rawT) ? `≤ ${rawT}` : `≥ ${rawT}`;
      } else {
        standardVal = rawT;
      }
    }
  }

  let varianceVal = cleanStr(
    rawData.variance || rep.actual_variance || rawData.variance_percentage || rawData.gap ||
    rep.gap || diagObj.gap
  );
  if (!varianceVal && fullText) {
    const mV1 = fullText.match(/([0-9.]+\s*(?:days|hours|weeks|%)?)(?:\s*\((?:or\s*)?([0-9.]+%)\))?\s*(above|below)/i);
    if (mV1) {
      const diffNum = mV1[1].trim();
      const pct = mV1[2];
      const dir = mV1[3].toLowerCase() === 'above' ? '+' : '-';
      varianceVal = pct ? `${dir}${diffNum} (${dir}${pct})` : `${dir}${diffNum}`;
    } else {
      const mV2 = fullText.match(/(?:exceeding|above|below)\s+[^,.]*?\s+by\s+([0-9.]+\s*(?:days|hours|weeks|%)?)/i);
      if (mV2) varianceVal = `+${mV2[1].trim()}`;
    }
  }

  if (!varianceVal && companyVal && standardVal && companyVal !== 'Not yet fetched' && standardVal !== 'Not yet fetched') {
    const cNum = String(companyVal).match(/([0-9.]+)/);
    const tNum = String(standardVal).match(/([0-9.]+)/);
    if (cNum && tNum) {
      const cF = parseFloat(cNum[1]);
      const tF = parseFloat(tNum[1]);
      const diff = cF - tF;
      const unit = /day/i.test(companyVal) ? ' days' : (/%/.test(companyVal) ? '%' : '');
      const pctDiff = tF !== 0 ? Math.abs((diff / tF) * 100).toFixed(1) : '0';
      const sign = diff > 0 ? '+' : '-';
      varianceVal = `${sign}${Math.abs(diff).toFixed(1)}${unit} (${sign}${pctDiff}%)`;
    }
  }

  const statusCandidate = String(rawData.status || rep.healthState || rep.health_state || '').toLowerCase();
  let statusVal = 'At Risk';
  if (statusCandidate.includes('crit')) statusVal = 'Critical';
  else if (statusCandidate.includes('risk') || statusCandidate.includes('warn') || statusCandidate.includes('breach')) statusVal = 'At Risk';
  else if (statusCandidate.includes('health') || statusCandidate.includes('target') || statusCandidate.includes('good')) statusVal = 'Healthy';
  else if (fullText) {
    if (/\bcritical\b/i.test(fullText)) statusVal = 'Critical';
    else if (/\b(?:at-risk|at_risk|at risk|warning)\b/i.test(fullText)) statusVal = 'At Risk';
    else if (/\b(?:healthy|on-track|on track)\b/i.test(fullText)) statusVal = 'Healthy';
  }

  companyVal = companyVal || 'Not yet fetched';
  standardVal = standardVal || 'Not yet fetched';
  varianceVal = varianceVal || 'Not yet fetched';

  // 1. Factors / Drivers extraction
  const factorsRaw = rep.factors || rawData.factors || [];
  const shapFactors = [];
  let stageDrivers = [];
  let segmentDrivers = [];

  if (Array.isArray(factorsRaw) && factorsRaw.length > 0) {
    for (const f of factorsRaw) {
      if (typeof f === 'object' && f) {
        const fname = f.factorName || f.name || 'Operational Factor';
        const pct = f.impactPct || f.impact_pct || 0;
        const val = f.avgFactorValue || f.value || '';
        const entry = {
          name: fname,
          impact: typeof pct === 'string' && pct.includes('%') ? pct : `+${pct}%`,
          description: `Contributes ${pct}% to the variance gap (average ${val}).`
        };
        shapFactors.push(entry);
        if (/role|job|segment/i.test(fname)) {
          segmentDrivers.push({
            id: `A${segmentDrivers.length + 1}`,
            driver: fname,
            name: fname,
            avgDays: val || '-',
            vsCompany: entry.impact
          });
        } else {
          stageDrivers.push({
            id: `S${stageDrivers.length + 1}`,
            driver: fname,
            name: fname,
            avgDays: val || '-',
            share: entry.impact
          });
        }
      }
    }
  }

  // Explicit driver arrays override
  const explicitStage = rep.stageDrivers || rep.stage_drivers || rawData.stageDrivers || rawData.stage_drivers;
  if (Array.isArray(explicitStage) && explicitStage.length > 0) {
    stageDrivers = explicitStage.map((sd, i) => ({
      id: sd.id || `S${i + 1}`,
      driver: sd.driver || sd.name || sd.stage || `Stage ${i + 1}`,
      name: sd.name || sd.driver || `Stage ${i + 1}`,
      avgDays: sd.avgDays || sd.days || sd.impact || '-',
      share: sd.share || sd.impact || (sd.breachContribution ? `${sd.breachContribution}%` : '-')
    }));
  }

  const explicitSegment = rep.segmentDrivers || rep.segment_drivers || rawData.segmentDrivers || rawData.segment_drivers;
  if (Array.isArray(explicitSegment) && explicitSegment.length > 0) {
    segmentDrivers = explicitSegment.map((seg, i) => ({
      id: seg.id || `A${i + 1}`,
      driver: seg.driver || seg.name || seg.segment || `Segment ${i + 1}`,
      name: seg.name || seg.driver || `Segment ${i + 1}`,
      avgDays: seg.avgDays || seg.actual || seg.impact || '-',
      vsCompany: seg.vsCompany || seg.gap || seg.impact || '-'
    }));
  }

  // 2. Plan extraction (prioritizing top-level dynamic plan with 114 hours, 6 weeks)
  const rawPlan = rawData.plan || rawData.brdPlan || rep.plan || rep.brdPlan || repNested.plan || {};

  // Phases
  const rawPhases = rawPlan.phases || rawPlan.phasedActivities || [];
  const phasedActivities = [];
  if (Array.isArray(rawPhases)) {
    for (let pIdx = 0; pIdx < rawPhases.length; pIdx++) {
      const p = rawPhases[pIdx];
      const pName = p.phaseName || p.title || p.phase || `Phase ${pIdx + 1}`;
      const acts = [];
      const rawActs = p.activities || [];
      if (Array.isArray(rawActs)) {
        for (const a of rawActs) {
          const h = a.effort || a.hours || 8;
          acts.push({
            activity: a.activity || a.title || a.name || '',
            owner: a.owner || a.role || 'Specialist',
            workstream: a.workstream || a.id || '-',
            effort: typeof h === 'number' || !String(h).includes('Hour') ? `${h} Hours` : String(h)
          });
        }
      }
      phasedActivities.push({
        phaseName: pName,
        milestone: p.milestone || '',
        deliverable: p.deliverable || '',
        activities: acts
      });
    }
  }

  // Roles
  const rawRoles = rawPlan.roles || rawPlan.specialistManpower || [];
  const specialistManpower = [];
  if (Array.isArray(rawRoles)) {
    for (const r of rawRoles) {
      const h = r.effort || r.hours || 40;
      specialistManpower.push({
        role: r.role || 'Specialist Consultant',
        headcount: r.headcount || r.count || 1,
        effort: typeof h === 'number' || !String(h).includes('Hour') ? `${h} Person-Hours` : String(h)
      });
    }
  }

  // Workstreams
  const rawPlanWs = rep.workstreams || rawData.workstreams || rawPlan.executionWorkstreams || rawPlan.workstreams || [];
  const executionWorkstreams = [];
  if (Array.isArray(rawPlanWs) && rawPlanWs.length > 0) {
    for (let i = 0; i < rawPlanWs.length; i++) {
      const ws = rawPlanWs[i];
      let fixes = ws.fixesFactors || ws.fixesDrivers || 'Governance SLA';
      if (Array.isArray(fixes)) fixes = fixes.join(', ');
      executionWorkstreams.push({
        id: ws.id || `W${i + 1}`,
        remediationStep: ws.step || ws.remediationStep || ws.title || '',
        fixesDrivers: String(fixes)
      });
    }
  }

  const totHours = rawPlan.totalHours || rawPlan.totalEffortHours || (
    specialistManpower.reduce((acc, r) => {
      const num = parseInt(r.effort, 10);
      return acc + (isNaN(num) ? 0 : num);
    }, 0) || 60
  );
  const durWeeks = rawPlan.durationWeeks || rawPlan.timeline || 5;
  const timelineStr = typeof durWeeks === 'number' || !String(durWeeks).includes('Week') ? `${durWeeks} Weeks` : String(durWeeks);
  const effortStr = typeof totHours === 'number' || !String(totHours).includes('Hour') ? `${totHours} Total Hours` : String(totHours);

  const assumptionsAndRisks = rawPlan.assumptionsAndRisks || rep.assumptionsAndRisks || rawData.assumptionsAndRisks || [];
  const successCriteria = rawPlan.successCriteria || rep.successCriteria || rawData.successCriteria || [];
  const targetOutcome = (
    rawPlan.targetOutcome ||
    rootCause ||
    (rep.diagnosis && rep.diagnosis.headline) ||
    'Achieve standard compliance across all process stages.'
  );

  const rawBiz = rep.businessImpact || rawData.businessImpact || rep.business_impact || rawData.business_impact || {};
  const businessImpact = {
    overview: rawBiz.overview || rep.howItEffects || rawData.howItEffects || '',
    financialExposure: rawBiz.financialExposure || rawBiz.financial_exposure || '',
    slaAndTurnaround: rawBiz.slaAndTurnaround || rawBiz.sla_and_turnaround || '',
    governanceAndAudit: rawBiz.governanceAndAudit || rawBiz.governance_and_audit || ''
  };

  const normalizedBrd = {
    ...rawPlan,
    phases: rawPhases,
    roles: rawRoles,
    specialistManpower: specialistManpower.length > 0 ? specialistManpower : (rawPlan.specialistManpower || []),
    phasedActivities: phasedActivities.length > 0 ? phasedActivities : (rawPlan.phasedActivities || []),
    executionWorkstreams: executionWorkstreams.length > 0 ? executionWorkstreams : (rawPlan.executionWorkstreams || []),
    stageDrivers,
    segmentDrivers,
    assumptionsAndRisks: Array.isArray(assumptionsAndRisks) ? assumptionsAndRisks : [assumptionsAndRisks],
    successCriteria: Array.isArray(successCriteria) ? successCriteria : [successCriteria],
    timelineAndEffort: {
      timeline: timelineStr,
      totalEffort: effortStr
    },
    timeline: timelineStr,
    totalEffortHours: totHours,
    totalEffortsDisplay: effortStr,
    targetOutcome
  };

  return {
    metric: {
      code: metricCode,
      metric: metricName || metricCode,
      category: rawData.category || 'Operational Quality',
      company: String(companyVal),
      standard: String(standardVal),
      status: statusVal,
      variance: String(varianceVal),
      isSupabaseLive: true,
      _source: rawData._source || 'supabase',
      diagnosis: diagObj,
      suggestions: suggestionsList,
      businessImpact,
      moduleOverview: modOverviewObj,
      detailedAnalysis: {
        headline: headlineText,
        whyItHappens: narrativeText || rootCause || modOverviewObj.rootCause,
        whereItHappens: affectedArea || modOverviewObj.affectedArea,
        howToOvercome: suggestionsList,
        trendAnalysis: rep.trendAnalysis || rawData.trendAnalysis || {},
        missingConfigurations: rawData.missingConfigurations || [],
        howItEffects: businessImpact.overview || rep.businessImpact?.overview || rawData.howItEffects || '',
        businessImpact
      }
    },
    diagnosis: diagObj,
    suggestions: suggestionsList,
    businessImpact,
    moduleOverview: modOverviewObj,
    brdPlan: normalizedBrd,
    stageDrivers,
    segmentDrivers,
    shapFactors,
    source: rawData._source || 'supabase',
    storagePath: rawData._storage_path || `report/latest/${metricCode}.json`
  };
}

function parseMetricDeepDivePayload(metricCode, metricName, raw) {
  return normalizeSupabaseInsightPayload(raw, metricCode, metricName);
}

export const apiService = {
  /**
   * Check if backend service is reachable and retrieve Supabase connection details
   */
  async checkHealth() {
    try {
      const rootUrl = BASE_URL.replace('/api/v1', '');
      const res = await fetchWithTimeout(`${rootUrl}/health`, { method: 'GET' }, 3000);
      if (!res.ok) return false;
      const data = await res.json();
      return data.status === 'HEALTHY' || data.status === 'ok';
    } catch {
      return false;
    }
  },

  /**
   * Detailed health check reporting backend status + Supabase bucket info
   */
  async checkHealthWithSupabase() {
    try {
      const rootUrl = BASE_URL.replace('/api/v1', '');
      const res = await fetchWithTimeout(`${rootUrl}/health`, { method: 'GET' }, 3000);
      if (!res.ok) {
        return { isConnected: false, supabaseConnected: false, bucketFiles: 0 };
      }
      const data = await res.json();
      const supa = data.supabase || {};
      return {
        isConnected: true,
        supabaseConnected: supa.configured && supa.status === 'connected',
        supabaseStatus: supa.status || 'unknown',
        bucketName: supa.bucket_name || 'ml-insights',
        folder: supa.folder || 'insights',
        bucketFiles: supa.files_count || 0,
        files: supa.files || []
      };
    } catch {
      return { isConnected: false, supabaseConnected: false, bucketFiles: 0 };
    }
  },

  /**
   * Inspect Supabase Storage bucket files directly
   */
  async getSupabaseStorageStatus() {
    try {
      const res = await fetchWithTimeout(`${BASE_URL}/insights/status`, { method: 'GET' }, 3000);
      if (!res.ok) return null;
      return await res.json();
    } catch (e) {
      console.warn('Failed to fetch Supabase storage status:', e.message);
      return null;
    }
  },

  /**
   * Seed test ML insights into Supabase bucket
   */
  async seedSupabaseBucket() {
    try {
      const res = await fetchWithTimeout(`${BASE_URL}/insights/seed-samples`, { method: 'POST' }, 5000);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch (e) {
      console.warn('Failed to seed Supabase bucket:', e.message);
      throw e;
    }
  },

  /**
   * Fetch all modules dynamically from FastAPI backend.
   * Backend queries Supabase (Storage + LLM_Reports) and populates live data or 'Not yet fetched'.
   */
  async getModules() {
    try {
      const res = await fetchWithTimeout(`${BASE_URL}/modules`, { method: 'GET' }, 8000);
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data) && data.length > 0) {
          return data;
        }
      }
    } catch (err) {
      console.warn('Backend /modules call failed, using default baseline:', err.message);
    }
    return SF_MODULES;
  },

  /**
   * Fetch a single module by ID
   */
  async getModuleDetails(moduleId) {
    try {
      const res = await fetchWithTimeout(`${BASE_URL}/modules/${encodeURIComponent(moduleId)}`, { method: 'GET' }, 8000);
      if (res.ok) {
        const data = await res.json();
        if (data && data.id) return data;
      }
    } catch (_) {}
    const allMods = await this.getModules();
    return allMods.find((m) => m.id.toLowerCase() === moduleId.toLowerCase()) || null;
  },

  /**
   * Fast parallel fallback directly to Supabase Storage if backend service is unreachable
   */
  async fetchDirectFromSupabase(metricCode, metricName = null, moduleId = null) {
    const sbUrl = APP_CONFIG.supabaseUrl;
    const sbKey = APP_CONFIG.supabaseKey;
    const bucket = APP_CONFIG.supabaseBucket || 'Insights and Reports';
    if (!sbUrl || !sbKey) return null;

    const headers = {
      apikey: sbKey,
      Authorization: `Bearer ${sbKey}`
    };

    const rawName = String(metricName || metricCode || '').trim();
    const cleanMetric = rawName.replace(/\s+/g, '').replace(/[-_]/g, '');
    const pascalMetric = rawName.replace(/(?:^\w|[A-Z]|\b\w)/g, (letter) => letter.toUpperCase()).replace(/[\s_-]+/g, '');
    const modId = moduleId ? String(moduleId).toUpperCase().trim() : '';

    const candidates = [
      modId ? `reports/latest/${modId}/${pascalMetric}.json` : null,
      modId ? `reports/latest/${modId}/${cleanMetric}.json` : null,
      `reports/latest/${pascalMetric}.json`
    ].filter(Boolean);

    // Run candidate fetches in parallel with fast 1.5s timeout instead of sequential loops
    try {
      const promises = candidates.map(async (p) => {
        try {
          const url = `${sbUrl}/storage/v1/object/authenticated/${encodeURIComponent(bucket)}/${p}`;
          const res = await fetchWithTimeout(url, { headers }, 1500);
          if (res.ok) {
            const raw = await res.json();
            if (raw && typeof raw === 'object') {
              return parseMetricDeepDivePayload(metricCode, metricName, raw);
            }
          }
        } catch (_) {}
        return null;
      });

      const results = await Promise.all(promises);
      const found = results.find(Boolean);
      if (found) return found;
    } catch (_) {}

    return null;
  },

  /**
   * Fetch 8-section BRD deep dive and tree insights for a specific metric directly from backend
   */
  async getMetricDeepDive(metricCode, metricName = null, moduleId = null) {
    let backendData = null;
    try {
      const params = new URLSearchParams();
      if (metricName) params.append('metric_name', metricName);
      if (moduleId) params.append('module_id', moduleId);
      const queryStr = params.toString() ? `?${params.toString()}` : '';

      const res = await fetchWithTimeout(
        `${BASE_URL}/metrics/${encodeURIComponent(metricCode)}/deep-dive${queryStr}`,
        { method: 'GET' },
        5000
      );
      if (res.ok) {
        const data = await res.json();
        if (data && data.metric) {
          backendData = data;
        }
      }
    } catch (err) {
      console.warn(`Failed to fetch deep dive for ${metricCode} from backend:`, err.message);
    }

    // Backend is the authoritative source for Supabase data — return immediately!
    if (backendData && backendData.metric) {
      return backendData;
    }

    // Direct Supabase live fallback ONLY if backend server was completely offline/unreachable
    try {
      const directData = await this.fetchDirectFromSupabase(metricCode, metricName, moduleId);
      if (directData && directData.metric) {
        return directData;
      }
    } catch (directErr) {
      console.warn('Direct Supabase fetch fallback warning:', directErr);
    }

    // Strict fallback for unfetched metrics: NO mock data!
    return {
      metric: {
        code: metricCode,
        metric: metricName || metricCode,
        category: 'Operational KPI',
        company: 'Not yet fetched',
        standard: 'Not yet fetched',
        status: 'Not yet fetched',
        variance: 'Not yet fetched',
        isSupabaseLive: false,
        _source: 'static_baseline',
        moduleOverview: {
          rootCause: 'Data not yet fetched from Supabase',
          affectedArea: 'Data not yet fetched from Supabase',
          suggestions: []
        },
        detailedAnalysis: {
          whyItHappens: 'Data not yet fetched from Supabase',
          whereItHappens: 'Data not yet fetched from Supabase',
          trendAnalysis: { summary: 'Data not yet fetched from Supabase', points: [] },
          missingConfigurations: [],
          howItEffects: 'Data not yet fetched from Supabase',
          howToOvercome: []
        }
      },
      moduleOverview: {
        rootCause: 'Data not yet fetched from Supabase',
        affectedArea: 'Data not yet fetched from Supabase',
        suggestions: []
      },
      stageDrivers: [],
      segmentDrivers: [],
      shapFactors: [],
      missingConfigurations: [],
      brdPlan: {
        specialistManpower: [],
        phasedActivities: [],
        executionWorkstreams: [],
        stageDrivers: [],
        segmentDrivers: [],
        assumptionsAndRisks: [],
        successCriteria: [],
        timeline: 'Not yet fetched',
        totalEffortHours: 0,
        totalEffortsDisplay: 'Not yet fetched',
        timelineAndEffort: { timeline: 'Not yet fetched', totalEffort: 'Not yet fetched' },
        targetOutcome: 'Data not yet fetched from Supabase'
      }
    };
  },

  /**
   * Test SAP SuccessFactors OData handshake
   */
  async testConnection({ datacenter, companyId, username, password, clientId, clientSecret }) {
    const res = await fetchWithTimeout(`${BASE_URL}/connect/test`, {
      method: 'POST',
      body: JSON.stringify({
        datacenter,
        companyId,
        username,
        password: password || '',
        clientId: clientId || '',
        clientSecret: clientSecret || ''
      })
    });
    if (!res.ok) {
      const errJson = await res.json().catch(() => ({}));
      throw new Error(errJson.detail || `Connection test failed (HTTP ${res.status})`);
    }
    return await res.json();
  },

  /**
   * Upload custom standards map to backend
   */
  async uploadCustomStandards(standardsMap, uploadedBy = 'enterprise_admin') {
    const res = await fetchWithTimeout(`${BASE_URL}/standards/upload`, {
      method: 'POST',
      body: JSON.stringify({
        standards: standardsMap,
        uploadedBy
      })
    });
    if (!res.ok) {
      const errJson = await res.json().catch(() => ({}));
      throw new Error(errJson.detail || `Upload failed (HTTP ${res.status})`);
    }
    return await res.json();
  },

  /**
   * Trigger Analytics & ML calculation pipeline
   */
  async triggerMlPipeline(moduleId = null, forceRefreshAllLlms = false) {
    try {
      const res = await fetchWithTimeout(`${BASE_URL}/pipeline/trigger-ml-run`, {
        method: 'POST',
        body: JSON.stringify({
          module_id: moduleId,
          force_refresh_all_llms: forceRefreshAllLlms
        })
      }, 2500);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch (err) {
      console.warn('Backend ML trigger fallback to simulated pipeline:', err.message);
      return { status: 'success', simulated: true };
    }
  }
};

export default apiService;
