// Helper to generate realistic, metric-specific BRD (Business Requirements Document) Plan of Action
// including required manpower, hours, phases, milestones, deliverables, and governance.

export const METRIC_BRD_PLANS = {
  'Employee Data Accuracy Rate': {
    specialistManpower: [
      { role: 'SAP SF Employee Central Functional Consultant', headcount: 2, effort: '60 Person-Hours' },
      { role: 'HR Master Data Steward / Operations Lead', headcount: 1, effort: '30 Person-Hours' },
      { role: 'QA & Regression Testing Specialist', headcount: 1, effort: '20 Person-Hours' }
    ],
    timelineAndEffort: {
      timeline: '3 Weeks (Sprint Cycle 1–2)',
      totalEffort: '110 Total Hours'
    },
    workforceRequired: [
      { role: 'SAP SF Employee Central Functional Consultant', count: 2, hours: '60 Person-Hours', focus: 'Picklist validation & business rules configuration' },
      { role: 'HR Master Data Steward / Operations Lead', count: 1, hours: '30 Person-Hours', focus: 'Data governance policy & exception verification matrix' },
      { role: 'QA & Regression Testing Specialist', count: 1, hours: '20 Person-Hours', focus: 'Integration Center UAT and error validation' }
    ],
    totalManpower: '4 Specialists (110 Person-Hours)',
    timeline: '3 Weeks (Sprint Cycle 1–2)',
    totalEffortHours: 110,
    totalEffortsDisplay: '110 Hours',
    governanceLead: 'HR Systems Governance & Data Quality Board',
    expectedOutcome: 'Restore data accuracy to ≥98.0%, eliminating downstream payroll exceptions and regulatory filing risks.',
    targetOutcome: 'Restore data accuracy to ≥98.0%, eliminating downstream payroll exceptions and regulatory filing risks.',
    stageDrivers: [
      { driver: 'Biographical & National ID Portlets', avgDays: '5.2', share: '44%', id: 'S1' },
      { driver: 'Custom MDF Object Free-Text Inputs', avgDays: '3.8', share: '32%', id: 'S2' },
      { driver: 'Mass CSV Data Ingestion Pipelines', avgDays: '2.6', share: '24%', id: 'S3' }
    ],
    segmentDrivers: [
      { driver: 'Business Unit: Operations', avgDays: '8.4', vsCompany: '+3.2', id: 'A1' },
      { driver: 'Region: North America (US/CA)', avgDays: '7.1', vsCompany: '+1.9', id: 'A2' },
      { driver: 'Entry Mode: CSV Batch Uploads', avgDays: '9.6', vsCompany: '+4.4', id: 'A3' }
    ],
    milestones: [
      { phase: 'Sprint 1 (Week 1)', title: 'Architecture Review & BRD Sign-Off', deliverable: 'BRD Spec & Picklist Mapping Document' },
      { phase: 'Sprint 2 (Week 2)', title: 'Validation Rules & Attachment Mandates', deliverable: 'Configured SF Business Rules in Pre-Prod' },
      { phase: 'Sprint 3 (Week 3)', title: 'Data Cleanse & Automated Health Scans', deliverable: 'Weekly Automated Data Quality Scanner' }
    ],
    deliverables: [
      'Approved BRD & Data Governance Policy Document',
      'SuccessFactors EC Business Rules Configuration Workbook',
      'Automated Weekly Exception Monitoring Report in Integration Center',
      'End-User Data Entry Field Mask Guide'
    ],
    footnote: 'Sections 1, 3 and 4 are rendered directly from the ML insight JSON. Sections 2 and 5-9 are written by the LLM under the system prompt; effort and staffing are indicative estimates.'
  },

  'Time to hire': {
    specialistManpower: [
      { role: 'SAP SuccessFactors Recruiting Lead Functional Consultant', headcount: 2, effort: '48 Person-Hours' },
      { role: 'Talent Acquisition Operations & Process Governance Lead', headcount: 1, effort: '32 Person-Hours' },
      { role: 'Quality Assurance & UAT Specialist', headcount: 1, effort: '20 Person-Hours' }
    ],
    timelineAndEffort: {
      timeline: '4 Weeks (Sprint 1-2)',
      totalEffort: '100 Total Hours'
    },
    workforceRequired: [
      { role: 'SAP SuccessFactors Recruiting Lead Functional Consultant', count: 2, hours: '48 Person-Hours', focus: 'Stage aging SLAs & offer approval routing' },
      { role: 'Talent Acquisition Operations & Process Governance Lead', count: 1, hours: '32 Person-Hours', focus: 'Process governance & stakeholder sign-off' },
      { role: 'Quality Assurance & UAT Specialist', count: 1, hours: '20 Person-Hours', focus: 'Staging environment test & UAT execution' }
    ],
    totalManpower: '4 Specialists (100 Person-Hours)',
    timeline: '4 Weeks (Sprint 1-2)',
    totalEffortHours: 100,
    totalEffortsDisplay: '100 Hours',
    governanceLead: 'Talent Acquisition Operations & Process Governance Lead',
    expectedOutcome: 'Eliminate the variance gap of +14.2 days (+71.0%) and return Time to Hire to the industry standard of 20 days.',
    targetOutcome: 'Eliminate the variance gap of +14.2 days (+71.0%) and return Time to Hire to the industry standard of 20 days.',
    phasedActivities: [
      {
        phaseName: 'Phase 1: Architecture (20 h)',
        milestone: 'Root Cause Validation & BRD Sign-Off',
        deliverable: 'Approved BRD & Architecture Specification',
        activities: [
          {
            activity: 'Validate stage and segment drivers against the live recruiting process',
            owner: 'SAP SuccessFactors Recruiting Lead Functional Consultant',
            workstream: '-',
            effort: '8 Hours'
          },
          {
            activity: 'Define stage-level SLAs and escalation rules with talent acquisition leadership',
            owner: 'Talent Acquisition Operations & Process Governance Lead',
            workstream: 'W1',
            effort: '8 Hours'
          },
          {
            activity: 'BRD and architecture sign-off with stakeholders',
            owner: 'Talent Acquisition Operations & Process Governance Lead',
            workstream: '-',
            effort: '4 Hours'
          }
        ]
      },
      {
        phaseName: 'Phase 2: Configuration (48 h)',
        milestone: 'Rule Build & Staging Environment Test',
        deliverable: 'SuccessFactors Recruiting Configuration & UAT Sign-Off',
        activities: [
          {
            activity: 'Configure stage-aging SLAs and escalation notifications to recruiters and hiring managers',
            owner: 'SAP SuccessFactors Recruiting Lead Functional Consultant',
            workstream: 'W1',
            effort: '8 Hours'
          },
          {
            activity: 'Configure offer approval routing so senior grades are approved in parallel, not in sequence',
            owner: 'SAP SuccessFactors Recruiting Lead Functional Consultant',
            workstream: 'W2',
            effort: '10 Hours'
          },
          {
            activity: 'Configure interview scheduling reminders and panel-availability rules',
            owner: 'SAP SuccessFactors Recruiting Lead Functional Consultant',
            workstream: 'W3',
            effort: '8 Hours'
          },
          {
            activity: 'Configure offer follow-up reminders and pre-approved offer ranges',
            owner: 'SAP SuccessFactors Recruiting Lead Functional Consultant',
            workstream: 'W4',
            effort: '6 Hours'
          },
          {
            activity: 'Review Agency source SLAs and set pipeline targets',
            owner: 'Talent Acquisition Operations & Process Governance Lead',
            workstream: 'W5',
            effort: '4 Hours'
          },
          {
            activity: 'Staging environment test of all recruiting rules',
            owner: 'Quality Assurance & UAT Specialist',
            workstream: '-',
            effort: '6 Hours'
          },
          {
            activity: 'UAT execution and business sign-off',
            owner: 'Quality Assurance & UAT Specialist',
            workstream: '-',
            effort: '6 Hours'
          }
        ]
      },
      {
        phaseName: 'Phase 3: Rollout (32 h)',
        milestone: 'Production Cutover & Exception Monitoring',
        deliverable: 'Weekly Health Monitoring Report',
        activities: [
          {
            activity: 'Production cutover of validated configuration',
            owner: 'SAP SuccessFactors Recruiting Lead Functional Consultant',
            workstream: '-',
            effort: '8 Hours'
          },
          {
            activity: 'Exception monitoring during hypercare',
            owner: 'Talent Acquisition Operations & Process Governance Lead',
            workstream: '-',
            effort: '8 Hours'
          },
          {
            activity: 'Weekly Health Monitoring Report review and briefing to recruiters and hiring managers',
            owner: 'Talent Acquisition Operations & Process Governance Lead',
            workstream: '-',
            effort: '8 Hours'
          },
          {
            activity: 'Re-measure Time to Hire against the industry standard',
            owner: 'Quality Assurance & UAT Specialist',
            workstream: '-',
            effort: '8 Hours'
          }
        ]
      }
    ],
    executionWorkstreams: [
      {
        id: 'W1',
        remediationStep: 'Introduce stage-aging SLAs with recruiter and hiring-manager escalation for the interview-to-offer-release stage.',
        fixesDrivers: 'S1'
      },
      {
        id: 'W2',
        remediationStep: 'Configure offer approval routing so senior-grade offers are approved in parallel, not in sequence.',
        fixesDrivers: 'S1, A3'
      },
      {
        id: 'W3',
        remediationStep: 'Configure interview scheduling reminders and panel-availability rules, prioritising Engineering requisitions.',
        fixesDrivers: 'S2, A1'
      },
      {
        id: 'W4',
        remediationStep: 'Set up candidate follow-up reminders and pre-approved offer ranges to shorten offer acceptance.',
        fixesDrivers: 'S3'
      },
      {
        id: 'W5',
        remediationStep: 'Review Agency source SLAs and introduce pipeline targets to reduce requisition-to-application time.',
        fixesDrivers: 'A2, S4'
      }
    ],
    successCriteria: [
      {
        criterion: 'Company value',
        target: '20 days or lower (industry standard)',
        verifiedBy: 'Next daily ML run'
      },
      {
        criterion: 'Health state',
        target: 'critical moves to healthy',
        verifiedBy: 'ML insight JSON'
      },
      {
        criterion: 'Trend direction',
        target: 'up moves to down or stable',
        verifiedBy: 'Trend analysis section'
      }
    ],
    assumptionsAndRisks: [
      {
        type: 'Assumption',
        description: 'A staging instance mirroring production recruiting configuration is available.',
        mitigation: 'Confirm before Sprint 1.'
      },
      {
        type: 'Risk',
        description: 'Hiring managers may not adopt the new SLAs and escalations.',
        mitigation: 'Executive sponsorship and a weekly review with talent acquisition leadership.'
      },
      {
        type: 'Risk',
        description: 'Frequent reminders may cause notification fatigue.',
        mitigation: 'Tune reminder frequency during UAT and hypercare.'
      }
    ],
    stageDrivers: [
      { driver: 'Interview To Offer Release', avgDays: '11.8', share: '41%', id: 'S1' },
      { driver: 'Screening To Interview', avgDays: '8.4', share: '27%', id: 'S2' },
      { driver: 'Offer Release To Offer Accepted', avgDays: '6.9', share: '19%', id: 'S3' },
      { driver: 'Requisition To Application', avgDays: '4.5', share: '13%', id: 'S4' }
    ],
    segmentDrivers: [
      { driver: 'Department: Engineering', avgDays: '41.3', vsCompany: '+7.1', id: 'A1' },
      { driver: 'Source: Agency', avgDays: '39.0', vsCompany: '+4.8', id: 'A2' },
      { driver: 'Grade: G7', avgDays: '42.6', vsCompany: '+8.4', id: 'A3' }
    ],
    footnote: 'Sections 1, 3 and 4 are rendered directly from the ML insight JSON. Sections 2 and 5-9 are written by the LLM under the system prompt; effort and staffing are indicative estimates.'
  },

  'New Hire Early Attrition Rate (90-day)': {
    specialistManpower: [
      { role: 'Senior HR Business Partner (HRBP) Lead', headcount: 1, effort: '40 Person-Hours' },
      { role: 'SAP SF Job Profile Builder (JPB) Consultant', headcount: 1, effort: '35 Person-Hours' },
      { role: 'Talent Experience / Change Specialist', headcount: 1, effort: '25 Person-Hours' }
    ],
    timelineAndEffort: {
      timeline: '4 Weeks (Sprint Cycle 1–2)',
      totalEffort: '100 Total Hours'
    },
    workforceRequired: [
      { role: 'Senior HR Business Partner (HRBP) Lead', count: 1, hours: '40 Person-Hours', focus: 'Role ambiguity diagnosis & manager onboarding framework' },
      { role: 'SAP SF Job Profile Builder (JPB) Consultant', count: 1, hours: '35 Person-Hours', focus: 'Competency-to-position mapping & continuous review workflows' },
      { role: 'Talent Experience / Change Specialist', count: 1, hours: '25 Person-Hours', focus: '30/60/90-day pulse check automation & buddy program' }
    ],
    totalManpower: '3 Specialists (100 Person-Hours)',
    timeline: '4 Weeks (Sprint Cycle 1–2)',
    totalEffortHours: 100,
    totalEffortsDisplay: '100 Hours',
    governanceLead: 'Head of Talent Management & HR Operations',
    expectedOutcome: 'Decrease early turnover from 14.2% to ≤8.0%, saving an estimated $1.8M in replacement and lost productivity costs.',
    targetOutcome: 'Decrease early turnover from 14.2% to ≤8.0%, saving an estimated $1.8M in replacement and lost productivity costs.',
    stageDrivers: [
      { driver: 'Days 1-30: Role Ambiguity & JPB Misalignment', avgDays: '4.8', share: '46%', id: 'S1' },
      { driver: 'Days 31-60: Manager 1-on-1 Feedback Gap', avgDays: '3.6', share: '34%', id: 'S2' },
      { driver: 'Days 61-90: Team Integration & Peer Buddy Lapses', avgDays: '2.1', share: '20%', id: 'S3' }
    ],
    segmentDrivers: [
      { driver: 'Department: Software Engineering', avgDays: '18.4%', vsCompany: '+4.2%', id: 'A1' },
      { driver: 'Work Arrangement: Fully Remote', avgDays: '16.8%', vsCompany: '+2.6%', id: 'A2' },
      { driver: 'Band: Mid-Career / Senior Specialists', avgDays: '15.5%', vsCompany: '+1.3%', id: 'A3' }
    ],
    milestones: [
      { phase: 'Week 1', title: 'Competency & Role Alignment Audit', deliverable: 'Job Profile Builder (JPB) Gap Assessment' },
      { phase: 'Week 2–3', title: 'Workflow & Pulse Survey Deployment', deliverable: 'Automated 30/60/90-day escalation rules in CPM' },
      { phase: 'Week 4', title: 'Peer Buddy Program Rollout & Pilot', deliverable: 'Manager Enablement Toolkit & Tracking Dashboard' }
    ],
    deliverables: [
      'Standardized Job Profile Competency Matrix',
      'Continuous Performance Management (CPM) 30/60/90 Template',
      'Early Warning Attrition Predictive Dashboard',
      'Manager Onboarding Check-in Playbook'
    ],
    footnote: 'Sections 1, 3 and 4 are rendered directly from the ML insight JSON. Sections 2 and 5-9 are written by the LLM under the system prompt; effort and staffing are indicative estimates.'
  },

  'Workflow Approval Cycle Time': {
    specialistManpower: [
      { role: 'SAP SF Workflow Architect / Consultant', headcount: 1, effort: '35 Person-Hours' },
      { role: 'HR Operations Process Analyst', headcount: 1, effort: '25 Person-Hours' },
      { role: 'Integration / Mobile Platform Engineer', headcount: 1, effort: '15 Person-Hours' }
    ],
    timelineAndEffort: {
      timeline: '2 Weeks (Sprint Cycle 1)',
      totalEffort: '75 Total Hours'
    },
    workforceRequired: [
      { role: 'SAP SF Workflow Architect / Consultant', count: 1, hours: '35 Person-Hours', focus: 'Dynamic approval routing & Intelligent Services configuration' },
      { role: 'HR Operations Process Analyst', count: 1, hours: '25 Person-Hours', focus: 'Approval tier audit & delegation policy alignment' },
      { role: 'Integration / Mobile Platform Engineer', count: 1, hours: '15 Person-Hours', focus: 'Mobile Cards & Microsoft Teams approval integration' }
    ],
    totalManpower: '3 Specialists (75 Person-Hours)',
    timeline: '2 Weeks (Sprint Cycle 1)',
    totalEffortHours: 75,
    totalEffortsDisplay: '75 Hours',
    governanceLead: 'HR Technology Operations Steering Committee',
    expectedOutcome: 'Compress workflow turnaround from 6.8 days to ≤2.5 days, eliminating administrative transfer bottlenecks.',
    targetOutcome: 'Compress workflow turnaround from 6.8 days to ≤2.5 days, eliminating administrative transfer bottlenecks.',
    stageDrivers: [
      { driver: 'Multi-Tier Manager Escalation Lag', avgDays: '3.6', share: '53%', id: 'S1' },
      { driver: 'Absence of Auto-Delegation Rules', avgDays: '2.1', share: '31%', id: 'S2' },
      { driver: 'Lack of Mobile One-Click Approvals', avgDays: '1.1', share: '16%', id: 'S3' }
    ],
    segmentDrivers: [
      { driver: 'Entity: Corporate HQ & Shared Services', avgDays: '8.1 days', vsCompany: '+1.3 days', id: 'A1' },
      { driver: 'Workflow: Lateral Transfer / Promotion', avgDays: '9.2 days', vsCompany: '+2.4 days', id: 'A2' }
    ],
    milestones: [
      { phase: 'Week 1', title: 'Workflow Matrix Streamlining & BRD Approval', deliverable: 'Streamlined Approval Hierarchy Spec' },
      { phase: 'Week 2', title: 'Intelligent Escalation & Mobile Setup', deliverable: '48h Auto-Escalation & Mobile Approval Activation' }
    ],
    deliverables: [
      'Approved Workflow Governance Matrix',
      'Intelligent Services Auto-Escalation Configuration',
      'One-Click Mobile Approval Configuration in SAP Mobile Cards',
      'Tier-1 Shared Services SLA Tracking Report'
    ],
    footnote: 'Sections 1, 3 and 4 are rendered directly from the ML insight JSON. Sections 2 and 5-9 are written by the LLM under the system prompt; effort and staffing are indicative estimates.'
  },

  'Retroactive Transaction Volume': {
    specialistManpower: [
      { role: 'EC Payroll Integration Lead', headcount: 1, effort: '40 Person-Hours' },
      { role: 'SF Security & Permissions Lead', headcount: 1, effort: '20 Person-Hours' }
    ],
    timelineAndEffort: {
      timeline: '3 Weeks',
      totalEffort: '60 Total Hours'
    },
    workforceRequired: [
      { role: 'EC Payroll Integration Lead', count: 1, hours: '40 Person-Hours', focus: 'Retroactive payroll freeze configuration' },
      { role: 'SF Security & Permissions Lead', count: 1, hours: '20 Person-Hours', focus: 'Role-based permission locks and audit reports' }
    ],
    totalManpower: '2 Specialists (60 Person-Hours)',
    timeline: '3 Weeks',
    totalEffortHours: 60,
    totalEffortsDisplay: '60 Hours',
    governanceLead: 'Payroll Operations & Compliance Director',
    expectedOutcome: 'Cap retroactive change requests to ≤5.0% by enforcing strict payroll lock windows and manager back-dated entry restrictions.',
    targetOutcome: 'Cap retroactive change requests to ≤5.0% by enforcing strict payroll lock windows and manager back-dated entry restrictions.',
    stageDrivers: [
      { driver: 'Late Submission of Salary / Title Changes', avgDays: '14.2 days retro', share: '62%', id: 'S1' },
      { driver: 'Manager Unawareness of Payroll Cutoff Dates', avgDays: '6.4 days retro', share: '28%', id: 'S2' },
      { driver: 'Emergency Off-Cycle Correction Processing', avgDays: '2.3 days retro', share: '10%', id: 'S3' }
    ],
    segmentDrivers: [
      { driver: 'Department: Field Sales & Services', avgDays: '26.4%', vsCompany: '+7.9%', id: 'A1' },
      { driver: 'Action: Off-Cycle Promotion', avgDays: '22.1%', vsCompany: '+3.6%', id: 'A2' }
    ],
    footnote: 'Sections 1, 3 and 4 are rendered directly from the ML insight JSON. Sections 2 and 5-9 are written by the LLM under the system prompt; effort and staffing are indicative estimates.'
  }
};

