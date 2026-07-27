import { useEffect } from 'react';
import { BrowserRouter } from 'react-router-dom';
import { AppProviders } from '@/contexts/AppProviders';
import { AppRoutes } from '@/routes/AppRoutes';
import { useAuthStore } from '@/stores/authStore';

/**
 * Root application component with providers.
 */
function App() {
  const bootstrap = useAuthStore((state) => state.bootstrap);

  useEffect(() => {
    void bootstrap();
  }, [bootstrap]);

  return (
    <AppProviders>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </AppProviders>
  );
}

export default App;
