import { useEffect, useMemo, useState } from 'react';
import { apiService } from '../services/apiService';

const PAGE_SIZE = 100;

function formatDatasetCell(value) {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'string') {
    const isoDateTime = value.match(/^(\d{4}-\d{2}-\d{2})T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?$/);
    if (isoDateTime) return isoDateTime[1];
  }
  return String(value);
}

export default function MetricDatasetPage({ module, metric, onBack }) {
  const [dataset, setDataset] = useState(null);
  const [offset, setOffset] = useState(0);
  const [selectedDateColumn, setSelectedDateColumn] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [selectedColumns, setSelectedColumns] = useState('default');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    apiService.getMetricDataset(module?.id, metric?.metric || metric?.metricName, metric?.code || '', module?.name || '', offset, PAGE_SIZE, selectedDateColumn || dataset?.dateColumns?.[0] || '', dateFrom, dateTo)
      .then((result) => {
        if (active) {
          setDataset(result);
          setSelectedDateColumn((current) => current || result.dateColumns?.[0] || '');
        }
      })
      .catch((requestError) => { if (active) setError(requestError.message || 'Could not load this dataset from Supabase.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [module?.id, module?.name, metric?.metric, metric?.metricName, metric?.code, offset, selectedDateColumn, dateFrom, dateTo]);

  useEffect(() => {
    setSelectedColumns('default');
    setSelectedDateColumn(dataset?.dateColumns?.[0] || '');
  }, [dataset?.fileName, dataset?.sheetName]);

  const rows = dataset?.rows || [];
  const columns = dataset?.columns || [];
  const dateColumns = dataset?.dateColumns || [];
  const defaultColumns = columns.slice(0, 8);
  const visibleColumns = selectedColumns === 'all'
    ? columns
    : selectedColumns === 'default'
      ? defaultColumns
      : columns.filter((column) => selectedColumns.includes(column));
  const totalPages = Math.ceil((dataset?.totalRows || 0) / PAGE_SIZE);
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;
  const firstShown = dataset?.totalRows ? offset + 1 : 0;
  const lastShown = Math.min(offset + PAGE_SIZE, dataset?.totalRows || 0);
  const pageNumbers = useMemo(() => {
    if (totalPages <= 9) return Array.from({ length: totalPages }, (_, index) => index + 1);
    const start = Math.max(2, Math.min(currentPage - 2, totalPages - 5));
    const middle = Array.from({ length: 5 }, (_, index) => start + index);
    return [...new Set([1, ...middle, totalPages])].sort((a, b) => a - b);
  }, [currentPage, totalPages]);

  return (
    <section className="dataset-page" aria-labelledby="dataset-page-title">
      <header className="dataset-page-header">
        <div>
          <button type="button" className="dataset-back-button" onClick={onBack}>← Back to Deep Dive</button>
          <p className="dataset-eyebrow">{module?.name || 'Module'} / Source Data</p>
          <h1 id="dataset-page-title">{metric?.metric || metric?.metricName || 'Metric'} Dataset</h1>
          <p className="dataset-description">Source data retrieved from the Supabase raw data bucket for this metric.</p>
        </div>
        {dataset?.downloadUrl && <a className="dataset-download-button" href={dataset.downloadUrl}>Download dataset</a>}
      </header>

      <div className="dataset-meta-bar">
        <span><strong>File:</strong> {dataset?.fileName || (loading ? 'Loading…' : '—')}</span>
        {dataset?.sheetName && <span><strong>Sheet:</strong> {dataset.sheetName}</span>}
        {Number.isFinite(dataset?.totalRows) && <span><strong>Rows:</strong> {dataset.totalRows.toLocaleString()}</span>}
      </div>

      <div className="dataset-toolbar">
        <div className="dataset-filter-controls">
          <label>
            Date column
            <select value={selectedDateColumn || dateColumns[0] || ''} onChange={(event) => { setSelectedDateColumn(event.target.value); setOffset(0); }} disabled={!dateColumns.length}>
              {!dateColumns.length && <option value="">No date columns found</option>}
              {dateColumns.map((column) => <option key={column} value={column}>{column}</option>)}
            </select>
          </label>
          <label>
            From month
            <input type="month" value={dateFrom} onChange={(event) => { setDateFrom(event.target.value); setOffset(0); }} disabled={!dateColumns.length} />
          </label>
          <label>
            To month
            <input type="month" value={dateTo} onChange={(event) => { setDateTo(event.target.value); setOffset(0); }} disabled={!dateColumns.length} />
          </label>
          {(dateFrom || dateTo) && <button type="button" className="dataset-clear-filter" onClick={() => { setDateFrom(''); setDateTo(''); setOffset(0); }}>Clear dates</button>}
          <details className="dataset-column-controller">
            <summary>Columns ({visibleColumns.length}/{columns.length})</summary>
            <div className="dataset-column-options">
              <button type="button" onClick={() => setSelectedColumns('all')}>Show all</button>
              <button type="button" onClick={() => setSelectedColumns([])}>Hide all</button>
              {columns.map((column) => (
                <label key={column}>
                  <input
                    type="checkbox"
                    checked={selectedColumns === 'all' || (selectedColumns === 'default' ? defaultColumns.includes(column) : selectedColumns.includes(column))}
                    onChange={(event) => setSelectedColumns((current) => {
                      const base = current === 'all' ? columns : current === 'default' ? defaultColumns : current;
                      const next = new Set(base);
                      if (event.target.checked) next.add(column); else next.delete(column);
                      return Array.from(next);
                    })}
                  />
                  {column}
                </label>
              ))}
            </div>
          </details>
        </div>

        {!loading && !error && totalPages > 0 && (
          <footer className="dataset-pagination dataset-pagination-top">
            <span>Showing {firstShown.toLocaleString()}–{lastShown.toLocaleString()} of {dataset.totalRows.toLocaleString()} rows</span>
            <nav className="dataset-page-list" aria-label="Dataset pages">
              <button type="button" onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))} disabled={currentPage === 1}>Previous</button>
              {pageNumbers.map((page, index) => (
                <span className="dataset-page-item" key={page}>
                  {index > 0 && pageNumbers[index - 1] < page - 1 && <span className="dataset-page-ellipsis" aria-hidden="true">…</span>}
                  <button type="button" className={page === currentPage ? 'active' : ''} aria-current={page === currentPage ? 'page' : undefined} onClick={() => setOffset((page - 1) * PAGE_SIZE)}>{page}</button>
                </span>
              ))}
              <button type="button" onClick={() => setOffset(offset + PAGE_SIZE)} disabled={currentPage >= totalPages}>Next</button>
            </nav>
          </footer>
        )}
      </div>

      <div className="dataset-table-frame">
        {loading ? <div className="dataset-state">Loading dataset from Supabase…</div>
          : error ? <div className="dataset-state dataset-error" role="alert">{error}</div>
            : columns.length === 0 ? <div className="dataset-state">This dataset has no rows to display.</div>
              : (
                <>
                {visibleColumns.length > 8 && (
                  <div className="dataset-horizontal-scroll-hint" aria-hidden="true">
                    <span>↔</span> Scroll horizontally to view all fields
                  </div>
                )}
                <div className={`dataset-table-scroll${visibleColumns.length > 8 ? ' dataset-table-scroll-wide' : ''}`}>
                  <table className={`dataset-table${visibleColumns.length > 8 ? ' dataset-table-wide' : ''}`}>
                    <thead><tr>{visibleColumns.map((column, index) => <th key={`${column}-${index}`}>{column}</th>)}</tr></thead>
                    <tbody>
                      {rows.map((row, rowIndex) => (
                        <tr key={offset + rowIndex}>
                          {visibleColumns.map((column, columnIndex) => (
                            <td key={`${column}-${columnIndex}`}>{formatDatasetCell(row[column])}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                </>
              )}
      </div>

    </section>
  );
}
