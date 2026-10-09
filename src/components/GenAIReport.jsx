import React, { useState } from 'react';

export default function GenAIReport({ module }) {
  const { benchmarks = [] } = module || {};

  // Check if all metrics are not yet fetched
  const isModuleNotFetched = benchmarks.length === 0 || benchmarks.every((b) => {
    const s = String(b.status || '').toLowerCase().trim();
    return s.includes('not yet') || s === '--' || s === 'pending';
  });

  // Filter Critical and At Risk metrics that require diagnostic attention
  const issueMetrics = benchmarks.filter((b) => {
    const s = String(b.status || '').toLowerCase().trim();
    const v = String(b.variance || '').toLowerCase().trim();
    if (s.includes('not yet') || s === '--' || s === 'pending') return false;
    const hasBreach = (v.includes('+') || v.includes('-')) && !v.includes('on target');
    if (s.includes('crit') || s.includes('risk') || s.includes('warn') || hasBreach) {
      return true;
    }
    const isHealthy = s.includes('health') || (v.includes('on target') && !hasBreach);
    return !isHealthy;
  });

  // Manage accordion state: collapsed by default
  const [expandedIndex, setExpandedIndex] = useState(null);

  const toggleMetric = (idx) => {
    setExpandedIndex(expandedIndex === idx ? null : idx);
  };

  return (
    <div className="issues-identified-column">
      {/* Column Header: Document Icon + Issues Identified + Active Variances Badge */}
      <div className="issues-identified-header">
        <div className="issues-title-left">
          <span className="issues-header-icon" aria-hidden="true">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
              <polyline points="14 2 14 8 20 8"></polyline>
              <line x1="16" y1="13" x2="8" y2="13"></line>
              <line x1="16" y1="17" x2="8" y2="17"></line>
              <polyline points="10 9 9 9 8 9"></polyline>
            </svg>
          </span>
          <h2 className="issues-header-title">Areas of Focus</h2>
        </div>

        {issueMetrics.length > 0 && (
          <span className="issues-variances-badge">
            {issueMetrics.length} Active Variances
          </span>
        )}
      </div>

      {issueMetrics.length === 0 ? (
        isModuleNotFetched ? (
          <div className="healthy-state-report-callout" style={{ borderLeftColor: '#64748b' }}>
            <div className="healthy-icon-pill" style={{ background: '#f1f5f9', color: '#64748b' }}>⏳</div>
            <div>
              <h4 className="healthy-title">Data Not Yet Fetched</h4>
              <p className="healthy-desc">
                No active metrics or diagnostic reports have been ingested for this module.
              </p>
            </div>
          </div>
        ) : (
          <div className="healthy-state-report-callout">
            <div className="healthy-icon-pill">✓</div>
            <div>
              <h4 className="healthy-title">All Module Benchmarks Healthy</h4>
              <p className="healthy-desc">
                Every tracked metric in this module is operating within established SLA parameters. No active SLA breaches or degradation risks detected.
              </p>
            </div>
          </div>
        )
      ) : (
        <div className="ai-accordion-list" role="region" aria-label="Diagnostic Issue Details">
          {issueMetrics.map((metricRow, idx) => {
            const isCritical = String(metricRow.status || '').toLowerCase().includes('crit');
            const isExpanded = expandedIndex === idx;
            const whereText = metricRow.moduleOverview?.affectedArea || metricRow.detailedAnalysis?.whereItHappens || `${metricRow.category} processes within ${module?.name || 'the system'}.`;
            const whyText = metricRow.moduleOverview?.rootCause || metricRow.detailedAnalysis?.whyItHappens || 'Diagnostic variance detected against benchmark standard.';

            const rawActions = (
              (metricRow.moduleOverview?.suggestions && metricRow.moduleOverview.suggestions.length > 0 ? metricRow.moduleOverview.suggestions : null) ||
              (metricRow.detailedAnalysis?.howToOvercome && metricRow.detailedAnalysis.howToOvercome.length > 0 ? metricRow.detailedAnalysis.howToOvercome : null) ||
              metricRow.suggestions ||
              []
            );
            const actions = Array.isArray(rawActions) ? rawActions : (typeof rawActions === 'string' ? [rawActions] : (rawActions ? [rawActions] : []));

            const indexStr = String(idx + 1).padStart(2, '0');

            return (
              <div 
                key={idx} 
                className={`diagnostic-accordion-card ${isCritical ? 'accordion-critical' : 'accordion-at-risk'} ${isExpanded ? 'is-open' : ''}`}
              >
                {/* Card Main Info */}
                <div className="accordion-main-card">
                  <div className="accordion-header-row">
                    <div className="accordion-header-left">
                      {/* Red / Amber Number Badge (01, 02) */}
                      <span className={`card-index-badge ${isCritical ? 'badge-num-critical' : 'badge-num-at-risk'}`}>
                        {indexStr}
                      </span>
                      <h3 className="accordion-metric-title">{metricRow.metric}</h3>
                    </div>

                    <span className={`pill-badge ${isCritical ? 'badge-critical' : 'badge-at-risk'}`}>
                      {metricRow.status}
                    </span>
                  </div>

                  {/* Locus Description / Where it happens */}
                  <p className="accordion-summary-locus">
                    {whereText}
                  </p>

                  {/* Dropdown Toggle: Why it is happening & Suggestions to improve */}
                  <button 
                    type="button" 
                    className={`accordion-dropdown-trigger ${isExpanded ? 'is-expanded' : ''}`}
                    onClick={() => toggleMetric(idx)}
                    aria-expanded={isExpanded}
                  >
                    <span className="dropdown-trigger-label">
                      {isExpanded ? 'Hide Root Cause & Suggestions' : 'Why it is happening & Suggestions to improve'}
                    </span>
                    <span className={`accordion-chevron-box ${isExpanded ? 'rotated' : ''}`} aria-hidden="true">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="6 9 12 15 18 9"></polyline>
                      </svg>
                    </span>
                  </button>
                </div>

                {/* Dropdown Body: Revealed on Down Arrow Click */}
                {isExpanded && (
                  <div className="accordion-body">
                    {/* Sub-block 1: Why It is Happening (Root Cause) */}
                    <div className="accordion-sub-section">
                      <div className="sub-section-header">
                        <span className="sub-section-icon">🔍</span>
                        <h5 className="sub-section-title">Why It is Happening (Root Cause)</h5>
                      </div>
                      <p className="sub-section-text">
                        {whyText}
                      </p>
                    </div>

                    {/* Sub-block 2: Suggestions to Improve */}
                    {actions.length > 0 && (
                      <div className="accordion-sub-section">
                        <div className="sub-section-header">
                          <span className="sub-section-icon">💡</span>
                          <h5 className="sub-section-title">Suggestions to Improve</h5>
                        </div>
                        <ol className="accordion-suggestions-list">
                          {actions.map((action, aIdx) => (
                            <li key={aIdx} className="accordion-suggestion-item">
                              <span className="accordion-step-counter">{aIdx + 1}</span>
                              <span className="accordion-step-text">{action}</span>
                            </li>
                          ))}
                        </ol>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
