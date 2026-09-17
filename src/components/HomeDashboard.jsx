import React from 'react';

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

export default function HomeDashboard({ modules, onSelectModule }) {
  // Compute executive metrics for Swiss business summary
  const criticalCount = modules.filter(m => m.status === 'Critical').length;
  const atRiskCount = modules.filter(m => m.status === 'At Risk').length;
  const totalMetrics = modules.reduce((acc, m) => acc + (m.benchmarks ? m.benchmarks.length : 0), 0);

  return (
    <div className="overview-container">
      {/* Header Area */}
      <div className="overview-heading-wrap">
        <div className="swiss-eyebrow">EXECUTIVE OVERVIEW • LIVE HEALTH MONITORING</div>
        <h2 className="overview-main-title">Module Health Overview</h2>
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
          <span className="kpi-cell-label">Monitored Metrics</span>
          <span className="kpi-cell-value">{totalMetrics}</span>
          <span className="kpi-cell-sub">Benchmark Comparisons</span>
        </div>
      </div>

      {/* 4 Smooth Module Cards Grid */}
      <div className="module-cards-row">
        {modules.map((mod) => {
          return (
            <div 
              key={mod.id} 
              className="overview-card"
              onClick={() => onSelectModule(mod.id)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => e.key === 'Enter' && onSelectModule(mod.id)}
            >
              {/* Card Header: Module Title on Left, Icon on Right */}
              <div className="card-top-meta">
                <h3 className="card-module-title">{mod.name}</h3>
                <div 
                  className="card-icon-box" 
                  style={{ backgroundColor: mod.iconBg }}
                >
                  <ModuleIcon type={mod.iconType} />
                </div>
              </div>

              {/* Short Description */}
              <p className="card-module-desc">{mod.description}</p>

              {/* KPI Count Micro-pill */}
              <div className="card-kpi-count-tag">
                <span>{mod.benchmarks?.length || 0} Benchmark Metrics</span>
              </div>

              {/* Footer: Status Pill on left, View Analysis link on right */}
              <div className="card-bottom-actions">
                <span className={`pill-badge ${mod.status === 'Critical' ? 'badge-critical' : mod.status === 'Healthy' ? 'badge-healthy' : 'badge-at-risk'}`}>
                  {mod.status}
                </span>

                <span className="view-analysis-link">
                  <span>View Analysis</span>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
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
