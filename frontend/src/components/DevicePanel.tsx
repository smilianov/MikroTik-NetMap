/**
 * Slide-in device detail panel (shown on double-click).
 */

import { useNetworkStore } from '../stores/networkStore';
import { getPingColor } from '../utils/colorThresholds';
import { formatRtt, formatBandwidth } from '../utils/formatters';

export function DevicePanel() {
  const { devices, pingData, trafficData, thresholds, selectedDevice, selectDevice } = useNetworkStore();

  if (!selectedDevice) return null;

  const device = devices.find((d) => d.id === selectedDevice);
  if (!device) return null;

  const ping = pingData[device.id];
  const color = getPingColor(ping?.lastSeen ?? null, thresholds);
  const elapsed = ping?.lastSeen
    ? (Date.now() - new Date(ping.lastSeen).getTime()) / 1000
    : null;

  return (
    <div style={{
      position: 'absolute',
      right: 0,
      top: 0,
      bottom: 0,
      width: '360px',
      background: '#1F2937',
      borderLeft: '1px solid #374151',
      padding: '20px',
      overflowY: 'auto',
      fontFamily: 'Inter, system-ui, sans-serif',
      zIndex: 100,
      boxShadow: '-4px 0 20px rgba(0,0,0,0.3)',
    }}>
      {/* Close button */}
      <button
        onClick={() => selectDevice(null)}
        style={{
          position: 'absolute',
          top: '12px',
          right: '12px',
          background: 'none',
          border: 'none',
          color: '#9CA3AF',
          fontSize: '20px',
          cursor: 'pointer',
        }}
      >
        ✕
      </button>

      {/* Device header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '20px' }}>
        <div style={{
          width: '16px',
          height: '16px',
          borderRadius: '50%',
          background: color,
          boxShadow: `0 0 10px ${color}`,
        }} />
        <div>
          <div style={{ fontSize: '18px', fontWeight: 700, color: '#F9FAFB' }}>
            {device.name}
          </div>
          <div style={{ fontSize: '13px', color: '#9CA3AF' }}>
            {device.host}
          </div>
        </div>
      </div>

      {/* Info grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 1fr',
        gap: '12px',
        marginBottom: '20px',
      }}>
        <InfoCard label="Type" value={device.type} />
        <InfoCard label="Profile" value={device.profile} />
        <InfoCard label="RTT" value={formatRtt(ping?.rttMs ?? null)} />
        <InfoCard
          label="Status"
          value={
            elapsed === null ? 'Unknown' :
            elapsed <= 5 ? 'Online' :
            elapsed <= 180 ? `Down ${Math.round(elapsed)}s` :
            'Down'
          }
          valueColor={color}
        />
      </div>

      {/* Ping history placeholder */}
      <div style={{
        padding: '16px',
        background: '#111827',
        borderRadius: '8px',
        marginBottom: '12px',
      }}>
        <div style={{ fontSize: '12px', color: '#6B7280', marginBottom: '8px', textTransform: 'uppercase' }}>
          Last Seen
        </div>
        <div style={{ fontSize: '14px', color: '#D1D5DB' }}>
          {ping?.lastSeen ? new Date(ping.lastSeen).toLocaleString() : 'Never'}
        </div>
      </div>

      {/* Interface Traffic */}
      {(() => {
        const deviceTraffic = trafficData[device.id];
        if (!deviceTraffic || Object.keys(deviceTraffic).length === 0) {
          return (
            <div style={{
              padding: '16px',
              background: '#111827',
              borderRadius: '8px',
              fontSize: '13px',
              color: '#6B7280',
              textAlign: 'center',
            }}>
              No traffic data available.
              <br />
              Device may not have API credentials configured.
            </div>
          );
        }

        return (
          <div>
            <div style={{
              fontSize: '12px',
              color: '#6B7280',
              textTransform: 'uppercase',
              marginBottom: '8px',
            }}>
              Interface Traffic
            </div>
            {Object.entries(deviceTraffic)
              .filter(([, stats]) => stats.rxBps > 0 || stats.txBps > 0)
              .sort(([a], [b]) => a.localeCompare(b))
              .map(([ifName, stats]) => (
                <div
                  key={ifName}
                  style={{
                    padding: '10px 12px',
                    background: '#111827',
                    borderRadius: '6px',
                    marginBottom: '6px',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                  }}
                >
                  <div style={{ fontSize: '13px', color: '#D1D5DB', fontWeight: 600 }}>
                    {ifName}
                  </div>
                  <div style={{ textAlign: 'right', fontSize: '12px' }}>
                    <div style={{ color: '#22C55E' }}>
                      RX: {formatBandwidth(stats.rxBps)}
                    </div>
                    <div style={{ color: '#60A5FA' }}>
                      TX: {formatBandwidth(stats.txBps)}
                    </div>
                  </div>
                </div>
              ))}
          </div>
        );
      })()}
    </div>
  );
}

function InfoCard({
  label,
  value,
  valueColor,
}: {
  label: string;
  value: string;
  valueColor?: string;
}) {
  return (
    <div style={{
      padding: '12px',
      background: '#111827',
      borderRadius: '8px',
    }}>
      <div style={{ fontSize: '11px', color: '#6B7280', textTransform: 'uppercase', marginBottom: '4px' }}>
        {label}
      </div>
      <div style={{ fontSize: '15px', fontWeight: 600, color: valueColor || '#E5E7EB' }}>
        {value}
      </div>
    </div>
  );
}
