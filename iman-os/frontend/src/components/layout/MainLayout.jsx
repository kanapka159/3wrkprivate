import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';

export default function MainLayout() {
  return (
    <div className="min-h-screen bg-primary">
      <Sidebar />
      <main className="ml-60 p-8">
        <Outlet />
      </main>
    </div>
  );
}
