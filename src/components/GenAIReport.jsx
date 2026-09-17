function getConciseSentence(text) {
  if (!text) return '';
  const match = text.match(/.*?[.!?](\s|$)/);
  return match ? match[0].trim() : text;
}

export default function GenAIReport({ module, onSelectMetric }) {
  const { aiReport, benchmarks = [] } = module || {};

  // Filter ONLY Critical and At Risk metrics as explicitly mandated
  const issueMetrics = benchmarks.filter(
    (b) => (b.status === 'Critical' || b.status === 'At Risk') && b.detailedAnalysis
  );

  const criticalCount = issueMetrics.filter(m => m.status === 'Critical').length;
  const atRiskCount = issueMetrics.filter(m => m.status === 'At Risk').length;

  const executiveSummary = aiReport?.summary || 
    `${module?.name || 'Module'} currently shows ${criticalCount} Critical and ${atRiskCount} At Risk metric variances against enterprise benchmark targets. Immediate governance and automated remediation steps are recommended to restore SLA compliance.`;

  return (
    <div className="white-panel ai-diagnostic-panel">
      {/* Panel Header */}
      <div className="ai-report-header">
        <span className="swiss-panel-eyebrow">Diagnostic Analysis • AI Insights</span>
        <h2 className="panel-main-title">AI Diagnostic Report</h2>
      </div>

      {/* Executive Summary Callout */}
      <div className="ai-summary-callout">
        <div className="callout-header-tag">
          Executive Summary • {criticalCount} Critical, {atRiskCount} At Risk
        </div>
        <p className="callout-text">{executiveSummary}</p>
      </div>


      {issueMetrics.length === 0 ? (
        <div className="healthy-state-report-callout">
          <div className="healthy-icon-pill">✓</div>
          <div>
            <h4 className="healthy-title">All Module Benchmarks Healthy</h4>
            <p className="healthy-desc">
              Every tracked metric in this module is operating within established SLA parameters. No active SLA breaches or degradation risks detected.
            </p>
          </div>
        </div>
      ) : (
        <>
          {/* Sub-header 1: Where the Issue is Happening (Streamlined Location Cards) */}
          <div className="ai-section-title-wrap">
            <h3 className="ai-section-numbered-title">
              <span className="section-index-num">01</span>
              <span>Where the Issue is Happening ({issueMetrics.length} Active Variances)</span>
            </h3>
          </div>

          {/* Issues Cards dynamically mapped from Critical & At Risk benchmarks */}
          <div className="ai-issue-cards-list">
            {issueMetrics.map((metricRow, idx) => {
              const isCritical = metricRow.status === 'Critical';
              return (
                <div 
                  key={idx} 
                  className={`ai-issue-item-card clickable-issue-card ${isCritical ? 'issue-card-critical' : 'issue-card-at-risk'}`}
                  onClick={() => onSelectMetric && onSelectMetric(metricRow)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (onSelectMetric && (e.key === 'Enter' || e.key === ' ')) {
                      e.preventDefault();
                      onSelectMetric(metricRow);
                    }
                  }}
                  title="Click to view deep dive analysis"
                >
                  <div className="issue-item-header">
                    <div className="issue-title-group">
                      <h4 className="issue-item-name">{metricRow.metric}</h4>
                      <span className="code-tag">{metricRow.category}</span>
                    </div>
                    <span className={`pill-badge ${isCritical ? 'badge-critical' : 'badge-at-risk'}`}>
                      {metricRow.status}
                    </span>
                  </div>

                  <p className="issue-desc-text">
                    {getConciseSentence(metricRow.detailedAnalysis?.howItEffects || metricRow.detailedAnalysis?.whyItHappens)}
                  </p>
                </div>
              );
            })}
          </div>

          {/* Sub-header 2: Why it is Happening (Consolidated Root Causes - Color Accents & Clickable Deep Dive) */}
          <div className="ai-sub-block">
            <h3 className="ai-section-numbered-title mt-lg">
              <span className="section-index-num">02</span>
              <span>Why It is Happening (Metric-Wise Root Cause)</span>
            </h3>
            <ol className="ai-numbered-list">
              {issueMetrics.map((metricRow, cIdx) => {
                const isCritical = metricRow.status === 'Critical';
                return (
                  <li 
                    key={cIdx} 
                    className={`numbered-item issue-root-cause-item clickable-diagnostic-item ${isCritical ? 'cause-critical' : 'cause-at-risk'}`}
                    onClick={() => onSelectMetric && onSelectMetric(metricRow)}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (onSelectMetric && (e.key === 'Enter' || e.key === ' ')) {
                        e.preventDefault();
                        onSelectMetric(metricRow);
                      }
                    }}
                    title={`Click to view deep dive analysis for ${metricRow.metric}`}
                  >
                    <span className="item-counter">{cIdx + 1}</span>
                    <div className="item-content-wrap">
                      <div className="item-metric-headline">
                        <span className="headline-metric-name">{metricRow.metric}</span>
                        <span className={`headline-status-badge ${isCritical ? 'badge-critical' : 'badge-at-risk'}`}>
                          {metricRow.status}
                        </span>
                      </div>
                      <p className="item-text">
                        {getConciseSentence(metricRow.detailedAnalysis?.whyItHappens)}
                      </p>
                    </div>
                  </li>
                );
              })}
            </ol>
          </div>

          {/* Sub-header 3: Suggestions to Improve (Concise Actionable Remediation - Color Accents & Clickable Deep Dive) */}
          <div className="ai-sub-block">
            <h3 className="ai-section-numbered-title mt-lg">
              <span className="section-index-num">03</span>
              <span>Suggestions to Improve (Actionable Remediation)</span>
            </h3>
            <div className="ai-suggestions-metric-groups">
              {issueMetrics.map((metricRow, sIdx) => {
                const actions = metricRow.detailedAnalysis?.howToOvercome || [];
                if (actions.length === 0) return null;
                const isCritical = metricRow.status === 'Critical';
                return (
                  <div 
                    key={sIdx} 
                    className={`metric-suggestion-group clickable-diagnostic-item ${isCritical ? 'suggestion-critical' : 'suggestion-at-risk'}`}
                    onClick={() => onSelectMetric && onSelectMetric(metricRow)}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (onSelectMetric && (e.key === 'Enter' || e.key === ' ')) {
                        e.preventDefault();
                        onSelectMetric(metricRow);
                      }
                    }}
                    title={`Click to view deep dive analysis for ${metricRow.metric}`}
                  >
                    <div className="suggestion-metric-header">
                      <div className="suggestion-header-left">
                        <span className="suggestion-step-num">Step 0{sIdx + 1}</span>
                        <span className="suggestion-metric-label">{metricRow.metric}</span>
                      </div>
                      <span className={`pill-badge ${isCritical ? 'badge-critical' : 'badge-at-risk'}`}>
                        {metricRow.status}
                      </span>
                    </div>
                    <div className="suggestion-action-summary">
                      <p className="suggestion-action-text">
                        <span className="bullet-indicator">›</span>
                        <span>{actions[0]}</span>
                      </p>
                      {actions.length > 1 && (
                        <div className="deepdive-more-tag">
                          +{actions.length - 1} more remediation actions in Deep Dive →
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </>
      )}
    </div>
  );
}


