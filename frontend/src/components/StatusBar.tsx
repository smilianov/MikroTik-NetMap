/**
 * Top status bar showing online/offline/degraded device counts.
 */

import { useNetworkStore } from '../stores/networkStore';

export function StatusBar() {
  const { devices, pingData, thresholds } = useNetworkStore();

  let online = 0;
  let degraded = 0;
  let offline = 0;
  let unknown = 0;

  // Use the first and last configured thresholds for consistent status classification.
  const onlineMax = thresholds.length > 0 ? thresholds[0].maxSeconds : 35;
  const offlineMax = thresholds.length > 0 ? thresholds[thresholds.length - 1].maxSeconds : 345;

  for (const dev of devices) {
    const ping = pingData[dev.id];
    if (!ping?.lastSeen) {
      unknown++;
      continue;
    }
    const elapsed = (Date.now() - new Date(ping.lastSeen).getTime()) / 1000;
    if (elapsed <= onlineMax) online++;
    else if (elapsed <= offlineMax) degraded++;
    else offline++;
  }

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      padding: '12px 24px',
      background: '#1F2937',
      borderBottom: '1px solid #374151',
      fontFamily: 'Inter, system-ui, sans-serif',
      position: 'relative',
    }}>
      {/* Left: stats */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        <StatChip color="#22C55E" label="Online" count={online} />
        <StatChip color="#FFD700" label="Degraded" count={degraded} />
        <StatChip color="#EF4444" label="Offline" count={offline} />
        <StatChip color="#6B7280" label="Unknown" count={unknown} />
      </div>

      {/* Center: title */}
      <div style={{
        position: 'absolute',
        left: '50%',
        transform: 'translateX(-50%)',
        fontSize: '20px',
        fontWeight: 700,
        color: '#F9FAFB',
        whiteSpace: 'nowrap',
      }}>
        MikroTik NetMap by LS
      </div>

      {/* Right: device count */}
      <div style={{ flex: 1 }} />
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
