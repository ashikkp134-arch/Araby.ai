import { useEffect, useMemo, useState } from 'react';
import * as esbuild from 'esbuild-wasm';
import esbuildWasmUrl from 'esbuild-wasm/esbuild.wasm?url';
import type { ProjectFile } from '@/types';
import { Button } from '@/components/common/Button';

const SCRIPT_END = /<\/script/gi;
const REACT_ENTRY_PATHS = [
  'src/main.tsx',
  'src/index.tsx',
  'index.tsx',
  'src/main.jsx',
  'src/index.jsx',
  'index.jsx',
  'src/main.ts',
  'src/index.ts',
];
const SOURCE_EXTENSIONS = ['', '.tsx', '.ts', '.jsx', '.js', '.css', '.json'];
const CDN_PACKAGE_VERSIONS: Record<string, string> = {
  react: '18.3.1',
  'react-dom': '18.3.1',
  'react-router': '6.28.1',
  'react-router-dom': '6.28.1',
  'framer-motion': '11.15.0',
  'lucide-react': '0.468.0',
};

/**
 * esbuild-wasm only allows `initialize()` to run once per page load; calling it
 * again throws `Cannot call "initialize" more than once`. Vite HMR re-executes
 * this module's top-level code on every edit though, which would reset a plain
 * module-local variable and trigger a duplicate call. Stashing the ready-promise
 * on `globalThis` lets it survive HMR reloads of this file.
 */
const GLOBAL_KEY = '__livePreviewEsbuildReady__';
type GlobalWithEsbuild = typeof globalThis & { [GLOBAL_KEY]?: Promise<void> };
const globalWithEsbuild = globalThis as GlobalWithEsbuild;

/** Persist CDN fetches across rebuilds so Live Preview stays low-latency. */
const cdnHttpCache = new Map<string, string>();

function initializeCompiler(): Promise<void> {
  globalWithEsbuild[GLOBAL_KEY] ??= esbuild
    .initialize({
      wasmURL: esbuildWasmUrl,
      worker: true,
    })
    .catch((error: unknown) => {
      // Another HMR-surviving caller already initialized esbuild; treat as ready.
      if (error instanceof Error && /initialize.*more than once/i.test(error.message)) {
        return;
      }
      globalWithEsbuild[GLOBAL_KEY] = undefined;
      throw error;
    });
  return globalWithEsbuild[GLOBAL_KEY];
}

interface LivePreviewProps {
  files: ProjectFile[];
  onRefresh?: () => void;
  refreshing?: boolean;
}

/**
 * Live iframe preview for Website Builder projects.
 * Static HTML/CSS/JS projects render directly; React/TS projects are
 * compiled in-browser with esbuild-wasm into a self-contained bundle.
 */
