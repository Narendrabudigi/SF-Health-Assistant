import { APP_CONFIG } from '../config/env';
import { SF_MODULES } from '../data/modulesData';

const BASE_URL =
  APP_CONFIG.apiBaseUrl || 'http://localhost:8000/api/v1';

/* =========================================================
   FETCH HELPERS
========================================================= */

async function fetchWithTimeout(
  resource,
  options = {},
  timeoutMs = 20000
) {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);

  try {
    return await fetch(resource, {
      ...options,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...(options.headers || {})
      }
    });
  } finally {
    clearTimeout(id);
  }
}

const CANONICAL_MODULE_NAMES = {
  ec: 'Employee Central',
  rcm: 'Recruitment',
  onb: 'Onboarding',
  ofb: 'Offboarding',
  ecp: 'Employee Central Payroll'
};

/* =========================================================
   METRIC NORMALIZATION AND DUPLICATE PREVENTION
========================================================= */

/**
 * Normalizes metric identifiers.
 *
 * These identifiers all map to the same metric:
 * TTH
 * Time to Hire
 * TimeToHire
 * TimeToHireTTH
 * TimeHire
 *
 * IMPORTANT:
 * Only map aliases here when they represent the same business metric.
 */
function normalizeAlphaKey(text) {
  if (!text) return '';

  const clean = String(text).replace(/\(.*?\)/g, '');

  const key = clean
    .replace(/[^a-zA-Z0-9]/g, '')
    .toLowerCase();

  const aliases = {
    tth: 'timetohire',
    timetohire: 'timetohire',
    timetohiretth: 'timetohire',
    timehire: 'timetohire',
    timetohiremetric: 'timetohire'
  };

  return aliases[key] || key;
}

/**
 * Detect placeholders without treating a genuine zero as missing.
 */
function isMissingMetricValue(value) {
  if (value === null || value === undefined) {
    return true;
  }

  const text = String(value).trim().toLowerCase();

  return [
    '',
    'n/a',
    'na',
    'n/a (data gap)',
    'not available',
    'not yet fetched',
    'data not yet fetched',
    'data not yet fetched from supabase',
    '--',
    '-',
    'null',
    'none'
  ].includes(text);
}

/**
 * Determine whether a payload contains usable information.
 */
function hasUsableData(value, seen = new WeakSet()) {
  if (value === null || value === undefined) {
    return false;
  }

  if (typeof value === 'string') {
    return value.trim().length > 0;
  }

  if (typeof value === 'number') {
    return Number.isFinite(value);
  }

  if (typeof value === 'boolean') {
    return true;
  }

  if (Array.isArray(value)) {
    return value.some((item) => hasUsableData(item, seen));
  }

  if (typeof value === 'object') {
    if (seen.has(value)) {
      return false;
    }

    seen.add(value);

    return Object.values(value).some((item) =>
      hasUsableData(item, seen)
    );
  }

  return false;
}

function firstUsableValue(...values) {
  return values.find((value) => hasUsableData(value));
}

/**
 * Extract actual missing field names.
 *
 * This helper is also useful for the data-gap count.
 */
function getMetricMissingFields(metric) {
  if (!metric || typeof metric !== 'object') {
    return [];
  }

  const candidates = [
    metric.missingConfigurations,
    metric.missingConfiguration,
    metric.detailedAnalysis?.missingConfigurations,
    metric.detailedAnalysis?.missingConfiguration,
    metric.dataQuality?.missingFields
  ];

  for (const candidate of candidates) {
    if (Array.isArray(candidate) && candidate.length > 0) {
      return normalizeMissingFieldList(candidate);
    }

    if (typeof candidate === 'string' && candidate.trim()) {
      return normalizeMissingFieldList(
        candidate.split(',')
      );
    }
  }

  const checks = metric.dataQuality?.checks;

  if (Array.isArray(checks)) {
    return normalizeMissingFieldList(
      checks.flatMap((check) => {
        const category = String(check?.category || '').toLowerCase();
        const checkName = String(check?.checkName || check?.name || '').toLowerCase();
        const reportsMissingData =
          ['completeness', 'schema', 'missingvalues'].includes(category) ||
          ['completeness', 'schema', 'missingvalues'].includes(checkName);

        return reportsMissingData && Array.isArray(check?.affectedColumns)
          ? check.affectedColumns
          : [];
      })
    );
  }

  return [];
}

function normalizeMissingFieldList(fields) {
  if (!Array.isArray(fields)) {
    return [];
  }

  const unique = new Map();

  for (const field of fields) {
    let name = '';

    if (typeof field === 'string') {
      name = field.trim();
    } else if (field && typeof field === 'object') {
      name = String(
        field.field ||
        field.fieldName ||
        field.name ||
        field.column ||
        field.columnName ||
        ''
      ).trim();
    }

    if (name && !unique.has(name.toLowerCase())) {
      unique.set(name.toLowerCase(), name);
    }
  }

  return Array.from(unique.values());
}

/**
 * Merge duplicate metric records while preserving available data.
 *
 * A populated company value replaces N/A or Not yet fetched.
 * An existing valid standard is retained.
 * Missing field names are taken from the record with the
 * more complete missing-field information.
 */
function mergeDuplicateMetric(existing, incoming) {
  const existingCompanyMissing =
    isMissingMetricValue(existing.company);

  const incomingCompanyMissing =
    isMissingMetricValue(incoming.company);

  // Prefer a real company value over a placeholder.
  if (existingCompanyMissing && !incomingCompanyMissing) {
    existing.company = incoming.company;
  }

  // Fill other values only if the current record is missing them.
  if (isMissingMetricValue(existing.standard)) {
    if (!isMissingMetricValue(incoming.standard)) {
      existing.standard = incoming.standard;
    }
  }

  if (isMissingMetricValue(existing.variance)) {
    if (!isMissingMetricValue(incoming.variance)) {
      existing.variance = incoming.variance;
    }
  }

  if (isMissingMetricValue(existing.status)) {
    if (!isMissingMetricValue(incoming.status)) {
      existing.status = incoming.status;
    }
  }

  existing.confidenceScore =
    existing.confidenceScore ??
    incoming.confidenceScore ??
    null;

  existing.diagnosis = {
    ...(incoming.diagnosis || {}),
    ...(existing.diagnosis || {})
  };

  existing.moduleOverview = {
    ...(incoming.moduleOverview || {}),
    ...(existing.moduleOverview || {})
  };

  const existingDetails =
    existing.detailedAnalysis || {};

  const incomingDetails =
    incoming.detailedAnalysis || {};

  existing.detailedAnalysis = {
    ...incomingDetails,
    ...existingDetails
  };

  const currentGaps = getMetricMissingFields(existing);
  const incomingGaps = getMetricMissingFields(incoming);

  if (incomingGaps.length > currentGaps.length) {
    existing.missingConfigurations = incomingGaps;

    existing.detailedAnalysis = {
      ...existing.detailedAnalysis,
      missingConfigurations: incomingGaps
    };
  } else if (currentGaps.length > 0) {
    existing.missingConfigurations = currentGaps;

    existing.detailedAnalysis = {
      ...existing.detailedAnalysis,
      missingConfigurations: currentGaps
    };
  }

  if (
    incoming.isSupabaseLive ||
    incoming._storage_path ||
    incoming._source
  ) {
    existing._source =
      incoming._source || existing._source;

    existing.isSupabaseLive = Boolean(
      existing.isSupabaseLive ||
      incoming.isSupabaseLive
    );
  }

  return existing;
}

/* =========================================================
   STATUS NORMALIZATION
========================================================= */

function normalizeStatus(status) {
  const s = String(status || '').toLowerCase().trim().replace(/[_-]+/g, ' ');

  if (/^(?:n\s*\/\s*a|na)$/.test(s)) {
    return 'Process Gaps';
  }

  if (s.includes('crit')) {
    return 'Critical';
  }

  if (
    s.includes('risk') ||
    s.includes('warn') ||
    s.includes('breach')
  ) {
    return 'At Risk';
  }

  if (s.includes('healthy') || s.includes('on track') || s.includes('on target') || s === 'good' || s === 'ok') {
    return 'Healthy';
  }
  return 'Not yet fetched';
}

/* =========================================================
   MODULE AND BENCHMARK MERGING
========================================================= */

