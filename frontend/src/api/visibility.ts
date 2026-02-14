/**
 * API helpers for device visibility (hide / blacklist).
 */

const API_BASE = '/api/devices';

export async function hideDevice(deviceId: string): Promise<void> {
  await fetch(`${API_BASE}/${encodeURIComponent(deviceId)}/hide`, { method: 'POST' });
}

export async function unhideDevice(deviceId: string): Promise<void> {
  await fetch(`${API_BASE}/${encodeURIComponent(deviceId)}/unhide`, { method: 'POST' });
}

export async function blacklistDevice(deviceId: string, reason?: string): Promise<void> {
  await fetch(`${API_BASE}/${encodeURIComponent(deviceId)}/blacklist`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason: reason || '' }),
  });
}

export async function unblacklistDevice(deviceId: string): Promise<void> {
  await fetch(`${API_BASE}/${encodeURIComponent(deviceId)}/unblacklist`, { method: 'POST' });
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
  return res.json();
}

export async function moveDeviceToMap(deviceId: string, mapName: string): Promise<void> {
  await fetch(`${API_BASE}/${encodeURIComponent(deviceId)}/map`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ map: mapName }),
  });
}

export async function renameMap(mapName: string, label: string): Promise<void> {
  await fetch(`/api/maps/${encodeURIComponent(mapName)}/label`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ label }),
  });
}

export async function createMap(name: string, label: string): Promise<void> {
  await fetch('/api/maps', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, label }),
  });
}

export async function deleteMap(mapName: string): Promise<void> {
  await fetch(`/api/maps/${encodeURIComponent(mapName)}`, { method: 'DELETE' });
}