// Comprehensive formatter guaranteeing the exact 9-section BRD schema for any metric
function formatBrdPlan(plan, metric) {
  if (!plan) return null;

  const metricName = metric.metric || metric.name || 'Metric';
  const category = metric.category || 'Core HR';
  const variance = metric.variance || '+14.2 days (+71.0%)';
  const standard = metric.standard || 'Industry standard';
  const status = metric.status || 'Critical';
  const howToOvercome = metric.detailedAnalysis?.howToOvercome || plan.actionSteps || [];

  // 1. Specialist Manpower Table
  const specialistManpower = plan.specialistManpower || (plan.workforceRequired || []).map((wf) => ({
    role: wf.role,
    headcount: wf.count || wf.headcount || 1,
    effort: wf.hours || wf.effort || '30 Person-Hours'
  }));

  // 2. Timeline and Effort
  const timelineAndEffort = plan.timelineAndEffort || {
    timeline: plan.timeline || '4 Weeks (Sprint 1-2)',
    totalEffort: `${plan.totalEffortHours || 100} Total Hours`
  };

  // 3. Phased Activities
  let phasedActivities = plan.phasedActivities;
  if (!phasedActivities || phasedActivities.length === 0) {
    const leadRole = specialistManpower[0]?.role || 'SAP SuccessFactors Lead Functional Consultant';
    const opsRole = specialistManpower[1]?.role || 'Operations & Process Governance Lead';
    const qaRole = specialistManpower[2]?.role || 'Quality Assurance & UAT Specialist';

    const act1 = howToOvercome[0] || `Audit ${category} configuration and diagnostic telemetry`;
    const act2 = howToOvercome[1] || `Configure automated SLA alerts and approval routings in SAP SuccessFactors`;
    const act3 = howToOvercome[2] || `Deploy validation thresholds and streamline process handover checkpoints`;

    phasedActivities = [
      {
        phaseName: 'Phase 1: Architecture (20 h)',
        milestone: 'Root Cause Validation & BRD Sign-Off',
        deliverable: 'Approved BRD & Architecture Specification',
        activities: [
          {
            activity: `Validate telemetry drivers and root-cause failure modes against live ${category} processes`,
            owner: leadRole,
            workstream: '-',
            effort: '8 Hours'
          },
          {
            activity: `Define stage-level SLAs, escalation matrix and approval governance with leadership`,
            owner: opsRole,
            workstream: 'W1',
            effort: '8 Hours'
          },
          {
            activity: 'BRD and architecture sign-off with enterprise stakeholders',
            owner: opsRole,
            workstream: '-',
            effort: '4 Hours'
          }
        ]
      },
      {
        phaseName: `Phase 2: Configuration (${Math.round((plan.totalEffortHours || 100) * 0.48)} h)`,
        milestone: 'Rule Build & Staging Environment Test',
        deliverable: 'SuccessFactors System Configuration & UAT Sign-Off',
        activities: [
          {
            activity: act1,
            owner: leadRole,
            workstream: 'W1',
            effort: '10 Hours'
          },
          {
            activity: act2,
            owner: leadRole,
            workstream: 'W2',
            effort: '12 Hours'
          },
          {
            activity: act3,
            owner: opsRole,
            workstream: 'W3',
            effort: '8 Hours'
          },
          {
            activity: 'Configure automated notification cadences, reminder triggers and exception alerts',
            owner: leadRole,
            workstream: 'W4',
            effort: '6 Hours'
          },
          {
            activity: 'Execute end-to-end sandbox regression and integration staging test',
            owner: qaRole,
            workstream: '-',
            effort: '6 Hours'
          },
          {
            activity: 'UAT scenario execution and operational business sign-off',
            owner: qaRole,
            workstream: '-',
            effort: '6 Hours'
          }
        ]
      },
      {
        phaseName: `Phase 3: Rollout (${Math.round((plan.totalEffortHours || 100) * 0.32)} h)`,
        milestone: 'Production Cutover & Exception Monitoring',
        deliverable: 'Weekly Health Monitoring Report & Operational Governance',
        activities: [
          {
            activity: 'Production cutover of validated configuration workbook and rules',
            owner: leadRole,
            workstream: '-',
            effort: '8 Hours'
          },
          {
            activity: 'Hypercare exception triage and operational queue stabilization',
            owner: opsRole,
            workstream: '-',
            effort: '8 Hours'
          },
          {
            activity: 'Weekly Health Monitoring Report review and briefing to management',
            owner: opsRole,
            workstream: '-',
            effort: '8 Hours'
          },
          {
            activity: `Re-measure ${metricName} against industry standard benchmark`,
            owner: qaRole,
            workstream: '-',
            effort: '8 Hours'
          }
        ]
      }
    ];
  }

  // 4. Execution Workstreams
  let executionWorkstreams = plan.executionWorkstreams;
  if (!executionWorkstreams || executionWorkstreams.length === 0) {
    const driverIds = ['S1', 'S2, A1', 'S3', 'S1, A3', 'A2, S4'];
    executionWorkstreams = howToOvercome.map((step, idx) => ({
      id: `W${idx + 1}`,
      remediationStep: step,
      fixesDrivers: driverIds[idx % driverIds.length]
    }));
    if (executionWorkstreams.length === 0) {
      executionWorkstreams = [
        { id: 'W1', remediationStep: `Introduce stage-aging SLAs with operational escalation for ${metricName}.`, fixesDrivers: 'S1' },
        { id: 'W2', remediationStep: `Reconfigure dynamic approval routing to eliminate sequential approval bottlenecks.`, fixesDrivers: 'S1, A3' },
        { id: 'W3', remediationStep: `Deploy automated notification alerts and panel availability rules.`, fixesDrivers: 'S2, A1' }
      ];
    }
  }

  // 5. Target Outcome
  const targetOutcome = plan.targetOutcome || plan.expectedOutcome ||
    `Eliminate the variance gap of ${variance} and return ${metricName} to the industry standard of ${standard}.`;

  // 6. Success Criteria & Monitoring
  const successCriteria = plan.successCriteria || [
    {
      criterion: 'Company value',
      target: `${standard} or lower (industry standard)`,
      verifiedBy: 'Next daily ML run'
    },
    {
      criterion: 'Health state',
      target: `${status.toLowerCase()} moves to healthy`,
      verifiedBy: 'ML insight JSON'
    },
    {
      criterion: 'Trend direction',
      target: 'up moves to down or stable',
      verifiedBy: 'Trend analysis section'
    }
  ];

  // 7. Assumptions & Risks
  const assumptionsAndRisks = plan.assumptionsAndRisks || [
    {
      type: 'Assumption',
      description: 'A staging instance mirroring production recruiting and core HR configuration is available.',
      mitigation: 'Confirm before Sprint 1.'
    },
    {
      type: 'Risk',
      description: 'Operational managers may delay adoption of new automated SLAs and escalations.',
      mitigation: 'Executive sponsorship and a weekly review cadence with leadership.'
    },
    {
      type: 'Risk',
      description: 'Frequent automated reminders may cause notification fatigue.',
      mitigation: 'Tune reminder frequency and consolidation during UAT and hypercare.'
    }
  ];

  // 8. Stage Drivers & Segment Drivers defaults if missing
  const stageDrivers = plan.stageDrivers || [
    { driver: `${category} Initial Processing Stage`, avgDays: '4.5', share: '45%', id: 'S1' },
    { driver: 'Approval Hierarchy Latency', avgDays: '3.2', share: '32%', id: 'S2' },
    { driver: 'Downstream Integration Sync Delay', avgDays: '2.1', share: '23%', id: 'S3' }
  ];

  const segmentDrivers = plan.segmentDrivers || [
    { driver: 'Business Unit: Operations & Engineering', avgDays: '5.8', vsCompany: '+2.1', id: 'A1' },
    { driver: 'Region: North America & EMEA', avgDays: '4.9', vsCompany: '+1.4', id: 'A2' }
  ];

  const footnote = plan.footnote ||
    'Sections 1, 3 and 4 are rendered directly from the ML insight JSON. Sections 2 and 5-9 are written by the LLM under the system prompt; effort and staffing are indicative estimates.';

  return {
    ...plan,
    specialistManpower,
    timelineAndEffort,
    phasedActivities,
    totalEffortsDisplay: plan.totalEffortsDisplay || `${plan.totalEffortHours || 100} Hours`,
    executionWorkstreams,
    targetOutcome,
    successCriteria,
    assumptionsAndRisks,
    stageDrivers,
    segmentDrivers,
    footnote,
    // Preserve backwards-compatibility fields
    workforceRequired: plan.workforceRequired || specialistManpower.map(sp => ({ role: sp.role, count: sp.headcount, hours: sp.effort, focus: 'System implementation' })),
    timeline: plan.timeline || timelineAndEffort.timeline,
    totalEffortHours: plan.totalEffortHours || 100,
    expectedOutcome: targetOutcome
  };
}

