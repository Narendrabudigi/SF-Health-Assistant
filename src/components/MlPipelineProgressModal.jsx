import React, { useEffect, useState } from 'react';

const PIPELINE_STEPS = [
  {
    id: 'ingestion',
    name: '1. SuccessFactors Data Ingestion',
    sub: 'Pulling OData delta telemetry from SAP SuccessFactors tenant',
    tech: 'OData API • Delta Sync',
    durationMs: 600
  },
  {
    id: 'ml_engine',
    name: '2. Analytics & TreeSHAP ML Model',
    sub: 'Computing dual variance, health state classification & breach drivers',
    tech: 'SAP BTP • TreeSHAP ML',
    durationMs: 750
  },
  {
    id: 'llm_gen',
    name: '3. Asynchronous LLM Engine',
    sub: 'Synthesizing diagnoses & resource-staffed BRD action plans',
    tech: 'Gemini 1.5 Pro (Grok Fallback)',
    durationMs: 900
  },
  {
    id: 'data_fabric',
    name: '4. Supabase Central Fabric Commit',
    sub: 'Writing pre-computed BRD action plans & ML drivers to central cache',
    tech: 'PostgreSQL JSONB • Supabase',
    durationMs: 500
  },
  {
    id: 'ui_refresh',
    name: '5. FastAPI Backend & React UI Re-hydration',
    sub: 'Streaming refreshed telemetry & updating live dashboard state',
    tech: 'FastAPI • Sub-50ms React Update',
    durationMs: 400
  }
];

