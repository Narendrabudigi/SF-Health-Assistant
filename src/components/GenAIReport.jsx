import React from 'react';

export default function GenAIReport({ module }) {
  const { aiReport } = module;

  return (
    <div className="white-panel ai-diagnostic-panel">
      {/* Panel Title */}
      <h2 className="panel-main-title">AI Diagnostic Report</h2>

      {/* Summary Box with Left Blue Accent Border */}
      <div className="ai-summary-callout">
        <p>{aiReport.summary}</p>
      </div>

      {/* Sub-header 1: Where the Issue is Happening */}
      <div className="ai-section-title-wrap">
        <h3 className="ai-section-numbered-title">1. Where the Issue is Happening</h3>
      </div>

      {/* Issues Cards */}
      <div className="ai-issue-cards-list">
        {aiReport.issues.map((issue, idx) => {
          const isCritical = issue.status === 'Critical';
          return (
            <div key={idx} className="ai-issue-item-card">
              <div className="issue-item-header">
                <h4 className="issue-item-name">{issue.title}</h4>
                <span className={`pill-badge ${isCritical ? 'badge-critical' : 'badge-at-risk'}`}>
                  {issue.status}
                </span>
              </div>
              <div className="issue-tag-box">
                <span>{issue.tag}</span>
              </div>
              <p className="issue-desc-text">{issue.description}</p>
            </div>
          );
        })}
      </div>

      {/* Sub-header 2: Why it is Happening */}
      {aiReport.whyItHappens && aiReport.whyItHappens.length > 0 && (
        <div className="ai-sub-block">
          <h3 className="ai-section-numbered-title mt-lg">2. Why It is Happening (Root Cause)</h3>
          <ul className="ai-bullet-list">
            {aiReport.whyItHappens.map((cause, cIdx) => (
              <li key={cIdx} className="bullet-point">{cause}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Sub-header 3: How to Improve */}
      {aiReport.howToImprove && aiReport.howToImprove.length > 0 && (
        <div className="ai-sub-block">
          <h3 className="ai-section-numbered-title mt-lg">3. Suggestions to Improve</h3>
          <ul className="ai-bullet-list">
            {aiReport.howToImprove.map((item, sIdx) => (
              <li key={sIdx} className="bullet-point">{item}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
