import React, { useState } from 'react';

export default function ComparisonTable({ module, standardMode = 'standard' }) {
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
        <h2 className="panel-main-title">
          {isCustom ? 'Company vs. Custom Standards' : 'Company vs. Industry Standards'}
        </h2>

        <div className="pill-filter-group">
          <button
            type="button"
            className={`pill-filter-btn ${filterMode === 'all' ? 'active' : ''}`}
            onClick={() => setFilterMode('all')}
          >
            All
          </button>
          <button
            type="button"
            className={`pill-filter-btn ${filterMode === 'critical' ? 'active' : ''}`}
            onClick={() => setFilterMode('critical')}
          >
            Critical
          </button>
          <button
            type="button"
            className={`pill-filter-btn ${filterMode === 'at-risk' ? 'active' : ''}`}
            onClick={() => setFilterMode('at-risk')}
          >
            At Risk
          </button>
          <button
            type="button"
            className={`pill-filter-btn ${filterMode === 'healthy' ? 'active' : ''}`}
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
              <th scope="col" className="th-metric">METRIC</th>
              <th scope="col" className="th-company text-left">OUR COMPANY</th>
              <th scope="col" className="th-standard text-left">
                {isCustom ? 'CUSTOM STANDARD' : 'INDUSTRY STANDARD'}
              </th>
              <th scope="col" className="th-status text-center">HEALTHY STATE</th>
              <th scope="col" className="th-variance text-center">VARIANCE</th>
            </tr>
          </thead>
          <tbody>
            {filteredBenchmarks.length === 0 ? (
              <tr>
                <td colSpan={5} className="no-data-msg">
                  No metrics match the selected filter.
                </td>
              </tr>
            ) : (
              filteredBenchmarks.map((row, idx) => {
                return (
                  <tr key={idx}>
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
                    <td className="td-variance text-center">
                      <span className="variance-text">{row.variance}</span>
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
