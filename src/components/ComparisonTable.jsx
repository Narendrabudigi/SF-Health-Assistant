import React, { useState } from 'react';

export default function ComparisonTable({ module, standardMode = 'standard', onSelectMetric }) {
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

  return (
    <div className="white-panel comparison-panel">
      {/* Header with Title and Filter Buttons */}
      <div className="comparison-header">
        <div className="comparison-title-wrap">
          <span className="swiss-panel-eyebrow">Benchmark Standards • SLA Tracking</span>
          <h2 className="panel-main-title">
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
            Critical
          </button>
          <button 
            type="button" 
            className={`pill-filter-btn filter-btn-at-risk ${filterMode === 'at-risk' ? 'active' : ''}`}
            onClick={() => setFilterMode('at-risk')}
          >
            At Risk
          </button>
          <button 
            type="button" 
            className={`pill-filter-btn filter-btn-healthy ${filterMode === 'healthy' ? 'active' : ''}`}
            onClick={() => setFilterMode('healthy')}
          >
            Healthy
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
                return (
                  <tr 
                    key={idx}
                    className={hasDetailedAnalysis ? 'clickable-metric-row' : 'static-metric-row'}
                    onClick={() => {
                      if (hasDetailedAnalysis && onSelectMetric) {
                        onSelectMetric(row);
                      }
                    }}
                    onKeyDown={(e) => {
                      if (hasDetailedAnalysis && onSelectMetric && (e.key === 'Enter' || e.key === ' ')) {
                        e.preventDefault();
                        onSelectMetric(row);
                      }
                    }}
                    tabIndex={hasDetailedAnalysis ? 0 : undefined}
                    role={hasDetailedAnalysis ? 'button' : undefined}
                    aria-label={hasDetailedAnalysis ? `View detailed analysis for ${row.metric}` : undefined}
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

                    {/* INDUSTRY STANDARD */}
                    <td className="td-standard">
                      <span className="standard-val">{row.standard}</span>
                    </td>

                    {/* HEALTHY STATE */}
                    <td className="td-status text-center">
                      <span className={`pill-badge ${getBadgeClass(row.status)}`}>
                        {row.status}
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

