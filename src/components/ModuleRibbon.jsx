import React from 'react';

export default function ModuleRibbon({ 
  modules, 
  activeModuleId, 
  onSelectModule, 
  onGoHome,
  onOpenConnectSystem,
  isConnected
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

        {/* Right Area: Status Badge + Connect System Option */}
        <div className="ribbon-right-controls">
          {activeModule && (
            <div className="ribbon-status-area">
              <span className="ribbon-status-label">Status:</span>
              <span className={`pill-badge ${activeModule.status === 'Critical' ? 'badge-critical' : 'badge-at-risk'}`}>
                {activeModule.status}
              </span>
            </div>
          )}

          {/* Connect System on the Right Top Ribbon */}
          <button 
            className={`ribbon-connect-btn ${isConnected ? 'is-connected' : ''}`}
            onClick={onOpenConnectSystem}
            title={isConnected ? "System Connected to SAP SuccessFactors" : "Connect SAP SuccessFactors System"}
          >
            <span className={`status-pulse-dot ${isConnected ? 'dot-online' : ''}`}></span>
            <span>{isConnected ? 'System Connected' : '+ Connect System'}</span>
          </button>
        </div>
      </div>
    </nav>
  );
}
