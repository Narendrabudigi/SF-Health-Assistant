import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { getBrdPlan } from '../utils/brdPlanData';
import { generateMetricBrdPdf } from '../utils/pdfGenerator';

const CATALOG_SECTIONS = [
  { id: 'sec-diagnosis', label: 'Diagnosis', icon: 'help', desc: 'LLM diagnostic synthesis & touchpoints' },
  { id: 'sec-trend', label: 'Trend Analysis', icon: 'trend', desc: 'Progression & trajectory' },
  { id: 'sec-rca', label: 'Root Cause Analysis', icon: 'search', desc: 'Stage & segment breach drivers' },
  { id: 'sec-impact', label: 'Business Impact', icon: 'alert', desc: 'Downstream SLA & financial risk' },
  { id: 'sec-brd', label: 'BRD Plan of Action', icon: 'clipboard', desc: 'Workforce, hours & milestones' },
  { id: 'sec-overcome', label: 'Execution Roadmap', icon: 'check', desc: 'Remediation steps & target ROI' },
  { id: 'sec-criteria', label: 'Success Criteria & Risks', icon: 'target', desc: 'Monitoring targets & mitigations' }
];

// Module-specific technical mapping for Architecture Touchpoints & RCA Failure Modes
function getModuleMapping(moduleId, metricName) {
  switch (moduleId) {
    case 'rcm': // Recruitment
      return {
        touchpoints: [
          { label: 'Career Site Builder (CSB)', type: 'core' },
          { label: 'Candidate Workbench & Requisitions', type: 'config' },
          { label: 'Interview Central & Self-Scheduling', type: 'workflow' },
          { label: 'Offer Approval & DocuSign e-Signature', type: 'integration' }
        ],
        rca: [
          {
            title: 'Top-of-Funnel Inflow & Knock-Out Screening Gaps',
            category: 'Screening Governance',
            detail: 'Absence of mandatory role-specific pre-screening questions and automated qualification scoring allows hundreds of unqualified applicants into recruiter triage queues.'
          },
          {
            title: 'Hiring Manager Scorecard Submission Latency',
            category: 'Panel Coordination',
            detail: 'Lack of automated 24-hour evaluation reminders and mobile-optimized scorecard forms causes multi-day delays between interview rounds.'
          },
          {
            title: 'Offer Package Benchmarking & Approval Chains',
            category: 'Compensation Governance',
            detail: 'Multi-tiered compensation approval hierarchies and outdated salary range bands lead to 6+ day offer turnaround and top-tier candidate drop-off.'
          }
        ]
      };

    case 'onb': // Onboarding
      return {
        touchpoints: [
          { label: 'Onboarding 2.0 Dashboard', type: 'core' },
          { label: 'Pre-Day-1 Candidate Portal', type: 'config' },
          { label: 'IT Asset & Facilities Task Queues', type: 'workflow' },
          { label: 'SAP Work Zone & I-9 / E-Verify', type: 'integration' }
        ],
        rca: [
          {
            title: 'Pre-Day-1 Portal Authentication & Mobile Friction',
            category: 'Pre-Hire Engagement',
            detail: 'New hires experience initial credential setup hurdles and lack mobile magic-link access, leaving essential compliance paperwork pending past Day 1.'
          },
          {
            title: 'Cross-Department IT Hardware Provisioning Desync',
            category: 'Inter-Departmental SLA',
            detail: 'Manual coordination handoffs between HR Operations, IT logistics, and Facilities result in asset readiness falling behind start date schedules.'
          },
          {
            title: 'Manager Assimilation Check-in Governance Deficit',
            category: 'Ramp Governance',
            detail: '30/60/90-day structured review milestones are not linked to Continuous Performance Management (CPM) or auto-synced with calendar invites.'
          }
        ]
      };

    case 'ofb': // Offboarding
      return {
        touchpoints: [
          { label: 'SAP BTP Event Mesh (IAM Webhook)', type: 'integration' },
          { label: 'Active Directory & Okta SSO Sync', type: 'config' },
          { label: 'Separation Clearance Workflows', type: 'workflow' },
          { label: 'Asset Recovery & Exit Portals', type: 'core' }
        ],
        rca: [
          {
            title: 'Event-Triggered IAM De-provisioning Disconnect',
            category: 'Security & Access SLA',
            detail: 'Manual IT ticket dispatch following employee separation creates a multi-hour lag before corporate email, AD credentials, and Okta sessions are terminated.'
          },
          {
            title: 'Sequential Departmental Clearance Bottlenecks',
            category: 'Clearance Throughput',
            detail: 'Routing offboarding clearance sequentially across HR, Finance, IT, and Facilities causes delayed full & final settlements and backlogs.'
          },
          {
            title: 'Knowledge Handover Verification Gaps',
            category: 'Knowledge Governance',
            detail: 'Lack of mandatory digital handover checklists and verified repository sign-offs leads to loss of project context during employee notice periods.'
          }
        ]
      };

    case 'ec': // Employee Central
    default:
      return {
        touchpoints: [
          { label: 'Custom MDF Objects & Extension Portals', type: 'core' },
          { label: 'Biographical & Personal Info Portlets', type: 'config' },
          { label: 'Integration Center CSV Ingestion Pipelines', type: 'integration' },
          { label: 'Employee Central Business Rules Engine', type: 'workflow' }
        ],
        rca: [
          {
            title: 'Unstructured Custom MDF Data Entry Gaps',
            category: 'Data Governance',
            detail: 'High reliance on free-text fields in custom MDF objects leads to non-standard abbreviations and broken downstream payroll sync.'
          },
          {
            title: 'Real-Time Validation Rule Deficits',
            category: 'Validation Architecture',
            detail: 'Absence of mandatory attachment verification rules on National ID portlets enables incomplete employee records to bypass standard approval.'
          },
          {
            title: 'Mass Data Upload Exception Routing Latency',
            category: 'Batch Integration',
            detail: 'Integration Center automated uploads lack real-time email alerting for validation failures, delaying exception resolution by 48+ hours.'
          }
        ]
      };
  }
}

