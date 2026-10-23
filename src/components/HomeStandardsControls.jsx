import React from 'react';

export default function HomeStandardsControls({ standardMode, onSelectStandardMode, onOpenUploadModal, hasCustomStandards, compact = false }) {
  const isCustom = standardMode === 'custom';

  return (
    <div className={`home-standards-controls ${compact ? 'home-standards-controls-compact' : ''}`} aria-label="Standards controls">
      <button
        type="button"
        className="home-standards-upload"
        onClick={onOpenUploadModal}
        title={hasCustomStandards ? 'Update Custom Standards' : 'Upload Custom Standards'}
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
          <polyline points="17 8 12 3 7 8" />
          <line x1="12" y1="3" x2="12" y2="15" />
        </svg>
        <span>{hasCustomStandards ? 'Update Standards' : 'Upload Standards'}</span>
      </button>

      <div className="home-standards-toggle" aria-label="Standards selector">
        <button
          type="button"
          className={`home-standards-label ${!isCustom ? 'active' : ''}`}
          onClick={() => onSelectStandardMode('standard')}
          aria-pressed={!isCustom}
        >
          Industrial Standards
        </button>
        <button
          type="button"
          className={`home-standards-switch ${isCustom ? 'checked' : ''}`}
          onClick={() => onSelectStandardMode(isCustom ? 'standard' : 'custom')}
          role="switch"
          aria-checked={isCustom}
          aria-label="Toggle between Industrial Standards and Custom Standards"
        >
          <span />
        </button>
        <button
          type="button"
          className={`home-standards-label ${isCustom ? 'active' : ''}`}
          onClick={() => onSelectStandardMode('custom')}
          aria-pressed={isCustom}
        >
          Custom Standards
        </button>
      </div>
    </div>
  );
}
