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
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="2" y="2" width="20" height="8" rx="2" ry="2"></rect>
                <rect x="2" y="14" width="20" height="8" rx="2" ry="2"></rect>
                <line x1="6" y1="6" x2="6.01" y2="6"></line>
                <line x1="6" y1="18" x2="6.01" y2="18"></line>
              </svg>
            </div>
            <div>
              <h3 className="modal-title">SAP SuccessFactors System Integration</h3>
              <p className="modal-subtitle">Connect your enterprise tenant for real-time telemetry, benchmark sync & diagnostics</p>
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
            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '2px' }}>
                <strong style={{ fontSize: '0.92rem' }}>
                  {isConnected ? 'System Live & Connected' : 'System Not Connected (Baseline Mode)'}
                </strong>
                <span className={`pill-badge ${isConnected ? 'badge-healthy' : 'badge-at-risk'}`}>
                  {isConnected ? 'Active Sync' : 'Offline'}
                </span>
              </div>
              <div className="connection-status-sub">
                {isConnected 
                  ? `Authenticated with tenant "${companyId}". Live OData telemetry is actively synchronizing with the health dashboard.` 
                  : 'Enter your SuccessFactors OData API credentials below to authenticate and link live telemetry.'}
              </div>
            </div>
          </div>

          {/* Form Fields */}
          <div className="form-group">
            <label className="form-label">API Data Center & Region</label>
            <select 
              className="form-control" 
              value={datacenter} 
              onChange={(e) => setDatacenter(e.target.value)}
              disabled={isConnected}
            >
              <option value="https://api12preview.sapsf.eu (Europe DC12)">Europe DC12 — api12preview.sapsf.eu (Production)</option>
              <option value="https://api4.successfactors.com (US DC04)">US Central DC04 — api4.successfactors.com</option>
              <option value="https://api8.successfactors.com (US DC08)">US East DC08 — api8.successfactors.com</option>
              <option value="https://api2.successfactors.eu (Europe DC02)">Europe DC02 — api2.successfactors.eu</option>
              <option value="https://api10.successfactors.com (Australia DC10)">Australia DC10 — api10.successfactors.com</option>
            </select>
          </div>

          <div className="form-row">
            <div className="form-group flex-1">
              <label className="form-label">Company ID (Tenant)</label>
              <input 
                type="text" 
                className="form-control" 
                value={companyId} 
                onChange={(e) => setCompanyId(e.target.value)}
                placeholder="e.g. YASH_ENTERPRISE_PRD"
                required
                disabled={isConnected}
              />
            </div>
            <div className="form-group flex-1">
              <label className="form-label">API Service Username</label>
              <input 
                type="text" 
                className="form-control" 
                value={username} 
                onChange={(e) => setUsername(e.target.value)}
                placeholder="e.g. sf_telemetry_svc"
                required
                disabled={isConnected}
              />
            </div>
          </div>

          <div className="form-group">
            <label className="form-label">OAuth 2.0 Secret / Client Certificate</label>
            <input 
              type="password" 
              className="form-control" 
              value={clientSecret} 
              onChange={(e) => setClientSecret(e.target.value)}
              placeholder="Enter OAuth certificate or private token"
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
                  Save & Close
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
                  {isConnecting ? 'Testing Connection...' : 'Connect & Sync System'}
                </button>
              </>
            )}
          </div>
        </form>
      </div>
    </div>
  );
}
