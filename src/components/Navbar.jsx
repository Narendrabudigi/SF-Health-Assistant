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
          <h1 className="brand-app-title">SAP SuccessFactors</h1>
        </div>

        {/* Right: Connect System Option */}
        <div className="navbar-right">
          <button
            className={`btn-connect-system ${isConnected ? 'is-connected' : ''}`}
            onClick={onOpenConnectSystem}
            title={isConnected ? "System Connected (Click to manage)" : "Connect your SAP SuccessFactors system"}
          >
            <span className={`status-pulse-dot ${isConnected ? 'dot-online' : ''}`}></span>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
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