function sanitizeAndMergeModules(rawModules) {
  if (!Array.isArray(rawModules) || rawModules.length === 0) {
    return SF_MODULES;
  }

  const defaultModulesMap = new Map();

  SF_MODULES.forEach((mod) => {
    defaultModulesMap.set(
      String(mod.id || '').toLowerCase(),
      mod
    );
  });

  return rawModules.map((rawMod) => {
    const modId = String(rawMod.id || '').toLowerCase();

    const defaultMod = defaultModulesMap.get(modId);

    const modName =
      CANONICAL_MODULE_NAMES[modId] ||
      defaultMod?.name ||
      rawMod.name ||
      'Module';

    const defaultBenchmarkMap = new Map();

    if (defaultMod && Array.isArray(defaultMod.benchmarks)) {
      defaultMod.benchmarks.forEach((benchmark) => {
        const metricKey = normalizeAlphaKey(
          benchmark.metric
        );

        const codeKey = normalizeAlphaKey(
          benchmark.code
        );

        if (metricKey) {
          defaultBenchmarkMap.set(
            metricKey,
            benchmark
          );
        }

        if (codeKey) {
          defaultBenchmarkMap.set(
            codeKey,
            benchmark
          );
        }
      });
    }

    const mergedBenchmarks = [];
    const seenAlphaKeys = new Set();

    const incomingBenchmarks = Array.isArray(rawMod.benchmarks)
      ? rawMod.benchmarks
      : [];

    for (const benchmark of incomingBenchmarks) {
      const alphaKey = normalizeAlphaKey(
        benchmark.metric || benchmark.code || ''
      );

      if (!alphaKey) {
        continue;
      }

      const defaultBenchmark =
        defaultBenchmarkMap.get(alphaKey);

      /*
       * DUPLICATE CHECK
       *
       * TTH and TimeToHireTTH both normalize to timetohire.
       * Therefore only one Time to Hire row is retained.
       */
      if (seenAlphaKeys.has(alphaKey)) {
        const existingIndex = mergedBenchmarks.findIndex(
          (item) =>
            normalizeAlphaKey(
              item.metric || item.code
            ) === alphaKey
        );

        if (existingIndex !== -1) {
          mergeDuplicateMetric(
            mergedBenchmarks[existingIndex],
            benchmark
          );
        }

        continue;
      }

      seenAlphaKeys.add(alphaKey);

      const metricName =
        defaultBenchmark?.metric ||
        benchmark.metric ||
        benchmark.code;

      const category =
        benchmark.category ||
        defaultBenchmark?.category ||
        'Operational KPI';

      const isFromSupabase = Boolean(
        benchmark._source === 'supabase_storage_metric_folder' ||
        benchmark._source === 'supabase_llm_reports_table' ||
        benchmark._source === 'supabase_ml_notebook_insights_table' ||
        benchmark._source === 'supabase_table' ||
        benchmark._source === 'supabase' ||
        benchmark._storage_path ||
        benchmark.isSupabaseLive ||
        !isMissingMetricValue(benchmark.company)
      );

      const companyVal = isFromSupabase
        ? (
            isMissingMetricValue(benchmark.company)
              ? 'Not yet fetched'
              : benchmark.company
          )
        : 'Not yet fetched';

      const standardVal = isFromSupabase
        ? (
            isMissingMetricValue(benchmark.standard)
              ? 'Not yet fetched'
              : benchmark.standard
          )
        : 'Not yet fetched';

      const varianceVal = isFromSupabase
        ? (
            isMissingMetricValue(benchmark.variance)
              ? 'Not yet fetched'
              : benchmark.variance
          )
        : 'Not yet fetched';

      let statusVal = isFromSupabase
        ? normalizeStatus(benchmark.status)
        : 'Not yet fetched';

      const overview =
        benchmark.moduleOverview ||
        extractSectionValue(
          benchmark,
          'moduleOverview',
          'module_overview',
          'overview'
        ) ||
        {};

      const liveRootCause =
        extractSectionValue(
          overview,
          'rootCause',
          'root_cause'
        ) ||
        extractSectionValue(
          benchmark,
          'rootCause',
          'root_cause'
        ) ||
        (
          isFromSupabase
            ? benchmark.whyItHappens
            : null
        );

      const liveAffectedArea =
        extractSectionValue(
          overview,
          'affectedArea',
          'affected_area'
        ) ||
        extractSectionValue(
          benchmark,
          'affectedArea',
          'affected_area'
        ) ||
        (
          isFromSupabase
            ? benchmark.whereItHappens
            : null
        );

      const rawWorkstreams =
        benchmark.workstreams ||
        overview.workstreams ||
        [];

      let workstreamSteps = [];

      if (
        Array.isArray(rawWorkstreams) &&
        rawWorkstreams.length > 0
      ) {
        workstreamSteps = rawWorkstreams
          .filter(
            (workstream) =>
              workstream &&
              (
                workstream.step ||
                workstream.remediationStep ||
                workstream.title
              ) &&
              workstream.kind !== 'data'
          )
          .map(
            (workstream) =>
              workstream.step ||
              workstream.remediationStep ||
              workstream.title
          );

        if (workstreamSteps.length === 0) {
          workstreamSteps = rawWorkstreams
            .filter(
              (workstream) =>
                workstream &&
                (
                  workstream.step ||
                  workstream.remediationStep ||
                  workstream.title
                )
            )
            .map(
              (workstream) =>
                workstream.step ||
                workstream.remediationStep ||
                workstream.title
            );
        }
      }

      const rawSuggestions =
        (
          workstreamSteps.length > 0
            ? workstreamSteps
            : null
        ) ||
        (
          Array.isArray(overview.suggestions) &&
          overview.suggestions.length > 0
            ? overview.suggestions
            : null
        ) ||
        (
          Array.isArray(
            benchmark.moduleOverview?.suggestions
          ) &&
          benchmark.moduleOverview.suggestions.length > 0
            ? benchmark.moduleOverview.suggestions
            : null
        ) ||
        (
          Array.isArray(benchmark.suggestions) &&
          benchmark.suggestions.length > 0
            ? benchmark.suggestions
            : null
        ) ||
        extractSectionValue(
          overview,
          'suggestions'
        ) ||
        extractSectionValue(
          benchmark,
          'suggestions'
        ) ||
        (
          isFromSupabase
            ? benchmark.howToOvercome
            : null
        );

      const liveSuggestions = Array.isArray(rawSuggestions)
        ? rawSuggestions
        : (
            typeof rawSuggestions === 'string'
              ? [rawSuggestions]
              : rawSuggestions
                ? [rawSuggestions]
                : []
          );

      const finalWhyItHappens =
        liveRootCause ||
        (
          isFromSupabase
            ? benchmark.whyItHappens
            : null
        ) ||
        'Data not yet fetched';

      const finalWhereItHappens =
        liveAffectedArea ||
        (
          isFromSupabase
            ? benchmark.whereItHappens
            : null
        ) ||
        'Data not yet fetched';

      const finalModuleOverview = {
        rootCause:
          liveRootCause || finalWhyItHappens,

        affectedArea:
          liveAffectedArea || finalWhereItHappens,

        suggestions: liveSuggestions
      };

      const detailedAnalysis = {
        ...(defaultBenchmark?.detailedAnalysis || {}),
        ...(benchmark.detailedAnalysis || {}),

        whyItHappens: finalWhyItHappens,
        whereItHappens: finalWhereItHappens,

        howToOvercome: liveSuggestions
      };

      const gaps = getMetricMissingFields(benchmark);

      mergedBenchmarks.push({
        ...defaultBenchmark,
        ...benchmark,

        code:
          benchmark.code ||
          defaultBenchmark?.code ||
          `${modId}_${alphaKey}`,

        metric: metricName,
        category,

        company: companyVal,
        standard: standardVal,
        status: statusVal,
        variance: varianceVal,

        confidenceScore:
          benchmark.confidenceScore ??
          defaultBenchmark?.confidenceScore ??
          null,

        missingConfigurations: gaps,

        _source: isFromSupabase
          ? (benchmark._source || 'supabase_table')
          : 'static_baseline',

        isSupabaseLive: isFromSupabase,

        diagnosis:
          benchmark.diagnosis ||
          defaultBenchmark?.diagnosis ||
          {},

        moduleOverview: finalModuleOverview,
        detailedAnalysis
      });
    }

    /*
     * Add static fallback metrics only when a matching metric
     * has not already been received from the backend.
     */
    if (defaultMod && Array.isArray(defaultMod.benchmarks)) {
      for (const defaultBenchmark of defaultMod.benchmarks) {
        const key = normalizeAlphaKey(
          defaultBenchmark.metric || defaultBenchmark.code
        );

        if (!key || seenAlphaKeys.has(key)) {
          continue;
        }

        seenAlphaKeys.add(key);

        mergedBenchmarks.push({
          ...defaultBenchmark,

          company: 'Not yet fetched',
          standard:
            defaultBenchmark.standard || 'Not yet fetched',

          status: 'Not yet fetched',
          variance: 'Not yet fetched',

          confidenceScore: null,

          missingConfigurations: [],

          moduleOverview: {
            rootCause: 'Data not yet fetched',
            affectedArea: 'Data not yet fetched',
            suggestions: []
          },

          detailedAnalysis: {
            whyItHappens: 'Data not yet fetched',
            whereItHappens: 'Data not yet fetched',

            trendAnalysis: {
              summary: 'Data not yet fetched',
              points: []
            },

            missingConfigurations: [],

            howItEffects: 'Data not yet fetched',
            howToOvercome: []
          },

          _source: 'static_baseline',
          isSupabaseLive: false
        });
      }
    }

    const statusCounts = mergedBenchmarks.reduce((counts, benchmark) => {
      const status = normalizeStatus(benchmark.status);
      if (status === 'Critical') counts.critical += 1;
      else if (status === 'At Risk') counts.atRisk += 1;
      else if (status === 'Healthy') counts.healthy += 1;
      return counts;
    }, { critical: 0, atRisk: 0, healthy: 0 });

    const criticalCount = statusCounts.critical;
    const atRiskCount = statusCounts.atRisk;
    const healthyCount = statusCounts.healthy;

    const hasLive = mergedBenchmarks.some(
      (benchmark) => benchmark.isSupabaseLive
    );

    let computedModuleStatus = 'Not yet fetched';

    if (hasLive) {
      computedModuleStatus = [
        ['Critical', criticalCount],
        ['At Risk', atRiskCount],
        ['Healthy', healthyCount]
      ].reduce(
        (leader, [status, count]) => count > leader.count ? { status, count } : leader,
        {
          status: mergedBenchmarks.some((benchmark) =>
            benchmark.isSupabaseLive &&
            isMissingMetricValue(benchmark.company) &&
            getMetricMissingFields(benchmark).length > 0
          ) ? 'Process Gaps' : 'Not yet fetched',
          count: 0
        }
      ).status;
    }

    const computedAiReport = hasLive
      ? (
          rawMod.aiReport || {
            summary:
              `${modName} health status is ${computedModuleStatus}.`
          }
        )
      : {
          summary: 'Data not yet fetched.'
        };

    return {
      ...defaultMod,
      ...rawMod,

      id: modId,
      name: modName,

      status: computedModuleStatus,
      aiReport: computedAiReport,

      benchmarks: mergedBenchmarks,
      benchmarksCount: mergedBenchmarks.length,

      criticalCount,
      atRiskCount,
      healthyCount
    };
  });
}

