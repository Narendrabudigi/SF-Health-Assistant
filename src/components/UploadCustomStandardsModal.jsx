import React, { useEffect, useRef, useState } from 'react';
import { apiService } from '../services/apiService';
import { formatDisplayUnits } from '../utils/displayUnits';

export default function UploadCustomStandardsModal({ isOpen, onClose, onImport }) {
  const [dragOver, setDragOver] = useState(false);
  const [file, setFile] = useState(null);
  const [error, setError] = useState('');
  const [rows, setRows] = useState([]);
  const [busy, setBusy] = useState(false);
  const fileInputRef = useRef(null);

  const reset = () => {
    setFile(null);
    setError('');
    setRows([]);
    setBusy(false);
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  useEffect(() => {
    if (!isOpen) return undefined;
    const previousBodyOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const onKeyDown = (event) => {
      if (event.key === 'Escape' && !busy) {
        setFile(null);
        setError('');
        setRows([]);
        onClose();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => {
      document.body.style.overflow = previousBodyOverflow;
      window.removeEventListener('keydown', onKeyDown);
    };
  }, [isOpen, busy, onClose]);

  if (!isOpen) return null;

  const processFile = async (selectedFile) => {
    if (!selectedFile) return;
    setError('');
    setRows([]);
    if (!selectedFile.name.toLowerCase().endsWith('.xlsx')) {
      setFile(null);
      setError('Choose an .xlsx workbook with Module, Metric Name, and Industry Benchmark columns.');
      return;
    }
    setFile(selectedFile);
    setBusy(true);
    try {
      const preview = await apiService.previewCustomStandards(selectedFile);
      setRows(preview.standards || []);
    } catch (previewError) {
      setError(previewError.message || 'Could not validate the workbook.');
    } finally {
      setBusy(false);
    }
  };

  const handleImport = async () => {
    if (!file || rows.length === 0 || busy) return;
    setBusy(true);
    setError('');
    try {
      const result = await apiService.uploadCustomStandards(file);
      onImport(result.standardsMap || {});
      handleClose();
    } catch (uploadError) {
      setError(uploadError.message || 'Could not replace the workbook in Supabase.');
    } finally {
      setBusy(false);
    }
  };

  const handleDownloadTemplate = async () => {
    setError('');
    try {
      const blob = await apiService.downloadCustomStandardsTemplate();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'SF Health Monitoring Custom Standards Template.xlsx';
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (downloadError) {
      setError(downloadError.message || 'Could not download the workbook template.');
    }
  };

  return (
    <div className="modal-backdrop" onClick={busy ? undefined : handleClose} role="dialog" aria-modal="true" aria-labelledby="upload-modal-title">
      <div className="modal-card upload-standards-modal" onClick={(event) => event.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-title-wrap">
            <div className="modal-icon-badge" aria-hidden="true">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="17 8 12 3 7 8" />
                <line x1="12" y1="3" x2="12" y2="15" />
              </svg>
            </div>
            <div>
              <h3 id="upload-modal-title" className="modal-title">Upload Custom Standards</h3>
              <p className="modal-subtitle">Replace the current custom standards workbook in Supabase. The new workbook takes effect on the next refresh.</p>
            </div>
          </div>
          <button type="button" className="btn-modal-close" onClick={handleClose} disabled={busy} aria-label="Close modal">✕</button>
        </div>

        <div className="upload-modal-body">
          <div className="upload-instruction-card">
            <div className="instruction-badge">Excel Workbook Format</div>
            <p className="instruction-text">
              Include <code>Module</code>, <code>Metric Name</code>, and <code>Industry Benchmark</code> columns. Use the exact <code>Metric_Name</code> from Supabase (the downloaded template lists all 21 names). Supported modules: EC, RCM, ONB2, OFB2, and ECP.
            </p>
            <p className="instruction-text">Upload replaces <strong>SF Health Monitoring Custom Standards.xlsx</strong> in the <strong>SF_Health_Raw_Data</strong> bucket.</p>
            <button type="button" className="btn-secondary" onClick={handleDownloadTemplate} disabled={busy}>
              Download Sample Template (.xlsx)
            </button>
          </div>

          <div
            className={`csv-dropzone ${dragOver ? 'drag-over' : ''} ${file ? 'has-file' : ''}`}
            onDragOver={(event) => { event.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(event) => { event.preventDefault(); setDragOver(false); processFile(event.dataTransfer.files?.[0]); }}
            onClick={() => !busy && fileInputRef.current?.click()}
            role="button"
            tabIndex={0}
            onKeyDown={(event) => (event.key === 'Enter' || event.key === ' ') && !busy && fileInputRef.current?.click()}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".xlsx"
              disabled={busy}
              style={{ display: 'none' }}
              onChange={(event) => processFile(event.target.files?.[0])}
            />
            <div className="dropzone-icon" aria-hidden="true">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
                <line x1="12" y1="18" x2="12" y2="12" />
                <line x1="9" y1="15" x2="15" y2="15" />
              </svg>
            </div>
            {file ? (
              <div className="dropzone-file-info">
                <span className="file-name">{file.name}</span>
                <span className="file-size">{busy ? 'Validating workbook…' : `(${(file.size / 1024).toFixed(1)} KB) • Click to change file`}</span>
              </div>
            ) : (
              <div className="dropzone-prompt">
                <span className="prompt-primary">Click to browse or drag & drop your .xlsx workbook</span>
                <span className="prompt-sub">The workbook is validated before replacing the current Supabase file.</span>
              </div>
            )}
          </div>

          {error && (
            <div className="csv-error-alert" role="alert">
              <span className="error-icon">⚠️</span>
              <div className="error-content">
                <span className="error-title">Upload could not continue</span>
                <p className="error-msg">{error}</p>
              </div>
            </div>
          )}

          {rows.length > 0 && (
            <div className="csv-verified-container">
              <div className="verified-header-strip">
                <div className="verified-pill"><span className="check-icon">✓</span><span>Verified: {rows.length} custom standards</span></div>
                <span className="verified-subtext">Workbook ready to replace in Supabase</span>
              </div>
              <div className="csv-preview-table-wrapper">
                <table className="csv-preview-table">
                  <thead>
                    <tr><th scope="col">#</th><th scope="col">Module</th><th scope="col">Metric Name</th><th scope="col">Custom Standard</th></tr>
                  </thead>
                  <tbody>
                    {rows.map((row, index) => (
                      <tr key={`${row.module}:${row.metric}`}>
                        <td className="td-idx">{index + 1}</td>
                        <td>{row.moduleCode || row.module}</td>
                        <td className="td-metric-name">{row.metric}</td>
                        <td className="td-custom-std"><span className="custom-std-pill">{formatDisplayUnits(row.standard)}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>

        <div className="modal-footer">
          <button type="button" className="btn-secondary" onClick={handleClose} disabled={busy}>Cancel</button>
          <button type="button" className="btn-primary" disabled={!file || rows.length === 0 || busy} onClick={handleImport}>
            {busy ? 'Working…' : `Replace Custom Standards (${rows.length})`}
          </button>
        </div>
      </div>
    </div>
  );
}
