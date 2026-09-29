import React, { useState } from 'react';

export default function ComparisonTable({ 
  module, 
  standardMode = 'standard', 
  onSelectMetric, 
  customStandardsMap = {} 
}) {
  const { benchmarks } = module;
  const [filterMode, setFilterMode] = useState('all'); // 'all' | 'critical' | 'at-risk' | 'healthy'

  const isCustom = standardMode === 'custom';

  const filteredBenchmarks = benchmarks.filter(row => {
    if (filterMode === 'critical') return row.status === 'Critical';
    if (filterMode === 'at-risk') return row.status === 'At Risk';
    if (filterMode === 'healthy') return row.status === 'Healthy';
    return true;
  });

  const getBadgeClass = (status) => {
    if (status === 'Critical') return 'badge-critical';
    if (status === 'At Risk') return 'badge-at-risk';
    if (status === 'Healthy') return 'badge-healthy';
    return 'badge-at-risk';
  };

  const criticalCount = benchmarks.filter(b => b.status === 'Critical').length;
  const atRiskCount = benchmarks.filter(b => b.status === 'At Risk').length;
  const healthyCount = benchmarks.filter(b => b.status === 'Healthy').length;

  return (
    <div className="white-panel comparison-panel">
      {/* Header with Icon, Title and Filter Buttons */}
      <div className="comparison-header">
        <div className="comparison-title-wrap">
          <span className="comparison-header-icon" aria-hidden="true">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M16 16l3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1z"></path>
              <path d="M2 16l3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1z"></path>
              <path d="M7 21h10"></path>
              <path d="M12 3v18"></path>
              <path d="M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2"></path>
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

      {/* Comparison Table */}
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
              <th scope="col" className="th-variance text-right">Variance</th>
              <th scope="col" className="th-action text-right">Analysis</th>
            </tr>
          </thead>
          <tbody>
            {filteredBenchmarks.length === 0 ? (
              <tr>
                <td colSpan={6} className="no-data-msg">
                  No metrics match the selected filter.
                </td>
              </tr>
            ) : (
              filteredBenchmarks.map((row, idx) => {
                const hasDetailedAnalysis = (row.status === 'Critical' || row.status === 'At Risk') && row.detailedAnalysis;
                const customStdVal = customStandardsMap[row.metric.toLowerCase().trim()];
                const displayStandard = (isCustom && customStdVal) ? customStdVal : row.standard;

                return (
                  <tr 
                    key={idx}
                    className="clickable-metric-row"
                    onClick={() => {
                      if (onSelectMetric) {
                        onSelectMetric(row);
                      }
                    }}
                    onKeyDown={(e) => {
                      if (onSelectMetric && (e.key === 'Enter' || e.key === ' ')) {
                        e.preventDefault();
                        onSelectMetric(row);
                      }
                    }}
                    tabIndex={0}
                    role="button"
                    aria-label={`View deep dive analysis for ${row.metric}`}
                  >
                    {/* METRIC */}
                    <td className="td-metric">
                      <div className="metric-primary-name">{row.metric}</div>
                      <div className="metric-category-subtext">{row.category}</div>
                    </td>

                    {/* OUR COMPANY */}
                    <td className="td-company">
                      <span className="bold-company-val">{row.company}</span>
                    </td>

                    {/* INDUSTRY / CUSTOM STANDARD */}
                    <td className="td-standard">
                      <div className="standard-cell-wrap">
                        <span className="standard-val">{displayStandard}</span>
                        {isCustom && customStdVal && (
                          <span className="custom-indicator-chip" title="Imported Custom Standard">Custom</span>
                        )}
                      </div>
                    </td>


                    {/* HEALTHY STATE */}
                    <td className="td-status text-center">
                      <span className={`pill-badge ${getBadgeClass(row.status)}`}>
                        <span className="badge-dot" aria-hidden="true"></span>
                        <span>{row.status}</span>
                      </span>
                    </td>

                    {/* VARIANCE */}
                    <td className="td-variance text-right">
                      <span className={`variance-tag variance-${row.status.toLowerCase().replace(/\s+/g, '-')}`}>
                        {row.variance}
                      </span>
                    </td>

                    {/* ACTION / DEEP DIVE */}
                    <td className="td-action text-right">
                      {hasDetailedAnalysis ? (
                        <span className="metric-deepdive-tag">
                          Deep Dive <span className="deepdive-arrow">→</span>
                        </span>
                      ) : (
                        <span className="metric-on-target-tag">On Target</span>
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

