import { useState, useEffect, useMemo } from 'react';
import { BarChart3, Activity, AlertTriangle, Clock, ChevronDown } from 'lucide-react';
import { PageHeader } from '../components/layout';
import {
  StatsCard,
  StatusBadge,
  SuggestionBadge,
  WarningBadge,
  FilterBar,
  Button,
  LoadingSpinner,
} from '../components/shared';
import { useApi, useMutation } from '../hooks/useApi';
import { api } from '../utils/api';
import { formatNumber, formatPercent, timeAgo } from '../utils/formatters';

// Rate color helper
function getRateColor(rate) {
  if (rate >= 2) return 'text-success';
  if (rate >= 1) return 'text-warning';
  if (rate >= 0.5) return 'text-accent';
  return 'text-danger';
}

// Status dropdown component
function StatusDropdown({ status, campaignId, onStatusChange, disabled }) {
  const [isOpen, setIsOpen] = useState(false);

  const handleChange = async (newStatus) => {
    setIsOpen(false);
    if (newStatus !== status) {
      await onStatusChange(campaignId, newStatus);
    }
  };

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        disabled={disabled}
        className="flex items-center gap-1 disabled:opacity-50"
      >
        <StatusBadge status={status} />
        <ChevronDown size={14} className="text-gray-500" />
      </button>
      {isOpen && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setIsOpen(false)} />
          <div className="absolute top-full left-0 mt-1 bg-secondary border border-gray-700 rounded-lg shadow-lg z-20 py-1 min-w-[120px]">
            {['STARTED', 'PAUSED', 'STOPPED'].map((s) => (
              <button
                key={s}
                onClick={() => handleChange(s)}
                className="w-full px-3 py-2 text-left text-sm hover:bg-card transition-colors flex items-center gap-2"
              >
                <StatusBadge status={s} />
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

export default function CampaignHealth() {
  // State
  const [search, setSearch] = useState('');
  const [clientFilter, setClientFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [onlySuggestions, setOnlySuggestions] = useState(false);

  // API calls
  const {
    data: campaignsData,
    loading: campaignsLoading,
    error: campaignsError,
    execute: refreshCampaigns,
  } = useApi(() => api.getCampaigns({ only_suggestions: onlySuggestions }), [onlySuggestions]);

  const { data: overviewData, execute: refreshOverview } = useApi(
    () => api.getOverview(7),
    []
  );

  const { data: syncStatus, execute: refreshSyncStatus } = useApi(api.getSyncStatus, []);

  const { execute: triggerSync, loading: syncing } = useMutation(api.triggerSync);
  const { execute: applySuggestion, loading: applying } = useMutation(api.applySuggestion);
  const { execute: updateStatus, loading: updatingStatus } = useMutation(
    (campaignId, status) => api.updateCampaignStatus(campaignId, status)
  );

  // Refresh all data
  const handleRefresh = async () => {
    try {
      await triggerSync();
      await Promise.all([refreshCampaigns(), refreshOverview(), refreshSyncStatus()]);
    } catch (err) {
      console.error('Sync failed:', err);
    }
  };

  // Run analytics (same as refresh for now)
  const handleRunAnalytics = async () => {
    await handleRefresh();
  };

  // Apply suggestion
  const handleApply = async (campaignId, action) => {
    try {
      await applySuggestion(campaignId, action);
      await refreshCampaigns();
    } catch (err) {
      console.error('Failed to apply:', err);
    }
  };

  // Change status
  const handleStatusChange = async (campaignId, newStatus) => {
    try {
      await updateStatus(campaignId, newStatus);
      await refreshCampaigns();
    } catch (err) {
      console.error('Failed to update status:', err);
    }
  };

  // Filter campaigns
  const filteredCampaigns = useMemo(() => {
    let result = campaignsData?.campaigns || [];

    if (search) {
      const searchLower = search.toLowerCase();
      result = result.filter(
        (c) =>
          c.name?.toLowerCase().includes(searchLower) ||
          c.client_name?.toLowerCase().includes(searchLower)
      );
    }

    if (clientFilter) {
      result = result.filter((c) => String(c.client_id) === clientFilter);
    }

    if (statusFilter) {
      result = result.filter((c) => c.status === statusFilter);
    }

    return result;
  }, [campaignsData, search, clientFilter, statusFilter]);

  // Get unique clients for filter dropdown
  const clients = useMemo(() => {
    const clientMap = new Map();
    (campaignsData?.campaigns || []).forEach((c) => {
      if (c.client_id && c.client_name) {
        clientMap.set(c.client_id, { id: c.client_id, name: c.client_name });
      }
    });
    return Array.from(clientMap.values());
  }, [campaignsData]);

  // Stats calculations
  const stats = useMemo(() => {
    const campaigns = campaignsData?.campaigns || [];
    return {
      total: campaigns.length,
      active: campaigns.filter((c) => c.status === 'STARTED').length,
      withSuggestions: campaigns.filter(
        (c) => c.suggestion?.color && c.suggestion.color !== 'green'
      ).length,
      lowData: campaigns.filter((c) => (c.stats?.sent_count || 0) < 200).length,
    };
  }, [campaignsData]);

  const isLoading = campaignsLoading || syncing;

  return (
    <div>
      {/* Header */}
      <PageHeader
        title="Campaign Health"
        subtitle="Monitor and manage campaign performance"
      />

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <StatsCard
          title="Total Campaigns"
          value={stats.total}
          icon={BarChart3}
        />
        <StatsCard
          title="Active"
          value={stats.active}
          subtitle="currently running"
          icon={Activity}
        />
        <StatsCard
          title="With Suggestions"
          value={stats.withSuggestions}
          subtitle="need attention"
          icon={AlertTriangle}
        />
        <StatsCard
          title="Under 200 Sends"
          value={stats.lowData}
          subtitle="low data"
          icon={Clock}
        />
      </div>

      {/* Filter Bar */}
      <FilterBar
        search={search}
        onSearchChange={setSearch}
        clients={clients}
        clientFilter={clientFilter}
        onClientFilterChange={setClientFilter}
        statusFilter={statusFilter}
        onStatusFilterChange={setStatusFilter}
        onlySuggestions={onlySuggestions}
        onOnlySuggestionsChange={setOnlySuggestions}
        lastSync={timeAgo(syncStatus?.last_sync?.completed_at)}
        onRefresh={handleRefresh}
        onRunAnalytics={handleRunAnalytics}
        isLoading={isLoading}
      />

      {/* Error State */}
      {campaignsError && (
        <div className="bg-danger/20 text-danger p-4 rounded-lg mb-6">
          Error loading campaigns: {campaignsError}
        </div>
      )}

      {/* Data Table */}
      <div className="bg-card rounded-lg overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-secondary">
              <tr>
                <th className="text-left px-4 py-3 text-gray-400 text-xs font-medium uppercase tracking-wider">Campaign</th>
                <th className="text-left px-4 py-3 text-gray-400 text-xs font-medium uppercase tracking-wider">Client</th>
                <th className="text-left px-4 py-3 text-gray-400 text-xs font-medium uppercase tracking-wider">Status</th>
                <th className="text-left px-4 py-3 text-gray-400 text-xs font-medium uppercase tracking-wider">Suggested</th>
                <th className="text-right px-4 py-3 text-gray-400 text-xs font-medium uppercase tracking-wider">7D Sent</th>
                <th className="text-right px-4 py-3 text-gray-400 text-xs font-medium uppercase tracking-wider">7D Rate</th>
                <th className="text-right px-4 py-3 text-gray-400 text-xs font-medium uppercase tracking-wider">14D Sent</th>
                <th className="text-right px-4 py-3 text-gray-400 text-xs font-medium uppercase tracking-wider">14D Rate</th>
                <th className="text-right px-4 py-3 text-gray-400 text-xs font-medium uppercase tracking-wider">28D Rate</th>
                <th className="text-right px-4 py-3 text-gray-400 text-xs font-medium uppercase tracking-wider">Pos Rate</th>
                <th className="text-left px-4 py-3 text-gray-400 text-xs font-medium uppercase tracking-wider">Warnings</th>
                <th className="text-left px-4 py-3 text-gray-400 text-xs font-medium uppercase tracking-wider">Last Sync</th>
                <th className="text-right px-4 py-3 text-gray-400 text-xs font-medium uppercase tracking-wider">Action</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr>
                  <td colSpan="13" className="px-4 py-12 text-center">
                    <LoadingSpinner size="lg" />
                  </td>
                </tr>
              ) : filteredCampaigns.length === 0 ? (
                <tr>
                  <td colSpan="13" className="px-4 py-12 text-center text-gray-500">
                    No campaigns found. Run a sync to fetch campaigns from Smartlead.
                  </td>
                </tr>
              ) : (
                filteredCampaigns.map((campaign) => {
                  const stats = campaign.stats || {};
                  const suggestion = campaign.suggestion || {};
                  const periods = campaign.periods || {};

                  return (
                    <tr
                      key={campaign.id}
                      className="border-t border-gray-800 hover:bg-secondary/30 transition-colors"
                    >
                      {/* Campaign Name */}
                      <td className="px-4 py-3">
                        <div className="font-medium text-white text-sm truncate max-w-[200px]" title={campaign.name}>
                          {campaign.name}
                        </div>
                      </td>

                      {/* Client */}
                      <td className="px-4 py-3">
                        <span className="text-gray-400 text-sm">
                          {campaign.client_name || '-'}
                        </span>
                      </td>

                      {/* Status with dropdown */}
                      <td className="px-4 py-3">
                        <StatusDropdown
                          status={campaign.status}
                          campaignId={campaign.id}
                          onStatusChange={handleStatusChange}
                          disabled={updatingStatus}
                        />
                      </td>

                      {/* Suggestion */}
                      <td className="px-4 py-3">
                        {suggestion.suggestion ? (
                          <SuggestionBadge
                            suggestion={suggestion.suggestion}
                            color={suggestion.color}
                          />
                        ) : (
                          <span className="text-gray-600">-</span>
                        )}
                      </td>

                      {/* 7D Sent */}
                      <td className="px-4 py-3 text-right">
                        <span className="text-white text-sm">
                          {formatNumber(periods['7_days']?.sent_count || stats.sent_count || 0)}
                        </span>
                      </td>

                      {/* 7D Rate */}
                      <td className="px-4 py-3 text-right">
                        <span className={`text-sm font-medium ${getRateColor(periods['7_days']?.reply_rate || stats.reply_rate || 0)}`}>
                          {formatPercent(periods['7_days']?.reply_rate || stats.reply_rate || 0)}
                        </span>
                      </td>

                      {/* 14D Sent */}
                      <td className="px-4 py-3 text-right">
                        <span className="text-white text-sm">
                          {formatNumber(periods['14_days']?.sent_count || stats.sent_count || 0)}
                        </span>
                      </td>

                      {/* 14D Rate */}
                      <td className="px-4 py-3 text-right">
                        <span className={`text-sm font-medium ${getRateColor(periods['14_days']?.reply_rate || stats.reply_rate || 0)}`}>
                          {formatPercent(periods['14_days']?.reply_rate || stats.reply_rate || 0)}
                        </span>
                      </td>

                      {/* 28D Rate */}
                      <td className="px-4 py-3 text-right">
                        <span className={`text-sm font-medium ${getRateColor(periods['28_days']?.reply_rate || stats.reply_rate || 0)}`}>
                          {formatPercent(periods['28_days']?.reply_rate || stats.reply_rate || 0)}
                        </span>
                      </td>

                      {/* Positive Rate */}
                      <td className="px-4 py-3 text-right">
                        <span className="text-gray-400 text-sm">
                          {formatPercent(stats.positive_rate || 0)}
                        </span>
                      </td>

                      {/* Warnings */}
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap gap-1">
                          {campaign.warnings?.length > 0 ? (
                            campaign.warnings.map((warning, i) => (
                              <WarningBadge key={i} text={warning} />
                            ))
                          ) : (
                            <span className="text-gray-600">-</span>
                          )}
                        </div>
                      </td>

                      {/* Last Sync */}
                      <td className="px-4 py-3">
                        <span className="text-gray-500 text-sm">
                          {timeAgo(campaign.last_synced_at)}
                        </span>
                      </td>

                      {/* Action */}
                      <td className="px-4 py-3 text-right">
                        {suggestion.color && suggestion.color !== 'green' && suggestion.color !== 'gray' && (
                          <Button
                            size="sm"
                            variant={suggestion.color === 'red' ? 'danger' : 'secondary'}
                            onClick={() => handleApply(campaign.id, suggestion.suggestion === 'KILL' ? 'STOP' : 'PAUSE')}
                            disabled={applying}
                          >
                            + Apply
                          </Button>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Footer info */}
      <div className="mt-4 text-sm text-gray-500 text-right">
        Showing {filteredCampaigns.length} of {campaignsData?.campaigns?.length || 0} campaigns
      </div>
    </div>
  );
}