export function LivePreview({ files, onRefresh, refreshing }: LivePreviewProps) {
  const staticDocument = useMemo(() => buildStaticPreviewDocument(files), [files]);
  const [documentHtml, setDocumentHtml] = useState(staticDocument);
  const [iframeSrc, setIframeSrc] = useState<string>();
  const [status, setStatus] = useState('Live Preview');
  const [compiling, setCompiling] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const entry = findReactEntry(files);

    if (!entry) {
      setDocumentHtml(staticDocument);
      setStatus('Live Preview');
      setCompiling(false);
      return () => {
        cancelled = true;
      };
    }

    setCompiling(true);
    setStatus('Compiling React preview…');

    void buildReactPreviewDocument(files, entry)
      .then((html) => {
        if (!cancelled) {
          setDocumentHtml(html);
          setStatus('Live Preview');
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setDocumentHtml(buildPreviewErrorDocument(error));
          setStatus('Preview error');
        }
      })
      .finally(() => {
        if (!cancelled) {
          setCompiling(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [files, staticDocument]);

  // Blob URLs give a real http(s) origin (unlike about:srcdoc), so history/URL
  // APIs and CDN-relative resolution behave like a normal page.
  useEffect(() => {
    const blob = new Blob([documentHtml], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    setIframeSrc(url);
    return () => {
      URL.revokeObjectURL(url);
    };
  }, [documentHtml]);

  function handleOpenInNewTab() {
    // Dedicated blob so the tab keeps working even if the iframe preview refreshes.
    const blob = new Blob([documentHtml], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    const tab = window.open(url, '_blank', 'noopener,noreferrer');
    if (!tab) {
      URL.revokeObjectURL(url);
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden bg-white">
      <div className="flex shrink-0 items-center justify-between gap-3 border-b border-slate-200 bg-slate-50 px-4 py-2 text-sm font-medium text-slate-700">
        <span>{status}</span>
        <div className="flex shrink-0 items-center gap-2">
          <Button
            size="sm"
            variant="secondary"
            onClick={handleOpenInNewTab}
            disabled={compiling || !documentHtml}
          >
            Open in new tab
          </Button>
          {onRefresh ? (
            <Button
              size="sm"
              variant="secondary"
              onClick={onRefresh}
              disabled={refreshing || compiling}
            >
              {refreshing ? 'Refreshing…' : 'Refresh preview'}
            </Button>
          ) : null}
        </div>
      </div>
      <iframe
        title="Website preview"
        className="min-h-0 flex-1 bg-slate-950"
        sandbox="allow-scripts allow-forms allow-modals allow-popups allow-same-origin"
        src={iframeSrc}
      />
    </div>
  );
}

/**
 * Compose HTML/CSS/JS files into a previewable document.
 */
function buildStaticPreviewDocument(files: ProjectFile[]): string {
  const htmlFile =
    files.find((file) => file.path === 'index.html') ||
    files.find((file) => file.path.endsWith('.html'));
  const css = files
    .filter((file) => file.path.endsWith('.css'))
    .map((file) => file.content)
    .join('\n');
  const js = files
    .filter((file) => file.path.endsWith('.js') && !file.path.includes('node_modules'))
    .map((file) => file.content)
    .join('\n');

  if (!htmlFile) {
    return `<!DOCTYPE html><html><body style="font-family:sans-serif;padding:2rem;background:#020617;color:#e2e8f0">
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
    const safeJs = js.replace(SCRIPT_END, '<\\/script');
    if (html.includes('</body>')) {
      html = html.replace('</body>', `<script>${safeJs}</script></body>`);
    } else {
      html = `${html}<script>${safeJs}</script>`;
    }
  }
  return html;
}

function findReactEntry(files: ProjectFile[]): string | undefined {
  const paths = new Set(files.map((file) => normalizePath(file.path)));
  return REACT_ENTRY_PATHS.find((path) => paths.has(path));
}

/**
 * Compile a generated React/TypeScript project into a self-contained preview document.
 * Dependencies are fetched from esm.sh and inlined so the iframe does not rely on import maps.
 */
async function buildReactPreviewDocument(
  files: ProjectFile[],
  entry: string,
): Promise<string> {
  await initializeCompiler();
  const sourceByPath = new Map(
    files.map((file) => [normalizePath(file.path), file.content] as const),
  );

  const result = await esbuild.build({
    entryPoints: [entry],
    bundle: true,
    write: false,
    outfile: 'preview-bundle.js',
    format: 'esm',
    platform: 'browser',
    target: 'es2020',
    jsx: 'automatic',
    // Sourcemaps inflate the iframe payload; keep preview compiles fast.
    sourcemap: false,
    logLevel: 'silent',
    plugins: [
      {
        name: 'workspace-and-cdn',
        setup(build) {
          build.onResolve({ filter: /^https?:\/\// }, (args) => ({
            path: pinEsmShUrl(args.path),
            namespace: 'http-url',
          }));

          build.onResolve({ filter: /.*/, namespace: 'http-url' }, (args) => {
            // Bare imports inside CDN modules must not be treated as relative paths.
            if (isBareImport(args.path)) {
              return {
                path: bareImportToCdnUrl(args.path),
                namespace: 'http-url',
              };
            }
            if (args.path.startsWith('/')) {
              return {
                path: pinEsmShUrl(`https://esm.sh${args.path}`),
                namespace: 'http-url',
              };
            }
            return {
              path: pinEsmShUrl(new URL(args.path, args.importer).toString()),
              namespace: 'http-url',
            };
          });

          build.onResolve({ filter: /.*/ }, (args) => {
            const exactPath = normalizePath(args.path);
            if (sourceByPath.has(exactPath)) {
              return { path: exactPath, namespace: 'workspace' };
            }
            if (isBareImport(args.path)) {
              return {
                path: bareImportToCdnUrl(args.path),
                namespace: 'http-url',
              };
            }
            const resolved = resolveWorkspaceImport(
              sourceByPath,
              args.path,
              args.resolveDir || directoryOf(args.importer || ''),
            );
            if (resolved) {
              return { path: resolved, namespace: 'workspace' };
            }
            return {
              path: args.path,
              namespace: 'missing',
            };
          });

          build.onLoad({ filter: /.*/, namespace: 'workspace' }, (args) => {
            const content = sourceByPath.get(args.path);
            if (content === undefined) {
              return null;
            }
            return {
              contents: adaptSourceForPreview(content, args.path),
              loader: loaderForPath(args.path),
              resolveDir: directoryOf(args.path),
            };
          });

          build.onLoad({ filter: /.*/, namespace: 'http-url' }, async (args) => {
            if (!cdnHttpCache.has(args.path)) {
              const response = await fetch(args.path);
              if (!response.ok) {
                throw new Error(
                  `Preview could not download dependency ${args.path} (${response.status}). Check network access.`,
                );
              }
              cdnHttpCache.set(args.path, await response.text());
            }
            return {
              contents: cdnHttpCache.get(args.path)!,
              loader: 'js',
            };
          });

          build.onLoad({ filter: /.*/, namespace: 'missing' }, (args) => ({
            contents: `throw new Error(${JSON.stringify(
              `Missing module "${args.path}". Generate the imported file or fix the import path.`,
            )});`,
            loader: 'js',
          }));
        },
      },
    ],
  });

  const javascript = result.outputFiles.find((file) => file.path.endsWith('.js'))?.text;
  if (!javascript) {
    throw new Error('The generated project did not produce a browser JavaScript bundle.');
  }

  const projectCss = files
    .filter((file) => {
      const path = normalizePath(file.path);
      return path.endsWith('.css') && (path.startsWith('src/') || path === 'src/styles.css');
    })
    .map((file) => file.content)
    .join('\n');

  const runtimeGuard = `
window.addEventListener('error', function (event) {
  showPreviewCrash(event.error || event.message);
});
window.addEventListener('unhandledrejection', function (event) {
  showPreviewCrash(event.reason);
});
function showPreviewCrash(reason) {
  var message = '';
  if (reason && typeof reason === 'object') {
    message = (reason.message ? String(reason.message) + '\\n\\n' : '') + (reason.stack || '');
  } else {
    message = String(reason || 'Unknown runtime error');
  }
  var root = document.getElementById('root');
  if (!root) return;
  root.innerHTML = '<div style="margin:0;padding:32px;font:15px/1.6 system-ui;background:#020617;color:#e2e8f0;min-height:100vh"><h1 style="color:#f87171;margin:0 0 8px">Preview runtime error</h1><p style="margin:0 0 16px;color:#94a3b8">The React app compiled, but crashed while starting.</p><pre style="white-space:pre-wrap;background:#0f172a;padding:16px;border-radius:8px;color:#fda4af;margin:0"></pre></div>';
  root.querySelector('pre').textContent = message;
}
`;

  return `<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Generated website preview</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
      tailwind.config = {
        theme: {
          extend: {
            colors: {
              gold: '#F5B301',
              stadium: '#0B1F3A',
            },
          },
        },
      };
    </script>
    <style>
      html, body, #root { min-height: 100%; margin: 0; }
      body { background: #0B1F3A; color: #f8fafc; }
      ${projectCss}
    </style>
  </head>
  <body>
    <div id="root"></div>
    <script>${runtimeGuard.replace(SCRIPT_END, '<\\/script')}</script>
    <script type="module">${javascript.replace(SCRIPT_END, '<\\/script')}</script>
  </body>
</html>`;
}

