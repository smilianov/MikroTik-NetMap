/**
 * API helpers for manual link management.
 */

import { fetchWithAuth as fetch } from './fetchWithAuth';

const API_BASE = '/api/links';

export interface ManualLink {
  id: string;
  from: string;
  to: string;
  speed: number;
  type: string;
}

export async function getManualLinks(): Promise<ManualLink[]> {
  const res = await fetch(`${API_BASE}/manual`);
  return res.json();
}

export async function createLink(
  fromDevice: string,
  toDevice: string,
  speed: number = 1000,
  type: string = 'wired',
): Promise<ManualLink> {
  const res = await fetch(API_BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      from_device: fromDevice,
      to_device: toDevice,
      speed,
      type,
    }),
  });
  return res.json();
}

export async function deleteLink(linkId: string): Promise<void> {
  await fetch(`${API_BASE}/${encodeURIComponent(linkId)}`, { method: 'DELETE' });
}