export default function MetricDeepDivePage({ metric, initialMetric, module, onBack, onGoHome, onSelectModule }) {
  const currentMetric = metric || initialMetric;
  const [activeSection, setActiveSection] = useState('sec-diagnosis');
  const [isDownloading, setIsDownloading] = useState(false);
  const [downloadSuccess, setDownloadSuccess] = useState(false);
  const isManualScrollRef = useRef(false);

  if (!currentMetric) return null;

  const {
    detailedAnalysis,
    metric: metricName,
    category,
    company,
    standard,
    status,
    variance
  } = currentMetric;

  const isCritical = status === 'Critical';
  const badgeClass = isCritical
    ? 'badge-critical'
    : status === 'Healthy'
      ? 'badge-healthy'
      : 'badge-at-risk';

  // Scroll to top upon entering a metric deep dive
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'instant' });
  }, [currentMetric]);

  const brdPlan = useMemo(() => getBrdPlan(currentMetric), [currentMetric]);

  // Dynamic module mapping for architecture touchpoints & RCA failure modes
  const moduleMapping = useMemo(() => getModuleMapping(module?.id, metricName), [module?.id, metricName]);
  const systemTouchpoints = moduleMapping.touchpoints;
  const rcaFailureModes = moduleMapping.rca;

  const rcaPriorityLabels = useMemo(() => [
    'P1 • Critical Architecture Gap',
    'P2 • Operational Workflow Latency',
    'P3 • Integration & Sync Reliability'
  ], []);

  // Compute active section progress for catalog
  const activeSectionIndex = useMemo(
    () => Math.max(0, CATALOG_SECTIONS.findIndex(s => s.id === activeSection)),
    [activeSection]
  );
  const progressPercent = useMemo(
    () => Math.round(((activeSectionIndex + 1) / CATALOG_SECTIONS.length) * 100),
    [activeSectionIndex]
  );

  const currentSectionRef = useRef('sec-diagnosis');

  // Smooth scroll to section when clicked in left catalog using native GPU scrollIntoView
  const handleScrollToSection = useCallback((sectionId) => {
    isManualScrollRef.current = true;
    currentSectionRef.current = sectionId;
    setActiveSection(sectionId);

    const element = document.getElementById(sectionId);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    setTimeout(() => {
      isManualScrollRef.current = false;
    }, 750);
  }, []);

  // Cache section DOM elements to avoid document.getElementById queries on every scroll frame
  const renderedSectionsRef = useRef([]);

  useEffect(() => {
    const updateElements = () => {
      renderedSectionsRef.current = CATALOG_SECTIONS
        .map((s) => ({ id: s.id, el: document.getElementById(s.id) }))
        .filter((s) => s.el !== null);
    };
    updateElements();
    const timer = setTimeout(updateElements, 120);
    return () => clearTimeout(timer);
  }, [currentMetric]);

  // Rock-solid hysteresis scroll spy that NEVER flickers or jumps backward when scrolling slowly
  useEffect(() => {
    let ticking = false;
    currentSectionRef.current = 'sec-diagnosis';

    const onScroll = () => {
      if (isManualScrollRef.current) return;
      if (!ticking) {
        window.requestAnimationFrame(() => {
          ticking = false;
          if (isManualScrollRef.current) return;

          const scrollY = window.scrollY || window.pageYOffset || 0;
          const windowHeight = window.innerHeight;
          const documentHeight = document.documentElement.scrollHeight;

          // Retrieve cached section elements (with fallback)
          let renderedSections = (renderedSectionsRef.current || []).filter(s => s && s.el);
          if (renderedSections.length === 0) {
            renderedSections = CATALOG_SECTIONS
              .map((s) => ({ id: s.id, el: document.getElementById(s.id) }))
              .filter((s) => s.el !== null);
            renderedSectionsRef.current = renderedSections;
          }

          if (renderedSections.length === 0) return;

          // 1. Extreme top: Lock to first section
          if (scrollY < 120) {
            currentSectionRef.current = renderedSections[0].id;
            setActiveSection(renderedSections[0].id);
            return;
          }

          // 2. Extreme bottom: Lock to last section
          if (scrollY + windowHeight >= documentHeight - 60) {
            const lastId = renderedSections[renderedSections.length - 1].id;
            currentSectionRef.current = lastId;
            setActiveSection(lastId);
            return;
          }

          // 3. Robust hysteresis-based section tracking:
          const prevActiveId = currentSectionRef.current;
          const currentIdx = renderedSections.findIndex((s) => s.id === prevActiveId);
          const safeCurrentIdx = currentIdx >= 0 ? currentIdx : 0;

          let targetId = prevActiveId;

          // Check sections from bottom up
          for (let i = renderedSections.length - 1; i >= 0; i--) {
            const item = renderedSections[i];
            if (!item || !item.el) continue;
            const rect = item.el.getBoundingClientRect();
            if (i > safeCurrentIdx) {
              // Advancing forward: trigger when top reaches reading zone (<= 150px)
              if (rect.top <= 150) {
                targetId = item.id;
                break;
              }
            } else if (i === safeCurrentIdx) {
              // Current section: only drop back if its top has moved down past 200px (scrolling up)
              if (rect.top > 200) {
                let bestPrev = 0;
                for (let k = 0; k < safeCurrentIdx; k++) {
                  const prevItem = renderedSections[k];
                  if (prevItem && prevItem.el && prevItem.el.getBoundingClientRect().top <= 150) {
                    bestPrev = k;
                  }
                }
                targetId = renderedSections[bestPrev]?.id || prevActiveId;
                break;
              } else {
                targetId = prevActiveId;
                break;
              }
            }
          }

          if (targetId && targetId !== currentSectionRef.current) {
            currentSectionRef.current = targetId;
            setActiveSection(targetId);
          }
        });
        ticking = true;
      }
    };

    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, [currentMetric]);

  const handleDownloadPDF = useCallback(() => {
    setIsDownloading(true);
    setTimeout(() => {
      try {
        generateMetricBrdPdf(currentMetric, { brdPlan });
        setIsDownloading(false);
        setDownloadSuccess(true);
        setTimeout(() => setDownloadSuccess(false), 3000);
      } catch (err) {
        console.error('PDF Generation Error:', err);
        setIsDownloading(false);
      }
    }, 350);
  }, [currentMetric, brdPlan]);

  return (
    <div className="deepdive-page-container">
      {/* 1. Top Compact Breadcrumb & Actions Bar */}
      <div className="deepdive-top-bar">
        <div className="deepdive-breadcrumb-group">
          <button
            type="button"
            className="btn-deepdive-back"
            onClick={onBack}
            title={`Back to ${module?.name || 'Module'} Analysis`}
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="19" y1="12" x2="5" y2="12"></line>
              <polyline points="12 19 5 12 12 5"></polyline>
            </svg>
            <span>Back to {module?.name || 'Module'} Analysis</span>
          </button>

          <div className="deepdive-breadcrumb-trail">
            <button
              type="button"
              className="breadcrumb-link"
              onClick={onGoHome || onBack}
              title="Back to Overview Dashboard"
            >
              SAP SF Health
            </button>
            <span className="breadcrumb-sep">/</span>
            <button
              type="button"
              className="breadcrumb-link"
              onClick={onBack}
              title={`Back to ${module?.name || 'Module'} Analysis`}
            >
              {module?.name || 'Module'}
            </button>
            <span className="breadcrumb-sep">/</span>
            <span className="breadcrumb-active">{metricName} Deep Dive</span>
          </div>
        </div>
      </div>

      {/* 2. Master-Detail Split Layout */}
      <div className="deepdive-split-layout">

        {/* ========================================================
            LEFT COLUMN: DIAGNOSTIC CATALOG (TRACKER & PROGRESS)
           ======================================================== */}
        <aside className="deepdive-catalog-col" aria-label="Diagnostic Catalog">
          <div className="catalog-panel">
            {/* Catalog Header with Progress Tracker */}
            <div className="catalog-header">
              <div className="catalog-title-wrap">
                <span className="catalog-title">Diagnostic Catalog</span>
                <span className={`pill-badge ${badgeClass}`}>{status}</span>
              </div>
              <div className="catalog-metric-heading">{metricName}</div>
              <span className="catalog-sub">{category} • {module?.name || 'Module'}</span>

              {/* Step Progress Tracker */}
              <div className="catalog-progress-box">
                <div className="catalog-progress-info">
                  <span className="catalog-progress-label">Section {activeSectionIndex + 1} of {CATALOG_SECTIONS.length}</span>
                </div>
                <div className="catalog-progress-track">
                  <div
                    className="catalog-progress-bar"
                    style={{ width: `${progressPercent}%` }}
                  />
                </div>
              </div>
            </div>

            {/* Catalog Section Navigation Items */}
            <nav className="catalog-nav-list" aria-label="Diagnostic Sections">
              {CATALOG_SECTIONS.map((sec) => {
                const isActive = activeSection === sec.id;
                return (
                  <button
                    key={sec.id}
                    type="button"
                    className={`catalog-nav-item ${isActive ? 'catalog-nav-active' : ''}`}
                    onClick={() => handleScrollToSection(sec.id)}
                  >
                    <div className="catalog-nav-left">
                      <div className="catalog-nav-text">
                        <span className="catalog-nav-title">{sec.label}</span>
                        <span className="catalog-nav-desc">{sec.desc}</span>
                      </div>
                    </div>
                    <svg className="catalog-nav-arrow" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                      <polyline points="9 18 15 12 9 6"></polyline>
                    </svg>
                  </button>
                );
              })}
            </nav>
          </div>
        </aside>

        {/* ========================================================
            RIGHT COLUMN: DETAILED ANALYSIS SECTIONS
           ======================================================== */}
        <main className="deepdive-detail-col" aria-label="Detailed Analysis">

          {/* Hero Header Card (Metric Snapshot) */}
          <div className="deepdive-hero-card">
            <div className="deepdive-hero-header">
              <div>
                <div className="deepdive-hero-eyebrow">
                  {category} • Root Cause & Technical Diagnostic
                </div>
                <h1 className="deepdive-hero-title">{metricName}</h1>
              </div>

              <div className="deepdive-hero-badge-wrap">
                <span className={`pill-badge ${badgeClass}`}>{status}</span>
              </div>
            </div>

            {/* 3-KPI Summary Strip */}
            <div className="metric-summary-strip deepdive-strip">
              <div className="summary-stat-cell">
                <span className="stat-cell-label">Current Company Value</span>
                <span className="stat-cell-value current-val">{company}</span>
              </div>
              <div className="summary-stat-divider"></div>
              <div className="summary-stat-cell">
                <span className="stat-cell-label">Benchmark Standard</span>
                <span className="stat-cell-value">{standard}</span>
              </div>
              <div className="summary-stat-divider"></div>
              <div className="summary-stat-cell">
                <span className="stat-cell-label">Variance Gap</span>
                <span className={`stat-cell-value ${isCritical ? 'val-critical' : 'val-at-risk'}`}>
                  {variance}
                </span>
              </div>
            </div>

            {/* Simple Visual Comparison Bar */}
            <div className="simple-comparison-track">
              <div className="track-label-row">
                <span className="track-left-label">Actual Performance: <strong>{company}</strong></span>
                <span className="track-right-label">Target Standard: <strong>{standard}</strong></span>
              </div>
              <div className="track-bar-bg">
                <div
                  className={`track-bar-fill ${isCritical ? 'bg-critical-bar' : status === 'Healthy' ? 'bg-healthy-bar' : 'bg-atrisk-bar'}`}
                  style={{ width: isCritical ? '65%' : status === 'Healthy' ? '98%' : '80%' }}
                />
              </div>
            </div>
          </div>

          {detailedAnalysis ? (
            <div className="deepdive-cards-stack">

              {/* SECTION 02: DIAGNOSIS (MERGED & AUTHORITATIVE - ELIMINATING DUPLICATE WHERE/WHY) */}
              <div id="sec-diagnosis" className="diagnostic-card deepdive-card">
                <div className="diagnostic-card-header">
                  <div className="card-header-text">
                    <h2 className="diagnostic-card-title">2. Diagnosis</h2>
                    <span className="diagnostic-card-subtitle">Written by the LLM from the ML insights only</span>
                  </div>
                </div>
                <div className="diagnostic-card-content">
                  <p className="analysis-text-paragraph">{detailedAnalysis.whyItHappens || detailedAnalysis.whereItHappens}</p>

                  <div className="sf-footprint-box" style={{ marginTop: '16px' }}>
                    <div className="footprint-header">
                      {detailedAnalysis.whereItHappens ? (
                        <span><strong>Impacted Architecture Touchpoints:</strong> {detailedAnalysis.whereItHappens}</span>
                      ) : (
                        'Impacted Architecture Touchpoints:'
                      )}
                    </div>
                    {systemTouchpoints && systemTouchpoints.length > 0 && (
                      <div className="footprint-chips" style={{ marginTop: '8px' }}>
                        {systemTouchpoints.map((tp, idx) => (
                          <span key={idx} className={`footprint-chip chip-${tp.type}`}>
                            {tp.label}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* SECTION 03: TREND ANALYSIS (ALIGNED WITH BRD ORDER) */}
              {detailedAnalysis.trendAnalysis && (
                <div id="sec-trend" className="diagnostic-card deepdive-card">
                  <div className="diagnostic-card-header">
                    <div className="card-header-text">
                      <h2 className="diagnostic-card-title">3. Trend Analysis</h2>
                      <span className="diagnostic-card-subtitle">Quarterly Progression & Trajectory Tracking</span>
                    </div>
                  </div>
                  <div className="diagnostic-card-content">
                    <div className="trend-summary-row">
                      <div className="trend-summary-text">{detailedAnalysis.trendAnalysis.summary}</div>
                      <span className={`trend-status-pill ${isCritical ? 'pill-drift-critical' : 'pill-drift-atrisk'}`}>
                        {isCritical ? 'Trajectory Below SLA' : 'Sub-Optimal Variance'}
                      </span>
                    </div>

                    {detailedAnalysis.trendAnalysis.points && (
                      <div className="trend-visual-container">
                        <div className="trend-points-grid">
                          {detailedAnalysis.trendAnalysis.points.map((pt, pIdx) => {
                            const isCurrent = pIdx === detailedAnalysis.trendAnalysis.points.length - 1;
                            return (
                              <div key={pIdx} className={`trend-visual-card ${isCurrent ? 'trend-card-current' : ''}`}>
                                <div className="trend-card-quarter">{pt.period}</div>
                                <div className="trend-card-bar-wrap">
                                  <div
                                    className={`trend-card-bar-fill ${isCurrent ? (isCritical ? 'bar-critical' : 'bar-atrisk') : 'bar-historical'}`}
                                    style={{ height: `${48 + (pIdx * 14)}%` }}
                                  />
                                </div>
                                <div className="trend-card-value">{pt.value}</div>
                                {isCurrent && <span className="trend-current-tag">Current</span>}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* SECTION 04: ROOT CAUSE ANALYSIS (ALIGNED WITH BRD ORDER) */}
              <div id="sec-rca" className="diagnostic-card deepdive-card">
                <div className="diagnostic-card-header">
                  <div className="card-header-text">
                    <h2 className="diagnostic-card-title">4. Root Cause Analysis</h2>
                    <span className="diagnostic-card-subtitle">
                      {brdPlan?.stageDrivers ? 'What is causing the breach, rendered from the ML insight JSON' : 'Deep Failure Modes & Systemic Diagnostic Trace'}
                    </span>
                  </div>
                </div>
                <div className="diagnostic-card-content">
                  {brdPlan?.stageDrivers && (
                    <div className="rca-drivers-split-grid">
                      <div className="brd-spec-table-container">
                        <table className="brd-spec-table">
                          <thead>
                            <tr>
                              <th style={{ width: '45%' }}>Stage driver</th>
                              <th style={{ width: '25%' }}>Avg days</th>
                              <th style={{ width: '20%' }}>Share of breach</th>
                              <th style={{ width: '10%' }}>ID</th>
                            </tr>
                          </thead>
                          <tbody>
                            {brdPlan.stageDrivers.map((sd, sIdx) => (
                              <tr key={sIdx}>
                                <td><strong>{sd.driver}</strong></td>
                                <td>{sd.avgDays}</td>
                                <td>{sd.share}</td>
                                <td><span className="workstream-id-badge">{sd.id}</span></td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>

                      {brdPlan?.segmentDrivers && (
                        <div className="brd-spec-table-container">
                          <table className="brd-spec-table">
                            <thead>
                              <tr>
                                <th style={{ width: '45%' }}>Segment driver</th>
                                <th style={{ width: '25%' }}>Avg days</th>
                                <th style={{ width: '20%' }}>Vs company average</th>
                                <th style={{ width: '10%' }}>ID</th>
                              </tr>
                            </thead>
                            <tbody>
                              {brdPlan.segmentDrivers.map((seg, segIdx) => (
                                <tr key={segIdx}>
                                  <td><strong>{seg.driver}</strong></td>
                                  <td>{seg.avgDays}</td>
                                  <td>{seg.vsCompany}</td>
                                  <td><span className="workstream-id-badge">{seg.id}</span></td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </div>
                  )}

                  <div className="rca-breakdown-grid">
                    {rcaFailureModes.map((item, rIdx) => (
                      <div key={rIdx} className="rca-mode-card">
                        <div className="rca-mode-header">
                          <span className="rca-step-num">0{rIdx + 1}</span>
                          <span className="rca-priority-tag">{rcaPriorityLabels[rIdx] || item.category}</span>
                        </div>
                        <h3 className="rca-mode-title">{item.title}</h3>
                        <p className="rca-mode-desc">{item.detail}</p>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* SECTION 05: BUSINESS IMPACT */}
              <div id="sec-impact" className="diagnostic-card deepdive-card">
                <div className="diagnostic-card-header">
                  <div className="card-header-text">
                    <h2 className="diagnostic-card-title">5. Business &amp; Operational Impact</h2>
                    <span className="diagnostic-card-subtitle">Downstream Process, Cost Overrun &amp; Compliance Exposure</span>
                  </div>
                </div>
                <div className="diagnostic-card-content">
                  <p className="analysis-text-paragraph">{detailedAnalysis.howItEffects}</p>

                  <div className="impact-triad-grid">
                    <div className="impact-triad-card triad-cost">
                      <div className="triad-icon">💰</div>
                      <div className="triad-title">Financial Exposure</div>
                      <div className="triad-desc">Off-cycle adjustments, replacement recruiting fees &amp; lost productivity overhead</div>
                    </div>
                    <div className="impact-triad-card triad-sla">
                      <div className="triad-icon">⏱️</div>
                      <div className="triad-title">SLA &amp; Turnaround</div>
                      <div className="triad-desc">Process stagnation, managerial escalation queues &amp; extended cycle delays</div>
                    </div>
                    <div className="impact-triad-card triad-gov">
                      <div className="triad-icon">🛡️</div>
                      <div className="triad-title">Governance &amp; Audit</div>
                      <div className="triad-desc">Downstream integration exceptions, compliance findings &amp; security exposure</div>
                    </div>
                  </div>
                </div>
              </div>

              {/* SECTION 06: BRD PLAN OF ACTION */}
              {brdPlan && (
                <div id="sec-brd" className="diagnostic-card deepdive-card brd-clean-card">
                  <div className="diagnostic-card-header">
                    <div className="card-header-text">
                      <div className="card-badge-row">
                        <h2 className="diagnostic-card-title">6. BRD Plan of Action</h2>
                        <span className="brd-pill-tag">Approved Spec</span>
                      </div>
                      <span className="diagnostic-card-subtitle">
                        Resource allocation, specialist hours and sprint timeline
                      </span>
                    </div>
                  </div>

                  <div className="diagnostic-card-content">
                    {/* Specialist Manpower Required Table */}
                    <div className="brd-spec-table-container">
                      <table className="brd-spec-table">
                        <thead>
                          <tr>
                            <th style={{ width: '56%' }}>Specialist manpower required</th>
                            <th style={{ width: '22%' }}>Headcount</th>
                            <th style={{ width: '22%' }}>Effort</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(brdPlan.specialistManpower || []).map((sp, idx) => (
                            <tr key={idx}>
                              <td><strong>{sp.role}</strong></td>
                              <td>{sp.headcount}</td>
                              <td>{sp.effort}</td>
                            </tr>
                          ))}
                          <tr className="brd-spec-summary-row">
                            <td><strong>Timeline &amp; total effort</strong></td>
                            <td><strong>{brdPlan.timelineAndEffort?.timeline || brdPlan.timeline}</strong></td>
                            <td><strong>{brdPlan.timelineAndEffort?.totalEffort || `${brdPlan.totalEffortHours} Total Hours`}</strong></td>
                          </tr>
                        </tbody>
                      </table>
                    </div>

                    {/* Phased Activities Table */}
                    {brdPlan.phasedActivities && brdPlan.phasedActivities.length > 0 && (
                      <div className="brd-spec-table-container" style={{ marginTop: '20px' }}>
                        <table className="brd-spec-table">
                          <thead>
                            <tr>
                              <th style={{ width: '40%' }}>Phase / Activity</th>
                              <th style={{ width: '38%' }}>Owner</th>
                              <th style={{ width: '11%' }}>Workstream</th>
                              <th style={{ width: '11%' }}>Effort</th>
                            </tr>
                          </thead>
                          <tbody>
                            {brdPlan.phasedActivities.map((phase, pIdx) => (
                              <React.Fragment key={pIdx}>
                                <tr className="brd-phase-header-row">
                                  <td colSpan="4">
                                    <strong>{phase.phaseName}</strong>
                                    {phase.milestone && <span> | Milestone: {phase.milestone}</span>}
                                    {phase.deliverable && <span> | Deliverable: {phase.deliverable}</span>}
                                  </td>
                                </tr>
                                {(phase.activities || []).map((act, aIdx) => (
                                  <tr key={`${pIdx}-${aIdx}`}>
                                    <td>{act.activity}</td>
                                    <td style={{ color: '#334155' }}>{act.owner}</td>
                                    <td>
                                      {act.workstream && act.workstream !== '-' ? (
                                        <span className="workstream-id-badge">{act.workstream}</span>
                                      ) : (
                                        <span style={{ color: '#94a3b8' }}>-</span>
                                      )}
                                    </td>
                                    <td style={{ whiteSpace: 'nowrap' }}>{act.effort}</td>
                                  </tr>
                                ))}
                              </React.Fragment>
                            ))}
                            <tr className="brd-spec-summary-row">
                              <td colSpan="3"><strong>Total Efforts</strong></td>
                              <td style={{ whiteSpace: 'nowrap' }}>
                                <strong>{brdPlan.totalEffortsDisplay || `${brdPlan.totalEffortHours} Hours`}</strong>
                              </td>
                            </tr>
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* SECTION 07: HOW TO OVERCOME - EXECUTION WORKSTREAMS */}
              {brdPlan && (
                <div id="sec-overcome" className="diagnostic-card deepdive-card">
                  <div className="diagnostic-card-header">
                    <div className="card-header-text">
                      <h2 className="diagnostic-card-title">7. How to Overcome - Execution Workstreams</h2>
                      <span className="diagnostic-card-subtitle">
                        Prescriptive remediation steps, each traced to the root-cause drivers it fixes
                      </span>
                    </div>
                  </div>

                  <div className="diagnostic-card-content">
                    {/* Execution Workstreams Matrix */}
                    {brdPlan.executionWorkstreams && brdPlan.executionWorkstreams.length > 0 && (
                      <div className="brd-spec-table-container">
                        <table className="brd-spec-table">
                          <thead>
                            <tr>
                              <th style={{ width: '8%' }}>ID</th>
                              <th style={{ width: '74%' }}>Remediation step</th>
                              <th style={{ width: '18%' }}>Fixes drivers</th>
                            </tr>
                          </thead>
                          <tbody>
                            {brdPlan.executionWorkstreams.map((ws, wIdx) => (
                              <tr key={wIdx}>
                                <td><strong className="workstream-id-badge">{ws.id}</strong></td>
                                <td>{ws.remediationStep}</td>
                                <td><span className="fixes-driver-badge">{ws.fixesDrivers}</span></td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}

                    {/* Target Outcome Banner */}
                    {brdPlan.targetOutcome && (
                      <div className="brd-target-outcome-banner">
                        <span className="brd-target-outcome-label">TARGET OUTCOME</span>
                        <span className="brd-target-outcome-text">{brdPlan.targetOutcome}</span>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* SECTIONS 08 & 09: SUCCESS CRITERIA & RISKS */}
              {brdPlan && (
                <div id="sec-criteria" className="diagnostic-card deepdive-card">
                  <div className="diagnostic-card-header">
                    <div className="card-header-text">
                      <h2 className="diagnostic-card-title">8. Success Criteria &amp; 9. Assumptions &amp; Risks</h2>
                      <span className="diagnostic-card-subtitle">
                        Measurable verification targets, implementation dependencies, and risk mitigations
                      </span>
                    </div>
                  </div>

                  <div className="diagnostic-card-content">
                    <div className="criteria-risks-split-grid">
                      {/* 8. Success Criteria & Monitoring */}
                      {brdPlan.successCriteria && brdPlan.successCriteria.length > 0 && (
                        <div className="criteria-col">
                          <div className="brd-section-subheading" style={{ marginTop: '0px' }}>
                            <span>8. Success Criteria &amp; Monitoring</span>
                          </div>
                          <div className="brd-spec-table-container">
                            <table className="brd-spec-table">
                              <thead>
                                <tr>
                                  <th style={{ width: '25%' }}>Criterion</th>
                                  <th style={{ width: '45%' }}>Target</th>
                                  <th style={{ width: '30%' }}>Verified by</th>
                                </tr>
                              </thead>
                              <tbody>
                                {brdPlan.successCriteria.map((sc, scIdx) => (
                                  <tr key={scIdx}>
                                    <td><strong>{sc.criterion}</strong></td>
                                    <td>{sc.target}</td>
                                    <td>{sc.verifiedBy}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      )}

                      {/* 9. Assumptions & Risks */}
                      {brdPlan.assumptionsAndRisks && brdPlan.assumptionsAndRisks.length > 0 && (
                        <div className="risks-col">
                          <div className="brd-section-subheading" style={{ marginTop: '0px' }}>
                            <span>9. Assumptions &amp; Risks</span>
                          </div>
                          <div className="brd-spec-table-container">
                            <table className="brd-spec-table">
                              <thead>
                                <tr>
                                  <th style={{ width: '18%' }}>Type</th>
                                  <th style={{ width: '47%' }}>Description</th>
                                  <th style={{ width: '35%' }}>Mitigation</th>
                                </tr>
                              </thead>
                              <tbody>
                                {brdPlan.assumptionsAndRisks.map((ar, arIdx) => (
                                  <tr key={arIdx}>
                                    <td>
                                      <span className={`pill-badge ${ar.type === 'Risk' ? 'badge-at-risk' : 'badge-healthy'}`}>
                                        {ar.type}
                                      </span>
                                    </td>
                                    <td>{ar.description}</td>
                                    <td>{ar.mitigation}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      )}
                    </div>

                    {/* Footnote */}
                    {brdPlan.footnote && (
                      <div className="brd-spec-footnote">
                        {brdPlan.footnote}
                      </div>
                    )}
                  </div>
                </div>
              )}

            </div>
          ) : (
            <div className="healthy-state-notice">
              <div className="healthy-icon-pill">✓</div>
              <div>
                <h3 className="healthy-title">Metric Performing Within Benchmark Target</h3>
                <p className="healthy-desc">
                  This metric is operating in a Healthy state without active SLA breaches or downstream bottlenecks. Detailed diagnostic deep-dive is only generated for Critical and At Risk performance indicators.
                </p>
              </div>
            </div>
          )}
        </main>
      </div>

      {/* Floating Expandable Download BRD Button (Rendered directly into document.body to stay fixed across the entire scroll!) */}
      {typeof document !== 'undefined' && createPortal(
        <div className="fab-download-container">
          <button
            type="button"
            className={`fab-download-btn ${downloadSuccess ? 'fab-download-success' : ''}`}
            onClick={handleDownloadPDF}
            disabled={isDownloading}
            aria-label="Download BRD Plan (PDF)"
            title="Download BRD Plan (PDF)"
          >
            <span className="fab-icon-box" aria-hidden="true">
              {downloadSuccess ? (
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="20 6 9 17 4 12"></polyline>
                </svg>
              ) : isDownloading ? (
                <svg className="fab-spinner" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <circle cx="12" cy="12" r="10" strokeDasharray="32" strokeDashoffset="12"></circle>
                </svg>
              ) : (
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                  <polyline points="7 10 12 15 17 10"></polyline>
                  <line x1="12" y1="15" x2="12" y2="3"></line>
                </svg>
              )}
            </span>
            <span className="fab-label-text">
              {downloadSuccess
                ? 'Downloaded (PDF) ✓'
                : isDownloading
                  ? 'Generating PDF...'
                  : 'Download BRD Plan (PDF)'}
            </span>
          </button>
        </div>,
        document.body
      )}
    </div>
  );
}
