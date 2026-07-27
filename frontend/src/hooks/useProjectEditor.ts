import { useCallback, useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
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
import { listChatMessages, sendChatMessage } from '@/api/chat';
import { useEditorStore } from '@/stores/editorStore';
import type { FileNode, ProjectFile } from '@/types';
import { getErrorMessage } from '@/utils/helpers';

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
  const [flatFiles, setFlatFiles] = useState<ProjectFile[]>([]);

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
    return () => reset();
  }, [projectId, reset]);

  const activeTab = useMemo(
    () => tabs.find((tab) => tab.id === activeTabId) ?? null,
    [tabs, activeTabId],
  );

  const refreshPreviewFiles = useCallback(async () => {
    if (projectQuery.data?.workspace_type !== 'website') {
      return;
    }
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
    setFlatFiles(files);
  }, [projectId, projectQuery.data?.workspace_type]);

  useEffect(() => {
    void refreshPreviewFiles();
  }, [refreshPreviewFiles, treeQuery.dataUpdatedAt]);

  const saveActive = useCallback(async () => {
    if (!activeTab || !activeTab.dirty) {
      return;
    }
    setSaving(true);
    setError('');
    try {
      const saved = await updateFile(projectId, activeTab.id, { content: activeTab.content });
      markSaved(activeTab.id, saved.content);
      await refreshPreviewFiles();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }, [activeTab, markSaved, projectId, refreshPreviewFiles]);

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
   * Open a file node in a Monaco tab.
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
    } catch (err) {
      setError(getErrorMessage(err));
    }
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
      await refreshPreviewFiles();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  }

  const chatMutation = useMutation({
    mutationFn: (content: string) =>
      sendChatMessage(projectId, {
        content,
        current_file_path: activeTab?.path,
        apply_changes: true,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['chat', projectId] });
      await queryClient.invalidateQueries({ queryKey: ['file-tree', projectId] });
      await refreshPreviewFiles();
      if (activeTab) {
        const refreshed = await getFile(projectId, activeTab.id);
        openTab({
          id: refreshed.id,
          path: refreshed.path,
          name: refreshed.name,
          language: refreshed.language,
          content: refreshed.content,
          dirty: false,
        });
      }
    },
  });

  /**
   * Send a chat message through the AI pipeline.
   *
   * @param content - User message text.
   */
  async function handleSendChat(content: string) {
    setError('');
    try {
      await chatMutation.mutateAsync(content);
    } catch (err) {
      setError(getErrorMessage(err));
    }
  }

  return {
    projectQuery,
    treeQuery,
    chatQuery,
    tabs,
    activeTabId,
    activeTab,
    saving,
    error,
    flatFiles,
    chatPending: chatMutation.isPending,
    setActiveTab,
    closeTab,
    updateContent,
    saveActive,
    handleOpenFile,
    handleCreateFile,
    handleCreateFolder,
    handleDeleteNode,
    handleSendChat,
  };
}
