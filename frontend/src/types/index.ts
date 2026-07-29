export type WorkspaceType = 'javascript' | 'python' | 'website';

export interface ApiResponse<T> {
  success: boolean;
  message: string;
  data: T;
  error: unknown;
}

export interface PaginationMeta {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface PaginatedData<T> {
  items: T[];
  pagination: PaginationMeta;
}

export interface User {
  id: string;
  email: string;
  full_name: string;
  created_at: string;
}

export interface AuthTokens {
  user: User;
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface WorkspaceInfo {
  type: WorkspaceType;
  title: string;
  description: string;
  language_hint: string;
}

export interface Project {
  id: string;
  name: string;
  description: string;
  workspace_type: WorkspaceType;
  user_id: string;
  created_at: string;
  updated_at: string;
}

export interface FileNode {
  id: string;
  name: string;
  path: string;
  type: 'file' | 'folder';
  language?: string;
  children?: FileNode[];
}

export interface ProjectFile {
  id: string;
  project_id: string;
  name: string;
  path: string;
  folder_id?: string | null;
  content: string;
  language: string;
  updated_at: string;
  created_at: string;
}

export type DiffLineType = 'context' | 'add' | 'remove';

export interface DiffLine {
  type: DiffLineType;
  old_line?: number | null;
  new_line?: number | null;
  content: string;
}

export interface DiffHunk {
  old_start: number;
  old_lines: number;
  new_start: number;
  new_lines: number;
  lines: DiffLine[];
}

export interface FileChangeDiff {
  additions: number;
  deletions: number;
  is_new_file: boolean;
  is_deleted: boolean;
  truncated: boolean;
  hunks: DiffHunk[];
}

export interface FileChangeProposal {
  path: string;
  action: string;
  content?: string | null;
  diff?: FileChangeDiff | null;
}

export interface ChatMessage {
  id: string;
  session_id: string;
  project_id: string;
  role: 'user' | 'assistant' | string;
  content: string;
  token_count?: number | null;
  model?: string | null;
  latency_ms?: number | null;
  file_changes: FileChangeProposal[];
  undone?: boolean;
  created_at: string;
}

export interface UndoChangesResult {
  message_id: string;
  restored_paths: string[];
}

export interface ChatCompletion {
  user_message: ChatMessage;
  assistant_message: ChatMessage;
  applied_changes: FileChangeProposal[];
  metadata: Record<string, unknown>;
}

export interface EditorTab {
  id: string;
  path: string;
  name: string;
  language: string;
  content: string;
  dirty: boolean;
}
