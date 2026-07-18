/**
 * API helpers for manual link management.
 */

import { fetchWithAuth as fetch } from './fetchWithAuth';

const API_BASE = '/api/links';

/** Throw a descriptive error when a response is not OK. */
async function ensureOk(res: Response, action: string): Promise<void> {
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `${action} failed with HTTP ${res.status}`);
  }
}

export interface ManualLink {
  id: string;
  from: string;
  to: string;
  speed: number;
  type: string;
  map?: string;
}

export async function getManualLinks(): Promise<ManualLink[]> {
  const res = await fetch(`${API_BASE}/manual`);
  await ensureOk(res, 'Fetch manual links');
  return res.json();
}

export async function createLink(
  fromDevice: string,
  toDevice: string,
  speed: number = 1000,
  type: string = 'wired',
  map?: string,
): Promise<ManualLink> {
  const res = await fetch(API_BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      from_device: fromDevice,
      to_device: toDevice,
      speed,
      type,
      map,
    }),
  });
  await ensureOk(res, 'Create link');
  return res.json();
}

export async function deleteLink(linkId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/${encodeURIComponent(linkId)}`, { method: 'DELETE' });
  await ensureOk(res, 'Delete link');
}
