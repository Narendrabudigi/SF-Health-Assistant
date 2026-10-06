import { APP_CONFIG } from '../config/env';
import { SF_MODULES } from '../data/modulesData';

const BASE_URL = APP_CONFIG.apiBaseUrl || 'http://localhost:8000/api/v1';

/**
 * Helper to execute fetch with timeout
 */
async function fetchWithTimeout(resource, options = {}, timeoutMs = 8000) {
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

      let companyVal = b.company;
      if (!companyVal || companyVal === '0%') {
        companyVal = defaultB?.company || b.company || '0%';
      }

      let standardVal = b.standard;
      if (!standardVal || standardVal === '≥ 90.0%') {
        standardVal = defaultB?.standard || b.standard || '≥ 90.0%';
      }

      let varianceVal = b.variance;
      if (!varianceVal || varianceVal === '0%') {
        varianceVal = defaultB?.variance || b.variance || '0%';
      }

      let statusVal = normalizeStatus(b.status, varianceVal);
      if (b.status && (b.status.toLowerCase() === 'succeeded' || b.status.toLowerCase() === 'completed')) {
        if (defaultB && defaultB.status) {
          statusVal = defaultB.status;
        } else {
          statusVal = normalizeStatus(null, varianceVal);
        }
      }

      // Check if this metric is live from Supabase Storage or Table
      const isFromSupabase = Boolean(
        b._source === 'supabase_storage_metric_folder' ||
        b._source === 'supabase_llm_reports_table' ||
        b._source === 'supabase' ||
        b._storage_path ||
        b.isSupabaseLive
      );

      // Direct extraction of moduleOverview if provided in Supabase JSON
      const overview = (
        b.moduleOverview ||
        extractSectionValue(b, 'moduleOverview', 'module_overview', 'overview') ||
        {}
      );

      const liveRootCause = (
        extractSectionValue(overview, 'rootCause', 'root_cause') ||
        extractSectionValue(b, 'rootCause', 'root_cause') ||
        b.whyItHappens
      );

      const liveAffectedArea = (
        extractSectionValue(overview, 'affectedArea', 'affected_area') ||
        extractSectionValue(b, 'affectedArea', 'affected_area') ||
        b.whereItHappens
      );

      const rawLiveSuggestions = (
        (overview.suggestions && overview.suggestions.length > 0 ? overview.suggestions : null) ||
        (b.moduleOverview?.suggestions && b.moduleOverview.suggestions.length > 0 ? b.moduleOverview.suggestions : null) ||
        extractSectionValue(overview, 'suggestions') ||
        extractSectionValue(b, 'suggestions') ||
        (isFromSupabase ? b.howToOvercome : null)
      );
      const liveSuggestions = Array.isArray(rawLiveSuggestions)
        ? rawLiveSuggestions
        : (typeof rawLiveSuggestions === 'string' ? [rawLiveSuggestions] : (rawLiveSuggestions ? [rawLiveSuggestions] : null));

      const finalWhyItHappens = liveRootCause || defaultB?.detailedAnalysis?.whyItHappens || 'Diagnostic variance detected against benchmark standard.';
      const finalWhereItHappens = liveAffectedArea || defaultB?.detailedAnalysis?.whereItHappens || `${category} processes within ${modName}.`;
      const finalSuggestions = liveSuggestions !== null ? liveSuggestions : (defaultB?.detailedAnalysis?.howToOvercome || []);

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
        _source: isFromSupabase ? 'supabase_storage_metric_folder' : 'static_baseline',
        isSupabaseLive: isFromSupabase,
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
            _source: 'static_baseline',
            isSupabaseLive: false
          });
        }
      }
    }

    const critCount = mergedBenchmarks.filter(b => b.status === 'Critical').length;
    const atRiskCount = mergedBenchmarks.filter(b => b.status === 'At Risk').length;
    const healthyCount = mergedBenchmarks.filter(b => b.status === 'Healthy').length;

    let computedModuleStatus = 'Healthy';
    if (critCount > 0) computedModuleStatus = 'Critical';
    else if (atRiskCount > 0) computedModuleStatus = 'At Risk';

    return {
      ...defaultMod,
      ...rawMod,
      id: modId,
      name: modName,
      status: computedModuleStatus,
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
  const prefixes = ['report/latest', 'reports/latest', 'latest'];

  const rawName = String(metricName || '').replace('.json', '').trim();
  const alphaName = normalizeAlphaKey(rawName);
  const snakeName = rawName.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
  const pascalName = rawName.replace(/(?:^\w|[A-Z]|\b\w)/g, (letter) => letter.toUpperCase()).replace(/[\s_-]+/g, '');

  const metricAliases = Array.from(new Set([rawName, alphaName, snakeName, pascalName])).filter(Boolean);

  const candidateUrls = [];
  for (const p of prefixes) {
    for (const f of folders) {
      for (const m of metricAliases) {
        candidateUrls.push(`${APP_CONFIG.supabaseUrl}/storage/v1/object/authenticated/${encodeURIComponent(bucket)}/${p}/${f}/${m}.json`);
        candidateUrls.push(`${APP_CONFIG.supabaseUrl}/storage/v1/object/authenticated/${encodeURIComponent(bucket)}/${p}/${f}/${m}/report.json`);
        candidateUrls.push(`${APP_CONFIG.supabaseUrl}/storage/v1/object/authenticated/${encodeURIComponent(bucket)}/${p}/${f}/${m}/data.json`);
        candidateUrls.push(`${APP_CONFIG.supabaseUrl}/storage/v1/object/authenticated/${encodeURIComponent(bucket)}/${p}/${f}/${m}/${m}.json`);
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

  const rep = (rawData.report && typeof rawData.report === 'object') ? rawData.report : rawData;
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

  const rawSug = (
    overview.suggestions ||
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

  const companyVal = rawData.company || rep.company || rawData.company_actual || rep.company_actual || '0%';
  const standardVal = rawData.standard || rep.standard || rawData.benchmark_target || rep.benchmark_target || '≥ 90.0%';
  const statusVal = normalizeStatus(rawData.status || rep.healthState || 'At Risk', String(rawData.variance || ''));
  const varianceVal = rawData.variance || rep.actual_variance || rawData.variance_percentage || '0%';

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

  // 2. Plan extraction
  const rawPlan = rep.plan || rep.brdPlan || rep.brd_plan || rawData.plan || rawData.brdPlan || {};

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
  const rawWs = rep.workstreams || rawData.workstreams || rawPlan.executionWorkstreams || rawPlan.workstreams || [];
  const executionWorkstreams = [];
  if (Array.isArray(rawWs) && rawWs.length > 0) {
    for (let i = 0; i < rawWs.length; i++) {
      const ws = rawWs[i];
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

  const normalizedBrd = {
    ...rawPlan,
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
      moduleOverview: modOverviewObj,
      detailedAnalysis: {
        whyItHappens: rootCause || modOverviewObj.rootCause,
        whereItHappens: affectedArea || modOverviewObj.affectedArea,
        howToOvercome: suggestionsList,
        trendAnalysis: rep.trendAnalysis || rawData.trendAnalysis || {},
        missingConfigurations: rawData.missingConfigurations || [],
        howItEffects: rep.businessImpact?.overview || rawData.howItEffects || ''
      }
    },
    moduleOverview: modOverviewObj,
    brdPlan: normalizedBrd,
    stageDrivers,
    segmentDrivers,
    shapFactors,
    source: rawData._source || 'supabase',
    storagePath: rawData._storage_path || `report/latest/${metricCode}.json`
  };
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
   * Fetch all modules directly with benchmarks populated from Backend and Supabase
   */
  async getModules() {
    try {
      // 1. Fetch live LLM_Reports table rows directly from Supabase
      const tableRows = await fetchDirectSupabaseTable('LLM_Reports');

      // 2. Also fetch direct storage metric for RCM/TimeToHire
      const liveRcmData = await fetchDirectSupabaseStorageMetric('RCM', 'TimeToHire');

      // 3. Query backend /modules endpoint
      const res = await fetchWithTimeout(`${BASE_URL}/modules?refresh=true`, { method: 'GET' }, 10000);
      let rawModules = SF_MODULES;
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data) && data.length > 0) {
          rawModules = data;
        }
      }

      // Merge direct Supabase table rows into rawModules benchmarks!
      if (Array.isArray(tableRows) && tableRows.length > 0) {
        for (const row of tableRows) {
          const modKey = (row.module || '').toLowerCase().trim();
          const targetMod = rawModules.find(m => m.id === modKey || normalizeAlphaKey(m.name) === normalizeAlphaKey(row.module));
          if (targetMod && Array.isArray(targetMod.benchmarks)) {
            const b = targetMod.benchmarks.find(item => 
              normalizeAlphaKey(item.metric) === normalizeAlphaKey(row.metric_name) ||
              normalizeAlphaKey(item.code) === normalizeAlphaKey(row.metric_name)
            );
            if (b) {
              const rep = row.report || row;
              const ov = row.moduleOverview || row.module_overview || rep.moduleOverview || rep.module_overview || {};
              const rc = ov.rootCause || ov.root_cause || row.rootCause;
              const aa = ov.affectedArea || ov.affected_area || row.affectedArea;
              const sug = ov.suggestions || row.suggestions;
              const sugList = Array.isArray(sug) ? sug : (typeof sug === 'string' ? [sug] : (sug ? [sug] : []));

              if (rc) {
                b.whyItHappens = rc;
                if (b.detailedAnalysis) b.detailedAnalysis.whyItHappens = rc;
              }
              if (aa) {
                b.whereItHappens = aa;
                if (b.detailedAnalysis) b.detailedAnalysis.whereItHappens = aa;
              }
              if (sugList.length > 0) {
                b.howToOvercome = sugList;
                if (b.detailedAnalysis) b.detailedAnalysis.howToOvercome = sugList;
              }

              b.moduleOverview = {
                rootCause: rc || b.whyItHappens,
                affectedArea: aa || b.whereItHappens,
                suggestions: sugList.length > 0 ? sugList : (b.howToOvercome || [])
              };

              if (row.company || rep.company) b.company = String(row.company || rep.company);
              if (row.standard || rep.standard) b.standard = String(row.standard || rep.standard);
              if (row.status || rep.healthState) b.status = row.status || rep.healthState;
              if (row.variance || rep.actual_variance) b.variance = String(row.variance || rep.actual_variance);

              b.isSupabaseLive = true;
              b._source = 'supabase_llm_reports_table';
            }
          }
        }
      }

      // Merge direct storage data if available
      if (liveRcmData) {
        const rcmMod = rawModules.find(m => m.id === 'rcm');
        if (rcmMod && Array.isArray(rcmMod.benchmarks)) {
          const tth = rcmMod.benchmarks.find(b => normalizeAlphaKey(b.metric) === 'timetohire' || normalizeAlphaKey(b.code) === 'timetohire');
          if (tth) {
            const rep = liveRcmData.report || liveRcmData;
            const overview = liveRcmData.moduleOverview || liveRcmData.module_overview || rep.moduleOverview || rep.module_overview || {};
            const rc = overview.rootCause || overview.root_cause || extractSectionValue(liveRcmData, 'rootCause', 'root_cause');
            const aa = overview.affectedArea || overview.affected_area || extractSectionValue(liveRcmData, 'affectedArea', 'affected_area');
            const sug = overview.suggestions || extractSectionValue(liveRcmData, 'suggestions');
            const sugList = Array.isArray(sug) ? sug : (typeof sug === 'string' ? [sug] : (sug ? [sug] : []));

            if (rc) {
              tth.whyItHappens = rc;
              if (tth.detailedAnalysis) tth.detailedAnalysis.whyItHappens = rc;
            }
            if (aa) {
              tth.whereItHappens = aa;
              if (tth.detailedAnalysis) tth.detailedAnalysis.whereItHappens = aa;
            }
            if (sugList.length > 0) {
              tth.howToOvercome = sugList;
              if (tth.detailedAnalysis) tth.detailedAnalysis.howToOvercome = sugList;
            }

            tth.moduleOverview = {
              rootCause: rc || tth.whyItHappens,
              affectedArea: aa || tth.whereItHappens,
              suggestions: sugList.length > 0 ? sugList : (tth.howToOvercome || [])
            };

            if (liveRcmData.company || rep.company || liveRcmData.company_actual || rep.company_actual) {
              tth.company = String(liveRcmData.company || rep.company || liveRcmData.company_actual || rep.company_actual);
            }
            if (liveRcmData.standard || rep.standard || liveRcmData.benchmark_target || rep.benchmark_target) {
              tth.standard = String(liveRcmData.standard || rep.standard || liveRcmData.benchmark_target || rep.benchmark_target);
            }
            if (liveRcmData.status || rep.healthState) {
              tth.status = liveRcmData.status || rep.healthState;
            }
            if (liveRcmData.variance || rep.actual_variance || liveRcmData.variance_percentage) {
              tth.variance = String(liveRcmData.variance || rep.actual_variance || liveRcmData.variance_percentage);
            }

            tth.isSupabaseLive = true;
            tth._source = 'supabase_storage_metric_folder';
          }
        }
      }

      return sanitizeAndMergeModules(rawModules);
    } catch (err) {
      console.warn('Backend unavailable, falling back to local dataset:', err.message);
      return SF_MODULES;
    }
  },

  /**
   * Fetch a single module by ID
   */
  async getModuleDetails(moduleId) {
    try {
      const res = await fetchWithTimeout(`${BASE_URL}/modules/${moduleId}`, { method: 'GET' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const raw = await res.json();
      const sanitizedList = sanitizeAndMergeModules([raw]);
      return sanitizedList[0] || null;
    } catch (err) {
      console.warn(`Failed to fetch module ${moduleId} from API:`, err.message);
      return SF_MODULES.find((m) => m.id === moduleId) || null;
    }
  },

  /**
   * Fetch 9-section BRD deep dive and TreeSHAP insights for a specific metric
   */
  async getMetricDeepDive(metricCode, metricName = null, moduleId = null) {
    try {
      const targetMod = moduleId || 'rcm';
      const targetMetric = metricName || metricCode;

      // 1. Query direct Supabase LLM_Reports table
      const tableRows = await fetchDirectSupabaseTable('LLM_Reports');
      let matchedRow = null;
      if (Array.isArray(tableRows) && tableRows.length > 0) {
        matchedRow = tableRows.find(r => {
          const mRow = normalizeAlphaKey(r.metric_name || r.metric || '');
          const targetAlpha = normalizeAlphaKey(targetMetric);
          const codeAlpha = normalizeAlphaKey(metricCode);
          return mRow === targetAlpha || mRow === codeAlpha || (mRow && targetAlpha.includes(mRow));
        });
      }

      // 2. Query direct Supabase Storage
      const directSupaStorage = await fetchDirectSupabaseStorageMetric(targetMod, targetMetric);

      // Combine Supabase table row and storage data (prioritizing moduleOverview)
      let bestSupabaseData = null;
      if (directSupaStorage && matchedRow) {
        const curOverview = directSupaStorage.moduleOverview || directSupaStorage.report?.moduleOverview;
        bestSupabaseData = { ...matchedRow, ...directSupaStorage };
        if (curOverview) {
          bestSupabaseData.moduleOverview = curOverview;
        }
      } else if (directSupaStorage) {
        bestSupabaseData = directSupaStorage;
      } else if (matchedRow) {
        bestSupabaseData = matchedRow;
      }

      // 3. Query backend endpoint
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
          backendData = await res.json();
        }
      } catch (err) {
        console.warn(`Backend deep dive fetch failed:`, err.message);
      }

      // Normalize direct Supabase data if available
      const normalizedLive = bestSupabaseData
        ? normalizeSupabaseInsightPayload(bestSupabaseData, metricCode, targetMetric)
        : null;

      if (backendData && normalizedLive) {
        // Merge backend structure enriched with live Supabase text & brdPlan
        return {
          ...backendData,
          ...normalizedLive,
          metric: {
            ...backendData.metric,
            ...normalizedLive.metric,
            moduleOverview: normalizedLive.moduleOverview || backendData.moduleOverview,
            detailedAnalysis: {
              ...backendData.metric?.detailedAnalysis,
              ...normalizedLive.metric?.detailedAnalysis
            }
          },
          moduleOverview: normalizedLive.moduleOverview || backendData.moduleOverview,
          stageDrivers: (normalizedLive.stageDrivers && normalizedLive.stageDrivers.length > 0)
            ? normalizedLive.stageDrivers
            : backendData.stageDrivers,
          segmentDrivers: (normalizedLive.segmentDrivers && normalizedLive.segmentDrivers.length > 0)
            ? normalizedLive.segmentDrivers
            : backendData.segmentDrivers,
          shapFactors: (normalizedLive.shapFactors && normalizedLive.shapFactors.length > 0)
            ? normalizedLive.shapFactors
            : backendData.shapFactors,
          brdPlan: {
            ...backendData.brdPlan,
            ...normalizedLive.brdPlan
          }
        };
      }

      if (normalizedLive) return normalizedLive;
      if (backendData) return backendData;
      return null;
    } catch (err) {
      console.warn(`Failed to fetch deep dive for ${metricCode}:`, err.message);
      return null;
    }
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
