import { Link, Outlet } from 'react-router-dom';
import { useAuthStore } from '@/stores/authStore';
import { Button } from '@/components/common/Button';

/**
 * Authenticated application shell with top navigation.
 */
export function AppLayout() {
  const user = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-40 border-b border-white/10 bg-ink-950/80 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4 sm:px-6">
          <Link to="/workspaces" className="font-display text-xl tracking-tight text-sand-50">
            Araby <span className="text-accent">CodeAI</span>
          </Link>
          <div className="flex items-center gap-3">
            <span className="hidden text-sm text-slate-400 sm:inline">{user?.full_name}</span>
            <Button variant="ghost" size="sm" onClick={() => void logout()}>
              Log out
            </Button>
          </div>
        </div>
      </header>
      <main>
        <Outlet />
      </main>
    </div>
  );
}
