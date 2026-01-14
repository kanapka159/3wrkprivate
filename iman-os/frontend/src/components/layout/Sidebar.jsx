import {
  LayoutDashboard,
  Users,
  HeartPulse,
  Globe,
  RefreshCw,
  BarChart3,
  Rocket,
  Search,
  Settings,
} from 'lucide-react';
import SidebarItem from './SidebarItem';

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Ops Dashboard', disabled: false },
  { to: '/clients', icon: Users, label: 'Client Analytics', disabled: true },
  { to: '/campaigns', icon: HeartPulse, label: 'Campaign Health', disabled: false },
  { to: '/domains', icon: Globe, label: 'Domain Health', disabled: false },
  { to: '/domain-replace', icon: RefreshCw, label: 'Domain Replacement', disabled: true },
  { to: '/ab-analytics', icon: BarChart3, label: 'A/B Analytics', disabled: true },
  { to: '/launcher', icon: Rocket, label: 'Campaign Launcher', disabled: true },
  { to: '/leads', icon: Search, label: 'Lead Search', disabled: true },
  { to: '/settings', icon: Settings, label: 'Settings', disabled: false },
];

export default function Sidebar() {
  return (
    <aside className="w-60 h-screen bg-secondary flex flex-col fixed left-0 top-0">
      {/* Logo */}
      <div className="px-4 py-6 border-b border-gray-800">
        <h1 className="text-xl font-bold flex items-center gap-2">
          <span className="text-2xl">🎯</span>
          <span className="text-white">IMAN OS</span>
        </h1>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-4 overflow-y-auto">
        {navItems.map((item) => (
          <SidebarItem
            key={item.to}
            to={item.to}
            icon={item.icon}
            label={item.label}
            disabled={item.disabled}
          />
        ))}
      </nav>

      {/* Footer */}
      <div className="px-4 py-4 border-t border-gray-800 text-xs text-gray-600">
        v0.1.0
      </div>
    </aside>
  );
}
