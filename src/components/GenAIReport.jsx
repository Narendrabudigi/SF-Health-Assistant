import React from 'react';

export default function GenAIReport({ module }) {
  const { aiReport } = module;

  return (
    <div className="white-panel ai-diagnostic-panel">
      {/* Panel Header */}
      <div className="ai-report-header">
        <span className="swiss-panel-eyebrow">Diagnostic Analysis • AI Insights</span>
        <h2 className="panel-main-title">AI Diagnostic Report</h2>
      </div>

      {/* Executive Summary Callout */}
      <div className="ai-summary-callout">
        <div className="callout-header-tag">Executive Summary</div>
        <p className="callout-text">{aiReport.summary}</p>
      </div>

      {/* Sub-header 1: Where the Issue is Happening */}
      <div className="ai-section-title-wrap">
        <h3 className="ai-section-numbered-title">
          <span className="section-index-num">1</span>
          <span>Where the Issue is Happening</span>
        </h3>
      </div>

      {/* Issues Cards */}
      <div className="ai-issue-cards-list">
        {aiReport.issues.map((issue, idx) => {
          const isCritical = issue.status === 'Critical';
          return (
            <div key={idx} className="ai-issue-item-card">
              <div className="issue-item-header">
                <h4 className="issue-item-name">{issue.title}</h4>
                <span className={`pill-badge ${issue.status === 'Critical' ? 'badge-critical' : issue.status === 'Healthy' ? 'badge-healthy' : 'badge-at-risk'}`}>
                  {issue.status}
                </span>
              </div>
              <div className="issue-tag-box">
                <span className="code-tag">{issue.tag}</span>
              </div>
              <p className="issue-desc-text">{issue.description}</p>
            </div>
          );
        })}
      </div>

      {/* Sub-header 2: Why it is Happening */}
      {aiReport.whyItHappens && aiReport.whyItHappens.length > 0 && (
        <div className="ai-sub-block">
          <h3 className="ai-section-numbered-title mt-lg">
            <span className="section-index-num">2</span>
            <span>Why It is Happening (Root Cause)</span>
          </h3>
          <ol className="ai-numbered-list">
            {aiReport.whyItHappens.map((cause, cIdx) => (
              <li key={cIdx} className="numbered-item">
                <span className="item-counter">{cIdx + 1}</span>
                <span className="item-text">{cause}</span>
              </li>
            ))}
          </ol>
        </div>
      )}

      {/* Sub-header 3: How to Improve */}
      {aiReport.howToImprove && aiReport.howToImprove.length > 0 && (
        <div className="ai-sub-block">
          <h3 className="ai-section-numbered-title mt-lg">
            <span className="section-index-num">3</span>
            <span>Suggestions to Improve</span>
          </h3>
          <ol className="ai-numbered-list">
            {aiReport.howToImprove.map((item, sIdx) => (
              <li key={sIdx} className="numbered-item">
                <span className="item-counter">{sIdx + 1}</span>
                <span className="item-text">{item}</span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}
