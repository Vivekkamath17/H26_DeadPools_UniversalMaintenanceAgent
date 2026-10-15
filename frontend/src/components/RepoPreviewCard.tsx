// src/components/RepoPreviewCard.tsx
import { Star, Calendar, Code } from 'lucide-react';
import type { RepoMeta } from '../api';

interface RepoPreviewCardProps {
  meta: RepoMeta;
}

export function RepoPreviewCard({ meta }: RepoPreviewCardProps) {
  const updatedDays = Math.floor(
    (Date.now() - new Date(meta.updated_at).getTime()) / (1000 * 86400)
  );

  return (
    <div className="border border-[#30363d] bg-[#161b22] rounded-lg p-4 animate-fade-in">
      <div className="flex items-start justify-between gap-2 mb-2">
        <div>
          <a
            href={`https://github.com/${meta.full_name}`}
            target="_blank" rel="noreferrer"
            className="text-blue-400 hover:text-blue-300 text-sm font-semibold font-mono transition-colors"
          >
            {meta.full_name}
          </a>
          {meta.description && (
            <p className="text-xs text-gray-400 mt-1 line-clamp-2">{meta.description}</p>
          )}
        </div>
      </div>
      <div className="flex flex-wrap gap-3 mt-3">
        {meta.language && (
          <span className="flex items-center gap-1 text-xs text-gray-400">
            <Code size={12} className="text-amber-400" /> {meta.language}
          </span>
        )}
        <span className="flex items-center gap-1 text-xs text-gray-400">
          <Star size={12} className="text-yellow-400" /> {meta.stargazers_count.toLocaleString()}
        </span>
        <span className="flex items-center gap-1 text-xs text-gray-400">
          <Calendar size={12} className="text-blue-400" /> Updated {updatedDays}d ago
        </span>
      </div>
    </div>
  );
}
