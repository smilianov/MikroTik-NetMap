/**
 * WebSocket hook with auto-reconnect.
 * Connects to the backend and dispatches state updates to the store.
 */

import { useEffect, useRef } from 'react';
import { useNetworkStore } from '../stores/networkStore';

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

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<number | null>(null);
  const {
    setConfig,
    updatePingState,
    updateTraffic,
    updateDevicePosition,
    mergeTopology,
    setVisibility,
    updateDeviceMap,
    updateMapLabel,
    setMaps,
    setWsConnected,
  } = useNetworkStore();

  useEffect(() => {
    function connect() {
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('[WS] Connected');
        setWsConnected(true);
        _wsSendFn = (data) => ws.send(data);
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          handleMessage(msg);
        } catch (err) {
          console.error('[WS] Parse error:', err);
        }
      };

      ws.onclose = () => {
        console.log('[WS] Disconnected, reconnecting...');
        setWsConnected(false);
        _wsSendFn = null;
        scheduleReconnect();
      };

      ws.onerror = (err) => {
        console.error('[WS] Error:', err);
        ws.close();
      };
    }

    function handleMessage(msg: any) {
      switch (msg.type) {
        case 'config':
          setConfig(
            (msg.devices || []).map((d: any) => ({
              id: d.id,
              name: d.name,
              host: d.host,
              type: d.type,
              profile: d.profile,
              map: d.map,
              position: d.position || { x: 0, y: 0 },
            })),
            (msg.links || []).map((l: any) => ({
              from: l.from,
              to: l.to,
              speed: l.speed,
              type: l.type,
              confirmed: l.confirmed,
              manual: l.manual,
            })),
            (msg.thresholds || []).map((t: any) => ({
              maxSeconds: t.max_seconds,
              color: t.color,
              label: t.label,
            })),
            (msg.maps || []).map((m: any) => ({
              name: m.name,
              label: m.label || m.name,
              parent: m.parent || null,
              background: m.background || null,
            })),
          );
          setVisibility(msg.hidden || [], msg.blacklisted || []);
          break;

        case 'ping_state':
          updatePingState(
            (msg.devices || []).map((d: any) => ({
              id: d.id,
              lastSeen: d.last_seen,
              rttMs: d.rtt_ms,
              isAlive: d.is_alive,
            })),
          );
          break;

        case 'topology_update':
          mergeTopology(
            (msg.added_devices || []).map((d: any) => ({
              id: d.id,
              name: d.name,
              host: d.host,
              type: d.type,
              profile: d.profile || 'edge',
              map: d.map || 'main',
              position: d.position || { x: 0, y: 0 },
            })),
            (msg.added_links || []).map((l: any) => ({
              from: l.from,
              to: l.to,
              speed: l.speed,
              type: l.type,
              confirmed: l.confirmed,
              manual: l.manual,
            })),
            msg.removed_links || [],
            msg.removed_devices || [],
          );
          break;

        case 'visibility_update':
          setVisibility(msg.hidden || [], msg.blacklisted || []);
          break;

        case 'traffic_state':
          updateTraffic(
            Object.fromEntries(
              Object.entries(msg.interfaces || {}).map(
                ([deviceId, ifaces]: [string, any]) => [
                  deviceId,
                  Object.fromEntries(
                    Object.entries(ifaces).map(([ifName, stats]: [string, any]) => [
                      ifName,
                      { rxBps: stats.rx_bps, txBps: stats.tx_bps },
                    ]),
                  ),
                ],
              ),
            ),
          );
          break;

        case 'position_update':
          updateDevicePosition(msg.device_id, msg.position);
          break;

        case 'device_map_change':
          updateDeviceMap(msg.device_id, msg.map);
          break;

        case 'map_label_change':
          updateMapLabel(msg.map_name, msg.label);
          break;

        case 'maps_changed':
          setMaps((msg.maps || []).map((m: any) => ({
            name: m.name,
            label: m.label || m.name,
            parent: m.parent || null,
            background: m.background || null,
          })));
          break;
      }
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
  }, [setConfig, updatePingState, updateTraffic, updateDevicePosition, mergeTopology, setVisibility, updateDeviceMap, updateMapLabel, setMaps, setWsConnected]);
}
