import React, { useState } from 'react';

export default function ModuleRibbon({ 
  modules, 
  activeModuleId, 
  onSelectModule, 
  onGoHome,
  standardMode = 'standard',
  onSelectStandardMode
}) {
  const [isShaking, setIsShaking] = useState(false);
  const activeModule = modules.find(m => m.id === activeModuleId);

  const triggerShake = () => {
    setIsShaking(true);
    setTimeout(() => setIsShaking(false), 450);
  };

  const handleToggleClick = () => {
    if (standardMode === 'standard') {
      triggerShake();
      onSelectStandardMode('custom');
    } else {
      onSelectStandardMode('standard');
    }
  };

  const handleCustomClick = () => {
    triggerShake();
    onSelectStandardMode('custom');
  };

  const handleIndustrialClick = () => {
    onSelectStandardMode('standard');
  };

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
            return (
              <button
                key={mod.id}
                onClick={() => onSelectModule(mod.id)}
                className={`ribbon-tab-btn ${isActive ? 'active' : ''}`}
                aria-pressed={isActive}
              >
                {mod.name}
              </button>
            );
          })}
        </div>

        {/* Right Area: Status Badge + Industrial vs. Custom Standards Switch */}
        <div className="ribbon-right-controls">
          {activeModule && (
            <div className="ribbon-status-area">
              <span className="ribbon-status-label">Status:</span>
              <span className={`pill-badge ${activeModule.status === 'Critical' ? 'badge-critical' : activeModule.status === 'Healthy' ? 'badge-healthy' : 'badge-at-risk'}`}>
                {activeModule.status}
              </span>
            </div>
          )}

          {/* External Labels: Industrial Standards & Custom Standards with Toggle Switch */}
          <div className="standards-toggle-wrapper" aria-label="Standards Selector">
            <span 
              className={`standards-toggle-label ${standardMode === 'standard' ? 'active' : ''}`}
              onClick={handleIndustrialClick}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => e.key === 'Enter' && handleIndustrialClick()}
              title="Industrial Standards"
            >
              Industrial Standards
            </span>

            <button 
              type="button"
              className={`standards-switch-btn ${standardMode === 'custom' ? 'checked' : ''} ${isShaking ? 'shake-anim' : ''}`}
              onClick={handleToggleClick}
              role="switch"
              aria-checked={standardMode === 'custom'}
              title="Toggle standards mode"
              aria-label="Toggle between Industrial Standards and Custom Standards"
            >
              <span className="standards-switch-thumb"></span>
            </button>

            <span 
              className={`standards-toggle-label ${standardMode === 'custom' ? 'active' : ''}`}
              onClick={handleCustomClick}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => e.key === 'Enter' && handleCustomClick()}
              title="Custom Standards (Upload required)"
            >
              Custom Standards
            </span>
          </div>
        </div>
      </div>
    </nav>
  );
}
