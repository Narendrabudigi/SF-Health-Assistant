import React, { useState } from 'react';

export default function ConnectSystemModal({ 
  isOpen, 
  onClose, 
  isConnected, 
  onConnect, 
  onDisconnect 
}) {
  const [datacenter, setDatacenter] = useState('https://api12preview.sapsf.eu (Europe DC12)');
  const [companyId, setCompanyId] = useState('YASH_ENTERPRISE_PRD');
  const [username, setUsername] = useState('sf_service_telemetry');
  const [clientSecret, setClientSecret] = useState('••••••••••••••••');
  const [isConnecting, setIsConnecting] = useState(false);
  const [feedbackMsg, setFeedbackMsg] = useState('');

  if (!isOpen) return null;

  const handleTestAndConnect = (e) => {
    e.preventDefault();
    setIsConnecting(true);
    setFeedbackMsg('Testing OData API Handshake & OAuth 2.0 Token...');

    setTimeout(() => {
      setIsConnecting(false);
      onConnect({
        datacenter,
        companyId,
        username
      });
      setFeedbackMsg('Successfully connected to SAP SuccessFactors!');
      setTimeout(() => {
        setFeedbackMsg('');
        onClose();
      }, 900);
    }, 1200);
  };

  const handleDisconnectAction = () => {
    onDisconnect();
    setFeedbackMsg('System disconnected. Reverting to baseline.');
    setTimeout(() => {
      setFeedbackMsg('');
    }, 1500);
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        {/* Modal Header */}
        <div className="modal-header">
          <div className="modal-title-wrap">
            <div className="modal-icon-badge">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
              </svg>
            </div>
            <div>
              <h3 className="modal-title">Connect SAP SuccessFactors System</h3>
              <p className="modal-subtitle">Integrate your SuccessFactors tenant for live health monitoring & telemetry</p>
            </div>
          </div>
          <button className="btn-modal-close" onClick={onClose} aria-label="Close modal">
            ✕
          </button>
        </div>

        {/* Modal Body */}
        <form onSubmit={handleTestAndConnect} className="modal-form">
          {/* Status Alert Banner */}
          <div className={`connection-status-banner ${isConnected ? 'status-active' : 'status-inactive'}`}>
            <span className={`status-indicator-dot ${isConnected ? 'dot-live' : ''}`}></span>
            <div>
              <strong>{isConnected ? 'System Connected' : 'System Not Connected'}</strong>
              <div className="connection-status-sub">
                {isConnected 
                  ? `Active OData link with ${companyId} • Live API Telemetry Connected` 
                  : 'Configure your SuccessFactors API credentials below to connect your instance.'}
              </div>
            </div>
          </div>

          {/* Form Fields */}
          <div className="form-group">
            <label className="form-label">SAP SuccessFactors API Data Center</label>
            <select 
              className="form-control" 
              value={datacenter} 
              onChange={(e) => setDatacenter(e.target.value)}
              disabled={isConnected}
            >
              <option value="https://api12preview.sapsf.eu (Europe DC12)">Europe DC12 (api12preview.sapsf.eu)</option>
              <option value="https://api4.successfactors.com (US DC04)">US Central DC04 (api4.successfactors.com)</option>
              <option value="https://api8.successfactors.com (US DC08)">US East DC08 (api8.successfactors.com)</option>
              <option value="https://api2.successfactors.eu (Europe DC02)">Europe DC02 (api2.successfactors.eu)</option>
              <option value="https://api10.successfactors.com (Australia DC10)">Australia DC10 (api10.successfactors.com)</option>
            </select>
          </div>

          <div className="form-row">
            <div className="form-group flex-1">
              <label className="form-label">Company ID (Tenant ID)</label>
              <input 
                type="text" 
                className="form-control" 
                value={companyId} 
                onChange={(e) => setCompanyId(e.target.value)}
                placeholder="e.g. YASH_GLOBAL_PRD"
                required
                disabled={isConnected}
              />
            </div>
            <div className="form-group flex-1">
              <label className="form-label">API Username / Client ID</label>
              <input 
                type="text" 
                className="form-control" 
                value={username} 
                onChange={(e) => setUsername(e.target.value)}
                placeholder="e.g. sf_service_account"
                required
                disabled={isConnected}
              />
            </div>
          </div>

          <div className="form-group">
            <label className="form-label">API Secret / OAuth Token</label>
            <input 
              type="password" 
              className="form-control" 
              value={clientSecret} 
              onChange={(e) => setClientSecret(e.target.value)}
              placeholder="Enter OAuth certificate or secret token"
              required
              disabled={isConnected}
            />
          </div>

          {feedbackMsg && (
            <div className="feedback-message">
              {feedbackMsg}
            </div>
          )}

          {/* Modal Actions */}
          <div className="modal-footer">
            {isConnected ? (
              <>
                <button 
                  type="button" 
                  className="btn-danger-outline"
                  onClick={handleDisconnectAction}
                >
                  Disconnect System
                </button>
                <button 
                  type="button" 
                  className="btn-primary"
                  onClick={onClose}
                >
                  Done
                </button>
              </>
            ) : (
              <>
                <button 
                  type="button" 
                  className="btn-secondary"
                  onClick={onClose}
                >
                  Cancel
                </button>
                <button 
                  type="submit" 
                  className="btn-primary"
                  disabled={isConnecting}
                >
                  {isConnecting ? 'Connecting...' : 'Connect & Sync System'}
                </button>
              </>
            )}
          </div>
        </form>
      </div>
    </div>
  );
}
