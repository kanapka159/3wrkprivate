// Backend API URL - hardcoded for Railway deployment
// Always ensure HTTPS to avoid mixed content errors
let BASE_URL = import.meta.env.VITE_API_URL || 'https://3wrkprivate-production.up.railway.app/api';
if (BASE_URL.startsWith('http://')) {
  BASE_URL = BASE_URL.replace('http://', 'https://');
}

async function request(endpoint, options = {}) {
  const url = `${BASE_URL}${endpoint}`;

  const config = {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  };

  const response = await fetch(url, config);

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  return response.json();
}

export const api = {
  // Campaigns
  getCampaigns: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return request(`/campaigns${query ? `?${query}` : ''}`);
  },

  getCampaign: (id) => request(`/campaigns/${id}`),

  updateCampaignStatus: (campaignId, status) =>
    request(`/campaigns/${campaignId}/status?status=${status}`, { method: 'POST' }),

  // Stats
  getOverview: (days = 7) => request(`/stats/overview?days=${days}`),

  // Sync
  triggerSync: () => request('/sync', { method: 'POST' }),
  getSyncStatus: () => request('/sync/status'),

  // Suggestions
  getSuggestions: () => request('/suggestions'),
  applySuggestion: (campaignId, action) =>
    request(`/suggestions/${campaignId}/apply?action=${action}`, { method: 'POST' }),

  // Health
  getHealth: () => request('/health'),
};

export default api;
