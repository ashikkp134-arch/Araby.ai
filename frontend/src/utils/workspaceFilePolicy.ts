/**
 * Workspace file-type edit policy for the editor and AI chat.
 *
 * Python / JavaScript workspaces can view any file, but only language sources
 * may be edited or AI-enhanced. Website workspaces are unrestricted.
 */

import type { WorkspaceType } from '@/types';

const PYTHON_EDITABLE = new Set(['.py']);
const JAVASCRIPT_EDITABLE = new Set(['.js', '.jsx', '.ts', '.tsx']);

export const PYTHON_EDIT_MESSAGE =
  'Only Python files can be edited or enhanced in this workspace.';

export const JAVASCRIPT_EDIT_MESSAGE =
  'Only JavaScript-related files (.js, .jsx, .ts, .tsx) can be edited or enhanced in this workspace.';

const EDIT_INTENT_RE =
  /\b(edit|enhance|improve|refactor|fix|update|modify|change|rewrite|implement|add|create|delete|remove|generate|replace)\b/i;

/**
 * Return the lowercase file extension including the leading dot.
 *
 * @param path - File path or name.
 * @returns Extension such as `.py`, or empty string for extensionless / dotfiles.
 */
export function fileExtension(path: string): string {
  const name = path.replace(/\\/g, '/').split('/').pop() || '';
  const dot = name.lastIndexOf('.');
  if (dot <= 0) {
    return '';
  }
  return name.slice(dot).toLowerCase();
}

/**
 * Allowed editable extensions for a workspace, or `null` when unrestricted.
 *
 * @param workspaceType - Active workspace.
 * @returns Set of extensions or null.
 */
export function editableExtensionsFor(
  workspaceType: WorkspaceType | string | undefined,
): Set<string> | null {
  const workspace = (workspaceType || '').toLowerCase();
  if (workspace === 'python') {
    return PYTHON_EDITABLE;
  }
  if (workspace === 'javascript') {
    return JAVASCRIPT_EDITABLE;
  }
  return null;
}

/**
 * User-facing restriction message for a workspace.
 *
 * @param workspaceType - Active workspace.
 * @returns Modal message text.
 */
export function editRestrictionMessage(
  workspaceType: WorkspaceType | string | undefined,
): string {
  const workspace = (workspaceType || '').toLowerCase();
  if (workspace === 'python') {
    return PYTHON_EDIT_MESSAGE;
  }
  if (workspace === 'javascript') {
    return JAVASCRIPT_EDIT_MESSAGE;
  }
  return 'This file type cannot be edited in the current workspace.';
}

/**
 * Whether a path may be edited / AI-enhanced in the workspace.
 *
 * @param workspaceType - Active workspace.
 * @param path - File path.
 * @returns True when edits are allowed.
 */
export function isPathEditable(
  workspaceType: WorkspaceType | string | undefined,
  path: string | undefined | null,
): boolean {
  if (!path) {
    return true;
  }
  const allowed = editableExtensionsFor(workspaceType);
  if (!allowed) {
    return true;
  }
  return allowed.has(fileExtension(path));
}

/**
 * Whether a chat message looks like an edit/enhance request.
 *
 * @param content - User chat text.
 * @returns True when the message implies file mutation.
 */
export function isEditIntentMessage(content: string): boolean {
  return EDIT_INTENT_RE.test(content || '');
}
