/**
 * WebSocket hook with auto-reconnect.
 * Connects to the backend and dispatches state updates to the store.
 */

import { useEffect, useRef } from 'react';
import { useNetworkStore } from '../stores/networkStore';

const WS_URL = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws`;
const RECONNECT_DELAY = 3000;

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<number | null>(null);
  const { setConfig, updatePingState, setWsConnected } = useNetworkStore();

  useEffect(() => {
    function connect() {
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('[WS] Connected');
        setWsConnected(true);
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
            })),
            (msg.thresholds || []).map((t: any) => ({
              maxSeconds: t.max_seconds,
              color: t.color,
              label: t.label,
            })),
          );
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
      wsRef.current?.close();
    };
  }, [setConfig, updatePingState, setWsConnected]);
}
