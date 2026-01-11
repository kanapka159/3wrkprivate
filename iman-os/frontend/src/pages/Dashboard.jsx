import { Mail, MessageSquare, TrendingUp, AlertTriangle, RefreshCw } from 'lucide-react';
import { PageHeader } from '../components/layout';
import { StatsCard, Button, LoadingSpinner } from '../components/shared';
import { useApi, useMutation } from '../hooks/useApi';
import { api } from '../utils/api';
import { formatNumber, formatPercent, timeAgo } from '../utils/formatters';

export default function Dashboard() {
  const { data: overview, loading, error, execute: refresh } = useApi(
    () => api.getOverview(7),
    []
  );
  const { data: syncStatus } = useApi(api.getSyncStatus, []);
  const { execute: triggerSync, loading: syncing } = useMutation(api.triggerSync);

  const handleSync = async () => {
    try {
      await triggerSync();
      refresh();
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

  return (
    <div>
      <PageHeader
        title="Ops Dashboard"
        subtitle={`Last synced: ${timeAgo(syncStatus?.last_sync?.completed_at)}`}
        actions={
          <Button onClick={handleSync} loading={syncing}>
            <RefreshCw size={16} />
            Sync Now
          </Button>
        }
      />

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <StatsCard
          title="Total Campaigns"
          value={campaigns.total || 0}
          subtitle={`${campaigns.active || 0} active`}
          icon={TrendingUp}
        />
        <StatsCard
          title="Emails Sent (7d)"
          value={formatNumber(metrics.sent_count || 0)}
          icon={Mail}
        />
        <StatsCard
          title="Reply Rate"
          value={formatPercent(metrics.reply_rate || 0)}
          subtitle={`${formatNumber(metrics.reply_count || 0)} replies`}
          icon={MessageSquare}
        />
        <StatsCard
          title="Needing Action"
          value={overview?.needing_action || 0}
          subtitle="campaigns"
          icon={AlertTriangle}
        />
      </div>

      {/* Additional Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-card rounded-lg p-6">
          <h3 className="text-gray-400 text-sm mb-4">Campaign Status</h3>
          <div className="space-y-3">
            <div className="flex justify-between">
              <span className="text-gray-400">Active</span>
              <span className="text-success font-medium">{campaigns.active || 0}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">Paused</span>
              <span className="text-warning font-medium">{campaigns.paused || 0}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">Stopped</span>
              <span className="text-danger font-medium">{campaigns.stopped || 0}</span>
            </div>
          </div>
        </div>

        <div className="bg-card rounded-lg p-6">
          <h3 className="text-gray-400 text-sm mb-4">Performance (7d)</h3>
          <div className="space-y-3">
            <div className="flex justify-between">
              <span className="text-gray-400">Open Rate</span>
              <span className="text-white font-medium">{formatPercent(metrics.open_rate || 0)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">Reply Rate</span>
              <span className="text-white font-medium">{formatPercent(metrics.reply_rate || 0)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">Positive Rate</span>
              <span className="text-white font-medium">{formatPercent(metrics.positive_rate || 0)}</span>
            </div>
          </div>
        </div>

        <div className="bg-card rounded-lg p-6">
          <h3 className="text-gray-400 text-sm mb-4">Deliverability</h3>
          <div className="space-y-3">
            <div className="flex justify-between">
              <span className="text-gray-400">Bounce Rate</span>
              <span className={`font-medium ${(metrics.bounce_rate || 0) > 3 ? 'text-danger' : 'text-success'}`}>
                {formatPercent(metrics.bounce_rate || 0)}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">Bounces</span>
              <span className="text-white font-medium">{formatNumber(metrics.bounce_count || 0)}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
