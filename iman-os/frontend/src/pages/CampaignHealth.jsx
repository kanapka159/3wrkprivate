import { useState } from 'react';
import { PageHeader } from '../components/layout';
import { StatusBadge, SuggestionBadge, Button, LoadingSpinner } from '../components/shared';
import { useApi, useMutation } from '../hooks/useApi';
import { api } from '../utils/api';
import { formatNumber, formatPercent } from '../utils/formatters';

export default function CampaignHealth() {
  const [filter, setFilter] = useState('all');
  const { data, loading, error, execute: refresh } = useApi(
    () => api.getCampaigns({ only_suggestions: filter === 'suggestions' }),
    [filter]
  );
  const { execute: applySuggestion, loading: applying } = useMutation(api.applySuggestion);

  const handleApply = async (campaignId, action) => {
    try {
      await applySuggestion(campaignId, action);
      refresh();
    } catch (err) {
      console.error('Failed to apply action:', err);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  const campaigns = data?.campaigns || [];

  return (
    <div>
      <PageHeader
        title="Campaign Health"
        subtitle={`${campaigns.length} campaigns`}
        actions={
          <div className="flex gap-2">
            <Button
              variant={filter === 'all' ? 'primary' : 'secondary'}
              size="sm"
              onClick={() => setFilter('all')}
            >
              All
            </Button>
            <Button
              variant={filter === 'suggestions' ? 'primary' : 'secondary'}
              size="sm"
              onClick={() => setFilter('suggestions')}
            >
              Needs Action
            </Button>
          </div>
        }
      />

      {error && (
        <div className="bg-danger/20 text-danger p-4 rounded-lg mb-6">
          Error: {error}
        </div>
      )}

      {/* Campaign Table */}
      <div className="bg-card rounded-lg overflow-hidden">
        <table className="w-full">
          <thead className="bg-secondary">
            <tr>
              <th className="text-left px-6 py-4 text-gray-400 text-sm font-medium">Campaign</th>
              <th className="text-left px-6 py-4 text-gray-400 text-sm font-medium">Status</th>
              <th className="text-right px-6 py-4 text-gray-400 text-sm font-medium">Sent</th>
              <th className="text-right px-6 py-4 text-gray-400 text-sm font-medium">Reply Rate</th>
              <th className="text-left px-6 py-4 text-gray-400 text-sm font-medium">Suggestion</th>
              <th className="text-left px-6 py-4 text-gray-400 text-sm font-medium">Warnings</th>
              <th className="text-right px-6 py-4 text-gray-400 text-sm font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {campaigns.length === 0 ? (
              <tr>
                <td colSpan="7" className="px-6 py-12 text-center text-gray-500">
                  No campaigns found. Run a sync to fetch campaigns.
                </td>
              </tr>
            ) : (
              campaigns.map((campaign) => (
                <tr key={campaign.id} className="border-t border-gray-800 hover:bg-secondary/30">
                  <td className="px-6 py-4">
                    <div className="font-medium text-white">{campaign.name}</div>
                    <div className="text-sm text-gray-500">{campaign.client_name || 'No client'}</div>
                  </td>
                  <td className="px-6 py-4">
                    <StatusBadge status={campaign.status} />
                  </td>
                  <td className="px-6 py-4 text-right text-white">
                    {formatNumber(campaign.stats?.sent_count || 0)}
                  </td>
                  <td className="px-6 py-4 text-right">
                    <span className={campaign.stats?.reply_rate >= 2 ? 'text-success' : campaign.stats?.reply_rate >= 1 ? 'text-warning' : 'text-danger'}>
                      {formatPercent(campaign.stats?.reply_rate || 0)}
                    </span>
                  </td>
                  <td className="px-6 py-4">
                    {campaign.suggestion && (
                      <SuggestionBadge
                        suggestion={campaign.suggestion.suggestion}
                        color={campaign.suggestion.color}
                      />
                    )}
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex flex-wrap gap-1">
                      {campaign.warnings?.map((warning, i) => (
                        <span key={i} className="text-xs bg-warning/20 text-warning px-2 py-0.5 rounded">
                          {warning}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="px-6 py-4 text-right">
                    {campaign.suggestion?.color === 'red' && campaign.status === 'STARTED' && (
                      <Button
                        size="sm"
                        variant="danger"
                        onClick={() => handleApply(campaign.id, 'STOP')}
                        disabled={applying}
                      >
                        Stop
                      </Button>
                    )}
                    {campaign.suggestion?.color === 'orange' && campaign.status === 'STARTED' && (
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => handleApply(campaign.id, 'PAUSE')}
                        disabled={applying}
                      >
                        Pause
                      </Button>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