function normalizePath(path: string): string {
  const parts: string[] = [];
  for (const part of path.replace(/\\/g, '/').split('/')) {
    if (!part || part === '.') {
      continue;
    }
    if (part === '..') {
      parts.pop();
    } else {
      parts.push(part);
    }
  }
  return parts.join('/');
}

function directoryOf(path: string): string {
  const index = path.lastIndexOf('/');
  return index === -1 ? '' : path.slice(0, index);
}

function isBareImport(specifier: string): boolean {
  return !specifier.startsWith('.') && !specifier.startsWith('/') && !specifier.startsWith('@/');
}

function bareImportToCdnUrl(specifier: string): string {
  const match = specifier.match(/^((?:@[^/]+\/)?[^/]+)(\/.*)?$/);
  const pkg = match?.[1] || specifier;
  const subpath = match?.[2] || '';
  const version = CDN_PACKAGE_VERSIONS[pkg];
  const versioned = version ? `${pkg}@${version}` : pkg;
  return pinEsmShUrl(`https://esm.sh/${versioned}${subpath}`);
}

/**
 * Normalize esm.sh URLs so React peer ranges do not pull a second major version.
 */
function pinEsmShUrl(url: string): string {
  return url
    .replace(/esm\.sh\/react@[^/"'?]+/g, 'esm.sh/react@18.3.1')
    .replace(/esm\.sh\/react-dom@[^/"'?]+/g, 'esm.sh/react-dom@18.3.1')
    .replace(/esm\.sh\/scheduler@[^/"'?]+/g, 'esm.sh/scheduler@0.23.2');
}

function resolveWorkspaceImport(
  files: Map<string, string>,
  specifier: string,
  resolveDir: string,
): string | undefined {
  const base = specifier.startsWith('@/')
    ? `src/${specifier.slice(2)}`
    : specifier.startsWith('/')
      ? specifier.slice(1)
      : `${resolveDir}/${specifier}`;
  const normalized = normalizePath(base);
  const candidates = [
    ...SOURCE_EXTENSIONS.map((extension) => `${normalized}${extension}`),
    ...SOURCE_EXTENSIONS.filter(Boolean).map((extension) => `${normalized}/index${extension}`),
  ];
  return candidates.find((candidate) => files.has(candidate));
}

function loaderForPath(path: string): esbuild.Loader {
  if (path.endsWith('.tsx')) return 'tsx';
  if (path.endsWith('.ts')) return 'ts';
  if (path.endsWith('.jsx')) return 'jsx';
  if (path.endsWith('.css')) return 'css';
  if (path.endsWith('.json')) return 'json';
  return 'js';
}

function adaptSourceForPreview(content: string, path: string): string {
  if (!/\.[jt]sx?$/.test(path)) {
    return content;
  }
  // BrowserRouter/HashRouter call encodeLocation → new URL(path, location.href).
  // In preview iframes that base is often "about:srcdoc", which throws Invalid URL.
  // MemoryRouter keeps routing fully in-memory and is the reliable preview choice.
  return content
    .replace(/\bcreateBrowserRouter\b/g, 'createMemoryRouter')
    .replace(/\bcreateHashRouter\b/g, 'createMemoryRouter')
    .replace(/\bBrowserRouter\b/g, 'MemoryRouter')
    .replace(/\bHashRouter\b/g, 'MemoryRouter');
}

function buildPreviewErrorDocument(error: unknown): string {
  const message = error instanceof Error ? error.message : 'Unknown preview compilation error';
  const escaped = message
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
  return `<!doctype html><html><body style="margin:0;background:#020617;color:#e2e8f0;font:15px/1.6 system-ui;padding:32px">
    <h1 style="color:#f8fafc">Preview could not compile</h1>
    <p>The generated React/TypeScript files failed while building the live preview bundle.</p>
    <pre style="white-space:pre-wrap;background:#0f172a;padding:16px;border-radius:8px;color:#fda4af">${escaped}</pre>
  </body></html>`;
}
