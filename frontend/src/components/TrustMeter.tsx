// src/components/TrustMeter.tsx

interface Segment {
  label: string;
  count: number;
  color: string;
  bg: string;
}

interface TrustMeterProps {
  observed: number;
  executed: number;
  aiRecommended: number;
  unverified: number;
}

export function TrustMeter({ observed, executed, aiRecommended, unverified }: TrustMeterProps) {
  const total = observed + executed + aiRecommended + unverified;

  const segments: Segment[] = [
    { label: 'EXECUTED',       count: executed,      color: 'bg-emerald-500', bg: 'bg-emerald-950/60' },
    { label: 'OBSERVED FACT',  count: observed,       color: 'bg-blue-500',    bg: 'bg-blue-950/60'    },
    { label: 'AI RECOMMENDED', count: aiRecommended,  color: 'bg-amber-500',   bg: 'bg-amber-950/60'   },
    { label: 'UNVERIFIED',     count: unverified,     color: 'bg-slate-600',   bg: 'bg-slate-800/60'   },
  ].filter(s => s.count > 0);

  return (
    <div className="bg-[#161b22] border border-[#30363d] rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-300">Trust Meter</h3>
        <span className="text-xs text-gray-500 font-mono">{total} total claims</span>
      </div>

      {/* Segmented bar */}
      <div className="flex h-3 rounded-full overflow-hidden gap-0.5 mb-4">
        {total === 0 ? (
          <div className="flex-1 bg-[#30363d] rounded-full" />
        ) : segments.map((s) => (
          <div
            key={s.label}
            className={`${s.color} transition-all`}
            style={{ width: `${(s.count / total) * 100}%` }}
            title={`${s.label}: ${s.count}`}
          />
        ))}
      </div>

      {/* Legend */}
      <div className="grid grid-cols-2 gap-2">
        {segments.map((s) => (
          <div key={s.label} className={`flex items-center justify-between ${s.bg} rounded px-2 py-1.5 border border-white/5`}>
            <div className="flex items-center gap-2">
              <div className={`w-2 h-2 rounded-full ${s.color}`} />
              <span className="text-[10px] text-gray-400 font-mono tracking-wide">{s.label}</span>
            </div>
            <span className="text-xs font-bold text-gray-200">{s.count}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
