/**
 * API helpers for device visibility (hide / blacklist).
 */

import { fetchWithAuth as fetch } from './fetchWithAuth';

const API_BASE = '/api/devices';

/** Throw a descriptive error when a response is not OK. */
async function ensureOk(res: Response, action: string): Promise<void> {
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `${action} failed with HTTP ${res.status}`);
  }
}

export async function hideDevice(deviceId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/${encodeURIComponent(deviceId)}/hide`, { method: 'POST' });
  await ensureOk(res, 'Hide device');
}

export async function unhideDevice(deviceId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/${encodeURIComponent(deviceId)}/unhide`, { method: 'POST' });
  await ensureOk(res, 'Unhide device');
}

export async function blacklistDevice(deviceId: string, reason?: string): Promise<void> {
  const res = await fetch(`${API_BASE}/${encodeURIComponent(deviceId)}/blacklist`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason: reason || '' }),
  });
  await ensureOk(res, 'Blacklist device');
}

export async function unblacklistDevice(deviceId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/${encodeURIComponent(deviceId)}/unblacklist`, { method: 'POST' });
  await ensureOk(res, 'Unblacklist device');
}

export interface BlacklistedEntry {
  id: string;
  host: string;
  mac: string;
  reason: string;
  blacklisted_at: string;
}

export async function getBlacklisted(): Promise<BlacklistedEntry[]> {
  const res = await fetch(`${API_BASE}/blacklisted`);
  await ensureOk(res, 'Fetch blacklist');
  return res.json();
}

export async function moveDeviceToMap(deviceId: string, mapName: string): Promise<void> {
  const res = await fetch(`${API_BASE}/${encodeURIComponent(deviceId)}/map`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ map: mapName }),
  });
  await ensureOk(res, 'Move device to map');
}

export async function renameMap(mapName: string, label: string): Promise<void> {
  const res = await fetch(`/api/maps/${encodeURIComponent(mapName)}/label`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ label }),
  });
  await ensureOk(res, 'Rename map');
}

export async function createMap(name: string, label: string): Promise<void> {
  const res = await fetch('/api/maps', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, label }),
  });
  await ensureOk(res, 'Create map');
}

export async function deleteMap(mapName: string): Promise<void> {
  const res = await fetch(`/api/maps/${encodeURIComponent(mapName)}`, { method: 'DELETE' });
  await ensureOk(res, 'Delete map');
}

export async function pinDevice(deviceId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/${encodeURIComponent(deviceId)}/pin`, { method: 'POST' });
  await ensureOk(res, 'Pin device');
}

export async function unpinDevice(deviceId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/${encodeURIComponent(deviceId)}/pin`, { method: 'DELETE' });
  await ensureOk(res, 'Unpin device');
}