/* =========================================================
   NESTED SECTION EXTRACTION
========================================================= */

function extractSectionValue(obj, ...candidateKeys) {
  if (!obj || typeof obj !== 'object') {
    return null;
  }

  const normalizedKeys = candidateKeys.map(
    (key) => key.toLowerCase().replace(/[_-]/g, '')
  );

  for (const [key, value] of Object.entries(obj)) {
    const normalizedKey = key
      .toLowerCase()
      .replace(/[_-]/g, '');

    if (
      normalizedKeys.includes(normalizedKey) &&
      value !== null &&
      value !== undefined &&
      value !== ''
    ) {
      return value;
    }
  }

  const containers = [
    'moduleOverview',
    'module_overview',
    'overview',
    'report',
    'detailedAnalysis',
    'detailed_analysis'
  ];

  for (const container of containers) {
    if (
      obj[container] &&
      typeof obj[container] === 'object' &&
      !Array.isArray(obj[container])
    ) {
      const result = extractSectionValue(
        obj[container],
        ...candidateKeys
      );

      if (
        result !== null &&
        result !== undefined &&
        result !== ''
      ) {
        return result;
      }
    }
  }

  for (const value of Object.values(obj)) {
    if (
      value &&
      typeof value === 'object' &&
      !Array.isArray(value)
    ) {
      const result = extractSectionValue(
        value,
        ...candidateKeys
      );

      if (
        result !== null &&
        result !== undefined &&
        result !== ''
      ) {
        return result;
      }
    }
  }

  return null;
}

/* =========================================================
   DIRECT SUPABASE STORAGE FALLBACK
========================================================= */

async function fetchDirectSupabaseStorageMetric(
  moduleFolder = 'rcm',
  metricName = 'TimeToHire'
) {
  if (
    !APP_CONFIG.supabaseUrl ||
    !APP_CONFIG.supabaseKey
  ) {
    return null;
  }

  const bucket =
    APP_CONFIG.supabaseBucket ||
    'Insights and Reports';

  const normalizedFolder =
    String(moduleFolder).toLowerCase().trim();

  const folders = Array.from(
    new Set([
      moduleFolder,
      normalizedFolder,
      normalizedFolder.toUpperCase()
    ])
  ).filter(Boolean);

  const prefixes = [
    'reports/latest',
    'report/latest',
    'latest',
    'reports',
    'report'
  ];

  const rawName = String(metricName || '')
    .replace(/\.json$/i, '')
    .trim();

  const alphaName = normalizeAlphaKey(rawName);

  const snakeName = rawName
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');

  const pascalName = rawName
    .replace(/(?:^\w|[A-Z]|\b\w)/g, (letter) =>
      letter.toUpperCase()
    )
    .replace(/[\s_-]+/g, '');

  const metricAliases = Array.from(
    new Set([
      rawName,
      alphaName,
      snakeName,
      pascalName
    ])
  ).filter(Boolean);

  const urls = [];

  for (const prefix of prefixes) {
    for (const folder of folders) {
      for (const metric of metricAliases) {
        urls.push(
          `${APP_CONFIG.supabaseUrl}/storage/v1/object/` +
          `${encodeURIComponent(bucket)}/${prefix}/${folder}/${metric}.json`
        );

        urls.push(
          `${APP_CONFIG.supabaseUrl}/storage/v1/object/public/` +
          `${encodeURIComponent(bucket)}/${prefix}/${folder}/${metric}.json`
        );

        urls.push(
          `${APP_CONFIG.supabaseUrl}/storage/v1/object/authenticated/` +
          `${encodeURIComponent(bucket)}/${prefix}/${folder}/${metric}.json`
        );
      }
    }
  }

  for (const url of urls) {
    try {
      const response = await fetchWithTimeout(
        url,
        {
          method: 'GET',
          headers: {
            apikey: APP_CONFIG.supabaseKey,
            Authorization: `Bearer ${APP_CONFIG.supabaseKey}`
          }
        },
        1500
      );

      if (response.ok) {
        const data = await response.json();

        if (data && typeof data === 'object') {
          data._storage_path = url;
          data._source = 'supabase_storage_metric_folder';

          return data;
        }
      }
    } catch {
      // Try the next URL.
    }
  }

  return null;
}

/* =========================================================
   DIRECT SUPABASE TABLE FALLBACK
========================================================= */

async function fetchDirectSupabaseTable(tableName) {
  if (
    !APP_CONFIG.supabaseUrl ||
    !APP_CONFIG.supabaseKey
  ) {
    return [];
  }

  try {
    const response = await fetchWithTimeout(
      `${APP_CONFIG.supabaseUrl}/rest/v1/${tableName}?select=*&limit=50`,
      {
        method: 'GET',
        headers: {
          apikey: APP_CONFIG.supabaseKey,
          Authorization: `Bearer ${APP_CONFIG.supabaseKey}`
        }
      },
      3000
    );

    if (response.ok) {
      const data = await response.json();

      if (Array.isArray(data)) {
        return data;
      }
    }
  } catch (error) {
    console.warn(
      `Direct fetch of Supabase table ${tableName} failed:`,
      error.message
    );
  }

  return [];
}

/* =========================================================
   SUCCESS CRITERIA NORMALIZATION
========================================================= */

/**
 * Preserves the source representation as much as possible.
 *
 * Arrays of strings remain strings.
 * Arrays of objects remain objects.
 * Plain newline-separated strings become arrays.
 * Nested fields such as items/criteria are unwrapped.
 */
