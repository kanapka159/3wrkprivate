export default function WarningBadge({ text }) {
  return (
    <span className="inline-flex px-2 py-0.5 rounded-full text-xs font-medium bg-accent/20 text-accent">
      {text}
    </span>
  );
}
