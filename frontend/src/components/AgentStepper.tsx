// src/components/AgentStepper.tsx
import { Check, Loader, Minus, AlertTriangle } from 'lucide-react';
import type { AgentEvent } from '../api';

interface AgentStep {
  phase: string;
  name: string;
  status: 'waiting' | 'running' | 'done' | 'skipped' | 'warning' | 'error';
  message?: string;
  elapsed?: number;
}

interface AgentStepperProps {
  events: AgentEvent[];
  startedAt?: number;
}

const AGENT_PHASES = [
  { phase: '1', name: 'Inspector + Tree-Sitter AST' },
  { phase: '2', name: 'Diagnostic Agent (CoV)' },
  { phase: '3', name: 'Sandbox Agent' },
  { phase: '4', name: 'Capsule Compiler' },
  { phase: '5', name: 'PR Agent' },
];

function buildSteps(events: AgentEvent[]): AgentStep[] {
  const stepMap: Record<string, AgentStep> = {};

  AGENT_PHASES.forEach(({ phase, name }) => {
    stepMap[phase] = { phase, name, status: 'waiting' };
  });

  events.forEach(ev => {
    if (ev.type === 'agent_update' && ev.phase) {
      const s = stepMap[ev.phase];
      if (s) {
        s.status = (ev.status as AgentStep['status']) || 'running';
        s.message = ev.message;
      }
    }
  });

  return AGENT_PHASES.map(({ phase }) => stepMap[phase]);
}

function StepIcon({ status }: { status: AgentStep['status'] }) {
  if (status === 'running')  return <Loader size={14} className="animate-spin-slow text-blue-400" />;
  if (status === 'done')     return <Check size={14} className="text-emerald-400" />;
  if (status === 'skipped')  return <Minus size={14} className="text-slate-500" />;
  if (status === 'warning')  return <AlertTriangle size={14} className="text-amber-400" />;
  if (status === 'error')    return <AlertTriangle size={14} className="text-red-400" />;
  return <div className="w-3.5 h-3.5 rounded-full border border-[#30363d]" />;
}

const statusBg: Record<AgentStep['status'], string> = {
  waiting: 'bg-[#21262d] border-[#30363d]',
  running: 'bg-blue-950/40  border-blue-700',
  done:    'bg-emerald-950/40 border-emerald-700',
  skipped: 'bg-slate-800/40 border-slate-700',
  warning: 'bg-amber-950/40 border-amber-700',
  error:   'bg-red-950/40   border-red-700',
};

export function AgentStepper({ events }: AgentStepperProps) {
  const steps = buildSteps(events);

  return (
    <div className="bg-[#161b22] border border-[#30363d] rounded-lg p-4">
      <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-4">
        Agent Pipeline
      </h3>
      <div className="flex flex-col gap-2">
        {steps.map((step, i) => (
          <div key={step.phase} className="flex items-start gap-3">
            {/* Phase connector */}
            <div className="flex flex-col items-center">
              <div className={`w-7 h-7 rounded-full border flex items-center justify-center flex-shrink-0 ${statusBg[step.status]}`}>
                <StepIcon status={step.status} />
              </div>
              {i < steps.length - 1 && (
                <div className="w-px flex-1 min-h-[1rem] bg-[#30363d] mt-1" />
              )}
            </div>
            <div className="flex-1 pb-2">
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-500 font-mono">Phase {step.phase}</span>
                <span className="text-sm font-medium text-gray-200">{step.name}</span>
              </div>
              {step.message && (
                <p className="text-xs text-gray-500 mt-0.5 line-clamp-2 font-mono">{step.message}</p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
