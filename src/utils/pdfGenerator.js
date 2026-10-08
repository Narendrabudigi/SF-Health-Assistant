/**
 * Enterprise BRD PDF Generator for SAP SuccessFactors Diagnostic Intelligence
 * Exports the complete 8-Section Business Requirements Document (BRD) Plan of Action
 * directly as a downloaded PDF file into the user's browser Downloads.
 */

// Helper to load html2pdf.js dynamically if not already present
function loadHtml2Pdf() {
  if (typeof window !== 'undefined' && window.html2pdf) {
    return Promise.resolve(window.html2pdf);
  }

  return new Promise((resolve, reject) => {
    if (typeof window !== 'undefined' && window.html2pdf) {
      return resolve(window.html2pdf);
    }

    const cdnUrls = [
      'https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js',
      'https://cdn.jsdelivr.net/npm/html2pdf.js@0.10.1/dist/html2pdf.bundle.min.js',
      'https://unpkg.com/html2pdf.js@0.10.1/dist/html2pdf.bundle.min.js'
    ];

    let currentIdx = 0;

    function tryNext() {
      if (typeof window !== 'undefined' && window.html2pdf) {
        return resolve(window.html2pdf);
      }
      if (currentIdx >= cdnUrls.length) {
        return reject(new Error('Failed to load html2pdf from CDNs'));
      }

      const script = document.createElement('script');
      script.src = cdnUrls[currentIdx++];
      script.async = true;
      script.onload = () => {
        if (typeof window !== 'undefined' && window.html2pdf) {
          resolve(window.html2pdf);
        } else {
          tryNext();
        }
      };
      script.onerror = () => tryNext();
      document.head.appendChild(script);
    }

    // Quick poll for existing script tag in case it is already finishing
    let elapsed = 0;
    const interval = setInterval(() => {
      elapsed += 50;
      if (typeof window !== 'undefined' && window.html2pdf) {
        clearInterval(interval);
        return resolve(window.html2pdf);
      }
      if (elapsed >= 800) {
        clearInterval(interval);
        tryNext();
      }
    }, 50);
  });
}

