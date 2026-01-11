import { Construction } from 'lucide-react';
import { PageHeader } from '../components/layout';

export default function PlaceholderPage({ title }) {
  return (
    <div>
      <PageHeader title={title || 'Coming Soon'} />

      <div className="flex flex-col items-center justify-center py-24 text-center">
        <Construction size={64} className="text-gray-600 mb-4" />
        <h2 className="text-xl font-medium text-gray-400 mb-2">Under Construction</h2>
        <p className="text-gray-600">This feature is coming soon.</p>
      </div>
    </div>
  );
}
