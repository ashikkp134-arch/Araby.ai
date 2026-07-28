import type { EditorTab } from '@/types';
import { cn } from '@/utils/helpers';

interface EditorTabsProps {
  tabs: EditorTab[];
  activeTabId: string | null;
  onSelect: (tabId: string) => void;
  onClose: (tabId: string) => void;
  previewOpen?: boolean;
  previewActive?: boolean;
  onSelectPreview?: () => void;
  onClosePreview?: () => void;
}

/**
 * Multi-tab header for the Monaco editor, plus an optional Live Preview tab.
 */
export function EditorTabs({
  tabs,
  activeTabId,
  onSelect,
  onClose,
  previewOpen = false,
  previewActive = false,
  onSelectPreview,
  onClosePreview,
}: EditorTabsProps) {
  if (tabs.length === 0 && !previewOpen) {
    return (
      <div className="border-b border-white/10 px-4 py-3 text-sm text-slate-500">
        Open a file to start editing
      </div>
    );
  }

  return (
    <div className="flex gap-1 overflow-x-auto border-b border-white/10 bg-ink-950/40 px-2 py-2">
      {tabs.map((tab) => (
        <div
          key={tab.id}
          className={cn(
            'flex items-center gap-2 rounded-md px-3 py-1.5 text-sm',
            !previewActive && activeTabId === tab.id
              ? 'bg-ink-800 text-sand-50'
              : 'text-slate-400 hover:bg-white/5 hover:text-sand-50',
          )}
        >
          <button type="button" onClick={() => onSelect(tab.id)} className="max-w-[160px] truncate">
            {tab.dirty ? '• ' : ''}
            {tab.name}
          </button>
          <button
            type="button"
            onClick={() => onClose(tab.id)}
            className="text-slate-500 hover:text-white"
            aria-label={`Close ${tab.name}`}
          >
            ×
          </button>
        </div>
      ))}
      {previewOpen ? (
        <div
          className={cn(
            'flex items-center gap-2 rounded-md border border-dashed px-3 py-1.5 text-sm',
            previewActive
              ? 'border-accent/40 bg-accent/10 text-accent-soft'
              : 'border-white/10 text-slate-400 hover:bg-white/5 hover:text-sand-50',
          )}
        >
          <button type="button" onClick={onSelectPreview} className="max-w-[160px] truncate">
            ▶ Preview
          </button>
          <button
            type="button"
            onClick={onClosePreview}
            className="text-slate-500 hover:text-white"
            aria-label="Close preview"
          >
            ×
          </button>
        </div>
      ) : null}
    </div>
  );
}
