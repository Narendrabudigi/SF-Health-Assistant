import React from 'react';

export default function Navbar({
  onGoHome,
  onOpenConnectSystem,
  isConnected,
  backendStatus = {},
  onTriggerRefresh,
  isRefreshing = false
}) {
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

        {/* Right: Actions */}
        <div className="navbar-right">


          {/* Single Optimized Refresh Button: Triggers ML Model -> LLM -> Backend -> UI */}
          <button
            type="button"
            className={`btn-pipeline-refresh ${isRefreshing ? 'is-running' : ''}`}
            onClick={onTriggerRefresh}
            disabled={isRefreshing}
            title="Run Analytics & TreeSHAP ML Model, synthesize GenAI insights, and refresh dashboard"
          >
            <svg 
              className={`pipeline-sync-icon ${isRefreshing ? 'spin-anim' : ''}`}
              width="13" 
              height="13" 
              viewBox="0 0 24 24" 
              fill="none" 
              stroke="currentColor" 
              strokeWidth="2.4" 
              strokeLinecap="round" 
              strokeLinejoin="round"
            >
              <polyline points="23 4 23 10 17 10"></polyline>
              <polyline points="1 20 1 14 7 14"></polyline>
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
            </svg>
            <span>{isRefreshing ? 'Refreshing...' : 'Refresh'}</span>
          </button>

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
