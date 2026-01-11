import { Construction, ArrowLeft } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { PageHeader } from '../components/layout';
import { Button } from '../components/shared';

export default function PlaceholderPage({ title }) {
  const navigate = useNavigate();

  return (
    <div>
      <PageHeader title={title || 'Coming Soon'} />

      <div className="flex flex-col items-center justify-center py-24 text-center">
        <div className="w-20 h-20 rounded-full bg-secondary flex items-center justify-center mb-6">
          <Construction size={40} className="text-gray-500" />
        </div>

        <h2 className="text-2xl font-semibold text-white mb-2">Coming Soon</h2>
        <p className="text-gray-500 mb-8 max-w-md">
          This feature is currently under development. Check back later for updates.
        </p>

        <Button variant="secondary" onClick={() => navigate('/')}>
          <ArrowLeft size={16} />
          Back to Dashboard
        </Button>
      </div>
    </div>
  );
}
