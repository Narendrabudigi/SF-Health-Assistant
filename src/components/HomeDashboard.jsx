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
    case 'credit-card': // Employee Central Payroll (green)
      return (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="1" y="4" width="22" height="16" rx="2" ry="2"></rect>
          <line x1="1" y1="10" x2="23" y2="10"></line>
        </svg>
      );
    default:
      return null;
  }
}

export default function HomeDashboard({ modules, onSelectModule }) {
  return (
    <div className="overview-container">
      {/* Title & Subtitle */}
      <div className="overview-heading-wrap">
        <h2 className="overview-main-title">Module Health Overview</h2>
        <p className="overview-sub-title">
          Select any module below to view its health analysis and industry comparison.
        </p>
      </div>

      {/* 5 Neat Cards in a row */}
      <div className="module-cards-row">
        {modules.map((mod) => {
          const isCritical = mod.status === 'Critical';
          return (
            <div 
              key={mod.id} 
              className="overview-card"
              onClick={() => onSelectModule(mod.id)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => e.key === 'Enter' && onSelectModule(mod.id)}
            >
              {/* Rounded Color Icon */}
              <div 
                className="card-icon-box" 
                style={{ backgroundColor: mod.iconBg }}
              >
                <ModuleIcon type={mod.iconType} />
              </div>

              {/* Module Name */}
              <h3 className="card-module-title">{mod.name}</h3>

              {/* Short Description */}
              <p className="card-module-desc">{mod.description}</p>

              {/* Footer: Status Pill on left, View Analysis link on right */}
              <div className="card-bottom-actions">
                <span className={`pill-badge ${isCritical ? 'badge-critical' : 'badge-at-risk'}`}>
                  {mod.status}
                </span>

                <span className="view-analysis-link">
                  View Analysis
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
