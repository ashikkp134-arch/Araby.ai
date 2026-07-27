import { useMemo } from 'react';
import type { ProjectFile } from '@/types';

interface LivePreviewProps {
  files: ProjectFile[];
}

/**
 * Live iframe preview for Website Builder projects.
 */
export function LivePreview({ files }: LivePreviewProps) {
  const srcDoc = useMemo(() => buildPreviewDocument(files), [files]);

  return (
    <div className="flex h-full flex-col border-l border-white/10 bg-white">
      <div className="border-b border-slate-200 bg-slate-50 px-4 py-2 text-sm font-medium text-slate-700">
        Live Preview
      </div>
      <iframe title="Website preview" className="min-h-0 flex-1 bg-white" srcDoc={srcDoc} />
    </div>
  );
}

/**
 * Compose HTML/CSS/JS files into a previewable document.
 *
 * @param files - Project files.
 * @returns HTML document string.
 */
function buildPreviewDocument(files: ProjectFile[]): string {
  const htmlFile =
    files.find((file) => file.path === 'index.html') ||
    files.find((file) => file.path.endsWith('.html'));
  const css = files
    .filter((file) => file.path.endsWith('.css'))
    .map((file) => file.content)
    .join('\n');
  const js = files
    .filter((file) => file.path.endsWith('.js'))
    .map((file) => file.content)
    .join('\n');

  if (!htmlFile) {
    return `<!DOCTYPE html><html><body style="font-family:sans-serif;padding:2rem">
      <h1>No HTML file found</h1>
      <p>Create an index.html to preview your website.</p>
    </body></html>`;
  }

  let html = htmlFile.content;
  if (css) {
    if (html.includes('</head>')) {
      html = html.replace('</head>', `<style>${css}</style></head>`);
    } else {
      html = `<style>${css}</style>${html}`;
    }
  }
  if (js) {
    if (html.includes('</body>')) {
      html = html.replace('</body>', `<script>${js}</script></body>`);
    } else {
      html = `${html}<script>${js}</script>`;
    }
  }
  return html;
}
