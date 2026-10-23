import React, { useEffect, useRef, useState } from 'react';
import { apiService } from '../services/apiService';

const TERMINAL_STATES = new Set(['succeeded', 'failed', 'stopped']);

export default function MlPipelineProgressModal({
  isOpen,
  onClose,
  activeModuleName,
  standards = 'industry',
  onCompleted,
  onFailed
}) {
  const [status, setStatus] = useState('idle');
  const [logs, setLogs] = useState([]);
  const [error, setError] = useState('');
  const onCompletedRef = useRef(onCompleted);
  const onFailedRef = useRef(onFailed);

  useEffect(() => { onCompletedRef.current = onCompleted; }, [onCompleted]);
  useEffect(() => { onFailedRef.current = onFailed; }, [onFailed]);

  useEffect(() => {
    if (!isOpen) {
      setStatus('idle');
      setLogs([]);
      setError('');
      return undefined;
    }

    let cancelled = false;
    let completedCallbackSent = false;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    const finish = (finalStatus, output = []) => {
      if (cancelled) return;
      setStatus(finalStatus);
      setLogs(output);
      if (finalStatus === 'succeeded' && !completedCallbackSent) {
        completedCallbackSent = true;
        onCompletedRef.current?.();
      } else if (finalStatus === 'failed') {
        onFailedRef.current?.(output.at(-1) || 'The orchestrator run failed.');
      }
    };

    const run = async () => {
      setStatus('starting');
      const standardLabel = standards === 'custom' ? 'custom standards' : 'industry standards';
      setLogs([`[${new Date().toLocaleTimeString()}] Starting the ML and LLM orchestrator for ${standardLabel}...`]);
      try {
        const started = await apiService.startOrchestratorPipeline({ standards });
        if (cancelled) return;
        setStatus(started.status || 'running');
        setLogs(started.output || []);

        if (TERMINAL_STATES.has(started.status)) {
          finish(started.status, started.output || []);
          return;
        }

        while (!cancelled) {
          await new Promise((resolve) => setTimeout(resolve, 3000));
          if (cancelled) return;
          const current = await apiService.getOrchestratorStatus(100);
          if (cancelled) return;
          setStatus(current.status || 'running');
          setLogs(current.output || []);
          if (TERMINAL_STATES.has(current.status)) {
            finish(current.status, current.output || []);
            return;
          }
        }
      } catch (requestError) {
        if (cancelled) return;
        const message = requestError.message || 'Could not communicate with the orchestrator.';
        setError(message);
        const failureLog = `[${new Date().toLocaleTimeString()}] ${message}`;
        setLogs((current) => [...current, failureLog]);
        finish('failed', [failureLog]);
      }
    };

    run();
    return () => {
      cancelled = true;
      document.body.style.overflow = previousOverflow;
    };
  }, [isOpen, standards]);

  if (!isOpen) return null;

  const isRunning = status === 'starting' || status === 'running';
  const isTerminal = TERMINAL_STATES.has(status);
  const progressPercent = status === 'succeeded' ? 100 : isRunning ? 42 : 0;
  const title = status === 'succeeded'
    ? 'Orchestrator Run Complete'
    : status === 'failed'
      ? 'Orchestrator Run Failed'
      : status === 'stopped'
        ? 'Orchestrator Run Stopped'
        : 'Running ML and LLM Orchestrator';

  const handleStop = async () => {
    setStatus('stopping');
    try {
      const result = await apiService.stopOrchestratorPipeline();
      setStatus(result.status || 'stopped');
      setLogs(result.output || logs);
    } catch (stopError) {
      setError(stopError.message);
      setStatus('running');
    }
  };

  return (
    <div className="modal-backdrop" onClick={isTerminal ? onClose : undefined}>
      <div
        className="modal-card pipeline-progress-modal"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="pipeline-modal-title"
      >
        <div className="modal-header">
          <div className="modal-title-wrap">
            <div className="modal-icon-badge pipeline-icon-badge" aria-hidden="true">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                {status === 'succeeded'
                  ? <polyline points="20 6 9 17 4 12" />
                  : <><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" /></>}
              </svg>
            </div>
            <div>
              <h3 id="pipeline-modal-title" className="modal-title">{title}</h3>
              <p className="modal-subtitle">
                {activeModuleName ? `${activeModuleName} selected · ` : ''}
                Running the orchestrator across all configured modules using {standards === 'custom' ? 'custom' : 'industry'} standards.
              </p>
            </div>
          </div>
          {isTerminal && (
            <button className="btn-modal-close" onClick={onClose} aria-label="Close modal">✕</button>
          )}
        </div>

        <div className="pipeline-modal-body">
          <div className="pipeline-progress-track-wrap">
            <div className="pipeline-progress-meta">
              <span className="pipeline-status-text">
                {status === 'starting' ? 'Starting background run…' :
                  status === 'running' ? 'Running notebooks and generating reports…' :
                    status === 'succeeded' ? 'Completed successfully' :
                      status === 'failed' ? 'Run failed' :
                        status === 'stopped' ? 'Run stopped' : 'Preparing run…'}
              </span>
              {status === 'succeeded' && <span className="pipeline-percent-text">100%</span>}
            </div>
            <div className="pipeline-track" role="progressbar" aria-label="Orchestrator run progress" aria-valuetext={isRunning ? 'Running' : status}>
              <div
                className={`pipeline-fill-bar ${status === 'succeeded' ? 'is-complete' : ''} ${isRunning ? 'is-running' : ''}`}
                style={{ width: `${progressPercent}%` }}
              />
            </div>
          </div>

          <section className="pipeline-console-box" aria-label="Orchestrator output">
            <div className="console-header">
              <span className="console-dot dot-red" />
              <span className="console-dot dot-yellow" />
              <span className="console-dot dot-green" />
              <span className="console-title">Live orchestrator output</span>
            </div>
            <div className="console-logs-content" aria-live="polite">
              {logs.length ? logs.map((line, index) => (
                <div key={`${index}-${line}`} className="console-line">{line}</div>
              )) : (
                <div className="console-line">Waiting for orchestrator output…</div>
              )}
            </div>
          </section>
          {error && <p role="alert" className="pipeline-error-message">{error}</p>}
        </div>

        <div className="modal-footer">
          {isRunning || status === 'stopping' ? (
            <button type="button" className="btn-primary btn-pipeline-finish" onClick={handleStop} disabled={status === 'stopping'}>
              {status === 'stopping' ? 'Stopping…' : 'Stop run'}
            </button>
          ) : (
            <button type="button" className="btn-primary btn-pipeline-finish" onClick={onClose} autoFocus>
              {status === 'succeeded' ? 'View refreshed insights' : 'Close'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
