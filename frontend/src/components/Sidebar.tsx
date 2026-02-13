/**
 * Left sidebar with device list, search, visibility toggles, and blacklist access.
 */

import { useState } from 'react';
import { useNetworkStore } from '../stores/networkStore';
import { getPingColor } from '../utils/colorThresholds';
import { formatRtt } from '../utils/formatters';
import { hideDevice, unhideDevice } from '../api/visibility';
import { BlacklistPanel } from './BlacklistPanel';

export function Sidebar() {
  const { devices, pingData, thresholds, hiddenDevices, selectDevice, selectedDevice } = useNetworkStore();
  const [search, setSearch] = useState('');
  const [showHidden, setShowHidden] = useState(false);
  const [showBlacklist, setShowBlacklist] = useState(false);

  const hiddenCount = devices.filter((d) => hiddenDevices.has(d.id)).length;

  const filtered = devices.filter((d) => {
    const matchesSearch = d.name.toLowerCase().includes(search.toLowerCase()) || d.host.includes(search);
    if (!matchesSearch) return false;
    if (hiddenDevices.has(d.id) && !showHidden) return false;
    return true;
  });

  // Sort: hidden to bottom, then alive first, then by name.
  const sorted = [...filtered].sort((a, b) => {
    const aHidden = hiddenDevices.has(a.id) ? 1 : 0;
    const bHidden = hiddenDevices.has(b.id) ? 1 : 0;
    if (aHidden !== bHidden) return aHidden - bHidden;
    const aAlive = pingData[a.id]?.isAlive ? 0 : 1;
    const bAlive = pingData[b.id]?.isAlive ? 0 : 1;
    if (aAlive !== bAlive) return aAlive - bAlive;
    return a.name.localeCompare(b.name);
  });

  const handleToggleVisibility = async (e: React.MouseEvent, deviceId: string) => {
    e.stopPropagation();
    if (hiddenDevices.has(deviceId)) {
      await unhideDevice(deviceId);
    } else {
      await hideDevice(deviceId);
    }
  };

  return (
    <>
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

        {/* Show hidden toggle */}
        {hiddenCount > 0 && (
          <div style={{ padding: '0 12px 8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <button
              onClick={() => setShowHidden(!showHidden)}
              style={{
                background: showHidden ? '#374151' : 'transparent',
                border: '1px solid #374151',
                borderRadius: '4px',
                color: showHidden ? '#E5E7EB' : '#6B7280',
                fontSize: '11px',
                padding: '3px 8px',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
              }}
            >
              {showHidden ? '\u{1F441}' : '\u{1F648}'}
              <span>{hiddenCount} hidden</span>
            </button>
          </div>
        )}

        {/* Device list */}
        <div style={{ flex: 1, overflowY: 'auto' }}>
          {sorted.map((dev) => {
            const ping = pingData[dev.id];
            const color = getPingColor(ping?.lastSeen ?? null, thresholds);
            const isSelected = selectedDevice === dev.id;
            const isHidden = hiddenDevices.has(dev.id);

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
                  opacity: isHidden ? 0.45 : 1,
                  position: 'relative',
                }}
                onMouseEnter={(e) => {
                  if (!isSelected) (e.currentTarget.style.background = '#283040');
                  const eyeBtn = e.currentTarget.querySelector('[data-eye]') as HTMLElement;
                  if (eyeBtn) eyeBtn.style.opacity = '1';
                }}
                onMouseLeave={(e) => {
                  if (!isSelected) (e.currentTarget.style.background = 'transparent');
                  const eyeBtn = e.currentTarget.querySelector('[data-eye]') as HTMLElement;
                  if (eyeBtn && !isHidden) eyeBtn.style.opacity = '0';
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
                      textDecoration: isHidden ? 'line-through' : 'none',
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
                  {/* Eye toggle button */}
                  <div
                    data-eye
                    onClick={(e) => handleToggleVisibility(e, dev.id)}
                    style={{
                      opacity: isHidden ? 1 : 0,
                      transition: 'opacity 0.15s',
                      cursor: 'pointer',
                      fontSize: '14px',
                      flexShrink: 0,
                      padding: '2px',
                    }}
                    title={isHidden ? 'Unhide device' : 'Hide device'}
                  >
                    {isHidden ? '\u{1F648}' : '\u{1F441}'}
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Bottom: Blacklist manager button */}
        <div style={{
          padding: '12px',
          borderTop: '1px solid #374151',
        }}>
          <button
            onClick={() => setShowBlacklist(true)}
            style={{
              width: '100%',
              padding: '8px 12px',
              background: '#111827',
              border: '1px solid #374151',
              borderRadius: '6px',
              color: '#9CA3AF',
              fontSize: '12px',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '6px',
            }}
          >
            {'\u{1F5D1}'} Manage Blacklist
          </button>
        </div>
      </div>

      {/* Blacklist panel overlay */}
      {showBlacklist && <BlacklistPanel onClose={() => setShowBlacklist(false)} />}
    </>
  );
}
