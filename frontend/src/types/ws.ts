/**
 * Wire shapes for server→client WebSocket messages.
 * Mirrors the backend payloads documented in the README API Reference.
 */

export interface WsDevice {
  id: string;
  name: string;
  host: string;
  type: string;
  profile?: string;
  map?: string;
  position?: { x: number; y: number };
  parent?: string | null;
  discovered?: boolean;
  pinned?: boolean;
}

export interface WsLink {
  id?: string;
  from: string;
  to: string;
  speed: number;
  type: string;
  confirmed?: boolean;
  manual?: boolean;
  discovered?: boolean;
  map?: string;
}

export interface WsThreshold {
  max_seconds: number;
  color: string;
  label: string;
}

export interface WsMap {
  name: string;
  label?: string;
  parent?: string | null;
  background?: string | null;
}

export interface WsPingEntry {
  id: string;
  last_seen: string | null;
  rtt_ms: number | null;
  is_alive: boolean;
}

export interface WsTrafficStats {
  rx_bps: number;
  tx_bps: number;
}

/** Discriminated union of all messages the server can send. */
export type ServerMessage =
  | {
      type: 'config';
      devices?: WsDevice[];
      links?: WsLink[];
      thresholds?: WsThreshold[];
      maps?: WsMap[];
      hidden?: string[];
      blacklisted?: string[];
    }
  | { type: 'ping_state'; devices?: WsPingEntry[] }
  | {
      type: 'topology_update';
      added_devices?: WsDevice[];
      added_links?: WsLink[];
      removed_links?: string[];
      removed_devices?: string[];
      updated_devices?: WsDevice[];
    }
  | { type: 'visibility_update'; hidden?: string[]; blacklisted?: string[] }
  | {
      type: 'traffic_state';
      interfaces?: Record<string, Record<string, WsTrafficStats>>;
    }
  | { type: 'position_update'; device_id: string; position: { x: number; y: number } }
  | { type: 'device_map_change'; device_id: string; map: string }
  | { type: 'map_label_change'; map_name: string; label: string }
  | { type: 'config_refresh'; devices?: WsDevice[] }
  | { type: 'maps_changed'; maps?: WsMap[] };
