import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { getBrdPlan } from '../utils/brdPlanData';
import { generateMetricBrdPdf } from '../utils/pdfGenerator';
import TrendDrillDownView from './TrendDrillDownView';
import { apiService } from '../services/apiService';

const CATALOG_SECTIONS = [
  { id: 'sec-diagnosis', label: 'Diagnosis', icon: 'help', desc: 'LLM diagnostic synthesis & touchpoints' },
  { id: 'sec-trend', label: 'Trend Analysis', icon: 'trend', desc: 'Yearly, quarterly & monthly drill-down' },
  { id: 'sec-missing-configs', label: 'Data Gaps', icon: 'settings', desc: 'Identified data gaps & unpopulated fields' },
  { id: 'sec-rca', label: 'Root Cause Analysis', icon: 'search', desc: 'Stage & segment breach drivers' },
  { id: 'sec-impact', label: 'Business Impact', icon: 'alert', desc: 'Downstream SLA & financial risk' },
  { id: 'sec-brd', label: 'BRD Plan of Action', icon: 'clipboard', desc: 'Workforce, hours & milestones' },
  { id: 'sec-overcome', label: 'Execution Roadmap', icon: 'check', desc: 'Remediation steps & target ROI' },
  { id: 'sec-criteria', label: 'Success Criteria & Risks', icon: 'target', desc: 'Monitoring targets & mitigations' }
];

