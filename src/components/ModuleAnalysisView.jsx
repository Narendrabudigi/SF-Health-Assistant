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
  const [selectedMetric, setSelectedMetric] = useState(() => {
    try {
      const saved = sessionStorage.getItem(`sf_active_metric_${module?.id}`);
      if (saved && module?.benchmarks) {
        const found = module.benchmarks.find((b) => b.metric === saved);
        if (found) return found;
      }
    } catch (e) {
      // ignore
    }
    return null;
  });

  // Sync deep dive status with parent App component and persist in sessionStorage
  useEffect(() => {
    if (onDeepDiveChange) {
      onDeepDiveChange(Boolean(selectedMetric));
    }
    try {
      if (selectedMetric?.metric && module?.id) {
        sessionStorage.setItem(`sf_active_metric_${module.id}`, selectedMetric.metric);
      } else if (module?.id) {
        sessionStorage.removeItem(`sf_active_metric_${module.id}`);
      }
    } catch (e) {
      // ignore
    }
  }, [selectedMetric, module?.id, onDeepDiveChange]);

  // When active module changes (e.g. from ribbon), reset selected metric
  useEffect(() => {
    setSelectedMetric(null);
  }, [module?.id]);

  // Handle ESC key to close deep dive
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && selectedMetric) {
        setSelectedMetric(null);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectedMetric]);

  // If a metric is selected, render the dedicated Full-Page Deep Dive with BRD Plan
  if (selectedMetric) {
    return (
      <MetricDeepDivePage
        metric={selectedMetric}
        module={module}
        onBack={() => setSelectedMetric(null)}
      />
    );
  }

  if (!module) return null;

  const CANONICAL_MODULE_NAMES = {
    ec: 'Employee Central',
    rcm: 'Recruitment',
    onb: 'Onboarding',
    ofb: 'Offboarding',
    ecp: 'Employee Central Payroll'
  };

  const displayName = CANONICAL_MODULE_NAMES[module.id?.toLowerCase()] || module.name;
  const benchmarks = module.benchmarks || [];
  const criticalCount = module.criticalCount !== undefined 
    ? module.criticalCount 
    : benchmarks.filter(b => String(b.status || '').toLowerCase().includes('crit')).length;
  const atRiskCount = module.atRiskCount !== undefined 
    ? module.atRiskCount 
    : benchmarks.filter(b => String(b.status || '').toLowerCase().includes('risk') || String(b.status || '').toLowerCase().includes('warn')).length;
  const healthyCount = module.healthyCount !== undefined 
    ? module.healthyCount 
    : benchmarks.filter(b => String(b.status || '').toLowerCase().includes('health')).length;

  const hasLiveMetrics = benchmarks.some(b => 
    b.isSupabaseLive || 
    b._source === 'supabase' || 
    b._source === 'supabase_storage_metric_folder' || 
    b._source === 'supabase_llm_reports_table'
  );

  const isModuleNotFetched = !hasLiveMetrics || module.status === 'Not yet fetched' || String(module.status || '').toLowerCase().includes('not yet');

  const executiveSummary = isModuleNotFetched
    ? (module.aiReport?.summary && !module.aiReport.summary.toLowerCase().includes('critically bottlenecked') ? module.aiReport.summary : 'Data not yet fetched from Supabase.')
    : (module.aiReport?.summary || `${displayName} diagnostic analysis synthesized from Supabase.`);

  const overlineText = isModuleNotFetched
    ? 'EXECUTIVE SUMMARY • NOT YET FETCHED'
    : `EXECUTIVE SUMMARY • ${criticalCount} CRITICAL, ${atRiskCount} AT RISK`;

  return (
    <div className="analysis-page-wrapper">
      {/* 1. Header: Summary Report & Subtitle */}
      <div className="analysis-page-header">
        <h1 className="analysis-page-title">Summary Report</h1>
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
              {overlineText}
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
