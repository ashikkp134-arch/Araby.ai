import type { PropsWithChildren } from 'react';
import { cn } from '@/utils/helpers';

interface SpinnerProps {
  className?: string;
  label?: string;
}

/**
 * Lightweight loading spinner.
 */
export function Spinner({ className, label = 'Loading' }: SpinnerProps) {
  return (
    <div className={cn('flex items-center gap-3 text-slate-300', className)} role="status">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-accent/30 border-t-accent" />
      <span className="text-sm">{label}</span>
    </div>
  );
}

interface EmptyStateProps {
  title: string;
  description?: string;
}

/**
 * Empty-state placeholder for lists and panels.
 */
export function EmptyState({ title, description }: EmptyStateProps) {
  return (
    <div className="rounded-xl border border-dashed border-white/10 px-6 py-10 text-center">
      <h3 className="font-display text-lg text-sand-50">{title}</h3>
      {description ? <p className="mt-2 text-sm text-slate-400">{description}</p> : null}
    </div>
  );
}

/**
 * Simple modal shell.
 */
export function Modal({
  title,
  children,
  onClose,
}: PropsWithChildren<{ title: string; onClose: () => void }>) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="glass-panel w-full max-w-md rounded-2xl p-6 shadow-panel animate-rise">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-display text-xl">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md px-2 py-1 text-slate-400 hover:bg-white/5 hover:text-white"
          >
            Close
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
