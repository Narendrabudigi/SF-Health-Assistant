/** Normalize unit words for UI labels without changing the source values. */
export function formatDisplayUnits(value) {
  if (typeof value !== 'string') return value;

  return value
    .replace(/\bpercent(?:age)?s?\b/gi, (match) =>
      match.toLowerCase().endsWith('s') ? 'Percentages' : 'Percentage'
    )
    .replace(/\bdays?\b/gi, (match) =>
      match.toLowerCase().endsWith('s') ? 'Days' : 'Day'
    );
}
