import React from 'react';
import { normalizeMetricStatus } from '../utils/metricStatus';
import { getMissingFieldCount } from '../utils/dataGapUtils';

const isCompanyValueUnavailable = (value) => {
  const companyValue = String(value ?? '').trim().toLowerCase();
  return !companyValue || /^(not yet fetched|data not yet fetched|n\/a|na|unknown|--|no data\b|data gaps?|process gaps?)(\b|$)/.test(companyValue);
};

const CANONICAL_MODULE_NAMES = {
  ec: 'Employee Central',
  rcm: 'Recruitment',
  onb: 'Onboarding',
  ofb: 'Offboarding',
  ecp: 'Employee Central Payroll'
};

// Icon mapping helper matching the screenshot's rounded colored icon squares
function ModuleIcon({ type }) {
  switch (type) {
    case 'users': // Employee Central (blue)
      return (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
          <circle cx="9" cy="7" r="4"></circle>
          <path d="M23 21v-2a4 4 0 0 0-3-3.87"></path>
          <path d="M16 3.13a4 4 0 0 1 0 7.75"></path>
        </svg>
      );
    case 'briefcase': // Recruitment (purple)
      return (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="2" y="7" width="20" height="14" rx="2" ry="2"></rect>
          <path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"></path>
        </svg>
      );
    case 'user-plus': // Onboarding (green)
      return (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
          <circle cx="8.5" cy="7" r="4"></circle>
          <line x1="20" y1="8" x2="20" y2="14"></line>
          <line x1="23" y1="11" x2="17" y2="11"></line>
        </svg>
      );
    case 'user-minus': // Offboarding (orange)
      return (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
          <circle cx="8.5" cy="7" r="4"></circle>
          <line x1="23" y1="11" x2="17" y2="11"></line>
        </svg>
      );
    default:
      return null;
  }
}

const getBadgeClass = (status) => {
  if (status === 'Critical') return 'badge-critical';
  if (status === 'At Risk') return 'badge-at-risk';
  if (status === 'Healthy') return 'badge-healthy';
  return 'badge-neutral';
};

