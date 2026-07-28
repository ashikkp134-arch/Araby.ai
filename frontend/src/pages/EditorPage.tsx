import { Link, useParams } from 'react-router-dom';
import { FileExplorer } from '@/components/editor/FileExplorer';
import { EditorTabs } from '@/components/editor/EditorTabs';
import { CodeEditor } from '@/components/editor/CodeEditor';
import { LivePreview } from '@/components/editor/LivePreview';
import { ChatPanel } from '@/components/chat/ChatPanel';
import { Button } from '@/components/common/Button';
import { Spinner } from '@/components/common/Modal';
import { useProjectEditor } from '@/hooks/useProjectEditor';
import { useUiStore } from '@/stores/uiStore';

/**
 * Full project editor with files, Monaco, chat, and a dedicated preview tab.
 */
export function EditorPage() {
  const { projectId = '' } = useParams<{ projectId: string }>();
  const { chatOpen, toggleChat } = useUiStore();
  const editor = useProjectEditor(projectId);

  if (editor.projectQuery.isLoading) {
    return (
      <div className="flex min-h-[70vh] items-center justify-center">
        <Spinner label="Opening project" />
      </div>
    );
  }

  if (!editor.projectQuery.data) {
    return <p className="p-8 text-rose-300">Project not found.</p>;
  }

  const project = editor.projectQuery.data;
  const isWebsite = project.workspace_type === 'website';
  const showingPreview = editor.activeView === 'preview' && editor.previewTab.open;

  return (
    <div className="flex h-[calc(100vh-73px)] flex-col overflow-hidden">
      <div className="flex shrink-0 items-center justify-between border-b border-white/10 px-4 py-3">
        <div>
          <Link
            to={`/workspaces/${project.workspace_type}`}
            className="text-xs text-accent hover:underline"
          >
            ← Projects
          </Link>
          <h1 className="font-display text-xl">{project.name}</h1>
        </div>
        <div className="flex gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => void editor.handleDownloadProject()}
            disabled={editor.downloading}
          >
            {editor.downloading ? 'Saving ZIP…' : 'Save project'}
          </Button>
          {isWebsite ? (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => void editor.handleOpenPreview()}
              disabled={editor.previewTab.loading}
            >
              {editor.previewTab.loading ? 'Loading preview…' : 'Live preview'}
            </Button>
          ) : null}
          <Button variant="secondary" size="sm" onClick={toggleChat}>
            {chatOpen ? 'Hide chat' : 'Show chat'}
          </Button>
        </div>
      </div>

      {editor.error ? (
        <p className="shrink-0 bg-rose-500/10 px-4 py-2 text-sm text-rose-300">{editor.error}</p>
      ) : null}

      <div className="grid min-h-0 flex-1 grid-cols-1 overflow-hidden lg:grid-cols-[240px_minmax(0,1fr)_minmax(280px,340px)]">
        <FileExplorer
          nodes={editor.treeQuery.data || []}
          activePath={editor.activeTab?.path}
          onOpenFile={(node) => void editor.handleOpenFile(node)}
          onCreateFile={() => void editor.handleCreateFile()}
          onCreateFolder={() => void editor.handleCreateFolder()}
          onDeleteNode={(node) => void editor.handleDeleteNode(node)}
        />

        <div className="flex min-h-0 flex-col overflow-hidden border-r border-white/10">
          <EditorTabs
            tabs={editor.tabs}
            activeTabId={editor.activeTabId}
            onSelect={editor.setActiveTab}
            onClose={editor.closeTab}
            previewOpen={editor.previewTab.open}
            previewActive={showingPreview}
            onSelectPreview={editor.handleSelectPreviewTab}
            onClosePreview={editor.handleClosePreviewTab}
          />
          <div className="min-h-0 flex-1 overflow-hidden">
            {showingPreview ? (
              <LivePreview
                files={editor.previewTab.files}
                onRefresh={() => void editor.handleOpenPreview()}
                refreshing={editor.previewTab.loading}
              />
            ) : (
              <CodeEditor
                tab={editor.activeTab}
                onChange={(value) => {
                  if (editor.activeTab) {
                    editor.updateContent(editor.activeTab.id, value);
                  }
                }}
                onSave={() => void editor.saveActive()}
                saving={editor.saving}
              />
            )}
          </div>
        </div>

        {chatOpen ? (
          <ChatPanel
            messages={editor.chatMessages}
            isSending={editor.chatPending}
            streamingContent={editor.streamingContent}
            onSend={editor.handleSendChat}
            onCancel={editor.handleCancelChat}
            appliedChangesCount={editor.lastChangeSet?.file_changes.length ?? 0}
            canUndo={editor.canUndo}
            undoPending={editor.undoPending}
            onUndo={() => void editor.handleUndoLastChanges()}
          />
        ) : (
          <div className="hidden lg:block" />
        )}
      </div>
    </div>
  );
}
