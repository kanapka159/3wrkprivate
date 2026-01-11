const suggestionStyles = {
  KEEP: 'bg-success/20 text-success border-success/30',
  MONITOR: 'bg-warning/20 text-warning border-warning/30',
  PAUSE: 'bg-accent/20 text-accent border-accent/30',
  KILL: 'bg-danger/20 text-danger border-danger/30',
  WAIT: 'bg-gray-500/20 text-gray-400 border-gray-500/30',
  'LOW DATA': 'bg-gray-500/20 text-gray-400 border-gray-500/30',
};

// Color-based styles for backward compatibility
const colorStyles = {
  green: 'bg-success/20 text-success border-success/30',
  yellow: 'bg-warning/20 text-warning border-warning/30',
  orange: 'bg-accent/20 text-accent border-accent/30',
  red: 'bg-danger/20 text-danger border-danger/30',
  gray: 'bg-gray-500/20 text-gray-400 border-gray-500/30',
};

export default function SuggestionBadge({ suggestion, color }) {
  // Try suggestion-based style first, then color-based, then default
  const normalizedSuggestion = suggestion?.toUpperCase() || '';
  const style = suggestionStyles[normalizedSuggestion] || colorStyles[color] || colorStyles.gray;

  return (
    <span className={`inline-flex px-3 py-1 rounded-full text-xs font-bold border ${style}`}>
      {suggestion}
    </span>
  );
}
