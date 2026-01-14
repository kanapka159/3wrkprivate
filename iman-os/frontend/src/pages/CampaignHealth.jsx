import { useState, useMemo } from 'react';
import { BarChart3, Activity, AlertTriangle, Clock, ChevronDown, ChevronUp, Minus, Plus, Eye, EyeOff, RefreshCw } from 'lucide-react';
import { PageHeader } from '../components/layout';
import {
  StatsCard,
  StatusBadge,
  SuggestionBadge,
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

// Warning Badge with Tooltip
function WarningBadgeWithTooltip({ text }) {
  const tooltips = {
    'Low Quality': 'Reply rate is below 1%. Consider pausing this campaign, reviewing your email copy, or targeting different leads.',
    'Low Reply Rate': 'This campaign has a low reply rate. Try A/B testing subject lines or adjusting your targeting.',
    'High Bounce': 'High bounce rate detected. Verify your email list quality and remove invalid addresses.',
    'Needs Review': 'This campaign needs manual review. Check recent performance metrics.',
  };

  const tooltip = tooltips[text] || `Warning: ${text}. Review this campaign for potential improvements.`;

  return (
    <span
      className="inline-flex px-2 py-0.5 rounded-full text-xs font-medium bg-accent/20 text-accent cursor-help"
      title={tooltip}
    >
      {text}
    </span>
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

// Sortable header component
function SortableHeader({ label, field, sortField, sortDirection, onSort, align = 'left' }) {
  const isActive = sortField === field;
  const alignClass = align === 'right' ? 'text-right justify-end' : 'text-left';

  return (
    <th
      className={`px-4 py-3 text-gray-400 text-xs font-medium uppercase tracking-wider cursor-pointer hover:text-white transition-colors ${alignClass}`}
      onClick={() => onSort(field)}
    >
      <div className={`flex items-center gap-1 ${align === 'right' ? 'justify-end' : ''}`}>
        <span>{label}</span>
        {isActive && (
          sortDirection === 'asc' ? <ChevronUp size={14} /> : <ChevronDown size={14} />
        )}
      </div>
    </th>
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
  onRefreshTable,
  isRefreshing = false,
  title,
  titleColor = 'white',
}) {
  const [sortField, setSortField] = useState(null);
  const [sortDirection, setSortDirection] = useState('desc');

  const handleSort = (field) => {
    if (sortField === field) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection('desc');
    }
  };

  // Sort campaigns
  const sortedCampaigns = useMemo(() => {
    if (!sortField) return campaigns;

    return [...campaigns].sort((a, b) => {
      let aVal, bVal;

      switch (sortField) {
        case 'name':
          aVal = a.name?.toLowerCase() || '';
          bVal = b.name?.toLowerCase() || '';
          break;
        case 'created':
          aVal = new Date(a.created_at || 0).getTime();
          bVal = new Date(b.created_at || 0).getTime();
          break;
        case 'status':
          aVal = a.status || '';
          bVal = b.status || '';
          break;
        case 'suggestion':
          aVal = a.suggestion?.suggestion || '';
          bVal = b.suggestion?.suggestion || '';
          break;
        case '7d_sent':
          aVal = a.periods?.['7_days']?.sent_count || a.stats?.sent_count || 0;
          bVal = b.periods?.['7_days']?.sent_count || b.stats?.sent_count || 0;
          break;
        case '7d_rate':
          aVal = a.periods?.['7_days']?.reply_rate || a.stats?.reply_rate || 0;
          bVal = b.periods?.['7_days']?.reply_rate || b.stats?.reply_rate || 0;
          break;
        case '14d_sent':
          aVal = a.periods?.['14_days']?.sent_count || 0;
          bVal = b.periods?.['14_days']?.sent_count || 0;
          break;
        case '14d_rate':
          aVal = a.periods?.['14_days']?.reply_rate || 0;
          bVal = b.periods?.['14_days']?.reply_rate || 0;
          break;
        case '28d_rate':
          aVal = a.periods?.['28_days']?.reply_rate || 0;
          bVal = b.periods?.['28_days']?.reply_rate || 0;
          break;
        case 'positive':
          aVal = a.stats?.positive_rate || 0;
          bVal = b.stats?.positive_rate || 0;
          break;
        default:
          return 0;
      }

      if (typeof aVal === 'string') {
        return sortDirection === 'asc'
          ? aVal.localeCompare(bVal)
          : bVal.localeCompare(aVal);
      }
      return sortDirection === 'asc' ? aVal - bVal : bVal - aVal;
    });
  }, [campaigns, sortField, sortDirection]);

  // Only show full loading spinner on initial load (no data yet)
  const showLoadingSpinner = isInitialLoading && campaigns.length === 0;

  return (
    <div className="mb-4">
      {/* Table Header with Title and Refresh */}
      <div className="flex items-center justify-between mb-4">
        <h2 className={`text-3xl font-bold text-${titleColor}`}>{title}</h2>
        {onRefreshTable && (
          <button
            onClick={onRefreshTable}
            disabled={isRefreshing}
            className="p-2 rounded-lg hover:bg-secondary transition-colors disabled:opacity-50"
            title="Refresh this table"
          >
            <RefreshCw size={18} className={`text-gray-400 hover:text-white ${isRefreshing ? 'animate-spin' : ''}`} />
          </button>
        )}
      </div>

      <div className="bg-card rounded-lg overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-secondary">
              <tr>
                <th className="w-8 px-2 py-3"></th>
                <SortableHeader label="Campaign" field="name" sortField={sortField} sortDirection={sortDirection} onSort={handleSort} />
                <SortableHeader label="Created" field="created" sortField={sortField} sortDirection={sortDirection} onSort={handleSort} />
                <SortableHeader label="Status" field="status" sortField={sortField} sortDirection={sortDirection} onSort={handleSort} />
                <SortableHeader label="Suggested" field="suggestion" sortField={sortField} sortDirection={sortDirection} onSort={handleSort} />
                <SortableHeader label="7D Sent" field="7d_sent" sortField={sortField} sortDirection={sortDirection} onSort={handleSort} align="right" />
                <SortableHeader label="7D Reply" field="7d_rate" sortField={sortField} sortDirection={sortDirection} onSort={handleSort} align="right" />
                <SortableHeader label="14D Sent" field="14d_sent" sortField={sortField} sortDirection={sortDirection} onSort={handleSort} align="right" />
                <SortableHeader label="14D Reply" field="14d_rate" sortField={sortField} sortDirection={sortDirection} onSort={handleSort} align="right" />
                <SortableHeader label="28D Reply" field="28d_rate" sortField={sortField} sortDirection={sortDirection} onSort={handleSort} align="right" />
                <SortableHeader label="Positive" field="positive" sortField={sortField} sortDirection={sortDirection} onSort={handleSort} align="right" />
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
              ) : sortedCampaigns.length === 0 ? (
                <tr>
                  <td colSpan="14" className="px-4 py-12 text-center text-gray-500">
                    {emptyMessage}
                  </td>
                </tr>
              ) : (
                sortedCampaigns.map((campaign) => {
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

                      {/* 7D Reply */}
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

                      {/* 14D Reply */}
                      <td className="px-4 py-3 text-right">
                        <span className={`text-sm font-medium ${getRateColor(periods['14_days']?.reply_rate || 0)}`}>
                          {formatPercent(periods['14_days']?.reply_rate || 0)}
                        </span>
                      </td>

                      {/* 28D Reply */}
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
                              <WarningBadgeWithTooltip key={i} text={warning} />
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

      {/* Footer info */}
      <div className="mt-2 text-sm text-gray-500 text-right">
        Showing {sortedCampaigns.length} campaigns
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
  const [refreshingMain, setRefreshingMain] = useState(false);
  const [refreshingFollowUp, setRefreshingFollowUp] = useState(false);

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

  // Refresh all data (full sync)
  const handleRefresh = async () => {
    try {
      await triggerSync();
      await Promise.all([refreshCampaigns(), refreshOverview(), refreshSyncStatus(), refreshHiddenCampaigns()]);
    } catch (err) {
      console.error('Sync failed:', err);
    }
  };

  // Refresh just the main campaigns table (quick refresh without full sync)
  const handleRefreshMainTable = async () => {
    setRefreshingMain(true);
    try {
      await refreshCampaigns();
    } catch (err) {
      console.error('Refresh failed:', err);
    } finally {
      setRefreshingMain(false);
    }
  };

  // Refresh just the follow-up campaigns table
  const handleRefreshFollowUpTable = async () => {
    setRefreshingFollowUp(true);
    try {
      await refreshCampaigns();
    } catch (err) {
      console.error('Refresh failed:', err);
    } finally {
      setRefreshingFollowUp(false);
    }
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

  // Stats calculations - check for both STARTED and ACTIVE statuses
  const stats = useMemo(() => {
    const campaigns = campaignsData?.campaigns || [];
    const regular = campaigns.filter((c) => !isFollowUpCampaign(c));
    return {
      total: regular.length,
      active: regular.filter((c) => c.status === 'STARTED' || c.status === 'ACTIVE').length,
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
          subtitle="total tracked"
          icon={BarChart3}
        />
        <StatsCard
          title="Active"
          value={stats.active}
          subtitle="currently running"
          icon={Activity}
        />
        <StatsCard
          title="Need Attention"
          value={stats.withSuggestions}
          subtitle="with suggestions"
          icon={AlertTriangle}
        />
        <StatsCard
          title="Low Data"
          value={stats.lowData}
          subtitle="< 200 total sends"
          icon={Clock}
        />
        <StatsCard
          title="Follow-ups"
          value={stats.followUps}
          subtitle="subsequences"
          icon={Activity}
        />
      </div>

      {/* Filter Bar - only Sync button, removed redundant Run Analytics */}
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
        isLoading={isSyncing}
      />

      {/* Error State */}
      {campaignsError && (
        <div className="bg-danger/20 text-danger p-4 rounded-lg mb-6">
          Error loading campaigns: {campaignsError}
        </div>
      )}

      {/* Main Campaigns Table */}
      <CampaignTable
        campaigns={regularCampaigns}
        isInitialLoading={isInitialLoading}
        onStatusChange={handleStatusChange}
        onApply={handleApply}
        onToggleHide={handleToggleHide}
        updatingStatus={updatingStatus}
        applying={applying}
        hidingId={hidingId}
        emptyMessage="No main campaigns found. Click 'Sync Campaigns' to fetch from Smartlead."
        title="MAIN CAMPAIGNS"
        titleColor="accent"
        onRefreshTable={handleRefreshMainTable}
        isRefreshing={refreshingMain}
      />

      {/* Divider */}
      <div className="border-t-4 border-gray-700 my-10"></div>

      {/* Follow-up / Subsequences Section */}
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
        title="FOLLOW-UP CAMPAIGNS"
        titleColor="accent"
        onRefreshTable={handleRefreshFollowUpTable}
        isRefreshing={refreshingFollowUp}
      />

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
                  title="Hidden Main Campaigns"
                  titleColor="gray-400"
                />
              )}

              {/* Hidden Follow-up Campaigns */}
              {hiddenFollowUpCampaigns.length > 0 && (
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
                  title="Hidden Follow-up Campaigns"
                  titleColor="gray-400"
                />
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}
