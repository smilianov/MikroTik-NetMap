/**
 * Left sidebar with device list and search.
 */

import { useState } from 'react';
import { useNetworkStore } from '../stores/networkStore';
import { getPingColor } from '../utils/colorThresholds';
import { formatRtt } from '../utils/formatters';

export function Sidebar() {
  const { devices, pingData, thresholds, selectDevice, selectedDevice } = useNetworkStore();
  const [search, setSearch] = useState('');

  const filtered = devices.filter((d) =>
    d.name.toLowerCase().includes(search.toLowerCase()) ||
    d.host.includes(search)
  );

  // Sort: alive first, then by name.
  const sorted = [...filtered].sort((a, b) => {
    const aAlive = pingData[a.id]?.isAlive ? 0 : 1;
    const bAlive = pingData[b.id]?.isAlive ? 0 : 1;
    if (aAlive !== bAlive) return aAlive - bAlive;
    return a.name.localeCompare(b.name);
  });

  return (
    <div style={{
      width: '240px',
      background: '#1F2937',
      borderRight: '1px solid #374151',
      display: 'flex',
      flexDirection: 'column',
      fontFamily: 'Inter, system-ui, sans-serif',
    }}>
      {/* Search */}
      <div style={{ padding: '12px' }}>
        <input
          type="text"
          placeholder="Search devices..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{
            width: '100%',
            padding: '8px 12px',
            background: '#111827',
            border: '1px solid #374151',
            borderRadius: '6px',
            color: '#E5E7EB',
            fontSize: '13px',
            outline: 'none',
            boxSizing: 'border-box',
          }}
        />
      </div>

      {/* Device list */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {sorted.map((dev) => {
          const ping = pingData[dev.id];
          const color = getPingColor(ping?.lastSeen ?? null, thresholds);
          const isSelected = selectedDevice === dev.id;

          return (
            <div
              key={dev.id}
              onClick={() => selectDevice(dev.id)}
              style={{
                padding: '10px 12px',
                cursor: 'pointer',
                background: isSelected ? '#374151' : 'transparent',
                borderLeft: isSelected ? `3px solid ${color}` : '3px solid transparent',
                transition: 'background 0.15s',
              }}
              onMouseEnter={(e) => {
                if (!isSelected) (e.currentTarget.style.background = '#283040');
              }}
              onMouseLeave={(e) => {
                if (!isSelected) (e.currentTarget.style.background = 'transparent');
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <div style={{
                  width: '8px',
                  height: '8px',
                  borderRadius: '50%',
                  background: color,
                  flexShrink: 0,
                }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{
                    fontSize: '13px',
                    fontWeight: 600,
                    color: '#E5E7EB',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}>
                    {dev.name}
                  </div>
                  <div style={{
                    fontSize: '11px',
                    color: '#6B7280',
                    display: 'flex',
                    justifyContent: 'space-between',
                  }}>
                    <span>{dev.host}</span>
                    <span>{formatRtt(ping?.rttMs ?? null)}</span>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
