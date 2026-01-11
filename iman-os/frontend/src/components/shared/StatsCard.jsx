export default function StatsCard({ title, value, subtitle, icon: Icon }) {
  return (
    <div className="bg-card rounded-lg p-6">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-gray-400 text-sm font-medium">{title}</p>
          <p className="text-3xl font-bold text-white mt-2">{value}</p>
          {subtitle && <p className="text-gray-500 text-sm mt-1">{subtitle}</p>}
        </div>
        {Icon && (
          <div className="p-3 bg-secondary rounded-lg">
            <Icon size={24} className="text-accent" />
          </div>
        )}
      </div>
    </div>
  );
}
