import { useEffect, useMemo, useRef, useState } from 'react';
import * as esbuild from 'esbuild-wasm';
import esbuildWasmUrl from 'esbuild-wasm/esbuild.wasm?url';
import type { ProjectFile } from '@/types';
import { Button } from '@/components/common/Button';
import { cn } from '@/utils/helpers';

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
const REACT_APP_PATHS = [
  'src/App.tsx',
  'src/App.jsx',
  'App.tsx',
  'App.jsx',
];
const VIRTUAL_REACT_ENTRY = '__araby_preview_entry__.tsx';
const SOURCE_EXTENSIONS = ['', '.tsx', '.ts', '.jsx', '.js', '.css', '.json'];
/**
 * CSS `url()` and `@import` targets are browser requests, not source modules.
 * Routing them through the module loader makes esbuild fail the whole bundle
 * ("NetworkError when attempting to fetch resource" / "Cannot use ... as a URL")
 * because of one image reference, so they must stay external.
 */
const ASSET_RESOLVE_KINDS = new Set<esbuild.ImportKind>(['url-token', 'import-rule']);
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
  /** True while background auto-repair / regenerate is in flight. */
  repairing?: boolean;
  /** Called when compile or runtime preview fails (e.g. missing imports). */
  onPreviewError?: (error: PreviewErrorInfo) => void;
}

export interface PreviewErrorInfo {
  kind: 'compile' | 'runtime';
  message: string;
  missingModule?: string;
}

/**
 * Live iframe preview for Website Builder projects.
 * Static HTML/CSS/JS projects render directly; React/TS projects are
 * compiled in-browser with esbuild-wasm into a self-contained bundle.
 */
