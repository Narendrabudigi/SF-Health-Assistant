/** Normalize unit words for UI labels without changing the source values. */
export function formatDisplayUnits(value) {
  if (typeof value !== 'string') return value;

  return value
    .replace(/\s*\bpercent(?:age)?s?\b/gi, '%')
    .replace(/\bdays?\b/gi, (match) =>
      match.toLowerCase().endsWith('s') ? 'Days' : 'Day'
    );
}

/** Format numeric variance for display without changing the fetched source value. */
export function formatVarianceDisplay(value) {
  if (typeof value === 'number' && Number.isFinite(value)) return value.toFixed(2);
  if (typeof value !== 'string' || !value.trim()) return value;
  if (/data\s*gap|not yet fetched|on target/i.test(value)) return formatDisplayUnits(value);
  return formatDisplayUnits(value.replace(/[-+]?\d*\.?\d+/g, (number) => {
    const parsed = Number(number);
    return Number.isFinite(parsed) ? parsed.toFixed(2) : number;
  }));
}
