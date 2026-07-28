import JSZip from 'jszip';
import type { ProjectFile } from '@/types';

/**
 * Build and trigger a browser download of every project file as a ZIP archive.
 *
 * @param projectName - Used for the archive filename.
 * @param files - Project files to include.
 */
export async function downloadProjectZip(
  projectName: string,
  files: ProjectFile[],
): Promise<void> {
  if (!files.length) {
    throw new Error('This project has no files to download.');
  }

  const zip = new JSZip();
  const used = new Set<string>();

  for (const file of files) {
    const path = (file.path || file.name || 'untitled').replace(/^\/+/, '');
    if (!path || used.has(path)) {
      continue;
    }
    used.add(path);
    zip.file(path, file.content ?? '');
  }

  const blob = await zip.generateAsync({ type: 'blob', compression: 'DEFLATE' });
  const safeName =
    (projectName || 'project')
      .trim()
      .replace(/[^\w.\- ]+/g, '')
      .replace(/\s+/g, '-')
      .slice(0, 80) || 'project';

  const url = URL.createObjectURL(blob);
  try {
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `${safeName}.zip`;
    anchor.rel = 'noopener';
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
}