export default function MlPipelineProgressModal({
  isOpen,
  onClose,
  activeModuleName,
  onCompleted
}) {
  const [currentStepIdx, setCurrentStepIdx] = useState(0);
  const [isDone, setIsDone] = useState(false);
  const [logs, setLogs] = useState([]);
  const onCompletedRef = React.useRef(onCompleted);

  useEffect(() => {
    onCompletedRef.current = onCompleted;
  }, [onCompleted]);

  useEffect(() => {
    if (!isOpen) {
      setCurrentStepIdx(0);
      setIsDone(false);
      setLogs([]);
      return;
    }

    let isCancelled = false;
    let step = 0;
    let stepTimer = null;

    const prevBodyOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    const initialLog = `[${new Date().toLocaleTimeString()}] Pipeline triggered for ${activeModuleName || 'Enterprise Suite'}...`;
    setLogs([initialLog]);

    const runNextStep = () => {
      if (isCancelled) return;

      if (step >= PIPELINE_STEPS.length) {
        setIsDone(true);
        setLogs((prev) => [
          ...prev,
          `[${new Date().toLocaleTimeString()}] ✓ Pipeline run completed successfully. UI state re-hydrated.`
        ]);
        if (onCompletedRef.current) {
          onCompletedRef.current();
        }
        return;
      }

      const currentStep = PIPELINE_STEPS[step];
      setCurrentStepIdx(step);

      setLogs((prev) => [
        ...prev,
        `[${new Date().toLocaleTimeString()}] Executing ${currentStep.name} (${currentStep.tech})...`
      ]);

      stepTimer = setTimeout(() => {
        if (isCancelled) return;
        step += 1;
        runNextStep();
      }, currentStep.durationMs);
    };

    const initialTimer = setTimeout(runNextStep, 250);

    return () => {
      isCancelled = true;
      clearTimeout(initialTimer);
      if (stepTimer) clearTimeout(stepTimer);
      document.body.style.overflow = prevBodyOverflow;
    };
  }, [isOpen]);

  if (!isOpen) return null;

  const progressPercent = isDone 
    ? 100 
    : Math.round(((currentStepIdx + 1) / PIPELINE_STEPS.length) * 90);

  return (
    <div className="modal-backdrop" onClick={isDone ? onClose : undefined}>
      <div 
        className="modal-card pipeline-progress-modal" 
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="pipeline-modal-title"
      >
        {/* Header */}
        <div className="modal-header">
          <div className="modal-title-wrap">
            <div className="modal-icon-badge pipeline-icon-badge">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
              </svg>
            </div>
            <div>
              <h3 id="pipeline-modal-title" className="modal-title">
                {isDone ? 'Pipeline Execution Complete' : 'Executing Architecture Pipeline'}
              </h3>
              <p className="modal-subtitle">
                {activeModuleName ? `${activeModuleName} • ` : ''}Running Analytics, TreeSHAP ML &amp; Asynchronous LLM Synthesis
              </p>
            </div>
          </div>
          {isDone && (
            <button className="btn-modal-close" onClick={onClose} aria-label="Close modal">
              ✕
            </button>
          )}
        </div>

        {/* Modal Body */}
        <div className="pipeline-modal-body">
          {/* Overall Progress Bar */}
          <div className="pipeline-progress-track-wrap">
            <div className="pipeline-progress-meta">
              <span className="pipeline-status-text">
                {isDone ? 'All Pipeline Stages Successfully Synchronized' : `Executing Stage ${currentStepIdx + 1} of ${PIPELINE_STEPS.length}...`}
              </span>
              <span className="pipeline-percent-text">{progressPercent}%</span>
            </div>
            <div className="pipeline-track">
              <div 
                className={`pipeline-fill-bar ${isDone ? 'is-complete' : ''}`}
                style={{ width: `${progressPercent}%` }}
              />
            </div>
          </div>

          {/* Stepper Grid (Aligned with Eraser Architecture Diagram) */}
          <div className="pipeline-stepper-list">
            {PIPELINE_STEPS.map((s, idx) => {
              const isPassed = isDone || idx < currentStepIdx;
              const isCurrent = !isDone && idx === currentStepIdx;

              let stepStateClass = 'step-pending';
              if (isPassed) stepStateClass = 'step-passed';
              else if (isCurrent) stepStateClass = 'step-active';

              return (
                <div key={s.id} className={`pipeline-step-item ${stepStateClass}`}>
                  <div className="step-icon-col">
                    <div className="step-node-bubble">
                      {isPassed ? (
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                          <polyline points="20 6 9 17 4 12"></polyline>
                        </svg>
                      ) : isCurrent ? (
                        <span className="step-spinning-indicator"></span>
                      ) : (
                        <span className="step-num">{idx + 1}</span>
                      )}
                    </div>
                    {idx < PIPELINE_STEPS.length - 1 && (
                      <div className={`step-connector-line ${isPassed ? 'connector-passed' : ''}`} />
                    )}
                  </div>

                  <div className="step-content-col">
                    <div className="step-top-line">
                      <span className="step-name">{s.name}</span>
                      <span className="step-tech-badge">{s.tech}</span>
                    </div>
                    <p className="step-sub">{s.sub}</p>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Real-time Execution Log Console */}
          <div className="pipeline-console-box">
            <div className="console-header">
              <span className="console-dot dot-red"></span>
              <span className="console-dot dot-yellow"></span>
              <span className="console-dot dot-green"></span>
              <span className="console-title">FastAPI &amp; SAP BTP Execution Telemetry</span>
            </div>
            <div className="console-logs-content">
              {logs.map((log, i) => (
                <div key={i} className="console-line">
                  {log}
                </div>
              ))}
              {!isDone && (
                <div className="console-line line-cursor">
                  <span className="console-prompt">&gt;</span> Processing active pipeline batch...
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="modal-footer">
          {isDone ? (
            <button 
              type="button" 
              className="btn-primary btn-pipeline-finish"
              onClick={onClose}
              autoFocus
            >
              <span>View Refreshed Insights</span>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <polyline points="9 18 15 12 9 6"></polyline>
              </svg>
            </button>
          ) : (
            <div className="pipeline-waiting-indicator">
              <span className="pipeline-pulse-dot"></span>
              <span>Processing ML calculations and asynchronous LLM synthesis...</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
