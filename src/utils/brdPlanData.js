/**
 * BRD (Business Requirements Document) Plan of Action Formatter.
 * Strictly reflects data fetched from Supabase.
 * If data is not available, defaults strictly to "Not yet fetched" / empty arrays.
 * Zero static or mock placeholder data!
 */

export const METRIC_BRD_PLANS = {};

/**
 * Normalizes and formats a BRD plan object from Supabase telemetry.
 */
export function formatBrdPlan(rawPlan, metric = {}) {
  if (!rawPlan || typeof rawPlan !== 'object') {
    return {
      specialistManpower: [],
      workforceRequired: [],
      phasedActivities: [],
      executionWorkstreams: [],
      stageDrivers: [],
      segmentDrivers: [],
      assumptionsAndRisks: [],
      successCriteria: [],
      milestones: [],
      deliverables: [],
      timeline: 'Not yet fetched',
      totalEffortHours: 0,
      totalEffortsDisplay: 'Not yet fetched',
      timelineAndEffort: { timeline: 'Not yet fetched', totalEffort: 'Not yet fetched' },
      targetOutcome: 'Data not yet fetched',
      expectedOutcome: 'Data not yet fetched'
    };
  }

  // 1. Specialist Manpower & Workforce
  const rawRoles = Array.isArray(rawPlan.specialistManpower) && rawPlan.specialistManpower.length > 0
    ? rawPlan.specialistManpower
    : (Array.isArray(rawPlan.roles) && rawPlan.roles.length > 0
      ? rawPlan.roles
      : (Array.isArray(rawPlan.workforceRequired) ? rawPlan.workforceRequired : []));

  const specialistManpower = rawRoles.map(r => ({
    role: r.role || r.name || 'Specialist Consultant',
    headcount: r.headcount || r.count || 1,
    effort: (typeof r.hours === 'number' || typeof r.effort === 'number')
      ? `${r.hours || r.effort} Person-Hours`
      : (r.effort || (r.hours ? `${r.hours} Person-Hours` : 'Not yet fetched'))
  }));

  const workforceRequired = rawRoles.map(r => ({
    role: r.role || r.name || 'Specialist Consultant',
    count: r.headcount || r.count || 1,
    hours: (typeof r.hours === 'number' || typeof r.effort === 'number')
      ? `${r.hours || r.effort} Person-Hours`
      : (r.effort || (r.hours ? `${r.hours} Person-Hours` : 'Not yet fetched')),
    focus: r.focus || r.deliverable || ''
  }));

  // 2. Timeline & Effort
  let totalEffortHours = rawPlan.totalEffortHours || rawPlan.totalHours;
  if (!totalEffortHours && rawRoles.length > 0) {
    const calc = rawRoles.reduce((sum, r) => {
      const h = typeof r.hours === 'number' ? r.hours : parseInt(r.hours || r.effort || 0, 10);
      return sum + (isNaN(h) ? 0 : h);
    }, 0);
    if (calc > 0) totalEffortHours = calc;
  }

  const durationWeeks = rawPlan.durationWeeks || rawPlan.timelineWeeks;
  const timeline = rawPlan.timeline || (durationWeeks ? `${durationWeeks} Weeks` : 'Not yet fetched');
  const totalEffortsDisplay = rawPlan.totalEffortsDisplay || (totalEffortHours ? `${totalEffortHours} Total Hours` : 'Not yet fetched');

  const timelineAndEffort = {
    timeline,
    totalEffort: totalEffortsDisplay
  };

  // 3. Phased Activities
  const rawPhases = Array.isArray(rawPlan.phasedActivities) && rawPlan.phasedActivities.length > 0
    ? rawPlan.phasedActivities
    : (Array.isArray(rawPlan.phases) ? rawPlan.phases : []);

  const phasedActivities = rawPhases.map((p, idx) => ({
    phaseName: p.phaseName || p.title || p.phase || `Phase ${idx + 1}`,
    milestone: p.milestone || '',
    deliverable: p.deliverable || '',
    activities: (p.activities || []).map(a => ({
      activity: a.activity || a.title || '',
      owner: a.owner || a.role || 'Specialist',
      workstream: a.workstream || '-',
      effort: (typeof a.hours === 'number' || typeof a.effort === 'number')
        ? `${a.hours || a.effort} Hours`
        : (a.effort || (a.hours ? `${a.hours} Hours` : '-'))
    }))
  }));

  // 4. Execution Workstreams
  const rawWs = Array.isArray(rawPlan.executionWorkstreams) && rawPlan.executionWorkstreams.length > 0
    ? rawPlan.executionWorkstreams
    : (Array.isArray(rawPlan.workstreams) ? rawPlan.workstreams : []);

  const executionWorkstreams = rawWs.map((ws, idx) => ({
    id: ws.id || `W${idx + 1}`,
    remediationStep: ws.remediationStep || ws.step || ws.title || '',
    fixesDrivers: Array.isArray(ws.fixesDrivers)
      ? ws.fixesDrivers.join(', ')
      : (ws.fixesDrivers || ws.fixesFactors || '')
  }));

  // 5. Stage & Segment Drivers
  const stageDrivers = Array.isArray(rawPlan.stageDrivers) ? rawPlan.stageDrivers : [];
  const segmentDrivers = Array.isArray(rawPlan.segmentDrivers) ? rawPlan.segmentDrivers : [];

  // 6. Assumptions & Risks, Success Criteria
  const assumptionsAndRisks = Array.isArray(rawPlan.assumptionsAndRisks) ? rawPlan.assumptionsAndRisks : [];
  const successCriteria = Array.isArray(rawPlan.successCriteria) ? rawPlan.successCriteria : [];

  // 7. Target Outcome
  const targetOutcome = rawPlan.targetOutcome || rawPlan.expectedOutcome || 'Data not yet fetched';

  return {
    ...rawPlan,
    specialistManpower,
    workforceRequired,
    phasedActivities,
    executionWorkstreams,
    stageDrivers,
    segmentDrivers,
    assumptionsAndRisks,
    successCriteria,
    milestones: rawPlan.milestones || [],
    deliverables: rawPlan.deliverables || [],
    timeline,
    totalEffortHours: totalEffortHours || 0,
    totalEffortsDisplay,
    timelineAndEffort,
    targetOutcome,
    expectedOutcome: targetOutcome
  };
}

/**
 * Returns BRD plan if fetched from telemetry; otherwise returns strictly empty / "Not yet fetched".
 */
export function getBrdPlan(metric) {
  if (!metric) return null;

  const raw = metric.brdPlan || metric.plan;
  if (raw && typeof raw === 'object' && Object.keys(raw).length > 0) {
    return formatBrdPlan(raw, metric);
  }

  // Strict empty fallback for un-fetched metrics
  return {
    specialistManpower: [],
    workforceRequired: [],
    phasedActivities: [],
    executionWorkstreams: [],
    stageDrivers: [],
    segmentDrivers: [],
    assumptionsAndRisks: [],
    successCriteria: [],
    milestones: [],
    deliverables: [],
    timeline: 'Not yet fetched',
    totalEffortHours: 0,
    totalEffortsDisplay: 'Not yet fetched',
    timelineAndEffort: { timeline: 'Not yet fetched', totalEffort: 'Not yet fetched' },
    targetOutcome: 'Data not yet fetched',
    expectedOutcome: 'Data not yet fetched'
  };
}

export default getBrdPlan;
