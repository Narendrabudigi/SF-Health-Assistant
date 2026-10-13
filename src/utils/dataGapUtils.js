/**
 * Extracts missing field names from a metric.
 *
 * Use getMissingFieldCount() in the Analysis view to show ONLY the count.
 * Use getMissingFields() in the Deep Dive to show the actual field names.
 */

/**
 * Normalize missing fields into a unique array of field-name strings.
 */
function normalizeFields(fields) {
  if (!Array.isArray(fields)) {
    return [];
  }

  return fields
    .map((field) => {
      if (typeof field === 'string') {
        return field.trim();
      }

      if (field && typeof field === 'object') {
        return String(
          field.field ||
          field.fieldName ||
          field.name ||
          field.column ||
          field.columnName ||
          ''
        ).trim();
      }

      return '';
    })
    .filter(Boolean);
}

/**
 * Converts a supported missing-field value into an array.
 */
function parseMissingFields(value) {
  if (Array.isArray(value)) {
    return normalizeFields(value);
  }

  if (typeof value === 'string' && value.trim()) {
    return normalizeFields(value.split(','));
  }

  return [];
}

/**
 * Returns the actual missing field names for a metric.
 *
 * Supports:
 * - missingConfigurations
 * - missingConfiguration
 * - detailedAnalysis.missingConfigurations
 * - dataQuality.missingFields
 * - dataQuality.checks[].affectedColumns for completeness/schema checks only
 *
 * Duplicate field names are removed.
 */
export function getMissingFields(metric) {
  if (!metric || typeof metric !== 'object') {
    return [];
  }

  const fields = [
    ...parseMissingFields(metric.missingConfigurations),
    ...parseMissingFields(metric.missingConfiguration),
    ...parseMissingFields(
      metric.detailedAnalysis?.missingConfigurations
    ),
    ...parseMissingFields(metric.dataQuality?.missingFields)
  ];

  // Some payloads report missing fields in data-quality checks.
  const checks = metric.dataQuality?.checks;

  if (Array.isArray(checks)) {
    checks.forEach((check) => {
      const category = String(check?.category || '').toLowerCase();
      const checkName = String(check?.checkName || check?.name || '').toLowerCase();
      const reportsMissingData =
        ['completeness', 'schema', 'missingvalues'].includes(category) ||
        ['completeness', 'schema', 'missingvalues'].includes(checkName);

      if (reportsMissingData && Array.isArray(check?.affectedColumns)) {
        fields.push(...normalizeFields(check.affectedColumns));
      }
    });
  }

  // Remove duplicate field names without changing their original casing.
  const uniqueFields = new Map();

  fields.forEach((field) => {
    const key = field.toLowerCase().trim();

    if (key && !uniqueFields.has(key)) {
      uniqueFields.set(key, field.trim());
    }
  });

  return Array.from(uniqueFields.values());
}

/**
 * Returns the number of unique missing fields.
 *
 * Use this in the Analysis view.
 */
export function getMissingFieldCount(metric) {
  return getMissingFields(metric).length;
}

export default getMissingFields;
