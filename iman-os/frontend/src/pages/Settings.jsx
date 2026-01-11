import { useState, useEffect } from 'react';
import { PageHeader } from '../components/layout';
import { Button, LoadingSpinner } from '../components/shared';
import { api } from '../utils/api';

export default function Settings() {
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    checkHealth();
  }, []);

  const checkHealth = async () => {
    setLoading(true);
    try {
      const result = await api.getHealth();
      setHealth(result);
    } catch (err) {
      setHealth({ status: 'error', error: err.message });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <PageHeader title="Settings" subtitle="System configuration" />

      <div className="max-w-2xl space-y-6">
        {/* API Connection */}
        <div className="bg-card rounded-lg p-6">
          <h3 className="text-lg font-medium text-white mb-4">API Connection</h3>

          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-gray-400">Backend Status</span>
              {loading ? (
                <LoadingSpinner size="sm" />
              ) : health?.status === 'ok' ? (
                <span className="text-success flex items-center gap-2">
                  <span className="w-2 h-2 bg-success rounded-full"></span>
                  Connected
                </span>
              ) : (
                <span className="text-danger flex items-center gap-2">
                  <span className="w-2 h-2 bg-danger rounded-full"></span>
                  Disconnected
                </span>
              )}
            </div>

            <div className="flex items-center justify-between">
              <span className="text-gray-400">API URL</span>
              <span className="text-white font-mono text-sm">http://localhost:8000/api</span>
            </div>

            <Button variant="secondary" size="sm" onClick={checkHealth}>
              Test Connection
            </Button>
          </div>
        </div>

        {/* Thresholds Info */}
        <div className="bg-card rounded-lg p-6">
          <h3 className="text-lg font-medium text-white mb-4">Suggestion Thresholds</h3>

          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 bg-success rounded-full"></span>
                <span className="text-gray-400">KEEP (Green)</span>
              </div>
              <span className="text-white">&ge; 2% reply rate</span>
            </div>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 bg-warning rounded-full"></span>
                <span className="text-gray-400">MONITOR (Yellow)</span>
              </div>
              <span className="text-white">&ge; 1% reply rate</span>
            </div>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 bg-accent rounded-full"></span>
                <span className="text-gray-400">PAUSE (Orange)</span>
              </div>
              <span className="text-white">&ge; 0.5% reply rate</span>
            </div>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 bg-danger rounded-full"></span>
                <span className="text-gray-400">KILL (Red)</span>
              </div>
              <span className="text-white">&lt; 0.5% reply rate</span>
            </div>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 bg-gray-500 rounded-full"></span>
                <span className="text-gray-400">WAIT (Gray)</span>
              </div>
              <span className="text-white">&lt; 200 sends</span>
            </div>
          </div>
        </div>

        {/* About */}
        <div className="bg-card rounded-lg p-6">
          <h3 className="text-lg font-medium text-white mb-4">About</h3>
          <div className="space-y-2 text-gray-400">
            <p>IMAN OS v0.1.0</p>
            <p>Campaign Analytics Dashboard for Smartlead</p>
          </div>
        </div>
      </div>
    </div>
  );
}
