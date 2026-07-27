import { Link, Outlet } from 'react-router-dom';

/**
 * Public layout for authentication pages.
 */
export function AuthLayout() {
  return (
    <div className="relative min-h-screen overflow-hidden">
      <div className="pointer-events-none absolute -left-20 top-20 h-64 w-64 animate-drift rounded-full bg-accent/10 blur-3xl" />
      <div className="pointer-events-none absolute bottom-10 right-0 h-72 w-72 animate-drift rounded-full bg-sky-400/10 blur-3xl" />
      <div className="mx-auto flex min-h-screen max-w-6xl flex-col justify-center px-4 py-10 sm:px-6">
        <Link to="/login" className="mb-10 font-display text-3xl text-sand-50">
          Araby <span className="text-accent">CodeAI</span>
        </Link>
        <Outlet />
      </div>
    </div>
  );
}