// Fallback to trigger direct file download as standalone HTML if PDF engine is blocked
function triggerFileDownload(content, filename, mimeType = 'text/html') {
  const blob = new Blob([content], { type: `${mimeType};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => {
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, 400);
}

export async function generateMetricBrdPdf(metric, options = {}) {
  const brdPlan = options.brdPlan || {};
  const missingConfigs = options.missingConfigs || [];
  const systemTouchpoints = options.systemTouchpoints || [];
  const rcaFailureModes = options.rcaFailureModes || [];
  const moduleName = options.moduleName || 'SAP SuccessFactors';

  const { detailedAnalysis, metric: metricName, category, company, standard, status, variance } = metric || {};
  const isCritical = status === 'Critical';

  const currentDate = new Date().toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric'
  });

  const sanitizedFileName = (metricName || 'Metric')
    .replace(/[^a-zA-Z0-9_-]/g, '_')
    .replace(/_+/g, '_');

  const pdfFilename = `BRD_Action_Plan_${sanitizedFileName}.pdf`;

  const rcaPriorityLabels = [
    'P1 • Critical Architecture Gap',
    'P2 • Operational Workflow Latency',
    'P3 • Integration & Sync Reliability'
  ];

  // Self-contained document styled identically to the on-screen BRD specification
  const htmlTemplate = `
    <div class="brd-doc-container" style="
      width: 780px;
      margin: 0 auto;
      background: #ffffff;
      color: #0f172a;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      font-size: 11px;
      line-height: 1.45;
      padding: 24px 28px;
      box-sizing: border-box;
    ">
      <style>
        .brd-doc-container * { box-sizing: border-box; }
        .doc-header { border-bottom: 2px solid #0b4d75; padding-bottom: 12px; margin-bottom: 14px; display: flex; justify-content: space-between; align-items: flex-start; }
        .doc-meta-pre { font-size: 9.5px; text-transform: uppercase; letter-spacing: 0.08em; color: #64748b; font-weight: 700; margin-bottom: 3px; }
        .doc-title { font-size: 19px; font-weight: 800; color: #0b3954; margin-bottom: 4px; }
        .doc-meta-sub { font-size: 10.5px; color: #475569; }
        .badge { display: inline-block; padding: 4px 10px; border-radius: 9999px; font-size: 9.5px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; }
        .badge-critical { background: #fee2e2; color: #991b1b; border: 1px solid #fecaca; }
        .badge-at-risk { background: #fef3c7; color: #92400e; border: 1px solid #fde68a; }
        .badge-healthy { background: #dcfce7; color: #166534; border: 1px solid #bbf7d0; }

        .kpi-strip { display: flex; background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 6px; padding: 10px 14px; margin-bottom: 16px; gap: 12px; }
        .kpi-cell { flex: 1; }
        .kpi-cell-label { font-size: 9px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: #64748b; margin-bottom: 2px; }
        .kpi-cell-value { font-size: 13.5px; font-weight: 800; color: #0f172a; }
        .kpi-cell-value.critical { color: #dc2626; }
        .kpi-cell-value.at-risk { color: #d97706; }
        .kpi-divider { width: 1px; background: #e2e8f0; }

        .diagnostic-card { background: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px; margin-bottom: 14px; page-break-inside: avoid; break-inside: avoid; }
        .diagnostic-card-header { padding: 9px 14px; background: #f8fafc; border-bottom: 1px solid #e2e8f0; display: flex; justify-content: space-between; align-items: center; }
        .diagnostic-card-title { font-size: 12.5px; font-weight: 800; color: #0b3954; }
        .diagnostic-card-subtitle { font-size: 9.5px; color: #64748b; margin-top: 1px; }
        .approved-pill { background: #dcfce7; color: #166534; border: 1px solid #bbf7d0; font-size: 8.5px; font-weight: 700; padding: 2px 7px; border-radius: 9999px; text-transform: uppercase; }
        .diagnostic-card-content { padding: 12px 14px; }

        .analysis-text { font-size: 10.5px; color: #334155; line-height: 1.5; margin-bottom: 8px; }
        .section-subheading { font-size: 11px; font-weight: 700; color: #0f172a; margin-top: 10px; margin-bottom: 6px; }

        .footprint-box { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 5px; padding: 8px 10px; margin-top: 8px; }
        .footprint-header { font-size: 9.5px; font-weight: 700; color: #475569; margin-bottom: 5px; }
        .footprint-chips { display: flex; flex-wrap: wrap; gap: 6px; }
        .footprint-chip { font-size: 9px; font-weight: 600; padding: 2px 8px; border-radius: 4px; border: 1px solid #cbd5e1; background: #ffffff; color: #334155; }
        .chip-core { background: #e0f2fe; color: #0369a1; border-color: #bae6fd; }
        .chip-config { background: #fef3c7; color: #92400e; border-color: #fde68a; }
        .chip-workflow { background: #ede9fe; color: #6d28d9; border-color: #ddd6fe; }
        .chip-integration { background: #dcfce7; color: #166534; border-color: #bbf7d0; }

        .brd-spec-table-container { margin-top: 8px; border: 1px solid #cbd5e1; border-radius: 5px; overflow: hidden; page-break-inside: avoid; break-inside: avoid; }
        .brd-spec-table { width: 100%; border-collapse: collapse; font-size: 10px; text-align: left; }
        .brd-spec-table th { background-color: #0b4d75; color: #ffffff; font-weight: 700; padding: 7px 10px; font-size: 9.5px; border-bottom: 2px solid #083b5a; white-space: nowrap; }
        .brd-spec-table td { padding: 6px 10px; border-bottom: 1px solid #e2e8f0; color: #1e293b; vertical-align: middle; line-height: 1.4; }
        .brd-spec-table tr:last-child td { border-bottom: none; }
        .brd-phase-header-row td { background-color: #e8eff6; color: #0b3954; font-weight: 700; font-size: 9.5px; padding: 7px 10px; border-top: 1px solid #cbd5e1; border-bottom: 1px solid #cbd5e1; }
        .brd-spec-summary-row td { background-color: #f1f5f9; font-weight: 700; color: #0f172a; }

        .workstream-id-badge { font-weight: 700; color: #0b4d75; font-size: 10px; }
        .fixes-driver-badge { display: inline-block; font-weight: 600; color: #334155; font-size: 9px; background: #f1f5f9; padding: 1px 6px; border-radius: 3px; border: 1px solid #e2e8f0; }

        .cfg-summary-banner { display: flex; justify-content: space-between; align-items: center; gap: 12px; background: #fffbeb; border: 1px solid #fde68a; border-left: 4px solid #f59e0b; border-radius: 5px; padding: 8px 12px; margin-bottom: 8px; }
        .cfg-banner-title { font-size: 10.5px; font-weight: 700; color: #92400e; }
        .cfg-banner-desc { font-size: 9.5px; color: #78350f; }
        .cfg-banner-stats { display: flex; gap: 6px; flex-shrink: 0; }
        .cfg-stat-pill { font-size: 9px; font-weight: 700; padding: 2px 7px; border-radius: 9999px; white-space: nowrap; }
        .pill-critical { background: #fee2e2; color: #991b1b; border: 1px solid #fecaca; }
        .pill-high { background: #ffedd5; color: #9a3412; border: 1px solid #fed7aa; }
        .pill-medium { background: #e0f2fe; color: #0369a1; border: 1px solid #bae6fd; }
        .cfg-setting-code { display: inline-block; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 9px; background: #f8fafc; color: #0f172a; padding: 2px 6px; border-radius: 3px; border: 1px solid #e2e8f0; word-break: break-word; }

        .trend-points-strip { display: flex; gap: 8px; margin-top: 6px; }
        .trend-point-chip { flex: 1; background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 4px; padding: 6px 8px; text-align: center; }
        .trend-period { font-size: 8.5px; font-weight: 700; color: #64748b; text-transform: uppercase; display: block; }
        .trend-value { font-size: 11px; font-weight: 800; color: #0f172a; }

        .rca-drivers-split-grid { display: flex; gap: 10px; margin-bottom: 8px; }
        .rca-drivers-split-grid > div { flex: 1; }
        .rca-breakdown-grid { display: flex; gap: 8px; margin-top: 8px; }
        .rca-mode-card { flex: 1; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 5px; padding: 8px 10px; }
        .rca-mode-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
        .rca-step-num { font-size: 9px; font-weight: 800; color: #0284c7; }
        .rca-priority-tag { font-size: 8.5px; font-weight: 700; color: #475569; }
        .rca-mode-title { font-size: 10px; font-weight: 700; color: #0f172a; margin-bottom: 2px; }
        .rca-mode-desc { font-size: 9px; color: #475569; line-height: 1.4; }

        .impact-triad-grid { display: flex; gap: 8px; margin-top: 8px; }
        .impact-triad-card { flex: 1; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 5px; padding: 8px 10px; }
        .triad-title { font-size: 10px; font-weight: 700; color: #0f172a; margin-bottom: 2px; }
        .triad-desc { font-size: 9px; color: #64748b; line-height: 1.35; }

        .brd-target-outcome-banner { margin-top: 10px; padding: 8px 12px; background-color: #f0fdf4; border: 1px solid #86efac; border-radius: 5px; display: flex; align-items: center; gap: 10px; }
        .brd-target-outcome-label { font-weight: 800; font-size: 9px; letter-spacing: 0.05em; color: #166534; white-space: nowrap; }
        .brd-target-outcome-text { font-size: 10px; color: #14532d; font-weight: 600; }

        .criteria-risks-split-grid { display: flex; gap: 12px; }
        .criteria-risks-split-grid > div { flex: 1; }

        .brd-spec-footnote { margin-top: 10px; padding-top: 8px; font-size: 8.5px; color: #64748b; font-style: italic; border-top: 1px dashed #cbd5e1; }
        .doc-footer { border-top: 1px solid #cbd5e1; padding-top: 10px; margin-top: 16px; display: flex; justify-content: space-between; font-size: 9px; color: #94a3b8; }
      </style>

      <!-- Document Header -->
      <header class="doc-header">
        <div>
          <div class="doc-meta-pre">SAP SuccessFactors Enterprise Diagnostic Intelligence • BRD Plan of Action</div>
          <h1 class="doc-title">${metricName || 'Metric Diagnostic Report'}</h1>
          <div class="doc-meta-sub">
            Category: <strong>${category || 'HCM Core'}</strong> • Module: <strong>${moduleName}</strong> • Generated: <strong>${currentDate}</strong>
          </div>
        </div>
        <div>
          <span class="badge ${isCritical ? 'badge-critical' : status === 'Healthy' ? 'badge-healthy' : 'badge-at-risk'}">
            ${status || 'At Risk'}
          </span>
        </div>
      </header>

      <!-- KPI Summary Strip -->
      <div class="kpi-strip">
        <div class="kpi-cell">
          <div class="kpi-cell-label">Current Company Value</div>
          <div class="kpi-cell-value ${isCritical ? 'critical' : 'at-risk'}">${company || 'N/A'}</div>
        </div>
        <div class="kpi-divider"></div>
        <div class="kpi-cell">
          <div class="kpi-cell-label">Benchmark Standard</div>
          <div class="kpi-cell-value">${standard || 'N/A'}</div>
        </div>
        <div class="kpi-divider"></div>
        <div class="kpi-cell">
          <div class="kpi-cell-label">Variance Gap</div>
          <div class="kpi-cell-value ${isCritical ? 'critical' : 'at-risk'}">${variance || 'N/A'}</div>
        </div>
        <div class="kpi-divider"></div>
        <div class="kpi-cell">
          <div class="kpi-cell-label">Remediation Timeline</div>
          <div class="kpi-cell-value" style="color: #0b4d75; font-size: 12.5px;">${brdPlan.timelineAndEffort?.timeline || brdPlan.timeline || '3-4 Weeks'}</div>
        </div>
        <div class="kpi-divider"></div>
        <div class="kpi-cell">
          <div class="kpi-cell-label">Total Specialist Effort</div>
          <div class="kpi-cell-value" style="color: #0b4d75; font-size: 12.5px;">${brdPlan.timelineAndEffort?.totalEffort || `${brdPlan.totalEffortHours || 100} Total Hours`}</div>
        </div>
      </div>

      <!-- SECTION 01: DIAGNOSIS -->
      <div class="diagnostic-card">
        <div class="diagnostic-card-header">
          <div>
            <h2 class="diagnostic-card-title">1. Diagnosis</h2>
            <div class="diagnostic-card-subtitle">Written by the LLM from the ML insights only</div>
          </div>
        </div>
        <div class="diagnostic-card-content">
          ${(options.diagnosisHeadline || detailedAnalysis.headline) ? `
            <div style="margin-bottom: 12px; padding: 10px 14px; background: rgba(239, 68, 68, 0.08); border-left: 4px solid #ef4444; border-radius: 6px; font-weight: 600; font-size: 11.5px; color: #1e293b;">
              🚨 ${options.diagnosisHeadline || detailedAnalysis.headline}
            </div>
          ` : ''}
          ${(options.whyItHappensText || detailedAnalysis.whyItHappens) ? `
            <div style="margin-bottom: 12px;">
              <div style="font-weight: 700; color: #1e293b; margin-bottom: 4px;">🔍 Why It is Happening (Root Cause):</div>
              <p class="analysis-text" style="margin-top: 0; line-height: 1.6;">${options.whyItHappensText || detailedAnalysis.whyItHappens}</p>
            </div>
          ` : ''}
          ${(options.whereItHappensText && options.whereItHappensText !== 'SuccessFactors workflow touchpoints' && options.whereItHappensText !== options.whyItHappensText && options.whereItHappensText !== 'Data not yet fetched from Supabase') ? `
          <div class="footprint-box">
            <div class="footprint-header">
              <strong>Impacted Architecture Touchpoints:</strong> ${options.whereItHappensText}
            </div>
          </div>
          ` : ''}
          ${((options.howToOvercomeList && options.howToOvercomeList.length > 0) || (detailedAnalysis.howToOvercome && detailedAnalysis.howToOvercome.length > 0)) ? `
            <div class="footprint-box" style="margin-top: 12px;">
              <div class="footprint-header" style="margin-bottom: 6px;">
                <strong>💡 Suggestions to Improve:</strong>
              </div>
              <ol style="margin: 0; padding-left: 20px; color: #334155; line-height: 1.5; font-size: 11px;">
                ${(options.howToOvercomeList || detailedAnalysis.howToOvercome).map(sug => `
                  <li style="margin-bottom: 4px;">${sug}</li>
                `).join('')}
              </ol>
            </div>
          ` : ''}
        </div>
      </div>

      <!-- SECTION 02: TREND ANALYSIS -->
      <div class="diagnostic-card">
        <div class="diagnostic-card-header">
          <div>
            <h2 class="diagnostic-card-title">2. Trend Analysis</h2>
            <div class="diagnostic-card-subtitle">Hierarchical Drill-Down Trajectory Tracking (Yearly › Quarterly › Monthly)</div>
          </div>
        </div>
        <div class="diagnostic-card-content">
          <p class="analysis-text">${detailedAnalysis.trendAnalysis?.summary || 'Historical progression analysis tracks deteriorating SLA performance over recent reporting cycles.'}</p>
          ${detailedAnalysis.trendAnalysis?.points && detailedAnalysis.trendAnalysis.points.length > 0 ? `
            <div class="trend-points-strip">
              ${detailedAnalysis.trendAnalysis.points.map(pt => `
                <div class="trend-point-chip">
                  <span class="trend-period">${pt.period}</span>
                  <span class="trend-value">${pt.value}</span>
                </div>
              `).join('')}
            </div>
          ` : ''}
        </div>
      </div>

      <!-- SECTION 03: MISSING CONFIGURATIONS -->
      ${missingConfigs && missingConfigs.length > 0 ? `
      <div class="diagnostic-card">
        <div class="diagnostic-card-header">
          <div>
            <h2 class="diagnostic-card-title">3. Missing Configurations</h2>
            <div class="diagnostic-card-subtitle">System Configuration Gaps, Missing Rules & Governance Inactive Controls</div>
          </div>
        </div>
        <div class="diagnostic-card-content">
          <div class="cfg-summary-banner">
            <div>
              <div class="cfg-banner-title">⚠️ ${missingConfigs.length} Identified Configuration Gaps</div>
              <div class="cfg-banner-desc">Technical audit diagnosed the following missing validation rules, unassigned picklists, and workflow escalation deficits directly driving the variance gap.</div>
            </div>
            <div class="cfg-banner-stats">
              <span class="cfg-stat-pill pill-critical">${missingConfigs.filter(c => c.severity === 'Critical').length} Critical</span>
              <span class="cfg-stat-pill pill-high">${missingConfigs.filter(c => c.severity === 'High').length} High</span>
              <span class="cfg-stat-pill pill-medium">${missingConfigs.filter(c => c.severity === 'Medium').length} Medium</span>
            </div>
          </div>

          <div class="brd-spec-table-container">
            <table class="brd-spec-table">
              <thead>
                <tr>
                  <th style="width: 8%;">ID</th>
                  <th style="width: 24%;">Configuration Component</th>
                  <th style="width: 30%;">Missing Configuration / Deficit</th>
                  <th style="width: 12%;">Severity</th>
                  <th style="width: 26%;">Recommended Target Configuration</th>
                </tr>
              </thead>
              <tbody>
                ${missingConfigs.map(c => `
                  <tr>
                    <td><span class="workstream-id-badge">${c.id}</span></td>
                    <td><strong>${c.component}</strong></td>
                    <td>
                      <div style="font-weight: 600; color: #0f172a;">${c.title}</div>
                      <div style="font-size: 8.5px; color: #64748b; margin-top: 1px;">Current Status: <span style="color: #b91c1c; font-weight: 600;">${c.status}</span></div>
                    </td>
                    <td>
                      <span class="badge ${c.severity === 'Critical' ? 'badge-critical' : c.severity === 'High' ? 'badge-at-risk' : 'badge-healthy'}">
                        ${c.severity}
                      </span>
                    </td>
                    <td><code class="cfg-setting-code">${c.setting}</code></td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        </div>
      </div>
      ` : ''}

      <!-- SECTION 04: ROOT CAUSE ANALYSIS -->
      <div class="diagnostic-card">
        <div class="diagnostic-card-header">
          <div>
            <h2 class="diagnostic-card-title">4. Root Cause Analysis</h2>
            <div class="diagnostic-card-subtitle">${brdPlan?.stageDrivers ? 'What is causing the breach, rendered from the ML insight JSON' : 'Deep Failure Modes & Systemic Diagnostic Trace'}</div>
          </div>
        </div>
        <div class="diagnostic-card-content">
          ${brdPlan?.stageDrivers ? `
            <div class="rca-drivers-split-grid">
              <div class="brd-spec-table-container">
                <table class="brd-spec-table">
                  <thead>
                    <tr>
                      <th style="width: 45%;">Stage driver</th>
                      <th style="width: 25%;">Avg days</th>
                      <th style="width: 20%;">Share of breach</th>
                      <th style="width: 10%;">ID</th>
                    </tr>
                  </thead>
                  <tbody>
                    ${brdPlan.stageDrivers.map(sd => `
                      <tr>
                        <td><strong>${sd.driver}</strong></td>
                        <td>${sd.avgDays}</td>
                        <td>${sd.share}</td>
                        <td><span class="workstream-id-badge">${sd.id}</span></td>
                      </tr>
                    `).join('')}
                  </tbody>
                </table>
              </div>

              ${brdPlan?.segmentDrivers ? `
                <div class="brd-spec-table-container">
                  <table class="brd-spec-table">
                    <thead>
                      <tr>
                        <th style="width: 45%;">Segment driver</th>
                        <th style="width: 25%;">Avg days</th>
                        <th style="width: 20%;">Vs company average</th>
                        <th style="width: 10%;">ID</th>
                      </tr>
                    </thead>
                    <tbody>
                      ${brdPlan.segmentDrivers.map(seg => `
                        <tr>
                          <td><strong>${seg.driver}</strong></td>
                          <td>${seg.avgDays}</td>
                          <td>${seg.vsCompany}</td>
                          <td><span class="workstream-id-badge">${seg.id}</span></td>
                        </tr>
                      `).join('')}
                    </tbody>
                  </table>
                </div>
              ` : ''}
            </div>
          ` : ''}

          ${rcaFailureModes && rcaFailureModes.length > 0 ? `
            <div class="rca-breakdown-grid">
              ${rcaFailureModes.map((item, rIdx) => `
                <div class="rca-mode-card">
                  <div class="rca-mode-header">
                    <span class="rca-step-num">0${rIdx + 1}</span>
                    <span class="rca-priority-tag">${rcaPriorityLabels[rIdx] || item.category}</span>
                  </div>
                  <div class="rca-mode-title">${item.title}</div>
                  <div class="rca-mode-desc">${item.detail}</div>
                </div>
              `).join('')}
            </div>
          ` : ''}
        </div>
      </div>

      <!-- SECTION 05: BUSINESS IMPACT -->
      <div class="diagnostic-card">
        <div class="diagnostic-card-header">
          <div>
            <h2 class="diagnostic-card-title">5. Business & Operational Impact</h2>
            <div class="diagnostic-card-subtitle">Downstream Process, Cost Overrun & Compliance Exposure</div>
          </div>
        </div>
        <div class="diagnostic-card-content">
          <p class="analysis-text">${detailedAnalysis.howItEffects || ''}</p>
          <div class="impact-triad-grid">
            <div class="impact-triad-card">
              <div class="triad-title">💰 Financial Exposure</div>
              <div class="triad-desc">Off-cycle adjustments, replacement recruiting fees & lost productivity overhead</div>
            </div>
            <div class="impact-triad-card">
              <div class="triad-title">⏱️ SLA & Turnaround</div>
              <div class="triad-desc">Process stagnation, managerial escalation queues & extended cycle delays</div>
            </div>
            <div class="impact-triad-card">
              <div class="triad-title">🛡️ Governance & Audit</div>
              <div class="triad-desc">Downstream integration exceptions, compliance findings & security exposure</div>
            </div>
          </div>
        </div>
      </div>

      <!-- SECTION 06: BRD PLAN OF ACTION -->
      ${brdPlan ? `
      <div class="diagnostic-card">
        <div class="diagnostic-card-header">
          <div>
            <h2 class="diagnostic-card-title">
              6. BRD Plan of Action
              <span class="approved-pill">Approved Spec</span>
            </h2>
            <div class="diagnostic-card-subtitle">Resource allocation, specialist hours and sprint timeline</div>
          </div>
        </div>
        <div class="diagnostic-card-content">
          <div class="brd-spec-table-container">
            <table class="brd-spec-table">
              <thead>
                <tr>
                  <th style="width: 56%;">Specialist manpower required</th>
                  <th style="width: 22%;">Headcount</th>
                  <th style="width: 22%;">Effort</th>
                </tr>
              </thead>
              <tbody>
                ${(brdPlan.specialistManpower || []).map(sp => `
                  <tr>
                    <td><strong>${sp.role}</strong></td>
                    <td>${sp.headcount}</td>
                    <td>${sp.effort}</td>
                  </tr>
                `).join('')}
                <tr class="brd-spec-summary-row">
                  <td><strong>Timeline & total effort</strong></td>
                  <td><strong>${brdPlan.timelineAndEffort?.timeline || brdPlan.timeline || '3-4 Weeks'}</strong></td>
                  <td><strong>${brdPlan.timelineAndEffort?.totalEffort || `${brdPlan.totalEffortHours} Total Hours`}</strong></td>
                </tr>
              </tbody>
            </table>
          </div>

          ${brdPlan.phasedActivities && brdPlan.phasedActivities.length > 0 ? `
            <div class="brd-spec-table-container" style="margin-top: 12px;">
              <table class="brd-spec-table">
                <thead>
                  <tr>
                    <th style="width: 40%;">Phase / Activity</th>
                    <th style="width: 38%;">Owner</th>
                    <th style="width: 11%;">Workstream</th>
                    <th style="width: 11%;">Effort</th>
                  </tr>
                </thead>
                <tbody>
                  ${brdPlan.phasedActivities.map(phase => `
                    <tr class="brd-phase-header-row">
                      <td colspan="4">
                        <strong>${phase.phaseName}</strong>
                        ${phase.milestone ? ` | Milestone: ${phase.milestone}` : ''}
                        ${phase.deliverable ? ` | Deliverable: ${phase.deliverable}` : ''}
                      </td>
                    </tr>
                    ${(phase.activities || []).map(act => `
                      <tr>
                        <td>${act.activity}</td>
                        <td style="color: #334155;">${act.owner}</td>
                        <td>
                          ${act.workstream && act.workstream !== '-' ? `<span class="workstream-id-badge">${act.workstream}</span>` : `<span style="color: #94a3b8;">-</span>`}
                        </td>
                        <td style="white-space: nowrap;">${act.effort}</td>
                      </tr>
                    `).join('')}
                  `).join('')}
                  <tr class="brd-spec-summary-row">
                    <td colspan="3"><strong>Total Efforts</strong></td>
                    <td style="white-space: nowrap;"><strong>${brdPlan.totalEffortsDisplay || `${brdPlan.totalEffortHours} Hours`}</strong></td>
                  </tr>
                </tbody>
              </table>
            </div>
          ` : ''}
        </div>
      </div>
      ` : ''}

      <!-- SECTION 07: HOW TO OVERCOME - EXECUTION WORKSTREAMS -->
      ${brdPlan ? `
      <div class="diagnostic-card">
        <div class="diagnostic-card-header">
          <div>
            <h2 class="diagnostic-card-title">7. How to Overcome - Execution Workstreams</h2>
            <div class="diagnostic-card-subtitle">Prescriptive remediation steps, each traced to the root-cause drivers it fixes</div>
          </div>
        </div>
        <div class="diagnostic-card-content">
          ${brdPlan.executionWorkstreams && brdPlan.executionWorkstreams.length > 0 ? `
            <div class="brd-spec-table-container">
              <table class="brd-spec-table">
                <thead>
                  <tr>
                    <th style="width: 8%;">ID</th>
                    <th style="width: 74%;">Remediation step</th>
                    <th style="width: 18%;">Fixes drivers</th>
                  </tr>
                </thead>
                <tbody>
                  ${brdPlan.executionWorkstreams.map(ws => `
                    <tr>
                      <td><strong class="workstream-id-badge">${ws.id}</strong></td>
                      <td>${ws.remediationStep}</td>
                      <td><span class="fixes-driver-badge">${ws.fixesDrivers}</span></td>
                    </tr>
                  `).join('')}
                </tbody>
              </table>
            </div>
          ` : ''}

          ${brdPlan.targetOutcome ? `
            <div class="brd-target-outcome-banner">
              <span class="brd-target-outcome-label">TARGET OUTCOME</span>
              <span class="brd-target-outcome-text">${brdPlan.targetOutcome}</span>
            </div>
          ` : ''}
        </div>
      </div>
      ` : ''}

      <!-- SECTION 08: SUCCESS CRITERIA, ASSUMPTIONS & RISKS -->
      ${brdPlan ? `
      <div class="diagnostic-card">
        <div class="diagnostic-card-header">
          <div>
            <h2 class="diagnostic-card-title">8. Success Criteria, Assumptions & Risks</h2>
            <div class="diagnostic-card-subtitle">Measurable verification targets, implementation dependencies, and risk mitigations</div>
          </div>
        </div>
        <div class="diagnostic-card-content">
          <div class="criteria-risks-split-grid">
            <!-- Success Criteria & Monitoring (WITHOUT "Verified by") -->
            ${brdPlan.successCriteria && brdPlan.successCriteria.length > 0 ? `
              <div>
                <div class="section-subheading" style="margin-top: 0;">Success Criteria & Monitoring</div>
                <div class="brd-spec-table-container">
                  <table class="brd-spec-table">
                    <thead>
                      <tr>
                        <th style="width: 35%;">Criterion</th>
                        <th style="width: 65%;">Target</th>
                      </tr>
                    </thead>
                    <tbody>
                      ${brdPlan.successCriteria.map(sc => `
                        <tr>
                          <td><strong>${sc.criterion}</strong></td>
                          <td>${sc.target}</td>
                        </tr>
                      `).join('')}
                    </tbody>
                  </table>
                </div>
              </div>
            ` : ''}

            <!-- Assumptions & Risks -->
            ${brdPlan.assumptionsAndRisks && brdPlan.assumptionsAndRisks.length > 0 ? `
              <div>
                <div class="section-subheading" style="margin-top: 0;">Assumptions & Risks</div>
                <div class="brd-spec-table-container">
                  <table class="brd-spec-table">
                    <thead>
                      <tr>
                        <th style="width: 20%;">Type</th>
                        <th style="width: 45%;">Description</th>
                        <th style="width: 35%;">Mitigation</th>
                      </tr>
                    </thead>
                    <tbody>
                      ${brdPlan.assumptionsAndRisks.map(ar => `
                        <tr>
                          <td>
                            <span class="badge ${ar.type === 'Risk' ? 'badge-at-risk' : 'badge-healthy'}">
                              ${ar.type}
                            </span>
                          </td>
                          <td>${ar.description}</td>
                          <td>${ar.mitigation}</td>
                        </tr>
                      `).join('')}
                    </tbody>
                  </table>
                </div>
              </div>
            ` : ''}
          </div>

          <!-- Footnote -->
          <div class="brd-spec-footnote">
            ${brdPlan.footnote
        ? brdPlan.footnote.replace('Sections 1, 3 and 4', 'Sections 1, 2, 3 and 4').replace('Sections 2 and 5-9', 'Sections 5–8')
        : 'Sections 1, 2, 3 and 4 are rendered directly from telemetry, trend analysis, and configuration audit scans. Sections 5–8 are generated under the system prompt; effort and staffing are indicative estimates.'}
          </div>
        </div>
      </div>
      ` : ''}

      <!-- Document Footer -->
      <footer class="doc-footer">
        <span>CONFIDENTIAL • FOR INTERNAL ENTERPRISE REMEDIATION ONLY</span>
        <span>Powered by SAP SuccessFactors Enterprise Health Engine</span>
      </footer>
    </div>
  `;

  // Create temporary rendering container attached to DOM
  // Must be position: absolute at (0, 0) so html2canvas computes valid bounding coordinates
  const renderContainer = document.createElement('div');
  renderContainer.id = 'brd-pdf-render-container';
  renderContainer.style.position = 'absolute';
  renderContainer.style.left = '0';
  renderContainer.style.top = '0';
  renderContainer.style.width = '780px';
  renderContainer.style.background = '#ffffff';
  renderContainer.style.zIndex = '-99999';
  renderContainer.style.pointerEvents = 'none';
  renderContainer.style.opacity = '1';
  renderContainer.style.visibility = 'visible';
  renderContainer.innerHTML = htmlTemplate;

  // Temporarily preserve user's scroll position and align to (0, 0) for pristine canvas capture
  const savedScrollY = window.scrollY || window.pageYOffset || 0;
  const savedScrollX = window.scrollX || window.pageXOffset || 0;

  window.scrollTo(0, 0);
  document.body.appendChild(renderContainer);

  // Allow browser layout engine 200ms to compute element geometry and font metrics
  await new Promise(resolve => setTimeout(resolve, 200));

  try {
    const html2pdf = await loadHtml2Pdf();

    const pdfOptions = {
      margin: [10, 8, 10, 8], // top, left, bottom, right in mm
      filename: pdfFilename,
      image: { type: 'jpeg', quality: 0.98 },
      html2canvas: {
        scale: 2,
        useCORS: true,
        logging: false,
        scrollX: 0,
        scrollY: 0,
        x: 0,
        y: 0,
        width: 780,
        windowWidth: 780
      },
      jsPDF: {
        unit: 'mm',
        format: 'a4',
        orientation: 'portrait'
      },
      pagebreak: {
        mode: ['css', 'legacy']
      }
    };

    // Generate and directly trigger file download in browser
    await html2pdf().set(pdfOptions).from(renderContainer).save();
  } catch (err) {
    console.warn('Direct PDF conversion error, executing fallback file download:', err);
    // Reliable fallback: directly download as complete standalone HTML file
    triggerFileDownload(
      `<!DOCTYPE html><html><head><meta charset="UTF-8"><title>${pdfFilename}</title></head><body>${htmlTemplate}</body></html>`,
      `BRD_Action_Plan_${sanitizedFileName}.html`,
      'text/html'
    );
  } finally {
    window.scrollTo(savedScrollX, savedScrollY);
    if (document.body.contains(renderContainer)) {
      document.body.removeChild(renderContainer);
    }
  }
}

export default generateMetricBrdPdf;
