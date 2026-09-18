import React, { useState, useRef, useEffect } from 'react';

export default function UploadCustomStandardsModal({
  isOpen,
  onClose,
  onImport,
  module
}) {
  const [dragOver, setDragOver] = useState(false);
  const [file, setFile] = useState(null);
  const [parseError, setParseError] = useState(null);
  const [parsedData, setParsedData] = useState([]);
  const [verifiedCount, setVerifiedCount] = useState(0);
  const fileInputRef = useRef(null);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && isOpen) {
        handleClose();
      }
    };
    if (isOpen) {
      const prevBodyOverflow = document.body.style.overflow;
      const prevHtmlOverflow = document.documentElement.style.overflow;
      document.body.style.overflow = 'hidden';
      document.documentElement.style.overflow = 'hidden';
      window.addEventListener('keydown', handleKeyDown);
      return () => {
        document.body.style.overflow = prevBodyOverflow;
        document.documentElement.style.overflow = prevHtmlOverflow;
        window.removeEventListener('keydown', handleKeyDown);
      };
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleClose = () => {
    setFile(null);
    setParseError(null);
    setParsedData([]);
    setVerifiedCount(0);
    onClose();
  };

  const parseCSV = (csvText) => {
    setParseError(null);
    setParsedData([]);
    setVerifiedCount(0);

    const lines = csvText
      .split(/\r?\n/)
      .map(line => line.trim())
      .filter(line => line.length > 0);

    if (lines.length < 2) {
      setParseError('CSV file is empty or missing data rows. At least a header row and one metric row are required.');
      return;
    }

    // Parse header row
    const parseLine = (line) => {
      // Split by comma taking quoted strings into account
      const result = [];
      let current = '';
      let inQuotes = false;
      for (let i = 0; i < line.length; i++) {
        const char = line[i];
        if (char === '"') {
          inQuotes = !inQuotes;
        } else if (char === ',' && !inQuotes) {
          result.push(current.trim());
          current = '';
        } else {
          current += char;
        }
      }
      result.push(current.trim());
      return result;
    };

    const headers = parseLine(lines[0]);

    // Validation Rule 1: Exactly 2 columns
    if (headers.length !== 2) {
      setParseError(`Invalid column count: Found ${headers.length} columns. The file must contain exactly 2 columns: "Metric Name" and "Custom Standard".`);
      return;
    }

    const cleanHeader0 = headers[0].toLowerCase().replace(/[^a-z0-9]/g, '');
    const cleanHeader1 = headers[1].toLowerCase().replace(/[^a-z0-9]/g, '');

    const validCol0 = ['metricname', 'metric'].includes(cleanHeader0);
    const validCol1 = ['customstandard', 'standard', 'custombenchmark'].includes(cleanHeader1);

    if (!validCol0 || !validCol1) {
      setParseError(`Invalid column headers: "${headers[0]}" and "${headers[1]}". Required columns must be "Metric Name" and "Custom Standard".`);
      return;
    }

    const rows = [];
    const moduleBenchmarks = module?.benchmarks || [];

    for (let i = 1; i < lines.length; i++) {
      const cols = parseLine(lines[i]);
      if (cols.length === 2 && cols[0] && cols[1]) {
        const metricName = cols[0];
        const customStandard = cols[1];

        // Check if metric matches one of the module benchmarks
        const isMatched = moduleBenchmarks.some(
          b => b.metric.toLowerCase() === metricName.toLowerCase()
        );

        rows.push({
          metric: metricName,
          customStandard,
          isMatched
        });
      }
    }

    if (rows.length === 0) {
      setParseError('No valid data rows found in the uploaded CSV file.');
      return;
    }

    setParsedData(rows);
    setVerifiedCount(rows.length);
  };

  const handleFileChange = (e) => {
    const selectedFile = e.target.files?.[0];
    processFile(selectedFile);
  };

  const processFile = (selectedFile) => {
    if (!selectedFile) return;

    if (!selectedFile.name.toLowerCase().endsWith('.csv')) {
      setParseError('Invalid file type. Only .csv files are supported.');
      setFile(null);
      return;
    }

    setFile(selectedFile);

    const reader = new FileReader();
    reader.onload = (event) => {
      const text = event.target?.result;
      if (typeof text === 'string') {
        parseCSV(text);
      }
    };
    reader.readAsText(selectedFile);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    const droppedFile = e.dataTransfer.files?.[0];
    processFile(droppedFile);
  };

  const handleImportSubmit = () => {
    if (parsedData.length === 0) return;

    // Build key-value map: normalized metric name -> custom standard
    const standardsMap = {};
    parsedData.forEach(row => {
      standardsMap[row.metric.toLowerCase().trim()] = row.customStandard.trim();
    });

    onImport(standardsMap);
    handleClose();
  };

  const handleDownloadSample = () => {
    const moduleBenchmarks = module?.benchmarks || [];
    let sampleRows = [
      ['Metric Name', 'Custom Standard']
    ];

    if (moduleBenchmarks.length > 0) {
      moduleBenchmarks.forEach(b => {
        sampleRows.push([`"${b.metric}"`, `"${b.standard}"`]);
      });
    } else {
      sampleRows.push(['"Employee Data Accuracy Rate"', '"≥ 99.0%"']);
      sampleRows.push(['"Workflow Approval Cycle Time"', '"≤ 2.0 Days"']);
      sampleRows.push(['"Time to hire"', '"≤ 25 Days"']);
    }

    const csvContent = sampleRows.map(r => r.join(',')).join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', `${module?.id || 'custom'}_standards_template.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="modal-backdrop" onClick={handleClose} role="dialog" aria-modal="true" aria-labelledby="upload-modal-title">
      <div className="modal-card upload-standards-modal" onClick={(e) => e.stopPropagation()}>
        {/* Modal Header */}
        <div className="modal-header">
          <div className="modal-title-wrap">
            <div className="modal-icon-badge">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                <polyline points="17 8 12 3 7 8"></polyline>
                <line x1="12" y1="3" x2="12" y2="15"></line>
              </svg>
            </div>
            <div>
              <h3 id="upload-modal-title" className="modal-title">Upload Custom Standards</h3>
              <p className="modal-subtitle">
                Upload a 2-column CSV file to update benchmark standards across dependent metrics.
              </p>
            </div>
          </div>
          <button type="button" className="btn-modal-close" onClick={handleClose} aria-label="Close modal">
            ✕
          </button>
        </div>

        {/* Modal Content */}
        <div className="upload-modal-body">
          {/* Instructions Strip with Sample Template Link */}
          <div className="upload-instruction-card">
            <div className="instruction-badge">CSV Format Requirement</div>
            <p className="instruction-text">
              The uploaded file must be a <strong>.csv</strong> containing <strong>exactly two columns</strong>:
              <code>Metric Name</code> and <code>Custom Standard</code>.
            </p>
            <button
              type="button"
              className="btn-download-sample"
              onClick={handleDownloadSample}
              title="Download formatted CSV template for current module"
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                <polyline points="7 10 12 15 17 10"></polyline>
                <line x1="12" y1="15" x2="12" y2="3"></line>
              </svg>
              <span>Download Sample CSV Template</span>
            </button>
          </div>

          {/* Drag & Drop File Zone */}
          <div
            className={`csv-dropzone ${dragOver ? 'drag-over' : ''} ${file ? 'has-file' : ''}`}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && fileInputRef.current?.click()}
          >
            <input
              type="file"
              ref={fileInputRef}
              accept=".csv"
              style={{ display: 'none' }}
              onChange={handleFileChange}
            />

            <div className="dropzone-icon">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                <polyline points="14 2 14 8 20 8"></polyline>
                <line x1="12" y1="18" x2="12" y2="12"></line>
                <line x1="9" y1="15" x2="15" y2="15"></line>
              </svg>
            </div>

            {file ? (
              <div className="dropzone-file-info">
                <span className="file-name">{file.name}</span>
                <span className="file-size">({(file.size / 1024).toFixed(1)} KB) • Click to change file</span>
              </div>
            ) : (
              <div className="dropzone-prompt">
                <span className="prompt-primary">Click to browse or drag & drop your .csv file here</span>
                <span className="prompt-sub">Only valid 2-column CSV files will be processed</span>
              </div>
            )}
          </div>

          {/* Validation Error Alert */}
          {parseError && (
            <div className="csv-error-alert" role="alert">
              <span className="error-icon">⚠️</span>
              <div className="error-content">
                <span className="error-title">Verification Failed</span>
                <p className="error-msg">{parseError}</p>
              </div>
            </div>
          )}

          {/* Verification Success & Preview Table */}
          {parsedData.length > 0 && !parseError && (
            <div className="csv-verified-container">
              <div className="verified-header-strip">
                <div className="verified-pill">
                  <span className="check-icon">✓</span>
                  <span>Verified: {verifiedCount} Metrics Ready for Import</span>
                </div>
                <span className="verified-subtext">Exactly 2 columns validated</span>
              </div>

              <div className="csv-preview-table-wrapper">
                <table className="csv-preview-table">
                  <thead>
                    <tr>
                      <th scope="col">#</th>
                      <th scope="col">Metric Name</th>
                      <th scope="col">Custom Standard</th>
                      <th scope="col" className="text-center">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {parsedData.map((row, idx) => (
                      <tr key={idx}>
                        <td className="td-idx">{idx + 1}</td>
                        <td className="td-metric-name">{row.metric}</td>
                        <td className="td-custom-std">
                          <span className="custom-std-pill">{row.customStandard}</span>
                        </td>
                        <td className="td-status text-center">
                          <span className={`match-badge ${row.isMatched ? 'badge-matched' : 'badge-unmatched'}`}>
                            {row.isMatched ? 'Matched Module' : 'Custom'}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="modal-footer">
          <button type="button" className="btn-secondary" onClick={handleClose}>
            Cancel
          </button>
          <button
            type="button"
            className="btn-primary"
            disabled={parsedData.length === 0 || !!parseError}
            onClick={handleImportSubmit}
          >
            Import Custom Standards ({verifiedCount})
          </button>
        </div>
      </div>
    </div>
  );
}
