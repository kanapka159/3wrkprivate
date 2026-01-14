import { useState, useMemo } from 'react';
import { BarChart3, Activity, AlertTriangle, Clock, ChevronDown, Minus, Plus, Eye, EyeOff, RefreshCw } from 'lucide-react';
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

// Check if campaign is a follow-up/subsequence
function isFollowUpCampaign(campaign) {
  const name = (campaign.name || '').toLowerCase();
  return name.includes('follow up') || name.includes('follow-up') || name.includes('followup');
}

// Top loading banner component
function SyncingBanner({ isVisible }) {
  if (!isVisible) return null;

  return (
    <div className="fixed top-0 left-0 right-0 z-50 bg-accent/90 text-white py-2 px-4 flex items-center justify-center gap-3 shadow-lg">
      <RefreshCw size={18} className="animate-spin" />
      <span className="font-medium">Syncing campaigns...</span>
    </div>
  );
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

// Reusable Campaign Table component
function CampaignTable({
  campaigns,
  isInitialLoading,
  onStatusChange,
  onApply,
  onToggleHide,
  updatingStatus,
  applying,
  hidingId,
  emptyMessage = "No campaigns found.",
  showUnhide = false,
}) {
  // Only show full loading spinner on initial load (no data yet)
  const showLoadingSpinner = isInitialLoading && campaigns.length === 0;

  return (
    <div className="bg-card rounded-lg overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead className="bg-secondary">
            <tr>
              <th className="w-8 px-2 py-3"></th>
              <th className="text-left px-4 py-3 text-gray-400 text-xs font-medium uppercase tracking-wider">Campaign</th>
              <th className="text-left px-4 py-3 text-gray-400 text-xs font-medium uppercase tracking-wider">Created</th>
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
            {showLoadingSpinner ? (
              <tr>
                <td colSpan="14" className="px-4 py-12 text-center">
                  <LoadingSpinner size="lg" />
                </td>
              </tr>
            ) : campaigns.length === 0 ? (
              <tr>
                <td colSpan="14" className="px-4 py-12 text-center text-gray-500">
                  {emptyMessage}
                </td>
              </tr>
            ) : (
              campaigns.map((campaign) => {
                const stats = campaign.stats || {};
                const suggestion = campaign.suggestion || {};
                const periods = campaign.periods || {};

                // Format created date
                const createdDate = campaign.created_at
                  ? new Date(campaign.created_at).toLocaleDateString('en-US', {
                      month: 'short',
                      day: 'numeric',
                      year: 'numeric'
                    })
                  : '-';

                return (
                  <tr
                    key={campaign.id}
                    className="border-t border-gray-800 hover:bg-secondary/30 transition-colors group"
                  >
                    {/* Hide/Unhide Button */}
                    <td className="px-2 py-3">
                      <button
                        onClick={() => onToggleHide(campaign.id)}
                        disabled={hidingId === campaign.id}
                        className={`
                          w-6 h-6 flex items-center justify-center rounded
                          transition-all duration-200
                          ${showUnhide
                            ? 'text-gray-400 hover:text-success hover:bg-success/20'
                            : 'text-gray-700 opacity-0 group-hover:opacity-100 hover:text-danger hover:bg-danger/20'
                          }
                          disabled:opacity-50 disabled:cursor-not-allowed
                        `}
                        title={showUnhide ? 'Unhide campaign' : 'Hide campaign'}
                      >
                        {hidingId === campaign.id ? (
                          <LoadingSpinner size="sm" />
                        ) : showUnhide ? (
                          <Plus size={14} />
                        ) : (
                          <Minus size={14} />
                        )}
                      </button>
                    </td>

                    {/* Campaign Name */}
                    <td className="px-4 py-3">
                      <div className="font-medium text-white text-sm truncate max-w-[200px]" title={campaign.name}>
                        {campaign.name}
                      </div>
                    </td>

                    {/* Created Date */}
                    <td className="px-4 py-3">
                      <span className="text-gray-400 text-sm">
                        {createdDate}
                      </span>
                    </td>

                    {/* Status with dropdown */}
                    <td className="px-4 py-3">
                      <StatusDropdown
                        status={campaign.status}
                        campaignId={campaign.id}
                        onStatusChange={onStatusChange}
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
                        {formatNumber(periods['14_days']?.sent_count || 0)}
                      </span>
                    </td>

                    {/* 14D Rate */}
                    <td className="px-4 py-3 text-right">
                      <span className={`text-sm font-medium ${getRateColor(periods['14_days']?.reply_rate || 0)}`}>
                        {formatPercent(periods['14_days']?.reply_rate || 0)}
                      </span>
                    </td>

                    {/* 28D Rate */}
                    <td className="px-4 py-3 text-right">
                      <span className={`text-sm font-medium ${getRateColor(periods['28_days']?.reply_rate || 0)}`}>
                        {formatPercent(periods['28_days']?.reply_rate || 0)}
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
                          onClick={() => onApply(campaign.id, suggestion.suggestion === 'KILL' ? 'STOP' : 'PAUSE')}
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
  );
}

export default function CampaignHealth() {
  // State
  const [search, setSearch] = useState('');
  const [clientFilter, setClientFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [onlySuggestions, setOnlySuggestions] = useState(false);
  const [showHidden, setShowHidden] = useState(false);
  const [hidingId, setHidingId] = useState(null);
  const [hasLoadedOnce, setHasLoadedOnce] = useState(false);

  // API calls
  const {
    data: campaignsData,
    loading: campaignsLoading,
    error: campaignsError,
    execute: refreshCampaigns,
  } = useApi(() => api.getCampaigns({ only_suggestions: onlySuggestions }), [onlySuggestions]);

  // Track when data has loaded at least once
  if (campaignsData && !hasLoadedOnce) {
    setHasLoadedOnce(true);
  }

  // Fetch hidden campaigns
  const {
    data: hiddenCampaignsData,
    loading: hiddenLoading,
    execute: refreshHiddenCampaigns,
  } = useApi(() => api.getHiddenCampaigns(), []);

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
  const { execute: toggleHidden } = useMutation(api.toggleCampaignHidden);

  // Determine loading states
  const isInitialLoading = campaignsLoading && !hasLoadedOnce;
  const isSyncing = syncing || (campaignsLoading && hasLoadedOnce);

  // Refresh all data
  const handleRefresh = async () => {
    try {
      await triggerSync();
      await Promise.all([refreshCampaigns(), refreshOverview(), refreshSyncStatus(), refreshHiddenCampaigns()]);
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

  // Toggle hide campaign
  const handleToggleHide = async (campaignId) => {
    try {
      setHidingId(campaignId);
      await toggleHidden(campaignId);
      await Promise.all([refreshCampaigns(), refreshHiddenCampaigns()]);
    } catch (err) {
      console.error('Failed to toggle hide:', err);
    } finally {
      setHidingId(null);
    }
  };

  // Filter and separate campaigns
  const { regularCampaigns, followUpCampaigns } = useMemo(() => {
    let result = campaignsData?.campaigns || [];

    // Apply search filter
    if (search) {
      const searchLower = search.toLowerCase();
      result = result.filter(
        (c) =>
          c.name?.toLowerCase().includes(searchLower) ||
          c.client_name?.toLowerCase().includes(searchLower)
      );
    }

    // Apply client filter
    if (clientFilter) {
      result = result.filter((c) => String(c.client_id) === clientFilter);
    }

    // Apply status filter
    if (statusFilter) {
      result = result.filter((c) => c.status === statusFilter);
    }

    // Separate into regular and follow-up campaigns
    const regular = result.filter((c) => !isFollowUpCampaign(c));
    const followUp = result.filter((c) => isFollowUpCampaign(c));

    return { regularCampaigns: regular, followUpCampaigns: followUp };
  }, [campaignsData, search, clientFilter, statusFilter]);

  // Filter hidden campaigns
  const { hiddenRegularCampaigns, hiddenFollowUpCampaigns } = useMemo(() => {
    const hidden = hiddenCampaignsData?.campaigns || [];
    return {
      hiddenRegularCampaigns: hidden.filter((c) => !isFollowUpCampaign(c)),
      hiddenFollowUpCampaigns: hidden.filter((c) => isFollowUpCampaign(c)),
    };
  }, [hiddenCampaignsData]);

  const totalHidden = (hiddenCampaignsData?.campaigns || []).length;

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
    const regular = campaigns.filter((c) => !isFollowUpCampaign(c));
    return {
      total: regular.length,
      active: regular.filter((c) => c.status === 'STARTED').length,
      withSuggestions: regular.filter(
        (c) => c.suggestion?.color && c.suggestion.color !== 'green'
      ).length,
      lowData: regular.filter((c) => (c.stats?.sent_count || 0) < 200).length,
      followUps: campaigns.filter((c) => isFollowUpCampaign(c)).length,
    };
  }, [campaignsData]);

  return (
    <div>
      {/* Syncing Banner - shows at top when refreshing */}
      <SyncingBanner isVisible={isSyncing} />

      {/* Header */}
      <PageHeader
        title="Campaign Health"
        subtitle="Monitor and manage campaign performance"
      />

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4 mb-6">
        <StatsCard
          title="Main Campaigns"
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
        <StatsCard
          title="Follow-ups"
          value={stats.followUps}
          subtitle="subsequences"
          icon={Activity}
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
        isLoading={isSyncing}
      />

      {/* Error State */}
      {campaignsError && (
        <div className="bg-danger/20 text-danger p-4 rounded-lg mb-6">
          Error loading campaigns: {campaignsError}
        </div>
      )}

      {/* Main Campaigns Table */}
      <div className="mb-4">
        <h2 className="text-xl font-bold text-white mb-4">Main Campaigns</h2>
        <CampaignTable
          campaigns={regularCampaigns}
          isInitialLoading={isInitialLoading}
          onStatusChange={handleStatusChange}
          onApply={handleApply}
          onToggleHide={handleToggleHide}
          updatingStatus={updatingStatus}
          applying={applying}
          hidingId={hidingId}
          emptyMessage="No main campaigns found. Run a sync to fetch campaigns from Smartlead."
        />
      </div>

      {/* Footer info for main campaigns */}
      <div className="mb-8 text-sm text-gray-500 text-right">
        Showing {regularCampaigns.length} main campaigns
      </div>

      {/* Divider */}
      <div className="border-t-4 border-accent my-10"></div>

      {/* Follow-up / Subsequences Section */}
      <div className="mb-4">
        <h2 className="text-3xl font-bold text-accent mb-2">FOLLOW-UP CAMPAIGNS</h2>
        <p className="text-gray-400 mb-4">Subsequence campaigns for lead nurturing</p>
        <CampaignTable
          campaigns={followUpCampaigns}
          isInitialLoading={isInitialLoading}
          onStatusChange={handleStatusChange}
          onApply={handleApply}
          onToggleHide={handleToggleHide}
          updatingStatus={updatingStatus}
          applying={applying}
          hidingId={hidingId}
          emptyMessage="No follow-up campaigns found."
        />
      </div>

      {/* Footer info for follow-up campaigns */}
      <div className="mt-4 text-sm text-gray-500 text-right">
        Showing {followUpCampaigns.length} follow-up campaigns
      </div>

      {/* Hidden Campaigns Section */}
      {totalHidden > 0 && (
        <>
          <div className="border-t-2 border-gray-700 my-10"></div>

          <div className="mb-4">
            <button
              onClick={() => setShowHidden(!showHidden)}
              className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors"
            >
              {showHidden ? <EyeOff size={20} /> : <Eye size={20} />}
              <span className="text-lg font-medium">
                {showHidden ? 'Hide' : 'Show'} Hidden Campaigns ({totalHidden})
              </span>
            </button>
          </div>

          {showHidden && (
            <>
              {/* Hidden Main Campaigns */}
              {hiddenRegularCampaigns.length > 0 && (
                <div className="mb-8">
                  <h3 className="text-lg font-semibold text-gray-400 mb-4">Hidden Main Campaigns</h3>
                  <CampaignTable
                    campaigns={hiddenRegularCampaigns}
                    isInitialLoading={hiddenLoading && hiddenRegularCampaigns.length === 0}
                    onStatusChange={handleStatusChange}
                    onApply={handleApply}
                    onToggleHide={handleToggleHide}
                    updatingStatus={updatingStatus}
                    applying={applying}
                    hidingId={hidingId}
                    emptyMessage="No hidden main campaigns."
                    showUnhide={true}
                  />
                </div>
              )}

              {/* Hidden Follow-up Campaigns */}
              {hiddenFollowUpCampaigns.length > 0 && (
                <div className="mb-4">
                  <h3 className="text-lg font-semibold text-gray-400 mb-4">Hidden Follow-up Campaigns</h3>
                  <CampaignTable
                    campaigns={hiddenFollowUpCampaigns}
                    isInitialLoading={hiddenLoading && hiddenFollowUpCampaigns.length === 0}
                    onStatusChange={handleStatusChange}
                    onApply={handleApply}
                    onToggleHide={handleToggleHide}
                    updatingStatus={updatingStatus}
                    applying={applying}
                    hidingId={hidingId}
                    emptyMessage="No hidden follow-up campaigns."
                    showUnhide={true}
                  />
                </div>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}