function normalizeSuccessCriteria(value, depth = 0) {
  if (depth > 12 || !hasUsableData(value)) {
    return [];
  }

  if (Array.isArray(value)) {
    return value.flatMap((item) =>
      normalizeSuccessCriteria(item, depth + 1)
    );
  }

  if (typeof value === 'string') {
    const trimmed = value.trim();

    if (!trimmed) {
      return [];
    }

    // Support JSON strings stored in the database.
    if (
      trimmed.startsWith('[') ||
      trimmed.startsWith('{')
    ) {
      try {
        const parsed = JSON.parse(trimmed);

        if (
          parsed &&
          typeof parsed === 'object'
        ) {
          return normalizeSuccessCriteria(
            parsed,
            depth + 1
          );
        }
      } catch {
        // Keep treating it as ordinary text.
      }
    }

    return trimmed
      .split(/\r?\n/)
      .map((line) =>
        line
          .replace(/^\s*(?:[-*•]|\d+[.)])\s*/, '')
          .trim()
      )
      .filter(Boolean);
  }

  if (typeof value === 'object') {
    const nested = firstUsableValue(
      value.items,
      value.criteria,
      value.successCriteria,
      value.success_criteria,
      value.successCriteriaAndMonitoring,
      value.success_criteria_and_monitoring,
      value.successMetrics,
      value.success_metrics,
      value.measures,
      value.rows,
      value.data
    );

    if (nested !== undefined && nested !== value) {
      return normalizeSuccessCriteria(
        nested,
        depth + 1
      );
    }

    // Keep an individual criterion object intact.
    const individualCriterion = firstUsableValue(
      value.criterion,
      value.name,
      value.metric,
      value.title,
      value.description,
      value.measure,
      value.indicator,
      value.kpi
    );

    const target = firstUsableValue(
      value.target,
      value.successTarget,
      value.success_target,
      value.expectedOutcome,
      value.expected_outcome,
      value.threshold,
      value.expected,
      value.goal
    );

    if (
      individualCriterion !== undefined ||
      target !== undefined
    ) {
      return [
        {
          ...value,
          ...(individualCriterion !== undefined
            ? { criterion: individualCriterion }
            : {}),
          ...(target !== undefined
            ? { target }
            : {})
        }
      ];
    }

    // Support objects such as { "Completeness": "98%" }.
    const entries = Object.entries(value);

    if (entries.length > 0) {
      return entries.flatMap(([key, item]) => {
        if (!hasUsableData(item)) {
          return [];
        }

        if (
          typeof item === 'string' ||
          typeof item === 'number' ||
          typeof item === 'boolean'
        ) {
          return [
            {
              criterion: key,
              target: String(item)
            }
          ];
        }

        return normalizeSuccessCriteria(
          item,
          depth + 1
        );
      });
    }
  }

  return [];
}

/**
 * Finds populated Success Criteria fields recursively.
 */
function findPopulatedFieldDeep(
  obj,
  candidateKeys,
  seen = new WeakSet()
) {
  if (
    !obj ||
    typeof obj !== 'object' ||
    seen.has(obj)
  ) {
    return undefined;
  }

  seen.add(obj);

  const wanted = new Set(
    candidateKeys.map((key) =>
      String(key).toLowerCase().replace(/[_-]/g, '')
    )
  );

  const entries = Array.isArray(obj)
    ? obj.map((value, index) => [String(index), value])
    : Object.entries(obj);

  for (const [key, value] of entries) {
    const normalizedKey = key
      .toLowerCase()
      .replace(/[_-]/g, '');

    if (
      wanted.has(normalizedKey) &&
      hasUsableData(value)
    ) {
      return value;
    }
  }

  for (const [, value] of entries) {
    if (value && typeof value === 'object') {
      const result = findPopulatedFieldDeep(
        value,
        candidateKeys,
        seen
      );

      if (hasUsableData(result)) {
        return result;
      }
    }
  }

  return undefined;
}

/* =========================================================
   NORMALIZE SUPABASE INSIGHT PAYLOAD
========================================================= */