// Module-specific technical mapping for Architecture Touchpoints, RCA Failure Modes & Missing Configurations
function getModuleMapping(moduleId, metricName = '') {
  return { touchpoints: [], missingConfigs: [], rca: [] };
}
function _unused_old_getModuleMapping(moduleId, metricName = '') {
  const normName = (metricName || '').toLowerCase();

  switch (moduleId) {
    case 'rcm': // Recruitment
      return {
        touchpoints: [
          { label: 'Career Site Builder (CSB)', type: 'core' },
          { label: 'Candidate Workbench & Requisitions', type: 'config' },
          { label: 'Interview Central & Self-Scheduling', type: 'workflow' },
          { label: 'Offer Approval & DocuSign e-Signature', type: 'integration' }
        ],
        missingConfigs: normName.includes('time') ? [
          {
            id: 'CFG-R01',
            component: 'Recruiting Business Rules (BCUI / ISC)',
            title: 'Automated 24-Hour Interview Scorecard SLA Escalation Rule',
            status: 'Inactive / Not Deployed',
            severity: 'Critical',
            setting: 'Manage Business Configuration > JobApplication > rule_escalate_pending_scorecard (Trigger escalation at 24h & auto-reassign after 48h)'
          },
          {
            id: 'CFG-R02',
            component: 'Job Requisition Template & Screening Engine',
            title: 'Mandatory Role-Specific Pre-Screening Knockout Questions',
            status: 'Disabled on Active Requisitions',
            severity: 'High',
            setting: 'Requisition Form Settings > enableKnockoutScore=true (Auto-filter unqualified applicants before recruiter triage queue)'
          },
          {
            id: 'CFG-R03',
            component: 'Offer Approval Governance Matrix',
            title: 'Conditional Salary-Band Approval Bypass Rules',
            status: 'Unbounded Multi-Tier Hierarchy',
            severity: 'High',
            setting: 'Manage Recruiting Settings > Offer Approval Template (Auto-bypass VP sign-off when proposed compa-ratio is within standard 0.90-1.10 band)'
          }
        ] : [
          {
            id: 'CFG-R01',
            component: 'Career Site Builder (CSB)',
            title: 'Mobile-Optimized Candidate Quick-Apply Gateway',
            status: 'Not Activated',
            severity: 'Critical',
            setting: 'CSB Settings > Mobile Application Flow > Enable one-click resume parsing & LinkedIn profile import'
          },
          {
            id: 'CFG-R02',
            component: 'Integration Center / DocuSign API',
            title: 'Event-Driven Real-Time e-Signature Offer Dispatch',
            status: 'Manual Document Dispatch',
            severity: 'High',
            setting: 'Integration Center > Outbound Webhook > Event: OfferApproved > Instant envelope trigger'
          },
          {
            id: 'CFG-R03',
            component: 'Interview Central Scheduling Engine',
            title: 'Candidate Self-Scheduling Microsoft 365 Calendar Sync',
            status: 'Manual Coordination',
            severity: 'Medium',
            setting: 'Admin Center > Set Up Interview Scheduling > Exchange Online OAuth2 Integration'
          }
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
        missingConfigs: [
          {
            id: 'CFG-O01',
            component: 'Identity Authentication Service (IAS)',
            title: 'Pre-Day 1 Mobile Magic Link Authentication Gateway',
            status: 'Restricted to Domain SSO',
            severity: 'Critical',
            setting: 'IAS Admin Console > Applications > SF ONB2 > Allow External Magic-Link Authentication'
          },
          {
            id: 'CFG-O02',
            component: 'SAP BTP Event Mesh (IAM Webhook)',
            title: 'Event-Driven IT Hardware & Workspace Provisioning Hook',
            status: 'Disconnected / Manual Queue',
            severity: 'High',
            setting: 'BTP Cockpit > Event Mesh > Queue: ONB_ASSET_DISPATCH (Real-time webhook to IT inventory)'
          },
          {
            id: 'CFG-O03',
            component: 'Continuous Performance Management (CPM)',
            title: 'Automated 30/60/90-Day New Hire Review Milestones',
            status: 'Unassigned Schedule',
            severity: 'High',
            setting: 'CPM Admin > Onboarding Activity Template > Auto-generate 30/60/90-day manager pulse milestones'
          }
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
        missingConfigs: [
          {
            id: 'CFG-X01',
            component: 'SAP BTP Event Mesh / IAM Identity Gateway',
            title: 'Real-Time IAM Okta/AD Termination Revocation Hook',
            status: 'Batch-Dependent (24h Delay)',
            severity: 'Critical',
            setting: 'BTP Event Mesh > Topic: /sf/ofb/separation_immediate > Instant revoke webhook to Okta'
          },
          {
            id: 'CFG-X02',
            component: 'Offboarding 2.0 Clearance Process Engine',
            title: 'Concurrent Parallel Department Task Routing',
            status: 'Sequential Waterfall (Blocking)',
            severity: 'High',
            setting: 'Process Configuration > OFB Separation > Switch clearance stages from Sequential to Concurrent Parallel'
          },
          {
            id: 'CFG-X03',
            component: 'Knowledge Handover Verification Checklist',
            title: 'Mandatory Digital Knowledge Transfer Repository Sign-off',
            status: 'Optional / Free-Text',
            severity: 'Medium',
            setting: 'Offboarding Task Definition > Knowledge Transfer > Mandate SharePoint/Wiki repository URL validation'
          }
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
      const ecMissing = normName.includes('accuracy') ? [
        {
          id: 'CFG-E01',
          component: 'Manage Business Configuration (BCUI)',
          title: 'Mandatory Checksum & Regex Validation Rule on National ID',
          status: 'Inactive Rule Binding',
          severity: 'Critical',
          setting: 'BCUI > nationalIdCard > onChange: rule_validate_national_id (Hard stop on format mismatch)'
        },
        {
          id: 'CFG-E02',
          component: 'Picklist Center & MDF Object Definition',
          title: 'Strict Picklist Constraint Binding on Custom MDF Objects',
          status: 'Unconstrained Free-Text',
          severity: 'High',
          setting: 'Configure Object Definitions > cust_emergency_contact > Field Data Type: Picklist (ID: ec_rel_picklist)'
        },
        {
          id: 'CFG-E03',
          component: 'Integration Center CSV Data Ingestion Pipelines',
          title: 'Real-Time Integration Center Error Hook & Alerting',
          status: 'Silent Failure Logging',
          severity: 'Medium',
          setting: 'Integration Center > Edit Definition > Schedule & Notifications > Alert HR Master Data Steward on schema fault'
        }
      ] : normName.includes('workflow') || normName.includes('approval') ? [
        {
          id: 'CFG-E01',
          component: 'Intelligent Services Center (ISC)',
          title: '48-Hour Workflow Stagnation Escalation Event Rule',
          status: 'Inactive / Not Configured',
          severity: 'Critical',
          setting: 'Intelligent Services Center > Event: Workflow Stagnant > Auto-reassign to higher supervisor after 48h'
        },
        {
          id: 'CFG-E02',
          component: 'Workflow Configuration (wfConfig)',
          title: 'Conditional Rule-Based Skip for Non-Compensation Changes',
          status: 'Rigid Multi-Tier VP Routing',
          severity: 'High',
          setting: 'Manage Organization, Pay and Job Structures > wfConfig > Condition: If change != compensation, skip VP'
        },
        {
          id: 'CFG-E03',
          component: 'SAP Mobile Services & Work Zone Cards',
          title: 'Executive Mobile One-Click Workflow Approval Cards',
          status: 'Push Disabled',
          severity: 'Medium',
          setting: 'Mobile Settings > Enable SAP Mobile Cards for HRIS Workflow Approvals with push notifications'
        }
      ] : normName.includes('retroactive') ? [
        {
          id: 'CFG-E01',
          component: 'Employee Central Business Rules Engine',
          title: 'Effective Date Retro-Window Constraint Rule (≤ 14 Days)',
          status: 'Unrestricted Past Dates',
          severity: 'Critical',
          setting: 'Job Information > onSave: rule_block_retro_dates_over_14d (Requires VP HR approval for retroactive overrides)'
        },
        {
          id: 'CFG-E02',
          component: 'Alert & Notification Center',
          title: 'Proactive 30-Day Contract & Milestone Expiration Alerts',
          status: 'Missing Event Schedule',
          severity: 'High',
          setting: 'Alert Engine > Batch Job: daily_contract_expiry_scan > Send reminder email 30 days prior to contract end'
        },
        {
          id: 'CFG-E03',
          component: 'Payroll Control Center (PCC) Cutoff Lock',
          title: 'Manager Self-Service (MSS) Edit Freeze During Payroll Window',
          status: 'Open Unlocked Portlets',
          severity: 'High',
          setting: 'Role-Based Permissions (RBP) > Time-based restriction on Job & Compensation changes during payroll cycle'
        }
      ] : [
        {
          id: 'CFG-E01',
          component: 'Manage Business Configuration (BCUI)',
          title: 'Mandatory Field Validations & Document Attachment Verification',
          status: 'Inactive Rules',
          severity: 'Critical',
          setting: 'BCUI > Configure Business Rules > Set mandatory attachment verification for key HRIS entities'
        },
        {
          id: 'CFG-E02',
          component: 'Intelligent Services Center (ISC)',
          title: 'Event-Driven Operational Alert Triggers',
          status: 'Unassigned Events',
          severity: 'High',
          setting: 'ISC > Connect employee lifecycle events to automated supervisor email notifications'
        },
        {
          id: 'CFG-E03',
          component: 'Picklist Center & MDF Governance',
          title: 'Standardized Enterprise Picklist Value Normalization',
          status: 'Unlinked Legacy Picklists',
          severity: 'Medium',
          setting: 'Picklist Center > Map all custom portlet fields to standardized enterprise picklists'
        }
      ];

      return {
        touchpoints: [
          { label: 'Custom MDF Objects & Extension Portals', type: 'core' },
          { label: 'Biographical & Personal Info Portlets', type: 'config' },
          { label: 'Integration Center CSV Ingestion Pipelines', type: 'integration' },
          { label: 'Employee Central Business Rules Engine', type: 'workflow' }
        ],
        missingConfigs: ecMissing,
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
  const isManualScrollRef = useRef(false);

  if (!currentMetric) return null;

  const {
    detailedAnalysis: baseDetailedAnalysis,
    metric: metricName,
    category,
    company: baseCompany,
    standard: baseStandard,
    status: baseStatus,
    variance: baseVariance
  } = currentMetric;

  // Live ML Insight fetched from Supabase Storage bucket via FastAPI
  const [liveInsight, setLiveInsight] = useState(null);

  useEffect(() => {
    let active = true;
    setLiveInsight(null);
    const metricCode = currentMetric.code || currentMetric.metric;
    if (metricCode) {
      apiService.getMetricDeepDive(metricCode, currentMetric.metric, module?.id)
        .then((data) => {
          if (active && data) {
            setLiveInsight(data);
          }
        })
        .catch(() => { });
    }
    return () => { active = false; };
  }, [currentMetric.code, currentMetric.metric, module?.id]);

  const pickNonEmpty = (liveVal, baseVal) => {
    const isInvalid = (v) => !v || ['not yet fetched', 'data not yet fetched from supabase', '--', '-', 'none', 'null', ''].includes(String(v).trim().toLowerCase());
    if (!isInvalid(liveVal)) return liveVal;
    if (!isInvalid(baseVal)) return baseVal;
    return liveVal || baseVal;
  };

  // Real-time overrides: Whatever is present in the Supabase metric folder reflects directly!
  const rawCompany = pickNonEmpty(liveInsight?.metric?.company, baseCompany);
  const rawStandard = pickNonEmpty(liveInsight?.metric?.standard, baseStandard);
  const rawStatus = pickNonEmpty(liveInsight?.metric?.status, baseStatus);
  const rawVariance = pickNonEmpty(liveInsight?.metric?.variance, baseVariance);
  const detailedAnalysis = liveInsight?.metric?.detailedAnalysis || baseDetailedAnalysis;

  const isMetricLive = Boolean(
    liveInsight?.source === 'supabase_storage' ||
    liveInsight?.source === 'supabase_storage_metric_folder' ||
    liveInsight?.source === 'supabase_llm_reports_table' ||
    liveInsight?.source === 'supabase_ml_notebook_insights_table' ||
    liveInsight?.source === 'supabase_table' ||
    liveInsight?.source === 'supabase' ||
    liveInsight?.source?.startsWith?.('supabase') ||
    liveInsight?.storagePath ||
    liveInsight?.metric?.isSupabaseLive ||
    Boolean(liveInsight?.diagnosis?.narrative) ||
    Boolean(liveInsight?.metric?.diagnosis?.narrative) ||
    currentMetric?.isSupabaseLive ||
    currentMetric?._source === 'supabase_storage' ||
    currentMetric?._source === 'supabase_storage_metric_folder' ||
    currentMetric?._source === 'supabase_llm_reports_table' ||
    currentMetric?._source === 'supabase_ml_notebook_insights_table' ||
    currentMetric?._source === 'supabase_table' ||
    currentMetric?._source === 'supabase'
  );
  const isSupabaseLive = isMetricLive;

  const cleanVal = (val) => {
    if (!val) return 'Not yet fetched';
    const s = String(val).trim();
    if (['not yet fetched', 'data not yet fetched from supabase', '--', '-', 'none', 'null', ''].includes(s.toLowerCase())) {
      return 'Not yet fetched';
    }
    return s;
  };

  const company = isMetricLive ? cleanVal(rawCompany) : 'Not yet fetched';
  const standard = isMetricLive ? cleanVal(rawStandard) : 'Not yet fetched';
  const status = isMetricLive ? (rawStatus && rawStatus !== 'Not yet fetched' ? rawStatus : 'Not yet fetched') : 'Not yet fetched';
  const variance = isMetricLive ? cleanVal(rawVariance) : 'Not yet fetched';

  const overviewData = isMetricLive
    ? (liveInsight?.moduleOverview || liveInsight?.metric?.moduleOverview || currentMetric?.moduleOverview || {})
    : { rootCause: 'Data not yet fetched', affectedArea: 'Data not yet fetched', suggestions: [] };

  const diagnosisData = isMetricLive
    ? (liveInsight?.diagnosis || liveInsight?.metric?.diagnosis || currentMetric?.diagnosis || {})
    : {};
  const diagnosisHeadline = diagnosisData?.headline || detailedAnalysis?.headline || '';
  const diagnosisNarrative = diagnosisData?.narrative || (detailedAnalysis?.whyItHappens && !['data not yet fetched', 'data not yet fetched from supabase'].includes(detailedAnalysis.whyItHappens.toLowerCase()) ? detailedAnalysis?.whyItHappens : '') || (overviewData.rootCause && !['data not yet fetched', 'data not yet fetched from supabase'].includes(overviewData.rootCause.toLowerCase()) ? overviewData.rootCause : '') || (isMetricLive ? '' : 'Data not yet fetched');

  const whyItHappensText = diagnosisNarrative || (isMetricLive ? '' : 'Data not yet fetched');
  const whereItHappensText = (overviewData.affectedArea && !['data not yet fetched', 'data not yet fetched from supabase'].includes(overviewData.affectedArea.toLowerCase()) ? overviewData.affectedArea : '') || (detailedAnalysis?.whereItHappens && !['data not yet fetched', 'data not yet fetched from supabase'].includes(detailedAnalysis.whereItHappens.toLowerCase()) ? detailedAnalysis?.whereItHappens : '') || (isMetricLive ? '' : 'Data not yet fetched');

  const businessImpactData = isMetricLive
    ? (liveInsight?.businessImpact || liveInsight?.metric?.businessImpact || detailedAnalysis?.businessImpact || currentMetric?.businessImpact || {})
    : {};
  const businessImpactOverview = businessImpactData?.overview || detailedAnalysis?.howItEffects || '';
  const financialExposure = businessImpactData?.financialExposure || '';
  const slaAndTurnaround = businessImpactData?.slaAndTurnaround || '';
  const governanceAndAudit = businessImpactData?.governanceAndAudit || '';

  const rawOvercome = isMetricLive
    ? (
        (Array.isArray(liveInsight?.suggestions) && liveInsight.suggestions.length > 0 ? liveInsight.suggestions : null) ||
        (Array.isArray(liveInsight?.metric?.suggestions) && liveInsight.metric.suggestions.length > 0 ? liveInsight.metric.suggestions : null) ||
        (Array.isArray(diagnosisData?.suggestions) && diagnosisData.suggestions.length > 0 ? diagnosisData.suggestions : null) ||
        (Array.isArray(detailedAnalysis?.howToOvercome) && detailedAnalysis.howToOvercome.length > 0 ? detailedAnalysis.howToOvercome : null) ||
        (Array.isArray(overviewData?.suggestions) && overviewData.suggestions.length > 0 ? overviewData.suggestions : null) ||
        []
      )
    : [];
  const howToOvercomeList = Array.isArray(rawOvercome) ? rawOvercome : (typeof rawOvercome === 'string' ? [rawOvercome] : (rawOvercome ? [rawOvercome] : []));

  const isCritical = status === 'Critical';
  const badgeClass = isCritical
    ? 'badge-critical'
    : status === 'Healthy'
      ? 'badge-healthy'
      : (status === 'At Risk' ? 'badge-at-risk' : 'badge-neutral');

  // Scroll to top upon entering a metric deep dive
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'instant' });
  }, [metricName]);

  const brdPlan = useMemo(() => {
    if (!isMetricLive && !liveInsight) {
      return {
        specialistManpower: [],
        workforceRequired: [],
        phasedActivities: [],
        executionWorkstreams: [],
        stageDrivers: [],
        segmentDrivers: [],
        assumptionsAndRisks: [],
        successCriteria: [],
        timeline: 'Not yet fetched',
        totalEffortHours: 0,
        totalEffortsDisplay: 'Not yet fetched',
        timelineAndEffort: { timeline: 'Not yet fetched', totalEffort: 'Not yet fetched' },
        targetOutcome: 'Data not yet fetched'
      };
    }

    const liveBrd = liveInsight?.brdPlan || liveInsight?.plan || currentMetric?.brdPlan || currentMetric?.plan || {};

    // 1. Phased Activities: Map live phases if raw phases exist from Supabase JSON
    const rawLivePhases = (Array.isArray(liveBrd.phasedActivities) && liveBrd.phasedActivities.length > 0)
      ? liveBrd.phasedActivities
      : (Array.isArray(liveBrd.phases) && liveBrd.phases.length > 0)
        ? liveBrd.phases.map((p, idx) => ({
            phaseName: p.title || p.phaseName || p.phase || `Phase ${idx + 1}`,
            milestone: p.milestone || '',
            deliverable: p.deliverable || '',
            activities: (p.activities || []).map((a) => ({
              activity: a.activity || a.title || '',
              owner: a.role || a.owner || 'Specialist',
              workstream: a.workstream || '-',
              effort: (typeof a.hours === 'number' || typeof a.effort === 'number')
                ? `${a.hours || a.effort} Hours`
                : (a.hours || a.effort || '-')
            }))
          }))
        : [];

    const phasedActivities = rawLivePhases;

    // 2. Specialist Manpower: Map live roles if raw roles exist from Supabase JSON
    const rawLiveSpecialists = (Array.isArray(liveBrd.specialistManpower) && liveBrd.specialistManpower.length > 0)
      ? liveBrd.specialistManpower
      : (Array.isArray(liveBrd.roles) && liveBrd.roles.length > 0)
        ? liveBrd.roles.map((r) => ({
            role: r.role || 'Specialist Consultant',
            headcount: r.headcount || 1,
            effort: (typeof r.hours === 'number' || typeof r.effort === 'number')
              ? `${r.hours || r.effort} Person-Hours`
              : (r.hours || r.effort || 'Not yet fetched')
          }))
        : [];

    const specialistManpower = rawLiveSpecialists;

    const executionWorkstreams = (Array.isArray(liveBrd.executionWorkstreams) && liveBrd.executionWorkstreams.length > 0)
      ? liveBrd.executionWorkstreams
      : (Array.isArray(liveInsight?.workstreams) && liveInsight.workstreams.length > 0
        ? liveInsight.workstreams.map((ws, i) => ({
            id: ws.id || `W${i + 1}`,
            remediationStep: ws.remediationStep || ws.step || ws.title || '',
            fixesDrivers: Array.isArray(ws.fixesDrivers) ? ws.fixesDrivers.join(', ') : (ws.fixesDrivers || ws.fixesFactors || '')
          }))
        : []);

    const stageDrivers = (Array.isArray(liveInsight?.stageDrivers) && liveInsight.stageDrivers.length > 0)
      ? liveInsight.stageDrivers.map((sd, i) => ({
          id: sd.id || `S${i + 1}`,
          driver: sd.stage || sd.driver || sd.name || `Stage ${i + 1}`,
          avgDays: sd.avgDays || sd.days || (sd.breachContribution ? `${sd.breachContribution}%` : '-'),
          share: sd.share || (sd.breachContribution ? `${sd.breachContribution}%` : '-')
        }))
      : (Array.isArray(liveBrd.stageDrivers) ? liveBrd.stageDrivers : []);

    const segmentDrivers = (Array.isArray(liveInsight?.segmentDrivers) && liveInsight.segmentDrivers.length > 0)
      ? liveInsight.segmentDrivers.map((seg, i) => ({
          id: seg.id || `A${i + 1}`,
          driver: seg.segment || seg.driver || seg.name || `Segment ${i + 1}`,
          avgDays: seg.actual || seg.avgDays || '-',
          vsCompany: seg.vsCompany || seg.gap || (seg.target ? `Target: ${seg.target}` : '-')
        }))
      : (Array.isArray(liveBrd.segmentDrivers) ? liveBrd.segmentDrivers : []);

    const assumptionsAndRisks = (Array.isArray(liveBrd.assumptionsAndRisks) && liveBrd.assumptionsAndRisks.length > 0)
      ? liveBrd.assumptionsAndRisks
      : (Array.isArray(liveInsight?.assumptionsAndRisks) && liveInsight.assumptionsAndRisks.length > 0
        ? liveInsight.assumptionsAndRisks
        : []);

    const successCriteria = (Array.isArray(liveBrd.successCriteria) && liveBrd.successCriteria.length > 0)
      ? liveBrd.successCriteria
      : (Array.isArray(liveInsight?.successCriteria) && liveInsight.successCriteria.length > 0
        ? liveInsight.successCriteria
        : []);

    let totalEffortHours = liveBrd.totalEffortHours || liveBrd.totalHours || 0;
    if (!totalEffortHours && rawLiveSpecialists.length > 0) {
      const calc = rawLiveSpecialists.reduce((sum, r) => {
        const h = parseInt(r.effort || 0, 10);
        return sum + (isNaN(h) ? 0 : h);
      }, 0);
      if (calc > 0) totalEffortHours = calc;
    }

    const durationWeeks = liveBrd.durationWeeks || liveBrd.timelineWeeks;
    const timeline = liveBrd.timeline || (durationWeeks ? `${durationWeeks} Weeks` : 'Not yet fetched');
    const totalEffortsDisplay = liveBrd.totalEffortsDisplay || (totalEffortHours ? `${totalEffortHours} Total Hours` : 'Not yet fetched');
    const timelineAndEffort = liveBrd.timelineAndEffort || { timeline, totalEffort: totalEffortsDisplay };
    const targetOutcome = liveBrd.targetOutcome || liveInsight?.targetOutcome || (isMetricLive && whyItHappensText && !['data not yet fetched', 'data not yet fetched from supabase'].includes(whyItHappensText.toLowerCase()) ? whyItHappensText : 'Data not yet fetched');

    return {
      ...liveBrd,
      specialistManpower,
      phasedActivities,
      executionWorkstreams,
      stageDrivers,
      segmentDrivers,
      assumptionsAndRisks,
      successCriteria,
      timeline,
      totalEffortHours,
      totalEffortsDisplay,
      timelineAndEffort,
      targetOutcome
    };
  }, [currentMetric, liveInsight, whyItHappensText, isMetricLive]);

  // Dynamic module mapping for architecture touchpoints & RCA failure modes
  const moduleMapping = useMemo(() => (isMetricLive ? getModuleMapping(module?.id, metricName) : { touchpoints: [], missingConfigs: [], rca: [] }), [module?.id, metricName, isMetricLive]);
  const systemTouchpoints = (liveInsight?.touchpoints && liveInsight.touchpoints.length > 0)
    ? liveInsight.touchpoints
    : (liveInsight?.report?.touchpoints || []);
  const rcaFailureModes = (liveInsight?.rca && liveInsight.rca.length > 0)
    ? liveInsight.rca
    : (liveInsight?.report?.rca || []);
  const rawMissingConfigs = (liveInsight?.missingConfigurations && liveInsight.missingConfigurations.length > 0)
    ? liveInsight.missingConfigurations
    : ((detailedAnalysis?.missingConfigurations && detailedAnalysis.missingConfigurations.length > 0)
      ? detailedAnalysis.missingConfigurations
      : ((currentMetric?.missingConfigurations && currentMetric.missingConfigurations.length > 0)
        ? currentMetric.missingConfigurations
        : ((currentMetric?.detailedAnalysis?.missingConfigurations && currentMetric.detailedAnalysis.missingConfigurations.length > 0)
          ? currentMetric.detailedAnalysis.missingConfigurations
          : [])));

  const missingConfigs = useMemo(() => {
    if (!rawMissingConfigs) return [];
    if (Array.isArray(rawMissingConfigs)) {
      return rawMissingConfigs.map((item, idx) => {
        if (typeof item === 'string') {
          const isMand = item.toLowerCase().includes('audit') || item.toLowerCase().includes('status');
          return {
            id: `CFG-${idx + 1 < 10 ? '0' : ''}${idx + 1}`,
            component: 'Employee Central Data Architecture',
            field: item,
            fieldName: item,
            title: isMand ? `Mandatory Field Missing: ${item}` : `Missing Field: ${item}`,
            status: isMand ? 'Unpopulated Mandatory Field' : 'Unpopulated Field',
            severity: isMand ? 'Critical' : 'Medium',
            setting: `Manage Business Configuration (BCUI) > Configure attribute mapping and data cleansing for '${item}'`
          };
        }
        if (typeof item === 'object' && item !== null) {
          const fieldName = item.field || item.fieldName || (item.title ? item.title.replace(/^(Mandatory\s+Field\s+Missing:\s*|Missing\s+Field:\s*)/i, '').trim() : '');
          return {
            ...item,
            field: fieldName || item.title,
            fieldName: fieldName || item.title
          };
        }
        return item;
      });
    }
    if (typeof rawMissingConfigs === 'object') {
      const list = [];
      let idx = 1;
      Object.entries(rawMissingConfigs).forEach(([cat, items]) => {
        const isMandatory = cat.toLowerCase().includes('mandat');
        if (Array.isArray(items)) {
          items.forEach((item) => {
            const fieldName = typeof item === 'object' ? item.field || item.name || JSON.stringify(item) : String(item);
            list.push({
              id: `CFG-${idx < 10 ? '0' : ''}${idx}`,
              component: 'Employee Central Data Architecture',
              field: fieldName,
              fieldName: fieldName,
              title: isMandatory ? `Mandatory Field Missing: ${fieldName}` : `Missing Field: ${fieldName}`,
              status: isMandatory ? 'Unpopulated Mandatory Field' : 'Unpopulated Field',
              severity: isMandatory ? 'Critical' : 'Medium',
              setting: `Manage Business Configuration (BCUI) > Enable mandatory validation and data cleansing for '${fieldName}'`
            });
            idx++;
          });
        }
      });
      return list;
    }
    return [];
  }, [rawMissingConfigs, currentMetric?.metric]);

  const hasDataGap = Boolean(
    String(variance || '').toLowerCase().includes('data gap') ||
    String(company || '').toLowerCase().includes('no data') ||
    company === 'N/A' ||
    company === 'Not yet fetched' ||
    status === 'Unknown' ||
    status === 'Not yet fetched' ||
    (liveInsight?.dataQuality && liveInsight.dataQuality.overallRating === 'poor') ||
    (currentMetric?.dataQuality && currentMetric.dataQuality.overallRating === 'poor') ||
    (missingConfigs.length > 0)
  );

  const rcaPriorityLabels = useMemo(() => [
    'P1 • Critical Architecture Gap',
    'P2 • Operational Workflow Latency',
    'P3 • Integration & Sync Reliability'
  ], []);

  const unifiedRcaDrivers = useMemo(() => {
    const list = [];
    (brdPlan?.stageDrivers || []).forEach((sd, idx) => {
      list.push({
        id: sd.id || `S${idx + 1}`,
        driver: sd.driver || sd.name || `Stage ${idx + 1}`,
        type: 'Stage Driver',
        typeBadgeBg: '#eff6ff',
        typeBadgeColor: '#0369a1',
        typeBadgeBorder: '#bae6fd',
        impact: sd.avgDays || '-',
        share: sd.share || '-'
      });
    });
    (brdPlan?.segmentDrivers || []).forEach((seg, idx) => {
      list.push({
        id: seg.id || `A${idx + 1}`,
        driver: seg.driver || seg.name || `Segment ${idx + 1}`,
        type: 'Segment Driver',
        typeBadgeBg: '#f0fdf4',
        typeBadgeColor: '#166534',
        typeBadgeBorder: '#bbf7d0',
        impact: seg.avgDays || '-',
        share: seg.vsCompany || '-'
      });
    });
    return list;
  }, [brdPlan?.stageDrivers, brdPlan?.segmentDrivers]);

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

  // Smooth scroll to section when clicked in left catalog using native GPU scroll with header offset
  const handleScrollToSection = useCallback((sectionId) => {
    isManualScrollRef.current = true;
    currentSectionRef.current = sectionId;
    setActiveSection(sectionId);

    const element = document.getElementById(sectionId);
    if (element) {
      const topOffset = element.getBoundingClientRect().top + window.pageYOffset - 90;
      window.scrollTo({ top: topOffset, behavior: 'smooth' });
    }

    setTimeout(() => {
      isManualScrollRef.current = false;
    }, 850);
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
  }, [metricName]);

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
            const firstId = renderedSections[0].id;
            if (currentSectionRef.current !== firstId) {
              currentSectionRef.current = firstId;
              setActiveSection(firstId);
            }
            return;
          }

          // 2. Extreme bottom: Lock to last section
          if (scrollY + windowHeight >= documentHeight - 60) {
            const lastId = renderedSections[renderedSections.length - 1].id;
            if (currentSectionRef.current !== lastId) {
              currentSectionRef.current = lastId;
              setActiveSection(lastId);
            }
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
  }, [metricName]);

  const handleDownloadPDF = useCallback(async () => {
    setIsDownloading(true);
    try {
      const liveMetric = {
        ...currentMetric,
        company,
        standard,
        status,
        variance,
        moduleOverview: overviewData,
        detailedAnalysis: {
          ...(detailedAnalysis || {}),
          whyItHappens: whyItHappensText,
          whereItHappens: whereItHappensText,
          howToOvercome: howToOvercomeList
        }
      };

      await generateMetricBrdPdf(liveMetric, {
        brdPlan,
        missingConfigs,
        systemTouchpoints,
        rcaFailureModes,
        moduleName: module?.name,
        diagnosisHeadline,
        whyItHappensText,
        whereItHappensText,
        howToOvercomeList
      });
    } catch (err) {
      console.error('PDF Generation Error:', err);
    } finally {
      setIsDownloading(false);
    }
  }, [currentMetric, company, standard, status, variance, overviewData, detailedAnalysis, diagnosisHeadline, whyItHappensText, whereItHappensText, howToOvercomeList, brdPlan, missingConfigs, systemTouchpoints, rcaFailureModes, module?.name]);

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
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap', marginTop: '4px' }}>
                <span className="catalog-sub">{category} • {module?.name || 'Module'}</span>
              </div>

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

              <div className="deepdive-hero-badge-wrap" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
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

              {/* SECTION 01: DIAGNOSIS (MERGED & AUTHORITATIVE - ELIMINATING DUPLICATE WHERE/WHY) */}
              <div id="sec-diagnosis" className="diagnostic-card deepdive-card">
                <div className="diagnostic-card-header">
                  <div className="card-header-text">
                    <h2 className="diagnostic-card-title">1. Diagnosis</h2>
                    <span className="diagnostic-card-subtitle">Written by the LLM from the ML insights only</span>
                  </div>
                </div>
                <div className="diagnostic-card-content">
                  {!isMetricLive ? (
                    <div style={{ padding: '24px', textAlign: 'center', color: '#64748b' }}>
                      <p style={{ margin: 0, fontWeight: 500 }}>Data not yet fetched.</p>
                    </div>
                  ) : (
                    <>
                      {hasDataGap && (
                        <div
                          className="diagnosis-data-gap-banner"
                          style={{
                            marginBottom: '14px',
                            padding: '11px 15px',
                            borderRadius: '6px',
                            background: '#fffbeb',
                            border: '1px solid #fde68a',
                            borderLeft: '4px solid #f59e0b',
                            display: 'flex',
                            alignItems: 'flex-start',
                            gap: '10px'
                          }}
                        >
                          <span style={{ fontSize: '16px', lineHeight: 1.2 }}>⚠️</span>
                          <div style={{ flex: 1 }}>
                            <div style={{ fontSize: '12.5px', fontWeight: 700, color: '#92400e', marginBottom: '2px' }}>
                              Data Gap Identified
                            </div>
                            <div style={{ fontSize: '11.8px', color: '#b45309', lineHeight: 1.5 }}>
                              {missingConfigs.length > 0
                                ? `${missingConfigs.length} unpopulated data field${missingConfigs.length > 1 ? 's' : ''} detected in client data feed. Records lack required attributes, resulting in an uncomputed company actual and variance data gap.`
                                : 'Record completeness checks failed or unpopulated values detected in data feed. Metric actuals reflect an operational data gap.'}
                            </div>
                          </div>
                        </div>
                      )}

                      {diagnosisHeadline && (
                        <div
                          className="diagnosis-headline-box"
                          style={{
                            marginBottom: '12px',
                            padding: '9px 13px',
                            borderRadius: '6px',
                            background: status === 'Critical'
                              ? 'rgba(239, 68, 68, 0.08)'
                              : status === 'Healthy'
                                ? 'rgba(16, 185, 129, 0.08)'
                                : 'rgba(245, 158, 11, 0.08)',
                            borderLeft: `3px solid ${status === 'Critical' ? '#ef4444' : status === 'Healthy' ? '#10b981' : '#f59e0b'}`,
                            border: `1px solid ${status === 'Critical' ? 'rgba(239, 68, 68, 0.2)' : status === 'Healthy' ? 'rgba(16, 185, 129, 0.2)' : 'rgba(245, 158, 11, 0.2)'}`,
                            color: '#1e293b',
                            fontSize: '12.5px',
                            fontWeight: 600,
                            lineHeight: 1.45,
                            display: 'flex',
                            alignItems: 'flex-start',
                            gap: '8px'
                          }}
                        >
                          <span style={{ fontSize: '13px', lineHeight: 1.2 }}>{status === 'Critical' ? '🚨' : status === 'Healthy' ? '✅' : '⚠️'}</span>
                          <span>{diagnosisHeadline}</span>
                        </div>
                      )}

                      {whyItHappensText && !['data not yet fetched', 'data not yet fetched from supabase'].includes(whyItHappensText.toLowerCase()) ? (
                        <div style={{ marginBottom: '14px' }}>
                          <div className="footprint-header" style={{ marginBottom: '5px', fontSize: '11.5px', color: '#475569', fontWeight: 700, letterSpacing: '0.02em' }}>
                            <span>🔍 WHY IT IS HAPPENING (ROOT CAUSE):</span>
                          </div>
                          <p className="analysis-text-paragraph" style={{ lineHeight: '1.55', color: '#334155', fontSize: '12px', margin: 0 }}>
                            {whyItHappensText}
                          </p>
                        </div>
                      ) : hasDataGap ? (
                        <div style={{ marginBottom: '14px' }}>
                          <div className="footprint-header" style={{ marginBottom: '5px', fontSize: '11.5px', color: '#475569', fontWeight: 700, letterSpacing: '0.02em' }}>
                            <span>🔍 WHY IT IS HAPPENING (ROOT CAUSE):</span>
                          </div>
                          <p className="analysis-text-paragraph" style={{ lineHeight: '1.55', color: '#92400e', fontSize: '12px', margin: 0, fontStyle: 'italic', background: '#fffbeb', padding: '10px 14px', borderRadius: '6px', border: '1px solid #fde68a' }}>
                            ⚠️ Data Gap: Automated root cause modeling could not be evaluated due to unpopulated fields in client data.
                          </p>
                        </div>
                      ) : null}

                      {whereItHappensText &&
                        whereItHappensText !== 'SuccessFactors workflow touchpoints' &&
                        !['data not yet fetched', 'data not yet fetched from supabase'].includes(whereItHappensText.toLowerCase()) &&
                        whereItHappensText !== whyItHappensText &&
                        whereItHappensText !== diagnosisNarrative ? (
                          <div className="sf-footprint-box" style={{ marginTop: '12px', padding: '10px 12px', borderRadius: '6px' }}>
                            <div className="footprint-header" style={{ fontSize: '11.5px', color: '#475569' }}>
                              <span><strong style={{ fontWeight: 700 }}>IMPACTED ARCHITECTURE TOUCHPOINTS:</strong> <span style={{ fontSize: '12px', color: '#334155', fontWeight: 500 }}>{whereItHappensText}</span></span>
                            </div>
                            {/* Only show real touchpoint chips if provided from Supabase */}
                            {liveInsight?.touchpoints && Array.isArray(liveInsight.touchpoints) && liveInsight.touchpoints.length > 0 && (
                              <div className="footprint-chips" style={{ marginTop: '6px' }}>
                                {liveInsight.touchpoints.map((tp, idx) => (
                                  <span key={idx} className="footprint-chip" style={{ fontSize: '11px', padding: '2px 8px' }}>
                                    {typeof tp === 'string' ? tp : tp.label || tp.name}
                                  </span>
                                ))}
                              </div>
                            )}
                          </div>
                        ) : hasDataGap ? (
                          <div className="sf-footprint-box" style={{ marginTop: '12px', padding: '10px 12px', borderRadius: '6px', background: '#fffbeb', border: '1px solid #fde68a' }}>
                            <div className="footprint-header" style={{ fontSize: '11.5px', color: '#92400e' }}>
                              <span><strong style={{ fontWeight: 700 }}>IMPACTED ARCHITECTURE TOUCHPOINTS:</strong> <span style={{ fontSize: '12px', color: '#b45309', fontStyle: 'italic' }}>⚠️ Data Gap: Architecture touchpoints unmapped due to missing data attributes.</span></span>
                            </div>
                          </div>
                        ) : null}

                      {howToOvercomeList && howToOvercomeList.length > 0 ? (
                        <div className="sf-footprint-box" style={{ marginTop: '12px', padding: '10px 12px', borderRadius: '6px' }}>
                          <div className="footprint-header" style={{ fontSize: '11.5px', marginBottom: '6px', color: '#475569', fontWeight: 700, letterSpacing: '0.02em' }}>
                            <span>💡 SUGGESTIONS TO IMPROVE:</span>
                          </div>
                          <ol className="accordion-suggestions-list" style={{ marginTop: '4px', paddingLeft: 0, listStyle: 'none', marginBottom: 0 }}>
                            {howToOvercomeList.map((sug, sIdx) => (
                              <li key={sIdx} className="accordion-suggestion-item" style={{ marginBottom: '6px', display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
                                <span className="accordion-step-counter" style={{ fontSize: '10px', width: '18px', height: '18px', minWidth: '18px', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', borderRadius: '4px' }}>{sIdx + 1}</span>
                                <span className="accordion-step-text" style={{ fontSize: '12px', lineHeight: '1.5', color: '#334155' }}>{sug}</span>
                              </li>
                            ))}
                          </ol>
                        </div>
                      ) : hasDataGap ? (
                        <div className="sf-footprint-box" style={{ marginTop: '12px', padding: '10px 12px', borderRadius: '6px', background: '#fffbeb', border: '1px solid #fde68a' }}>
                          <div className="footprint-header" style={{ fontSize: '11.5px', marginBottom: '6px', color: '#92400e', fontWeight: 700, letterSpacing: '0.02em' }}>
                            <span>💡 SUGGESTIONS TO IMPROVE:</span>
                          </div>
                          <p style={{ margin: '4px 0 0 0', fontSize: '12px', color: '#b45309', fontStyle: 'italic' }}>
                            ⚠️ Data Gap: No suggestions generated (mandatory configuration fields are missing).
                          </p>
                        </div>
                      ) : (
                        <div className="sf-footprint-box" style={{ marginTop: '12px', padding: '10px 12px', borderRadius: '6px' }}>
                          <div className="footprint-header" style={{ fontSize: '11.5px', marginBottom: '6px', color: '#475569', fontWeight: 700, letterSpacing: '0.02em' }}>
                            <span>💡 SUGGESTIONS TO IMPROVE:</span>
                          </div>
                          <p style={{ margin: '4px 0 0 0', fontSize: '12px', color: '#64748b', fontStyle: 'italic' }}>
                            No suggestions returned for this metric.
                          </p>
                        </div>
                      )}

                      {hasDataGap && missingConfigs.length > 0 && (
                        <div
                          className="diagnosis-data-gap-detail-card"
                          style={{
                            marginTop: '14px',
                            padding: '12px 14px',
                            borderRadius: '6px',
                            background: '#f8fafc',
                            border: '1px solid #e2e8f0',
                            borderLeft: '4px solid #f59e0b'
                          }}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                            <div style={{ fontSize: '12px', fontWeight: 700, color: '#334155' }}>
                              📋 Data Completeness &amp; Schema Audit (Data Gaps Breakdown)
                            </div>
                            <span style={{ fontSize: '11px', fontWeight: 600, color: '#92400e', background: '#fef3c7', padding: '2px 8px', borderRadius: '12px' }}>
                              {missingConfigs.length} Missing Fields
                            </span>
                          </div>
                          <div style={{ fontSize: '11.5px', color: '#64748b', lineHeight: 1.5, marginBottom: '8px' }}>
                            The following unpopulated attributes prevent calculation of the company actual benchmark. Populating these fields in SuccessFactors will resolve the data gap:
                          </div>
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                            {missingConfigs.map((cfg, idx) => (
                              <span
                                key={idx}
                                style={{
                                  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
                                  fontSize: '11px',
                                  fontWeight: 600,
                                  padding: '2px 8px',
                                  borderRadius: '4px',
                                  background: cfg.severity === 'Critical' ? '#fee2e2' : '#f1f5f9',
                                  color: cfg.severity === 'Critical' ? '#991b1b' : '#334155',
                                  border: `1px solid ${cfg.severity === 'Critical' ? '#fca5a5' : '#cbd5e1'}`
                                }}
                              >
                                {cfg.field || cfg.fieldName || cfg.title.replace(/^(Mandatory\s+Field\s+Missing:\s*|Missing\s+Field:\s*)/i, '').trim()}
                                {cfg.severity === 'Critical' ? ' (Mandatory)' : ''}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                    </>
                  )}
                </div>
              </div>

              {/* SECTION 02: TREND ANALYSIS (ALIGNED WITH BRD ORDER) */}
              <div id="sec-trend" className="diagnostic-card deepdive-card">
                <div className="diagnostic-card-header">
                  <div className="card-header-text">
                    <h2 className="diagnostic-card-title">2. Trend Analysis</h2>
                    <span className="diagnostic-card-subtitle">
                      Hierarchical Drill-Down Trajectory Tracking (Yearly › Quarterly › Monthly)
                    </span>
                  </div>
                </div>
                <div className="diagnostic-card-content">
                  {!isMetricLive ? (
                    <div style={{ padding: '24px', textAlign: 'center', color: '#64748b' }}>
                      <p style={{ margin: 0, fontWeight: 500 }}>Data not yet fetched.</p>
                    </div>
                  ) : (
                    <TrendDrillDownView metric={{ ...currentMetric, company, standard, status, variance, isSupabaseLive }} />
                  )}
                </div>
              </div>

              {/* SECTION 03: DATA GAPS */}
              <div id="sec-missing-configs" className="diagnostic-card deepdive-card">
                <div className="diagnostic-card-header">
                  <div className="card-header-text">
                    <h2 className="diagnostic-card-title">3. Data Gaps</h2>
                    <span className="diagnostic-card-subtitle">
                      System Configuration Gaps, Unpopulated Fields &amp; Governance Controls
                    </span>
                  </div>
                </div>
                <div className="diagnostic-card-content">
                  {!isMetricLive ? (
                    <div style={{ padding: '24px', textAlign: 'center', color: '#64748b' }}>
                      <p style={{ margin: 0, fontWeight: 500 }}>Data not yet fetched.</p>
                    </div>
                  ) : missingConfigs.length === 0 ? (
                    <div
                      className="cfg-no-missing-banner"
                      style={{
                        padding: '16px 20px',
                        borderRadius: '8px',
                        background: 'rgba(16, 185, 129, 0.06)',
                        border: '1px solid rgba(16, 185, 129, 0.25)',
                        borderLeft: '4px solid #10b981',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '12px',
                        marginTop: '6px'
                      }}
                    >
                      <span style={{ fontSize: '18px', lineHeight: 1 }}>✅</span>
                      <div>
                        <div style={{ fontSize: '12.5px', fontWeight: 700, color: '#065f46', marginBottom: '2px' }}>
                          No Data Gaps Detected
                        </div>
                        <div style={{ fontSize: '12px', color: '#047857', lineHeight: 1.45 }}>
                          All required system fields, validation rules, picklists, and governance controls are populated.
                        </div>
                      </div>
                    </div>
                  ) : (
                    <>
                      {/* Summary Banner */}
                      <div className="cfg-summary-banner">
                        <div className="cfg-banner-info">
                          <span className="cfg-banner-icon" aria-hidden="true">⚠️</span>
                          <div>
                            <div className="cfg-banner-title">
                              {missingConfigs.length} Identified Data Gaps
                            </div>
                            <div className="cfg-banner-desc">
                              Technical audit diagnosed the following unpopulated fields, missing attributes, and configuration deficits directly driving the variance gap.
                            </div>
                          </div>
                        </div>
                        <div className="cfg-banner-stats">
                          <span className="cfg-stat-pill pill-critical">
                            {missingConfigs.filter(c => c.severity === 'Critical').length} Critical
                          </span>
                          <span className="cfg-stat-pill pill-high">
                            {missingConfigs.filter(c => c.severity === 'High').length} High
                          </span>
                          <span className="cfg-stat-pill pill-medium">
                            {missingConfigs.filter(c => c.severity === 'Medium').length} Medium
                          </span>
                        </div>
                      </div>

                      {/* Specification Table */}
                      <div className="brd-spec-table-container" style={{ marginTop: '16px' }}>
                        <table className="brd-spec-table">
                          <thead>
                            <tr>
                              <th style={{ width: '9%' }}>ID</th>
                              <th style={{ width: '23%' }}>Configuration Component</th>
                              <th style={{ width: '30%' }}>Data Gap / Unpopulated Field</th>
                              <th style={{ width: '13%' }}>Severity</th>
                              <th style={{ width: '25%' }}>Recommended Target Configuration</th>
                            </tr>
                          </thead>
                          <tbody>
                            {missingConfigs.map((cfg, cIdx) => (
                              <tr key={cIdx}>
                                <td><span className="workstream-id-badge">{cfg.id}</span></td>
                                <td><strong>{cfg.component}</strong></td>
                                <td>
                                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '4px', flexWrap: 'wrap' }}>
                                    <span
                                      style={{
                                        fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
                                        fontSize: '0.84rem',
                                        fontWeight: 700,
                                        color: cfg.severity === 'Critical' ? '#991b1b' : '#0369a1',
                                        background: cfg.severity === 'Critical' ? '#fef2f2' : '#f0f9ff',
                                        border: `1px solid ${cfg.severity === 'Critical' ? '#fecaca' : '#bae6fd'}`,
                                        padding: '2px 8px',
                                        borderRadius: '4px',
                                        letterSpacing: '0.01em'
                                      }}
                                    >
                                      {cfg.field || cfg.fieldName || cfg.title.replace(/^(Mandatory\s+Field\s+Missing:\s*|Missing\s+Field:\s*)/i, '').trim()}
                                    </span>
                                    {cfg.severity === 'Critical' && (
                                      <span style={{ fontSize: '0.68rem', fontWeight: 700, color: '#b91c1c', background: '#fee2e2', border: '1px solid #fca5a5', padding: '1px 6px', borderRadius: '3px', textTransform: 'uppercase' }}>
                                        Mandatory
                                      </span>
                                    )}
                                  </div>
                                  <div style={{ fontWeight: 600, fontSize: '0.82rem', color: '#1e293b' }}>{cfg.title}</div>
                                  <div style={{ fontSize: '0.76rem', color: '#64748b', marginTop: '3px' }}>
                                    Current Status: <span style={{ color: cfg.severity === 'Critical' ? '#b91c1c' : '#b45309', fontWeight: 600 }}>{cfg.status}</span>
                                  </div>
                                </td>
                                <td>
                                  <span className={`pill-badge ${cfg.severity === 'Critical' ? 'badge-critical' : cfg.severity === 'High' ? 'badge-at-risk' : 'badge-healthy'}`}>
                                    {cfg.severity}
                                  </span>
                                </td>
                                <td>
                                  <code className="cfg-setting-code">{cfg.setting}</code>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </>
                  )}
                </div>
              </div>

              {/* SECTION 04: ROOT CAUSE ANALYSIS (ALIGNED WITH BRD ORDER) */}
              <div id="sec-rca" className="diagnostic-card deepdive-card">
                <div className="diagnostic-card-header">
                  <div className="card-header-text">
                    <h2 className="diagnostic-card-title">4. Root Cause Analysis</h2>
                    <span className="diagnostic-card-subtitle">
                      {unifiedRcaDrivers.length > 0 ? 'Primary factors and stage drivers causing the breach, extracted from ML diagnostics' : 'Deep Failure Modes & Systemic Diagnostic Trace'}
                    </span>
                  </div>
                </div>
                <div className="diagnostic-card-content">
                  {!isMetricLive ? (
                    <div style={{ padding: '24px', textAlign: 'center', color: '#64748b' }}>
                      <p style={{ margin: 0, fontWeight: 500 }}>Data not yet fetched.</p>
                    </div>
                  ) : (!unifiedRcaDrivers.length && !rcaFailureModes?.length) ? (
                    <div style={{ padding: '16px 20px', borderRadius: '6px', background: '#fffbeb', border: '1px solid #fde68a', borderLeft: '4px solid #f59e0b', color: '#92400e' }}>
                      <div style={{ fontWeight: 700, fontSize: '13px', marginBottom: '3px' }}>⚠️ Data Gap: Factor Attribution Unavailable</div>
                      <div style={{ fontSize: '12px', color: '#b45309', lineHeight: 1.5 }}>
                        Root cause factor ranking and TreeSHAP attribution could not be calculated because mandatory records/fields are missing from the input data feed. Please refer to Section 3 (Data Gaps) for the unpopulated fields.
                      </div>
                    </div>
                  ) : (
                    <>
                      {unifiedRcaDrivers.length > 0 && (
                        <div className="brd-spec-table-container" style={{ margin: '0 0 16px 0', border: '1px solid #cbd5e1', borderRadius: '6px' }}>
                          <table className="brd-spec-table" style={{ width: '100%' }}>
                            <thead>
                              <tr>
                                <th style={{ width: '40%' }}>Root Cause Factor / Driver</th>
                                <th style={{ width: '18%' }}>Category</th>
                                <th style={{ width: '18%' }}>Impact / Value</th>
                                <th style={{ width: '16%' }}>Share of Breach</th>
                                <th style={{ width: '8%', textAlign: 'center' }}>ID</th>
                              </tr>
                            </thead>
                            <tbody>
                              {unifiedRcaDrivers.map((driver, dIdx) => (
                                <tr key={dIdx}>
                                  <td>
                                    <strong style={{ color: '#0f172a' }}>{driver.driver}</strong>
                                  </td>
                                  <td>
                                    <span
                                      style={{
                                        display: 'inline-block',
                                        fontSize: '0.72rem',
                                        fontWeight: 600,
                                        padding: '2px 8px',
                                        borderRadius: '4px',
                                        background: driver.typeBadgeBg,
                                        color: driver.typeBadgeColor,
                                        border: `1px solid ${driver.typeBadgeBorder}`,
                                        whiteSpace: 'nowrap'
                                      }}
                                    >
                                      {driver.type}
                                    </span>
                                  </td>
                                  <td style={{ fontWeight: 600, color: '#334155' }}>
                                    {driver.impact}
                                  </td>
                                  <td>
                                    <span style={{ fontWeight: 700, color: '#b91c1c' }}>
                                      {driver.share}
                                    </span>
                                  </td>
                                  <td style={{ textAlign: 'center' }}>
                                    <span className="workstream-id-badge">{driver.id}</span>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}

                      {!unifiedRcaDrivers.length && rcaFailureModes && rcaFailureModes.length > 0 && (
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
                      )}
                    </>
                  )}
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
                  {!isMetricLive || (!detailedAnalysis?.howItEffects && !businessImpactOverview && !financialExposure) || (['data not yet fetched', 'data not yet fetched from supabase'].includes(detailedAnalysis?.howItEffects?.toLowerCase?.()) && !financialExposure) ? (
                    <div style={{ padding: '24px', textAlign: 'center', color: '#64748b' }}>
                      <p style={{ margin: 0, fontWeight: 500 }}>Data not yet fetched.</p>
                    </div>
                  ) : (
                    <>
                      <p className="analysis-text-paragraph">{businessImpactOverview || detailedAnalysis?.howItEffects}</p>

                      <div className="impact-triad-grid">
                        <div className="impact-triad-card triad-cost">
                          <div className="triad-icon">💰</div>
                          <div className="triad-title">Financial Exposure</div>
                          <div className="triad-desc">
                            {financialExposure || 'Data not yet fetched'}
                          </div>
                        </div>
                        <div className="impact-triad-card triad-sla">
                          <div className="triad-icon">⏱️</div>
                          <div className="triad-title">SLA &amp; Turnaround</div>
                          <div className="triad-desc">
                            {slaAndTurnaround || 'Data not yet fetched'}
                          </div>
                        </div>
                        <div className="impact-triad-card triad-gov">
                          <div className="triad-icon">🛡️</div>
                          <div className="triad-title">Governance &amp; Audit</div>
                          <div className="triad-desc">
                            {governanceAndAudit || 'Data not yet fetched'}
                          </div>
                        </div>
                      </div>
                    </>
                  )}
                </div>
              </div>

              {/* SECTION 06: BRD PLAN OF ACTION */}
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
                  {!isMetricLive || (!brdPlan?.specialistManpower?.length && !brdPlan?.phasedActivities?.length) ? (
                    <div style={{ padding: '24px', textAlign: 'center', color: '#64748b' }}>
                      <p style={{ margin: 0, fontWeight: 500 }}>Data not yet fetched.</p>
                    </div>
                  ) : (
                    <>
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
                    </>
                  )}
                </div>
              </div>

              {/* SECTION 07: HOW TO OVERCOME - EXECUTION WORKSTREAMS */}
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
                  {!isMetricLive || !brdPlan?.executionWorkstreams?.length ? (
                    <div style={{ padding: '24px', textAlign: 'center', color: '#64748b' }}>
                      <p style={{ margin: 0, fontWeight: 500 }}>Data not yet fetched.</p>
                    </div>
                  ) : (
                    <>
                      {/* Execution Workstreams Matrix */}
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

                      {/* Target Outcome Banner */}
                      {brdPlan.targetOutcome && (
                        <div className="brd-target-outcome-banner">
                          <span className="brd-target-outcome-label">TARGET OUTCOME</span>
                          <span className="brd-target-outcome-text">{brdPlan.targetOutcome}</span>
                        </div>
                      )}
                    </>
                  )}
                </div>
              </div>

              {/* SECTION 08: SUCCESS CRITERIA, ASSUMPTIONS & RISKS */}
              <div id="sec-criteria" className="diagnostic-card deepdive-card">
                <div className="diagnostic-card-header">
                  <div className="card-header-text">
                    <h2 className="diagnostic-card-title">8. Success Criteria, Assumptions &amp; Risks</h2>
                    <span className="diagnostic-card-subtitle">
                      Measurable verification targets, implementation dependencies, and risk mitigations
                    </span>
                  </div>
                </div>

                <div className="diagnostic-card-content">
                  {!isMetricLive || (!brdPlan?.assumptionsAndRisks?.length && !brdPlan?.successCriteria?.length) ? (
                    <div style={{ padding: '24px', textAlign: 'center', color: '#64748b' }}>
                      <p style={{ margin: 0, fontWeight: 500 }}>Data not yet fetched.</p>
                    </div>
                  ) : (
                    <>
                      <div className="criteria-risks-split-grid">
                        {/* Success Criteria & Monitoring */}
                        {brdPlan.successCriteria && brdPlan.successCriteria.length > 0 && (
                          <div className="criteria-col">
                            <div className="brd-section-subheading" style={{ marginTop: '0px' }}>
                              <span>Success Criteria &amp; Monitoring</span>
                            </div>
                            <div className="brd-spec-table-container">
                              <table className="brd-spec-table">
                                <thead>
                                  <tr>
                                    <th style={{ width: '35%' }}>Criterion</th>
                                    <th style={{ width: '65%' }}>Target</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {brdPlan.successCriteria.map((sc, scIdx) => (
                                    <tr key={scIdx}>
                                      <td><strong>{sc.criterion}</strong></td>
                                      <td>{sc.target}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          </div>
                        )}

                        {/* Assumptions & Risks */}
                        {brdPlan.assumptionsAndRisks && brdPlan.assumptionsAndRisks.length > 0 && (
                          <div className="risks-col">
                            <div className="brd-section-subheading" style={{ marginTop: '0px' }}>
                              <span>Assumptions &amp; Risks</span>
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
                      <div className="brd-spec-footnote">
                        {brdPlan.footnote
                          ? brdPlan.footnote.replace('Sections 1, 3 and 4', 'Sections 1, 2, 3 and 4').replace('Sections 2 and 5-9', 'Sections 5–8')
                          : 'Sections 1, 2, 3 and 4 are rendered directly from telemetry, trend analysis, and configuration audit scans. Sections 5–8 are generated under the system prompt; effort and staffing are indicative estimates.'}
                      </div>
                    </>
                  )}
                </div>
              </div>

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
            className="fab-download-btn"
            onClick={handleDownloadPDF}
            disabled={isDownloading}
            aria-label="Download BRD Plan (PDF)"
            title="Download BRD Plan (PDF)"
          >
            <span className="fab-icon-box" aria-hidden="true">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                <polyline points="7 10 12 15 17 10"></polyline>
                <line x1="12" y1="15" x2="12" y2="3"></line>
              </svg>
            </span>
            <span className="fab-label-text">
              Download BRD Plan (PDF)
            </span>
          </button>
        </div>,
        document.body
      )}
    </div>
  );
}

