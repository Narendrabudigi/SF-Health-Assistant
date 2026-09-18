import React, { useEffect, useState } from 'react';
import { getBrdPlan } from '../utils/brdPlanData';
import { generateMetricBrdPdf } from '../utils/pdfGenerator';

export default function MetricAnalysisModal({ metric, onClose }) {
  const [isDownloading, setIsDownloading] = useState(false);
  const [downloadSuccess, setDownloadSuccess] = useState(false);

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
  const brdPlan = getBrdPlan(metric);

  const isCritical = status === 'Critical';
  const badgeClass = isCritical ? 'badge-critical' : status === 'Healthy' ? 'badge-healthy' : 'badge-at-risk';

  const handleDownloadPDF = () => {
    setIsDownloading(true);
    setTimeout(() => {
      try {
        generateMetricBrdPdf(metric);
        setIsDownloading(false);
        setDownloadSuccess(true);
        setTimeout(() => setDownloadSuccess(false), 3000);
      } catch (err) {
        console.error('PDF Generation Error:', err);
        setIsDownloading(false);
      }
    }, 350);
  };

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

              {/* Card 4: How to Overcome • BRD Plan of Action */}
              {detailedAnalysis.howToOvercome && detailedAnalysis.howToOvercome.length > 0 && brdPlan && (
                <div className="diagnostic-card brd-clean-card">
                  <div className="diagnostic-card-header">
                    <span className="card-step-badge">04</span>
                    <div className="card-header-text">
                      <div className="card-badge-row">
                        <h4 className="diagnostic-card-title">How to Overcome</h4>
                        <span className="brd-pill-tag">BRD Plan of Action</span>
                      </div>
                      <span className="diagnostic-card-subtitle">
                        Resource allocation and execution roadmap to eliminate variance gap
                      </span>
                    </div>
                  </div>

                  <div className="diagnostic-card-content">
                    {/* Compact Resource & Timeline Strip */}
                    <div className="brd-compact-strip">
                      <div className="brd-compact-item brd-compact-grow">
                        <span className="brd-compact-label">
                          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                            <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
                            <circle cx="9" cy="7" r="4"></circle>
                            <path d="M23 21v-2a4 4 0 0 0-3-3.87"></path>
                            <path d="M16 3.13a4 4 0 0 1 0 7.75"></path>
                          </svg>
                          Manpower Required
                        </span>
                        <div className="brd-role-chips">
                          {brdPlan.workforceRequired.map((wf, wIdx) => (
                            <span key={wIdx} className="brd-role-chip">
                              <strong>{wf.count}x</strong> {wf.role} <span className="chip-hrs">({wf.hours})</span>
                            </span>
                          ))}
                        </div>
                      </div>

                      <div className="brd-compact-divider"></div>

                      <div className="brd-compact-item brd-compact-timeline">
                        <span className="brd-compact-label">
                          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                            <circle cx="12" cy="12" r="10"></circle>
                            <polyline points="12 6 12 12 16 14"></polyline>
                          </svg>
                          Est. Timeline & Effort
                        </span>
                        <div className="brd-timeline-val">
                          <strong>{brdPlan.timeline}</strong>
                          <span className="brd-effort-badge">{brdPlan.totalEffortHours} Total Hours</span>
                        </div>
                      </div>
                    </div>

                    {/* Prescriptive Remediation Steps */}
                    <div className="brd-clean-steps">
                      <div className="brd-clean-steps-header">
                        Execution Plan & Workstreams
                      </div>
                      <ol className="remediation-steps-list">
                        {detailedAnalysis.howToOvercome.map((step, sIdx) => (
                          <li key={sIdx} className="remediation-step-item">
                            <span className="step-counter">{sIdx + 1}</span>
                            <span className="step-text">{step}</span>
                          </li>
                        ))}
                      </ol>
                    </div>

                    {/* Target Business Outcome */}
                    {brdPlan.expectedOutcome && (
                      <div className="brd-clean-outcome">
                        <span className="outcome-tag">Target Outcome</span>
                        <span className="outcome-text">{brdPlan.expectedOutcome}</span>
                      </div>
                    )}
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

        {/* Modal Footer with PDF Download option instead of close button */}
        <div className="modal-footer metric-modal-footer">
          <span className="modal-footer-caption">
            SAP SuccessFactors Enterprise Diagnostic Intelligence • BRD Implementation Plan
          </span>
          <button 
            type="button" 
            className={`btn-primary btn-download-pdf ${downloadSuccess ? 'btn-download-success' : ''}`}
            onClick={handleDownloadPDF}
            disabled={isDownloading}
            title="Download complete BRD Action Plan and diagnostic report as a PDF document"
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
              <polyline points="7 10 12 15 17 10"></polyline>
              <line x1="12" y1="15" x2="12" y2="3"></line>
            </svg>
            <span>
              {downloadSuccess 
                ? 'Downloaded (PDF) ✓' 
                : isDownloading 
                  ? 'Generating PDF...' 
                  : 'Download BRD Plan (PDF)'}
            </span>
          </button>
        </div>
      </div>
    </div>
  );
}
