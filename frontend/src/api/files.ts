import { apiClient } from '@/api/client';
import type { ApiResponse, FileNode, ProjectFile } from '@/types';

/**
 * Fetch the nested file tree for a project.
 *
 * @param projectId - Project identifier.
 * @returns Nested file tree.
 */
export async function getFileTree(projectId: string): Promise<FileNode[]> {
  const { data } = await apiClient.get<ApiResponse<FileNode[]>>(`/files/${projectId}/tree`);
  return data.data;
}

/**
 * Fetch a file by id.
 *
 * @param projectId - Project identifier.
 * @param fileId - File identifier.
 * @returns File document.
 */
export async function getFile(projectId: string, fileId: string): Promise<ProjectFile> {
  const { data } = await apiClient.get<ApiResponse<ProjectFile>>(
    `/files/${projectId}/${fileId}`,
  );
  return data.data;
}

/**
 * Create a file in a project.
 *
 * @param projectId - Project identifier.
 * @param payload - File creation payload.
 * @returns Created file.
 */
export async function createFile(
  projectId: string,
  payload: { name: string; folder_path?: string; content?: string },
): Promise<ProjectFile> {
  const { data } = await apiClient.post<ApiResponse<ProjectFile>>(
    `/files/${projectId}`,
    payload,
  );
  return data.data;
}

/**
 * Create a folder in a project.
 *
 * @param projectId - Project identifier.
 * @param payload - Folder creation payload.
 */
export async function createFolder(
  projectId: string,
  payload: { name: string; parent_path?: string },
): Promise<void> {
  await apiClient.post(`/files/${projectId}/folders`, payload);
}

/**
 * Update file content or rename a file.
 *
 * @param projectId - Project identifier.
 * @param fileId - File identifier.
 * @param payload - Update payload.
 * @returns Updated file.
 */
export async function updateFile(
  projectId: string,
  fileId: string,
  payload: { content?: string; name?: string },
): Promise<ProjectFile> {
  const { data } = await apiClient.patch<ApiResponse<ProjectFile>>(
    `/files/${projectId}/${fileId}`,
    payload,
  );
  return data.data;
}

/**
 * Delete a file.
 *
 * @param projectId - Project identifier.
 * @param fileId - File identifier.
 */
export async function deleteFile(projectId: string, fileId: string): Promise<void> {
  await apiClient.delete(`/files/${projectId}/${fileId}`);
}

/**
 * Delete a folder by path.
 *
 * @param projectId - Project identifier.
 * @param path - Folder path.
 */
export async function deleteFolder(projectId: string, path: string): Promise<void> {
  await apiClient.delete(`/files/${projectId}/folders`, { params: { path } });
}
