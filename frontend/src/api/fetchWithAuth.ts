/**
 * Fetch wrapper that triggers logout on 401 responses.
 */

import { useAuthStore } from '../stores/authStore';

export async function fetchWithAuth(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<Response> {
  const res = await fetch(input, init);
  if (res.status === 401) {
    useAuthStore.getState().logout();
  }
  return res;
}
