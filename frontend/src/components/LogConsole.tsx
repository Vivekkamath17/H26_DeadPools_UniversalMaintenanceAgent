// src/components/LogConsole.tsx
import { useEffect, useRef } from 'react';
import { Terminal } from 'lucide-react';
import type { AgentEvent } from '../api';

interface LogConsoleProps {
  events: AgentEvent[];
}

export function LogConsole({ events }: LogConsoleProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [events]);

  const logLines = events.filter(e => e.type === 'agent_update' && e.message);

  return (
    <div className="bg-[#0d1117] border border-[#30363d] rounded-lg overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-2 bg-[#161b22] border-b border-[#30363d]">
        <Terminal size={14} className="text-emerald-400" />
        <span className="text-xs font-mono text-gray-400">Agent Log Stream</span>
        <span className="ml-auto text-[10px] text-gray-600">{logLines.length} events</span>
      </div>
      <div className="h-48 overflow-y-auto p-3 space-y-1 font-mono text-xs">
        {logLines.length === 0 && (
          <p className="text-gray-600 italic">Waiting for agent output...</p>
        )}
        {logLines.map((ev, i) => (
          <div key={i} className="flex gap-2 items-start animate-fade-in">
            <span className="text-gray-600 flex-shrink-0 tabular-nums">
              {new Date(ev.ts * 1000).toISOString().substring(11, 19)}
            </span>
            <span className={
              ev.status === 'done'    ? 'text-emerald-400' :
              ev.status === 'running' ? 'text-blue-400' :
              ev.status === 'error'   ? 'text-red-400' :
              ev.status === 'warning' ? 'text-amber-400' :
              ev.status === 'skipped' ? 'text-slate-500' :
              'text-gray-300'
            }>
              [{ev.phase ? `Phase ${ev.phase}` : ev.type}] {ev.message}
            </span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
