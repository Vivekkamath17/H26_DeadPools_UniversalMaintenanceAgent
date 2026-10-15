// src/components/RiskList.tsx
import { AlertTriangle, Shield } from 'lucide-react';
import { Badge } from './Badge';

interface RiskListProps {
  risks: string[];
  syntaxErrors?: Array<{ file_path: string; line_number: number; message: string }>;
}

export function RiskList({ risks, syntaxErrors = [] }: RiskListProps) {
  if (!risks.length && !syntaxErrors.length) {
    return (
      <div className="text-center py-10 text-gray-600">
        <Shield size={32} className="mx-auto mb-2 text-emerald-700 opacity-60" />
        <p className="text-sm text-emerald-600">No risk indicators identified.</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {syntaxErrors.map((err, i) => (
        <div key={`syn-${i}`} className="flex gap-3 p-3 bg-red-950/30 border border-red-800/50 rounded-lg animate-fade-in">
          <AlertTriangle size={16} className="text-red-400 flex-shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap mb-1">
              <Badge variant="red">AST SYNTAX ERROR</Badge>
              <code className="text-xs text-red-300 font-mono">{err.file_path}:{err.line_number}</code>
            </div>
            <p className="text-xs text-red-200 font-mono break-all">{err.message}</p>
          </div>
        </div>
      ))}

      {risks.map((risk, i) => (
        <div key={i} className="flex gap-3 p-3 bg-amber-950/20 border border-amber-800/30 rounded-lg animate-fade-in">
          <AlertTriangle size={16} className="text-amber-400 flex-shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <Badge variant="amber">AI ADVISORY</Badge>
            </div>
            <p className="text-sm text-gray-200">{risk}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
