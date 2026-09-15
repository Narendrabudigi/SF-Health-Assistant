/**
 * Centralized Application Configuration
 * Safely accesses Vite environment variables with fallback defaults
 */
export const APP_CONFIG = {
  appTitle: import.meta.env.VITE_APP_TITLE || 'Success Factors',
  companyName: import.meta.env.VITE_COMPANY_NAME || 'YASH Technologies',
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL || '/api',
  isGenAiStreamingEnabled: import.meta.env.VITE_ENABLE_GENAI_STREAMING === 'true',
  version: '1.0.0'
};
