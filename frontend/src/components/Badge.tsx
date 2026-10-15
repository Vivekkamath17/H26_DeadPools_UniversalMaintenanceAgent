// src/components/Badge.tsx
interface BadgeProps {
  variant: 'green' | 'blue' | 'amber' | 'red' | 'slate';
  children: React.ReactNode;
  className?: string;
}

const variantStyles: Record<BadgeProps['variant'], string> = {
  green: 'bg-emerald-950 text-emerald-400 border-emerald-800',
  blue:  'bg-blue-950  text-blue-400  border-blue-800',
  amber: 'bg-amber-950 text-amber-400 border-amber-800',
  red:   'bg-red-950   text-red-400   border-red-800',
  slate: 'bg-slate-800 text-slate-400 border-slate-700',
};

export function Badge({ variant, children, className = '' }: BadgeProps) {
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-bold border ${variantStyles[variant]} ${className}`}>
      {children}
    </span>
  );
}
