import { useMemo, useState } from 'react';

const parseNumber = (value) => {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  const match = String(value ?? '').replace(/,/g, '').match(/[-+]?\d*\.?\d+/);
  return match ? Number(match[0]) : null;
};

const formatValue = (value, sample) => {
  if (value == null) return '—';
  const text = String(sample ?? '');
  if (text.includes('%')) return `${value.toFixed(1)}%`;
  if (/day/i.test(text)) return `${value.toFixed(1)} days`;
  if (/hr/i.test(text)) return `${value.toFixed(1)} hrs`;
  return value.toFixed(1);
};

export default function ModuleTrendOverview({ module }) {
  const liveMetrics = useMemo(
    () => (module?.benchmarks || []).filter((b) => b?.isSupabaseLive && b?.metric),
    [module?.benchmarks]
  );
  const [selectedMetricName, setSelectedMetricName] = useState('');

  const selected = useMemo(() => {
    if (!liveMetrics.length) return null;
    return liveMetrics.find((m) => m.metric === selectedMetricName) || liveMetrics[0];
  }, [liveMetrics, selectedMetricName]);

  const points = useMemo(() => {
    const raw = selected?.detailedAnalysis?.trendAnalysis?.points
      || selected?.trendAnalysis?.periods
      || selected?.trendAnalysis?.points
      || [];
    return (Array.isArray(raw) ? raw : [])
      .map((p, index) => ({
        label: p.period || p.label || p.date || `P${index + 1}`,
        value: parseNumber(p.value ?? p.numericValue ?? p.actual ?? p.metricValue)
      }))
      .filter((p) => p.value != null);
  }, [selected]);

  const chart = useMemo(() => {
    if (points.length < 2) return null;
    const width = 860;
    const height = 250;
    const pad = { left: 54, right: 24, top: 24, bottom: 48 };
    const values = points.map((p) => p.value);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = max - min || Math.max(Math.abs(max) * 0.08, 1);
    const yMin = min - range * 0.12;
    const yMax = max + range * 0.12;
    const x = (i) => pad.left + (i / (points.length - 1)) * (width - pad.left - pad.right);
    const y = (v) => height - pad.bottom - ((v - yMin) / (yMax - yMin)) * (height - pad.top - pad.bottom);
    const coords = points.map((p, i) => ({ ...p, x: x(i), y: y(p.value) }));
    const line = coords.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ');
    const area = `${line} L ${coords[coords.length - 1].x.toFixed(1)} ${height - pad.bottom} L ${coords[0].x.toFixed(1)} ${height - pad.bottom} Z`;
    return { width, height, pad, coords, line, area, min, max };
  }, [points]);

  const selectedStandard = selected?.standard || '—';

  return (
    <section className="module-trend-panel" aria-label="Module trend overview">
      <div className="module-trend-header">
        <div>
          <h2 className="module-trend-title">Trend Overview</h2>
          <p className="module-trend-subtitle">Historical trajectory for the selected metric. Use the selector to switch metrics.</p>
        </div>
        <div className="module-trend-controls">
          <label htmlFor="module-trend-metric">Metric</label>
          <select
            id="module-trend-metric"
            value={selected?.metric || ''}
            onChange={(e) => setSelectedMetricName(e.target.value)}
            disabled={!liveMetrics.length}
          >
            {liveMetrics.length === 0 ? <option value="">No live trend data</option> : liveMetrics.map((m) => (
              <option key={m.metric} value={m.metric}>{m.metric}</option>
            ))}
          </select>
        </div>
      </div>

      {!selected || !chart ? (
        <div className="module-trend-empty">
          <strong>Trend data unavailable</strong>
          <span>Historical trend points are not available for the live metrics returned by the current data feed.</span>
        </div>
      ) : (
        <>
          <div className="module-trend-meta">
            <span><strong>{selected.metric}</strong></span>
            <span>Target: <strong>{selectedStandard}</strong></span>
            <span>Status: <strong>{selected.status || '—'}</strong></span>
          </div>
          <div className="module-trend-chart-wrap">
            <svg viewBox={`0 0 ${chart.width} ${chart.height}`} role="img" aria-label={`${selected.metric} trend chart`} className="module-trend-chart">
              <defs>
                <linearGradient id="moduleTrendArea" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" stopOpacity="0.20" />
                  <stop offset="100%" stopOpacity="0.02" />
                </linearGradient>
              </defs>
              {[0, 0.5, 1].map((ratio) => {
                const gy = chart.pad.top + ratio * (chart.height - chart.pad.top - chart.pad.bottom);
                const value = chart.max - ratio * (chart.max - chart.min);
                return <g key={ratio}><line x1={chart.pad.left} x2={chart.width - chart.pad.right} y1={gy} y2={gy} className="module-trend-grid" /><text x={8} y={gy + 4} className="module-trend-axis-label">{formatValue(value, selected.company)}</text></g>;
              })}
              <path d={chart.area} className="module-trend-area" />
              <path d={chart.line} className="module-trend-line" />
              {chart.coords.map((p) => (
                <g key={`${p.label}-${p.x}`}>
                  <circle cx={p.x} cy={p.y} r="4.5" className="module-trend-point" />
                  <text x={p.x} y={chart.height - 18} textAnchor="middle" className="module-trend-x-label">{p.label}</text>
                  <text x={p.x} y={p.y - 10} textAnchor="middle" className="module-trend-value-label">{formatValue(p.value, selected.company)}</text>
                </g>
              ))}
            </svg>
          </div>
        </>
      )}
    </section>
  );
}
