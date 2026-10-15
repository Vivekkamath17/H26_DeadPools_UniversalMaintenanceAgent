// src/components/TestMatrix.tsx
import { Minus } from 'lucide-react';
import { Badge } from './Badge';

interface TestResult {
  command: string;
  exit_code: number;
  success: boolean;
  attempts: number;
  rolled_back: boolean;
  stdout_tail: string;
  stderr_tail: string;
  reflection_count: number;
}

interface TestMatrixProps {
  result: TestResult;
}

export function TestMatrix({ result }: TestMatrixProps) {
  const skipped = result.command === 'skipped';

  return (
    <div className="space-y-4">
      {/* Summary row */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        {[
          { label: 'Status',     value: skipped ? 'SKIPPED' : result.success ? 'PASSED' : 'FAILED',
            badge: skipped ? <Badge variant="slate">SKIPPED</Badge> : result.success ? <Badge variant="green">✓ PASSED</Badge> : <Badge variant="red">✗ FAILED</Badge> },
          { label: 'Exit Code',  value: String(result.exit_code) },
          { label: 'Attempts',   value: String(result.attempts) },
          { label: 'Rolled Back', value: String(result.rolled_back) },
          { label: 'Self-Healing Loops', value: String(result.reflection_count) },
        ].map(row => (
          <div key={row.label} className="bg-[#161b22] border border-[#30363d] rounded-lg p-3">
            <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">{row.label}</div>
            {row.badge
              ? row.badge
              : <span className="font-mono text-sm text-gray-200">{row.value}</span>
            }
          </div>
        ))}
      </div>

      {/* Command */}
      <div className="bg-[#0d1117] border border-[#30363d] rounded-lg p-3">
        <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-2 flex items-center gap-1">
          <Badge variant="blue">EMPIRICAL</Badge> Command Executed
        </div>
        <code className="text-xs text-blue-300 font-mono break-all">{result.command}</code>
      </div>

      {/* stdout */}
      {result.stdout_tail && (
        <div className="bg-[#0d1117] border border-[#30363d] rounded-lg overflow-hidden">
          <div className="px-3 py-1.5 bg-[#161b22] border-b border-[#30363d] text-[10px] text-gray-500 uppercase tracking-wider">
            Standard Output (tail)
          </div>
          <pre className="text-xs text-gray-300 font-mono p-3 overflow-x-auto whitespace-pre-wrap max-h-40">
            {result.stdout_tail || '(empty)'}
          </pre>
        </div>
      )}

      {/* stderr */}
      {result.stderr_tail && (
        <div className="bg-[#0d1117] border border-red-900/30 rounded-lg overflow-hidden">
          <div className="px-3 py-1.5 bg-red-950/30 border-b border-red-900/30 text-[10px] text-red-400 uppercase tracking-wider">
            Standard Error (tail)
          </div>
          <pre className="text-xs text-red-300 font-mono p-3 overflow-x-auto whitespace-pre-wrap max-h-40">
            {result.stderr_tail}
          </pre>
        </div>
      )}

      {skipped && (
        <div className="flex items-center gap-2 p-3 bg-slate-800/30 border border-slate-700/50 rounded-lg">
          <Minus size={14} className="text-slate-500" />
          <span className="text-xs text-slate-400">
            Sandbox execution was skipped via <code className="font-mono">--skip-sandbox</code>.
            All verification results are marked <strong>NOT_RUN</strong> and patches are advisory only.
          </span>
        </div>
      )}
    </div>
  );
}
