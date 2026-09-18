/**
 * SAP SuccessFactors Enterprise Health Monitoring Benchmark Data
 * Enriched with Deep-Dive Metric Diagnostics for Critical & At Risk Metrics
 * Modules: Employee Central (EC), Recruitment (RCM), Onboarding (ONB2), Offboarding (OFB2)
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
      summary: 'Employee Central exhibits significant workflow approval delays (6.8 days vs 2.5 standard) and retroactive changes (18.5%). Immediate governance over hierarchical approvals and Picklist data validations is required to protect downstream payroll operations.'
    },
    benchmarks: [
      {
        metric: 'Employee Data Accuracy Rate',
        category: 'Core Data Quality',
        company: '91.4%',
        standard: '≥ 98.0%',
        status: 'Critical',
        variance: '-6.6% (-6.7%)',
        detailedAnalysis: {
          whereItHappens: 'Custom MDF objects, biographical data portlets, and national ID fields during mass CSV data imports.',
          whyItHappens: 'High reliance on unstructured free-text fields in custom MDF objects, absence of real-time validation on dependent records (Emergency Contacts, National ID), and incomplete automated checks during mass CSV uploads.',
          trendAnalysis: {
            summary: 'Degrading trajectory over the last 4 quarters due to organizational restructuring and decentralized data entry.',
            points: [
              { period: 'Q1', value: '94.8%' },
              { period: 'Q2', value: '93.5%' },
              { period: 'Q3', value: '92.1%' },
              { period: 'Q4 (Current)', value: '91.4%' }
            ]
          },
          howItEffects: 'Generates downstream payroll exceptions, causes healthcare enrollment data rejections with benefit providers, and creates audit non-compliance during annual workforce regulatory filings.',
          howToOvercome: [
            'Configure strict Picklist validation rules on all personal and biographical data entities.',
            'Deploy SAP SuccessFactors Business Rules to mandate attachment verification for critical personal changes.',
            'Implement weekly automated Data Quality Scans using Integration Center error reports.'
          ]
        }
      },
      {
        metric: 'New Hire Early Attrition Rate (90-day)',
        category: 'Talent Retention',
        company: '14.2%',
        standard: '≤ 8.0%',
        status: 'Critical',
        variance: '+6.2% (+77.5%)',
        detailedAnalysis: {
          whereItHappens: 'Technical and remote operational business units during the first 90 days following onboarding handover.',
          whyItHappens: 'Role ambiguity created by misaligned Job Requisition competencies vs. actual Position descriptions, coupled with fragmented manager check-ins during the critical first 90 days.',
          trendAnalysis: {
            summary: 'Sharp increase from Q2 to Q4, particularly within technical and remote operational teams.',
            points: [
              { period: 'Q1', value: '8.9%' },
              { period: 'Q2', value: '10.4%' },
              { period: 'Q3', value: '12.8%' },
              { period: 'Q4 (Current)', value: '14.2%' }
            ]
          },
          howItEffects: 'Inflates recruitment replacement costs by ~$1.8M annually, disrupts ongoing product delivery sprints, and lowers department-wide team morale.',
          howToOvercome: [
            'Standardize Job Profile Builder (JPB) competencies directly mapped to employee Position objects.',
            'Activate automated 30/60/90-day pulse check surveys with manager escalation triggers.',
            'Establish structured peer-buddy assignments tracked via Continuous Performance Management (CPM).'
          ]
        }
      },
      {
        metric: 'Workflow Approval Cycle Time',
        category: 'Approval Governance',
        company: '6.8 Days',
        standard: '≤ 2.5 Days',
        status: 'Critical',
        variance: '+4.3 Days (+172%)',
        detailedAnalysis: {
          whereItHappens: 'Level-3 executive approval hierarchies and non-delegated manager leave queues in Employee Central workflows.',
          whyItHappens: 'Multi-tier hierarchical approval chains requiring Level 3 executive sign-off for minor job updates, combined with lack of dynamic auto-delegation when managers are on approved leave.',
          trendAnalysis: {
            summary: 'Persistently above standard across all quarters with significant spikes during year-end compensation cycles.',
            points: [
              { period: 'Q1', value: '5.9 Days' },
              { period: 'Q2', value: '6.2 Days' },
              { period: 'Q3', value: '6.5 Days' },
              { period: 'Q4 (Current)', value: '6.8 Days' }
            ]
          },
          howItEffects: 'Delays critical employee transfers, creates compensation adjustment backlogs, and generates high ticket volumes to the Tier-1 HR Shared Services desk.',
          howToOvercome: [
            'Configure SF Intelligent Services to auto-escalate stagnant workflow requests after 48 hours.',
            'Implement dynamic rule-based routing: skip VP approval for lateral non-compensation updates.',
            'Enable mobile one-click workflow approvals via SAP Mobile Cards and MS Teams integration.'
          ]
        }
      },
      {
        metric: 'Position Management Accuracy',
        category: 'Org Data Health',
        company: '88.8%',
        standard: '≥ 95.0%',
        status: 'At Risk',
        variance: '-6.2% (-6.5%)',
        detailedAnalysis: {
          whereItHappens: 'Inactive position hierarchies and orphan position objects during MDF position-to-job sync batch runs.',
          whyItHappens: 'Orphaned and inactive positions remain unarchived following reorganization, and position-to-job information sync jobs fail due to concurrent manual updates.',
          trendAnalysis: {
            summary: 'Stabilized in Q3 but continues to remain below the 95% enterprise governance standard.',
            points: [
              { period: 'Q1', value: '87.2%' },
              { period: 'Q2', value: '88.0%' },
              { period: 'Q3', value: '88.9%' },
              { period: 'Q4 (Current)', value: '88.8%' }
            ]
          },
          howItEffects: 'Distorts workforce planning headcount reports, creates budget over-allocation in vacant positions, and complicates automated recruitment requisition creation.',
          howToOvercome: [
            'Schedule automated nightly Position Management reconciliation jobs via MDF batch processing.',
            'Enforce strict Position Hierarchy maintenance rules requiring HRBP sign-off before unfreezing requisitions.',
            'Automate archival of positions vacant for more than 180 consecutive days.'
          ]
        }
      },
      {
        metric: 'Avg. Time to Process Data Change Requests',
        category: 'HR Operations SLA',
        company: '4.5 Days',
        standard: '≤ 2.0 Days',
        status: 'At Risk',
        variance: '+2.5 Days (+125%)',
        detailedAnalysis: {
          whereItHappens: 'Employee Self-Service (ESS) bank detail and tax withholding modification request queues.',
          whyItHappens: 'Manual back-and-forth communication between employees and HR coordinators to clarify incomplete bank detail and tax withholding documentation.',
          trendAnalysis: {
            summary: 'Minor improvement over the past two quarters, but manual review steps keep cycle times elevated.',
            points: [
              { period: 'Q1', value: '5.1 Days' },
              { period: 'Q2', value: '4.8 Days' },
              { period: 'Q3', value: '4.6 Days' },
              { period: 'Q4 (Current)', value: '4.5 Days' }
            ]
          },
          howItEffects: 'Increases administrative handling overhead by 35% in HR Operations and triggers employee frustration regarding delayed payroll profile adjustments.',
          howToOvercome: [
            'Deploy Employee Self-Service (ESS) guided wizards with inline field format masks.',
            'Integrate automated document optical character recognition (OCR) for direct deposit verification.',
            'Set up SLA-based notification queues in SuccessFactors Service Center.'
          ]
        }
      },
      {
        metric: 'Data Sync Error Rate to Downstream Systems',
        category: 'Integration Health',
        company: '3.8%',
        standard: '≤ 1.0%',
        status: 'At Risk',
        variance: '+2.8% (+280%)',
        detailedAnalysis: {
          whereItHappens: 'Compound Employee API integration pipelines connecting Employee Central to downstream Active Directory and ERP.',
          whyItHappens: 'Schema mismatches between EC Compound Employee API and legacy downstream ERP/Active Directory middleware during high-volume batch runs.',
          trendAnalysis: {
            summary: 'Periodic spikes coinciding with bi-weekly integration middleware releases and custom picklist additions.',
            points: [
              { period: 'Q1', value: '2.9%' },
              { period: 'Q2', value: '3.4%' },
              { period: 'Q3', value: '4.1%' },
              { period: 'Q4 (Current)', value: '3.8%' }
            ]
          },
          howItEffects: 'Results in delayed badge access, missing user email provisioning, and synchronization errors in enterprise reporting data warehouses.',
          howToOvercome: [
            'Standardize on SAP Cloud Integration (CPI) with pre-packaged SuccessFactors integration packages.',
            'Implement automated schema validation and payload pre-flight checks before sync dispatch.',
            'Set up real-time alerting to IT Operations for any integration center queue failure.'
          ]
        }
      },
      {
        metric: 'Retroactive Data Changes Frequency',
        category: 'Master Data Integrity',
        company: '18.5%',
        standard: '≤ 5.0%',
        status: 'Critical',
        variance: '+13.5% (+270%)',
        detailedAnalysis: {
          whereItHappens: 'Line manager compensation adjustments, job reclassifications, and reporting line updates.',
          whyItHappens: 'Managers submitting promotions, department transfers, and supervisor updates with backdated effective dates rather than prospective scheduling.',
          trendAnalysis: {
            summary: 'Consistently high across all four quarters, indicating entrenched late-submission habits across line management.',
            points: [
              { period: 'Q1', value: '17.8%' },
              { period: 'Q2', value: '18.1%' },
              { period: 'Q3', value: '18.9%' },
              { period: 'Q4 (Current)', value: '18.5%' }
            ]
          },
          howItEffects: 'Triggers complex retro-payroll recalculations, generates tax withholding discrepancies, and burdens the payroll team with off-cycle adjustment runs.',
          howToOvercome: [
            'Enforce hard workflow validation blocking retro-changes older than 14 days without VP approval.',
            'Introduce automated proactive notifications for managers 30 days prior to contract milestone dates.',
            'Conduct quarterly manager training on prospective organizational change scheduling.'
          ]
        }
      },
      {
        metric: 'Regrettable Attrition Rate',
        category: 'Workforce Stability',
        company: '5.4%',
        standard: '≤ 6.0%',
        status: 'Healthy',
        variance: '-0.6% (On Target)'
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
      summary: 'Recruitment turnaround is critically bottlenecked with Time to Hire at 48 days (standard ≤ 30 days) and interview scorecard turnaround lag. Automating interview self-scheduling and establishing strict 24-hour scorecard SLAs are top priorities.'
    },
    benchmarks: [
      {
        metric: 'Time to hire',
        category: 'Cycle Turnaround',
        company: '48 Days',
        standard: '≤ 30 Days',
        status: 'Critical',
        variance: '+18 Days (+60%)',
        detailedAnalysis: {
          whereItHappens: 'Recruiter screening stages, hiring manager interview scorecard submission queues, and panel coordination workflows.',
          whyItHappens: 'Lengthy recruiter initial screening, delays of 5+ days in hiring managers returning interview scorecards, and multi-round scheduling friction across external panels.',
          trendAnalysis: {
            summary: 'Cycle turnaround lengthened steadily across the last 3 quarters due to increased interview rounds.',
            points: [
              { period: 'Q1', value: '38 Days' },
              { period: 'Q2', value: '42 Days' },
              { period: 'Q3', value: '45 Days' },
              { period: 'Q4 (Current)', value: '48 Days' }
            ]
          },
          howItEffects: 'Causes high top-tier candidate drop-out to competing offers, delays strategic project kick-offs, and increases agency spend by 28%.',
          howToOvercome: [
            'Activate automated self-scheduling for candidates via SAP SuccessFactors Interview Central.',
            'Establish a strict 24-hour SLA for interview scorecard submission with auto-reminders.',
            'Cap standard requisition interview processes to a maximum of 3 structured rounds.'
          ]
        }
      },
      {
        metric: 'Applicant-to-Interview Conversion Rate',
        category: 'Screening Efficiency',
        company: '12.4%',
        standard: '≥ 20.0%',
        status: 'Critical',
        variance: '-7.6% (-38.0%)',
        detailedAnalysis: {
          whereItHappens: 'Top-of-funnel job board applicant inflow, initial resume triage, and automated candidate knock-out screening.',
          whyItHappens: 'Generic job descriptions attracting high volumes of unqualified applicants, lack of automated knock-out pre-screening questions, and slow resume triage.',
          trendAnalysis: {
            summary: 'Conversion rate dropped steadily as job board distribution increased without qualification filtering.',
            points: [
              { period: 'Q1', value: '16.5%' },
              { period: 'Q2', value: '15.0%' },
              { period: 'Q3', value: '13.8%' },
              { period: 'Q4 (Current)', value: '12.4%' }
            ]
          },
          howItEffects: 'Floods recruiters with thousands of manual resume reviews, leading to candidate fatigue and delayed contact with truly qualified applicants.',
          howToOvercome: [
            'Implement mandatory role-specific pre-screening questions with automated qualification scoring.',
            'Leverage SAP SuccessFactors AI candidate matching to surface top-fit applicants instantly.',
            'Refine job postings with precise competency requirements developed via Job Profile Builder.'
          ]
        }
      },
      {
        metric: 'Offer acceptance rate',
        category: 'Offer Conversion',
        company: '81.0%',
        standard: '≥ 88.0%',
        status: 'At Risk',
        variance: '-7.0% (-8.0%)',
        detailedAnalysis: {
          whereItHappens: 'Final compensation benchmarking and formal offer letter presentation stage for specialized engineering and mid-senior roles.',
          whyItHappens: 'Extended turnaround between final interview and offer generation (avg 6 days), coupled with non-competitive base salary benchmarking for niche specialized skills.',
          trendAnalysis: {
            summary: 'Dipped below the 88% industry benchmark in Q2 and has remained suppressed.',
            points: [
              { period: 'Q1', value: '86.4%' },
              { period: 'Q2', value: '84.0%' },
              { period: 'Q3', value: '82.5%' },
              { period: 'Q4 (Current)', value: '81.0%' }
            ]
          },
          howItEffects: 'Forces recruiters to restart candidate searches from scratch, doubling cost-per-hire and leaving revenue-generating positions vacant.',
          howToOvercome: [
            'Streamline offer approval workflows to deliver formalized offer letters within 48 hours of verbal agreement.',
            'Integrate live compensation market benchmarks into RCM requisition compensation fields.',
            'Deploy dynamic total rewards preview statements within candidate offer portals.'
          ]
        }
      },
      {
        metric: 'Requisition Aging',
        category: 'Pipeline Health',
        company: '64 Days',
        standard: '≤ 45 Days',
        status: 'At Risk',
        variance: '+19 Days (+42.2%)',
        detailedAnalysis: {
          whereItHappens: 'Specialized technical, niche engineering, and remote operational job requisitions open in talent acquisition pipelines.',
          whyItHappens: 'Niche specialized job requisitions remaining open without active talent pipeline sourcing, and hiring managers repeatedly requesting candidate profile scope changes.',
          trendAnalysis: {
            summary: 'Average aging increased past 60 days in Q3 and remains in the at-risk zone.',
            points: [
              { period: 'Q1', value: '52 Days' },
              { period: 'Q2', value: '57 Days' },
              { period: 'Q3', value: '62 Days' },
              { period: 'Q4 (Current)', value: '64 Days' }
            ]
          },
          howItEffects: 'Strains existing team members covering vacant workloads, leading to burnout and delayed department deliverables.',
          howToOvercome: [
            'Institute bi-weekly requisition audit reviews with talent acquisition leadership for all roles >45 days.',
            'Deploy targeted proactive talent pooling and CRM nurture campaigns for high-demand skill sets.',
            'Require formal requisition re-authorization if job criteria are modified after 30 days.'
          ]
        }
      },
      {
        metric: 'Source of Hire Effectiveness',
        category: 'Channel Performance',
        company: '94.2%',
        standard: '≥ 90.0%',
        status: 'Healthy',
        variance: '+4.2% (On Target)'
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
      summary: 'Onboarding cycle time is 14.5 days against the 7-day standard, driven primarily by low Pre-Day-1 task completion (68%). Enabling mobile pre-boarding and parallel IT provisioning will accelerate ramp-up velocity.'
    },
    benchmarks: [
      {
        metric: 'Onboarding Cycle Time',
        category: 'Journey Velocity',
        company: '14.5 Days',
        standard: '≤ 7.0 Days',
        status: 'Critical',
        variance: '+7.5 Days (+107%)',
        detailedAnalysis: {
          whereItHappens: 'Cross-departmental handoffs between HR Operations, IT hardware provisioning, and Facilities readiness prior to Day 1.',
          whyItHappens: 'Manual coordination between HR, IT, and Facilities for new hire readiness, and document collection workflows remaining pending until hire start date.',
          trendAnalysis: {
            summary: 'Cycle time extended significantly over the past 3 quarters due to decentralized team onboarding.',
            points: [
              { period: 'Q1', value: '9.8 Days' },
              { period: 'Q2', value: '11.5 Days' },
              { period: 'Q3', value: '13.2 Days' },
              { period: 'Q4 (Current)', value: '14.5 Days' }
            ]
          },
          howItEffects: 'Delayed employee ramp-up time, idle work hours during week one, and negative initial employer brand perception for new hires.',
          howToOvercome: [
            'Automate event-triggered onboarding initiation in SuccessFactors Onboarding 2.0 upon offer acceptance.',
            'Deploy unified new hire task checklists accessible through SAP Work Zone.',
            'Integrate automated reminder nudges for managers and buddies 7 days before hire arrival.'
          ]
        }
      },
      {
        metric: 'Pre-Day-1 Task Completion Rate',
        category: 'Pre-Hire Engagement',
        company: '68.0%',
        standard: '≥ 90.0%',
        status: 'Critical',
        variance: '-22.0% (-24.4%)',
        detailedAnalysis: {
          whereItHappens: 'Pre-hire onboarding portal document collection, compliance form sign-offs, and initial corporate credential verification.',
          whyItHappens: 'New hires experience mobile login friction with initial credential setup, and pre-day-1 tasks lack clear deadline urgency notifications.',
          trendAnalysis: {
            summary: 'Persistently low compliance across all 4 quarters, with remote hires showing the lowest completion rate.',
            points: [
              { period: 'Q1', value: '71.2%' },
              { period: 'Q2', value: '69.5%' },
              { period: 'Q3', value: '68.4%' },
              { period: 'Q4 (Current)', value: '68.0%' }
            ]
          },
          howItEffects: 'Day-1 is consumed with routine administrative paperwork rather than meaningful team orientation and role enablement.',
          howToOvercome: [
            'Enable passwordless email magic-link authentication for pre-day-1 candidate portal access.',
            'Condense pre-day-1 paperwork to essential compliance forms using responsive mobile web forms.',
            'Configure SMS notifications alerting candidates 5 days and 2 days prior to start date.'
          ]
        }
      },
      {
        metric: 'Day 30/60/90 Milestone Completion Rate',
        category: 'Ramp & Assimilation',
        company: '76.4%',
        standard: '≥ 88.0%',
        status: 'At Risk',
        variance: '-11.6% (-13.2%)',
        detailedAnalysis: {
          whereItHappens: 'Post-hire manager check-in workflows, assimilation touchpoints, and 60/90-day structured review milestones.',
          whyItHappens: 'Managers deprioritize formal check-ins after the initial week, and milestone activities are not tied to performance management goals.',
          trendAnalysis: {
            summary: 'Declining completion rate specifically at the Day-60 and Day-90 touchpoint intervals.',
            points: [
              { period: 'Q1', value: '82.0%' },
              { period: 'Q2', value: '80.1%' },
              { period: 'Q3', value: '78.5%' },
              { period: 'Q4 (Current)', value: '76.4%' }
            ]
          },
          howItEffects: 'Early warning signs of role mismatch or training deficits go undetected, directly driving 90-day early attrition.',
          howToOvercome: [
            'Embed 30/60/90-day structured review forms directly into SuccessFactors Continuous Performance Management.',
            'Send calendar integration invites automatically to managers upon hire start date.',
            'Publish department-level milestone compliance dashboards to senior leadership.'
          ]
        }
      },
      {
        metric: 'Compliance Documentation Completion Rate',
        category: 'Regulatory Compliance',
        company: '98.5%',
        standard: '≥ 95.0%',
        status: 'Healthy',
        variance: '+3.5% (On Target)'
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
      summary: 'Offboarding processes show critical security exposure with Access & Asset Revocation taking 4.2 hours (standard ≤ 1.0 hour). Automated webhook de-provisioning via SAP BTP Event Mesh is required immediately to ensure SOC-2 compliance.'
    },
    benchmarks: [
      {
        metric: 'Access & Asset Revocation Timeliness',
        category: 'Security & IAM SLA',
        company: '4.2 Hours',
        standard: '≤ 1.0 Hour',
        status: 'Critical',
        variance: '+3.2 Hours (+320%)',
        detailedAnalysis: {
          whereItHappens: 'SuccessFactors termination event bridge to Active Directory, Okta IAM, and enterprise cloud SSO systems.',
          whyItHappens: 'Disconnection between SuccessFactors termination status events and Active Directory / IAM de-provisioning connectors, relying on manual IT ticket handling.',
          trendAnalysis: {
            summary: 'Average revocation time has consistently breached the 1-hour critical audit standard across all 4 quarters.',
            points: [
              { period: 'Q1', value: '3.6 Hours' },
              { period: 'Q2', value: '3.9 Hours' },
              { period: 'Q3', value: '4.5 Hours' },
              { period: 'Q4 (Current)', value: '4.2 Hours' }
            ]
          },
          howItEffects: 'Major corporate data security vulnerability, potential unauthorized data export by departing personnel, and recurring SOC-2/ISO-27001 audit findings.',
          howToOvercome: [
            'Configure real-time automated webhook triggers via SAP BTP Event Mesh to disable AD/Okta credentials immediately at separation timestamp.',
            'Implement automated single sign-on (SSO) session termination for cloud apps upon termination event.',
            'Establish an automated security dashboard logging timestamp difference between termination and credential revocation.'
          ]
        }
      },
      {
        metric: 'Offboarding Cycle Time',
        category: 'Separation Velocity',
        company: '9.4 Days',
        standard: '≤ 5.0 Days',
        status: 'At Risk',
        variance: '+4.4 Days (+88.0%)',
        detailedAnalysis: {
          whereItHappens: 'Supervisor separation notice routing and cross-departmental clearance workflows across HR Operations, Facilities, and Payroll.',
          whyItHappens: 'Delayed supervisor submission of separation notices and fragmented communication across HR, Facilities, and Payroll for clearance sign-off.',
          trendAnalysis: {
            summary: 'Cycle turnaround lengthened steadily across the year, predominantly for voluntary resignations.',
            points: [
              { period: 'Q1', value: '7.8 Days' },
              { period: 'Q2', value: '8.4 Days' },
              { period: 'Q3', value: '9.0 Days' },
              { period: 'Q4 (Current)', value: '9.4 Days' }
            ]
          },
          howItEffects: 'Extends administrative clearance timelines, delays timely release of experience letters, and leaves system accounts active longer than required.',
          howToOvercome: [
            'Implement an employee self-service resignation workflow in Employee Central with auto-approval routing.',
            'Deploy parallel offboarding task assignment across HR, IT, and Facilities rather than sequential chains.',
            'Set automated daily escalation alerts to managers for pending departure checklist items.'
          ]
        }
      },
      {
        metric: 'Knowledge Transfer Completion Rate',
        category: 'Operational Handover',
        company: '82.0%',
        standard: '≥ 90.0%',
        status: 'At Risk',
        variance: '-8.0% (-8.9%)',
        detailedAnalysis: {
          whereItHappens: 'Departmental handover repositories, codebase knowledge transfers, and manager sign-off workflows during employee notice periods.',
          whyItHappens: 'Departing employees lack structured handover documentation templates, and manager sign-offs occur without verifying project repository transfers.',
          trendAnalysis: {
            summary: 'Slight improvement from Q1 but remains below the 90% threshold for critical engineering and product roles.',
            points: [
              { period: 'Q1', value: '78.5%' },
              { period: 'Q2', value: '80.0%' },
              { period: 'Q3', value: '81.4%' },
              { period: 'Q4 (Current)', value: '82.0%' }
            ]
          },
          howItEffects: 'Leads to lost institutional knowledge, broken project context for replacement hires, and delayed delivery on client accounts.',
          howToOvercome: [
            'Mandate a standardized digital Knowledge Handover Checklist in SuccessFactors Offboarding.',
            'Require replacement or manager sign-off on repository access before final separation sign-off.',
            'Incorporate structured handover milestones into the final 2-week transition calendar.'
          ]
        }
      },
      {
        metric: 'Full & Final Settlement Timeliness',
        category: 'Settlement & Payroll SLA',
        company: '97.8%',
        standard: '≥ 95.0%',
        status: 'Healthy',
        variance: '+2.8% (On Target)'
      }
    ]
  }
];
