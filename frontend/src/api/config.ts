import { fetchWithAuth as fetch } from './fetchWithAuth';

export interface ReloadConfigResponse {
  ok: boolean;
  config_path: string;
  devices: number;
  maps: number;
  links: number;
  discovery_enabled: boolean;
  discovery_running: boolean;
  traffic_enabled: boolean;
  traffic_running: boolean;
}

export async function reloadConfig(): Promise<ReloadConfigResponse> {
  const res = await fetch('/api/config/reload', { method: 'POST' });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Reload failed with HTTP ${res.status}`);
  }
  return res.json();
}
