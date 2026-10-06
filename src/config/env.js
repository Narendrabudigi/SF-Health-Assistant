/**
 * Centralized Application Configuration
 * Safely accesses Vite environment variables with fallback defaults
 */
export const APP_CONFIG = {
  appTitle: import.meta.env.VITE_APP_TITLE || 'Success Factors',
  companyName: import.meta.env.VITE_COMPANY_NAME || 'YASH Technologies',
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1',
  supabaseUrl: import.meta.env.VITE_SUPABASE_URL || 'https://hwlqhakrpontqepzzbpe.supabase.co',
  supabaseKey: import.meta.env.VITE_SUPABASE_KEY || 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imh3bHFoYWtycG9udHFlcHp6YnBlIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4OTU1MTAyMywiZXhwIjoyMTA1MTI3MDIzfQ.UdAepgvtxyw6iKwP2pjndbe94IJNAXKRY0YxnPTJMJs',
  supabaseBucket: import.meta.env.VITE_SUPABASE_BUCKET || 'Insights and Reports',
  isGenAiStreamingEnabled: import.meta.env.VITE_ENABLE_GENAI_STREAMING === 'true',
  version: '1.0.0'
};
