// src/pages/RunDashboard.tsx
import { useState, useEffect, useRef } from 'react';
import { ArrowLeft } from 'lucide-react';
import { subscribeToRun, getCapsule, getRunStatus, type AgentEvent, type Capsule } from '../api';
import { AgentStepper } from '../components/AgentStepper';
import { LogConsole } from '../components/LogConsole';
import { VerdictBanner } from '../components/VerdictBanner';
import { TrustMeter } from '../components/TrustMeter';
import { RiskList } from '../components/RiskList';
import { PatchViewer } from '../components/PatchViewer';
import { TestMatrix } from '../components/TestMatrix';
import { ExportBar } from '../components/ExportBar';
import { Badge } from '../components/Badge';

type TabKey = 'overview' | 'risks' | 'patches' | 'tests' | 'raw';

interface RunDashboardProps {
  runId: string;
  onBack: () => void;
}

export function RunDashboard({ runId, onBack }: RunDashboardProps) {
  const [events, setEvents]     = useState<AgentEvent[]>([]);
  const [capsule, setCapsule]   = useState<Capsule | null>(null);
  const [done, setDone]         = useState(false);
  const [tab, setTab]           = useState<TabKey>('overview');
  const unsubRef                = useRef<(() => void) | null>(null);

  useEffect(() => {
    // Check if run is already completed
    getRunStatus(runId).then(async (res) => {
      if (res.status === 'completed' || res.capsule_ready) {
        setDone(true);
        try {
          const c = await getCapsule(runId);
          setCapsule(c);
        } catch { /* ignore */ }
      }
    }).catch(() => {});

    const unsub = subscribeToRun(
      runId,
      (ev) => setEvents(prev => [...prev, ev]),
      async () => {
        setDone(true);
        for (let attempt = 0; attempt < 5; attempt++) {
          try {
            const c = await getCapsule(runId);
            setCapsule(c);
            break;
          } catch {
            await new Promise(r => setTimeout(r, 600));
          }
        }
      },
    );
    unsubRef.current = unsub;
    return () => unsub();
  }, [runId]);

  const isRunning = !done;
  const tests      = capsule?.executed_test_results;
  const risks      = capsule?.risk_indicators ?? [];
  let patches      = capsule?.recommended_patches ?? [];
  if (patches.length === 0 && capsule?.proposed_changes_or_maintenance_approach) {
    const text = capsule.proposed_changes_or_maintenance_approach;
    const diffMatch = text.match(/```diff\n([\s\S]*?)```/);
    if (diffMatch) {
      const fileMatch = text.match(/\[(.*?)\]/);
      patches = [{
        file: fileMatch ? fileMatch[1] : 'proposed_fix.patch',
        description: text.split('```')[0].trim(),
        unified_diff: diffMatch[1].trim(),
      }];
    }
  }
  const syntaxErrors = events
    .filter(e => e.type === 'agent_update' && e.phase === '1' && e.data?.syntax_errors)
    .flatMap(e => (e.data!.syntax_errors as Array<{file_path:string;line_number:number;message:string}>) ?? []);

  const sandboxSkipped = tests?.command === 'skipped';
  const sandboxSuccess = !!tests?.success;

  // Trust meter metrics
  const executed      = tests && !sandboxSkipped && sandboxSuccess ? 3 : 0;
  const observed      = capsule ? 4 : 0;
  const aiRecommended = risks.length + patches.length;
  const unverified    = sandboxSkipped ? 2 : 0;

  const tabs: { key: TabKey; label: string; count?: number }[] = [
    { key: 'overview', label: 'Overview' },
    { key: 'risks',    label: 'Risks',   count: risks.length + syntaxErrors.length },
    { key: 'patches',  label: 'Patches', count: patches.length },
    { key: 'tests',    label: 'Tests' },
    { key: 'raw',      label: 'Raw JSON' },
  ];

  return (
    <div className="min-h-screen bg-[#0d1117] flex flex-col">
      {/* Top navbar */}
      <div className="border-b border-[#30363d] px-4 py-3 flex items-center gap-3 bg-[#161b22]">
        <button onClick={onBack} className="text-gray-400 hover:text-gray-200 transition-colors p-1">
          <ArrowLeft size={16} />
        </button>
        <div className="flex-1 min-w-0">
          <h1 className="text-sm font-semibold text-gray-200 truncate">Run Dashboard</h1>
          <p className="text-[10px] font-mono text-gray-500 truncate">{runId}</p>
        </div>
        {isRunning && (
          <span className="flex items-center gap-1.5 text-xs text-blue-400">
            <span className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-pulse" />
            Live
          </span>
        )}
        {done && !capsule && (
          <Badge variant="amber">Processing…</Badge>
        )}
        {capsule && (
          <Badge variant="green">Complete</Badge>
        )}
      </div>

      {/* Verdict banner */}
      {capsule && (
        <VerdictBanner
          success={sandboxSuccess}
          skipped={sandboxSkipped}
          riskCount={risks.length}
          patchCount={patches.length}
          claimsProven={executed}
          totalClaims={executed + observed + aiRecommended + unverified}
        />
      )}

      <div className="flex flex-col lg:flex-row flex-1 gap-0 min-h-0">
        {/* Left sidebar */}
        <aside className="lg:w-72 xl:w-80 flex-shrink-0 border-b lg:border-b-0 lg:border-r border-[#30363d] p-4 space-y-4 overflow-y-auto">
          <AgentStepper events={events} />
          <LogConsole events={events} />
          {capsule && (
            <TrustMeter
              executed={executed}
              observed={observed}
              aiRecommended={aiRecommended}
              unverified={unverified}
            />
          )}
        </aside>

        {/* Main content */}
        <main className="flex-1 overflow-y-auto">
          {/* Tab bar */}
          <div className="flex border-b border-[#30363d] px-4 pt-2 gap-1 bg-[#161b22]">
            {tabs.map(t => (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                className={`flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-t transition-colors border-b-2
                  ${tab === t.key
                    ? 'border-emerald-500 text-emerald-400 bg-[#0d1117]'
                    : 'border-transparent text-gray-500 hover:text-gray-300'}`}
              >
                {t.label}
                {t.count !== undefined && t.count > 0 && (
                  <span className="bg-[#30363d] text-gray-400 text-[9px] px-1 rounded">{t.count}</span>
                )}
              </button>
            ))}
          </div>

          <div className="p-5 space-y-5 animate-fade-in">
            {!capsule && isRunning && (
              <div className="text-center py-20">
                <div className="w-8 h-8 border-2 border-emerald-500/30 border-t-emerald-500 rounded-full animate-spin-slow mx-auto mb-4" />
                <p className="text-sm text-gray-500">Agents working…</p>
              </div>
            )}

            {/* ─ Overview ─ */}
            {tab === 'overview' && capsule && (
              <div className="space-y-5">
                <ExportBar runId={runId} capsule={capsule} />

                <div className="bg-[#161b22] border border-[#30363d] rounded-lg p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <Badge variant="amber">AI ANALYSIS</Badge>
                    <h3 className="text-sm font-semibold text-gray-200">Problem Identified</h3>
                  </div>
                  <p className="text-sm text-gray-300 leading-relaxed">
                    {capsule.maintenance_problem_identified || '—'}
                  </p>
                </div>

                <div className="bg-[#161b22] border border-[#30363d] rounded-lg p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <Badge variant="amber">AI ADVISORY</Badge>
                    <h3 className="text-sm font-semibold text-gray-200">Maintenance Recommendation</h3>
                  </div>
                  <p className="text-sm text-gray-300 leading-relaxed whitespace-pre-wrap">
                    {capsule.proposed_changes_or_maintenance_approach || '—'}
                  </p>
                </div>

                {capsule.compatibility_or_maintenance_gaps?.length > 0 && (
                  <div className="bg-[#161b22] border border-amber-800/30 rounded-lg p-4">
                    <div className="flex items-center gap-2 mb-3">
                      <Badge variant="amber">GAPS</Badge>
                      <h3 className="text-sm font-semibold text-gray-200">Compatibility Gaps</h3>
                    </div>
                    <ul className="space-y-1.5">
                      {capsule.compatibility_or_maintenance_gaps.map((g, i) => (
                        <li key={i} className="text-sm text-amber-200/80 flex gap-2">
                          <span className="text-amber-600 mt-0.5">›</span> {g}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {capsule.unresolved_concerns_and_limitations?.length > 0 && (
                  <div className="bg-[#161b22] border border-red-800/20 rounded-lg p-4">
                    <div className="flex items-center gap-2 mb-3">
                      <Badge variant="red">UNRESOLVED</Badge>
                      <h3 className="text-sm font-semibold text-gray-200">Concerns & Limitations</h3>
                    </div>
                    <ul className="space-y-1.5">
                      {capsule.unresolved_concerns_and_limitations.map((u, i) => (
                        <li key={i} className="text-sm text-red-200/70 flex gap-2">
                          <span className="text-red-600 mt-0.5">›</span> {u}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {capsule.suggested_tests_or_verification_steps?.length > 0 && (
                  <div className="bg-[#161b22] border border-blue-800/30 rounded-lg p-4">
                    <div className="flex items-center gap-2 mb-3">
                      <Badge variant="blue">AI ADVISORY</Badge>
                      <h3 className="text-sm font-semibold text-gray-200">Suggested Verification Steps</h3>
                    </div>
                    <ol className="space-y-1.5 list-decimal list-inside">
                      {capsule.suggested_tests_or_verification_steps.map((s, i) => (
                        <li key={i} className="text-sm text-blue-200/80">{s}</li>
                      ))}
                    </ol>
                  </div>
                )}

                {capsule._meta && (
                  <div className="flex flex-wrap gap-3 text-[10px] text-gray-600 font-mono">
                    <span>Generated: {capsule._meta.generated_at}</span>
                    <span>Backend: {capsule._meta.backend_used}</span>
                    <span>Schema: {capsule._meta.schema_version}</span>
                  </div>
                )}
              </div>
            )}

            {/* ─ Risks ─ */}
            {tab === 'risks' && (
              <RiskList risks={risks} syntaxErrors={syntaxErrors} />
            )}

            {/* ─ Patches ─ */}
            {tab === 'patches' && capsule && (
              <PatchViewer
                patches={patches}
                sandboxSuccess={sandboxSuccess}
                sandboxSkipped={sandboxSkipped}
              />
            )}

            {/* ─ Tests ─ */}
            {tab === 'tests' && (
              tests
                ? <TestMatrix result={tests} />
                : <p className="text-sm text-gray-500 text-center py-10">Waiting for sandbox data…</p>
            )}

            {/* ─ Raw JSON ─ */}
            {tab === 'raw' && capsule && (
              <div className="bg-[#0d1117] border border-[#30363d] rounded-lg overflow-hidden">
                <div className="flex items-center gap-2 px-4 py-2 bg-[#161b22] border-b border-[#30363d]">
                  <Badge variant="blue">RAW JSON</Badge>
                  <span className="text-xs text-gray-400">Dependency Exit Capsule</span>
                </div>
                <pre className="text-xs text-gray-300 font-mono p-4 overflow-x-auto whitespace-pre-wrap">
                  {JSON.stringify(capsule, null, 2)}
                </pre>
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
