import { apiClient } from '@/api/client';
import type { ApiResponse, WorkspaceInfo } from '@/types';

/**
 * Fetch available workspace cards.
 *
 * @returns Workspace catalog.
 */
export async function listWorkspaces(): Promise<WorkspaceInfo[]> {
  const { data } = await apiClient.get<ApiResponse<WorkspaceInfo[]>>('/workspaces');
  return data.data;
}
