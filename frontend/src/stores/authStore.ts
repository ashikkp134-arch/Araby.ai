import { create } from 'zustand';
import * as authApi from '@/api/auth';
import { setAccessToken } from '@/api/client';
import type { User } from '@/types';

const SESSION_HINT_KEY = 'acw_has_session';

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isBootstrapping: boolean;
  setSession: (user: User, accessToken: string) => void;
  clearSession: () => void;
  bootstrap: () => Promise<void>;
  logout: () => Promise<void>;
}

let bootstrapPromise: Promise<void> | null = null;
let bootstrapGeneration = 0;

/**
 * Mark that a refresh cookie may exist (non-sensitive client hint).
 */
function markSessionHint(): void {
  try {
    sessionStorage.setItem(SESSION_HINT_KEY, '1');
  } catch {
    // Ignore storage failures (private mode, etc.).
  }
}

/**
 * Clear the client session hint.
 */
function clearSessionHint(): void {
  try {
    sessionStorage.removeItem(SESSION_HINT_KEY);
  } catch {
    // Ignore storage failures.
  }
}

/**
 * Whether bootstrap should attempt a cookie refresh.
 *
 * @returns True when a prior login may have set a refresh cookie.
 */
function shouldAttemptBootstrapRefresh(): boolean {
  try {
    return sessionStorage.getItem(SESSION_HINT_KEY) === '1';
  } catch {
    return false;
  }
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  isAuthenticated: false,
  isBootstrapping: true,

  setSession: (user, accessToken) => {
    // Invalidate any in-flight bootstrap so a late 401 refresh cannot wipe login.
    bootstrapGeneration += 1;
    bootstrapPromise = null;
    markSessionHint();
    setAccessToken(accessToken);
    set({ user, isAuthenticated: true, isBootstrapping: false });
  },

  clearSession: () => {
    bootstrapGeneration += 1;
    bootstrapPromise = null;
    clearSessionHint();
    setAccessToken(null);
    set({ user: null, isAuthenticated: false, isBootstrapping: false });
  },

  bootstrap: async () => {
    if (get().isAuthenticated && get().user) {
      set({ isBootstrapping: false });
      return;
    }

    // No prior login in this tab — skip refresh to avoid noisy 401s.
    if (!shouldAttemptBootstrapRefresh()) {
      set({ isBootstrapping: false, isAuthenticated: false, user: null });
      return;
    }

    if (bootstrapPromise) {
      return bootstrapPromise;
    }

    const generation = bootstrapGeneration;
    bootstrapPromise = (async () => {
      try {
        const tokens = await authApi.refreshSession();
        if (generation !== bootstrapGeneration) {
          return;
        }
        markSessionHint();
        setAccessToken(tokens.access_token);
        set({ user: tokens.user, isAuthenticated: true, isBootstrapping: false });
      } catch {
        // Never clear a session established while refresh was in flight.
        if (generation !== bootstrapGeneration || get().isAuthenticated) {
          set({ isBootstrapping: false });
          return;
        }
        clearSessionHint();
        setAccessToken(null);
        set({ user: null, isAuthenticated: false, isBootstrapping: false });
      } finally {
        if (generation === bootstrapGeneration) {
          bootstrapPromise = null;
        }
      }
    })();

    return bootstrapPromise;
  },

  logout: async () => {
    bootstrapGeneration += 1;
    bootstrapPromise = null;
    try {
      await authApi.logout();
    } finally {
      clearSessionHint();
      setAccessToken(null);
      set({ user: null, isAuthenticated: false, isBootstrapping: false });
    }
  },
}));
