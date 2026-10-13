import { useState, useEffect } from 'react';
import ComparisonTable from './ComparisonTable';
import MetricDeepDivePage from './MetricDeepDivePage';

export default function ModuleAnalysisView({
  module,
  standardMode = 'standard',
  customStandardsMap = {},
  onGoHome: _onGoHome,
  onSelectModule: _onSelectModule,
  onDeepDiveChange
}) {
  const [selectedMetric, setSelectedMetric] = useState(() => {
    try {
      const saved = sessionStorage.getItem(`sf_active_metric_${module?.id}`);
      if (saved && module?.benchmarks) {
        const found = module.benchmarks.find((b) => b.metric === saved);
        if (found) return found;
      }
    } catch {
      // ignore
    }
    return null;
  });

  // Sync deep dive status with parent App component and persist in sessionStorage
  useEffect(() => {
    if (onDeepDiveChange) {
      onDeepDiveChange(Boolean(selectedMetric));
    }
    try {
      if (selectedMetric?.metric && module?.id) {
        sessionStorage.setItem(`sf_active_metric_${module.id}`, selectedMetric.metric);
      } else if (module?.id) {
        sessionStorage.removeItem(`sf_active_metric_${module.id}`);
      }
    } catch {
      // ignore
    }
  }, [selectedMetric, module?.id, onDeepDiveChange]);

  // When active module changes (e.g. from ribbon), reset selected metric
  useEffect(() => {
    setSelectedMetric(null);
  }, [module?.id]);

  // Handle ESC key to close deep dive
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && selectedMetric) {
        setSelectedMetric(null);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectedMetric]);

  // If a metric is selected, render the dedicated Full-Page Deep Dive with BRD Plan
  if (selectedMetric) {
    return (
      <MetricDeepDivePage
        metric={selectedMetric}
        module={module}
        onBack={() => setSelectedMetric(null)}
      />
    );
  }

  if (!module) return null;

  const statusCounts = (Array.isArray(module.benchmarks) ? module.benchmarks : []).reduce(
    (counts, benchmark) => {
      const status = String(benchmark?.status || '').toLowerCase();
      if (status.includes('crit')) counts.critical += 1;
      else if (status.includes('risk') || status.includes('warning')) counts.atRisk += 1;
      else if (status.includes('healthy') || status.includes('on track')) counts.healthy += 1;
      return counts;
    },
    { critical: 0, atRisk: 0, healthy: 0 }
  );

  return (
    <div className="analysis-page-wrapper">
      <section className="metric-status-summary" aria-label="Metric status summary">
        <article className="metric-status-card metric-status-critical">
          <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
            <path d="M12 3 22 20H2L12 3Z" />
            <path d="M12 9v5m0 3h.01" />
          </svg>
          <strong className="metric-status-count">{statusCounts.critical}</strong>
          <h2>Critical Issues</h2>
          <p>Requires immediate action</p>
        </article>

        <article className="metric-status-card metric-status-at-risk">
          <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
            <path d="M12 3 22 20H2L12 3Z" />
            <path d="M12 9v5m0 3h.01" />
          </svg>
          <strong className="metric-status-count">{statusCounts.atRisk}</strong>
          <h2>At Risk Issues</h2>
          <p>Need attention</p>
        </article>

        <article className="metric-status-card metric-status-healthy">
          <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
            <path d="M20 11.2V12a8 8 0 1 1-4.7-7.3" />
            <path d="m8.5 11.5 3 3L22 4" />
          </svg>
          <strong className="metric-status-count">{statusCounts.healthy}</strong>
          <h2>Healthy Metric</h2>
          <p>Performing well</p>
        </article>
      </section>

      {/* Full-Width Company vs. Standards Comparison Table */}
      <section className="analysis-table-full-section" aria-label="Company vs. Standards">
        <ComparisonTable
          module={module}
          standardMode={standardMode}
          onSelectMetric={setSelectedMetric}
          customStandardsMap={customStandardsMap}
        />
      </section>
    </div>
  );
}
