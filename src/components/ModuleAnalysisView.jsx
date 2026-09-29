import React, { useState, useEffect } from 'react';
import GenAIReport from './GenAIReport';
import ComparisonTable from './ComparisonTable';
import MetricDeepDivePage from './MetricDeepDivePage';

export default function ModuleAnalysisView({
  module,
  standardMode = 'standard',
  customStandardsMap = {},
  onGoHome,
  onSelectModule,
  onDeepDiveChange
}) {
  const [selectedMetric, setSelectedMetric] = useState(null);

  // Sync deep dive status with parent App component
  useEffect(() => {
    if (onDeepDiveChange) {
      onDeepDiveChange(Boolean(selectedMetric));
    }
  }, [selectedMetric, onDeepDiveChange]);

  // When active module changes (e.g. from ribbon), reset deep-dive metric view back to module analysis
  useEffect(() => {
    setSelectedMetric(null);
  }, [module?.id]);

  if (!module) return null;

  // When a metric is selected for deep dive, render as a full page view!
  if (selectedMetric) {
    return (
      <MetricDeepDivePage
        initialMetric={selectedMetric}
        module={module}
        onGoHome={onGoHome}
        onSelectModule={onSelectModule}
        onBack={() => {
          setSelectedMetric(null);
          window.scrollTo({ top: 0, behavior: 'smooth' });
        }}
      />
    );
  }

  const benchmarks = module.benchmarks || [];
  const criticalCount = benchmarks.filter(b => b.status === 'Critical').length;
  const atRiskCount = benchmarks.filter(b => b.status === 'At Risk').length;
  const healthyCount = benchmarks.filter(b => b.status === 'Healthy').length;

  const executiveSummary = module.aiReport?.summary ||
    `${module.name} turnaround is critically bottlenecked with key metric variances against benchmark targets. Immediate remediation and process optimization are top priorities.`;

  return (
    <div className="analysis-page-wrapper">
      {/* 1. Header: AI Diagnostic Report & Subtitle */}
      <div className="analysis-page-header">
        <h1 className="analysis-page-title">AI Diagnostic Report</h1>
        <p className="analysis-page-subtitle">
          Analyze your SuccessFactors configuration against SAP best practices and industry standards.
        </p>
      </div>

      {/* 2. Full-Width Top Executive Summary & KPI Stat Cards */}
      <div className="analysis-top-banner">
        {/* Left: Executive Summary Card */}
        <div className="executive-summary-card">
          <div className="exec-summary-icon-box" aria-hidden="true">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
              <polyline points="14 2 14 8 20 8"></polyline>
              <line x1="16" y1="13" x2="8" y2="13"></line>
              <line x1="16" y1="17" x2="8" y2="17"></line>
              <polyline points="10 9 9 9 8 9"></polyline>
            </svg>
          </div>
          <div className="exec-summary-content">
            <div className="exec-summary-overline">
              EXECUTIVE SUMMARY • {criticalCount} CRITICAL, {atRiskCount} AT RISK
            </div>
            <p className="exec-summary-text">{executiveSummary}</p>
          </div>
        </div>

        {/* Right: 3 KPI Summary Cards */}
        <div className="analysis-kpi-group">
          {/* Critical Card */}
          <div className="analysis-kpi-card kpi-card-critical">
            <div className="kpi-icon-wrap" aria-hidden="true">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 2L1 21h22L12 2zm0 3.99L19.53 19H4.47L12 5.99zM11 10v4h2v-4h-2zm0 6v2h2v-2h-2z" />
              </svg>
            </div>
            <div className="kpi-value-num">{criticalCount}</div>
            <div className="kpi-title-label">Critical Issues</div>
            <div className="kpi-sub-label">Requires immediate action</div>
          </div>

          {/* At Risk Card */}
          <div className="analysis-kpi-card kpi-card-at-risk">
            <div className="kpi-icon-wrap" aria-hidden="true">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 2L1 21h22L12 2zm0 3.99L19.53 19H4.47L12 5.99zM11 10v4h2v-4h-2zm0 6v2h2v-2h-2z" />
              </svg>
            </div>
            <div className="kpi-value-num">{atRiskCount}</div>
            <div className="kpi-title-label">At Risk Issues</div>
            <div className="kpi-sub-label">Need attention</div>
          </div>

          {/* Healthy Card */}
          <div className="analysis-kpi-card kpi-card-healthy">
            <div className="kpi-icon-wrap" aria-hidden="true">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
                <polyline points="22 4 12 14.01 9 11.01"></polyline>
              </svg>
            </div>
            <div className="kpi-value-num">{healthyCount}</div>
            <div className="kpi-title-label">{healthyCount === 1 ? 'Healthy Metric' : 'Healthy Metrics'}</div>
            <div className="kpi-sub-label">Performing well</div>
          </div>
        </div>
      </div>

      {/* 3. 2-Column Grid: Issues Identified (Left) & Standards Table (Right) */}
      <div className="analysis-view-grid">
        {/* Left Column: Issues Identified Accordion Cards */}
        <section className="analysis-grid-col" aria-label="Issues Identified">
          <GenAIReport module={module} />
        </section>

        {/* Right Column: Company vs. Standards Table */}
        <section className="analysis-grid-col" aria-label="Company vs. Standards">
          <ComparisonTable
            module={module}
            standardMode={standardMode}
            onSelectMetric={setSelectedMetric}
            customStandardsMap={customStandardsMap}
          />
        </section>
      </div>
    </div>
  );
}

