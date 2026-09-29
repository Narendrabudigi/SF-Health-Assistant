import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { getBrdPlan } from '../utils/brdPlanData';
import { generateMetricBrdPdf } from '../utils/pdfGenerator';

const CATALOG_SECTIONS = [
  { id: 'sec-where', key: 'WHERE', label: 'Where It Happens', icon: 'location', desc: 'Architecture touchpoints & portlets' },
  { id: 'sec-why', key: 'WHY', label: 'Why It Happens', icon: 'help', desc: 'Technical bottlenecks & direct cause' },
  { id: 'sec-rca', key: 'RCA', label: 'Root Cause Analysis', icon: 'search', desc: 'Deep failure modes & systemic gaps' },
  { id: 'sec-trend', key: 'TREND', label: 'Historical Trend', icon: 'trend', desc: 'Quarterly telemetry & trajectory' },
  { id: 'sec-impact', key: 'IMPACT', label: 'Business Impact', icon: 'alert', desc: 'Downstream SLA & financial risk' },
  { id: 'sec-brd', key: 'BRD PLAN', label: 'BRD Plan of Action', icon: 'clipboard', desc: 'Workforce, hours & milestones' },
  { id: 'sec-overcome', key: 'HOW TO OVERCOME', label: 'Execution Roadmap', icon: 'check', desc: 'Remediation steps & target ROI' }
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
          { label: 'Employee Central Core', type: 'core' },
          { label: 'Custom MDF Objects', type: 'config' },
          { label: 'Integration Center / OData', type: 'integration' },
          { label: 'Intelligent Services Rules', type: 'workflow' }
        ],
        rca: [
          {
            title: 'Data Ingestion & Field Mask Gaps',
            category: 'Architecture Vulnerability',
            detail: 'Absence of mandatory effective-dating and strict picklist validation on custom MDF portlets allows unverified records into production tables.'
          },
          {
            title: 'Workflow Delegation Latency',
            category: 'Approval Governance',
            detail: 'Static approval chains without dynamic auto-escalation thresholds trigger multi-day queue stalemates during managerial leave cycles.'
          },
          {
            title: 'Downstream Sync & Audit Lag',
            category: 'Interface Reliability',
            detail: 'Nightly batch sync jobs lack automated failure alerts, leading to silent synchronization backlogs with the Payroll Control Center.'
          }
        ]
      };
  }
}