function normalizeSupabaseInsightPayload(
  rawData,
  metricCode,
  metricName = null
) {
  if (!rawData || typeof rawData !== 'object') {
    return null;
  }

  const repNested =
    rawData.report &&
    typeof rawData.report === 'object'
      ? rawData.report
      : {};

  const rep = {
    ...repNested,
    ...rawData
  };

  const overview =
    rawData.moduleOverview ||
    rawData.module_overview ||
    rep.moduleOverview ||
    rep.module_overview ||
    {};

  const rootCause =
    overview.rootCause ||
    overview.root_cause ||
    extractSectionValue(
      rawData,
      'rootCause',
      'root_cause'
    ) ||
    rawData.whyItHappens ||
    rep.diagnosis?.headline ||
    rep.diagnosis?.narrative;

  const affectedArea =
    overview.affectedArea ||
    overview.affected_area ||
    extractSectionValue(
      rawData,
      'affectedArea',
      'affected_area'
    ) ||
    rawData.whereItHappens;

  const diagObj =
    rep.diagnosis &&
    typeof rep.diagnosis === 'object'
      ? rep.diagnosis
      : {};

  // Suggestions and workstreams.
  const rawWs =
    rawData.workstreams ||
    rep.workstreams ||
    [];

  let wsSteps = [];

  if (Array.isArray(rawWs) && rawWs.length > 0) {
    wsSteps = rawWs
      .filter(
        (workstream) =>
          workstream &&
          (
            workstream.step ||
            workstream.remediationStep ||
            workstream.title
          ) &&
          workstream.kind !== 'data'
      )
      .map(
        (workstream) =>
          workstream.step ||
          workstream.remediationStep ||
          workstream.title
      );

    if (wsSteps.length === 0) {
      wsSteps = rawWs
        .filter(
          (workstream) =>
            workstream &&
            (
              workstream.step ||
              workstream.remediationStep ||
              workstream.title
            )
        )
        .map(
          (workstream) =>
            workstream.step ||
            workstream.remediationStep ||
            workstream.title
        );
    }
  }

  const rawSug =
    (wsSteps.length > 0 ? wsSteps : null) ||
    (
      Array.isArray(rawData.suggestions) &&
      rawData.suggestions.length > 0
        ? rawData.suggestions
        : null
    ) ||
    (
      Array.isArray(repNested.suggestions) &&
      repNested.suggestions.length > 0
        ? repNested.suggestions
        : null
    ) ||
    (
      Array.isArray(diagObj.suggestions) &&
      diagObj.suggestions.length > 0
        ? diagObj.suggestions
        : null
    ) ||
    (
      Array.isArray(overview.suggestions) &&
      overview.suggestions.length > 0
        ? overview.suggestions
        : null
    ) ||
    extractSectionValue(rawData, 'suggestions') ||
    extractSectionValue(
      rawData,
      'howToOvercome',
      'how_to_overcome'
    ) ||
    rawData.howToOvercome ||
    rep.recommendations;

  const suggestionsList = Array.isArray(rawSug)
    ? rawSug
    : (
        typeof rawSug === 'string'
          ? [rawSug]
          : rawSug
            ? [rawSug]
            : []
      );

  const modOverviewObj = {
    rootCause:
      rootCause ||
      'Diagnostic variance detected against benchmark standard.',

    affectedArea:
      affectedArea ||
      'SuccessFactors workflow touchpoints',

    suggestions: suggestionsList
  };

  const headlineText = String(diagObj.headline || '');
  const narrativeText = String(diagObj.narrative || '');

  const impactText = String(
    rep.businessImpact?.overview ||
    rawData.businessImpact?.overview ||
    ''
  );

  const fullText =
    `${headlineText} ${narrativeText} ${impactText}`.trim();

  const cleanStr = (value) => {
    if (value === null || value === undefined) {
      return null;
    }

    const result = String(value).trim();

    if (
      [
        'not yet fetched',
        'data not yet fetched from supabase',
        '--',
        '-',
        'none',
        'null',
        ''
      ].includes(result.toLowerCase())
    ) {
      return null;
    }

    return result;
  };

  // Company value.
  let companyVal = cleanStr(
    rawData.company ||
    rep.company ||
    rawData.company_actual ||
    rep.company_actual ||
    rawData.current_value ||
    rep.current_value ||
    diagObj.current_value ||
    diagObj.actual
  );

  if (!companyVal && fullText) {
    const m1 = fullText.match(
      /(?:stands\s+at|actual\s+is|is\s+at|reaching|reaches)\s+([0-9.]+\s*(?:days|hours|weeks|months|%|\$|k)?)/i
    );

    if (m1) {
      companyVal = m1[1].trim();
    } else {
      const m2 = fullText.match(
        /(?:current\s+[a-zA-Z\s_-]+?\s+(?:stands\s+at|is|at))\s+([0-9.]+\s*(?:days|hours|weeks|months|%|\$|k)?)/i
      );

      if (m2) {
        companyVal = m2[1].trim();
      } else {
        const m3 = fullText.match(
          /(?:stands\s+at|at)\s+([0-9.]+\s*(?:days|hours|weeks|months|%|\$|k)?)/i
        );

        if (m3) {
          companyVal = m3[1].trim();
        }
      }
    }
  }

  // Industry standard.
  let standardVal = cleanStr(
    rawData.standard ||
    rep.standard ||
    rawData.benchmark_target ||
    rep.benchmark_target ||
    diagObj.standard ||
    diagObj.target
  );

  if (!standardVal && fullText) {
    const match = fullText.match(
      /(?:industry\s+standard|standard|benchmark|target)\s*(?:of|is|at|≤|≥)?\s*([≤≥<>~]?\s*[0-9.]+\s*(?:days|hours|weeks|months|%|\$|k)?)/i
    );

    if (match) {
      const rawStandard = match[1].trim();

      if (!/^[≤≥<>~]/.test(rawStandard)) {
        standardVal =
          /(?:day|hour|week|month|turnaround|latency|attrition)/i.test(rawStandard)
            ? `≤ ${rawStandard}`
            : `≥ ${rawStandard}`;
      } else {
        standardVal = rawStandard;
      }
    }
  }

  // Variance.
  let varianceVal = cleanStr(
    rawData.variance ||
    rep.actual_variance ||
    rawData.variance_percentage ||
    rawData.gap ||
    rep.gap ||
    diagObj.gap
  );

  if (!varianceVal && fullText) {
    const match = fullText.match(
      /([0-9.]+\s*(?:days|hours|weeks|%)?)(?:\s*\((?:or\s*)?([0-9.]+%)\))?\s*(above|below)/i
    );

    if (match) {
      const difference = match[1].trim();
      const percentage = match[2];

      const sign =
        match[3].toLowerCase() === 'above'
          ? '+'
          : '-';

      varianceVal = percentage
        ? `${sign}${difference} (${sign}${percentage})`
        : `${sign}${difference}`;
    } else {
      const secondMatch = fullText.match(
        /(?:exceeding|above|below)\s+[^,.]*?\s+by\s+([0-9.]+\s*(?:days|hours|weeks|%)?)/i
      );

      if (secondMatch) {
        varianceVal = `+${secondMatch[1].trim()}`;
      }
    }
  }

  if (
    !varianceVal &&
    companyVal &&
    standardVal &&
    companyVal !== 'Not yet fetched' &&
    standardVal !== 'Not yet fetched'
  ) {
    const companyNumber = String(companyVal).match(/([0-9.]+)/);
    const standardNumber = String(standardVal).match(/([0-9.]+)/);

    if (companyNumber && standardNumber) {
      const companyValue = parseFloat(companyNumber[1]);
      const standardValue = parseFloat(standardNumber[1]);

      const difference = companyValue - standardValue;

      const unit =
        /day/i.test(companyVal)
          ? ' days'
          : /%/.test(companyVal)
            ? '%'
            : '';

      const percentageDifference =
        standardValue !== 0
          ? Math.abs(
              (difference / standardValue) * 100
            ).toFixed(1)
          : '0';

      const sign = difference > 0 ? '+' : '-';

      varianceVal =
        `${sign}${Math.abs(difference).toFixed(1)}${unit} ` +
        `(${sign}${percentageDifference}%)`;
    }
  }

  // Confidence score.
  const rawConfidence = firstUsableValue(
    rawData.confidenceScore,
    rawData.confidence_score,
    diagObj.confidenceScore,
    diagObj.confidence_score,
    rep.confidenceScore,
    rep.confidence_score
  );

  let confidenceScore =
    rawConfidence === undefined ||
    rawConfidence === null ||
    rawConfidence === ''
      ? null
      : Number(rawConfidence);

  if (!Number.isFinite(confidenceScore)) {
    confidenceScore = null;
  }

  // 0.85 becomes 85%; 85 remains 85%.
  if (
    confidenceScore !== null &&
    confidenceScore >= 0 &&
    confidenceScore <= 1
  ) {
    confidenceScore *= 100;
  }

  if (confidenceScore !== null) {
    confidenceScore = Math.max(
      0,
      Math.min(100, confidenceScore)
    );
  }

  // Health status.
  const statusCandidate = String(
    rawData.status ||
    rep.healthState ||
    rep.health_state ||
    ''
  ).toLowerCase().trim().replace(/[_-]+/g, ' ');

  let statusVal = 'Not yet fetched';

  if (statusCandidate.includes('crit')) {
    statusVal = 'Critical';
  } else if (
    statusCandidate.includes('risk') ||
    statusCandidate.includes('warn') ||
    statusCandidate.includes('breach')
  ) {
    statusVal = 'At Risk';
  } else if (
    statusCandidate.includes('healthy') ||
    statusCandidate.includes('on track') ||
    statusCandidate.includes('on target') ||
    statusCandidate === 'good' ||
    statusCandidate === 'ok'
  ) {
    statusVal = 'Healthy';
  }

  companyVal = companyVal || 'Not yet fetched';
  standardVal = standardVal || 'Not yet fetched';
  varianceVal = varianceVal || 'Not yet fetched';

  // Drivers and SHAP factors.
  const factorsRaw = rep.factors || rawData.factors || [];

  const shapFactors = [];
  let stageDrivers = [];
  let segmentDrivers = [];

  if (Array.isArray(factorsRaw) && factorsRaw.length > 0) {
    for (const factor of factorsRaw) {
      if (typeof factor === 'object' && factor) {
        const factorName =
          factor.factorName ||
          factor.name ||
          'Operational Factor';

        const impactPercentage =
          factor.impactPct ||
          factor.impact_pct ||
          0;

        const factorValue =
          factor.avgFactorValue ||
          factor.value ||
          '';

        const entry = {
          name: factorName,

          impact:
            typeof impactPercentage === 'string' &&
            impactPercentage.includes('%')
              ? impactPercentage
              : `+${impactPercentage}%`,

          description:
            `Contributes ${impactPercentage}% to the variance gap (average ${factorValue}).`
        };

        shapFactors.push(entry);

        if (/role|job|segment/i.test(factorName)) {
          segmentDrivers.push({
            id: `A${segmentDrivers.length + 1}`,
            driver: factorName,
            name: factorName,
            avgDays: factorValue || '-',
            vsCompany: entry.impact
          });
        } else {
          stageDrivers.push({
            id: `S${stageDrivers.length + 1}`,
            driver: factorName,
            name: factorName,
            avgDays: factorValue || '-',
            share: entry.impact
          });
        }
      }
    }
  }

  const explicitStage =
    rep.stageDrivers ||
    rep.stage_drivers ||
    rawData.stageDrivers ||
    rawData.stage_drivers;

  if (Array.isArray(explicitStage) && explicitStage.length > 0) {
    stageDrivers = explicitStage.map((driver, index) => ({
      id: driver.id || `S${index + 1}`,

      driver:
        driver.driver ||
        driver.name ||
        driver.stage ||
        `Stage ${index + 1}`,

      name:
        driver.name ||
        driver.driver ||
        `Stage ${index + 1}`,

      avgDays:
        driver.avgDays ||
        driver.days ||
        driver.impact ||
        '-',

      share:
        driver.share ||
        driver.impact ||
        (
          driver.breachContribution
            ? `${driver.breachContribution}%`
            : '-'
        )
    }));
  }

  const explicitSegment =
    rep.segmentDrivers ||
    rep.segment_drivers ||
    rawData.segmentDrivers ||
    rawData.segment_drivers;

  if (
    Array.isArray(explicitSegment) &&
    explicitSegment.length > 0
  ) {
    segmentDrivers = explicitSegment.map((segment, index) => ({
      id: segment.id || `A${index + 1}`,

      driver:
        segment.driver ||
        segment.name ||
        segment.segment ||
        `Segment ${index + 1}`,

      name:
        segment.name ||
        segment.driver ||
        `Segment ${index + 1}`,

      avgDays:
        segment.avgDays ||
        segment.actual ||
        segment.impact ||
        '-',

      vsCompany:
        segment.vsCompany ||
        segment.gap ||
        segment.impact ||
        '-'
    }));
  }

  // ---------------------------------------------------------
  // PLAN AND BRD EXTRACTION
  // ---------------------------------------------------------

  const rawPlan = firstUsableValue(
    rawData.plan,
    rawData.brdPlan,
    rawData.brd_plan,
    rep.plan,
    rep.brdPlan,
    rep.brd_plan,
    repNested.plan,
    repNested.brdPlan,
    repNested.brd_plan
  ) || {};

  // Phases.
  const rawPhases =
    rawPlan.phases ||
    rawPlan.phasedActivities ||
    [];

  const phasedActivities = [];

  if (Array.isArray(rawPhases)) {
    for (
      let phaseIndex = 0;
      phaseIndex < rawPhases.length;
      phaseIndex++
    ) {
      const phase = rawPhases[phaseIndex];

      const phaseName =
        phase.phaseName ||
        phase.title ||
        phase.phase ||
        `Phase ${phaseIndex + 1}`;

      const activities = [];

      const rawActivities = phase.activities || [];

      if (Array.isArray(rawActivities)) {
        for (const activity of rawActivities) {
          const hours =
            activity.effort ||
            activity.hours ||
            8;

          activities.push({
            activity:
              activity.activity ||
              activity.title ||
              activity.name ||
              '',

            owner:
              activity.owner ||
              activity.role ||
              'Specialist',

            workstream:
              activity.workstream ||
              activity.id ||
              '-',

            effort:
              typeof hours === 'number' ||
              !String(hours).includes('Hour')
                ? `${hours} Hours`
                : String(hours)
          });
        }
      }

      phasedActivities.push({
        phaseName,
        milestone: phase.milestone || '',
        deliverable: phase.deliverable || '',
        activities
      });
    }
  }

  // Roles.
  const rawRoles =
    rawPlan.roles ||
    rawPlan.specialistManpower ||
    [];

  const specialistManpower = [];

  if (Array.isArray(rawRoles)) {
    for (const role of rawRoles) {
      const hours =
        role.effort ||
        role.hours ||
        40;

      specialistManpower.push({
        role:
          role.role ||
          'Specialist Consultant',

        headcount:
          role.headcount ||
          role.count ||
          1,

        effort:
          typeof hours === 'number' ||
          !String(hours).includes('Hour')
            ? `${hours} Person-Hours`
            : String(hours)
      });
    }
  }

  // Workstreams.
  const rawPlanWorkstreams =
    rep.workstreams ||
    rawData.workstreams ||
    rawPlan.executionWorkstreams ||
    rawPlan.workstreams ||
    [];

  const executionWorkstreams = [];

  if (
    Array.isArray(rawPlanWorkstreams) &&
    rawPlanWorkstreams.length > 0
  ) {
    for (
      let index = 0;
      index < rawPlanWorkstreams.length;
      index++
    ) {
      const workstream = rawPlanWorkstreams[index];

      let fixes =
        workstream.fixesFactors ||
        workstream.fixesDrivers ||
        'Governance SLA';

      if (Array.isArray(fixes)) {
        fixes = fixes.join(', ');
      }

      executionWorkstreams.push({
        id: workstream.id || `W${index + 1}`,

        remediationStep:
          workstream.step ||
          workstream.remediationStep ||
          workstream.title ||
          '',

        fixesDrivers: String(fixes)
      });
    }
  }

  const totalHours =
    rawPlan.totalHours ||
    rawPlan.totalEffortHours ||
    (
      specialistManpower.reduce((total, role) => {
        const value = parseInt(role.effort, 10);

        return total + (
          Number.isNaN(value)
            ? 0
            : value
        );
      }, 0) || 60
    );

  const durationWeeks =
    rawPlan.durationWeeks ||
    rawPlan.timeline ||
    5;

  const timelineStr =
    typeof durationWeeks === 'number' ||
    !String(durationWeeks).includes('Week')
      ? `${durationWeeks} Weeks`
      : String(durationWeeks);

  const effortStr =
    typeof totalHours === 'number' ||
    !String(totalHours).includes('Hour')
      ? `${totalHours} Total Hours`
      : String(totalHours);

  // Assumptions and Risks.
  const assumptionsAndRisks = firstUsableValue(
    rawPlan.assumptionsAndRisks,
    rawPlan.assumptions_and_risks,
    rep.assumptionsAndRisks,
    rep.assumptions_and_risks,
    rawData.assumptionsAndRisks,
    rawData.assumptions_and_risks
  ) || [];

  // ---------------------------------------------------------
  // SUCCESS CRITERIA
  // ---------------------------------------------------------

  const criteriaFieldNames = [
    'successCriteria',
    'success_criteria',
    'successCriteriaAndMonitoring',
    'success_criteria_and_monitoring',
    'successMetrics',
    'success_metrics',
    'criteria'
  ];

  const rawSuccessCriteria = firstUsableValue(
    // Plan-level fields.
    rawPlan.successCriteria,
    rawPlan.success_criteria,
    rawPlan.successCriteriaAndMonitoring,
    rawPlan.success_criteria_and_monitoring,
    rawPlan.successMetrics,
    rawPlan.success_metrics,
    rawPlan.criteria,

    // Report-level fields.
    rep.successCriteria,
    rep.success_criteria,
    rep.successCriteriaAndMonitoring,
    rep.success_criteria_and_monitoring,
    rep.successMetrics,
    rep.success_metrics,
    rep.criteria,

    // Nested report fields.
    repNested.successCriteria,
    repNested.success_criteria,
    repNested.successCriteriaAndMonitoring,
    repNested.success_criteria_and_monitoring,
    repNested.successMetrics,
    repNested.success_metrics,
    repNested.criteria,

    // Root-level fields.
    rawData.successCriteria,
    rawData.success_criteria,
    rawData.successCriteriaAndMonitoring,
    rawData.success_criteria_and_monitoring,
    rawData.successMetrics,
    rawData.success_metrics,
    rawData.criteria,

    // Search nested payloads when necessary.
    findPopulatedFieldDeep(
      rawData,
      criteriaFieldNames
    )
  );

  const successCriteria = normalizeSuccessCriteria(
    rawSuccessCriteria
  );

  const targetOutcome =
    rawPlan.targetOutcome ||
    rootCause ||
    rep.diagnosis?.headline ||
    'Achieve standard compliance across all process stages.';

  // Business Impact.
  const rawBusinessImpact =
    rep.businessImpact ||
    rawData.businessImpact ||
    rep.business_impact ||
    rawData.business_impact ||
    {};

  const businessImpact = {
    overview:
      rawBusinessImpact.overview ||
      rep.howItEffects ||
      rawData.howItEffects ||
      '',

    financialExposure: firstUsableValue(
      rawBusinessImpact.financialExposure,
      rawBusinessImpact.financial_exposure,
      rawBusinessImpact.financialImpact,
      rawBusinessImpact.financial_impact,
      rawBusinessImpact.estimatedFinancialImpact,
      rawBusinessImpact.costImpact,
      rep.financialExposure,
      rep.financial_exposure,
      rep.financialImpact,
      rep.financial_impact,
      rep.estimatedFinancialImpact,
      rep.costImpact,
      rawData.financialImpact,
      rawData.financial_impact,
      rawData.estimatedFinancialImpact,
      rawData.costImpact
    ) || '',

    slaAndTurnaround:
      rawBusinessImpact.slaAndTurnaround ||
      rawBusinessImpact.sla_and_turnaround ||
      '',

    governanceAndAudit:
      rawBusinessImpact.governanceAndAudit ||
      rawBusinessImpact.governance_and_audit ||
      ''
  };

  // Final normalized BRD.
  const normalizedBrd = {
    ...rawPlan,

    phases: rawPhases,
    roles: rawRoles,

    specialistManpower:
      specialistManpower.length > 0
        ? specialistManpower
        : (rawPlan.specialistManpower || []),

    phasedActivities:
      phasedActivities.length > 0
        ? phasedActivities
        : (rawPlan.phasedActivities || []),

    executionWorkstreams:
      executionWorkstreams.length > 0
        ? executionWorkstreams
        : (rawPlan.executionWorkstreams || []),

    stageDrivers,
    segmentDrivers,

    assumptionsAndRisks:
      Array.isArray(assumptionsAndRisks)
        ? assumptionsAndRisks
        : [assumptionsAndRisks],

    successCriteria,
    success_criteria: successCriteria,

    timelineAndEffort: {
      timeline: timelineStr,
      totalEffort: effortStr
    },

    timeline: timelineStr,
    totalEffortHours: totalHours,
    totalEffortsDisplay: effortStr,
    targetOutcome
  };

  const missingConfigurations = getMetricMissingFields(
    rawData
  );
  const forecastAccuracyScore = rawData.forecastAccuracyScore ??
    rep.forecastAccuracyScore ??
    rep.selectedTrainingModel?.forecastModel?.r2 ??
    rawData.selectedTrainingModel?.forecastModel?.r2 ??
    null;

  return {
    metric: {
      code: metricCode,
      metric: metricName || metricCode,

      category:
        rawData.category ||
        'Operational Quality',

      company: String(companyVal),
      standard: String(standardVal),
      status: statusVal,
      variance: String(varianceVal),

      confidenceScore,
      forecastAccuracyScore,

      successCriteria,
      success_criteria: successCriteria,

      missingConfigurations,

      isSupabaseLive: true,

      _source:
        rawData._source ||
        'supabase',

      diagnosis: diagObj,
      suggestions: suggestionsList,
      businessImpact,
      moduleOverview: modOverviewObj,

      detailedAnalysis: {
        headline: headlineText,

        whyItHappens:
          narrativeText ||
          rootCause ||
          modOverviewObj.rootCause,

        whereItHappens:
          affectedArea ||
          modOverviewObj.affectedArea,

        howToOvercome: suggestionsList,

        trendAnalysis:
          rep.trendAnalysis ||
          rawData.trendAnalysis ||
          {},

        forecast:
          rep.forecast ||
          rep.forecastAnalysis ||
          rep.futureTrendAnalysis ||
          rep.futureTrend ||
          rep.trendAnalysis?.forecast ||
          rep.trend_analysis?.forecast ||
          rawData.forecast ||
          rawData.forecastAnalysis ||
          rawData.futureTrendAnalysis ||
          rawData.futureTrend ||
          null,

        missingConfigurations,

        howItEffects:
          businessImpact.overview ||
          rep.businessImpact?.overview ||
          rawData.howItEffects ||
          '',

        businessImpact,

        successCriteria,
        success_criteria: successCriteria
      }
    },

    diagnosis: diagObj,

    confidenceScore,
    forecastAccuracyScore,

    successCriteria,
    success_criteria: successCriteria,

    suggestions: suggestionsList,
    businessImpact,
    moduleOverview: modOverviewObj,

    brdPlan: normalizedBrd,

    stageDrivers,
    segmentDrivers,
    shapFactors,

    missingConfigurations,

    source:
      rawData._source ||
      'supabase',

    storagePath:
      rawData._storage_path ||
      `report/latest/${metricCode}.json`
  };
}