export function LivePreview({
  files,
  onRefresh,
  refreshing,
  repairing = false,
  onPreviewError,
}: LivePreviewProps) {
  const staticDocument = useMemo(() => buildStaticPreviewDocument(files), [files]);
  const [documentHtml, setDocumentHtml] = useState(staticDocument);
  const [iframeSrc, setIframeSrc] = useState<string>();
  const [status, setStatus] = useState('Live Preview');
  const [compiling, setCompiling] = useState(false);
  const [lastError, setLastError] = useState<PreviewErrorInfo>();
  const onPreviewErrorRef = useRef(onPreviewError);
  onPreviewErrorRef.current = onPreviewError;

  useEffect(() => {
    let cancelled = false;
    const entry = findReactEntry(files);

    if (!entry) {
      setDocumentHtml(staticDocument);
      setStatus('Live Preview');
      setCompiling(false);
      setLastError(undefined);
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
          setLastError(undefined);
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          const message =
            error instanceof Error ? error.message : 'Unknown preview compilation error';
          // Keep a blank dark shell while auto-repair runs instead of an error page.
          setDocumentHtml(buildPreviewLoadingDocument());
          setStatus('Repairing preview…');
          const info: PreviewErrorInfo = {
            kind: 'compile',
            message,
            missingModule: extractMissingModule(message),
          };
          setLastError(info);
          onPreviewErrorRef.current?.(info);
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

  useEffect(() => {
    function onMessage(event: MessageEvent) {
      const data = event.data;
      if (!data || data.source !== 'araby-live-preview' || data.type !== 'runtime-error') {
        return;
      }
      const message = String(data.message || 'Preview runtime error');
      // React Router's default error UI ("Unexpected Application Error! 404 Not Found")
      // is a recoverable routing miss — never surface it in the Araby UI.
      if (isBenignRouterError(message)) {
        return;
      }
      // Swap to a blank loading shell; parent shows the motion buffer while repairing.
      setDocumentHtml(buildPreviewLoadingDocument());
      setStatus('Repairing preview…');
      const info: PreviewErrorInfo = {
        kind: 'runtime',
        message,
        missingModule: extractMissingModule(message),
      };
      setLastError(info);
      onPreviewErrorRef.current?.(info);
    }
    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, []);

  // If automatic repair finishes or exhausts its retries while the same error
  // remains, show the actual diagnostic instead of leaving a permanent black pane.
  useEffect(() => {
    if (!repairing && lastError && status === 'Repairing preview…') {
      if (isBenignRouterError(lastError.message)) {
        setLastError(undefined);
        setStatus('Live Preview');
        return;
      }
      setDocumentHtml(buildPreviewErrorDocument(lastError));
      setStatus('Preview error');
    }
  }, [lastError, repairing, status]);

  function handleOpenInNewTab() {
    // Dedicated blob so the tab keeps working even if the iframe preview refreshes.
    const blob = new Blob([documentHtml], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    const tab = window.open(url, '_blank', 'noopener,noreferrer');
    if (!tab) {
      URL.revokeObjectURL(url);
    }
  }

  const showLoader = repairing || compiling || Boolean(refreshing);

  return (
    <div className="relative flex h-full min-h-0 flex-col overflow-hidden bg-black">
      <div className="flex shrink-0 items-center justify-between gap-3 border-b border-white/10 bg-slate-950 px-4 py-2 text-sm font-medium text-slate-200">
        <span>{showLoader ? 'Loading…' : status}</span>
        <div className="flex shrink-0 items-center gap-2">
          <Button
            size="sm"
            variant="secondary"
            onClick={handleOpenInNewTab}
            disabled={showLoader || !documentHtml}
          >
            Open in new tab
          </Button>
          {onRefresh ? (
            <Button size="sm" variant="secondary" onClick={onRefresh} disabled={showLoader}>
              {refreshing ? 'Refreshing…' : 'Refresh preview'}
            </Button>
          ) : null}
        </div>
      </div>
      <div className="relative min-h-0 flex-1 bg-black">
        <iframe
          title="Website preview"
          className={cn(
            'h-full min-h-0 w-full bg-black',
            showLoader ? 'invisible' : 'visible',
          )}
          sandbox="allow-scripts allow-forms allow-modals allow-popups allow-same-origin"
          src={iframeSrc}
        />
        {showLoader ? <PreviewLoadingOverlay /> : null}
      </div>
    </div>
  );
}

function extractMissingModule(message: string): string | undefined {
  const match = message.match(/Missing module\s+"([^"]+)"/i);
  return match?.[1];
}

/**
 * React Router's default error boundary text. These are routing misses inside
 * the generated site, not Araby compile failures — hide them from the UI.
 */
function isBenignRouterError(message: string): boolean {
  return (
    /Unexpected Application Error/i.test(message) ||
    (/404\s*Not Found/i.test(message) && /router|route|application error/i.test(message)) ||
    /^404\s*Not Found$/i.test(message.trim())
  );
}

/**
 * Full-pane motion buffer matching a classic dotted spinner + "Loading.." label.
 */
function PreviewLoadingOverlay() {
  const dots = Array.from({ length: 12 }, (_, index) => index);
  return (
    <div
      className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-black"
      role="status"
      aria-live="polite"
      aria-label="Loading preview"
    >
      <div
        className="relative h-14 w-14"
        style={{ animation: 'preview-spinner-rotate 1s linear infinite' }}
      >
        {dots.map((index) => {
          const angle = (index / dots.length) * 360;
          const opacity = 0.15 + (index / (dots.length - 1)) * 0.85;
          return (
            <span
              key={index}
              className="absolute left-1/2 top-1/2 h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-white"
              style={{
                opacity,
                transform: `rotate(${angle}deg) translateY(-22px)`,
              }}
            />
          );
        })}
      </div>
      <p className="mt-5 text-sm font-medium tracking-wide text-white">Loading..</p>
      <style>{`
        @keyframes preview-spinner-rotate {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}

function buildPreviewLoadingDocument(): string {
  return `<!doctype html><html><body style="margin:0;background:#000"></body></html>`;
}

function buildPreviewErrorDocument(error: PreviewErrorInfo): string {
  const title = error.kind === 'compile' ? 'Preview compilation failed' : 'Preview crashed';
  const message = escapeHtml(error.message || 'Unknown preview error');
  return `<!doctype html>
<html>
  <body style="margin:0;min-height:100vh;background:#020617;color:#e2e8f0;font:15px/1.6 system-ui;padding:32px;box-sizing:border-box">
    <h1 style="margin:0 0 8px;color:#f87171;font-size:22px">${title}</h1>
    <p style="margin:0 0 16px;color:#94a3b8">Automatic repair could not resolve this issue.</p>
    <pre style="white-space:pre-wrap;overflow-wrap:anywhere;background:#0f172a;border:1px solid #334155;border-radius:10px;padding:16px;color:#fda4af">${message}</pre>
  </body>
</html>`;
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
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
  const conventionalEntry = REACT_ENTRY_PATHS.find((path) => paths.has(path));
  if (conventionalEntry) {
    return conventionalEntry;
  }

  // Generated projects occasionally contain a complete App component but omit
  // main.tsx/index.tsx. Compiling App directly succeeds without mounting it,
  // which produces a misleading blank white preview. A virtual entry keeps the
  // preview useful while the backend integrity repair creates the real entry.
  return REACT_APP_PATHS.some((path) => paths.has(path))
    ? VIRTUAL_REACT_ENTRY
    : undefined;
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
  if (entry === VIRTUAL_REACT_ENTRY) {
    const appPath = REACT_APP_PATHS.find((path) => sourceByPath.has(path));
    if (!appPath) {
      throw new Error(
        'React App component was detected but could not be resolved for Live Preview.',
      );
    }
    sourceByPath.set(
      VIRTUAL_REACT_ENTRY,
      [
        "import React from 'react';",
        "import { createRoot } from 'react-dom/client';",
        `import App from ${JSON.stringify(`./${appPath}`)};`,
        "const root = document.getElementById('root');",
        "if (!root) throw new Error('Live Preview could not find the #root element.');",
        'createRoot(root).render(React.createElement(App));',
      ].join('\n'),
    );
  }

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
          build.onResolve({ filter: /^https?:\/\// }, (args) => {
            if (ASSET_RESOLVE_KINDS.has(args.kind)) {
              return { path: args.path, external: true };
            }
            return {
              path: pinEsmShUrl(args.path),
              namespace: 'http-url',
            };
          });

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
            if (ASSET_RESOLVE_KINDS.has(args.kind)) {
              return { path: args.path, external: true };
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
function isBenignRouterErrorText(text) {
  var message = String(text || '');
  return /Unexpected Application Error/i.test(message) ||
    (/404\\s*Not Found/i.test(message) && /router|route|application error/i.test(message)) ||
    /^404\\s*Not Found$/i.test(message.trim());
}
function scrubRouterDefaultError() {
  var root = document.getElementById('root');
  if (!root) return;
  var text = root.textContent || '';
  if (!isBenignRouterErrorText(text)) return;
  // Soft recover: blank the React Router default 404 UI; do not alarm the parent shell.
  root.innerHTML = '<div style="min-height:100vh;margin:0;background:#0B1F3A" aria-hidden="true"></div>';
}
try {
  var _arabyObs = new MutationObserver(function () { scrubRouterDefaultError(); });
  _arabyObs.observe(document.documentElement, { childList: true, subtree: true, characterData: true });
  document.addEventListener('DOMContentLoaded', scrubRouterDefaultError);
  setInterval(scrubRouterDefaultError, 800);
} catch (e) {}
function showPreviewCrash(reason) {
  var message = '';
  if (reason && typeof reason === 'object') {
    message = (reason.message ? String(reason.message) + '\\n\\n' : '') + (reason.stack || '');
  } else {
    message = String(reason || 'Unknown runtime error');
  }
  if (isBenignRouterErrorText(message)) {
    scrubRouterDefaultError();
    return;
  }
  try {
    parent.postMessage(
      { source: 'araby-live-preview', type: 'runtime-error', message: message },
      '*'
    );
  } catch (e) {}
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
