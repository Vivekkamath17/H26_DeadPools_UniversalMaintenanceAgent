// src/components/VerdictBanner.tsx
import { CheckCircle, AlertTriangle, XCircle, Clock } from 'lucide-react';

type Verdict = 'verified' | 'partial' | 'unverified' | 'failed';

interface VerdictBannerProps {
  success: boolean;
  skipped: boolean;
  riskCount: number;
  patchCount: number;
  claimsProven?: number;
  totalClaims?: number;
}

export function VerdictBanner({
  success, skipped, riskCount, patchCount, claimsProven = 0, totalClaims = 0
}: VerdictBannerProps) {
  let verdict: Verdict = 'unverified';
  if (skipped) verdict = 'unverified';
  else if (success && riskCount === 0) verdict = 'verified';
  else if (success) verdict = 'partial';
  else verdict = 'failed';

  const config = {
    verified:   { icon: CheckCircle,    text: 'VERIFIED',          sub: 'All tests passed and no critical risks detected.',          bg: 'from-emerald-950 to-emerald-900/30', border: 'border-emerald-700', color: 'text-emerald-400' },
    partial:    { icon: AlertTriangle,  text: 'PARTIALLY VERIFIED', sub: `Tests passed but ${riskCount} risk indicator(s) remain.`,  bg: 'from-amber-950   to-amber-900/30',   border: 'border-amber-700',   color: 'text-amber-400'   },
    unverified: { icon: Clock,          text: 'NOT VERIFIED',       sub: 'Sandbox execution was skipped. Diffs are AI-advisory only.', bg: 'from-slate-900   to-slate-800/20',   border: 'border-slate-700',   color: 'text-slate-400'   },
    failed:     { icon: XCircle,        text: 'FAILED',             sub: `Sandbox tests did not pass. ${patchCount > 0 ? 'Patches were rolled back.' : ''}`, bg: 'from-red-950 to-red-900/30', border: 'border-red-700', color: 'text-red-400' },
  }[verdict];

  const Icon = config.icon;

  return (
    <div className={`sticky top-0 z-40 bg-gradient-to-r ${config.bg} border-b ${config.border} px-6 py-3 flex items-center justify-between backdrop-blur-sm`}>
      <div className="flex items-center gap-3">
        <Icon size={22} className={config.color} />
        <div>
          <span className={`text-sm font-bold ${config.color} tracking-widest`}>{config.text}</span>
          <p className="text-xs text-gray-400 mt-0.5">{config.sub}</p>
        </div>
      </div>
      {totalClaims > 0 && (
        <div className="text-right">
          <span className="text-xs text-gray-400">Claims verified by execution</span>
          <div className="text-sm font-mono font-bold text-emerald-400 mt-0.5">
            {claimsProven} / {totalClaims}
          </div>
        </div>
      )}
    </div>
  );
}
