import { useState } from 'react';
import type { DiffLine, FileChangeProposal } from '@/types';
import { cn } from '@/utils/helpers';

interface AppliedChangesProps {
  changes: FileChangeProposal[];
  /** Open the changed file in the editor. */
  onOpenFile?: (path: string) => void;
}

const ACTION_LABELS: Record<string, string> = {
  create: 'new file',
  update: 'edited',
  delete: 'deleted',
};

const LINE_STYLES: Record<DiffLine['type'], string> = {
  add: 'bg-emerald-500/10 text-emerald-200',
  remove: 'bg-rose-500/10 text-rose-200',
  context: 'text-slate-400',
};

const LINE_SIGNS: Record<DiffLine['type'], string> = {
  add: '+',
  remove: '-',
  context: ' ',
};

/**
 * Review panel for a chat message's applied file changes: one row per file
 * with its added/removed line counts, expanding into the actual line diff.
 */
export function AppliedChanges({ changes, onOpenFile }: AppliedChangesProps) {
  const [expandedPath, setExpandedPath] = useState<string | null>(
    changes.length === 1 ? changes[0].path : null,
  );

  if (!changes.length) {
    return null;
  }

  return (
    <div className="mt-2 space-y-1.5">
      {changes.map((change) => {
        const diff = change.diff;
        const expanded = expandedPath === change.path;
        return (
          <div
            key={`${change.action}-${change.path}`}
            className="overflow-hidden rounded-lg border border-white/10 bg-ink-950/60"
          >
            <div className="flex items-center gap-2 px-2 py-1.5">
              <button
                type="button"
                onClick={() => setExpandedPath(expanded ? null : change.path)}
                className="flex min-w-0 flex-1 items-center gap-2 text-left"
              >
                <span className="w-2 shrink-0 text-[10px] text-slate-500">
                  {expanded ? '▾' : '▸'}
                </span>
                <span
                  className="truncate font-mono text-[11px] text-sand-50"
                  title={change.path}
                >
                  {change.path}
                </span>
                <span className="shrink-0 rounded bg-white/5 px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-slate-400">
                  {ACTION_LABELS[change.action] || change.action}
                </span>
              </button>
              {diff ? (
                <span className="shrink-0 font-mono text-[10px]">
                  <span className="text-emerald-300">+{diff.additions}</span>{' '}
                  <span className="text-rose-300">−{diff.deletions}</span>
                </span>
              ) : null}
              {onOpenFile && change.action !== 'delete' ? (
                <button
                  type="button"
                  onClick={() => onOpenFile(change.path)}
                  className="shrink-0 text-[10px] text-accent hover:underline"
                >
                  Open
                </button>
              ) : null}
            </div>

            {expanded ? <DiffBody change={change} /> : null}
          </div>
        );
      })}
    </div>
  );
}

/**
 * Render the hunks of a single file change, or an explanation when no line
 * diff is available.
 *
 * @param change - Applied file change to render.
 */
function DiffBody({ change }: { change: FileChangeProposal }) {
  const diff = change.diff;

  if (!diff) {
    return (
      <p className="border-t border-white/10 px-2 py-1.5 text-[11px] text-slate-500">
        No line diff was recorded for this change.
      </p>
    );
  }

  if (!diff.hunks.length) {
    return (
      <p className="border-t border-white/10 px-2 py-1.5 text-[11px] text-slate-500">
        {diff.truncated
          ? `Diff too large to display (+${diff.additions} / −${diff.deletions} lines).`
          : 'File content is unchanged.'}
      </p>
    );
  }

  return (
    <div className="border-t border-white/10">
      <div className="max-h-72 overflow-auto">
        {diff.hunks.map((hunk) => (
          <div key={`${hunk.old_start}-${hunk.new_start}`}>
            <div className="bg-ink-900/70 px-2 py-0.5 font-mono text-[10px] text-slate-500">
              @@ -{hunk.old_start},{hunk.old_lines} +{hunk.new_start},{hunk.new_lines} @@
            </div>
            {hunk.lines.map((line, index) => (
              <div
                key={`${hunk.new_start}-${index}`}
                className={cn(
                  'flex items-start font-mono text-[11px] leading-5',
                  LINE_STYLES[line.type],
                )}
              >
                <span className="w-8 shrink-0 select-none pr-1 text-right text-slate-600">
                  {line.old_line ?? ''}
                </span>
                <span className="w-8 shrink-0 select-none pr-1 text-right text-slate-600">
                  {line.new_line ?? ''}
                </span>
                <span className="w-3 shrink-0 select-none text-center opacity-70">
                  {LINE_SIGNS[line.type]}
                </span>
                <pre className="whitespace-pre pr-2">{line.content || ' '}</pre>
              </div>
            ))}
          </div>
        ))}
      </div>
      {diff.truncated ? (
        <p className="border-t border-white/10 px-2 py-1 text-[10px] text-slate-500">
          Diff truncated — showing the first hunks only.
        </p>
      ) : null}
    </div>
  );
}