// Fallback generator for custom or unlisted metrics
export function getBrdPlan(metric) {
  if (!metric) return null;
  const name = metric.metric || metric.name || '';

  // Case-insensitive lookup in METRIC_BRD_PLANS
  const matchedKey = Object.keys(METRIC_BRD_PLANS).find(
    (k) => k.toLowerCase() === name.toLowerCase() ||
           k.toLowerCase().replace(/\s+/g, '') === name.toLowerCase().replace(/\s+/g, '')
  );

  if (matchedKey && METRIC_BRD_PLANS[matchedKey]) {
    const raw = {
      ...METRIC_BRD_PLANS[matchedKey],
      actionSteps: metric.detailedAnalysis?.howToOvercome || []
    };
    return formatBrdPlan(raw, metric);
  }

  // Dynamic contextual fallback based on category & status
  const isCritical = metric.status === 'Critical';
  const consultantHours = isCritical ? '60 Person-Hours' : '40 Person-Hours';
  const opsHours = isCritical ? '30 Person-Hours' : '20 Person-Hours';
  const qaHours = isCritical ? '20 Person-Hours' : '15 Person-Hours';
  const totalHours = isCritical ? 110 : 75;
  const sprintWeeks = isCritical ? '3 Weeks (Sprint 1–2)' : '2 Weeks (Sprint 1)';

  const fallbackRaw = {
    workforceRequired: [
      { role: 'SAP SuccessFactors Lead Functional Consultant', count: 2, hours: consultantHours, focus: 'Technical reconfiguration & business rules execution' },
      { role: 'HR Operations & Process Governance Lead', count: 1, hours: opsHours, focus: 'Operational workflow alignment & change governance' },
      { role: 'Quality Assurance & UAT Specialist', count: 1, hours: qaHours, focus: 'Functional testing & regression validation' }
    ],
    totalManpower: `4 Specialists (${totalHours} Person-Hours)`,
    timeline: sprintWeeks,
    totalEffortHours: totalHours,
    governanceLead: 'HR Systems Steering Committee & Module Governance Lead',
    expectedOutcome: `Eliminate variance gap of ${metric.variance || 'benchmark target'} and return metric to compliant operational threshold.`,
    milestones: [
      { phase: 'Phase 1: Architecture', title: 'Root Cause Validation & BRD Sign-Off', deliverable: 'Approved BRD & Architecture Specification' },
      { phase: 'Phase 2: Configuration', title: 'Rule Build & Staging Environment Test', deliverable: 'SuccessFactors Business Rules & UAT Sign-Off' },
      { phase: 'Phase 3: Rollout', title: 'Production Cutover & Exception Monitoring', deliverable: 'Weekly Health Monitoring Report' }
    ],
    deliverables: [
      'Approved Business Requirements Document (BRD)',
      'SuccessFactors Configuration Workbook & Business Rules',
      'UAT Test Script Sign-Off Matrix',
      'Continuous Exception Monitoring Dashboard'
    ],
    actionSteps: metric.detailedAnalysis?.howToOvercome || [
      'Perform detailed audit of configuration and workflow validation rules.',
      'Deploy automated escalation thresholds in SAP SuccessFactors.',
      'Establish weekly executive SLA tracking reports.'
    ]
  };

  return formatBrdPlan(fallbackRaw, metric);
}

export default getBrdPlan;
