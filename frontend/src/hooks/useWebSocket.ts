/**
 * WebSocket hook with auto-reconnect.
 * Connects to the backend and dispatches state updates to the store.
 */

import { useEffect, useRef } from 'react';
import { useNetworkStore, type DeviceInfo, type LinkInfo, type MapInfo } from '../stores/networkStore';
import { useAuthStore } from '../stores/authStore';
import type { ServerMessage, WsDevice, WsLink, WsMap } from '../types/ws';

const WS_URL = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws`;
const RECONNECT_DELAY = 3000;

/** Module-level send function — set when WebSocket is open. */
let _wsSendFn: ((data: string) => void) | null = null;

/** Send a JSON message to the backend via WebSocket. */
export function sendWsMessage(msg: object): void {
  if (_wsSendFn) {
    _wsSendFn(JSON.stringify(msg));
  }
}

/** Map a wire device to the store shape. */
function toDeviceInfo(d: WsDevice): DeviceInfo {
  return {
    id: d.id,
    name: d.name,
    host: d.host,
    type: d.type,
    profile: d.profile || 'edge',
    map: d.map || 'main',
    position: d.position || { x: 0, y: 0 },
    parent: d.parent ?? undefined,
    discovered: d.discovered ?? false,
    pinned: d.pinned ?? false,
  };
}

/** Map a wire link to the store shape. */
function toLinkInfo(l: WsLink): LinkInfo {
  return {
    id: l.id,
    from: l.from,
    to: l.to,
    speed: l.speed,
    type: l.type,
    confirmed: l.confirmed,
    manual: l.manual,
    discovered: l.discovered,
    map: l.map,
  };
}

/** Map a wire map entry to the store shape. */
function toMapInfo(m: WsMap): MapInfo {
  return {
    name: m.name,
    label: m.label || m.name,
    parent: m.parent || null,
    background: m.background || null,
  };
}

/** Dispatch a server message to the store (read imperatively — no subscription). */
function handleMessage(msg: ServerMessage) {
  const store = useNetworkStore.getState();
  switch (msg.type) {
    case 'config':
      store.setConfig(
        (msg.devices || []).map(toDeviceInfo),
        (msg.links || []).map(toLinkInfo),
        (msg.thresholds || []).map((t) => ({
          maxSeconds: t.max_seconds,
          color: t.color,
          label: t.label,
        })),
        (msg.maps || []).map(toMapInfo),
      );
      store.setVisibility(msg.hidden || [], msg.blacklisted || []);
      break;

    case 'ping_state':
      store.updatePingState(
        (msg.devices || []).map((d) => ({
          id: d.id,
          lastSeen: d.last_seen,
          rttMs: d.rtt_ms,
          isAlive: d.is_alive,
        })),
      );
      break;

    case 'topology_update':
      store.mergeTopology(
        (msg.added_devices || []).map(toDeviceInfo),
        (msg.added_links || []).map(toLinkInfo),
        msg.removed_links || [],
        msg.removed_devices || [],
        (msg.updated_devices || []).map(toDeviceInfo),
      );
      break;

    case 'visibility_update':
      store.setVisibility(msg.hidden || [], msg.blacklisted || []);
      break;

    case 'traffic_state':
      store.updateTraffic(
        Object.fromEntries(
          Object.entries(msg.interfaces || {}).map(([deviceId, ifaces]) => [
            deviceId,
            Object.fromEntries(
              Object.entries(ifaces).map(([ifName, stats]) => [
                ifName,
                { rxBps: stats.rx_bps, txBps: stats.tx_bps },
              ]),
            ),
          ]),
        ),
      );
      break;

    case 'position_update':
      store.updateDevicePosition(msg.device_id, msg.position);
      break;

    case 'device_map_change':
      store.updateDeviceMap(msg.device_id, msg.map);
      break;

    case 'map_label_change':
      store.updateMapLabel(msg.map_name, msg.label);
      break;

    case 'config_refresh':
      // Server sent updated device list (e.g. after pin/unpin).
      useNetworkStore.setState({
        devices: (msg.devices || []).map(toDeviceInfo),
      });
      break;

    case 'maps_changed':
      store.setMaps((msg.maps || []).map(toMapInfo));
      break;
  }
}

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<number | null>(null);

  useEffect(() => {
    function connect() {
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('[WS] Connected');
        useNetworkStore.getState().setWsConnected(true);
        _wsSendFn = (data) => ws.send(data);
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data) as ServerMessage;
          handleMessage(msg);
        } catch (err) {
          console.error('[WS] Parse error:', err);
        }
      };

      ws.onclose = (event) => {
        useNetworkStore.getState().setWsConnected(false);
        _wsSendFn = null;
        if (event.code === 4401) {
          console.log('[WS] Auth rejected (4401), redirecting to login');
          useAuthStore.getState().logout();
          return;
        }
        console.log('[WS] Disconnected, reconnecting...');
        scheduleReconnect();
      };

      ws.onerror = (err) => {
        console.error('[WS] Error:', err);
        ws.close();
      };
    }

    function scheduleReconnect() {
      if (reconnectTimer.current) return;
      reconnectTimer.current = window.setTimeout(() => {
        reconnectTimer.current = null;
        connect();
      }, RECONNECT_DELAY);
    }

    connect();

    return () => {
      if (reconnectTimer.current) {
        clearTimeout(reconnectTimer.current);
      }
      _wsSendFn = null;
      wsRef.current?.close();
    };
  }, []);
}
