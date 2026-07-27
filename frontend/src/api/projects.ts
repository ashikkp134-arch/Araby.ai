import { apiClient } from '@/api/client';
import type { ApiResponse, PaginatedData, Project, WorkspaceType } from '@/types';

/**
 * Create a project in a workspace.
 *
 * @param payload - Project creation payload.
 * @returns Created project.
 */
export async function createProject(payload: {
  name: string;
  description?: string;
  workspace_type: WorkspaceType;
}): Promise<Project> {
  const { data } = await apiClient.post<ApiResponse<Project>>('/projects', payload);
  return data.data;
}

/**
 * Import a local folder as a new project.
 *
 * @param payload - Project metadata and file contents.
 * @returns Created project seeded with the imported files.
 */
export async function importProject(payload: {
  name: string;
  description?: string;
  workspace_type: WorkspaceType;
  files: Array<{ path: string; content: string }>;
}): Promise<Project> {
  const { data } = await apiClient.post<ApiResponse<Project>>('/projects/import', payload);
  return data.data;
}

/**
 * List projects for the current user.
 *
 * @param params - Optional filters and pagination.
 * @returns Paginated projects.
 */
export async function listProjects(params?: {
  workspace_type?: WorkspaceType;
  page?: number;
  page_size?: number;
}): Promise<PaginatedData<Project>> {
  const { data } = await apiClient.get<ApiResponse<PaginatedData<Project>>>('/projects', {
    params,
  });
  return data.data;
}

/**
 * Fetch a single project.
 *
 * @param projectId - Project identifier.
 * @returns Project details.
 */
export async function getProject(projectId: string): Promise<Project> {
  const { data } = await apiClient.get<ApiResponse<Project>>(`/projects/${projectId}`);
  return data.data;
}

/**
 * Delete a project.
 *
 * @param projectId - Project identifier.
 */
export async function deleteProject(projectId: string): Promise<void> {
  await apiClient.delete(`/projects/${projectId}`);
}
