import React from 'react';

export default function Navbar({ onGoHome, onOpenConnectSystem, isConnected }) {
  return (
    <header className="dark-navbar">
      <div className="dark-navbar-inner">
        {/* Left: Official YASH Technologies Logo + Divider + Success Factors Title */}
        <div className="navbar-brand" onClick={onGoHome} role="button" tabIndex={0} title="Back to Overview">
          <div className="yash-logo-badge">
            <img src="/yash-logo.svg" alt="YASH Technologies" className="yash-logo-img" />
          </div>
          <div className="brand-divider"></div>
          <div className="brand-title-group">
            <span className="brand-app-title">SAP SuccessFactors</span>
            <span className="brand-system-tag">HEALTH MONITORING // ENTERPRISE AUDIT</span>
          </div>
        </div>

        {/* Right: Connect System Option */}
        <div className="navbar-right">
          {isConnected && (
            <div 
              className="navbar-telemetry-pill"
              title="Live Telemetry: Connected to SAP SuccessFactors via OData v2 API"
            >
              <span className="status-pulse-dot dot-online"></span>
              <span className="telemetry-label">LIVE</span>
            </div>
          )}

          <button
            className={`btn-connect-system ${isConnected ? 'is-connected' : ''}`}
            onClick={onOpenConnectSystem}
            title={isConnected ? "System Connected (Click to manage)" : "Connect your SAP SuccessFactors system"}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              {isConnected ? (
                <path d="M20 6L9 17l-5-5" strokeLinecap="round" strokeLinejoin="round" />
              ) : (
                <path d="M12 5v14M5 12h14" strokeLinecap="round" strokeLinejoin="round" />
              )}
            </svg>
            <span>{isConnected ? 'System Connected' : 'Connect System'}</span>
          </button>
        </div>
      </div>
    </header>
  );
}
