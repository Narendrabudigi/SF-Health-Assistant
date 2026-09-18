// PDF Generator for SAP SuccessFactors Enterprise Health Diagnostic
// Generates a valid PDF 1.4 Business Requirements Document (BRD) Action Plan

import { getBrdPlan } from './brdPlanData';

function escapePdf(str) {
  if (!str) return '';
  return String(str)
    .replace(/\\/g, '\\\\')
    .replace(/\(/g, '\\(')
    .replace(/\)/g, '\\)')
    .replace(/[^\x20-\x7E]/g, (ch) => {
      if (ch === '—' || ch === '–') return '--';
      if (ch === '≤') return '<=';
      if (ch === '≥') return '>=';
      if (ch === '•') return '*';
      if (ch === '“' || ch === '”') return '"';
      if (ch === '‘' || ch === '’') return "'";
      if (ch === '…') return '...';
      return ' ';
    });
}

function wordWrap(text, maxChars = 85) {
  if (!text) return [];
  const words = text.split(' ');
  const lines = [];
  let curLine = '';

  for (const word of words) {
    if ((curLine + (curLine ? ' ' : '') + word).length <= maxChars) {
      curLine += (curLine ? ' ' : '') + word;
    } else {
      if (curLine) lines.push(curLine);
      curLine = word;
    }
  }
  if (curLine) lines.push(curLine);
  return lines;
}

