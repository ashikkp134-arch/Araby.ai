import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { getProject } from '@/api/projects';
import {
  createFile,
  createFolder,
  deleteFile,
  deleteFolder,
  getFile,
  getFileTree,
  updateFile,
} from '@/api/files';
import {
  listChatMessages,
  streamChatMessage,
  undoLastAiChanges,
  type StreamChatHandle,
} from '@/api/chat';
import { useEditorStore } from '@/stores/editorStore';
import type { ChatMessage, FileNode, ProjectFile } from '@/types';
import { downloadProjectZip } from '@/utils/downloadProjectZip';
import { getErrorMessage } from '@/utils/helpers';

type ActiveView = 'editor' | 'preview';

interface PreviewTabState {
  open: boolean;
  files: ProjectFile[];
  loading: boolean;
}

/**
 * Encapsulate editor page data loading and file/chat mutations.
 *
 * @param projectId - Active project identifier.
 * @returns Editor page state and handlers.
 */
export function useProjectEditor(projectId: string) {
  const queryClient = useQueryClient();
  const {
    tabs,
    activeTabId,
    openTab,
    closeTab,
    setActiveTab,
    updateContent,
    markSaved,
    reset,
  } = useEditorStore();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [chatPending, setChatPending] = useState(false);
  const [undoPending, setUndoPending] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const [optimisticMessages, setOptimisticMessages] = useState<ChatMessage[]>([]);
  const [activeView, setActiveView] = useState<ActiveView>('editor');
  const [previewTab, setPreviewTab] = useState<PreviewTabState>({
    open: false,
    files: [],
    loading: false,
  });
  const [downloading, setDownloading] = useState(false);
  const streamHandleRef = useRef<StreamChatHandle | null>(null);

  const projectQuery = useQuery({
    queryKey: ['project', projectId],
    queryFn: () => getProject(projectId),
    enabled: Boolean(projectId),
  });

  const treeQuery = useQuery({
    queryKey: ['file-tree', projectId],
    queryFn: () => getFileTree(projectId),
    enabled: Boolean(projectId),
  });

  const chatQuery = useQuery({
    queryKey: ['chat', projectId],
    queryFn: () => listChatMessages(projectId),
    enabled: Boolean(projectId),
  });

  useEffect(() => {
    reset();
    setOptimisticMessages([]);
    setStreamingContent('');
    setActiveView('editor');
    setPreviewTab({ open: false, files: [], loading: false });
    return () => {
      streamHandleRef.current?.cancel();
      reset();
    };
  }, [projectId, reset]);

  const activeTab = useMemo(
    () => tabs.find((tab) => tab.id === activeTabId) ?? null,
    [tabs, activeTabId],
  );

  const chatMessages = useMemo(() => {
    const server = chatQuery.data?.items ?? [];
    if (!optimisticMessages.length) {
      return server;
    }
    return [...server, ...optimisticMessages];
  }, [chatQuery.data?.items, optimisticMessages]);

  /**
   * Most recent assistant message that applied file changes. Drives the
   * "Applied Changes" counter and Undo Last AI Changes availability.
   */
  const lastChangeSet = useMemo(() => {
    for (let i = chatMessages.length - 1; i >= 0; i -= 1) {
      const message = chatMessages[i];
      if (message.role === 'assistant' && message.file_changes?.length) {
        return message;
      }
    }
    return null;
  }, [chatMessages]);

  const canUndo = Boolean(lastChangeSet && !lastChangeSet.undone && !chatPending && !undoPending);

  /**
   * Fetch every project file (used to snapshot a Live Preview render).
   */
  const fetchAllFiles = useCallback(async (): Promise<ProjectFile[]> => {
    const tree = await getFileTree(projectId);
    const files: ProjectFile[] = [];

    async function walk(nodes: FileNode[]) {
      for (const node of nodes) {
        if (node.type === 'file') {
          files.push(await getFile(projectId, node.id));
        }
        if (node.children) {
          await walk(node.children);
        }
      }
    }

    await walk(tree);
    return files;
  }, [projectId]);

  const saveActive = useCallback(async () => {
    if (!activeTab || !activeTab.dirty) {
      return;
    }
    setSaving(true);
    setError('');
    try {
      const saved = await updateFile(projectId, activeTab.id, { content: activeTab.content });
      markSaved(activeTab.id, saved.content);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }, [activeTab, markSaved, projectId]);

  useEffect(() => {
    if (!activeTab?.dirty) {
      return undefined;
    }
    const timer = window.setTimeout(() => {
      void saveActive();
    }, 1200);
    return () => window.clearTimeout(timer);
  }, [activeTab?.content, activeTab?.dirty, activeTab?.id, saveActive]);

  /**
   * Open a file node in a Monaco tab and switch back to the editor view.
   *
   * @param node - File tree node.
   */
  async function handleOpenFile(node: FileNode) {
    setError('');
    try {
      const file = await getFile(projectId, node.id);
      openTab({
        id: file.id,
        path: file.path,
        name: file.name,
        language: file.language,
        content: file.content,
        dirty: false,
      });
      setActiveView('editor');
    } catch (err) {
      setError(getErrorMessage(err));
    }
  }

  /**
   * Select an already-open file tab and switch back to the editor view.
   *
   * @param tabId - Editor tab identifier.
   */
  function handleSelectFileTab(tabId: string) {
    setActiveTab(tabId);
    setActiveView('editor');
  }

  /**
   * Prompt and create a new file.
   */
  async function handleCreateFile() {
    const name = window.prompt('File name (e.g. utils.js)');
    if (!name) {
      return;
    }
    const folderPath = window.prompt('Folder path (leave empty for root)', '') || '';
    try {
      const file = await createFile(projectId, { name, folder_path: folderPath, content: '' });
      await queryClient.invalidateQueries({ queryKey: ['file-tree', projectId] });
      openTab({
        id: file.id,
        path: file.path,
        name: file.name,
        language: file.language,
        content: file.content,
        dirty: false,
      });
      setActiveView('editor');
    } catch (err) {
      setError(getErrorMessage(err));
    }
  }

  /**
   * Prompt and create a new folder.
   */
  async function handleCreateFolder() {
    const name = window.prompt('Folder name');
    if (!name) {
      return;
    }
    const parentPath = window.prompt('Parent path (leave empty for root)', '') || '';
    try {
      await createFolder(projectId, { name, parent_path: parentPath });
      await queryClient.invalidateQueries({ queryKey: ['file-tree', projectId] });
    } catch (err) {
      setError(getErrorMessage(err));
    }
  }

  /**
   * Delete a file or folder node.
   *
   * @param node - File tree node.
   */
  async function handleDeleteNode(node: FileNode) {
    if (!window.confirm(`Delete ${node.path}?`)) {
      return;
    }
    try {
      if (node.type === 'file') {
        await deleteFile(projectId, node.id);
        closeTab(node.id);
      } else {
        await deleteFolder(projectId, node.path);
      }
      await queryClient.invalidateQueries({ queryKey: ['file-tree', projectId] });
    } catch (err) {
      setError(getErrorMessage(err));
    }
  }

  /**
   * Cancel an in-flight streaming chat request.
   */
  function handleCancelChat() {
    streamHandleRef.current?.cancel();
    streamHandleRef.current = null;
    setChatPending(false);
    setStreamingContent('');
  }

  /**
   * Re-sync the active tab's content after a server-side file mutation
   * (AI change apply or undo). Closes the tab if the file no longer exists.
   */
  const resyncActiveTab = useCallback(async () => {
    if (!activeTab) {
      return;
    }
    try {
      const refreshed = await getFile(projectId, activeTab.id);
      openTab({
        id: refreshed.id,
        path: refreshed.path,
        name: refreshed.name,
        language: refreshed.language,
        content: refreshed.content,
        dirty: false,
      });
    } catch {
      // File was deleted by the AI change (or its undo); drop the stale tab.
      closeTab(activeTab.id);
    }
  }, [activeTab, closeTab, openTab, projectId]);

  /**
   * Send a chat message through the streaming AI pipeline. The Send button
   * stays disabled (via chatPending) until streaming AND file application
   * have both fully completed.
   *
   * @param content - User message text.
   */
  async function handleSendChat(content: string) {
    setError('');
    setChatPending(true);
    setStreamingContent('');
    setOptimisticMessages([
      {
        id: `local-user-${Date.now()}`,
        session_id: 'local',
        project_id: projectId,
        role: 'user',
        content,
        file_changes: [],
        created_at: new Date().toISOString(),
      },
    ]);

    const handle = streamChatMessage(
      projectId,
      {
        content,
        current_file_path: activeTab?.path,
        open_tabs: tabs.map((tab) => tab.path),
        apply_changes: true,
      },
      {
        onDelta: (chunk) => {
          setStreamingContent((prev) => prev + chunk);
        },
        onDone: () => {
          setStreamingContent('');
        },
        onError: (message) => {
          setError(message);
          setStreamingContent('');
        },
      },
    );
    streamHandleRef.current = handle;

    try {
      // Resolves only after the backend has streamed the full response AND
      // applied any file changes (the WS "done" event is sent last).
      await handle.done;
      setOptimisticMessages([]);
      await queryClient.invalidateQueries({ queryKey: ['chat', projectId] });
      await queryClient.invalidateQueries({ queryKey: ['file-tree', projectId] });
      await resyncActiveTab();
    } catch (err) {
      // Stream errors are already shown via onError; keep a fallback.
      setError((prev) => prev || getErrorMessage(err));
      setOptimisticMessages([]);
    } finally {
      streamHandleRef.current = null;
      setChatPending(false);
      setStreamingContent('');
    }
  }

  /**
   * Revert every file change from the most recent AI change set.
   */
  async function handleUndoLastChanges() {
    if (!canUndo) {
      return;
    }
    setError('');
    setUndoPending(true);
    try {
      await undoLastAiChanges(projectId);
      await queryClient.invalidateQueries({ queryKey: ['chat', projectId] });
      await queryClient.invalidateQueries({ queryKey: ['file-tree', projectId] });
      await resyncActiveTab();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setUndoPending(false);
    }
  }

  /**
   * Download every project file as a ZIP archive the user can save locally.
   */
  async function handleDownloadProject() {
    setError('');
    setDownloading(true);
    try {
      const files = await fetchAllFiles();
      await downloadProjectZip(projectQuery.data?.name || 'project', files);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setDownloading(false);
    }
  }

  /**
   * Open (or regenerate) the Live Preview workspace tab using the latest
   * saved project state, then switch to it.
   */
  async function handleOpenPreview() {
    setError('');
    setPreviewTab((prev) => ({ ...prev, open: true, loading: true }));
    try {
      const files = await fetchAllFiles();
      setPreviewTab({ open: true, files, loading: false });
      setActiveView('preview');
    } catch (err) {
      setError(getErrorMessage(err));
      setPreviewTab((prev) => ({ ...prev, loading: false }));
    }
  }

  /**
   * Switch to an already-open preview tab without regenerating it.
   */
  function handleSelectPreviewTab() {
    if (previewTab.open) {
      setActiveView('preview');
    }
  }

  /**
   * Close the preview tab. Does not affect project or editor file state.
   */
  function handleClosePreviewTab() {
    setPreviewTab({ open: false, files: [], loading: false });
    setActiveView((current) => (current === 'preview' ? 'editor' : current));
  }

  return {
    projectQuery,
    treeQuery,
    chatQuery,
    chatMessages,
    tabs,
    activeTabId,
    activeTab,
    activeView,
    saving,
    error,
    chatPending,
    undoPending,
    streamingContent,
    lastChangeSet,
    canUndo,
    previewTab,
    downloading,
    setActiveTab: handleSelectFileTab,
    closeTab,
    updateContent,
    saveActive,
    handleOpenFile,
    handleCreateFile,
    handleCreateFolder,
    handleDeleteNode,
    handleSendChat,
    handleCancelChat,
    handleUndoLastChanges,
    handleDownloadProject,
    handleOpenPreview,
    handleSelectPreviewTab,
    handleClosePreviewTab,
  };
}
