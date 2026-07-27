import type { EditorTab } from '@/types';
import { cn } from '@/utils/helpers';

interface EditorTabsProps {
  tabs: EditorTab[];
  activeTabId: string | null;
  onSelect: (tabId: string) => void;
  onClose: (tabId: string) => void;
}

/**
 * Multi-tab header for the Monaco editor.
 */
export function EditorTabs({ tabs, activeTabId, onSelect, onClose }: EditorTabsProps) {
  if (tabs.length === 0) {
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
            activeTabId === tab.id
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
    </div>
  );
}
