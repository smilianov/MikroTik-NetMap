/**
 * Fetch wrapper that triggers logout and throws on 401 responses.
 */

import { useAuthStore } from '../stores/authStore';

export async function fetchWithAuth(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<Response> {
  const res = await fetch(input, init);
  if (res.status === 401) {
    useAuthStore.getState().logout();
    throw new Error('Session expired (HTTP 401) — logged out');
  }
  return res;
}
