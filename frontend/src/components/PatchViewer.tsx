// src/components/PatchViewer.tsx
import React from 'react';
import { useState } from 'react';
import { ChevronDown, ChevronRight, FileCode, Clock } from 'lucide-react';
import { Badge } from './Badge';

interface Patch {
  file?: string;
  description?: string;
  unified_diff?: string;
}

interface PatchViewerProps {
  patches: Patch[];
  sandboxSuccess?: boolean;
  sandboxSkipped?: boolean;
}

function diffLines(diff: string) {
  return diff.split('\n').map((line, i) => {
    let cls = 'text-gray-500';
    if (line.startsWith('+') && !line.startsWith('+++')) cls = 'text-emerald-400 bg-emerald-950/40';
    else if (line.startsWith('-') && !line.startsWith('---')) cls = 'text-red-400 bg-red-950/40';
    else if (line.startsWith('@@')) cls = 'text-blue-400 bg-blue-950/30';
    else if (line.startsWith('+++') || line.startsWith('---')) cls = 'text-gray-400';
    return (
      <div key={i} className={`px-3 py-px font-mono text-xs leading-5 whitespace-pre ${cls}`}>
        {line || ' '}
      </div>
    );
  });
}

export function PatchViewer({ patches, sandboxSuccess, sandboxSkipped }: PatchViewerProps) {
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});

  if (!patches.length) {
    return (
      <div className="text-center py-10 text-gray-600">
        <FileCode size={32} className="mx-auto mb-2 opacity-40" />
        <p className="text-sm">No automated patches proposed.</p>
      </div>
    );
  }

  const patchStatus = sandboxSkipped ? 'unverified' : sandboxSuccess ? 'applied' : 'failed';
  const statusBadge: Record<string, React.ReactElement> = {
    unverified: <Badge variant="slate"><Clock size={10} /> UNVERIFIED</Badge>,
    applied:    <Badge variant="green">✓ APPLIED</Badge>,
    failed:     <Badge variant="red">✗ FAILED</Badge>,
  };

  return (
    <div className="space-y-3">
      {patches.map((patch, i) => {
        const open = !!expanded[i];
        return (
          <div key={i} className="bg-[#0d1117] border border-[#30363d] rounded-lg overflow-hidden">
            <button
              onClick={() => setExpanded(e => ({ ...e, [i]: !e[i] }))}
              className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-[#161b22] transition-colors"
            >
              {open ? <ChevronDown size={14} className="text-gray-500" /> : <ChevronRight size={14} className="text-gray-500" />}
              <FileCode size={14} className="text-amber-400 flex-shrink-0" />
              <code className="text-sm text-amber-300 font-mono flex-1">{patch.file || 'unknown'}</code>
              <Badge variant="amber">AI PATCH</Badge>
              {statusBadge[patchStatus]}
            </button>
            {open && (
              <div className="border-t border-[#30363d]">
                {patch.description && (
                  <p className="px-4 py-2 text-xs text-gray-400 bg-[#161b22] border-b border-[#30363d]">
                    {patch.description}
                  </p>
                )}
                <div className="overflow-x-auto">
                  {patch.unified_diff
                    ? diffLines(patch.unified_diff)
                    : <p className="px-4 py-3 text-xs text-gray-600 italic">No unified diff available.</p>
                  }
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
