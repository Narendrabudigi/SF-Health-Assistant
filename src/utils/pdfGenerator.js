/**
 * Enterprise PDF Generator for SAP SuccessFactors BRD Action Plans
 * Generates and prints an executive-grade BRD document directly from browser.
 */

export function generateMetricBrdPdf(metric, options = {}) {
  const brdPlan = options.brdPlan || {};
  const { detailedAnalysis, metric: metricName, category, company, standard, status, variance } = metric || {};

  const printWindow = window.open('', '_blank', 'width=900,height=750');
  if (!printWindow) {
    alert('Please allow popups to download the BRD Action Plan PDF.');
    return;
  }

  const htmlContent = `
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>BRD Action Plan - ${metricName || 'Metric'}</title>
  <style>
    @page { size: A4; margin: 16mm 14mm 16mm 14mm; }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; }
    body { color: #0f172a; background: #ffffff; padding: 24px; font-size: 13px; line-height: 1.5; }
    
    .header-bar { display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 2px solid #0284c7; padding-bottom: 16px; margin-bottom: 20px; }
    .header-title-block h1 { font-size: 20px; font-weight: 800; color: #07152b; margin-bottom: 4px; }
    .header-title-block .meta { font-size: 11px; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; }
    .badge { display: inline-block; padding: 4px 12px; font-size: 11px; font-weight: 700; border-radius: 9999px; text-transform: uppercase; }
    .badge-critical { background: #fee2e2; color: #b91c1c; }
    .badge-at-risk { background: #fef3c7; color: #b45309; }
    
    .kpi-strip { display: flex; gap: 16px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px 18px; margin-bottom: 24px; }
    .kpi-item { flex: 1; }
    .kpi-label { font-size: 10px; font-weight: 700; color: #64748b; text-transform: uppercase; margin-bottom: 2px; }
    .kpi-value { font-size: 17px; font-weight: 800; color: #0f172a; }
    .kpi-value.critical { color: #dc2626; }
    .kpi-value.at-risk { color: #d97706; }

    .section { margin-bottom: 20px; page-break-inside: avoid; }
    .section-title { font-size: 13px; font-weight: 800; text-transform: uppercase; color: #0284c7; border-left: 4px solid #0284c7; padding-left: 8px; margin-bottom: 8px; letter-spacing: 0.5px; }
    .card { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; padding: 14px 16px; margin-bottom: 12px; }
    .card-title { font-size: 12px; font-weight: 700; color: #1e293b; margin-bottom: 6px; }
    .card-text { font-size: 12px; color: #334155; line-height: 1.6; }

    .role-chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 6px; }
    .role-chip { background: #e0f2fe; color: #0369a1; border: 1px solid #bae6fd; font-size: 11px; padding: 3px 8px; border-radius: 4px; font-weight: 600; }
    
    .steps-list { padding-left: 20px; font-size: 12px; color: #334155; line-height: 1.7; }
    .steps-list li { margin-bottom: 6px; }

    .footer { border-top: 1px solid #e2e8f0; padding-top: 12px; margin-top: 24px; display: flex; justify-content: space-between; font-size: 10px; color: #94a3b8; }
  </style>
</head>
<body>
  <div class="header-bar">
    <div class="header-title-block">
      <div class="meta">SAP SuccessFactors Enterprise Diagnostic Intelligence • BRD Action Plan</div>
      <h1>${metricName || 'Metric Diagnostic Report'}</h1>
      <div class="meta" style="margin-top: 4px;">Category: ${category || 'HCM Operational'} • Generated: ${new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })}</div>
    </div>
    <span class="badge ${status === 'Critical' ? 'badge-critical' : 'badge-at-risk'}">${status || 'At Risk'}</span>
  </div>

  <div class="kpi-strip">
    <div class="kpi-item">
      <div class="kpi-label">Company Actual</div>
      <div class="kpi-value">${company || 'N/A'}</div>
    </div>
    <div class="kpi-item">
      <div class="kpi-label">Benchmark Standard</div>
      <div class="kpi-value">${standard || 'N/A'}</div>
    </div>
    <div class="kpi-item">
      <div class="kpi-label">Variance Gap</div>
      <div class="kpi-value ${status === 'Critical' ? 'critical' : 'at-risk'}">${variance || 'N/A'}</div>
    </div>
    <div class="kpi-item">
      <div class="kpi-label">Remediation Timeline</div>
      <div class="kpi-value" style="font-size: 14px; color: #0284c7;">${brdPlan.timeline || '2 - 4 Weeks'}</div>
    </div>
  </div>

  ${detailedAnalysis ? `
  <div class="section">
    <div class="section-title">01 • Root Cause & Technical Diagnosis</div>
    <div class="card">
      <div class="card-title">Where It Happens</div>
      <div class="card-text">${detailedAnalysis.whereItHappens || 'SuccessFactors core portlets and workflow configurations.'}</div>
    </div>
    <div class="card">
      <div class="card-title">Why It Is Happening (Architecture Bottleneck)</div>
      <div class="card-text">${detailedAnalysis.whyItHappens || 'Data entry and approval delays exceeding SLA thresholds.'}</div>
    </div>
  </div>

  <div class="section">
    <div class="section-title">02 • Downstream Business & Operational Impact</div>
    <div class="card">
      <div class="card-text">${detailedAnalysis.howItEffects || 'Creates compliance deviations and processing bottlenecks.'}</div>
    </div>
  </div>

  <div class="section">
    <div class="section-title">03 • BRD Execution Plan & Resource Allocation</div>
    <div class="card">
      <div class="card-title">Recommended Specialist Manpower (${brdPlan.totalEffortHours || 60} Total Hours)</div>
      <div class="role-chips">
        ${(brdPlan.workforceRequired || []).map(w => `<span class="role-chip">${w.count}x ${w.role} (${w.hours})</span>`).join('')}
      </div>
    </div>

    <div class="card">
      <div class="card-title">Prescriptive Implementation Steps</div>
      <ol class="steps-list">
        ${(detailedAnalysis.howToOvercome || []).map(step => `<li>${step}</li>`).join('')}
      </ol>
    </div>

    ${brdPlan.expectedOutcome ? `
    <div class="card" style="background: #f0fdf4; border-color: #bbf7d0;">
      <div class="card-title" style="color: #166534;">Target Business Outcome</div>
      <div class="card-text" style="color: #15803d; font-weight: 600;">${brdPlan.expectedOutcome}</div>
    </div>` : ''}
  </div>
  ` : ''}

  <div class="footer">
    <span>CONFIDENTIAL • FOR INTERNAL ENTERPRISE REMEDIATION ONLY</span>
    <span>Powered by SAP SuccessFactors Enterprise Health Engine</span>
  </div>

  <script>
    window.onload = function() {
      setTimeout(function() {
        window.print();
      }, 400);
    };
  </script>
</body>
</html>
  `;

  printWindow.document.open();
  printWindow.document.write(htmlContent);
  printWindow.document.close();
}

export default generateMetricBrdPdf;
