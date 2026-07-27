import { Link } from 'react-router-dom';
import type { Project } from '@/types';
import { formatDate } from '@/utils/helpers';
import { Button } from '@/components/common/Button';

interface ProjectCardProps {
  project: Project;
  onDelete: (projectId: string) => void;
}

/**
 * Project summary card with open and delete actions.
 */
export function ProjectCard({ project, onDelete }: ProjectCardProps) {
  return (
    <article className="glass-panel flex flex-col justify-between rounded-2xl p-5">
      <div>
        <p className="text-xs uppercase tracking-[0.18em] text-slate-400">{project.workspace_type}</p>
        <h3 className="mt-2 font-display text-xl text-sand-50">{project.name}</h3>
        <p className="mt-2 line-clamp-2 text-sm text-slate-400">
          {project.description || 'No description yet.'}
        </p>
      </div>
      <div className="mt-5 flex items-center justify-between gap-3">
        <span className="text-xs text-slate-500">Updated {formatDate(project.updated_at)}</span>
        <div className="flex gap-2">
          <Button variant="ghost" size="sm" onClick={() => onDelete(project.id)}>
            Delete
          </Button>
          <Link to={`/projects/${project.id}`}>
            <Button size="sm">Open</Button>
          </Link>
        </div>
      </div>
    </article>
  );
}
