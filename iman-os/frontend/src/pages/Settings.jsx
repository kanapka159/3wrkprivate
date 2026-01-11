import { useState, useEffect } from 'react';
import { RefreshCw } from 'lucide-react';
import { PageHeader } from '../components/layout';
import { Button, LoadingSpinner } from '../components/shared';
import { useApi, useMutation } from '../hooks/useApi';
import { api } from '../utils/api';
import { timeAgo } from '../utils/formatters';

export default function Settings() {
  const [health, setHealth] = useState(null);
  const [testingConnection, setTestingConnection] = useState(false);
  const [autoSync, setAutoSync] = useState(false);

  const { data: syncStatus, execute: refreshSyncStatus } = useApi(api.getSyncStatus, []);
  const { execute: triggerSync, loading: syncing } = useMutation(api.triggerSync);

  useEffect(() => {
    checkHealth();
  }, []);

  const checkHealth = async () => {
    setTestingConnection(true);
    try {
      const result = await api.getHealth();
      setHealth(result);
    } catch (err) {
      setHealth({ status: 'error', error: err.message });
    } finally {
      setTestingConnection(false);
    }
  };

  const handleSync = async () => {
    try {
      await triggerSync();
      await refreshSyncStatus();
    } catch (err) {
      console.error('Sync failed:', err);
    }
  };

  const lastSyncTime = syncStatus?.last_sync?.completed_at;
  const lastSyncStatus = syncStatus?.last_sync?.status;

  return (
    <div>
      <PageHeader title="Settings" subtitle="System configuration and preferences" />

      <div className="max-w-2xl space-y-6">
        {/* Card 1: Smartlead API */}
        <div className="bg-card rounded-lg p-6">
          <h3 className="text-lg font-semibold text-white mb-4">Smartlead API</h3>

          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-gray-400">Connection Status</span>
              {testingConnection ? (
                <LoadingSpinner size="sm" />
              ) : health?.status === 'ok' ? (
                <span className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-success/20 text-success text-sm font-medium">
                  <span className="w-2 h-2 bg-success rounded-full animate-pulse"></span>
                  Connected
                </span>
              ) : (
                <span className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-danger/20 text-danger text-sm font-medium">
                  <span className="w-2 h-2 bg-danger rounded-full"></span>
                  Disconnected
                </span>
              )}
            </div>

            <div className="flex items-center justify-between">
              <span className="text-gray-400">API Endpoint</span>
              <span className="text-white font-mono text-sm bg-secondary px-2 py-1 rounded">
                localhost:8000/api
              </span>
            </div>

            <Button
              variant="secondary"
              size="sm"
              onClick={checkHealth}
              loading={testingConnection}
            >
              Test Connection
            </Button>
          </div>
        </div>

        {/* Card 2: Sync Settings */}
        <div className="bg-card rounded-lg p-6">
          <h3 className="text-lg font-semibold text-white mb-4">Sync Settings</h3>

          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-gray-400">Last Sync</span>
              <span className="text-white">
                {lastSyncTime ? timeAgo(lastSyncTime) : 'Never'}
                {lastSyncStatus && (
                  <span className={`ml-2 text-sm ${lastSyncStatus === 'completed' ? 'text-success' : 'text-warning'}`}>
                    ({lastSyncStatus})
                  </span>
                )}
              </span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-gray-400">Campaigns Synced</span>
              <span className="text-white">
                {syncStatus?.last_sync?.campaigns_synced ?? '-'}
              </span>
            </div>

            <div className="flex items-center justify-between">
              <div>
                <span className="text-gray-400">Auto-Sync</span>
                <p className="text-gray-600 text-sm">Automatically sync every hour</p>
              </div>
              <button
                onClick={() => setAutoSync(!autoSync)}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                  autoSync ? 'bg-accent' : 'bg-gray-600'
                }`}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                    autoSync ? 'translate-x-6' : 'translate-x-1'
                  }`}
                />
              </button>
            </div>

            <Button onClick={handleSync} loading={syncing}>
              <RefreshCw size={16} />
              Sync Now
            </Button>
          </div>
        </div>

        {/* Card 3: Thresholds */}
        <div className="bg-card rounded-lg p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-white">Suggestion Thresholds</h3>
            <span className="text-xs text-gray-500 bg-secondary px-2 py-1 rounded">Read-only</span>
          </div>

          <div className="space-y-3">
            <div className="flex items-center justify-between py-2 border-b border-gray-800">
              <div className="flex items-center gap-3">
                <span className="w-3 h-3 bg-success rounded-full"></span>
                <span className="text-white font-medium">KEEP</span>
              </div>
              <span className="text-gray-400">≥ 2% reply rate</span>
            </div>
            <div className="flex items-center justify-between py-2 border-b border-gray-800">
              <div className="flex items-center gap-3">
                <span className="w-3 h-3 bg-warning rounded-full"></span>
                <span className="text-white font-medium">MONITOR</span>
              </div>
              <span className="text-gray-400">≥ 1% reply rate</span>
            </div>
            <div className="flex items-center justify-between py-2 border-b border-gray-800">
              <div className="flex items-center gap-3">
                <span className="w-3 h-3 bg-accent rounded-full"></span>
                <span className="text-white font-medium">PAUSE</span>
              </div>
              <span className="text-gray-400">≥ 0.5% reply rate</span>
            </div>
            <div className="flex items-center justify-between py-2 border-b border-gray-800">
              <div className="flex items-center gap-3">
                <span className="w-3 h-3 bg-danger rounded-full"></span>
                <span className="text-white font-medium">KILL</span>
              </div>
              <span className="text-gray-400">&lt; 0.5% reply rate</span>
            </div>
            <div className="flex items-center justify-between py-2">
              <div className="flex items-center gap-3">
                <span className="w-3 h-3 bg-gray-500 rounded-full"></span>
                <span className="text-white font-medium">LOW DATA</span>
              </div>
              <span className="text-gray-400">&lt; 200 sends</span>
            </div>
          </div>
        </div>

        {/* Card 4: About */}
        <div className="bg-card rounded-lg p-6">
          <h3 className="text-lg font-semibold text-white mb-4">About</h3>

          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-gray-400">Version</span>
              <span className="text-white font-mono">1.0.0</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-gray-400">Application</span>
              <span className="text-white">IMAN OS</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-gray-400">Description</span>
              <span className="text-gray-400 text-sm">Campaign Analytics Dashboard</span>
            </div>
          </div>

          <div className="mt-6 pt-4 border-t border-gray-800">
            <p className="text-gray-600 text-sm">
              Built for Smartlead campaign management and optimization.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
