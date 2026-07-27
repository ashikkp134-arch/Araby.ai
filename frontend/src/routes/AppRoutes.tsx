import { Navigate, Route, Routes } from 'react-router-dom';
import { ProtectedRoute, PublicOnlyRoute } from '@/auth/ProtectedRoute';
import { AppLayout } from '@/layouts/AppLayout';
import { AuthLayout } from '@/layouts/AuthLayout';
import { LoginPage } from '@/pages/LoginPage';
import { SignupPage } from '@/pages/SignupPage';
import { WorkspacesPage } from '@/pages/WorkspacesPage';
import { ProjectDashboardPage } from '@/pages/ProjectDashboardPage';
import { EditorPage } from '@/pages/EditorPage';

/**
 * Application route table.
 */
export function AppRoutes() {
  return (
    <Routes>
      <Route element={<PublicOnlyRoute />}>
        <Route element={<AuthLayout />}>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/signup" element={<SignupPage />} />
        </Route>
      </Route>

      <Route element={<ProtectedRoute />}>
        <Route element={<AppLayout />}>
          <Route path="/workspaces" element={<WorkspacesPage />} />
          <Route path="/workspaces/:workspaceType" element={<ProjectDashboardPage />} />
          <Route path="/projects/:projectId" element={<EditorPage />} />
        </Route>
      </Route>

      <Route path="/" element={<Navigate to="/workspaces" replace />} />
      <Route path="*" element={<Navigate to="/workspaces" replace />} />
    </Routes>
  );
}