export function generateMetricBrdPdf(metric) {
  if (!metric) return;
  const brd = getBrdPlan(metric);
  const detailedAnalysis = metric.detailedAnalysis || {};

  const metricName = metric.metric || metric.name || 'Metric_Analysis';
  const category = metric.category || 'Core HR';
  const company = metric.company || 'N/A';
  const standard = metric.standard || 'N/A';
  const variance = metric.variance || 'N/A';
  const status = metric.status || 'At Risk';
  const isCritical = status === 'Critical';

  // Coordinate helper: A4 is 595.28 x 841.89 pt
  const H = 841.89;
  const py = (topY) => (H - topY).toFixed(2);

  // ---------------- Page 1 Stream ----------------
  let p1 = [];
  
  // Header background banner (dark navy #0b1a2d)
  p1.push(`0.043 0.102 0.176 rg`);
  p1.push(`0 ${py(75)} 595.28 75 re f`);

  // Header Title & Logo Accent
  p1.push(`0.22 0.74 0.97 rg`); // Cyan accent
  p1.push(`40 ${py(32)} 12 12 re f`);
  p1.push(`1 1 1 rg`); // White
  p1.push(`BT /F2 14 Tf 58 ${py(32)} Td (SAP SuccessFactors -- Enterprise Health Diagnostic) Tj ET`);
  p1.push(`0.58 0.65 0.74 rg`); // Muted slate
  p1.push(`BT /F1 8.5 Tf 40 ${py(52)} Td (BUSINESS REQUIREMENTS DOCUMENT (BRD) & ACTION PLAN // CONFIDENTIAL) Tj ET`);

  // Date and Status badge on right
  const dateStr = new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
  p1.push(`1 1 1 rg`);
  p1.push(`BT /F1 8.5 Tf 460 ${py(52)} Td (Generated: ${escapePdf(dateStr)}) Tj ET`);

  // Status Indicator Box
  if (isCritical) {
    p1.push(`0.99 0.93 0.93 rg`); // light red bg
    p1.push(`470 ${py(36)} 85 20 re f`);
    p1.push(`0.86 0.15 0.15 RG 1 w 470 ${py(36)} 85 20 re S`);
    p1.push(`0.75 0.05 0.05 rg`);
    p1.push(`BT /F2 9.5 Tf 482 ${py(32)} Td (CRITICAL SLA) Tj ET`);
  } else {
    p1.push(`0.99 0.96 0.89 rg`); // light amber bg
    p1.push(`470 ${py(36)} 85 20 re f`);
    p1.push(`0.85 0.55 0.05 RG 1 w 470 ${py(36)} 85 20 re S`);
    p1.push(`0.70 0.40 0.02 rg`);
    p1.push(`BT /F2 9.5 Tf 488 ${py(32)} Td (AT RISK SLA) Tj ET`);
  }

  // Metric Profile Title Box
  let y = 100;
  p1.push(`0.06 0.09 0.16 rg`);
  p1.push(`BT /F2 16 Tf 40 ${py(y)} Td (${escapePdf(metricName)}) Tj ET`);
  y += 16;
  p1.push(`0.39 0.45 0.55 rg`);
  p1.push(`BT /F1 9.5 Tf 40 ${py(y)} Td (Domain Module: ${escapePdf(category)} | Governance Scope: Enterprise Cloud Tenant) Tj ET`);

  // KPI Metrics Table Grid (Current, Benchmark, Variance Gap)
  y += 18;
  p1.push(`0.96 0.98 1.0 rg 40 ${py(y + 44)} 515.28 44 re f`);
  p1.push(`0.85 0.90 0.95 RG 1 w 40 ${py(y + 44)} 515.28 44 re S`);

  // Vertical dividers
  p1.push(`211.76 ${py(y + 44)} m 211.76 ${py(y)} l S`);
  p1.push(`383.52 ${py(y + 44)} m 383.52 ${py(y)} l S`);

  // Column 1
  p1.push(`0.39 0.45 0.55 rg`);
  p1.push(`BT /F1 8 Tf 55 ${py(y + 16)} Td (CURRENT ACTUAL VALUE) Tj ET`);
  p1.push(`0.05 0.10 0.20 rg`);
  p1.push(`BT /F2 13 Tf 55 ${py(y + 34)} Td (${escapePdf(company)}) Tj ET`);

  // Column 2
  p1.push(`0.39 0.45 0.55 rg`);
  p1.push(`BT /F1 8 Tf 226 ${py(y + 16)} Td (BENCHMARK TARGET) Tj ET`);
  p1.push(`0.05 0.10 0.20 rg`);
  p1.push(`BT /F2 13 Tf 226 ${py(y + 34)} Td (${escapePdf(standard)}) Tj ET`);

  // Column 3
  p1.push(`0.39 0.45 0.55 rg`);
  p1.push(`BT /F1 8 Tf 398 ${py(y + 16)} Td (VARIANCE GAP // DEVIATION) Tj ET`);
  if (isCritical) {
    p1.push(`0.86 0.15 0.15 rg`);
  } else {
    p1.push(`0.85 0.50 0.05 rg`);
  }
  p1.push(`BT /F2 13 Tf 398 ${py(y + 34)} Td (${escapePdf(variance)}) Tj ET`);

  y += 60;

  // Section 1: Root Cause Analysis (Why is it happening?)
  p1.push(`0.03 0.52 0.89 rg 40 ${py(y + 18)} 515.28 18 re f`);
  p1.push(`1 1 1 rg`);
  p1.push(`BT /F2 9.5 Tf 48 ${py(y + 13)} Td (01. ROOT CAUSE ANALYSIS & ARCHITECTURE BOTTLENECKS) Tj ET`);
  y += 26;

  const rootCause = detailedAnalysis.whyItHappens || 'Multi-tier operational and system validation bottlenecks.';
  const whereArea = detailedAnalysis.whereItHappens ? `Specific Area: ${detailedAnalysis.whereItHappens}` : '';
  
  if (whereArea) {
    p1.push(`0.15 0.20 0.30 rg`);
    p1.push(`BT /F2 8.5 Tf 44 ${py(y)} Td (${escapePdf(whereArea)}) Tj ET`);
    y += 14;
  }

  p1.push(`0.20 0.25 0.35 rg`);
  const rcLines = wordWrap(rootCause, 95);
  for (const line of rcLines) {
    p1.push(`BT /F1 8.5 Tf 44 ${py(y)} Td (${escapePdf(line)}) Tj ET`);
    y += 12;
  }

  y += 10;

  // Section 2: Trend Analysis (Quarterly Progression)
  p1.push(`0.03 0.52 0.89 rg 40 ${py(y + 18)} 515.28 18 re f`);
  p1.push(`1 1 1 rg`);
  p1.push(`BT /F2 9.5 Tf 48 ${py(y + 13)} Td (02. TREND ANALYSIS & HISTORICAL TRAJECTORY) Tj ET`);
  y += 26;

  const trendSummary = detailedAnalysis.trendAnalysis?.summary || 'Variance has tracked above SLA limits across recent cycles.';
  p1.push(`0.20 0.25 0.35 rg`);
  const tsLines = wordWrap(trendSummary, 95);
  for (const line of tsLines) {
    p1.push(`BT /F1 8.5 Tf 44 ${py(y)} Td (${escapePdf(line)}) Tj ET`);
    y += 12;
  }

  // Trend points chip strip
  if (detailedAnalysis.trendAnalysis?.points) {
    y += 4;
    let chipX = 44;
    for (const pt of detailedAnalysis.trendAnalysis.points) {
      p1.push(`0.93 0.95 0.98 rg ${chipX} ${py(y + 18)} 95 18 re f`);
      p1.push(`0.80 0.85 0.92 RG 0.8 w ${chipX} ${py(y + 18)} 95 18 re S`);
      p1.push(`0.30 0.35 0.45 rg`);
      p1.push(`BT /F1 7.5 Tf ${chipX + 6} ${py(y + 13)} Td (${escapePdf(pt.period)}:) Tj ET`);
      p1.push(`0.05 0.10 0.20 rg`);
      p1.push(`BT /F2 8.5 Tf ${chipX + 50} ${py(y + 13)} Td (${escapePdf(pt.value)}) Tj ET`);
      chipX += 105;
    }
    y += 24;
  }

  y += 10;

  // Section 3: Downstream Business Impact
  p1.push(`0.03 0.52 0.89 rg 40 ${py(y + 18)} 515.28 18 re f`);
  p1.push(`1 1 1 rg`);
  p1.push(`BT /F2 9.5 Tf 48 ${py(y + 13)} Td (03. BUSINESS, SLA & FINANCIAL RISK ASSESSMENT) Tj ET`);
  y += 26;

  const impact = detailedAnalysis.howItEffects || 'Creates compliance exposure, delayed processing timelines, and increased manual administrative burden.';
  p1.push(`0.20 0.25 0.35 rg`);
  const impLines = wordWrap(impact, 95);
  for (const line of impLines) {
    p1.push(`BT /F1 8.5 Tf 44 ${py(y)} Td (${escapePdf(line)}) Tj ET`);
    y += 12;
  }

  // Page 1 Footer
  p1.push(`0.85 0.88 0.92 RG 0.5 w 40 ${py(800)} m 555.28 ${py(800)} l S`);
  p1.push(`0.50 0.55 0.65 rg`);
  p1.push(`BT /F1 7.5 Tf 40 ${py(812)} Td (SAP SuccessFactors Health Monitor -- Document Ref: BRD-${escapePdf(category.toUpperCase().slice(0, 3))}-${Math.floor(1000 + Math.random() * 9000)}) Tj ET`);
  p1.push(`BT /F1 7.5 Tf 500 ${py(812)} Td (Page 1 of 2) Tj ET`);

  const stream1 = p1.join('\n');

  // ---------------- Page 2 Stream (BRD Plan of Action & Manpower) ----------------
  let p2 = [];

  // Header banner on Page 2
  p2.push(`0.043 0.102 0.176 rg`);
  p2.push(`0 ${py(50)} 595.28 50 re f`);
  p2.push(`1 1 1 rg`);
  p2.push(`BT /F2 11 Tf 40 ${py(32)} Td (BRD PLAN OF ACTION & RESOURCE REQUIREMENTS: ${escapePdf(metricName)}) Tj ET`);
  p2.push(`0.58 0.65 0.74 rg`);
  p2.push(`BT /F1 8 Tf 460 ${py(32)} Td (Section 04 // Implementation Spec) Tj ET`);

  let y2 = 70;

  // Section 4 Header
  p2.push(`0.03 0.52 0.89 rg 40 ${py(y2 + 20)} 515.28 20 re f`);
  p2.push(`1 1 1 rg`);
  p2.push(`BT /F2 10 Tf 48 ${py(y2 + 14)} Td (04. BUSINESS REQUIREMENTS DOCUMENT (BRD) -- IMPLEMENTATION PLAN OF ACTION) Tj ET`);
  y2 += 28;

  // Executive Resource Overview Box
  p2.push(`0.97 0.98 1.0 rg 40 ${py(y2 + 48)} 515.28 48 re f`);
  p2.push(`0.80 0.88 0.96 RG 1 w 40 ${py(y2 + 48)} 515.28 48 re S`);

  p2.push(`0.30 0.40 0.55 rg`);
  p2.push(`BT /F2 8 Tf 50 ${py(y2 + 14)} Td (TOTAL WORKFORCE ESTIMATE:) Tj ET`);
  p2.push(`0.05 0.10 0.20 rg`);
  p2.push(`BT /F2 9.5 Tf 190 ${py(y2 + 14)} Td (${escapePdf(brd.totalManpower)}) Tj ET`);

  p2.push(`0.30 0.40 0.55 rg`);
  p2.push(`BT /F2 8 Tf 50 ${py(y2 + 28)} Td (TARGET TIMELINE & CADENCE:) Tj ET`);
  p2.push(`0.05 0.10 0.20 rg`);
  p2.push(`BT /F2 9.5 Tf 190 ${py(y2 + 28)} Td (${escapePdf(brd.timeline)}) Tj ET`);

  p2.push(`0.30 0.40 0.55 rg`);
  p2.push(`BT /F2 8 Tf 50 ${py(y2 + 42)} Td (GOVERNANCE SPONSOR:) Tj ET`);
  p2.push(`0.05 0.10 0.20 rg`);
  p2.push(`BT /F1 8.5 Tf 190 ${py(y2 + 42)} Td (${escapePdf(brd.governanceLead)}) Tj ET`);

  y2 += 58;

  // Workforce Breakdown Table Header
  p2.push(`0.12 0.18 0.28 rg 40 ${py(y2 + 18)} 515.28 18 re f`);
  p2.push(`1 1 1 rg`);
  p2.push(`BT /F2 8 Tf 46 ${py(y2 + 13)} Td (REQUIRED ROLE / SPECIALIZATION) Tj ET`);
  p2.push(`BT /F2 8 Tf 270 ${py(y2 + 13)} Td (HEADCOUNT) Tj ET`);
  p2.push(`BT /F2 8 Tf 330 ${py(y2 + 13)} Td (PERSON-HOURS) Tj ET`);
  p2.push(`BT /F2 8 Tf 410 ${py(y2 + 13)} Td (PRIMARY WORKSTREAM FOCUS) Tj ET`);
  y2 += 18;

  // Workforce Breakdown Rows
  for (let i = 0; i < brd.workforceRequired.length; i++) {
    const wf = brd.workforceRequired[i];
    const rowBg = i % 2 === 0 ? '0.98 0.99 1.0' : '1 1 1';
    p2.push(`${rowBg} rg 40 ${py(y2 + 20)} 515.28 20 re f`);
    p2.push(`0.88 0.90 0.94 RG 0.5 w 40 ${py(y2 + 20)} 515.28 20 re S`);

    p2.push(`0.08 0.12 0.20 rg`);
    p2.push(`BT /F2 8 Tf 46 ${py(y2 + 14)} Td (${escapePdf(wf.role)}) Tj ET`);
    p2.push(`BT /F1 8 Tf 285 ${py(y2 + 14)} Td (${wf.count}) Tj ET`);
    p2.push(`0.03 0.45 0.75 rg`);
    p2.push(`BT /F2 8 Tf 330 ${py(y2 + 14)} Td (${escapePdf(wf.hours)}) Tj ET`);
    p2.push(`0.25 0.30 0.40 rg`);
    p2.push(`BT /F1 7.5 Tf 410 ${py(y2 + 14)} Td (${escapePdf(wf.focus.slice(0, 32))}) Tj ET`);
    y2 += 20;
  }

  y2 += 12;

  // Implementation Milestones
  p2.push(`0.90 0.94 0.98 rg 40 ${py(y2 + 16)} 515.28 16 re f`);
  p2.push(`0.15 0.25 0.40 rg`);
  p2.push(`BT /F2 8.5 Tf 46 ${py(y2 + 12)} Td (IMPLEMENTATION PHASES & SPRINT DELIVERABLES) Tj ET`);
  y2 += 20;

  for (const ms of brd.milestones) {
    p2.push(`0.03 0.52 0.89 rg`);
    p2.push(`BT /F2 8 Tf 46 ${py(y2)} Td ([${escapePdf(ms.phase)}]) Tj ET`);
    p2.push(`0.10 0.15 0.25 rg`);
    p2.push(`BT /F2 8 Tf 135 ${py(y2)} Td (${escapePdf(ms.title)}:) Tj ET`);
    p2.push(`0.30 0.35 0.45 rg`);
    p2.push(`BT /F1 8 Tf 290 ${py(y2)} Td (Deliverable: ${escapePdf(ms.deliverable)}) Tj ET`);
    y2 += 13;
  }

  y2 += 10;

  // Prescriptive Tactical Action Steps
  p2.push(`0.90 0.94 0.98 rg 40 ${py(y2 + 16)} 515.28 16 re f`);
  p2.push(`0.15 0.25 0.40 rg`);
  p2.push(`BT /F2 8.5 Tf 46 ${py(y2 + 12)} Td (PRESCRIPTIVE WORKSTREAM ACTION ITEMS) Tj ET`);
  y2 += 20;

  const actionSteps = brd.actionSteps || [];
  for (let sIdx = 0; sIdx < actionSteps.length; sIdx++) {
    const step = actionSteps[sIdx];
    p2.push(`0.03 0.52 0.89 rg`);
    p2.push(`BT /F2 8 Tf 46 ${py(y2)} Td (${sIdx + 1}.) Tj ET`);
    p2.push(`0.20 0.25 0.35 rg`);
    const stepLines = wordWrap(step, 90);
    for (let lIdx = 0; lIdx < stepLines.length; lIdx++) {
      const line = stepLines[lIdx];
      const indent = lIdx === 0 ? 60 : 60;
      p2.push(`BT /F1 8 Tf ${indent} ${py(y2)} Td (${escapePdf(line)}) Tj ET`);
      y2 += 11;
    }
    y2 += 3;
  }

  y2 += 8;

  // Expected ROI / Business Outcome Callout
  p2.push(`0.93 0.98 0.95 rg 40 ${py(y2 + 28)} 515.28 28 re f`);
  p2.push(`0.20 0.70 0.35 RG 1 w 40 ${py(y2 + 28)} 515.28 28 re S`);
  p2.push(`0.05 0.45 0.20 rg`);
  p2.push(`BT /F2 8 Tf 48 ${py(y2 + 12)} Td (EXPECTED BUSINESS OUTCOME & ROI:) Tj ET`);
  p2.push(`0.10 0.25 0.15 rg`);
  p2.push(`BT /F1 8 Tf 48 ${py(y2 + 22)} Td (${escapePdf(brd.expectedOutcome)}) Tj ET`);

  y2 += 38;

  // Enterprise Governance Sign-Off Block
  p2.push(`0.97 0.98 1.0 rg 40 ${py(y2 + 50)} 515.28 50 re f`);
  p2.push(`0.85 0.88 0.92 RG 1 w 40 ${py(y2 + 50)} 515.28 50 re S`);

  // 3 signoff columns
  p2.push(`BT /F2 7.5 Tf 50 ${py(y2 + 14)} Td (PREPARED BY:) Tj ET`);
  p2.push(`BT /F1 7.5 Tf 50 ${py(y2 + 26)} Td (Lead SuccessFactors Architect) Tj ET`);
  p2.push(`BT /F1 7 Tf 50 ${py(y2 + 38)} Td (Sign: _____________________) Tj ET`);

  p2.push(`BT /F2 7.5 Tf 220 ${py(y2 + 14)} Td (REVIEWED BY:) Tj ET`);
  p2.push(`BT /F1 7.5 Tf 220 ${py(y2 + 26)} Td (Director of HR Operations) Tj ET`);
  p2.push(`BT /F1 7 Tf 220 ${py(y2 + 38)} Td (Sign: _____________________) Tj ET`);

  p2.push(`BT /F2 7.5 Tf 390 ${py(y2 + 14)} Td (APPROVED BY:) Tj ET`);
  p2.push(`BT /F1 7.5 Tf 390 ${py(y2 + 26)} Td (VP / Enterprise Project Sponsor) Tj ET`);
  p2.push(`BT /F1 7 Tf 390 ${py(y2 + 38)} Td (Sign: _____________________) Tj ET`);

  // Page 2 Footer
  p2.push(`0.85 0.88 0.92 RG 0.5 w 40 ${py(800)} m 555.28 ${py(800)} l S`);
  p2.push(`0.50 0.55 0.65 rg`);
  p2.push(`BT /F1 7.5 Tf 40 ${py(812)} Td (SAP SuccessFactors Health Monitor -- BRD Action Plan Confidential) Tj ET`);
  p2.push(`BT /F1 7.5 Tf 500 ${py(812)} Td (Page 2 of 2) Tj ET`);

  const stream2 = p2.join('\n');

  // ---------------- Assemble Compliant PDF 1.4 Binary ----------------
  const objects = [];
  
  // Object 1: Catalog
  objects.push(`1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj`);

  // Object 2: Pages container (2 pages)
  objects.push(`2 0 obj\n<< /Type /Pages /Kids [3 0 R 7 0 R] /Count 2 >>\nendobj`);

  // Object 3: Page 1 definition
  objects.push(`3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595.28 841.89] /Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> /Contents 4 0 R >>\nendobj`);

  // Object 4: Page 1 Content Stream
  objects.push(`4 0 obj\n<< /Length ${stream1.length} >>\nstream\n${stream1}\nendstream\nendobj`);

  // Object 5: Standard Regular Font (Helvetica)
  objects.push(`5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj`);

  // Object 6: Standard Bold Font (Helvetica-Bold)
  objects.push(`6 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>\nendobj`);

  // Object 7: Page 2 definition
  objects.push(`7 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595.28 841.89] /Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> /Contents 8 0 R >>\nendobj`);

  // Object 8: Page 2 Content Stream
  objects.push(`8 0 obj\n<< /Length ${stream2.length} >>\nstream\n${stream2}\nendstream\nendobj`);

  // Build PDF document with exact byte offsets
  let pdf = `%PDF-1.4\n%âãÏÓ\n`;
  const offsets = [];

  for (const obj of objects) {
    offsets.push(pdf.length);
    pdf += obj + '\n';
  }

  const xrefOffset = pdf.length;
  pdf += `xref\n0 ${objects.length + 1}\n`;
  pdf += `0000000000 65535 f \n`;
  for (const offset of offsets) {
    pdf += String(offset).padStart(10, '0') + ` 00000 n \n`;
  }

  pdf += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF\n`;

  // Trigger download as a clean .pdf blob file
  const blob = new Blob([pdf], { type: 'application/pdf' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  const safeFilename = `${metricName.replace(/[^a-zA-Z0-9]/g, '_')}_BRD_Action_Plan.pdf`;
  a.download = safeFilename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);

  setTimeout(() => {
    URL.revokeObjectURL(url);
  }, 2000);

  return safeFilename;
}
