import { useQuery } from '@tanstack/react-query';
import { listWorkspaces } from '@/api/workspaces';
import { WorkspaceCard } from '@/components/workspace/WorkspaceCard';
import { Spinner } from '@/components/common/Modal';

/**
 * Hub page showing the three workspace cards.
 */
export function WorkspacesPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['workspaces'],
    queryFn: listWorkspaces,
  });

  return (
    <section className="mx-auto max-w-7xl px-4 py-10 sm:px-6">
      <div className="max-w-2xl animate-rise">
        <p className="text-xs uppercase tracking-[0.22em] text-accent-soft">Workspaces</p>
        <h1 className="mt-3 font-display text-4xl tracking-tight sm:text-5xl">
          Choose your coding environment
        </h1>
        <p className="mt-4 text-base leading-7 text-slate-300">
          Spin up isolated JavaScript, Python, or Website Builder projects with AI chat, nested
          files & editor.
        </p>
      </div>

      <div className="mt-10">
        {isLoading ? <Spinner label="Loading workspaces" /> : null}
        {error ? <p className="text-rose-300">Failed to load workspaces.</p> : null}
        <div className="grid gap-5 md:grid-cols-3">
          {data?.map((workspace) => (
            <WorkspaceCard key={workspace.type} workspace={workspace} className="animate-rise" />
          ))}
        </div>
      </div>
    </section>
  );
}
