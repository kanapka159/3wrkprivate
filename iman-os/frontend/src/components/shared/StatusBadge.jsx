const statusStyles = {
  STARTED: 'bg-success/20 text-success',
  PAUSED: 'bg-warning/20 text-warning',
  STOPPED: 'bg-danger/20 text-danger',
  DRAFT: 'bg-gray-500/20 text-gray-400',
};

export default function StatusBadge({ status }) {
  const style = statusStyles[status] || statusStyles.DRAFT;

  return (
    <span className={`px-2 py-1 rounded text-xs font-medium ${style}`}>
      {status}
    </span>
  );
}
