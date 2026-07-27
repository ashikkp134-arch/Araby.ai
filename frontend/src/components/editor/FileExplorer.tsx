import type { FileNode } from '@/types';
import { cn } from '@/utils/helpers';

interface FileExplorerProps {
  nodes: FileNode[];
  activePath?: string | null;
  onOpenFile: (node: FileNode) => void;
  onCreateFile: () => void;
  onCreateFolder: () => void;
  onDeleteNode: (node: FileNode) => void;
}

/**
 * Nested file explorer sidebar for a project.
 */
export function FileExplorer({
  nodes,
  activePath,
  onOpenFile,
  onCreateFile,
  onCreateFolder,
  onDeleteNode,
}: FileExplorerProps) {
  return (
    <aside className="flex h-full flex-col border-r border-white/10 bg-ink-950/60">
      <div className="flex items-center justify-between border-b border-white/10 px-3 py-3">
        <h2 className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Files</h2>
        <div className="flex gap-1">
          <button
            type="button"
            onClick={onCreateFile}
            className="rounded px-2 py-1 text-xs text-accent hover:bg-white/5"
            title="New file"
          >
            + File
          </button>
          <button
            type="button"
            onClick={onCreateFolder}
            className="rounded px-2 py-1 text-xs text-slate-300 hover:bg-white/5"
            title="New folder"
          >
            + Folder
          </button>
        </div>
      </div>
      <div className="flex-1 overflow-auto p-2">
        {nodes.length === 0 ? (
          <p className="px-2 py-4 text-sm text-slate-500">No files yet.</p>
        ) : (
          <TreeList
            nodes={nodes}
            depth={0}
            activePath={activePath}
            onOpenFile={onOpenFile}
            onDeleteNode={onDeleteNode}
          />
        )}
      </div>
    </aside>
  );
}

function TreeList({
  nodes,
  depth,
  activePath,
  onOpenFile,
  onDeleteNode,
}: {
  nodes: FileNode[];
  depth: number;
  activePath?: string | null;
  onOpenFile: (node: FileNode) => void;
  onDeleteNode: (node: FileNode) => void;
}) {
  return (
    <ul className="space-y-0.5">
      {nodes.map((node) => (
        <li key={node.id}>
          <div
            className={cn(
              'group flex items-center justify-between rounded-md px-2 py-1.5 text-sm hover:bg-white/5',
              activePath === node.path && 'bg-accent/10 text-accent-soft',
            )}
            style={{ paddingLeft: `${depth * 12 + 8}px` }}
          >
            <button
              type="button"
              className="min-w-0 flex-1 truncate text-left"
              onClick={() => {
                if (node.type === 'file') {
                  onOpenFile(node);
                }
              }}
            >
              <span className="mr-2 font-mono text-[10px] text-slate-500">
                {node.type === 'folder' ? '[D]' : '[F]'}
              </span>
              {node.name}
            </button>
            <button
              type="button"
              className="hidden rounded px-1.5 text-xs text-rose-300 group-hover:inline"
              onClick={() => onDeleteNode(node)}
            >
              ×
            </button>
          </div>
          {node.type === 'folder' && node.children?.length ? (
            <TreeList
              nodes={node.children}
              depth={depth + 1}
              activePath={activePath}
              onOpenFile={onOpenFile}
              onDeleteNode={onDeleteNode}
            />
          ) : null}
        </li>
      ))}
    </ul>
  );
}
