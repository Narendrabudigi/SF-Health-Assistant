import React, { useState } from 'react';
import GenAIReport from './GenAIReport';
import ComparisonTable from './ComparisonTable';
import MetricAnalysisModal from './MetricAnalysisModal';

export default function ModuleAnalysisView({ 
  module, 
  standardMode = 'standard',
  customStandardsMap = {}
}) {
  const [selectedMetric, setSelectedMetric] = useState(null);

  if (!module) return null;

  return (
    <>
      <div className="analysis-view-grid">
        {/* Left Half: AI Diagnostic Report (Accordion Diagnostic Cards) */}
        <section className="analysis-grid-col" aria-label="AI Diagnostic Report">
          <GenAIReport module={module} />
        </section>

        {/* Right Half: Company vs. Industry/Custom Standards */}
        <section className="analysis-grid-col" aria-label="Company vs. Standards">
          <ComparisonTable 
            module={module} 
            standardMode={standardMode} 
            onSelectMetric={setSelectedMetric}
            customStandardsMap={customStandardsMap}
          />
        </section>
      </div>

      {/* Deep-Dive Metric Diagnostics Overlay Window */}
      {selectedMetric && (
        <MetricAnalysisModal 
          metric={selectedMetric} 
          onClose={() => setSelectedMetric(null)} 
        />
      )}
    </>
  );
}

