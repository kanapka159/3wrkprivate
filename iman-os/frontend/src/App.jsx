import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { MainLayout } from './components/layout';
import { Dashboard, CampaignHealth, DomainHealth, Settings, PlaceholderPage } from './pages';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<MainLayout />}>
          <Route index element={<Dashboard />} />
          <Route path="campaigns" element={<CampaignHealth />} />
          <Route path="settings" element={<Settings />} />
          {/* Placeholder routes for disabled items */}
          <Route path="clients" element={<PlaceholderPage title="Client Analytics" />} />
          <Route path="domains" element={<DomainHealth />} />
          <Route path="domain-replace" element={<PlaceholderPage title="Domain Replacement" />} />
          <Route path="ab-analytics" element={<PlaceholderPage title="A/B Analytics" />} />
          <Route path="launcher" element={<PlaceholderPage title="Campaign Launcher" />} />
          <Route path="leads" element={<PlaceholderPage title="Lead Search" />} />
          <Route path="*" element={<PlaceholderPage title="Not Found" />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
