const statusStyles = {
  ACTIVE: 'bg-success/20 text-success',
  STARTED: 'bg-success/20 text-success',
  PAUSED: 'bg-warning/20 text-warning',
  STOPPED: 'bg-danger/20 text-danger',
  COMPLETED: 'bg-blue-500/20 text-blue-400',
  DRAFTED: 'bg-gray-500/20 text-gray-400',
  DRAFT: 'bg-gray-500/20 text-gray-400',
};

export default function StatusBadge({ status }) {
  const normalizedStatus = status?.toUpperCase() || 'DRAFT';
  const style = statusStyles[normalizedStatus] || statusStyles.DRAFT;

  return (
    <span className={`inline-flex px-2.5 py-1 rounded-full text-xs font-medium ${style}`}>
      {status}
    </span>
  );
}
