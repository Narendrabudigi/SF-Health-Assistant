import React, { useState, useMemo } from 'react';
import { getMissingFieldCount } from '../utils/dataGapUtils';
import { formatBenchmarkDisplay } from '../utils/benchmarkDisplay';
import { formatDisplayUnits, formatVarianceDisplay } from '../utils/displayUnits';
import { normalizeMetricStatus } from '../utils/metricStatus';

const getBadgeClass = (status) => {
  if (status === 'Critical') return 'badge-critical';
  if (status === 'At Risk') return 'badge-at-risk';
  if (status === 'Healthy') return 'badge-healthy';
  return 'badge-neutral';
};

export default function ComparisonTable({
  module,
  standardMode = 'standard',
  onSelectMetric,
  customStandardsMap = {}
}) {
  const { benchmarks = [] } = module || {};
  const [filterMode, setFilterMode] = useState('all');

  const isCustom = standardMode === 'custom';

  const {
    criticalCount,
    atRiskCount,
    healthyCount,
    processedBenchmarks
  } = useMemo(() => {
    let crit = 0;
    let atRisk = 0;
    let healthy = 0;

    const processed = benchmarks.map((row) => {
      const st = normalizeMetricStatus(row?.status);

      if (st === 'Critical') crit++;
      else if (st === 'At Risk') atRisk++;
      else if (st === 'Healthy') healthy++;

      return {
        ...row,
        normalizedStatus: st
      };
    });

    return {
      criticalCount: crit,
      atRiskCount: atRisk,
      healthyCount: healthy,
      processedBenchmarks: processed
    };
  }, [benchmarks]);

  const filteredBenchmarks = useMemo(() => {
    if (filterMode === 'all') return processedBenchmarks;
    if (filterMode === 'critical') {
      return processedBenchmarks.filter((row) => row.normalizedStatus === 'Critical');
    }
    if (filterMode === 'at-risk') {
      return processedBenchmarks.filter((row) => row.normalizedStatus === 'At Risk');
    }
    if (filterMode === 'healthy') {
      return processedBenchmarks.filter((row) => row.normalizedStatus === 'Healthy');
    }
    return processedBenchmarks;
  }, [processedBenchmarks, filterMode]);

  const selectMetric = (row, displayStandard) => {
    if (!onSelectMetric) return;

    onSelectMetric({
      ...row,
      status: row.normalizedStatus || normalizeMetricStatus(row.status),
      standard: displayStandard,
      isCustomStandard: Boolean(isCustom && customStandardsMap[row.metric?.toLowerCase().trim()])
    });
  };

  return (
    <div className="white-panel comparison-panel">
      <div className="comparison-header">
        <div className="comparison-title-wrap">
          <span className="comparison-header-icon" aria-hidden="true">
            <svg
              width="22"
              height="22"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M16 16l3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1z" />
              <path d="M2 16l3-8 3 8c-.87.65-1.92-1-3-1s-2.13-.35-3-1z" />
              <path d="M7 21h10" />
              <path d="M12 3v18" />
              <path d="M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2" />
            </svg>
          </span>

          <h2 className="comparison-main-title">
            {isCustom ? 'Company vs. Custom Standards' : 'Company vs. Industry Standards'}
          </h2>
        </div>

        <div className="pill-filter-group" role="tablist" aria-label="Filter Metrics">
          <button
            type="button"
            className={`pill-filter-btn ${filterMode === 'all' ? 'active' : ''}`}
            onClick={() => setFilterMode('all')}
          >
            All ({benchmarks.length})
          </button>

          <button
            type="button"
            className={`pill-filter-btn filter-btn-critical ${filterMode === 'critical' ? 'active' : ''}`}
            onClick={() => setFilterMode('critical')}
          >
            Critical ({criticalCount})
          </button>

          <button
            type="button"
            className={`pill-filter-btn filter-btn-at-risk ${filterMode === 'at-risk' ? 'active' : ''}`}
            onClick={() => setFilterMode('at-risk')}
          >
            At Risk ({atRiskCount})
          </button>

          <button
            type="button"
            className={`pill-filter-btn filter-btn-healthy ${filterMode === 'healthy' ? 'active' : ''}`}
            onClick={() => setFilterMode('healthy')}
          >
            Healthy ({healthyCount})
          </button>
        </div>
      </div>

      <div className="clean-table-container">
        <table className="clean-benchmark-table">
          <thead>
            <tr>
              <th scope="col" className="th-metric">Metric Name</th>
              <th scope="col" className="th-company text-left">Our Company</th>
              <th scope="col" className="th-standard text-left">
                {isCustom ? 'Custom Standard' : 'Industry Standard'}
              </th>
              <th scope="col" className="th-status text-center">Health Status</th>
              <th scope="col" className="th-data-gaps text-center">Data Gaps Count</th>
              <th scope="col" className="th-variance text-right">Variance</th>
              <th scope="col" className="th-date text-center">Date</th>
              <th scope="col" className="th-action text-right">Analysis</th>
            </tr>
          </thead>

          <tbody>
            {filteredBenchmarks.length === 0 ? (
              <tr>
                <td colSpan={7} className="no-data-msg">
                  No metrics match the selected filter.
                </td>
              </tr>
            ) : (
              filteredBenchmarks.map((row, idx) => {
                const currentStatus =
                  row.normalizedStatus ||
                  normalizeMetricStatus(row.status);

                const hasVarianceBreach = Boolean(
                  row.variance &&
                  !String(row.variance).toLowerCase().includes('on target') &&
                  String(row.variance).trim() !== '0%' &&
                  String(row.variance).trim() !== '0' &&
                  (String(row.variance).includes('+') ||
                    String(row.variance).includes('-'))
                );

                const isHealthy =
                  currentStatus === 'Healthy' && !hasVarianceBreach;

                const isIssue =
                  currentStatus === 'Critical' ||
                  currentStatus === 'At Risk' ||
                  hasVarianceBreach ||
                  !isHealthy;

                const customStdVal =
                  customStandardsMap[row.metric?.toLowerCase().trim()];

                const displayStandard =
                  isCustom && customStdVal
                    ? customStdVal
                    : row.standard;
                const benchmarkLabel = formatBenchmarkDisplay(displayStandard);
                const standardValue = formatDisplayUnits(benchmarkLabel);

                const dataGapCount = getMissingFieldCount(row);
                const hasSupabasePayload = Boolean(
                  row.isSupabaseLive ||
                  String(row._source || '').startsWith('supabase')
                );
                const companyValueText = String(row.company ?? '').trim().toLowerCase();
                const companyValueUnavailable =
                  !companyValueText ||
                  /^(not yet fetched|data not yet fetched|n\/a|na|unknown|--|no data\b)/.test(companyValueText);
                const hasProcessGap =
                  hasSupabasePayload && companyValueUnavailable && dataGapCount > 0;
                const varianceText = String(row.variance ?? '').trim();
                const normalizedVariance = varianceText.toLowerCase();
                const hasDataGaps = Boolean(
                  dataGapCount > 0 ||
                  normalizedVariance.includes('data gap') ||
                  String(row.company || '').toLowerCase().includes('no data') ||
                  String(row.company || '').toLowerCase() === 'n/a' ||
                  String(row.dataQuality?.overallRating || '').toLowerCase() === 'poor'
                );
                const varianceUnavailable =
                  !normalizedVariance ||
                  ['not yet fetched', 'data not yet fetched', 'n/a', 'na', '--', '-', 'unknown'].includes(normalizedVariance) ||
                  normalizedVariance.includes('data gap');
                const varianceDisplay = varianceUnavailable
                  ? (hasProcessGap ? 'Process Gaps' : (hasDataGaps ? 'Data Gaps' : 'Not yet fetched'))
                  : row.variance;

                return (
                  <tr
                    key={row.code || row.id || idx}
                    className="clickable-metric-row"
                    onClick={() => selectMetric(row, displayStandard)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        selectMetric(row, displayStandard);
                      }
                    }}
                    tabIndex={0}
                    role="button"
                    aria-label={`View deep dive analysis for ${row.metric}`}
                  >
                    <td className="td-metric">
                      <div className="metric-title-cell-wrap">
                        <span className="metric-primary-name">
                          {formatDisplayUnits(row.metric)}
                        </span>
                      </div>
                      <div className="metric-category-subtext">
                        {formatDisplayUnits(row.category)}
                      </div>
                    </td>

                    <td className="td-company">
                      <span className="bold-company-val">
                        {hasProcessGap ? 'Process Gaps' : (formatDisplayUnits(row.company) ?? 'Not yet fetched')}
                      </span>
                    </td>

                    <td className="td-standard">
                      <div className="standard-cell-wrap">
                        <span className="standard-val">
                          {hasProcessGap && (!standardValue || /^(not yet fetched|data not yet fetched|n\/a|na|unknown|--|—|-)$/i.test(String(standardValue).trim()))
                            ? 'Process Gaps'
                            : (standardValue ?? 'Not yet fetched')}
                        </span>

                        {isCustom && customStdVal && (
                          <span
                            className="custom-indicator-chip"
                            title="Imported Custom Standard"
                          >
                            Custom
                          </span>
                        )}
                      </div>
                    </td>

                    <td className="td-status text-center">
                      <span className={`pill-badge ${getBadgeClass(hasProcessGap ? 'Process Gaps' : currentStatus)}`}>
                        <span className="badge-dot" aria-hidden="true" />
                        <span>{hasProcessGap ? 'Process Gaps' : currentStatus}</span>
                      </span>
                    </td>

                    {/* Analysis view shows ONLY the count. */}
                    <td className="td-data-gaps text-center">
                      <span className="data-gap-count">
                        {dataGapCount}
                      </span>
                    </td>

                    <td className="td-variance text-right">
                      <span
                        className={`variance-tag variance-${currentStatus
                          .toLowerCase()
                          .replace(/\s+/g, '-')}`}
                      >
                        {formatVarianceDisplay(varianceDisplay)}
                      </span>
                    </td>

                    <td className="td-date text-center">
                      {typeof row.generatedAt === 'string' && /^\d{4}-\d{2}-\d{2}/.test(row.generatedAt)
                        ? row.generatedAt.slice(0, 10)
                        : '—'}
                    </td>

                    <td className="td-action text-right">
                      {isIssue ? (
                        <span className="metric-deepdive-tag">
                          Deep Dive <span className="deepdive-arrow">→</span>
                        </span>
                      ) : (
                        <span className="metric-on-target-tag">
                          On Target
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
