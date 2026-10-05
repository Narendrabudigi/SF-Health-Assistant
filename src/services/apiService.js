import { APP_CONFIG } from '../config/env';
import { SF_MODULES } from '../data/modulesData';

const BASE_URL = APP_CONFIG.apiBaseUrl || 'http://localhost:8000/api/v1';

/**
 * Helper to execute fetch with timeout
 */
async function fetchWithTimeout(resource, options = {}, timeoutMs = 8000) {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(resource, {
      ...options,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...(options.headers || {})
      }
    });
    clearTimeout(id);
    return response;
  } catch (error) {
    clearTimeout(id);
    throw error;
  }
}

export const apiService = {
  /**
   * Check if backend service is reachable
   */
  async checkHealth() {
    try {
      const rootUrl = BASE_URL.replace('/api/v1', '');
      const res = await fetchWithTimeout(`${rootUrl}/health`, { method: 'GET' }, 3000);
      if (!res.ok) return false;
      const data = await res.json();
      return data.status === 'HEALTHY' || data.status === 'ok';
    } catch {
      return false;
    }
  },

  /**
   * Fetch all modules and enrich with detailed benchmarks
   */
  async getModules() {
    try {
      const res = await fetchWithTimeout(`${BASE_URL}/modules`, { method: 'GET' });
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: Failed to fetch modules`);
      }
      const moduleTiles = await res.json();

      // Concurrently fetch benchmarks for each module to populate the detail views
      const enrichedModules = await Promise.all(
        moduleTiles.map(async (tile) => {
          try {
            const detailRes = await fetchWithTimeout(`${BASE_URL}/modules/${tile.id}`, { method: 'GET' }, 4000);
            if (detailRes.ok) {
              const detailData = await detailRes.json();
              return {
                ...tile,
                benchmarks: detailData.benchmarks || [],
                aiReport: {
                  summary: detailData.aiReportSummary || tile.description
                }
              };
            }
          } catch (e) {
            console.warn(`Could not load detailed benchmarks for ${tile.id}, using fallback`, e);
          }
          // Fallback to local module benchmarks if available
          const localMatch = SF_MODULES.find((m) => m.id === tile.id);
          return {
            ...tile,
            benchmarks: localMatch?.benchmarks || [],
            aiReport: localMatch?.aiReport || { summary: tile.description }
          };
        })
      );

      return enrichedModules;
    } catch (err) {
      console.warn('Backend unavailable, falling back to local dataset:', err.message);
      return SF_MODULES;
    }
  },

  /**
   * Fetch a single module by ID
   */
  async getModuleDetails(moduleId) {
    try {
      const res = await fetchWithTimeout(`${BASE_URL}/modules/${moduleId}`, { method: 'GET' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch (err) {
      console.warn(`Failed to fetch module ${moduleId} from API:`, err.message);
      return SF_MODULES.find((m) => m.id === moduleId) || null;
    }
  },

  /**
   * Fetch 9-section BRD deep dive and TreeSHAP insights for a specific metric
   */
  async getMetricDeepDive(metricCode) {
    try {
      const res = await fetchWithTimeout(`${BASE_URL}/metrics/${metricCode}/deep-dive`, { method: 'GET' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch (err) {
      console.warn(`Failed to fetch deep dive for ${metricCode}:`, err.message);
      return null;
    }
  },

  /**
   * Test SAP SuccessFactors OData handshake
   */
  async testConnection({ datacenter, companyId, username, password, clientId, clientSecret }) {
    const res = await fetchWithTimeout(`${BASE_URL}/connect/test`, {
      method: 'POST',
      body: JSON.stringify({
        datacenter,
        companyId,
        username,
        password: password || '',
        clientId: clientId || '',
        clientSecret: clientSecret || ''
      })
    });
    if (!res.ok) {
      const errJson = await res.json().catch(() => ({}));
      throw new Error(errJson.detail || `Connection test failed (HTTP ${res.status})`);
    }
    return await res.json();
  },

  /**
   * Upload custom standards map to backend
   */
  async uploadCustomStandards(standardsMap, uploadedBy = 'enterprise_admin') {
    const res = await fetchWithTimeout(`${BASE_URL}/standards/upload`, {
      method: 'POST',
      body: JSON.stringify({
        standards: standardsMap,
        uploadedBy
      })
    });
    if (!res.ok) {
      const errJson = await res.json().catch(() => ({}));
      throw new Error(errJson.detail || `Upload failed (HTTP ${res.status})`);
    }
    return await res.json();
  },

  /**
   * Trigger Analytics & ML calculation pipeline
   */
  async triggerMlPipeline(moduleId = null, forceRefreshAllLlms = false) {
    try {
      const res = await fetchWithTimeout(`${BASE_URL}/pipeline/trigger-ml-run`, {
        method: 'POST',
        body: JSON.stringify({
          module_id: moduleId,
          force_refresh_all_llms: forceRefreshAllLlms
        })
      }, 2500);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch (err) {
      console.warn('Backend ML trigger fallback to simulated pipeline:', err.message);
      return { status: 'success', simulated: true };
    }
  }
};

export default apiService;
