import { useState, useMemo, useRef, useCallback } from 'react';
import { BarChart3, Activity, AlertTriangle, Clock, ChevronDown, ChevronUp, Minus, Plus, Eye, EyeOff, RefreshCw, GripVertical } from 'lucide-react';
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

// Rate color helper - green >= 3.1%, yellow >= 1%, red < 1%
function getRateColor(rate) {
  if (rate >= 3.1) return 'text-success';
  if (rate >= 1) return 'text-warning';
  return 'text-danger';
}

// Positive reply ratio color helper - green >= 15%, yellow 5-15%, red < 5%
function getPositiveRateColor(rate) {
  if (rate >= 15) return 'text-success';
  if (rate >= 5) return 'text-warning';
  return 'text-danger';
}

// Status sort order - Active/Started first, then Paused, then Stopped
function getStatusSortOrder(status) {
  const order = {
    'ACTIVE': 0,
    'STARTED': 0,
    'PAUSED': 1,
    'STOPPED': 2,
    'DRAFTED': 3,
  };
  return order[status] ?? 4;
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

// Suggestion Badge with Tooltip
function SuggestionBadgeWithTooltip({ suggestion, color, reason }) {
  const tooltips = {
    'KEEP': 'This campaign is performing well. Keep it running as is.',
    'MONITOR': 'This campaign needs monitoring. Watch the metrics closely for any changes.',
    'WAIT': 'Not enough data yet. Wait for more results before making decisions.',
    'PAUSE': 'Consider pausing this campaign. Performance is below expectations.',
    'REVIEW': 'This campaign needs manual review. Check the targeting and copy.',
    'STOP': 'Recommend stopping this campaign due to poor performance.',
  };

  const tooltip = reason || tooltips[suggestion] || `Suggestion: ${suggestion}`;

  const colorClasses = {
    green: 'bg-success/20 text-success',
    yellow: 'bg-warning/20 text-warning',
    red: 'bg-danger/20 text-danger',
    orange: 'bg-accent/20 text-accent',
  };

  const bgClass = colorClasses[color] || 'bg-gray-500/20 text-gray-400';

  return (
    <span
      className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium cursor-help ${bgClass}`}
      title={tooltip}
    >
      {suggestion}
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

// Sortable header component with two-line support
function SortableHeader({ label, subLabel, field, sortField, sortDirection, onSort, align = 'left', minWidth, resizable = false }) {
  const isActive = sortField === field;
  const alignClass = align === 'center' ? 'text-center' : align === 'right' ? 'text-right' : 'text-left';
  const flexAlign = align === 'center' ? 'items-center' : align === 'right' ? 'items-end' : 'items-start';
  const justifyAlign = align === 'center' ? 'justify-center' : align === 'right' ? 'justify-end' : '';

  return (
    <th
      className={`px-3 py-3 text-white text-xs font-semibold uppercase tracking-wider cursor-pointer hover:text-accent transition-colors ${alignClass} ${resizable ? 'resize-x overflow-auto' : ''}`}
      onClick={() => onSort(field)}
      style={minWidth ? { minWidth } : {}}
    >
      <div className={`flex flex-col ${flexAlign}`}>
        <div className={`flex items-center gap-1 ${justifyAlign}`}>
          <span>{label}</span>
          {isActive && (
            sortDirection === 'asc'
              ? <ChevronUp size={14} strokeWidth={3} className="text-accent" />
              : <ChevronDown size={14} strokeWidth={3} className="text-accent" />
          )}
        </div>
        {subLabel && <span className="text-gray-400 text-[10px]">{subLabel}</span>}
      </div>
    </th>
  );
}

// Reusable Campaign Table component
function CampaignTable({
  campaigns,
  isInitialLoading,
  onStatusChange,
  onToggleHide,
  updatingStatus,
  hidingId,
  emptyMessage = "No campaigns found.",
  showUnhide = false,
  onRefreshTable,
  isRefreshing = false,
  title,
  titleColor = 'white',
  lastRefreshed,
}) {
  // Default sort by status (Active first)
  const [sortField, setSortField] = useState('status');
  const [sortDirection, setSortDirection] = useState('asc');
  const [nameColumnWidth, setNameColumnWidth] = useState(200);
  const resizingRef = useRef(false);
  const startXRef = useRef(0);
  const startWidthRef = useRef(0);

  // Handle resize drag
  const handleResizeStart = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    resizingRef.current = true;
    startXRef.current = e.clientX;
    startWidthRef.current = nameColumnWidth;

    const handleMouseMove = (moveE) => {
      if (!resizingRef.current) return;
      const delta = moveE.clientX - startXRef.current;
      const newWidth = Math.max(120, Math.min(500, startWidthRef.current + delta));
      setNameColumnWidth(newWidth);
    };

    const handleMouseUp = () => {
      resizingRef.current = false;
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  }, [nameColumnWidth]);

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
          // Use custom sort order for status
          aVal = getStatusSortOrder(a.status);
          bVal = getStatusSortOrder(b.status);
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
        case 'warnings':
          aVal = a.warnings?.length || 0;
          bVal = b.warnings?.length || 0;
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

  // Calculate summary/averages for all campaigns
  const summary = useMemo(() => {
    if (sortedCampaigns.length === 0) return null;

    const activeCampaigns = sortedCampaigns.filter(c => c.status === 'STARTED' || c.status === 'ACTIVE');
    const count = sortedCampaigns.length;

    // Calculate averages
    let total7dSent = 0, total7dRate = 0, total14dSent = 0, total14dRate = 0, total28dRate = 0, totalPositiveRate = 0;

    sortedCampaigns.forEach(c => {
      const periods = c.periods || {};
      const stats = c.stats || {};
      total7dSent += periods['7_days']?.sent_count || stats.sent_count || 0;
      total7dRate += periods['7_days']?.reply_rate || stats.reply_rate || 0;
      total14dSent += periods['14_days']?.sent_count || 0;
      total14dRate += periods['14_days']?.reply_rate || 0;
      total28dRate += periods['28_days']?.reply_rate || 0;
      totalPositiveRate += stats.positive_rate || 0;
    });

    return {
      activeCount: activeCampaigns.length,
      totalCount: count,
      avg7dSent: Math.round(total7dSent / count),
      avg7dRate: total7dRate / count,
      avg14dSent: Math.round(total14dSent / count),
      avg14dRate: total14dRate / count,
      avg28dRate: total28dRate / count,
      avgPositiveRate: totalPositiveRate / count,
    };
  }, [sortedCampaigns]);

  return (
    <div className="mb-4">
      {/* Table Header with Title, Refresh, and Last Updated */}
      <div className="flex items-center gap-3 mb-4">
        <h2 className={`text-3xl font-bold text-${titleColor}`}>{title}</h2>
        {onRefreshTable && (
          <button
            onClick={onRefreshTable}
            disabled={isRefreshing}
            className="p-1.5 rounded-lg hover:bg-secondary transition-colors disabled:opacity-50"
            title="Refresh this table"
          >
            <RefreshCw size={16} className={`text-gray-400 hover:text-white ${isRefreshing ? 'animate-spin' : ''}`} />
          </button>
        )}
        {lastRefreshed && (
          <span className="text-[11px] text-gray-500 ml-auto pl-4 font-light tracking-wide">
            · {lastRefreshed}
          </span>
        )}
      </div>

      <div className="bg-card rounded-lg overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-secondary">
              <tr>
                <th className="w-8 px-2 py-3"></th>
                {/* Resizable Campaign Name Column */}
                <th
                  className="px-3 py-3 text-white text-xs font-semibold uppercase tracking-wider cursor-pointer hover:text-accent transition-colors text-center relative"
                  style={{ width: nameColumnWidth, minWidth: 120, maxWidth: 500 }}
                >
                  <div className="flex items-center justify-center gap-1" onClick={() => handleSort('name')}>
                    <div className="flex flex-col items-center">
                      <div className="flex items-center gap-1">
                        <span>Campaign</span>
                        {sortField === 'name' && (
                          sortDirection === 'asc'
                            ? <ChevronUp size={14} strokeWidth={3} className="text-accent" />
                            : <ChevronDown size={14} strokeWidth={3} className="text-accent" />
                        )}
                      </div>
                      <span className="text-gray-400 text-[10px]">Name</span>
                    </div>
                  </div>
                  {/* Resize handle - drag to resize column */}
                  <div
                    className="absolute right-0 top-0 bottom-0 w-4 cursor-col-resize flex items-center justify-center group select-none"
                    onMouseDown={handleResizeStart}
                    onClick={(e) => e.stopPropagation()}
                    title="Drag to resize column"
                  >
                    <div className="w-1 h-6 bg-gray-600 group-hover:bg-accent group-hover:w-1.5 rounded-full transition-all"></div>
                  </div>
                </th>
                <SortableHeader label="Created" field="created" sortField={sortField} sortDirection={sortDirection} onSort={handleSort} minWidth="100px" />
                <SortableHeader label="Status" field="status" sortField={sortField} sortDirection={sortDirection} onSort={handleSort} minWidth="100px" />
                <SortableHeader label="7D" subLabel="Sent" field="7d_sent" sortField={sortField} sortDirection={sortDirection} onSort={handleSort} align="center" minWidth="70px" />
                <SortableHeader label="7D Reply" subLabel="Ratio" field="7d_rate" sortField={sortField} sortDirection={sortDirection} onSort={handleSort} align="center" minWidth="90px" />
                <SortableHeader label="14D" subLabel="Sent" field="14d_sent" sortField={sortField} sortDirection={sortDirection} onSort={handleSort} align="center" minWidth="70px" />
                <SortableHeader label="14D Reply" subLabel="Ratio" field="14d_rate" sortField={sortField} sortDirection={sortDirection} onSort={handleSort} align="center" minWidth="95px" />
                <SortableHeader label="28D Reply" subLabel="Ratio" field="28d_rate" sortField={sortField} sortDirection={sortDirection} onSort={handleSort} align="center" minWidth="95px" />
                <SortableHeader label="Positive" subLabel="Reply Ratio" field="positive" sortField={sortField} sortDirection={sortDirection} onSort={handleSort} align="center" minWidth="90px" />
                <SortableHeader label="Suggestions" field="suggestion" sortField={sortField} sortDirection={sortDirection} onSort={handleSort} minWidth="100px" />
                <SortableHeader label="Warnings" field="warnings" sortField={sortField} sortDirection={sortDirection} onSort={handleSort} minWidth="120px" />
              </tr>
            </thead>
            <tbody>
              {showLoadingSpinner ? (
                <tr>
                  <td colSpan="12" className="px-4 py-12 text-center">
                    <LoadingSpinner size="lg" />
                  </td>
                </tr>
              ) : sortedCampaigns.length === 0 ? (
                <tr>
                  <td colSpan="12" className="px-4 py-12 text-center text-gray-500">
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
                      <td className="px-3 py-3 text-center" style={{ width: nameColumnWidth, minWidth: 120, maxWidth: 500 }}>
                        <div
                          className="font-medium text-white text-sm truncate mx-auto"
                          style={{ maxWidth: nameColumnWidth - 24 }}
                          title={campaign.name}
                        >
                          {campaign.name}
                        </div>
                      </td>

                      {/* Created Date */}
                      <td className="px-3 py-3">
                        <span className="text-gray-400 text-sm">
                          {createdDate}
                        </span>
                      </td>

                      {/* Status with dropdown */}
                      <td className="px-3 py-3">
                        <StatusDropdown
                          status={campaign.status}
                          campaignId={campaign.id}
                          onStatusChange={onStatusChange}
                          disabled={updatingStatus}
                        />
                      </td>

                      {/* 7D Sent */}
                      <td className="px-3 py-3 text-center">
                        <span className="text-white text-sm font-medium">
                          {formatNumber(periods['7_days']?.sent_count || stats.sent_count || 0)}
                        </span>
                      </td>

                      {/* 7D Reply Ratio */}
                      <td className="px-3 py-3 text-center">
                        <span className={`text-sm font-bold ${getRateColor(periods['7_days']?.reply_rate || stats.reply_rate || 0)}`}>
                          {formatPercent(periods['7_days']?.reply_rate || stats.reply_rate || 0)}
                        </span>
                      </td>

                      {/* 14D Sent */}
                      <td className="px-3 py-3 text-center">
                        <span className="text-white text-sm font-medium">
                          {formatNumber(periods['14_days']?.sent_count || 0)}
                        </span>
                      </td>

                      {/* 14D Reply Ratio */}
                      <td className="px-3 py-3 text-center">
                        <span className={`text-sm font-bold ${getRateColor(periods['14_days']?.reply_rate || 0)}`}>
                          {formatPercent(periods['14_days']?.reply_rate || 0)}
                        </span>
                      </td>

                      {/* 28D Reply Ratio */}
                      <td className="px-3 py-3 text-center">
                        <span className={`text-sm font-bold ${getRateColor(periods['28_days']?.reply_rate || 0)}`}>
                          {formatPercent(periods['28_days']?.reply_rate || 0)}
                        </span>
                      </td>

                      {/* Positive Reply Ratio */}
                      <td className="px-3 py-3 text-center">
                        <span className={`text-sm font-bold ${getPositiveRateColor(stats.positive_rate || 0)}`}>
                          {formatPercent(stats.positive_rate || 0)}
                        </span>
                      </td>

                      {/* Suggestion */}
                      <td className="px-3 py-3">
                        {suggestion.suggestion ? (
                          <SuggestionBadgeWithTooltip
                            suggestion={suggestion.suggestion}
                            color={suggestion.color}
                            reason={suggestion.reason}
                          />
                        ) : (
                          <span className="text-gray-600">-</span>
                        )}
                      </td>

                      {/* Warnings */}
                      <td className="px-3 py-3">
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
                    </tr>
                  );
                })
              )}
              {/* Summary Row */}
              {summary && sortedCampaigns.length > 0 && (
                <tr className="border-t-2 border-gray-600 bg-secondary/50 font-semibold">
                  {/* Empty cell for hide button */}
                  <td className="px-2 py-3"></td>
                  {/* Summary Label */}
                  <td className="px-3 py-3 text-center" style={{ width: nameColumnWidth }}>
                    <div className="flex flex-col items-center">
                      <span className="text-accent text-sm font-bold">SUMMARY OF ALL</span>
                      <span className="text-gray-500 text-xs font-normal">
                        {summary.activeCount} active
                      </span>
                    </div>
                  </td>
                  {/* Created - skip */}
                  <td className="px-3 py-3"></td>
                  {/* Status - skip */}
                  <td className="px-3 py-3"></td>
                  {/* 7D Sent - average */}
                  <td className="px-3 py-3 text-center">
                    <span className="text-gray-300 text-sm">
                      {formatNumber(summary.avg7dSent)}
                    </span>
                  </td>
                  {/* 7D Reply Ratio - average */}
                  <td className="px-3 py-3 text-center">
                    <span className={`text-sm font-bold ${getRateColor(summary.avg7dRate)}`}>
                      {formatPercent(summary.avg7dRate)}
                    </span>
                  </td>
                  {/* 14D Sent - average */}
                  <td className="px-3 py-3 text-center">
                    <span className="text-gray-300 text-sm">
                      {formatNumber(summary.avg14dSent)}
                    </span>
                  </td>
                  {/* 14D Reply Ratio - average */}
                  <td className="px-3 py-3 text-center">
                    <span className={`text-sm font-bold ${getRateColor(summary.avg14dRate)}`}>
                      {formatPercent(summary.avg14dRate)}
                    </span>
                  </td>
                  {/* 28D Reply Ratio - average */}
                  <td className="px-3 py-3 text-center">
                    <span className={`text-sm font-bold ${getRateColor(summary.avg28dRate)}`}>
                      {formatPercent(summary.avg28dRate)}
                    </span>
                  </td>
                  {/* Positive Reply Ratio - average */}
                  <td className="px-3 py-3 text-center">
                    <span className={`text-sm font-bold ${getPositiveRateColor(summary.avgPositiveRate)}`}>
                      {formatPercent(summary.avgPositiveRate)}
                    </span>
                  </td>
                  {/* Suggestions - skip */}
                  <td className="px-3 py-3"></td>
                  {/* Warnings - skip */}
                  <td className="px-3 py-3"></td>
                </tr>
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
  const [lastRefreshTime, setLastRefreshTime] = useState(null);

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
      setLastRefreshTime(new Date());
    } catch (err) {
      console.error('Sync failed:', err);
    }
  };

  // Refresh just the main campaigns table (quick refresh without full sync)
  const handleRefreshMainTable = async () => {
    setRefreshingMain(true);
    try {
      await refreshCampaigns();
      setLastRefreshTime(new Date());
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
      setLastRefreshTime(new Date());
    } catch (err) {
      console.error('Refresh failed:', err);
    } finally {
      setRefreshingFollowUp(false);
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

  // Format last refresh time
  const formattedLastRefresh = lastRefreshTime ? timeAgo(lastRefreshTime.toISOString()) :
    (syncStatus?.last_sync?.completed_at ? timeAgo(syncStatus.last_sync.completed_at) : null);

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
        onToggleHide={handleToggleHide}
        updatingStatus={updatingStatus}
        hidingId={hidingId}
        emptyMessage="No main campaigns found. Click 'Sync Campaigns' to fetch from Smartlead."
        title="MAIN CAMPAIGNS"
        titleColor="accent"
        onRefreshTable={handleRefreshMainTable}
        isRefreshing={refreshingMain}
        lastRefreshed={formattedLastRefresh}
      />

      {/* Divider */}
      <div className="border-t-4 border-gray-700 my-10"></div>

      {/* Follow-up / Subsequences Section */}
      <CampaignTable
        campaigns={followUpCampaigns}
        isInitialLoading={isInitialLoading}
        onStatusChange={handleStatusChange}
        onToggleHide={handleToggleHide}
        updatingStatus={updatingStatus}
        hidingId={hidingId}
        emptyMessage="No follow-up campaigns found."
        title="FOLLOW-UP CAMPAIGNS"
        titleColor="accent"
        onRefreshTable={handleRefreshFollowUpTable}
        isRefreshing={refreshingFollowUp}
        lastRefreshed={formattedLastRefresh}
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
                  onToggleHide={handleToggleHide}
                  updatingStatus={updatingStatus}
                  hidingId={hidingId}
                  emptyMessage="No hidden main campaigns."
                  showUnhide={true}
                  title="Hidden Main Campaigns"
                  titleColor="gray-400"
                  lastRefreshed={formattedLastRefresh}
                />
              )}

              {/* Hidden Follow-up Campaigns */}
              {hiddenFollowUpCampaigns.length > 0 && (
                <CampaignTable
                  campaigns={hiddenFollowUpCampaigns}
                  isInitialLoading={hiddenLoading && hiddenFollowUpCampaigns.length === 0}
                  onStatusChange={handleStatusChange}
                  onToggleHide={handleToggleHide}
                  updatingStatus={updatingStatus}
                  hidingId={hidingId}
                  emptyMessage="No hidden follow-up campaigns."
                  showUnhide={true}
                  title="Hidden Follow-up Campaigns"
                  titleColor="gray-400"
                  lastRefreshed={formattedLastRefresh}
                />
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}