export default function MetricDeepDivePage({ metric, initialMetric, module, onBack, onGoHome, onSelectModule }) {
  const currentMetric = metric || initialMetric;
  const [activeSection, setActiveSection] = useState('sec-where');
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

  // Smooth scroll to section when clicked in left catalog using native GPU scrollIntoView
  const handleScrollToSection = useCallback((sectionId) => {
    isManualScrollRef.current = true;
    setActiveSection(sectionId);
    
    const element = document.getElementById(sectionId);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    setTimeout(() => {
      isManualScrollRef.current = false;
    }, 700);
  }, []);

  // High-performance IntersectionObserver for section scroll tracking (Zero CPU overhead, no layout thrashing)
  useEffect(() => {
    const sectionIds = CATALOG_SECTIONS.map(s => s.id);
    const elements = sectionIds.map(id => document.getElementById(id)).filter(Boolean);
    if (!elements.length) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (isManualScrollRef.current) return;
        const visible = entries.filter(e => e.isIntersecting);
        if (visible.length > 0) {
          // Sort by proximity to top reading line (75px)
          visible.sort((a, b) => Math.abs(a.boundingClientRect.top - 75) - Math.abs(b.boundingClientRect.top - 75));
          setActiveSection(visible[0].target.id);
        }
      },
      {
        rootMargin: '-75px 0px -40% 0px',
        threshold: [0, 0.25, 0.5, 0.75, 1.0]
      }
    );

    elements.forEach(el => observer.observe(el));

    // Fallback: When scrolled to absolute bottom, ensure the last section is active
    const handleBottomCheck = () => {
      if (isManualScrollRef.current) return;
      const scrollHeight = Math.max(document.documentElement.scrollHeight, document.body.scrollHeight);
      const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
      if (scrollTop + window.innerHeight >= scrollHeight - 120) {
        setActiveSection('sec-overcome');
      }
    };

    window.addEventListener('scroll', handleBottomCheck, { passive: true });

    return () => {
      observer.disconnect();
      window.removeEventListener('scroll', handleBottomCheck);
    };
  }, [currentMetric]);

  const handleDownloadPDF = useCallback(() => {
    setIsDownloading(true);
    setTimeout(() => {
      try {
        generateMetricBrdPdf(currentMetric);
        setIsDownloading(false);
        setDownloadSuccess(true);
        setTimeout(() => setDownloadSuccess(false), 3000);
      } catch (err) {
        console.error('PDF Generation Error:', err);
        setIsDownloading(false);
      }
    }, 350);
  }, [currentMetric]);

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
            LEFT COLUMN: DIAGNOSTIC CATALOG (RCA, WHERE, WHY, BRD...)
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
                  <span className="catalog-progress-pct">{progressPercent}%</span>
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
              {CATALOG_SECTIONS.map((sec, idx) => {
                const isActive = activeSection === sec.id;
                return (
                  <button
                    key={sec.id}
                    type="button"
                    className={`catalog-nav-item ${isActive ? 'catalog-nav-active' : ''}`}
                    onClick={() => handleScrollToSection(sec.id)}
                  >
                    <div className="catalog-nav-left">
                      <span className="catalog-nav-tag">{sec.key}</span>
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
          
          {/* Hero Header Card */}
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
              
              {/* SECTION 01: WHERE IT HAPPENS */}
              <div id="sec-where" className="diagnostic-card deepdive-card">
                <div className="diagnostic-card-header">
                  <span className="card-step-badge">WHERE</span>
                  <div className="card-header-text">
                    <h2 className="diagnostic-card-title">Where It Happens</h2>
                    <span className="diagnostic-card-subtitle">SAP SF Architecture Touchpoints & Manifestation Location</span>
                  </div>
                </div>
                <div className="diagnostic-card-content">
                  {detailedAnalysis.whereItHappens && (
                    <div className="manifestation-chip">
                      <strong>Target System Entities:</strong> {detailedAnalysis.whereItHappens}
                    </div>
                  )}

                  <div className="sf-footprint-box">
                    <div className="footprint-header">Impacted Architecture Layers:</div>
                    <div className="footprint-chips">
                      {systemTouchpoints.map((tp, idx) => (
                        <span key={idx} className={`footprint-chip chip-${tp.type}`}>
                          {tp.label}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              </div>

              {/* SECTION 02: WHY IT HAPPENS */}
              <div id="sec-why" className="diagnostic-card deepdive-card">
                <div className="diagnostic-card-header">
                  <span className="card-step-badge">WHY</span>
                  <div className="card-header-text">
                    <h2 className="diagnostic-card-title">Why It Happens</h2>
                    <span className="diagnostic-card-subtitle">Technical Bottlenecks & Trigger Factors</span>
                  </div>
                </div>
                <div className="diagnostic-card-content">
                  <p className="analysis-text-paragraph">{detailedAnalysis.whyItHappens}</p>
                </div>
              </div>

              {/* SECTION 03: ROOT CAUSE ANALYSIS (RCA) */}
              <div id="sec-rca" className="diagnostic-card deepdive-card">
                <div className="diagnostic-card-header">
                  <span className="card-step-badge">RCA</span>
                  <div className="card-header-text">
                    <h2 className="diagnostic-card-title">Root Cause Analysis (RCA)</h2>
                    <span className="diagnostic-card-subtitle">Deep Failure Modes & Systemic Diagnostic Trace</span>
                  </div>
                </div>
                <div className="diagnostic-card-content">
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

              {/* SECTION 04: HISTORICAL TREND */}
              {detailedAnalysis.trendAnalysis && (
                <div id="sec-trend" className="diagnostic-card deepdive-card">
                  <div className="diagnostic-card-header">
                    <span className="card-step-badge">TREND</span>
                    <div className="card-header-text">
                      <h2 className="diagnostic-card-title">Historical Trend Analysis</h2>
                      <span className="diagnostic-card-subtitle">Quarterly Progression & Trajectory Tracking</span>
                    </div>
                  </div>
                  <div className="diagnostic-card-content">
                    <div className="trend-banner-box">
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

              {/* SECTION 05: BUSINESS IMPACT */}
              <div id="sec-impact" className="diagnostic-card deepdive-card">
                <div className="diagnostic-card-header">
                  <span className="card-step-badge">IMPACT</span>
                  <div className="card-header-text">
                    <h2 className="diagnostic-card-title">Business & Operational Impact</h2>
                    <span className="diagnostic-card-subtitle">Downstream Process, Cost Overrun & Compliance Exposure</span>
                  </div>
                </div>
                <div className="diagnostic-card-content">
                  <p className="analysis-text-paragraph">{detailedAnalysis.howItEffects}</p>

                  <div className="impact-triad-grid">
                    <div className="impact-triad-card triad-cost">
                      <div className="triad-icon">💰</div>
                      <div className="triad-title">Financial Exposure</div>
                      <div className="triad-desc">Off-cycle adjustments, replacement recruiting fees & lost productivity overhead</div>
                    </div>
                    <div className="impact-triad-card triad-sla">
                      <div className="triad-icon">⏱️</div>
                      <div className="triad-title">SLA & Turnaround</div>
                      <div className="triad-desc">Process stagnation, managerial escalation queues & extended cycle delays</div>
                    </div>
                    <div className="impact-triad-card triad-gov">
                      <div className="triad-icon">🛡️</div>
                      <div className="triad-title">Governance & Audit</div>
                      <div className="triad-desc">Downstream integration exceptions, compliance findings & security exposure</div>
                    </div>
                  </div>
                </div>
              </div>

              {/* SECTION 06: BRD PLAN OF ACTION */}
              {brdPlan && (
                <div id="sec-brd" className="diagnostic-card deepdive-card brd-clean-card">
                  <div className="diagnostic-card-header">
                    <span className="card-step-badge">BRD PLAN</span>
                    <div className="card-header-text">
                      <div className="card-badge-row">
                        <h2 className="diagnostic-card-title">BRD Plan of Action</h2>
                        <span className="brd-pill-tag">Approved Spec</span>
                      </div>
                      <span className="diagnostic-card-subtitle">
                        Resource allocation, specialist hours, and sprint timeline
                      </span>
                    </div>
                  </div>

                  <div className="diagnostic-card-content">
                    <div className="brd-compact-strip">
                      <div className="brd-compact-item brd-compact-grow">
                        <span className="brd-compact-label">
                          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                            <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
                            <circle cx="9" cy="7" r="4"></circle>
                            <path d="M23 21v-2a4 4 0 0 0-3-3.87"></path>
                            <path d="M16 3.13a4 4 0 0 1 0 7.75"></path>
                          </svg>
                          Specialist Manpower Required
                        </span>
                        <div className="brd-role-chips">
                          {brdPlan.workforceRequired.map((wf, wIdx) => (
                            <span key={wIdx} className="brd-role-chip">
                              <strong>{wf.count}x</strong> {wf.role} <span className="chip-hrs">({wf.hours})</span>
                            </span>
                          ))}
                        </div>
                      </div>

                      <div className="brd-compact-divider"></div>

                      <div className="brd-compact-item brd-compact-timeline">
                        <span className="brd-compact-label">
                          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                            <circle cx="12" cy="12" r="10"></circle>
                            <polyline points="12 6 12 12 16 14"></polyline>
                          </svg>
                          Timeline & Total Effort
                        </span>
                        <div className="brd-timeline-val">
                          <strong>{brdPlan.timeline}</strong>
                          <span className="brd-effort-badge">{brdPlan.totalEffortHours} Total Hours</span>
                        </div>
                      </div>
                    </div>

                    {/* Phased Milestones */}
                    {brdPlan.milestones && brdPlan.milestones.length > 0 && (
                      <div className="milestones-section-box">
                        <div className="milestones-box-title">Phased Implementation Milestones</div>
                        <div className="milestones-grid-row">
                          {brdPlan.milestones.map((m, mIdx) => (
                            <div key={mIdx} className="milestone-box-card">
                              <span className="milestone-box-phase">{m.phase}</span>
                              <strong className="milestone-box-title">{m.title}</strong>
                              <span className="milestone-box-deliv">{m.deliverable}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* SECTION 07: HOW TO OVERCOME / EXECUTION ROADMAP */}
              {detailedAnalysis.howToOvercome && detailedAnalysis.howToOvercome.length > 0 && (
                <div id="sec-overcome" className="diagnostic-card deepdive-card">
                  <div className="diagnostic-card-header">
                    <span className="card-step-badge">ROADMAP</span>
                    <div className="card-header-text">
                      <h2 className="diagnostic-card-title">How to Overcome • Execution Workstreams</h2>
                      <span className="diagnostic-card-subtitle">Prescriptive remediation steps to eliminate variance</span>
                    </div>
                  </div>

                  <div className="diagnostic-card-content">
                    <ol className="remediation-steps-list">
                      {detailedAnalysis.howToOvercome.map((step, sIdx) => (
                        <li key={sIdx} className="remediation-step-item">
                          <span className="step-counter">{sIdx + 1}</span>
                          <span className="step-text">{step}</span>
                        </li>
                      ))}
                    </ol>

                    {brdPlan?.expectedOutcome && (
                      <div className="brd-clean-outcome">
                        <span className="outcome-tag">Target Outcome</span>
                        <span className="outcome-text">{brdPlan.expectedOutcome}</span>
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
