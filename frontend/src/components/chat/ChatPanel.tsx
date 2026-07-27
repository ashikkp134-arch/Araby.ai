import { FormEvent, useEffect, useRef, useState } from 'react';
import type { ChatMessage } from '@/types';
import { Button } from '@/components/common/Button';
import { cn } from '@/utils/helpers';

interface ChatPanelProps {
  messages: ChatMessage[];
  isSending: boolean;
  onSend: (content: string) => Promise<void>;
}

/**
 * Project-scoped AI chat panel.
 */
export function ChatPanel({ messages, isSending, onSend }: ChatPanelProps) {
  const [draft, setDraft] = useState('');
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isSending]);

  /**
   * Submit the current draft message.
   *
   * @param event - Form submit event.
   */
  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const content = draft.trim();
    if (!content || isSending) {
      return;
    }
    setDraft('');
    await onSend(content);
  }

  return (
    <aside className="flex h-full flex-col border-l border-white/10 bg-ink-950/70">
      <div className="border-b border-white/10 px-4 py-3">
        <h2 className="font-display text-lg">AI Chat</h2>
        <p className="text-xs text-slate-400">Ask about code or request file changes</p>
      </div>
      <div className="flex-1 space-y-3 overflow-auto px-4 py-4">
        {messages.length === 0 ? (
          <p className="text-sm text-slate-500">
            Try: “Improve the landing page layout with Tailwind” or “Explain this file”.
          </p>
        ) : (
          messages.map((message) => (
            <div
              key={message.id}
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
                <p className="mt-2 text-xs text-accent-soft">
                  Applied {message.file_changes.length} file change(s)
                </p>
              ) : null}
            </div>
          ))
        )}
        {isSending ? <p className="text-sm text-slate-400">Thinking…</p> : null}
        <div ref={endRef} />
      </div>
      <form onSubmit={handleSubmit} className="border-t border-white/10 p-3">
        <textarea
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          rows={3}
          placeholder="Ask the AI to explain or modify your project…"
          className="w-full resize-none rounded-xl border border-white/10 bg-ink-900 px-3 py-2 text-sm outline-none focus:border-accent/50"
        />
        <div className="mt-2 flex justify-end">
          <Button type="submit" size="sm" disabled={isSending || !draft.trim()}>
            Send
          </Button>
        </div>
      </form>
    </aside>
  );
}