/* =========================================================
   NORMALIZE FASTAPI SUCCESS CRITERIA RESPONSE
========================================================= */

/**
 * FastAPI responses are normally returned directly.
 * Normalize Success Criteria on that path, too.
 */
function attachNormalizedSuccessCriteria(payload) {
  if (!payload || typeof payload !== 'object') {
    return payload;
  }

  const brdPlan = firstUsableValue(
    payload.brdPlan,
    payload.brd_plan,
    payload.metric?.brdPlan,
    payload.metric?.brd_plan
  ) || {};

  const fieldNames = [
    'successCriteria',
    'success_criteria',
    'successCriteriaAndMonitoring',
    'success_criteria_and_monitoring',
    'successMetrics',
    'success_metrics',
    'criteria'
  ];

  const rawCriteria = firstUsableValue(
    brdPlan.successCriteria,
    brdPlan.success_criteria,
    brdPlan.successCriteriaAndMonitoring,
    brdPlan.success_criteria_and_monitoring,

    payload.successCriteria,
    payload.success_criteria,
    payload.successCriteriaAndMonitoring,
    payload.success_criteria_and_monitoring,

    payload.metric?.successCriteria,
    payload.metric?.success_criteria,
    payload.metric?.successCriteriaAndMonitoring,
    payload.metric?.success_criteria_and_monitoring,

    findPopulatedFieldDeep(
      payload,
      fieldNames
    )
  );

  const successCriteria = normalizeSuccessCriteria(
    rawCriteria
  );

  // Do not fabricate criteria if none was returned.
  if (successCriteria.length === 0) {
    return payload;
  }

  return {
    ...payload,

    successCriteria,
    success_criteria: successCriteria,

    brdPlan: {
      ...brdPlan,
      successCriteria,
      success_criteria: successCriteria
    },

    ...(payload.metric &&
    typeof payload.metric === 'object'
      ? {
          metric: {
            ...payload.metric,
            successCriteria,
            success_criteria: successCriteria,

            detailedAnalysis: {
              ...(payload.metric.detailedAnalysis || {}),
              successCriteria,
              success_criteria: successCriteria
            }
          }
        }
      : {})
  };
}

