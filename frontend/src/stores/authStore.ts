/**
 * Zustand store for authentication state.
 */

import { create } from 'zustand';

interface AuthState {
  initialized: boolean;
  authenticated: boolean;
  authEnabled: boolean;
  username: string | null;
  role: string | null;
  loginError: string | null;

  checkAuth: () => Promise<void>;
  login: (username: string, password: string) => Promise<boolean>;
  logout: () => Promise<void>;
  clearError: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  initialized: false,
  authenticated: false,
  authEnabled: false,
  username: null,
  role: null,
  loginError: null,

  checkAuth: async () => {
    try {
      const res = await fetch('/api/auth/me');
      const data = await res.json();
      if (data.authenticated) {
        set({
          initialized: true,
          authenticated: true,
          authEnabled: data.auth_enabled ?? false,
          username: data.username ?? null,
          role: data.role ?? null,
        });
      } else {
        set({
          initialized: true,
          authenticated: false,
          authEnabled: true,
        });
      }
    } catch {
      set({ initialized: true, authenticated: false, authEnabled: true });
    }
  },

  login: async (username: string, password: string) => {
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      const data = await res.json();
      if (data.ok) {
        set({
          authenticated: true,
          username: data.username,
          role: data.role,
          loginError: null,
        });
        return true;
      } else {
        set({ loginError: data.error || 'Login failed' });
        return false;
      }
    } catch {
      set({ loginError: 'Connection error' });
      return false;
    }
  },

  logout: async () => {
    try {
      await fetch('/api/auth/logout', { method: 'POST' });
    } catch {
      // Ignore.
    }
    set({ authenticated: false, username: null, role: null });
  },

  clearError: () => set({ loginError: null }),
}));
