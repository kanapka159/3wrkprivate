const colorStyles = {
  green: 'bg-success/20 text-success border-success/30',
  yellow: 'bg-warning/20 text-warning border-warning/30',
  orange: 'bg-accent/20 text-accent border-accent/30',
  red: 'bg-danger/20 text-danger border-danger/30',
  gray: 'bg-gray-500/20 text-gray-400 border-gray-500/30',
};

export default function SuggestionBadge({ suggestion, color }) {
  const style = colorStyles[color] || colorStyles.gray;

  return (
    <span className={`px-3 py-1 rounded-full text-xs font-bold border ${style}`}>
      {suggestion}
    </span>
  );
}
