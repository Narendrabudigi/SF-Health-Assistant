import { useState, useEffect } from 'react';
import ComparisonTable from './ComparisonTable';
import MetricDeepDivePage from './MetricDeepDivePage';
import ModuleTrendOverview from './ModuleTrendOverview';

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

  return (
    <div className="analysis-page-wrapper">
      {/* 1. Module Trend Overview */}
      <ModuleTrendOverview module={module} />

      {/* 2. Full-Width Company vs. Standards Comparison Table */}
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
