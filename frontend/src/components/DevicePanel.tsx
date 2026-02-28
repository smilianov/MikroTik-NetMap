/**
 * Slide-in device detail panel (shown on double-click).
 */

import React, { useState } from 'react';
import { useNetworkStore } from '../stores/networkStore';
import { getPingColor } from '../utils/colorThresholds';
import { formatRtt, formatBandwidth } from '../utils/formatters';
import { hideDevice as apiHide, unhideDevice as apiUnhide, blacklistDevice as apiBlacklist, pinDevice as apiPin, unpinDevice as apiUnpin, moveDeviceToMap as apiMoveToMap } from '../api/visibility';

export function DevicePanel() {
  const { devices, pingData, trafficData, thresholds, selectedDevice, selectDevice, hiddenDevices, maps, currentMap } = useNetworkStore();
  const [confirmRemove, setConfirmRemove] = useState(false);

  if (!selectedDevice) return null;

  const device = devices.find((d) => d.id === selectedDevice);
  if (!device) return null;

  const ping = pingData[device.id];
  const color = getPingColor(ping?.lastSeen ?? null, thresholds);
  const elapsed = ping?.lastSeen
    ? (Date.now() - new Date(ping.lastSeen).getTime()) / 1000
    : null;
  const isHidden = hiddenDevices.has(device.id);
  const isPinned = device.pinned ?? false;

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
            elapsed <= 35 ? 'Online' :
            elapsed <= 345 ? `Down ${Math.round(elapsed)}s` :
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

      {/* Action buttons */}
      <div style={{ marginTop: '20px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <button
          onClick={async () => {
            if (isHidden) await apiUnhide(device.id);
            else await apiHide(device.id);
          }}
          style={actionBtnStyle}
        >
          {isHidden ? 'Unhide Device' : 'Hide Device'}
        </button>
        <button
          onClick={async () => {
            if (isPinned) await apiUnpin(device.id);
            else await apiPin(device.id);
          }}
          style={actionBtnStyle}
        >
          {isPinned ? 'Unpin from all maps' : 'Pin to all maps'}
        </button>
        {maps.length > 1 && (
          <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
            {maps.filter((m) => m.name !== currentMap).map((m) => (
              <button
                key={m.name}
                onClick={async () => {
                  await apiMoveToMap(device.id, m.name);
                }}
                style={{ ...actionBtnStyle, flex: '1 1 auto', fontSize: '12px' }}
              >
                Move to {m.label || m.name}
              </button>
            ))}
          </div>
        )}
        {!confirmRemove ? (
          <button
            onClick={() => setConfirmRemove(true)}
            style={{ ...actionBtnStyle, color: '#EF4444', borderColor: '#7F1D1D' }}
          >
            Remove Device
          </button>
        ) : (
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              onClick={async () => {
                await apiBlacklist(device.id);
                setConfirmRemove(false);
                selectDevice(null);
              }}
              style={{ ...actionBtnStyle, flex: 1, background: '#7F1D1D', color: '#FCA5A5', borderColor: '#EF4444' }}
            >
              Confirm Remove
            </button>
            <button
              onClick={() => setConfirmRemove(false)}
              style={{ ...actionBtnStyle, flex: 1 }}
            >
              Cancel
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

const actionBtnStyle: React.CSSProperties = {
  padding: '8px 12px',
  background: '#111827',
  border: '1px solid #374151',
  borderRadius: '6px',
  color: '#D1D5DB',
  fontSize: '13px',
  cursor: 'pointer',
  fontFamily: 'Inter, system-ui, sans-serif',
};

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
