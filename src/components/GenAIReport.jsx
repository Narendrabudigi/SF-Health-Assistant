import React, { useState } from 'react';

export default function GenAIReport({ module }) {
  const { aiReport, benchmarks = [] } = module || {};

  // Filter ONLY Critical and At Risk metrics as explicitly mandated
  const issueMetrics = benchmarks.filter(
    (b) => (b.status === 'Critical' || b.status === 'At Risk') && b.detailedAnalysis
  );

  // Manage accordion state: first metric expanded by default
  const [expandedIndex, setExpandedIndex] = useState(0);

  const toggleMetric = (idx) => {
    setExpandedIndex(expandedIndex === idx ? null : idx);
  };

  const criticalCount = issueMetrics.filter(m => m.status === 'Critical').length;
  const atRiskCount = issueMetrics.filter(m => m.status === 'At Risk').length;

  const executiveSummary = aiReport?.summary || 
    `${module?.name || 'Module'} currently shows ${criticalCount} Critical and ${atRiskCount} At Risk metric variances against enterprise benchmark targets. Immediate governance and automated remediation steps are recommended to restore SLA compliance.`;

  return (
    <div className="white-panel ai-diagnostic-panel">
      {/* Panel Header */}
      <div className="ai-report-header">
        <span className="swiss-panel-eyebrow">
          <span className="ai-sparkle-icon" aria-hidden="true">✨</span>
          <span>Diagnostic Analysis • AI Insights</span>
        </span>
        <h2 className="panel-main-title">AI Diagnostic Report</h2>
      </div>

      {/* Executive Summary Callout */}
      <div className="ai-summary-callout">
        <div className="callout-header-tag">
          <span className="callout-icon">💡</span>
          <span>Executive Summary • {criticalCount} Critical, {atRiskCount} At Risk</span>
        </div>
        <p className="callout-text">{executiveSummary}</p>
      </div>

      {issueMetrics.length === 0 ? (
        <div className="healthy-state-report-callout">
          <div className="healthy-icon-pill">✓</div>
          <div>
            <h4 className="healthy-title">All Module Benchmarks Healthy</h4>
            <p className="healthy-desc">
              Every tracked metric in this module is operating within established SLA parameters. No active SLA breaches or degradation risks detected.
            </p>
          </div>
        </div>
      ) : (
        <>
          {/* Section Header: Where the Issue is Happening with Expandable Accordion Tiles */}
          <div className="ai-section-title-wrap">
            <h3 className="ai-section-numbered-title">
              <span className="section-index-num">01</span>
              <span>Where the Issue is Happening ({issueMetrics.length} Active Variances)</span>
            </h3>
          </div>

          {/* Expandable Diagnostic Accordion Cards */}
          <div className="ai-accordion-list" role="region" aria-label="Diagnostic Issue Details">
            {issueMetrics.map((metricRow, idx) => {
              const isCritical = metricRow.status === 'Critical';
              const isExpanded = expandedIndex === idx;
              const actions = metricRow.detailedAnalysis?.howToOvercome || [];

              return (
                <div 
                  key={idx} 
                  className={`diagnostic-accordion-card ${isCritical ? 'accordion-critical' : 'accordion-at-risk'} ${isExpanded ? 'is-open' : ''}`}
                >
                  {/* Card Main Info */}
                  <div className="accordion-main-card">
                    <div className="accordion-header-row">
                      <div className="accordion-header-left">
                        <h4 className="accordion-metric-title">{metricRow.metric}</h4>
                        <span className="code-tag">{metricRow.category}</span>
                      </div>

                      <span className={`pill-badge ${isCritical ? 'badge-critical' : 'badge-at-risk'}`}>
                        <span className="badge-dot" aria-hidden="true"></span>
                        <span>{metricRow.status}</span>
                      </span>
                    </div>

                    {/* Dedicated 'Where the Issue is Happening' Locus Description */}
                    <div className="accordion-where-box">
                      <div className="where-eyebrow">
                        <span className="where-pin-icon" aria-hidden="true">📍</span>
                        <span className="where-label-text">Where the issue is happening:</span>
                      </div>
                      <p className="where-locus-desc">
                        {metricRow.detailedAnalysis?.whereItHappens || `${metricRow.category} processes within ${module?.name || 'the system'}.`}
                      </p>
                    </div>

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
                          {metricRow.detailedAnalysis?.whyItHappens}
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
        </>
      )}
    </div>
  );
}