function parseMetricDeepDivePayload(
  metricCode,
  metricName,
  raw
) {
  return normalizeSupabaseInsightPayload(
    raw,
    metricCode,
    metricName
  );
}

/* =========================================================
   API SERVICE
========================================================= */

export const apiService = {
  async getMetricDataset(moduleId, metricName, metricCode = '', moduleName = '', offset = 0, limit = 100, dateColumn = '', dateFrom = '', dateTo = '') {
    const params = new URLSearchParams({
      module_id: moduleId || '',
      metric_name: metricName || '',
      metric_code: metricCode || '',
      module_name: moduleName || '',
      offset: String(offset),
      limit: String(limit)
    });
    if (dateColumn) params.set('date_column', dateColumn);
    if (dateFrom) params.set('date_from', dateFrom);
    if (dateTo) params.set('date_to', dateTo);
    let response;
    try {
      response = await fetchWithTimeout(
        `${BASE_URL}/datasets/preview?${params.toString()}`,
        { method: 'GET' },
        30000
      );
    } catch (error) {
      const rootUrl = BASE_URL.replace(/\/api\/v1\/?$/, '');
      const reason = error?.name === 'AbortError'
        ? 'The dataset request timed out.'
        : 'The browser could not connect to the dataset API.';
      throw new Error(`${reason} Check that the backend is running at ${rootUrl} and that VITE_API_BASE_URL points to it. (${error?.message || 'Network error'})`);
    }
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || `Dataset request failed (HTTP ${response.status})`);
    }
    return {
      ...payload,
      downloadUrl: payload.downloadUrl ? `${BASE_URL.replace('/api/v1', '')}${payload.downloadUrl}` : null
    };
  },

  /**
   * Check whether FastAPI is reachable.
   */
  async checkHealth() {
    try {
      const rootUrl = BASE_URL.replace('/api/v1', '');

      const response = await fetchWithTimeout(
        `${rootUrl}/health`,
        { method: 'GET' },
        3000
      );

      if (!response.ok) {
        return false;
      }

      const data = await response.json();

      return (
        data.status === 'HEALTHY' ||
        data.status === 'ok'
      );
    } catch {
      return false;
    }
  },

  /**
   * Check backend and Supabase connectivity.
   */
  async checkHealthWithSupabase() {
    try {
      const rootUrl = BASE_URL.replace('/api/v1', '');

      const response = await fetchWithTimeout(
        `${rootUrl}/health`,
        { method: 'GET' },
        3000
      );

      if (!response.ok) {
        return {
          isConnected: false,
          supabaseConnected: false,
          bucketFiles: 0
        };
      }

      const data = await response.json();
      const supa = data.supabase || {};

      return {
        isConnected: true,

        supabaseConnected:
          supa.configured &&
          supa.status === 'connected',

        supabaseStatus:
          supa.status || 'unknown',

        bucketName:
          supa.bucket_name || 'ml-insights',

        folder:
          supa.folder || 'insights',

        bucketFiles:
          supa.files_count || 0,

        files:
          supa.files || []
      };
    } catch {
      return {
        isConnected: false,
        supabaseConnected: false,
        bucketFiles: 0
      };
    }
  },

  /**
   * Check Supabase Storage status.
   */
  async getSupabaseStorageStatus() {
    try {
      const response = await fetchWithTimeout(
        `${BASE_URL}/insights/status`,
        { method: 'GET' },
        3000
      );

      if (!response.ok) {
        return null;
      }

      return await response.json();
    } catch (error) {
      console.warn(
        'Failed to fetch Supabase storage status:',
        error.message
      );

      return null;
    }
  },

  /**
   * Seed test ML insights.
   */
  async seedSupabaseBucket() {
    try {
      const response = await fetchWithTimeout(
        `${BASE_URL}/insights/seed-samples`,
        { method: 'POST' },
        5000
      );

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.warn(
        'Failed to seed Supabase bucket:',
        error.message
      );

      throw error;
    }
  },

  /**
   * Fetch and normalize every module.
   *
   * IMPORTANT:
   * This now applies sanitizeAndMergeModules().
   * Previously getModules() returned the raw backend array,
   * allowing duplicate metric identifiers to reach the UI.
   */
  async getModules(forceRefresh = false) {
    try {
      const response = await fetchWithTimeout(
        `${BASE_URL}/modules${forceRefresh ? '?refresh=true' : ''}`,
        { method: 'GET' },
        8000
      );

      if (response.ok) {
        const data = await response.json();

        if (Array.isArray(data) && data.length > 0) {
          return sanitizeAndMergeModules(data);
        }
      }
    } catch (error) {
      console.warn(
        'Backend /modules call failed, using default baseline:',
        error.message
      );
    }

    return sanitizeAndMergeModules(SF_MODULES);
  },

  /**
   * Fetch one module by ID.
   */
  async getModuleDetails(moduleId) {
    try {
      const response = await fetchWithTimeout(
        `${BASE_URL}/modules/${encodeURIComponent(moduleId)}`,
        { method: 'GET' },
        8000
      );

      if (response.ok) {
        const data = await response.json();

        if (data && data.id) {
          const normalized = sanitizeAndMergeModules([data]);

          if (normalized.length > 0) {
            return normalized[0];
          }
        }
      }
    } catch {
      // Fall back to getModules().
    }

    const allModules = await this.getModules();

    return (
      allModules.find(
        (module) =>
          String(module.id).toLowerCase() ===
          String(moduleId).toLowerCase()
      ) || null
    );
  },

  /**
   * Direct Supabase fallback for individual metric deep dives.
   */
  async fetchDirectFromSupabase(
    metricCode,
    metricName = null,
    moduleId = null
  ) {
    const sbUrl = APP_CONFIG.supabaseUrl;
    const sbKey = APP_CONFIG.supabaseKey;

    const bucket =
      APP_CONFIG.supabaseBucket ||
      'Insights and Reports';

    if (!sbUrl || !sbKey) {
      return null;
    }

    const headers = {
      apikey: sbKey,
      Authorization: `Bearer ${sbKey}`
    };

    const rawName = String(
      metricName || metricCode || ''
    ).trim();

    const cleanMetric = rawName
      .replace(/\s+/g, '')
      .replace(/[-_]/g, '');

    const pascalMetric = rawName
      .replace(/(?:^\w|[A-Z]|\b\w)/g, (letter) =>
        letter.toUpperCase()
      )
      .replace(/[\s_-]+/g, '');

    const modId = moduleId
      ? String(moduleId).toUpperCase().trim()
      : '';

    const candidates = [
      modId
        ? `reports/latest/${modId}/${pascalMetric}.json`
        : null,

      modId
        ? `reports/latest/${modId}/${cleanMetric}.json`
        : null,

      `reports/latest/${pascalMetric}.json`
    ].filter(Boolean);

    try {
      const promises = candidates.map(async (path) => {
        try {
          const url =
            `${sbUrl}/storage/v1/object/authenticated/` +
            `${encodeURIComponent(bucket)}/${path}`;

          const response = await fetchWithTimeout(
            url,
            { headers },
            1500
          );

          if (response.ok) {
            const raw = await response.json();

            if (raw && typeof raw === 'object') {
              return parseMetricDeepDivePayload(
                metricCode,
                metricName,
                raw
              );
            }
          }
        } catch {
          // Try the next path.
        }

        return null;
      });

      const results = await Promise.all(promises);

      const found = results.find(Boolean);

      if (found) {
        return found;
      }
    } catch {
      // No direct result.
    }

    return null;
  },

  /**
   * Fetch the eight-section metric deep dive.
   */
  async getMetricDeepDive(
    metricCode,
    metricName = null,
    moduleId = null
  ) {
    let backendData = null;

    try {
      const params = new URLSearchParams();

      if (metricName) {
        params.append('metric_name', metricName);
      }

      if (moduleId) {
        params.append('module_id', moduleId);
      }

      const queryString = params.toString()
        ? `?${params.toString()}`
        : '';

      const response = await fetchWithTimeout(
        `${BASE_URL}/metrics/${encodeURIComponent(metricCode)}/deep-dive${queryString}`,
        { method: 'GET' },
        5000
      );

      if (response.ok) {
        const data = await response.json();

        if (data && data.metric) {
          backendData = data;
        }
      }
    } catch (error) {
      console.warn(
        `Failed to fetch deep dive for ${metricCode} from backend:`,
        error.message
      );
    }

    /*
     * The backend remains authoritative.
     * Normalize Success Criteria before returning its response.
     */
    if (backendData && backendData.metric && backendData.source !== 'none') {
      return attachNormalizedSuccessCriteria(
        backendData
      );
    }

    /*
     * Use direct Supabase fallback only when the backend
     * did not return a usable metric payload.
     */
    try {
      const directData = await this.fetchDirectFromSupabase(
        metricCode,
        metricName,
        moduleId
      );

      if (directData && directData.metric) {
        return directData;
      }
    } catch (error) {
      console.warn(
        'Direct Supabase fetch fallback warning:',
        error
      );
    }

    // Strict fallback: do not invent live metric values.
    return {
      metric: {
        code: metricCode,
        metric: metricName || metricCode,
        category: 'Operational KPI',

        company: 'Not yet fetched',
        standard: 'Not yet fetched',
        status: 'Not yet fetched',
        variance: 'Not yet fetched',

        confidenceScore: null,

        successCriteria: [],
        success_criteria: [],

        missingConfigurations: [],

        isSupabaseLive: false,
        _source: 'static_baseline',

        moduleOverview: {
          rootCause: 'Data not yet fetched',
          affectedArea: 'Data not yet fetched',
          suggestions: []
        },

        detailedAnalysis: {
          whyItHappens: 'Data not yet fetched',
          whereItHappens: 'Data not yet fetched',

          trendAnalysis: {
            summary: 'Data not yet fetched',
            points: []
          },

          missingConfigurations: [],

          howItEffects: 'Data not yet fetched',
          howToOvercome: [],

          successCriteria: [],
          success_criteria: []
        }
      },

      moduleOverview: {
        rootCause: 'Data not yet fetched',
        affectedArea: 'Data not yet fetched',
        suggestions: []
      },

      stageDrivers: [],
      segmentDrivers: [],
      shapFactors: [],

      confidenceScore: null,

      successCriteria: [],
      success_criteria: [],

      missingConfigurations: [],

      brdPlan: {
        specialistManpower: [],
        phasedActivities: [],
        executionWorkstreams: [],

        stageDrivers: [],
        segmentDrivers: [],

        assumptionsAndRisks: [],

        successCriteria: [],
        success_criteria: [],

        timeline: 'Not yet fetched',
        totalEffortHours: 0,
        totalEffortsDisplay: 'Not yet fetched',

        timelineAndEffort: {
          timeline: 'Not yet fetched',
          totalEffort: 'Not yet fetched'
        },

        targetOutcome: 'Data not yet fetched'
      }
    };
  },

  /**
   * Test the SAP SuccessFactors OData handshake.
   */
  async testConnection({
    datacenter,
    companyId,
    username,
    password,
    clientId,
    clientSecret
  }) {
    const response = await fetchWithTimeout(
      `${BASE_URL}/connect/test`,
      {
        method: 'POST',
        body: JSON.stringify({
          datacenter,
          companyId,
          username,

          password: password || '',
          clientId: clientId || '',
          clientSecret: clientSecret || ''
        })
      }
    );

    if (!response.ok) {
      const errorJson = await response
        .json()
        .catch(() => ({}));

      throw new Error(
        errorJson.detail ||
        `Connection test failed (HTTP ${response.status})`
      );
    }

    return await response.json();
  },

  /**
   * Upload custom industry standards.
   */
  async uploadCustomStandards(
    standardsMap,
    uploadedBy = 'enterprise_admin'
  ) {
    const response = await fetchWithTimeout(
      `${BASE_URL}/standards/upload`,
      {
        method: 'POST',
        body: JSON.stringify({
          standards: standardsMap,
          uploadedBy
        })
      }
    );

    if (!response.ok) {
      const errorJson = await response
        .json()
        .catch(() => ({}));

      throw new Error(
        errorJson.detail ||
        `Upload failed (HTTP ${response.status})`
      );
    }

    return await response.json();
  },

  /**
   * Trigger the ML calculation pipeline.
   */
  async triggerMlPipeline(
    moduleId = null,
    forceRefreshAllLlms = false
  ) {
    try {
      const response = await fetchWithTimeout(
        `${BASE_URL}/pipeline/trigger-ml-run`,
        {
          method: 'POST',
          body: JSON.stringify({
            module_id: moduleId,
            force_refresh_all_llms: forceRefreshAllLlms
          })
        },
        2500
      );

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.warn(
        'Backend ML trigger fallback to simulated pipeline:',
        error.message
      );

      return {
        status: 'success',
        simulated: true
      };
    }
  }
};

export default apiService;
