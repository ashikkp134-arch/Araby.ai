import { apiClient, getAccessToken } from '@/api/client';
import type {
  ApiResponse,
  ChatCompletion,
  ChatMessage,
  FileChangeProposal,
  PaginatedData,
  UndoChangesResult,
} from '@/types';

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
 * Send a chat message to the AI assistant (non-streaming HTTP).
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
    open_tabs?: string[];
    apply_changes?: boolean;
  },
): Promise<ChatCompletion> {
  const { data } = await apiClient.post<ApiResponse<ChatCompletion>>(
    `/chat/${projectId}/messages`,
    payload,
  );
  return data.data;
}

/**
 * Revert every file change from the most recent AI change set.
 *
 * @param projectId - Project identifier.
 * @returns Summary of restored/removed file paths.
 */
export async function undoLastAiChanges(projectId: string): Promise<UndoChangesResult> {
  const { data } = await apiClient.post<ApiResponse<UndoChangesResult>>(
    `/chat/${projectId}/undo-last`,
  );
  return data.data;
}

export interface StreamChatHandlers {
  onStart?: (metadata: Record<string, unknown>) => void;
  onDelta?: (chunk: string) => void;
  /** Home page ready — open Live Preview immediately. */
  onPreviewReady?: (payload: {
    content: string;
    file_changes: FileChangeProposal[];
    metadata?: Record<string, unknown>;
  }) => void;
  /** Background Level-2 / Level-3 finished. */
  onStageDone?: (payload: {
    content: string;
    file_changes: FileChangeProposal[];
    metadata?: Record<string, unknown>;
  }) => void;
  onDone?: (payload: {
    content: string;
    file_changes: FileChangeProposal[];
    metadata?: Record<string, unknown>;
  }) => void;
  onError?: (message: string) => void;
}

export interface StreamChatHandle {
  cancel: () => void;
  done: Promise<void>;
}

/**
 * Stream an AI chat turn over WebSocket.
 *
 * @param projectId - Project identifier.
 * @param payload - Chat request payload.
 * @param handlers - Streaming lifecycle callbacks.
 * @returns Handle with cancel() and completion promise.
 */
export function streamChatMessage(
  projectId: string,
  payload: {
    content: string;
    current_file_path?: string | null;
    selected_code?: string | null;
    open_tabs?: string[];
    apply_changes?: boolean;
  },
  handlers: StreamChatHandlers = {},
): StreamChatHandle {
  const token = getAccessToken();
  if (!token) {
    const err = new Error('Not authenticated');
    handlers.onError?.(err.message);
    return {
      cancel: () => undefined,
      done: Promise.reject(err),
    };
  }

  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const wsUrl = `${protocol}://${window.location.host}/ws/chat/${projectId}`;
  const socket = new WebSocket(wsUrl);
  let settled = false;
  let resolveDone: (() => void) | null = null;

  // Stream errors are surfaced via handlers.onError and resolve `done`
  // (rather than reject it) so a failed AI turn doesn't produce an
  // unhandled promise rejection on top of the user-visible error banner.
  const done = new Promise<void>((resolve) => {
    resolveDone = resolve;
  });

  const finishOk = () => {
    if (settled) {
      return;
    }
    settled = true;
    resolveDone?.();
  };

  const finishErr = (message: string) => {
    if (settled) {
      return;
    }
    settled = true;
    handlers.onError?.(message);
    // Resolve (don't reject) so the UI can show a friendly banner without an
    // unhandled promise rejection / secondary catch overwriting the message.
    resolveDone?.();
  };

  socket.addEventListener('open', () => {
    socket.send(JSON.stringify({ token }));
    socket.send(
      JSON.stringify({
        content: payload.content,
        current_file_path: payload.current_file_path ?? null,
        selected_code: payload.selected_code ?? null,
        open_tabs: payload.open_tabs ?? [],
        apply_changes: payload.apply_changes ?? true,
      }),
    );
  });

  socket.addEventListener('message', (event) => {
    try {
      const data = JSON.parse(String(event.data)) as {
        type: string;
        content?: string;
        message?: string;
        metadata?: Record<string, unknown>;
        file_changes?: FileChangeProposal[];
      };
      if (data.type === 'start') {
        handlers.onStart?.(data.metadata || {});
      } else if (data.type === 'delta' && data.content) {
        handlers.onDelta?.(data.content);
      } else if (data.type === 'preview_ready') {
        handlers.onPreviewReady?.({
          content: data.content || '',
          file_changes: data.file_changes || [],
          metadata: data.metadata,
        });
      } else if (data.type === 'stage_done') {
        handlers.onStageDone?.({
          content: data.content || '',
          file_changes: data.file_changes || [],
          metadata: data.metadata,
        });
      } else if (data.type === 'done') {
        handlers.onDone?.({
          content: data.content || '',
          file_changes: data.file_changes || [],
          metadata: data.metadata,
        });
        socket.close();
        finishOk();
      } else if (data.type === 'error') {
        finishErr(data.message || 'Stream failed');
        socket.close();
      } else if (data.type === 'cancelled') {
        finishOk();
      }
    } catch {
      finishErr('Invalid stream payload');
      socket.close();
    }
  });

  socket.addEventListener('error', () => {
    finishErr('WebSocket connection failed');
  });

  socket.addEventListener('close', () => {
    if (!settled) {
      finishErr('Connection closed');
    }
  });

  return {
    cancel: () => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'cancel' }));
      }
      socket.close();
      finishOk();
    },
    done,
  };
}
