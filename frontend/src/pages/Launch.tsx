// src/pages/Launch.tsx
import { useState, useEffect } from 'react';
import { Search, Zap, AlertTriangle, ChevronRight } from 'lucide-react';
import { createRun, fetchRepoMeta, type RunRequest, type RepoMeta } from '../api';
import { RepoPreviewCard } from '../components/RepoPreviewCard';

const GITHUB_RE = /^https:\/\/github\.com\/[\w.-]+\/[\w.-]+\/?$/;

interface LaunchProps {
  onRunCreated: (runId: string) => void;
}

export function Launch({ onRunCreated }: LaunchProps) {
  const [url, setUrl]               = useState('https://github.com/rishrek/LinkWatch');
  const provider: RunRequest['provider'] = 'gemini';
  const [skipSandbox, setSkip]      = useState(true);
  const [repoMeta, setRepoMeta]     = useState<RepoMeta | null>(null);
  const [loading, setLoading]       = useState(false);
  const [error, setError]           = useState('');
  const [urlValid, setUrlValid]     = useState(false);

  // Live repo preview on valid URL
  useEffect(() => {
    const valid = GITHUB_RE.test(url.trim());
    setUrlValid(valid);
    if (!valid) { setRepoMeta(null); return; }
    const tid = setTimeout(async () => {
      const meta = await fetchRepoMeta(url.trim());
      setRepoMeta(meta);
    }, 600);
    return () => clearTimeout(tid);
  }, [url]);

  const handleSubmit = async () => {
    if (!urlValid) return;
    setLoading(true); setError('');
    try {
      const run = await createRun({ url: url.trim(), provider, skip_sandbox: skipSandbox });
      onRunCreated(run.run_id);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to start run');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#0d1117] flex flex-col">
      {/* Header */}
      <header className="border-b border-[#30363d] px-6 py-4 flex items-center gap-3">
        <div className="w-8 h-8 bg-emerald-500 rounded-lg flex items-center justify-center">
          <Zap size={16} className="text-white" />
        </div>
        <div>
          <h1 className="text-sm font-bold text-white tracking-tight">Universal Maintenance Agent</h1>
          <p className="text-[10px] text-gray-500">Agent Skills Open Standard · Track 2</p>
        </div>
      </header>

      <main className="flex-1 flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-2xl space-y-6 animate-fade-in">
          {/* Hero */}
          <div className="text-center space-y-2">
            <div className="inline-flex items-center gap-2 px-3 py-1 bg-emerald-950/60 border border-emerald-800 rounded-full text-xs text-emerald-400 mb-2">
              <span className="w-1.5 h-1.5 bg-emerald-400 rounded-full pulse-green" />
              v1.1.0 — Tree-Sitter · Gemini CoV · PR Automation
            </div>
            <h2 className="text-3xl font-bold text-white">Audit any repository</h2>
            <p className="text-gray-400 text-sm max-w-md mx-auto">
              Zero-hallucination dependency analysis using AST inspection, Chain-of-Verification AI reasoning, and empirical sandbox testing.
            </p>
          </div>

          {/* Input card */}
          <div className="bg-[#161b22] border border-[#30363d] rounded-xl overflow-hidden">
            {/* URL input */}
            <div className="p-5 border-b border-[#30363d]">
              <label className="text-xs text-gray-400 uppercase tracking-wider font-medium block mb-2">
                GitHub Repository URL
              </label>
              <div className="relative">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
                <input
                  type="url"
                  value={url}
                  onChange={e => setUrl(e.target.value)}
                  placeholder="https://github.com/owner/repository"
                  className={`w-full bg-[#0d1117] border rounded-lg pl-9 pr-4 py-2.5 text-sm font-mono text-gray-200 outline-none transition-colors
                    ${urlValid ? 'border-emerald-700 focus:border-emerald-500' : url ? 'border-red-800 focus:border-red-600' : 'border-[#30363d] focus:border-blue-700'}`}
                />
                {url && (
                  <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs">
                    {urlValid ? '✓' : '✗'}
                  </span>
                )}
              </div>
              {url && !urlValid && (
                <p className="text-xs text-red-400 mt-1 flex items-center gap-1">
                  <AlertTriangle size={10} /> Must be a valid GitHub URL: https://github.com/owner/repo
                </p>
              )}
            </div>

            {/* Config */}
            <div className="p-5">
              <div>
                <label className="text-xs text-gray-400 uppercase tracking-wider font-medium block mb-2">
                  Execution Options
                </label>
                <button
                  onClick={() => setSkip(!skipSandbox)}
                  className={`w-full flex items-center gap-3 p-3 rounded-lg border transition-all text-left
                    ${skipSandbox
                      ? 'bg-slate-900 border-slate-700'
                      : 'bg-emerald-950/40 border-emerald-800'}`}
                >
                  <div className={`w-9 h-5 rounded-full transition-colors relative flex-shrink-0
                    ${skipSandbox ? 'bg-slate-700' : 'bg-emerald-500'}`}>
                    <div className={`w-3.5 h-3.5 bg-white rounded-full absolute top-0.75 transition-transform
                      ${skipSandbox ? 'left-0.75' : 'translate-x-4 left-0.75'}`} />
                  </div>
                  <div>
                    <div className="text-xs font-medium text-gray-300">
                      {skipSandbox ? 'Skip Sandbox' : 'Run Sandbox'}
                    </div>
                    <div className="text-[10px] text-gray-500">
                      {skipSandbox ? 'Audit only — no patches applied' : 'Applies & verifies patches'}
                    </div>
                  </div>
                </button>
                {skipSandbox && (
                  <p className="text-[10px] text-amber-500 mt-1.5 flex items-center gap-1">
                    <AlertTriangle size={9} />
                    Patches marked as UNVERIFIED — not empirically tested
                  </p>
                )}
              </div>
            </div>

            {/* Repo preview */}
            {repoMeta && (
              <div className="px-5 pb-4">
                <RepoPreviewCard meta={repoMeta} />
              </div>
            )}

            {/* Submit */}
            <div className="px-5 pb-5">
              {error && (
                <div className="mb-3 p-3 bg-red-950/40 border border-red-800 rounded-lg text-xs text-red-300 flex items-center gap-2">
                  <AlertTriangle size={12} /> {error}
                </div>
              )}
              <button
                onClick={handleSubmit}
                disabled={!urlValid || loading}
                className="w-full flex items-center justify-center gap-2 py-3 bg-emerald-600 hover:bg-emerald-500 disabled:bg-[#21262d] disabled:text-gray-600
                  disabled:cursor-not-allowed text-white font-semibold rounded-lg transition-all text-sm"
              >
                {loading ? (
                  <><span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin-slow" />Starting…</>
                ) : (
                  <>Run Maintenance Audit <ChevronRight size={16} /></>
                )}
              </button>
            </div>
          </div>

          {/* Feature pills */}
          <div className="flex flex-wrap justify-center gap-2 text-[10px] text-gray-600">
            {['Tree-Sitter AST', 'Chain-of-Verification', 'Sandbox Self-Healing',
              'Schema-Validated Capsule', 'Interactive PR Agent'].map(f => (
              <span key={f} className="px-2 py-1 bg-[#161b22] border border-[#30363d] rounded-full">{f}</span>
            ))}
          </div>
        </div>
      </main>
    </div>
  );
}
