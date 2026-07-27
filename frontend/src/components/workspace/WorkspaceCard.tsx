import { Link } from 'react-router-dom';
import type { WorkspaceInfo } from '@/types';
import { cn } from '@/utils/helpers';

interface WorkspaceCardProps {
  workspace: WorkspaceInfo;
  className?: string;
}

const accentByType = {
  javascript: 'from-amber-400/20 via-transparent to-transparent',
  python: 'from-sky-400/20 via-transparent to-transparent',
  website: 'from-teal-400/20 via-transparent to-transparent',
} as const;

/**
 * Workspace selection card linking to the project dashboard.
 */
export function WorkspaceCard({ workspace, className }: WorkspaceCardProps) {
  return (
    <Link
      to={`/workspaces/${workspace.type}`}
      className={cn(
        'group relative overflow-hidden rounded-3xl border border-white/10 bg-ink-900/70 p-6 shadow-panel transition hover:-translate-y-1 hover:border-accent/40',
        className,
      )}
    >
      <div
        className={cn(
          'pointer-events-none absolute inset-0 bg-gradient-to-br opacity-90 transition group-hover:opacity-100',
          accentByType[workspace.type],
        )}
      />
      <div className="relative">
        <p className="text-xs uppercase tracking-[0.2em] text-accent-soft">{workspace.language_hint}</p>
        <h3 className="mt-3 font-display text-2xl text-sand-50">{workspace.title}</h3>
        <p className="mt-3 max-w-sm text-sm leading-6 text-slate-300">{workspace.description}</p>
        <span className="mt-6 inline-flex text-sm font-medium text-accent">Open workspace →</span>
      </div>
    </Link>
  );
}
