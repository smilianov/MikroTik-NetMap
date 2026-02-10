/**
 * Top status bar showing online/offline/degraded device counts.
 */

import { useNetworkStore } from '../stores/networkStore';

export function StatusBar() {
  const { devices, pingData, wsConnected } = useNetworkStore();

  let online = 0;
  let degraded = 0;
  let offline = 0;
  let unknown = 0;

  for (const dev of devices) {
    const ping = pingData[dev.id];
    if (!ping?.lastSeen) {
      unknown++;
      continue;
    }
    const elapsed = (Date.now() - new Date(ping.lastSeen).getTime()) / 1000;
    if (elapsed <= 5) online++;
    else if (elapsed <= 30) degraded++;
    else offline++;
  }

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: '24px',
      padding: '12px 24px',
      background: '#1F2937',
      borderBottom: '1px solid #374151',
      fontFamily: 'Inter, system-ui, sans-serif',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <span style={{ fontSize: '20px', fontWeight: 700, color: '#F9FAFB' }}>
          MikroTik NetMap
        </span>
        <span style={{
          fontSize: '11px',
          padding: '2px 8px',
          borderRadius: '4px',
          background: wsConnected ? '#065F46' : '#991B1B',
          color: wsConnected ? '#6EE7B7' : '#FCA5A5',
        }}>
          {wsConnected ? 'LIVE' : 'DISCONNECTED'}
        </span>
      </div>

      <div style={{ flex: 1 }} />

      <StatChip color="#22C55E" label="Online" count={online} />
      <StatChip color="#FFD700" label="Degraded" count={degraded} />
      <StatChip color="#EF4444" label="Offline" count={offline} />
      <StatChip color="#6B7280" label="Unknown" count={unknown} />

      <div style={{ color: '#9CA3AF', fontSize: '13px' }}>
        {devices.length} devices
      </div>
    </div>
  );
}

function StatChip({ color, label, count }: { color: string; label: string; count: number }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
      <div style={{
        width: '10px',
        height: '10px',
        borderRadius: '50%',
        background: color,
        boxShadow: count > 0 ? `0 0 6px ${color}` : 'none',
      }} />
      <span style={{ color: '#D1D5DB', fontSize: '13px' }}>
        {count} {label}
      </span>
    </div>
  );
}
