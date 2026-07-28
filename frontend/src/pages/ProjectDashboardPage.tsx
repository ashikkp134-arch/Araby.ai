import { FormEvent, useRef, useState, type ChangeEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { createProject, deleteProject, importProject, listProjects } from '@/api/projects';
import { ProjectCard } from '@/components/project/ProjectCard';
import { Button } from '@/components/common/Button';
import { EmptyState, Modal, Spinner } from '@/components/common/Modal';
import { Input } from '@/components/common/Input';
import type { WorkspaceType } from '@/types';
import { getErrorMessage } from '@/utils/helpers';
import { readLocalFolder, type LocalFolderSelection } from '@/utils/localFolderImport';

const titles: Record<WorkspaceType, string> = {
  javascript: 'JavaScript Workspace',
  python: 'Python Workspace',
  website: 'Website Builder',
};

/**
 * Project dashboard for a specific workspace type.
 */
export function ProjectDashboardPage() {
  const { workspaceType = 'javascript' } = useParams<{ workspaceType: WorkspaceType }>();
  const typedWorkspace = workspaceType as WorkspaceType;
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const folderInputRef = useRef<HTMLInputElement | null>(null);

  /**
   * Bind directory-picker attributes that TypeScript's JSX types omit.
   *
   * @param node - Hidden file input element.
   */
  function bindFolderInput(node: HTMLInputElement | null) {
    folderInputRef.current = node;
    if (node) {
      node.setAttribute('webkitdirectory', '');
      node.setAttribute('directory', '');
    }
  }

  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [error, setError] = useState('');

  const [importOpen, setImportOpen] = useState(false);
  const [importName, setImportName] = useState('');
  const [importDescription, setImportDescription] = useState('');
  const [importSelection, setImportSelection] = useState<LocalFolderSelection | null>(null);
  const [importError, setImportError] = useState('');
  const [importReading, setImportReading] = useState(false);

  const projectsQuery = useQuery({
    queryKey: ['projects', typedWorkspace],
    queryFn: () => listProjects({ workspace_type: typedWorkspace, page: 1, page_size: 50 }),
  });

  const createMutation = useMutation({
    mutationFn: createProject,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['projects', typedWorkspace] });
      setOpen(false);
      setName('');
      setDescription('');
    },
  });

  const importMutation = useMutation({
    mutationFn: importProject,
    onSuccess: async (project) => {
      await queryClient.invalidateQueries({ queryKey: ['projects', typedWorkspace] });
      setImportOpen(false);
      setImportSelection(null);
      setImportName('');
      setImportDescription('');
      navigate(`/projects/${project.id}`);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteProject,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['projects', typedWorkspace] });
    },
  });

  /**
   * Create a project in the current workspace.
   *
   * @param event - Form submit event.
   */
  async function handleCreate(event: FormEvent) {
    event.preventDefault();
    setError('');
    try {
      await createMutation.mutateAsync({
        name,
        description,
        workspace_type: typedWorkspace,
      });
    } catch (err) {
      setError(getErrorMessage(err));
    }
  }

  /**
   * Open the OS folder picker for local import.
   */
  function handleOpenProjectClick() {
    setImportError('');
    folderInputRef.current?.click();
  }

  /**
   * Read the chosen folder and open the import confirmation modal.
   *
   * @param event - Change event from the directory file input.
   */
  async function handleFolderPicked(event: ChangeEvent<HTMLInputElement>) {
    const list = event.target.files;
    // Allow selecting the same folder again later.
    event.target.value = '';
    if (!list || list.length === 0) {
      return;
    }
    setImportReading(true);
    setImportError('');
    try {
      const selection = await readLocalFolder(list);
      setImportSelection(selection);
      setImportName(selection.folderName.slice(0, 120));
      setImportDescription('Imported from local folder');
      setImportOpen(true);
    } catch (err) {
      setImportError(err instanceof Error ? err.message : getErrorMessage(err));
    } finally {
      setImportReading(false);
    }
  }

  /**
   * Confirm import and create the project from local files.
   *
   * @param event - Form submit event.
   */
  async function handleImportConfirm(event: FormEvent) {
    event.preventDefault();
    if (!importSelection) {
      return;
    }
    setImportError('');
    try {
      await importMutation.mutateAsync({
        name: importName.trim() || importSelection.folderName,
        description: importDescription,
        workspace_type: typedWorkspace,
        files: importSelection.files,
      });
    } catch (err) {
      setImportError(getErrorMessage(err));
    }
  }

  return (
    <section className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <Link to="/workspaces" className="text-sm text-accent hover:underline">
            ← All workspaces
          </Link>
          <h1 className="mt-2 font-display text-4xl">{titles[typedWorkspace] || 'Workspace'}</h1>
          <p className="mt-2 text-slate-400">
            Create a new project or open an existing folder from your computer.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="secondary"
            onClick={handleOpenProjectClick}
            disabled={importReading || importMutation.isPending}
          >
            {importReading ? 'Reading folder…' : 'Open project'}
          </Button>
          <Button onClick={() => setOpen(true)}>New project</Button>
        </div>
      </div>

      <input
        ref={bindFolderInput}
        type="file"
        className="hidden"
        multiple
        onChange={handleFolderPicked}
      />

      {importError && !importOpen ? (
        <p className="mt-4 text-sm text-rose-300">{importError}</p>
      ) : null}

      <div className="mt-8">
        {projectsQuery.isLoading ? <Spinner label="Loading projects" /> : null}
        {projectsQuery.data?.items.length === 0 ? (
          <EmptyState
            title="No projects yet"
            description="Create a new project or open a local folder to start editing with AI chat."
          />
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {projectsQuery.data?.items.map((project) => (
              <ProjectCard
                key={project.id}
                project={project}
                onDelete={(id) => {
                  if (window.confirm('Delete this project and all files?')) {
                    deleteMutation.mutate(id);
                  }
                }}
              />
            ))}
          </div>
        )}
      </div>

      {open ? (
        <Modal title="Create project" onClose={() => setOpen(false)}>
          <form className="space-y-4" onSubmit={handleCreate}>
            <Input
              label="Project name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              required
            />
            <Input
              label="Description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
            {error ? <p className="text-sm text-rose-300">{error}</p> : null}
            <Button type="submit" className="w-full" disabled={createMutation.isPending}>
              {createMutation.isPending ? 'Creating…' : 'Create'}
            </Button>
          </form>
        </Modal>
      ) : null}

      {importOpen && importSelection ? (
        <Modal
          title="Open local project"
          onClose={() => {
            if (importMutation.isPending) {
              return;
            }
            setImportOpen(false);
            setImportSelection(null);
            setImportError('');
          }}
        >
          <form className="space-y-4" onSubmit={handleImportConfirm}>
            <p className="text-sm text-slate-400">
              Importing <span className="text-sand-50">{importSelection.files.length}</span> text
              file{importSelection.files.length === 1 ? '' : 's'}
              {importSelection.skipped > 0
                ? ` (${importSelection.skipped} skipped: binaries, deps, or oversized)`
                : ''}
              . You can edit, save, and chat with AI the same as any other project.
            </p>
            <Input
              label="Project name"
              value={importName}
              onChange={(event) => setImportName(event.target.value)}
              required
            />
            <Input
              label="Description"
              value={importDescription}
              onChange={(event) => setImportDescription(event.target.value)}
            />
            {importError ? <p className="text-sm text-rose-300">{importError}</p> : null}
            <Button type="submit" className="w-full" disabled={importMutation.isPending}>
              {importMutation.isPending ? 'Importing…' : 'Import & open'}
            </Button>
          </form>
        </Modal>
      ) : null}
    </section>
  );
}
