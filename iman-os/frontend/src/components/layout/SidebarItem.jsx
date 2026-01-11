import { NavLink } from 'react-router-dom';

export default function SidebarItem({ to, icon: Icon, label, disabled = false }) {
  if (disabled) {
    return (
      <div className="flex items-center gap-3 px-4 py-3 text-gray-600 cursor-not-allowed">
        <Icon size={20} />
        <span>{label}</span>
      </div>
    );
  }

  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `flex items-center gap-3 px-4 py-3 transition-colors ${
          isActive
            ? 'text-accent border-l-2 border-accent bg-secondary/50'
            : 'text-gray-400 hover:text-white hover:bg-secondary/30'
        }`
      }
    >
      <Icon size={20} />
      <span>{label}</span>
    </NavLink>
  );
}
