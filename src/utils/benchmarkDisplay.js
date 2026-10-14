/** Remove a leading comparator from a benchmark label for display only. */
export function formatBenchmarkDisplay(value) {
  if (typeof value !== 'string') return value;

  return value
    .trim()
    .replace(
      /^\s*(?:(?:greater\s+than(?:\s+or\s+equal\s+to)?|less\s+than(?:\s+or\s+equal\s+to)?|at\s+least|at\s+most)\s*|(?:>=|<=|=>|=<|≥|≤|≧|≦|>|<|=)\s*)/i,
      ''
    )
    .trim();
}
