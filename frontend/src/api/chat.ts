import { apiClient } from '@/api/client';
import type { ApiResponse, ChatCompletion, ChatMessage, PaginatedData } from '@/types';

/**
 * List chat messages for a project.
 *
 * @param projectId - Project identifier.
 * @param page - Page number.
 * @param pageSize - Page size.
 * @returns Paginated chat messages.
 */
export async function listChatMessages(
  projectId: string,
  page = 1,
  pageSize = 100,
): Promise<PaginatedData<ChatMessage>> {
  const { data } = await apiClient.get<ApiResponse<PaginatedData<ChatMessage>>>(
    `/chat/${projectId}/messages`,
    { params: { page, page_size: pageSize } },
  );
  return data.data;
}

/**
 * Send a chat message to the AI assistant.
 *
 * @param projectId - Project identifier.
 * @param payload - Chat request payload.
 * @returns Chat completion response.
 */
export async function sendChatMessage(
  projectId: string,
  payload: {
    content: string;
    current_file_path?: string | null;
    selected_code?: string | null;
    apply_changes?: boolean;
  },
): Promise<ChatCompletion> {
  const { data } = await apiClient.post<ApiResponse<ChatCompletion>>(
    `/chat/${projectId}/messages`,
    payload,
  );
  return data.data;
}
