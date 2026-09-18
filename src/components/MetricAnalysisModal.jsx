import React, { useEffect } from 'react';

export default function MetricAnalysisModal({ metric, onClose }) {
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    const prevBodyOverflow = document.body.style.overflow;
    const prevHtmlOverflow = document.documentElement.style.overflow;
    document.body.style.overflow = 'hidden';
    document.documentElement.style.overflow = 'hidden';

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      document.body.style.overflow = prevBodyOverflow;
      document.documentElement.style.overflow = prevHtmlOverflow;
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [onClose]);

  if (!metric) return null;

  const { detailedAnalysis, metric: metricName, category, company, standard, status, variance } = metric;

  const isCritical = status === 'Critical';
  const badgeClass = isCritical ? 'badge-critical' : status === 'Healthy' ? 'badge-healthy' : 'badge-at-risk';

  return (
    <div className="modal-backdrop" onClick={onClose} role="dialog" aria-modal="true" aria-labelledby="modal-metric-title">
      <div 
        className="modal-card metric-analysis-modal" 
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className="modal-header metric-modal-header">
          <div className="modal-title-wrap">
            <div className={`metric-modal-icon-badge ${isCritical ? 'icon-critical' : 'icon-at-risk'}`}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10"></circle>
                <line x1="12" y1="8" x2="12" y2="12"></line>
                <line x1="12" y1="16" x2="12.01" y2="16"></line>
              </svg>
            </div>
            <div>
              <div className="metric-modal-eyebrow">
                {category} • Diagnostic Root Cause & Trend Deep Dive
              </div>
              <h3 id="modal-metric-title" className="modal-title">{metricName}</h3>
            </div>
          </div>
          <div className="metric-modal-actions">
            <span className={`pill-badge ${badgeClass}`}>{status}</span>
            <button 
              type="button" 
              className="btn-modal-close" 
              onClick={onClose}
              aria-label="Close detailed analysis"
            >
              ✕
            </button>
          </div>
        </div>

        {/* Modal Content Body */}
        <div className="metric-modal-body">
          {/* Top Performance Metric Summary Strip */}
          <div className="metric-summary-strip">
            <div className="summary-stat-cell">
              <span className="stat-cell-label">Current Company Value</span>
              <span className="stat-cell-value current-val">{company}</span>
            </div>
            <div className="summary-stat-divider"></div>
            <div className="summary-stat-cell">
              <span className="stat-cell-label">Benchmark Standard</span>
              <span className="stat-cell-value">{standard}</span>
            </div>
            <div className="summary-stat-divider"></div>
            <div className="summary-stat-cell">
              <span className="stat-cell-label">Variance Gap</span>
              <span className={`stat-cell-value ${isCritical ? 'val-critical' : 'val-at-risk'}`}>
                {variance}
              </span>
            </div>
          </div>

          {detailedAnalysis ? (
            <div className="diagnostic-cards-container">
              {/* Card 1: Why is it happening */}
              <div className="diagnostic-card">
                <div className="diagnostic-card-header">
                  <span className="card-step-badge">01</span>
                  <div className="card-header-text">
                    <h4 className="diagnostic-card-title">Why Is It Happening?</h4>
                    <span className="diagnostic-card-subtitle">Root Cause Analysis & Architecture Bottlenecks</span>
                  </div>
                </div>
                <div className="diagnostic-card-content">
                  <p className="analysis-text-paragraph">{detailedAnalysis.whyItHappens}</p>
                </div>
              </div>

              {/* Card 2: Trend Analysis */}
              {detailedAnalysis.trendAnalysis && (
                <div className="diagnostic-card">
                  <div className="diagnostic-card-header">
                    <span className="card-step-badge">02</span>
                    <div className="card-header-text">
                      <h4 className="diagnostic-card-title">Trend Analysis</h4>
                      <span className="diagnostic-card-subtitle">Quarterly Progression & Performance Trajectory</span>
                    </div>
                  </div>
                  <div className="diagnostic-card-content">
                    <p className="analysis-text-paragraph mb-sm">
                      {detailedAnalysis.trendAnalysis.summary}
                    </p>
                    {detailedAnalysis.trendAnalysis.points && (
                      <div className="trend-points-strip">
                        {detailedAnalysis.trendAnalysis.points.map((pt, pIdx) => (
                          <div key={pIdx} className="trend-point-chip">
                            <span className="trend-period">{pt.period}</span>
                            <span className="trend-value">{pt.value}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Card 3: How is it affecting */}
              <div className="diagnostic-card">
                <div className="diagnostic-card-header">
                  <span className="card-step-badge">03</span>
                  <div className="card-header-text">
                    <h4 className="diagnostic-card-title">How Is It Affecting the Business?</h4>
                    <span className="diagnostic-card-subtitle">Downstream SLA, Payroll & Operational Impact</span>
                  </div>
                </div>
                <div className="diagnostic-card-content">
                  <p className="analysis-text-paragraph">{detailedAnalysis.howItEffects}</p>
                </div>
              </div>

              {/* Card 4: How to overcome */}
              {detailedAnalysis.howToOvercome && detailedAnalysis.howToOvercome.length > 0 && (
                <div className="diagnostic-card">
                  <div className="diagnostic-card-header">
                    <span className="card-step-badge">04</span>
                    <div className="card-header-text">
                      <h4 className="diagnostic-card-title">How to Overcome</h4>
                      <span className="diagnostic-card-subtitle">Prescriptive Corrective Actions & Configuration Adjustments</span>
                    </div>
                  </div>
                  <div className="diagnostic-card-content">
                    <ol className="remediation-steps-list">
                      {detailedAnalysis.howToOvercome.map((step, sIdx) => (
                        <li key={sIdx} className="remediation-step-item">
                          <span className="step-counter">{sIdx + 1}</span>
                          <span className="step-text">{step}</span>
                        </li>
                      ))}
                    </ol>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="healthy-state-notice">
              <div className="healthy-icon-pill">✓</div>
              <div>
                <h4 className="healthy-title">Metric Performing Within Benchmark Target</h4>
                <p className="healthy-desc">
                  This metric is operating in a Healthy state without active SLA breaches or downstream bottlenecks. Detailed diagnostic deep-dive is only generated for Critical and At Risk performance indicators.
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="modal-footer metric-modal-footer">
          <span className="modal-footer-caption">
            SAP SuccessFactors Enterprise Diagnostic Intelligence
          </span>
          <button type="button" className="btn-secondary" onClick={onClose}>
            Close Analysis
          </button>
        </div>
      </div>
    </div>
  );
}
