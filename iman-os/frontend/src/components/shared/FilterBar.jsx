import { Search, RefreshCw } from 'lucide-react';
import Button from './Button';

export default function FilterBar({
  search,
  onSearchChange,
  clientFilter,
  onClientFilterChange,
  clients = [],
  statusFilter,
  onStatusFilterChange,
  onlySuggestions,
  onOnlySuggestionsChange,
  lastSync,
  onRefresh,
  isLoading = false,
}) {
  return (
    <div className="flex flex-wrap items-center gap-4 mb-6 p-4 bg-card rounded-lg">
      {/* Search */}
      <div className="relative flex-1 min-w-[200px]">
        <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
        <input
          type="text"
          placeholder="Search campaigns..."
          value={search || ''}
          onChange={(e) => onSearchChange?.(e.target.value)}
          className="w-full pl-10 pr-4 py-2 bg-secondary rounded-lg text-white placeholder-gray-500 border border-gray-700 focus:border-accent focus:outline-none"
        />
      </div>

      {/* Client Filter */}
      {clients.length > 0 && (
        <select
          value={clientFilter || ''}
          onChange={(e) => onClientFilterChange?.(e.target.value)}
          className="px-4 py-2 bg-secondary rounded-lg text-white border border-gray-700 focus:border-accent focus:outline-none"
        >
          <option value="">All Clients</option>
          {clients.map((client) => (
            <option key={client.id} value={client.id}>
              {client.name}
            </option>
          ))}
        </select>
      )}

      {/* Status Filter */}
      <select
        value={statusFilter || ''}
        onChange={(e) => onStatusFilterChange?.(e.target.value)}
        className="px-4 py-2 bg-secondary rounded-lg text-white border border-gray-700 focus:border-accent focus:outline-none"
      >
        <option value="">All Statuses</option>
        <option value="STARTED">Active</option>
        <option value="PAUSED">Paused</option>
        <option value="STOPPED">Stopped</option>
        <option value="COMPLETED">Completed</option>
      </select>

      {/* Only Suggestions Toggle */}
      <label className="flex items-center gap-2 cursor-pointer">
        <input
          type="checkbox"
          checked={onlySuggestions || false}
          onChange={(e) => onOnlySuggestionsChange?.(e.target.checked)}
          className="w-4 h-4 rounded border-gray-700 bg-secondary text-accent focus:ring-accent focus:ring-offset-0"
        />
        <span className="text-sm text-gray-400">Needs Action</span>
      </label>

      {/* Last Sync */}
      {lastSync && (
        <span className="text-sm text-gray-500">
          Last sync: {lastSync}
        </span>
      )}

      {/* Sync Button */}
      <div className="ml-auto">
        {onRefresh && (
          <Button
            variant="primary"
            onClick={onRefresh}
            loading={isLoading}
            disabled={isLoading}
          >
            <RefreshCw size={16} />
            Sync Campaigns
          </Button>
        )}
      </div>
    </div>
  );
}
