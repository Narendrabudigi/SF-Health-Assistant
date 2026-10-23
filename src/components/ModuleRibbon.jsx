import React from 'react';

const CANONICAL_MODULE_NAMES = {
  ec: 'Employee Central',
  rcm: 'Recruitment',
  onb: 'Onboarding',
  ofb: 'Offboarding',
  ecp: 'Employee Central Payroll'
};

const getBadgeClass = (status) => {
  if (status === 'Critical') return 'badge-critical';
  if (status === 'At Risk') return 'badge-at-risk';
  if (status === 'Healthy') return 'badge-healthy';
  return 'badge-neutral';
};

export default function ModuleRibbon({
  modules,
  activeModuleId,
  onSelectModule,
  onGoHome
}) {
  const activeModule = modules.find(m => m.id === activeModuleId);

  return (
    <nav className="dark-sub-ribbon" aria-label="Module Navigation Ribbon">
      <div className="dark-sub-ribbon-inner">
        {/* Back Button */}
        <button
          className="ribbon-back-button"
          onClick={onGoHome}
          title="Back to Overview"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <line x1="19" y1="12" x2="5" y2="12"></line>
            <polyline points="12 19 5 12 12 5"></polyline>
          </svg>
          <span>Back</span>
        </button>

        <div className="ribbon-v-divider"></div>

        {/* Module Pill Tabs */}
        <div className="ribbon-tabs-list">
          {modules.map((mod) => {
            const isActive = mod.id === activeModuleId;
            const displayName = CANONICAL_MODULE_NAMES[mod.id?.toLowerCase()] || mod.name;
            return (
              <button
                key={mod.id}
                onClick={() => onSelectModule(mod.id)}
                className={`ribbon-tab-btn ${isActive ? 'active' : ''}`}
                aria-pressed={isActive}
              >
                {displayName}
              </button>
            );
          })}
        </div>

        {/* Right Area: Active Module Status */}
        <div className="ribbon-right-controls">
          {activeModule && (
            <div className="ribbon-status-area">
              <span className="ribbon-status-label">Status:</span>
              <span className={`pill-badge ${getBadgeClass(/^n\s*\/\s*a$/i.test(String(activeModule.status || '').trim()) ? 'Process Gaps' : activeModule.status)}`}>
                <span className="badge-dot" aria-hidden="true"></span>
                <span>{/^n\s*\/\s*a$/i.test(String(activeModule.status || '').trim()) ? 'Process Gaps' : activeModule.status}</span>
              </span>
            </div>
          )}

        </div>
      </div>
    </nav>
  );
}

