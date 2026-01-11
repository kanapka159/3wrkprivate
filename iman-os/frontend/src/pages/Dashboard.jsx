import { useNavigate } from 'react-router-dom';
import {
  BarChart3,
  Activity,
  Mail,
  MessageSquare,
  TrendingUp,
  ThumbsUp,
  AlertTriangle,
  Clock,
  RefreshCw,
  HeartPulse,
} from 'lucide-react';
import { PageHeader } from '../components/layout';
import { StatsCard, Button, LoadingSpinner } from '../components/shared';
import { useApi, useMutation } from '../hooks/useApi';
import { api } from '../utils/api';
import { formatNumber, formatPercent, timeAgo } from '../utils/formatters';

export default function Dashboard() {
  const navigate = useNavigate();

  const { data: overview, loading, error, execute: refresh } = useApi(
    () => api.getOverview(7),
    []
  );
  const { data: syncStatus, execute: refreshSyncStatus } = useApi(api.getSyncStatus, []);
  const { execute: triggerSync, loading: syncing } = useMutation(api.triggerSync);

  const handleSync = async () => {
    try {
      await triggerSync();
      await Promise.all([refresh(), refreshSyncStatus()]);
    } catch (err) {
      console.error('Sync failed:', err);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-12">
        <p className="text-danger mb-4">Error loading dashboard: {error}</p>
        <Button onClick={refresh}>Retry</Button>
      </div>
    );
  }

  const metrics = overview?.metrics || {};
  const campaigns = overview?.campaigns || {};
  const lastSyncTime = syncStatus?.last_sync?.completed_at;

  return (
    <div>
      {/* Header */}
      <PageHeader
        title="Ops Dashboard"
        subtitle="Overview of all campaign operations"
      />

      {/* Stats Cards - Row 1 */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
        <StatsCard
          title="Total Campaigns"
          value={campaigns.total || 0}
          icon={BarChart3}
        />
        <StatsCard
          title="Active"
          value={campaigns.active || 0}
          subtitle="currently running"
          icon={Activity}
        />
        <StatsCard
          title="Emails Sent (7d)"
          value={formatNumber(metrics.sent_count || 0)}
          icon={Mail}
        />
        <StatsCard
          title="Replies (7d)"
          value={formatNumber(metrics.reply_count || 0)}
          icon={MessageSquare}
        />
      </div>

      {/* Stats Cards - Row 2 */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <StatsCard
          title="Avg Reply Rate"
          value={formatPercent(metrics.reply_rate || 0)}
          icon={TrendingUp}
        />
        <StatsCard
          title="Avg Positive Rate"
          value={formatPercent(metrics.positive_rate || 0)}
          icon={ThumbsUp}
        />
        <StatsCard
          title="Need Attention"
          value={overview?.needing_action || 0}
          subtitle="campaigns"
          icon={AlertTriangle}
        />
        <StatsCard
          title="Last Sync"
          value={lastSyncTime ? timeAgo(lastSyncTime) : 'Never'}
          icon={Clock}
        />
      </div>

      {/* Quick Actions */}
      <div className="bg-card rounded-lg p-6 mb-8">
        <h3 className="text-gray-400 text-sm font-medium uppercase tracking-wider mb-4">
          Quick Actions
        </h3>
        <div className="flex flex-wrap gap-4">
          <Button onClick={handleSync} loading={syncing}>
            <RefreshCw size={18} />
            Run Sync
          </Button>
          <Button variant="secondary" onClick={() => navigate('/campaigns')}>
            <HeartPulse size={18} />
            View Campaign Health
          </Button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Campaign Status */}
        <div className="bg-card rounded-lg p-6">
          <h3 className="text-gray-400 text-sm font-medium uppercase tracking-wider mb-4">
            Campaign Status
          </h3>
          <div className="space-y-3">
            <div className="flex justify-between items-center">
              <span className="text-gray-400">Active</span>
              <span className="text-success font-semibold">{campaigns.active || 0}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-gray-400">Paused</span>
              <span className="text-warning font-semibold">{campaigns.paused || 0}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-gray-400">Stopped</span>
              <span className="text-danger font-semibold">{campaigns.stopped || 0}</span>
            </div>
          </div>
        </div>

        {/* Performance */}
        <div className="bg-card rounded-lg p-6">
          <h3 className="text-gray-400 text-sm font-medium uppercase tracking-wider mb-4">
            Performance (7d)
          </h3>
          <div className="space-y-3">
            <div className="flex justify-between items-center">
              <span className="text-gray-400">Open Rate</span>
              <span className="text-white font-semibold">{formatPercent(metrics.open_rate || 0)}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-gray-400">Reply Rate</span>
              <span className="text-white font-semibold">{formatPercent(metrics.reply_rate || 0)}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-gray-400">Positive Rate</span>
              <span className="text-white font-semibold">{formatPercent(metrics.positive_rate || 0)}</span>
            </div>
          </div>
        </div>

        {/* Deliverability */}
        <div className="bg-card rounded-lg p-6">
          <h3 className="text-gray-400 text-sm font-medium uppercase tracking-wider mb-4">
            Deliverability
          </h3>
          <div className="space-y-3">
            <div className="flex justify-between items-center">
              <span className="text-gray-400">Bounce Rate</span>
              <span className={`font-semibold ${(metrics.bounce_rate || 0) > 3 ? 'text-danger' : 'text-success'}`}>
                {formatPercent(metrics.bounce_rate || 0)}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-gray-400">Total Bounces</span>
              <span className="text-white font-semibold">{formatNumber(metrics.bounce_count || 0)}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
