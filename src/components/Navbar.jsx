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
          {/* Supabase Storage / Backend Telemetry Status Badge */}
          {backendStatus?.isConnected && (
            <div
              className="navbar-telemetry-pill"
              title={
                backendStatus.supabaseConnected
                  ? `Supabase Connected: Bucket '${backendStatus.bucketName}/${backendStatus.folder}' has ${backendStatus.bucketFiles} insight file(s)`
                  : 'FastAPI Backend Online (Supabase credentials pending in backend/.env)'
              }
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                padding: '4px 10px',
                borderRadius: '12px',
                background: backendStatus.supabaseConnected ? 'rgba(16, 185, 129, 0.12)' : 'rgba(56, 189, 248, 0.12)',
                border: `1px solid ${backendStatus.supabaseConnected ? 'rgba(16, 185, 129, 0.3)' : 'rgba(56, 189, 248, 0.3)'}`,
                color: backendStatus.supabaseConnected ? '#34d399' : '#38bdf8',
                fontSize: '11px',
                fontWeight: 600,
                letterSpacing: '0.04em'
              }}
            >
              <span
                style={{
                  width: '7px',
                  height: '7px',
                  borderRadius: '50%',
                  background: backendStatus.supabaseConnected ? '#10b981' : '#38bdf8',
                  boxShadow: `0 0 8px ${backendStatus.supabaseConnected ? '#10b981' : '#38bdf8'}`
                }}
              ></span>
              <span>
                {backendStatus.supabaseConnected
                  ? `SUPABASE: LIVE (${backendStatus.bucketFiles} FILES)`
                  : 'BACKEND: LIVE'}
              </span>
            </div>
          )}

          {isConnected && (
            <div
              className="navbar-telemetry-pill"
              title="Live Telemetry: Connected to SAP SuccessFactors via OData v2 API"
            >
              <span className="status-pulse-dot dot-online"></span>
              <span className="telemetry-label">LIVE</span>
            </div>
          )}

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