export default function HomeDashboard({ modules, onSelectModule }) {
  // Home alert totals count metrics, not modules. Use the same explicit
  // Supabase health status normalization as the module analysis table.
  const allMetrics = (Array.isArray(modules) ? modules : []).flatMap((module) =>
    Array.isArray(module?.benchmarks) ? module.benchmarks : []
  );
  const metricStatuses = allMetrics.map((metric) => normalizeMetricStatus(metric?.status));
  const criticalCount = metricStatuses.filter((status) => status === 'Critical').length;
  const atRiskCount = metricStatuses.filter((status) => status === 'At Risk').length;
  const healthyCount = metricStatuses.filter((status) => status === 'Healthy').length;
  const processGapsCount = allMetrics.filter((metric) => {
    const hasSupabasePayload = Boolean(
      metric?.isSupabaseLive || String(metric?._source || '').startsWith('supabase')
    );
    return hasSupabasePayload && isCompanyValueUnavailable(metric?.company) && getMissingFieldCount(metric) > 0;
  }).length;
  const totalMetrics = metricStatuses.length;
  const healthyPercentage = totalMetrics > 0
    ? ((healthyCount / totalMetrics) * 100).toFixed(1)
    : '0.0';

  return (
    <div className="overview-container">
      {/* Header Area */}
      <div className="overview-heading-wrap">
        <h2 className="overview-main-title">SF Health Monitor</h2>
        <p className="overview-sub-title">
          Real-time benchmark comparisons, SLA tracking, and diagnostic insights across your core SAP SuccessFactors modules.
        </p>
      </div>

      {/* Smooth Executive KPI Banner Strip */}
      <div className="swiss-kpi-strip" role="region" aria-label="Executive KPI Summary">
        <div className="kpi-strip-cell">
          <span className="kpi-cell-label">Active Modules</span>
          <span className="kpi-cell-value">{modules.length}</span>
          <span className="kpi-cell-sub">Core Human Resources Scope</span>
        </div>
        <div className="kpi-strip-divider"></div>
        <div className="kpi-strip-cell">
          <span className="kpi-cell-label">Critical Alerts</span>
          <span className="kpi-cell-value text-critical">{criticalCount}</span>
          <span className="kpi-cell-sub">Immediate Attention Needed</span>
        </div>
        <div className="kpi-strip-divider"></div>
        <div className="kpi-strip-cell">
          <span className="kpi-cell-label">At-Risk Processes</span>
          <span className="kpi-cell-value text-at-risk">{atRiskCount}</span>
          <span className="kpi-cell-sub">SLA Variance Identified</span>
        </div>
        <div className="kpi-strip-divider"></div>
        <div className="kpi-strip-cell">
          <span className="kpi-cell-label">Process Gaps</span>
          <span className="kpi-cell-value text-process-gaps">{processGapsCount}</span>
          <span className="kpi-cell-sub">Metrics blocked by missing process data</span>
        </div>
        <div className="kpi-strip-divider"></div>
        <div className="kpi-strip-cell">
          <span className="kpi-cell-label">Monitored Metrics</span>
          <span className="kpi-cell-value">
            {totalMetrics}
            <span className="kpi-healthy-percentage">{healthyPercentage}% Healthy</span>
          </span>
          <span className="kpi-cell-sub">Benchmark Comparisons</span>
        </div>
      </div>

      {/* 4 Smooth Module Cards Grid */}
      <div className="module-cards-row">
        {modules.map((mod) => {
          const benchmarks = Array.isArray(mod.benchmarks) ? mod.benchmarks : [];
          const moduleStatusCounts = benchmarks.reduce((counts, metric) => {
            const status = normalizeMetricStatus(metric?.status);
            if (status === 'Healthy') counts.healthy += 1;
            else if (status === 'At Risk') counts.atRisk += 1;
            else if (status === 'Critical') counts.critical += 1;
            const hasSupabasePayload = Boolean(
              metric?.isSupabaseLive || String(metric?._source || '').startsWith('supabase')
            );
            if (
              hasSupabasePayload &&
              isCompanyValueUnavailable(metric?.company) &&
              getMissingFieldCount(metric) > 0
            ) {
              counts.processGaps += 1;
            }
            return counts;
          }, { healthy: 0, atRisk: 0, critical: 0, processGaps: 0 });
          const moduleHealthStatus = [
            ['Critical', moduleStatusCounts.critical],
            ['At Risk', moduleStatusCounts.atRisk],
            ['Healthy', moduleStatusCounts.healthy]
          ].reduce(
            (leader, [status, count]) => count > leader.count ? { status, count } : leader,
            { status: moduleStatusCounts.processGaps > 0 ? 'Process Gaps' : 'Not yet fetched', count: 0 }
          ).status;

          return (
            <div 
              key={mod.id} 
              className={`overview-card card-theme-${mod.id}`}
              onClick={() => onSelectModule(mod.id)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => e.key === 'Enter' && onSelectModule(mod.id)}
            >
              {/* Card Header: Module Title on Left, Icon on Right */}
              <div className="card-top-meta">
                <h3 className="card-module-title">{CANONICAL_MODULE_NAMES[mod.id?.toLowerCase()] || mod.name}</h3>
                <div 
                  className={`card-icon-box card-icon-${mod.id}`} 
                >
                  <ModuleIcon type={mod.iconType} />
                </div>
              </div>

              {/* KPI Count Micro-pill */}
              <div className="card-kpi-count-tag">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <line x1="18" y1="20" x2="18" y2="10"></line>
                  <line x1="12" y1="20" x2="12" y2="4"></line>
                  <line x1="6" y1="20" x2="6" y2="14"></line>
                </svg>
                <span>{benchmarks.length} Benchmark Metrics</span>
              </div>

              <div className="module-health-counts" aria-label={`${CANONICAL_MODULE_NAMES[mod.id?.toLowerCase()] || mod.name} metric counts`}>
                <div className="module-health-count module-health-count-healthy">
                  <span>Healthy</span><strong>{moduleStatusCounts.healthy}</strong>
                </div>
                <div className="module-health-count module-health-count-risk">
                  <span>At Risk</span><strong>{moduleStatusCounts.atRisk}</strong>
                </div>
                <div className="module-health-count module-health-count-critical">
                  <span>Critical</span><strong>{moduleStatusCounts.critical}</strong>
                </div>
                <div className="module-health-count module-health-count-process-gaps">
                  <span>Process Gaps</span><strong>{moduleStatusCounts.processGaps}</strong>
                </div>
              </div>

              {/* Footer: Status Pill on left, View Analysis link on right */}
              <div className="card-bottom-actions">
                <span className={`pill-badge ${getBadgeClass(moduleHealthStatus)}`}>
                  <span className="badge-dot" aria-hidden="true"></span>
                  <span>{moduleHealthStatus}</span>
                </span>

                <span 
                  className="view-analysis-link"
                  onClick={(e) => {
                    e.stopPropagation();
                    onSelectModule(mod.id);
                  }}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.stopPropagation();
                      onSelectModule(mod.id);
                    }
                  }}
                >
                  <span>View Analysis</span>
                  <svg className="view-arrow-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="5" y1="12" x2="19" y2="12"></line>
                    <polyline points="12 5 19 12 12 19"></polyline>
                  </svg>
                </span>
              </div>
            </div>
          );
        })}

      </div>
    </div>
  );
}
