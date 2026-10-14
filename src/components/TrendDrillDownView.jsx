import React, { useState, useMemo, useEffect, useRef } from 'react';
import { getTrendDrillDownData } from '../utils/trendDrillDownData';
import { formatDisplayUnits } from '../utils/displayUnits';

export default function TrendDrillDownView({ metric }) {
  const metricName = metric?.metric;
  const trendData = useMemo(() => getTrendDrillDownData(metric), [metric]);
  const isUnfetched = !metric?.isSupabaseLive || metric?.company === 'Not yet fetched' || ['data not yet fetched', 'data not yet fetched from supabase'].includes(String(metric?.company || '').toLowerCase());
  const isDataGap = Boolean(
    metric?.company === 'N/A' ||
    String(metric?.company || '').toLowerCase().includes('no data') ||
    String(metric?.variance || '').toLowerCase().includes('data gap')
  );

  const currentYearId = useMemo(() => {
    if (!trendData?.years?.length) return '';
    const cur = trendData.years.find((y) => y.isCurrent);
    return cur ? cur.year : (trendData.defaultYear || trendData.years[trendData.years.length - 1].year);
  }, [trendData]);

  const currentQuarterId = useMemo(() => {
    if (!trendData?.years?.length) return '';
    const curY = trendData.years.find((y) => y.year === currentYearId);
    const curQ = curY?.quarters.find((q) => q.isCurrent);
    return curQ ? curQ.quarter : (trendData.defaultQuarter || curY?.quarters?.[curY.quarters.length - 1]?.quarter || '');
  }, [trendData, currentYearId]);

  const [level, setLevel] = useState('yearly'); // 'yearly' | 'quarterly' | 'monthly'
  const [selectedYear, setSelectedYear] = useState(currentYearId);
  const [selectedQuarter, setSelectedQuarter] = useState(currentQuarterId);

  // Guard metric reset with ref to avoid any re-render loops
  const prevMetricRef = useRef(metricName);
  useEffect(() => {
    if (prevMetricRef.current !== metricName) {
      prevMetricRef.current = metricName;
      setLevel('yearly');
      setSelectedYear(currentYearId);
      setSelectedQuarter(currentQuarterId);
    }
  }, [metricName, currentYearId, currentQuarterId]);

  const {
    standard,
    standardNumeric,
    unit,
    isLowerBetter,
    years
  } = trendData || { standard: '', standardNumeric: 0, unit: '', isLowerBetter: false, years: [] };

  // Active Year object
  const currentYearObj = useMemo(() => {
    return years.find((y) => y.year === selectedYear) || years[years.length - 1];
  }, [years, selectedYear]);

  // Active Quarter object
  const currentQuarterObj = useMemo(() => {
    if (!currentYearObj) return null;
    return currentYearObj.quarters.find((q) => q.quarter === selectedQuarter) || currentYearObj.quarters[currentYearObj.quarters.length - 1];
  }, [currentYearObj, selectedQuarter]);

  // Active items being displayed based on current level
  const activeItems = useMemo(() => {
    if (level === 'yearly') {
      return years.map((y) => ({
        id: y.year,
        label: y.label,
        period: y.period,
        value: y.value,
        numericValue: y.numericValue,
        status: y.status,
        variance: y.variance,
        change: y.yoyChange,
        changeLabel: 'YoY',
        isCurrent: y.isCurrent,
        summary: y.summary,
        canDrill: y.quarters.length > 0,
        drillPrompt: `View ${y.quarters.length} Quarters`
      }));
    }

    if (level === 'quarterly') {
      return (currentYearObj?.quarters || []).map((q) => ({
        id: q.quarter,
        label: q.label,
        period: q.period,
        value: q.value,
        numericValue: q.numericValue,
        status: q.status,
        variance: q.variance,
        change: q.qoqChange,
        changeLabel: 'QoQ',
        isCurrent: q.isCurrent,
        summary: q.summary,
        canDrill: q.months.length > 0,
        drillPrompt: `View ${q.months.length} Months`
      }));
    }

    // Monthly level
    return (currentQuarterObj?.months || []).map((m) => ({
      id: m.id,
      label: m.month,
      period: m.period,
      value: m.value,
      numericValue: m.numericValue,
      status: m.status,
      variance: m.variance,
      change: m.momChange,
      changeLabel: 'MoM',
      isCurrent: m.isCurrent,
      summary: m.notes,
      canDrill: false,
      drillPrompt: 'Monthly Detail'
    }));
  }, [level, years, currentYearObj, currentQuarterObj]);

  // Calculate dynamic bar heights relative to min & max across the active set
  const barHeights = useMemo(() => {
    if (!activeItems || activeItems.length === 0) return {};
    const values = activeItems.map((i) => i.numericValue).filter(Number.isFinite);
    if (!values.length) return {};
    const minVal = Math.min(...values, standardNumeric);
    const maxVal = Math.max(...values, standardNumeric);
    const range = maxVal - minVal || 1;

    const map = {};
    activeItems.forEach((item) => {
      // Scale height between 38% and 94%
      const normalized = (item.numericValue - minVal) / range;
      const heightPercent = Math.round(38 + normalized * 54);
      map[item.id] = Math.min(100, Math.max(25, heightPercent));
    });
    return map;
  }, [activeItems, standardNumeric]);

  // Aggregate scope summary stats
  const scopeSummary = useMemo(() => {
    if (!activeItems || activeItems.length === 0) return null;
    const values = activeItems.map((i) => i.numericValue).filter(Number.isFinite);
    const avg = values.length ? (values.reduce((a, b) => a + b, 0) / values.length).toFixed(trendData.decimals) : 'Data Gap';
    const isCriticalCount = activeItems.filter((i) => i.status === 'Critical').length;
    const isHealthyCount = activeItems.filter((i) => i.status === 'Healthy').length;

    let overallScopeStatus = values.length ? 'At Risk' : 'Data Gap';
    if (isCriticalCount >= activeItems.length / 2) overallScopeStatus = 'Critical';
    else if (isHealthyCount === activeItems.length) overallScopeStatus = 'Healthy';

    let scopeTitle = '';
    let scopeContext = '';

    if (level === 'yearly') {
      scopeTitle = 'Multi-Year Macro Trend (2024 – 2026)';
      scopeContext = 'Annualized enterprise tracking across fiscal operating years. Tap any year to drill into quarterly milestones.';
    } else if (level === 'quarterly') {
      scopeTitle = `FY ${selectedYear} Quarterly Breakdown`;
      scopeContext = currentYearObj?.summary || `Quarter-by-quarter operational progression for FY ${selectedYear}. Tap any quarter to inspect monthly logs.`;
    } else {
      scopeTitle = `${selectedQuarter} ${selectedYear} Monthly Cadence`;
      scopeContext = currentQuarterObj?.summary || `Month-over-month operational review for ${selectedQuarter} ${selectedYear}.`;
    }

    return {
      title: scopeTitle,
      context: scopeContext,
      avg: `${avg}${unit}`,
      status: overallScopeStatus
    };
  }, [activeItems, level, selectedYear, selectedQuarter, currentYearObj, currentQuarterObj, trendData, unit]);

  // Drill down handler
  const handleItemClick = (item) => {
    if (level === 'yearly') {
      setSelectedYear(item.id);
      setLevel('quarterly');
    } else if (level === 'quarterly') {
      setSelectedQuarter(item.id);
      setLevel('monthly');
    }
  };

  if (isUnfetched) {
    return <div style={{ padding: '24px', textAlign: 'center', color: '#64748b' }}><p style={{ margin: 0, fontWeight: 500 }}>Data not yet fetched.</p></div>;
  }

  if (!years.length) {
    return (
      <div style={{ padding: '20px 24px', borderRadius: '8px', background: 'rgba(245, 158, 11, 0.08)', border: '1px solid rgba(245, 158, 11, 0.25)', borderLeft: '4px solid #f59e0b', color: '#92400e' }}>
        <div style={{ fontWeight: 700, marginBottom: '4px' }}>Historical Trend Data Unavailable</div>
        <div style={{ fontSize: '12px', lineHeight: 1.55 }}>{isDataGap ? 'The metric has data gaps, and ML Insights has no historical periods to display.' : 'No yearly, quarterly, or monthly periods were found for this metric in ML Insights.'}</div>
      </div>
    );
  }

  return (
    <div className="trend-drilldown-container" aria-label="Hierarchical Trend Analysis">
      {/* 1. Header Toolbar with Interactive Breadcrumb & Granularity Tabs */}
      <div className="trend-drilldown-toolbar">
        {/* Interactive Breadcrumb Hierarchy */}
        <nav className="trend-breadcrumb-nav" aria-label="Trend drill-down path">
          <button
            type="button"
            className={`trend-crumb-btn ${level === 'yearly' ? 'crumb-active' : ''}`}
            onClick={() => setLevel('yearly')}
            title="Switch to Yearly Overview"
          >
            <span className="crumb-icon">📅</span>
            <span>All Years</span>
          </button>

          {(level === 'quarterly' || level === 'monthly') && (
            <>
              <span className="trend-crumb-sep">›</span>
              <button
                type="button"
                className={`trend-crumb-btn ${level === 'quarterly' ? 'crumb-active' : ''}`}
                onClick={() => setLevel('quarterly')}
                title={`View ${selectedYear} Quarters`}
              >
                <span>FY {selectedYear}</span>
              </button>
            </>
          )}

          {level === 'monthly' && (
            <>
              <span className="trend-crumb-sep">›</span>
              <span className="trend-crumb-active">
                <span>{selectedQuarter} Months</span>
              </span>
            </>
          )}
        </nav>

        {/* Level Switcher Pill Tabs (Yearly / Quarterly / Monthly) */}
        <div className="trend-level-pill-group" role="tablist" aria-label="Select trend granularity">
          <button
            type="button"
            role="tab"
            aria-selected={level === 'yearly'}
            className={`trend-level-pill ${level === 'yearly' ? 'level-pill-active' : ''}`}
            onClick={() => setLevel('yearly')}
          >
            Yearly
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={level === 'quarterly'}
            className={`trend-level-pill ${level === 'quarterly' ? 'level-pill-active' : ''}`}
            onClick={() => {
              setSelectedYear(currentYearId);
              setLevel('quarterly');
            }}
            title={`View FY ${currentYearId} Quarters`}
          >
            Quarterly
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={level === 'monthly'}
            className={`trend-level-pill ${level === 'monthly' ? 'level-pill-active' : ''}`}
            onClick={() => {
              setSelectedYear(currentYearId);
              setSelectedQuarter(currentQuarterId);
              setLevel('monthly');
            }}
            title={`View ${currentQuarterId} ${currentYearId} Months`}
          >
            Monthly
          </button>
        </div>
      </div>

      {/* 2. Secondary Sub-Bar for Quick Period Switching when Drilled Down */}
      {level !== 'yearly' && (
        <div className="trend-sub-toolbar">
          <div className="trend-sub-left">
            {level === 'quarterly' && (
              <div className="trend-filter-row">
                <span className="trend-filter-label">Select Year:</span>
                <div className="trend-filter-pills">
                  {years.map((y) => (
                    <button
                      key={y.year}
                      type="button"
                      className={`trend-filter-chip ${selectedYear === y.year ? 'chip-selected' : ''}`}
                      onClick={() => setSelectedYear(y.year)}
                    >
                      {y.year} {y.isCurrent ? '(Current)' : ''}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {level === 'monthly' && (
              <div className="trend-filter-row">
                <span className="trend-filter-label">Select Quarter:</span>
                <div className="trend-filter-pills">
                  {(currentYearObj?.quarters || []).map(({ quarter: q }) => (
                    <button
                      key={q}
                      type="button"
                      className={`trend-filter-chip ${selectedQuarter === q ? 'chip-selected' : ''}`}
                      onClick={() => setSelectedQuarter(q)}
                    >
                      {q} {selectedYear === '2026' && q === 'Q4' ? '(Current)' : ''}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          <button
            type="button"
            className="btn-trend-stepup"
            onClick={() => {
              if (level === 'monthly') setLevel('quarterly');
              else if (level === 'quarterly') setLevel('yearly');
            }}
            title={level === 'monthly' ? 'Back to Quarters' : 'Back to Yearly'}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <polyline points="15 18 9 12 15 6"></polyline>
            </svg>
            <span>{level === 'monthly' ? `Back to ${selectedYear} Quarters` : 'Back to Yearly View'}</span>
          </button>
        </div>
      )}

      {/* 3. Scope Insight & KPI Summary Strip */}
      <div className="trend-scope-banner">
        <div className="trend-scope-text-wrap">
          <div className="trend-scope-heading-row">
            <h3 className="trend-scope-title">{scopeSummary?.title}</h3>
            <span className={`pill-badge ${scopeSummary?.status === 'Critical' ? 'badge-critical' : scopeSummary?.status === 'Healthy' ? 'badge-healthy' : 'badge-at-risk'}`}>
              {scopeSummary?.status}
            </span>
          </div>
            <p className="trend-scope-context">{formatDisplayUnits(scopeSummary?.context)}</p>
        </div>

        {/* Mini KPI metrics */}
        <div className="trend-scope-kpis">
          <div className="trend-kpi-block">
            <span className="trend-kpi-lbl">Period Average</span>
            <span className="trend-kpi-val">{formatDisplayUnits(scopeSummary?.avg)}</span>
          </div>
          <div className="trend-kpi-sep" />
          <div className="trend-kpi-block">
            <span className="trend-kpi-lbl">SLA Benchmark</span>
            <span className="trend-kpi-val val-standard">{formatDisplayUnits(standard)}</span>
          </div>
        </div>
      </div>

      {/* 4. Interactive Visual Cards / Bar Columns Grid */}
      <div className={`trend-cards-grid grid-${level}`} role="region" aria-label={`${level} trend data points`}>
        {activeItems.map((item) => {
          const isCritical = item.status === 'Critical';
          const isHealthy = item.status === 'Healthy';
          const statusClass = isCritical ? 'item-critical' : isHealthy ? 'item-healthy' : 'item-atrisk';
          const barHeight = barHeights[item.id] || 50;

          return (
            <div
              key={item.id}
              tabIndex={item.canDrill ? 0 : -1}
              role={item.canDrill ? 'button' : 'article'}
              className={`trend-interactive-card ${statusClass} ${item.isCurrent ? 'card-is-current' : ''} ${item.canDrill ? 'card-clickable' : ''}`}
              onClick={() => item.canDrill && handleItemClick(item)}
              onKeyDown={(e) => {
                if (item.canDrill && (e.key === 'Enter' || e.key === ' ')) {
                  e.preventDefault();
                  handleItemClick(item);
                }
              }}
              title={formatDisplayUnits(item.canDrill ? `Click to drill into ${item.drillPrompt}` : item.period)}
            >
              {item.isCurrent && (
                <div className="trend-active-ribbon">
                  <span>Current</span>
                </div>
              )}

              {/* Card Header */}
              <div className="trend-card-top-row">
                <span className="trend-card-period-tag">{formatDisplayUnits(item.label)}</span>
                <span className={`trend-micro-pill ${isCritical ? 'micro-critical' : isHealthy ? 'micro-healthy' : 'micro-atrisk'}`}>
                  {item.status}
                </span>
              </div>

              {/* Card Value Display */}
              <div className="trend-card-val-row">
                <span className="trend-card-primary-val">{formatDisplayUnits(item.value)}</span>
                {item.change && item.change !== '-' && (
                  <span className={`trend-change-badge ${item.change.startsWith('+') ? (isLowerBetter ? 'trend-delta-worse' : 'trend-delta-better') : (isLowerBetter ? 'trend-delta-better' : 'trend-delta-worse')}`}>
                    {item.change.startsWith('+') ? '▲' : '▼'} {formatDisplayUnits(item.change)} {formatDisplayUnits(item.changeLabel)}
                  </span>
                )}
              </div>

              {/* Visual Bar Column Representation */}
              <div className="trend-bar-track-wrap">
                <div className="trend-bar-track">
                  <div
                    className={`trend-bar-fill ${isCritical ? 'bar-critical' : isHealthy ? 'bar-healthy' : 'bar-atrisk'}`}
                    style={{ height: `${barHeight}%` }}
                  />
                  {/* Subtle Target Baseline marker */}
                  <div className="trend-target-baseline" title={`Benchmark Standard: ${standard}`} />
                </div>
              </div>

              {/* Card Bottom Meta & Drill Cue */}
              <div className="trend-card-footer">
                <span className="trend-variance-sub">
                  Gap: <strong>{formatDisplayUnits(item.variance)}</strong>
                </span>

                {item.canDrill ? (
                  <div className="trend-drill-indicator">
                    <span className="drill-text">{item.drillPrompt}</span>
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                      <polyline points="9 18 15 12 9 6"></polyline>
                    </svg>
                  </div>
                ) : (
                  <span className="trend-leaf-indicator">Monthly Verified</span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* 5. Helpful Interactive Hint Footer */}
      <div className="trend-drilldown-footer-hint">
        <div className="hint-left">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#0284c7" strokeWidth="2">
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="12" y1="16" x2="12" y2="12"></line>
            <line x1="12" y1="8" x2="12.01" y2="8"></line>
          </svg>
          {level === 'yearly' && (
            <span><strong>Drill-Down Guide:</strong> Click any <strong>Year</strong> card above to inspect its 4 quarterly milestones.</span>
          )}
          {level === 'quarterly' && (
            <span><strong>Drill-Down Guide:</strong> Click any <strong>Quarter</strong> card to drill down into its 3 monthly operational logs.</span>
          )}
          {level === 'monthly' && (
            <span><strong>Detailed View:</strong> You are viewing monthly velocity for <strong>{selectedQuarter} {selectedYear}</strong>. Use the breadcrumb or tabs above to zoom back out.</span>
          )}
        </div>
        <div className="hint-right">
          <span className="hint-target-legend">
            <span className="legend-dot dot-critical" /> Critical
            <span className="legend-dot dot-atrisk" /> At Risk
            <span className="legend-dot dot-healthy" /> Healthy
          </span>
        </div>
      </div>
    </div>
  );
}
