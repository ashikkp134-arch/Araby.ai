import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import type { ChatMessage } from '@/types';
import { AppliedChanges } from '@/components/chat/AppliedChanges';
import { Button } from '@/components/common/Button';
import { cn } from '@/utils/helpers';

interface ChatPanelProps {
  messages: ChatMessage[];
  isSending: boolean;
  streamingContent?: string;
  onSend: (content: string) => Promise<void>;
  onCancel?: () => void;
  appliedChangesCount?: number;
  /** Assistant message holding the most recent change set. */
  appliedChangesMessageId?: string;
  canUndo?: boolean;
  undoPending?: boolean;
  onUndo?: () => void;
  /** Open a changed file in the editor from the diff review. */
  onOpenFile?: (path: string) => void;
}

/**
 * Hide structured file fences while streaming so the explanation shows first.
 *
 * @param raw - Raw streamed assistant text.
 * @returns Display text without ```file blocks.
 */
function stripFileFences(raw: string): string {
  return raw
    .replace(/```file\s+path=[^\n]*\n[\s\S]*?(```|$)/gi, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

/**
 * Project-scoped AI chat panel with live streaming display, an independent
 * scroll container, and Applied Changes / Undo controls.
 */
export function ChatPanel({
  messages,
  isSending,
  streamingContent = '',
  onSend,
  onCancel,
  appliedChangesCount = 0,
  appliedChangesMessageId,
  canUndo = false,
  undoPending = false,
  onUndo,
  onOpenFile,
}: ChatPanelProps) {
  const [draft, setDraft] = useState('');
  // Assistant message whose file diff is currently expanded, if any.
  const [openDiffId, setOpenDiffId] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);
  const diffRefs = useRef(new Map<string, HTMLDivElement>());
  const liveText = useMemo(() => stripFileFences(streamingContent), [streamingContent]);
  // Prompt submission stays locked until streaming AND file application
  // have both finished (isSending), and while an undo is in flight.
  const inputLocked = isSending || undoPending;

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isSending, liveText]);

  useEffect(() => {
    if (!openDiffId) {
      return;
    }
    diffRefs.current.get(openDiffId)?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [openDiffId]);

  /**
   * Expand or collapse the line diff for one assistant change set.
   *
   * @param messageId - Assistant message identifier.
   */
  function toggleDiff(messageId: string) {
    setOpenDiffId((current) => (current === messageId ? null : messageId));
  }

  /**
   * Submit the current draft message.
   *
   * @param event - Form submit event.
   */
  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const content = draft.trim();
    if (!content || inputLocked) {
      return;
    }
    setDraft('');
    await onSend(content);
  }

  return (
    <aside className="flex h-full min-h-0 flex-col overflow-hidden border-l border-white/10 bg-ink-950/70">
      <div className="shrink-0 border-b border-white/10 px-4 py-3">
        <h2 className="font-display text-lg">AI Chat</h2>
        <p className="text-xs text-slate-400">Ask about code or request file changes</p>
      </div>

      {appliedChangesCount > 0 ? (
        <div className="flex shrink-0 items-center justify-between gap-2 border-b border-white/10 bg-ink-900/40 px-3 py-1.5">
          <button
            type="button"
            className="flex min-w-0 flex-1 items-center gap-1 text-left text-[11px] text-slate-400 hover:text-sand-50"
            disabled={!appliedChangesMessageId}
            onClick={() => appliedChangesMessageId && toggleDiff(appliedChangesMessageId)}
            title="Review the lines the AI changed"
          >
            <span className="truncate">
              Applied:{' '}
              <span className="font-medium text-sand-50">
                {appliedChangesCount} file{appliedChangesCount === 1 ? '' : 's'}
              </span>
            </span>
            <span className="shrink-0 text-accent">
              {openDiffId === appliedChangesMessageId ? 'Hide changes' : 'View changes'}
            </span>
          </button>
          <Button
            type="button"
            size="sm"
            variant="secondary"
            className="h-7 shrink-0 px-2.5 py-0 text-[11px]"
            disabled={!canUndo}
            onClick={onUndo}
          >
            {undoPending ? (
              <>
                <span className="h-3 w-3 animate-spin rounded-full border-2 border-current/30 border-t-current" />
                Undoing…
              </>
            ) : (
              'Undo last'
            )}
          </Button>
        </div>
      ) : null}

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-4">
        {messages.length === 0 && !isSending ? (
          <p className="text-sm text-slate-500">
            Try: “Improve the landing page layout with Tailwind” or “Explain this file”.
          </p>
        ) : (
          messages.map((message) => (
            <div
              key={message.id}
              ref={(node) => {
                if (node) {
                  diffRefs.current.set(message.id, node);
                } else {
                  diffRefs.current.delete(message.id);
                }
              }}
              className={cn(
                'rounded-2xl px-3 py-2 text-sm leading-6',
                message.role === 'user'
                  ? 'ml-6 bg-accent/15 text-sand-50'
                  : 'mr-6 bg-ink-800 text-slate-200',
              )}
            >
              <p className="mb-1 text-[10px] uppercase tracking-[0.16em] text-slate-400">
                {message.role}
              </p>
              <p className="whitespace-pre-wrap">{message.content}</p>
              {message.file_changes?.length ? (
                <>
                  <button
                    type="button"
                    onClick={() => toggleDiff(message.id)}
                    className="mt-2 text-xs text-accent-soft hover:underline"
                  >
                    {openDiffId === message.id ? '▾' : '▸'} Applied{' '}
                    {message.file_changes.length} file change(s)
                    {message.undone ? ' · reverted' : ''}
                  </button>
                  {openDiffId === message.id ? (
                    <AppliedChanges
                      changes={message.file_changes}
                      onOpenFile={onOpenFile}
                    />
                  ) : null}
                </>
              ) : null}
            </div>
          ))
        )}
        {isSending ? (
          <div className="mr-6 rounded-2xl bg-ink-800 px-3 py-2 text-sm leading-6 text-slate-200">
            <p className="mb-1 text-[10px] uppercase tracking-[0.16em] text-slate-400">
              assistant
            </p>
            {liveText ? (
              <p className="whitespace-pre-wrap">{liveText}</p>
            ) : (
              <p className="text-slate-400">Thinking…</p>
            )}
          </div>
        ) : null}
        <div ref={endRef} />
      </div>

      <form onSubmit={handleSubmit} className="shrink-0 border-t border-white/10 p-3">
        <textarea
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          rows={3}
          placeholder="Ask the AI to explain or modify your project…"
          className="w-full resize-none rounded-xl border border-white/10 bg-ink-900 px-3 py-2 text-sm outline-none focus:border-accent/50 disabled:cursor-not-allowed disabled:opacity-60"
          disabled={inputLocked}
        />
        <div className="mt-2 flex justify-end gap-2">
          {isSending && onCancel ? (
            <Button type="button" size="sm" variant="secondary" onClick={onCancel}>
              Stop
            </Button>
          ) : null}
          <Button type="submit" size="sm" disabled={inputLocked || !draft.trim()}>
            {isSending ? (
              <>
                <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current/30 border-t-current" />
                Generating…
              </>
            ) : (
              'Send'
            )}
          </Button>
        </div>
      </form>
    </aside>
  );
}
