// Helper to generate realistic, metric-specific BRD (Business Requirements Document) Plan of Action
// including required manpower, hours, phases, milestones, deliverables, and governance.

export const METRIC_BRD_PLANS = {
  'Biographical & Personal Data Accuracy Rate': {
    workforceRequired: [
      { role: 'SAP SF Employee Central Functional Consultant', count: 2, hours: '60 Person-Hours', focus: 'Picklist validation & business rules configuration' },
      { role: 'HR Master Data Steward / Operations Lead', count: 1, hours: '30 Person-Hours', focus: 'Data governance policy & exception verification matrix' },
      { role: 'QA & Regression Testing Specialist', count: 1, hours: '20 Person-Hours', focus: 'Integration Center UAT and error validation' }
    ],
    totalManpower: '4 Specialists (110 Person-Hours)',
    timeline: '3 Weeks (Sprint Cycle 1–2)',
    totalEffortHours: 110,
    governanceLead: 'HR Systems Governance & Data Quality Board',
    expectedOutcome: 'Restore data accuracy to ≥98.0%, eliminating downstream payroll exceptions and regulatory filing risks.',
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
    ]
  },

  'New Hire Early Attrition Rate (90-day)': {
    workforceRequired: [
      { role: 'Senior HR Business Partner (HRBP) Lead', count: 1, hours: '40 Person-Hours', focus: 'Role ambiguity diagnosis & manager onboarding framework' },
      { role: 'SAP SF Job Profile Builder (JPB) Consultant', count: 1, hours: '35 Person-Hours', focus: 'Competency-to-position mapping & continuous review workflows' },
      { role: 'Talent Experience / Change Specialist', count: 1, hours: '25 Person-Hours', focus: '30/60/90-day pulse check automation & buddy program' }
    ],
    totalManpower: '3 Specialists (100 Person-Hours)',
    timeline: '4 Weeks (Sprint Cycle 1–2)',
    totalEffortHours: 100,
    governanceLead: 'Head of Talent Management & HR Operations',
    expectedOutcome: 'Decrease early turnover from 14.2% to ≤8.0%, saving an estimated $1.8M in replacement and lost productivity costs.',
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
    ]
  },

  'Workflow Approval Cycle Time': {
    workforceRequired: [
      { role: 'SAP SF Workflow Architect / Consultant', count: 1, hours: '35 Person-Hours', focus: 'Dynamic approval routing & Intelligent Services configuration' },
      { role: 'HR Operations Process Analyst', count: 1, hours: '25 Person-Hours', focus: 'Approval tier audit & delegation policy alignment' },
      { role: 'Integration / Mobile Platform Engineer', count: 1, hours: '15 Person-Hours', focus: 'Mobile Cards & Microsoft Teams approval integration' }
    ],
    totalManpower: '3 Specialists (75 Person-Hours)',
    timeline: '2 Weeks (Sprint Cycle 1)',
    totalEffortHours: 75,
    governanceLead: 'HR Technology Operations Steering Committee',
    expectedOutcome: 'Compress workflow turnaround from 6.8 days to ≤2.5 days, eliminating administrative transfer bottlenecks.',
    milestones: [
      { phase: 'Week 1', title: 'Workflow Matrix Streamlining & BRD Approval', deliverable: 'Streamlined Approval Hierarchy Spec' },
      { phase: 'Week 2', title: 'Intelligent Escalation & Mobile Setup', deliverable: '48h Auto-Escalation & Mobile Approval Activation' }
    ],
    deliverables: [
      'Approved Workflow Governance Matrix',
      'Intelligent Services Auto-Escalation Configuration',
      'One-Click Mobile Approval Configuration in SAP Mobile Cards',
      'Tier-1 Shared Services SLA Tracking Report'
    ]
  },

  'Position Management Accuracy': {
    workforceRequired: [
      { role: 'SAP SF MDF & Position Management Specialist', count: 1, hours: '30 Person-Hours', focus: 'MDF position-to-job sync & nightly reconciliation jobs' },
      { role: 'Organizational Design / HRBP Analyst', count: 1, hours: '20 Person-Hours', focus: 'Hierarchy validation & vacant position archival policy' }
    ],
    totalManpower: '2 Specialists (50 Person-Hours)',
    timeline: '2 Weeks',
    totalEffortHours: 50,
    governanceLead: 'Workforce Planning & Org Governance Lead',
    expectedOutcome: 'Increase position accuracy to ≥95.0%, preventing headcount budget distortion and vacant job requisition errors.',
    milestones: [
      { phase: 'Week 1', title: 'Position Hierarchy Health Audit', deliverable: 'Orphan & Stale Position Reconciliation Log' },
      { phase: 'Week 2', title: 'Automated Sync & Archival Job Build', deliverable: 'Nightly MDF Reconciliation Scheduled Job' }
    ],
    deliverables: [
      'Position Management Governance Policy',
      'Automated 180-Day Vacancy Archival Rule',
      'Nightly Reconciliation Batch Schedule'
    ]
  },

  'Avg. Time to Process Data Change Requests': {
    workforceRequired: [
      { role: 'SAP SF ESS/MSS Portal Specialist', count: 1, hours: '30 Person-Hours', focus: 'Guided self-service wizards and field mask validation' },
      { role: 'HR Shared Services Operations Coordinator', count: 1, hours: '20 Person-Hours', focus: 'Service Center queue routing and SLA escalation thresholds' }
    ],
    totalManpower: '2 Specialists (50 Person-Hours)',
    timeline: '2 Weeks',
    totalEffortHours: 50,
    governanceLead: 'Head of HR Shared Services',
    expectedOutcome: 'Reduce change processing time from 4.5 days to ≤2.0 days, lowering operational backlog by 40%.',
    milestones: [
      { phase: 'Week 1', title: 'ESS Request Friction Analysis', deliverable: 'Guided Wizard Wireframes & Spec' },
      { phase: 'Week 2', title: 'Validation Rules & SLA Queue Deployment', deliverable: 'Service Center Notification Queues' }
    ],
    deliverables: [
      'Guided Employee Self-Service Form Workflow',
      'Automated Document OCR Verification Protocol',
      'HR Shared Services Queue Dashboard'
    ]
  },

  'Data Sync Error Rate to Downstream Systems': {
    workforceRequired: [
      { role: 'SAP Cloud Integration (CPI) Architect', count: 2, hours: '50 Person-Hours', focus: 'Compound Employee API mapping and schema pre-flight validations' },
      { role: 'Active Directory / Downstream ERP Engineer', count: 1, hours: '25 Person-Hours', focus: 'Middleware exception handling and queue alert webhooks' }
    ],
    totalManpower: '3 Specialists (75 Person-Hours)',
    timeline: '3 Weeks',
    totalEffortHours: 75,
    governanceLead: 'Enterprise IT Integration Lead',
    expectedOutcome: 'Curtail sync error rate to ≤1.0%, eliminating employee access delays and enterprise data warehouse mismatches.',
    milestones: [
      { phase: 'Week 1', title: 'Schema Diff & Error Log Triage', deliverable: 'Integration Error Root-Cause Catalogue' },
      { phase: 'Week 2', title: 'CPI Package Hardening & Pre-Flight Checks', deliverable: 'Standardized SAP CPI Integration Pipeline' },
      { phase: 'Week 3', title: 'Real-Time Alerting & Cutover', deliverable: 'Automated Operations Alert Webhook' }
    ],
    deliverables: [
      'Updated SAP CPI Integration Architecture Spec',
      'Pre-Flight API Payload Validation Rules',
      'Automated IT Incident Alerting Pipeline'
    ]
  },

  'Retroactive Data Changes Frequency': {
    workforceRequired: [
      { role: 'SAP SF Business Rules Consultant', count: 1, hours: '35 Person-Hours', focus: 'Hard retroactive validation rules and VP approval escalation triggers' },
      { role: 'Payroll Operations Specialist', count: 1, hours: '20 Person-Hours', focus: 'Retro-payroll impact assessment and cut-off schedule rules' },
      { role: 'HR Change & Enablement Trainer', count: 1, hours: '15 Person-Hours', focus: 'Manager prospective scheduling curriculum' }
    ],
    totalManpower: '3 Specialists (70 Person-Hours)',
    timeline: '2 Weeks',
    totalEffortHours: 70,
    governanceLead: 'VP of Payroll & HR Technology',
    expectedOutcome: 'Slash retroactive updates from 18.5% to ≤5.0%, preventing off-cycle payroll recalculations and tax discrepancies.',
    milestones: [
      { phase: 'Week 1', title: 'Validation Rule Construction & Approval', deliverable: '14-Day Retro Restriction Business Rule' },
      { phase: 'Week 2', title: 'Manager Milestone Notifications & Training', deliverable: '30-Day Contract Expiry Automated Alerts' }
    ],
    deliverables: [
      'Retroactive Data Governance Policy',
      'Configured Hard Validation Rule (>14 Days)',
      'Manager Prospective Scheduling Training Module'
    ]
  },

  'Time to hire': {
    workforceRequired: [
      { role: 'SAP SF Recruiting (RCM) Lead Consultant', count: 1, hours: '40 Person-Hours', focus: 'Interview Central automated self-scheduling & scorecard SLA triggers' },
      { role: 'Senior Talent Acquisition Operations Lead', count: 1, hours: '30 Person-Hours', focus: 'Recruiter screening playbooks and hiring manager interview caps' },
      { role: 'Recruitment Enablement Specialist', count: 1, hours: '20 Person-Hours', focus: 'Automated interviewer reminder nudges and training' }
    ],
    totalManpower: '3 Specialists (90 Person-Hours)',
    timeline: '3 Weeks (Sprint Cycle 1–2)',
    totalEffortHours: 90,
    governanceLead: 'Head of Global Talent Acquisition',
    expectedOutcome: 'Shorten hiring cycle from 48 days to ≤30 days, cutting candidate drop-off and saving ~28% in external agency costs.',
    milestones: [
      { phase: 'Week 1', title: 'Interview Workflow Audit & Cap Implementation', deliverable: '3-Round Interview Process Policy' },
      { phase: 'Week 2', title: 'Interview Central Self-Scheduling Setup', deliverable: 'Self-Scheduling Integration in SF RCM' },
      { phase: 'Week 3', title: '24-Hour Scorecard SLA & Manager Alerts', deliverable: 'Automated SLA Escalation Rules' }
    ],
    deliverables: [
      'Global Interview Process Governance Standard',
      'Configured Interview Central Self-Scheduling Module',
      '24-Hour Scorecard SLA Auto-Reminder System',
      'Recruitment Velocity Executive Dashboard'
    ]
  },

  'Applicant-to-Interview Conversion Rate': {
    workforceRequired: [
      { role: 'SAP SF Recruiting Marketing (RMK) Specialist', count: 1, hours: '35 Person-Hours', focus: 'Pre-screening knockout questions & AI candidate matching rules' },
      { role: 'Talent Acquisition Sourcing Lead', count: 1, hours: '25 Person-Hours', focus: 'Competency profile alignment with Job Profile Builder' }
    ],
    totalManpower: '2 Specialists (60 Person-Hours)',
    timeline: '2 Weeks',
    totalEffortHours: 60,
    governanceLead: 'Director of Talent Acquisition',
    expectedOutcome: 'Boost applicant qualification conversion from 12.4% to ≥20.0%, cutting recruiter triage time by 50%.',
    milestones: [
      { phase: 'Week 1', title: 'Pre-Screening Knockout Question Formulation', deliverable: 'Role-Specific Knockout Question Bank' },
      { phase: 'Week 2', title: 'SF AI Candidate Matching Activation', deliverable: 'AI Fit-Score Threshold Configuration' }
    ],
    deliverables: [
      'Job Requisition Knockout Question Matrix',
      'Automated Applicant Qualification Scoring Rules',
      'Revised Job Description Competency Templates'
    ]
  },

  'Offer acceptance rate': {
    workforceRequired: [
      { role: 'Total Rewards / Compensation Analyst', count: 1, hours: '25 Person-Hours', focus: 'Live market salary benchmarking integration in RCM' },
      { role: 'Recruiting Operations Specialist', count: 1, hours: '20 Person-Hours', focus: '48-hour offer letter generation workflow and digital signature' }
    ],
    totalManpower: '2 Specialists (45 Person-Hours)',
    timeline: '2 Weeks',
    totalEffortHours: 45,
    governanceLead: 'VP of Total Rewards & Talent',
    expectedOutcome: 'Increase offer acceptance from 81.0% to ≥88.0%, preventing search restarts and candidate loss to competitors.',
    milestones: [
      { phase: 'Week 1', title: 'Offer Turnaround Acceleration Workflow', deliverable: 'Streamlined 48-Hour Offer Workflow' },
      { phase: 'Week 2', title: 'Digital Total Rewards Preview Portal', deliverable: 'Candidate Dynamic Offer Letter Template' }
    ],
    deliverables: [
      'Accelerated Offer Approval Workflow Specification',
      'Candidate Total Rewards Digital Preview Module',
      'Market Benchmark Integration Guide'
    ]
  },

  'Requisition Aging': {
    workforceRequired: [
      { role: 'Talent Acquisition Operations Manager', count: 1, hours: '30 Person-Hours', focus: 'Bi-weekly aging audit governance & requisition freeze policies' },
      { role: 'Recruitment Sourcing Specialist', count: 1, hours: '25 Person-Hours', focus: 'Targeted CRM talent pools for long-open requisitions' }
    ],
    totalManpower: '2 Specialists (55 Person-Hours)',
    timeline: '2 Weeks',
    totalEffortHours: 55,
    governanceLead: 'Global Head of Recruiting',
    expectedOutcome: 'Lower average aging from 64 days to ≤45 days, alleviating workload strain across business units.',
    milestones: [
      { phase: 'Week 1', title: 'Requisition Audit & Triage Review', deliverable: 'Aged Requisition Action Log (>45 Days)' },
      { phase: 'Week 2', title: 'Proactive Talent Pool Activation', deliverable: 'SF Candidate Relationship Management (CRM) Pools' }
    ],
    deliverables: [
      'Requisition Lifecycle & Re-Authorization Policy',
      'Candidate Talent Pool Pipeline Strategy',
      'Bi-Weekly Requisition Aging Executive Report'
    ]
  },

  'Onboarding Cycle Time': {
    workforceRequired: [
      { role: 'SAP SF Onboarding 2.0 Lead Consultant', count: 2, hours: '50 Person-Hours', focus: 'Automated event-triggered onboarding and cross-system task flows' },
      { role: 'IT Hardware & Asset Provisioning Lead', count: 1, hours: '25 Person-Hours', focus: 'Pre-Day-1 automated IT equipment dispatch workflow' },
      { role: 'People Experience Coordinator', count: 1, hours: '20 Person-Hours', focus: 'Unified task checklist and manager buddy communication' }
    ],
    totalManpower: '4 Specialists (95 Person-Hours)',
    timeline: '3 Weeks (Sprint Cycle 1–2)',
    totalEffortHours: 95,
    governanceLead: 'Director of Employee Experience & IT Services',
    expectedOutcome: 'Compress onboarding cycle from 14.5 days to ≤7.0 days, ensuring Day-1 readiness and eliminating idle time.',
    milestones: [
      { phase: 'Week 1', title: 'Cross-Departmental Handshake Design', deliverable: 'HR-IT-Facilities Parallel Handshake Spec' },
      { phase: 'Week 2', title: 'Onboarding 2.0 Automated Trigger Build', deliverable: 'Automated Initiation upon Offer Acceptance' },
      { phase: 'Week 3', title: 'Work Zone Unified Checklist & Pilot', deliverable: 'Integrated New Hire Journey Dashboard' }
    ],
    deliverables: [
      'Cross-Functional Day-1 Readiness SLA Agreement',
      'Configured SF Onboarding 2.0 Process Flow',
      'SAP Work Zone Unified Onboarding Checklist',
      'Automated Manager 7-Day Pre-Arrival Nudge System'
    ]
  },

  'Pre-Day-1 Task Completion Rate': {
    workforceRequired: [
      { role: 'SAP SF Onboarding Specialist', count: 1, hours: '35 Person-Hours', focus: 'Passwordless magic-link login and mobile-friendly compliance forms' },
      { role: 'HR Operations Coordinator', count: 1, hours: '20 Person-Hours', focus: 'Automated SMS and email nudge cadences' }
    ],
    totalManpower: '2 Specialists (55 Person-Hours)',
    timeline: '2 Weeks',
    totalEffortHours: 55,
    governanceLead: 'HR Operations & Onboarding Lead',
    expectedOutcome: 'Elevate task completion from 68.0% to ≥90.0%, freeing Day-1 for team assimilation and culture.',
    milestones: [
      { phase: 'Week 1', title: 'Mobile Login & Authentication Overhaul', deliverable: 'Magic-Link Authentication Configuration' },
      { phase: 'Week 2', title: 'Responsive Form Build & SMS Nudge Triggers', deliverable: 'Automated T-5 and T-2 Day SMS Alerts' }
    ],
    deliverables: [
      'Mobile-Optimized Pre-Day-1 Compliance Forms',
      'Magic-Link Authentication Protocol Specification',
      'Automated Candidate Reminder Notification Rules'
    ]
  },

  'Day 30/60/90 Milestone Completion Rate': {
    workforceRequired: [
      { role: 'SAP SF Continuous Performance Management (CPM) Consultant', count: 1, hours: '30 Person-Hours', focus: '30/60/90-day structured review forms embedded in CPM' },
      { role: 'People & Culture Program Lead', count: 1, hours: '25 Person-Hours', focus: 'Manager calendar automation and leadership compliance tracking' }
    ],
    totalManpower: '2 Specialists (55 Person-Hours)',
    timeline: '2 Weeks',
    totalEffortHours: 55,
    governanceLead: 'VP of Organizational Development',
    expectedOutcome: 'Increase milestone completion from 76.4% to ≥88.0%, identifying role mismatches early to reduce turnover.',
    milestones: [
      { phase: 'Week 1', title: 'Review Form Design in CPM', deliverable: 'Standardized 30/60/90 Feedback Template' },
      { phase: 'Week 2', title: 'Calendar Sync & Department Compliance Dashboards', deliverable: 'Automated Manager Calendar Invites' }
    ],
    deliverables: [
      'Embedded Continuous Performance Management Milestone Form',
      'Automated Manager Calendar Integration Playbook',
      'Department Milestone Compliance Report'
    ]
  },

  'Access & Asset Revocation Timeliness': {
    workforceRequired: [
      { role: 'SAP BTP Event Mesh / Cloud Integration Architect', count: 1, hours: '40 Person-Hours', focus: 'Real-time termination webhook to Active Directory & Okta IAM' },
      { role: 'Enterprise IAM & IT Security Engineer', count: 1, hours: '30 Person-Hours', focus: 'Immediate single sign-on (SSO) session termination scripts' },
      { role: 'IT Audit & Compliance Officer', count: 1, hours: '15 Person-Hours', focus: 'SOC-2 / ISO-27001 audit logging verification' }
    ],
    totalManpower: '3 Specialists (85 Person-Hours)',
    timeline: '2 Weeks (Sprint Cycle 1)',
    totalEffortHours: 85,
    governanceLead: 'Chief Information Security Officer (CISO) & IT Ops',
    expectedOutcome: 'Cut revocation time from 4.2 hours to ≤1.0 hour, eliminating corporate security vulnerabilities and ensuring 100% SOC-2 compliance.',
    milestones: [
      { phase: 'Week 1', title: 'SAP BTP Event Mesh Webhook Architecture', deliverable: 'Real-Time Termination Event Bridge Spec' },
      { phase: 'Week 2', title: 'AD/Okta Immediate De-Provisioning & Audit Logger', deliverable: 'Automated Revocation Pipeline & SOC-2 Log' }
    ],
    deliverables: [
      'Event-Driven Access De-Provisioning Architecture Spec',
      'Configured SAP BTP Webhook to Okta/Active Directory',
      'Real-Time Security Audit Timestamp Verification Dashboard',
      'SOC-2 / ISO-27001 Compliance Certification Report'
    ]
  },

  'Offboarding Cycle Time': {
    workforceRequired: [
      { role: 'SAP SF Offboarding Consultant', count: 1, hours: '35 Person-Hours', focus: 'Self-service resignation workflows and parallel departmental clearance' },
      { role: 'HR Operations & Facilities Coordinator', count: 1, hours: '25 Person-Hours', focus: 'Clearance checklist SLA and manager escalation nudges' }
    ],
    totalManpower: '2 Specialists (60 Person-Hours)',
    timeline: '2 Weeks',
    totalEffortHours: 60,
    governanceLead: 'Head of HR Operations',
    expectedOutcome: 'Compress offboarding turnaround from 9.4 days to ≤5.0 days, expediting clearances and account security.',
    milestones: [
      { phase: 'Week 1', title: 'Self-Service Resignation & Routing Spec', deliverable: 'ESS Resignation Workflow Template' },
      { phase: 'Week 2', title: 'Parallel Task Assignment & Manager Escalations', deliverable: 'Parallel Clearance Rules & Daily Escalation Nudges' }
    ],
    deliverables: [
      'Employee Self-Service Resignation Process Guide',
      'Cross-Departmental Clearance Matrix (HR/IT/Facilities)',
      'Manager Departure Escalation Workflow'
    ]
  },

  'Knowledge Transfer Completion Rate': {
    workforceRequired: [
      { role: 'SAP SF Knowledge & Offboarding Specialist', count: 1, hours: '30 Person-Hours', focus: 'Standardized digital handover checklist and repository sign-off' },
      { role: 'Departmental Operations Lead', count: 1, hours: '20 Person-Hours', focus: 'Transition calendar milestones and manager verification' }
    ],
    totalManpower: '2 Specialists (50 Person-Hours)',
    timeline: '2 Weeks',
    totalEffortHours: 50,
    governanceLead: 'Director of HR Operations & Knowledge Management',
    expectedOutcome: 'Improve handover completion from 82.0% to ≥90.0%, safeguarding business continuity and project handovers.',
    milestones: [
      { phase: 'Week 1', title: 'Digital Knowledge Handover Checklist Design', deliverable: 'Standardized Handover Template in SF' },
      { phase: 'Week 2', title: 'Mandatory Sign-off Gate in Offboarding', deliverable: 'Repository & Transition Verification Gate' }
    ],
    deliverables: [
      'Digital Knowledge Transfer Checklist Specification',
      'Manager Transition Verification Sign-off Gate',
      'Knowledge Retention Governance Policy'
    ]
  }
};

// Fallback generator for custom or unlisted metrics
export function getBrdPlan(metric) {
  if (!metric) return null;
  const name = metric.metric || metric.name || '';
  
  if (METRIC_BRD_PLANS[name]) {
    return {
      ...METRIC_BRD_PLANS[name],
      actionSteps: metric.detailedAnalysis?.howToOvercome || []
    };
  }

  // Dynamic contextual fallback based on category & status
  const isCritical = metric.status === 'Critical';
  const consultantHours = isCritical ? '60 Person-Hours' : '40 Person-Hours';
  const opsHours = isCritical ? '30 Person-Hours' : '20 Person-Hours';
  const qaHours = isCritical ? '20 Person-Hours' : '15 Person-Hours';
  const totalHours = isCritical ? 110 : 75;
  const sprintWeeks = isCritical ? '3 Weeks (Sprint 1–2)' : '2 Weeks (Sprint 1)';

  return {
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
}
