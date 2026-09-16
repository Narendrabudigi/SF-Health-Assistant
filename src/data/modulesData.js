/**
 * Pixel-Perfect Mock Data Matching the User's Screenshot Design:
 * Order: Employee Central, Recruitment, Onboarding, Offboarding
 */

export const SF_MODULES = [
  {
    id: 'ec',
    name: 'Employee Central',
    status: 'At Risk', // 'At Risk' | 'Critical' | 'Healthy'
    iconType: 'users',
    iconColor: '#0284c7', // Blue
    iconBg: '#0284c7',
    description: 'Workflow approval delays and retroactive data changes are impacting downstream payroll accuracy and manager SLAs.',
    aiReport: {
      summary: 'Employee Central shows an average workflow cycle of 6.8 days (vs 2.5d industry standard) primarily caused by delayed intermediate manager approvals. In addition, 18.5% of job changes are submitted retroactively, creating downstream payroll corrections.',
      issues: [
        {
          title: 'Job Information Approvals',
          tag: 'Manager Transfer & Compensation Adjustments',
          status: 'Critical',
          description: 'Workflows stall at Level 2 Manager sign-off without auto-escalation.'
        },
        {
          title: 'Position Management',
          tag: 'Organizational Structure & Vacancies',
          status: 'At Risk',
          description: 'Inactive and orphaned positions remain unarchived post reorganization.'
        }
      ],
      whyItHappens: [
        'Lack of dynamic auto-delegation triggers when managers are on approved leave.',
        'Over-engineered 4-tier approval chains for lateral transfers within identical pay grades.',
        'Absence of automated notifications nudging HR business partners after 48h SLA breach.'
      ],
      howToImprove: [
        'Configure SF Intelligent Services to auto-escalate stagnant workflow requests after 48 hours.',
        'Implement dynamic rule-based routing: skip VP approval for non-compensation updates.',
        'Enforce strict MDF picklist validation rules to eliminate data reentry latency.'
      ]
    },
    benchmarks: [
      {
        metric: 'Workflow Approval Cycle Time',
        category: 'Approval Governance',
        company: '6.8 Days',
        standard: '≤ 2.5 Days',
        status: 'Critical',
        variance: '+4.3 Days (+172%)'
      },
      {
        metric: 'Self-Service (ESS/MSS) Adoption',
        category: 'Digital Adoption',
        company: '62.4%',
        standard: '≥ 85.0%',
        status: 'At Risk',
        variance: '-22.6% (-26.6%)'
      },
      {
        metric: 'Position Management Accuracy',
        category: 'Org Data Health',
        company: '11.2%',
        standard: '≤ 3.0%',
        status: 'At Risk',
        variance: '+8.2% (+273%)'
      },
      {
        metric: 'Retroactive Data Changes Frequency',
        category: 'Master Data Integrity',
        company: '18.5%',
        standard: '≤ 5.0%',
        status: 'Critical',
        variance: '+13.5% (+270%)'
      },
      {
        metric: 'Employee Profile & Address Completeness',
        category: 'Core Data Quality',
        company: '98.6%',
        standard: '≥ 95.0%',
        status: 'Healthy',
        variance: '+3.6% (On Target)'
      }
    ]
  },
  {
    id: 'rcm',
    name: 'Recruitment',
    status: 'Critical',
    iconType: 'briefcase',
    iconColor: '#7c3aed', // Purple
    iconBg: '#7c3aed',
    description: 'Requisition approval cycles and mobile candidate application drop-offs are exceeding industry averages.',
    aiReport: {
      summary: 'Recruitment turnaround exhibits an average cycle time of 48 days (vs 30d industry benchmark). High screening drop-off on mobile devices (24%) and slow interviewer scorecard turnarounds are the primary bottlenecks in candidate acquisition.',
      issues: [
        {
          title: 'Candidate Screening Drop-Off',
          tag: 'Career Site & Mobile Apply',
          status: 'Critical',
          description: 'Multi-step application forms without auto-fill cause 24% candidate abandonment.'
        },
        {
          title: 'Interview Scorecard Submissions',
          tag: 'Interviewer Turnaround SLA',
          status: 'At Risk',
          description: 'Hiring managers average 5.2 days to log scorecard ratings after panel interviews.'
        }
      ],
      whyItHappens: [
        'Career Site Builder (CSB) not optimized for rapid one-click LinkedIn/resume parsing.',
        'Interview evaluation reminders are sent via email rather than MS Teams or SF Mobile nudges.',
        'Redundant approval steps for standard pre-budgeted job requisitions.'
      ],
      howToImprove: [
        'Activate Quick-Apply mobile candidate experience reducing form fields by 60%.',
        'Configure automated MS Teams / Slack bot reminders 24h post-interview.',
        'Auto-approve requisitions mapped to approved Annual Operating Plan (AOP) headcount.'
      ]
    },
    benchmarks: [
      {
        metric: 'Average Time-to-Hire',
        category: 'Cycle Turnaround',
        company: '48 Days',
        standard: '≤ 30 Days',
        status: 'Critical',
        variance: '+18 Days (+60%)'
      },
      {
        metric: 'Mobile Application Completion Rate',
        category: 'Candidate Experience',
        company: '46.2%',
        standard: '≥ 75.0%',
        status: 'Critical',
        variance: '-28.8% (-38.4%)'
      },
      {
        metric: 'Offer Acceptance Rate',
        category: 'Offer Conversion',
        company: '81.0%',
        standard: '≥ 88.0%',
        status: 'At Risk',
        variance: '-7.0% (-8.0%)'
      },
      {
        metric: 'Requisition SLA Compliance',
        category: 'Hiring Operations',
        company: '74.5%',
        standard: '≥ 90.0%',
        status: 'At Risk',
        variance: '-15.5% (-17.2%)'
      },
      {
        metric: 'Career Portal Availability & Uptime',
        category: 'Portal Infrastructure',
        company: '99.8%',
        standard: '≥ 99.5%',
        status: 'Healthy',
        variance: '+0.3% (On Target)'
      }
    ]
  },
  {
    id: 'onb',
    name: 'Onboarding',
    status: 'At Risk',
    iconType: 'user-plus',
    iconColor: '#059669', // Emerald Green
    iconBg: '#059669',
    description: 'Day-1 IT asset readiness is behind target, causing productivity lag for new joiners in their first week.',
    aiReport: {
      summary: 'Onboarding data indicates Day-1 provisioning readiness is at 68% (vs 95% standard). API delays between SuccessFactors Onboarding 2.0 and IT Asset Provisioning systems result in an average of 3.4 days delay in new hire laptop delivery.',
      issues: [
        {
          title: 'IT Hardware Provisioning Trigger',
          tag: 'Asset Management API Sync',
          status: 'Critical',
          description: 'Asset orders are only triggered post-eSignature instead of candidate offer acceptance.'
        },
        {
          title: 'Day-1 Compliance Documentation',
          tag: 'I-9 & National ID Verification',
          status: 'At Risk',
          description: 'Document verification queues experience 48-hour backlog during peak intake cycles.'
        }
      ],
      whyItHappens: [
        'Batch Integration Center job runs once daily at midnight rather than event-driven real-time.',
        'Hiring managers lack automated checklist visibility prior to hire arrival.',
        'Address and tax withholding format mismatches reject silently in middleware.'
      ],
      howToImprove: [
        'Deploy SAP BTP Event Mesh to publish hiring events in real-time upon offer signature.',
        'Enable mobile push checklists for hiring managers 5 days prior to start date.',
        'Integrate real-time address validation in Onboarding 2.0 Custom Data Collection.'
      ]
    },
    benchmarks: [
      {
        metric: 'Day-1 Asset & Access Readiness',
        category: 'IT & Hardware Delivery',
        company: '68.0%',
        standard: '≥ 95.0%',
        status: 'Critical',
        variance: '-27.0% (-28.4%)'
      },
      {
        metric: 'Paperwork Completion on Day 1',
        category: 'Compliance Operations',
        company: '76.4%',
        standard: '≥ 92.0%',
        status: 'At Risk',
        variance: '-15.6% (-17.0%)'
      },
      {
        metric: 'Time to Full Productivity',
        category: 'New Hire Ramp Velocity',
        company: '58 Days',
        standard: '≤ 40 Days',
        status: 'At Risk',
        variance: '+18 Days (+45%)'
      },
      {
        metric: 'New Hire 90-Day Retention',
        category: 'Engagement Health',
        company: '88.5%',
        standard: '≥ 90.0%',
        status: 'At Risk',
        variance: '-1.5% (-1.7%)'
      },
      {
        metric: 'Digital Document E-Signature Turnaround',
        category: 'DocuSign / e-Sign SLA',
        company: '1.2 Days',
        standard: '≤ 2.0 Days',
        status: 'Healthy',
        variance: '-0.8 Days (Optimal)'
      }
    ]
  },
  {
    id: 'ofb',
    name: 'Offboarding',
    status: 'At Risk',
    iconType: 'user-minus',
    iconColor: '#ea580c', // Orange
    iconBg: '#ea580c',
    description: 'Company hardware recovery compliance is below target, and access revocation takes longer than standard.',
    aiReport: {
      summary: 'Offboarding workflows show credential revocation TAT averaging 4.2 hours (vs 1.0 hour target) and hardware recovery compliance at 78% (vs 92% benchmark), creating audit findings in enterprise device management.',
      issues: [
        {
          title: 'Hardware Asset Return TAT',
          tag: 'Logistics & Remote Return Kits',
          status: 'Critical',
          description: 'Prepaid return packaging is delayed by 3-5 days for remote employee separations.'
        },
        {
          title: 'Identity & Access De-provisioning',
          tag: 'Active Directory / IAM Sync',
          status: 'At Risk',
          description: 'Single Sign-On sessions remain valid for several hours post effective separation date.'
        }
      ],
      whyItHappens: [
        'Termination events in EC are frequently scheduled with delayed effective timestamps.',
        'Asset recovery tracking relies on manual spreadsheet follow-ups between HR and Facilities.',
        'Manager sign-off checklists are frequently bypassed or approved without verification.'
      ],
      howToImprove: [
        'Automate immediate SAP Cloud Identity credential suspension upon termination submission.',
        'Auto-generate courier return slips via automated API webhook upon offboarding initiation.',
        'Enforce mandatory serial number confirmation before final payroll clearance sign-off.'
      ]
    },
    benchmarks: [
      {
        metric: 'Hardware Recovery Compliance',
        category: 'Asset Reclamation',
        company: '78.0%',
        standard: '≥ 92.0%',
        status: 'Critical',
        variance: '-14.0% (-15.2%)'
      },
      {
        metric: 'Access Revocation Turnaround Time',
        category: 'Security & IAM SLA',
        company: '4.2 Hours',
        standard: '≤ 1.0 Hour',
        status: 'Critical',
        variance: '+3.2 Hours (+320%)'
      },
      {
        metric: 'Knowledge Transfer Sign-off Rate',
        category: 'Operational Continuity',
        company: '82.0%',
        standard: '≥ 90.0%',
        status: 'At Risk',
        variance: '-8.0% (-8.9%)'
      },
      {
        metric: 'Exit Survey Participation',
        category: 'HR Intelligence',
        company: '68.0%',
        standard: '≥ 75.0%',
        status: 'At Risk',
        variance: '-7.0% (-9.3%)'
      },
      {
        metric: 'Separation Document Archival Compliance',
        category: 'Audit & Records Retention',
        company: '99.4%',
        standard: '≥ 98.0%',
        status: 'Healthy',
        variance: '+1.4% (On Target)'
      }
    ]
  }
];
