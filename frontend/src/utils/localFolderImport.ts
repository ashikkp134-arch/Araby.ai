/**
 * Helpers for importing a local folder into a workspace project.
 */

/** Directories skipped when reading a local folder. */
const SKIP_DIRS = new Set([
  'node_modules',
  '.git',
  '.svn',
  '.hg',
  'dist',
  'build',
  '.next',
  '.nuxt',
  'coverage',
  '__pycache__',
  '.venv',
  'venv',
  'vendor',
  '.idea',
  '.vscode',
  '.turbo',
  '.cache',
]);

/** File extensions treated as binary / non-editable and skipped. */
const SKIP_EXTENSIONS = new Set([
  '.png',
  '.jpg',
  '.jpeg',
  '.gif',
  '.webp',
  '.ico',
  '.bmp',
  '.svg',
  '.pdf',
  '.zip',
  '.gz',
  '.tar',
  '.rar',
  '.7z',
  '.woff',
  '.woff2',
  '.ttf',
  '.eot',
  '.mp3',
  '.mp4',
  '.webm',
  '.wasm',
  '.exe',
  '.dll',
  '.so',
  '.dylib',
  '.class',
  '.jar',
  '.pyc',
  '.lock',
]);

const MAX_FILES = 200;
const MAX_FILE_BYTES = 256 * 1024;
const MAX_TOTAL_BYTES = 5 * 1024 * 1024;

export interface LocalImportFile {
  path: string;
  content: string;
}

export interface LocalFolderSelection {
  folderName: string;
  files: LocalImportFile[];
  skipped: number;
}

/**
 * Whether a relative path should be excluded from import.
 *
 * @param relativePath - Path relative to the chosen folder root.
 * @returns True when the path should be skipped.
 */
function shouldSkipPath(relativePath: string): boolean {
  const parts = relativePath.split('/').filter(Boolean);
  if (parts.some((part) => SKIP_DIRS.has(part))) {
    return true;
  }
  const name = parts[parts.length - 1] || '';
  if (name.startsWith('.') && name !== '.env.example' && name !== '.gitignore') {
    // Keep common text dotfiles; skip the rest (e.g. .DS_Store).
    const allowedDot = new Set(['.env.example', '.gitignore', '.editorconfig', '.prettierrc']);
    if (!allowedDot.has(name) && !name.endsWith('.json') && !name.endsWith('.yml') && !name.endsWith('.yaml')) {
      if (name === '.DS_Store' || name === '.env') {
        return true;
      }
    }
  }
  const dot = name.lastIndexOf('.');
  if (dot >= 0) {
    const ext = name.slice(dot).toLowerCase();
    if (SKIP_EXTENSIONS.has(ext)) {
      return true;
    }
  }
  return false;
}

/**
 * Strip the top-level folder name from a webkitRelativePath.
 *
 * Browser folder picks prefix every path with the root folder name.
 *
 * @param relativePath - webkitRelativePath value.
 * @returns Path inside the project root.
 */
function stripRootFolder(relativePath: string): string {
  const normalized = relativePath.replace(/\\/g, '/');
  const slash = normalized.indexOf('/');
  if (slash === -1) {
    return normalized;
  }
  return normalized.slice(slash + 1);
}

/**
 * Read a FileList from a directory input into importable text files.
 *
 * @param fileList - Files from `<input webkitdirectory>`.
 * @returns Folder name plus filtered text files.
 */
export async function readLocalFolder(fileList: FileList): Promise<LocalFolderSelection> {
  const files = Array.from(fileList);
  if (files.length === 0) {
    throw new Error('No files selected');
  }

  const firstPath = (files[0].webkitRelativePath || files[0].name).replace(/\\/g, '/');
  const folderName = firstPath.split('/')[0] || 'imported-project';

  const selected: LocalImportFile[] = [];
  let skipped = 0;
  let totalBytes = 0;

  for (const file of files) {
    const relative = stripRootFolder(file.webkitRelativePath || file.name);
    if (!relative || shouldSkipPath(relative)) {
      skipped += 1;
      continue;
    }
    if (file.size > MAX_FILE_BYTES) {
      skipped += 1;
      continue;
    }
    if (selected.length >= MAX_FILES) {
      skipped += 1;
      continue;
    }

    let content: string;
    try {
      content = await file.text();
    } catch {
      skipped += 1;
      continue;
    }

    // Skip likely-binary payloads that slipped past extension filters.
    if (content.includes('\u0000')) {
      skipped += 1;
      continue;
    }

    const bytes = new TextEncoder().encode(content).length;
    if (totalBytes + bytes > MAX_TOTAL_BYTES) {
      skipped += 1;
      continue;
    }
    totalBytes += bytes;
    selected.push({ path: relative, content });
  }

  if (selected.length === 0) {
    throw new Error('No importable text files found in that folder');
  }

  return { folderName, files: selected, skipped };
}
