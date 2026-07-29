import Editor, { type OnMount } from '@monaco-editor/react';
import type { EditorTab } from '@/types';
import { Button } from '@/components/common/Button';

interface CodeEditorProps {
  tab: EditorTab | null;
  onChange: (value: string) => void;
  onSave: () => void;
  saving?: boolean;
  /** When false, content is view-only (workspace file-type policy). */
  editable?: boolean;
  /** Called when the user tries to type in a read-only workspace file. */
  onReadonlyEditAttempt?: () => void;
}

/**
 * Monaco-powered code editor with save action.
 */
export function CodeEditor({
  tab,
  onChange,
  onSave,
  saving,
  editable = true,
  onReadonlyEditAttempt,
}: CodeEditorProps) {
  if (!tab) {
    return (
      <div className="flex h-full items-center justify-center text-slate-500">
        Select a file from the explorer
      </div>
    );
  }

  const handleMount: OnMount = (editor) => {
    if (!editable && onReadonlyEditAttempt) {
      editor.onDidAttemptReadOnlyEdit(() => {
        onReadonlyEditAttempt();
      });
    }
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-white/10 px-4 py-2">
        <div>
          <p className="font-mono text-sm text-sand-50">{tab.path}</p>
          <p className="text-xs text-slate-500">
            {!editable
              ? 'View only · editing blocked in this workspace'
              : tab.dirty
                ? 'Unsaved changes · autosave enabled'
                : 'Saved'}
          </p>
        </div>
        <Button size="sm" onClick={onSave} disabled={!editable || !tab.dirty || saving}>
          {saving ? 'Saving…' : 'Save'}
        </Button>
      </div>
      <div className="min-h-0 flex-1">
        <Editor
          height="100%"
          theme="vs-dark"
          language={tab.language || 'plaintext'}
          value={tab.content}
          onChange={(value) => {
            if (!editable) {
              return;
            }
            onChange(value ?? '');
          }}
          onMount={handleMount}
          options={{
            readOnly: !editable,
            domReadOnly: !editable,
            fontFamily: 'IBM Plex Mono, monospace',
            fontSize: 14,
            minimap: { enabled: false },
            automaticLayout: true,
            wordWrap: 'on',
            scrollBeyondLastLine: false,
          }}
        />
      </div>
    </div>
  );
}
