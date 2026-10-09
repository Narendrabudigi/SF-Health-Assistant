"""
Master dataset for SAP SuccessFactors Enterprise Health Monitoring.
Synchronized 1:1 with frontend SF_MODULES schema.
All metric values default to 'Not yet fetched' and are overridden dynamically
by live telemetry and diagnostic reports fetched from Supabase.
"""

NOT_YET_FETCHED = "Not yet fetched"
DATA_NOT_YET_FETCHED = "Data not yet fetched"

def default_analysis():
    return {
        "whyItHappens": DATA_NOT_YET_FETCHED,
        "whereItHappens": DATA_NOT_YET_FETCHED,
        "howToOvercome": [],
        "trendAnalysis": {
            "summary": DATA_NOT_YET_FETCHED,
            "points": []
        },
        "missingConfigurations": [],
        "howItEffects": DATA_NOT_YET_FETCHED
    }

def default_overview():
    return {
        "rootCause": DATA_NOT_YET_FETCHED,
        "affectedArea": DATA_NOT_YET_FETCHED,
        "suggestions": []
    }

DEFAULT_MODULES = [
    {
        "id": "ec",
        "name": "Employee Central",
        "status": NOT_YET_FETCHED,
        "iconType": "users",
        "iconColor": "#0284c7",
        "iconBg": "#0284c7",
        "description": DATA_NOT_YET_FETCHED,
        "aiReport": {
            "summary": f"{DATA_NOT_YET_FETCHED}."
        },
        "benchmarks": [
            {
                "code": "ec_data_accuracy",
                "metric": "Employee Data Accuracy Rate",
                "category": "Core Data Quality",
                "company": NOT_YET_FETCHED,
                "standard": NOT_YET_FETCHED,
                "status": NOT_YET_FETCHED,
                "variance": NOT_YET_FETCHED,
                "moduleOverview": default_overview(),
                "detailedAnalysis": default_analysis()
            },
            {
                "code": "ec_early_attrition",
                "metric": "New Hire Early Attrition Rate (90-day)",
                "category": "Talent Retention",
                "company": NOT_YET_FETCHED,
                "standard": NOT_YET_FETCHED,
                "status": NOT_YET_FETCHED,
                "variance": NOT_YET_FETCHED,
                "moduleOverview": default_overview(),
                "detailedAnalysis": default_analysis()
            },
            {
                "code": "ec_workflow_latency",
                "metric": "Workflow Approval Cycle Time",
                "category": "Approval Governance",
                "company": NOT_YET_FETCHED,
                "standard": NOT_YET_FETCHED,
                "status": NOT_YET_FETCHED,
                "variance": NOT_YET_FETCHED,
                "moduleOverview": default_overview(),
                "detailedAnalysis": default_analysis()
            },
            {
                "code": "ec_position_accuracy",
                "metric": "Position Management Accuracy",
                "category": "Org Data Health",
                "company": NOT_YET_FETCHED,
                "standard": NOT_YET_FETCHED,
                "status": NOT_YET_FETCHED,
                "variance": NOT_YET_FETCHED,
                "moduleOverview": default_overview(),
                "detailedAnalysis": default_analysis()
            },
            {
                "code": "ec_data_change_time",
                "metric": "Avg. Time to Process Data Change Requests",
                "category": "HR Operations SLA",
                "company": NOT_YET_FETCHED,
                "standard": NOT_YET_FETCHED,
                "status": NOT_YET_FETCHED,
                "variance": NOT_YET_FETCHED,
                "moduleOverview": default_overview(),
                "detailedAnalysis": default_analysis()
            },
            {
                "code": "ec_sync_error_rate",
                "metric": "Data Sync Error Rate to Downstream Systems",
                "category": "Integration Health",
                "company": NOT_YET_FETCHED,
                "standard": NOT_YET_FETCHED,
                "status": NOT_YET_FETCHED,
                "variance": NOT_YET_FETCHED,
                "moduleOverview": default_overview(),
                "detailedAnalysis": default_analysis()
            },
            {
                "code": "ec_retro_changes",
                "metric": "Retroactive Data Changes Frequency",
                "category": "Master Data Integrity",
                "company": NOT_YET_FETCHED,
                "standard": NOT_YET_FETCHED,
                "status": NOT_YET_FETCHED,
                "variance": NOT_YET_FETCHED,
                "moduleOverview": default_overview(),
                "detailedAnalysis": default_analysis()
            },
            {
                "code": "ec_regrettable_attrition",
                "metric": "Regrettable Attrition Rate",
                "category": "Workforce Stability",
                "company": NOT_YET_FETCHED,
                "standard": NOT_YET_FETCHED,
                "status": NOT_YET_FETCHED,
                "variance": NOT_YET_FETCHED,
                "moduleOverview": default_overview(),
                "detailedAnalysis": default_analysis()
            }
        ]
    },
    {
        "id": "rcm",
        "name": "Recruitment",
        "status": NOT_YET_FETCHED,
        "iconType": "briefcase",
        "iconColor": "#7c3aed",
        "iconBg": "#7c3aed",
        "description": DATA_NOT_YET_FETCHED,
        "aiReport": {
            "summary": f"{DATA_NOT_YET_FETCHED}."
        },
        "benchmarks": [
            {
                "code": "rcm_time_to_hire",
                "metric": "Time to hire",
                "category": "Cycle Turnaround",
                "company": NOT_YET_FETCHED,
                "standard": NOT_YET_FETCHED,
                "status": NOT_YET_FETCHED,
                "variance": NOT_YET_FETCHED,
                "moduleOverview": default_overview(),
                "detailedAnalysis": default_analysis()
            },
            {
                "code": "rcm_applicant_conversion",
                "metric": "Applicant-to-Interview Conversion Rate",
                "category": "Screening Efficiency",
                "company": NOT_YET_FETCHED,
                "standard": NOT_YET_FETCHED,
                "status": NOT_YET_FETCHED,
                "variance": NOT_YET_FETCHED,
                "moduleOverview": default_overview(),
                "detailedAnalysis": default_analysis()
            },
            {
                "code": "rcm_offer_acceptance",
                "metric": "Offer acceptance rate",
                "category": "Offer Conversion",
                "company": NOT_YET_FETCHED,
                "standard": NOT_YET_FETCHED,
                "status": NOT_YET_FETCHED,
                "variance": NOT_YET_FETCHED,
                "moduleOverview": default_overview(),
                "detailedAnalysis": default_analysis()
            },
            {
                "code": "rcm_requisition_aging",
                "metric": "Requisition Aging",
                "category": "Pipeline Health",
                "company": NOT_YET_FETCHED,
                "standard": NOT_YET_FETCHED,
                "status": NOT_YET_FETCHED,
                "variance": NOT_YET_FETCHED,
                "moduleOverview": default_overview(),
                "detailedAnalysis": default_analysis()
            },
            {
                "code": "rcm_source_effectiveness",
                "metric": "Source of Hire Effectiveness",
                "category": "Channel Performance",
                "company": NOT_YET_FETCHED,
                "standard": NOT_YET_FETCHED,
                "status": NOT_YET_FETCHED,
                "variance": NOT_YET_FETCHED,
                "moduleOverview": default_overview(),
                "detailedAnalysis": default_analysis()
            }
        ]
    },
    {
        "id": "onb",
        "name": "Onboarding",
        "status": NOT_YET_FETCHED,
        "iconType": "user-plus",
        "iconColor": "#059669",
        "iconBg": "#059669",
        "description": DATA_NOT_YET_FETCHED,
        "aiReport": {
            "summary": f"{DATA_NOT_YET_FETCHED}."
        },
        "benchmarks": [
            {
                "code": "onb_cycle_time",
                "metric": "Onboarding Cycle Time",
                "category": "Journey Velocity",
                "company": NOT_YET_FETCHED,
                "standard": NOT_YET_FETCHED,
                "status": NOT_YET_FETCHED,
                "variance": NOT_YET_FETCHED,
                "moduleOverview": default_overview(),
                "detailedAnalysis": default_analysis()
            },
            {
                "code": "onb_preday1_completion",
                "metric": "Pre-Day-1 Task Completion Rate",
                "category": "Pre-Hire Engagement",
                "company": NOT_YET_FETCHED,
                "standard": NOT_YET_FETCHED,
                "status": NOT_YET_FETCHED,
                "variance": NOT_YET_FETCHED,
                "moduleOverview": default_overview(),
                "detailedAnalysis": default_analysis()
            },
            {
                "code": "onb_milestones",
                "metric": "Day 30/60/90 Milestone Completion Rate",
                "category": "Ramp & Assimilation",
                "company": NOT_YET_FETCHED,
                "standard": NOT_YET_FETCHED,
                "status": NOT_YET_FETCHED,
                "variance": NOT_YET_FETCHED,
                "moduleOverview": default_overview(),
                "detailedAnalysis": default_analysis()
            },
            {
                "code": "onb_compliance",
                "metric": "Compliance Documentation Completion Rate",
                "category": "Regulatory Compliance",
                "company": NOT_YET_FETCHED,
                "standard": NOT_YET_FETCHED,
                "status": NOT_YET_FETCHED,
                "variance": NOT_YET_FETCHED,
                "moduleOverview": default_overview(),
                "detailedAnalysis": default_analysis()
            }
        ]
    },
    {
        "id": "ofb",
        "name": "Offboarding",
        "status": NOT_YET_FETCHED,
        "iconType": "user-minus",
        "iconColor": "#ea580c",
        "iconBg": "#ea580c",
        "description": DATA_NOT_YET_FETCHED,
        "aiReport": {
            "summary": f"{DATA_NOT_YET_FETCHED}."
        },
        "benchmarks": [
            {
                "code": "ofb_revocation",
                "metric": "Access & Asset Revocation Timeliness",
                "category": "Security & IAM SLA",
                "company": NOT_YET_FETCHED,
                "standard": NOT_YET_FETCHED,
                "status": NOT_YET_FETCHED,
                "variance": NOT_YET_FETCHED,
                "moduleOverview": default_overview(),
                "detailedAnalysis": default_analysis()
            },
            {
                "code": "ofb_cycle_time",
                "metric": "Offboarding Cycle Time",
                "category": "Separation Velocity",
                "company": NOT_YET_FETCHED,
                "standard": NOT_YET_FETCHED,
                "status": NOT_YET_FETCHED,
                "variance": NOT_YET_FETCHED,
                "moduleOverview": default_overview(),
                "detailedAnalysis": default_analysis()
            },
            {
                "code": "ofb_knowledge_transfer",
                "metric": "Knowledge Transfer Completion Rate",
                "category": "Operational Handover",
                "company": NOT_YET_FETCHED,
                "standard": NOT_YET_FETCHED,
                "status": NOT_YET_FETCHED,
                "variance": NOT_YET_FETCHED,
                "moduleOverview": default_overview(),
                "detailedAnalysis": default_analysis()
            },
            {
                "code": "ofb_final_settlement",
                "metric": "Full & Final Settlement Timeliness",
                "category": "Settlement & Payroll SLA",
                "company": NOT_YET_FETCHED,
                "standard": NOT_YET_FETCHED,
                "status": NOT_YET_FETCHED,
                "variance": NOT_YET_FETCHED,
                "moduleOverview": default_overview(),
                "detailedAnalysis": default_analysis()
            }
        ]
    }
]

DEFAULT_ML_INSIGHTS = []
