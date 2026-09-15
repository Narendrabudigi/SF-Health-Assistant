import React from 'react';
import GenAIReport from './GenAIReport';
import ComparisonTable from './ComparisonTable';

export default function ModuleAnalysisView({ module }) {
  if (!module) return null;

  return (
    <div className="analysis-view-grid">
      {/* Left Half: AI Diagnostic Report */}
      <section className="analysis-grid-col" aria-label="AI Diagnostic Report">
        <GenAIReport module={module} />
      </section>

      {/* Right Half: Company vs. Industry Standards */}
      <section className="analysis-grid-col" aria-label="Company vs. Industry Standards">
        <ComparisonTable module={module} />
      </section>
    </div>
  );
}
