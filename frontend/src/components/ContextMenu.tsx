/**
 * Right-click context menu for device nodes on the map.
 */

import { useEffect, useRef } from 'react';
import { useNetworkStore } from '../stores/networkStore';
import { hideDevice as apiHide, unhideDevice as apiUnhide } from '../api/visibility';

interface ContextMenuProps {
  x: number;
  y: number;
  deviceId: string;
  onClose: () => void;
  onBlacklist: (deviceId: string) => void;
  onMoveToMap?: (deviceId: string, mapName: string) => void;
}

export function ContextMenu({ x, y, deviceId, onClose, onBlacklist, onMoveToMap }: ContextMenuProps) {
  const ref = useRef<HTMLDivElement>(null);
  const { hiddenDevices, maps, currentMap } = useNetworkStore();
  const isHidden = hiddenDevices.has(deviceId);

  // Close on click outside or Escape.
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        onClose();
      }
    }
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    document.addEventListener('mousedown', handleClick);
    document.addEventListener('keydown', handleKey);
    return () => {
      document.removeEventListener('mousedown', handleClick);
      document.removeEventListener('keydown', handleKey);
    };
  }, [onClose]);

  const handleHide = async () => {
    if (isHidden) {
      await apiUnhide(deviceId);
    } else {
      await apiHide(deviceId);
    }
    onClose();
  };

  const handleBlacklist = () => {
    onBlacklist(deviceId);
    onClose();
  };

  const menuStyle: React.CSSProperties = {
    position: 'fixed',
    top: y,
    left: x,
    zIndex: 1000,
    background: '#1F2937',
    border: '1px solid #374151',
    borderRadius: '8px',
    padding: '4px 0',
    minWidth: '160px',
    boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
    fontFamily: 'Inter, system-ui, sans-serif',
  };

  const itemStyle: React.CSSProperties = {
    padding: '8px 16px',
    cursor: 'pointer',
    fontSize: '13px',
    color: '#E5E7EB',
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  };

  return (
    <div ref={ref} style={menuStyle}>
      <div style={{ padding: '6px 16px', fontSize: '11px', color: '#6B7280', fontWeight: 600, borderBottom: '1px solid #374151', marginBottom: '4px' }}>
        {deviceId}
      </div>
      <div
        style={itemStyle}
        onMouseEnter={(e) => (e.currentTarget.style.background = '#283040')}
        onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
        onClick={handleHide}
      >
        <span>{isHidden ? '\u{1F441}' : '\u{1F648}'}</span>
        <span>{isHidden ? 'Unhide Device' : 'Hide Device'}</span>
      </div>
      {maps.length > 1 && onMoveToMap && (
        <>
          <div style={{ height: '1px', background: '#374151', margin: '4px 0' }} />
          <div style={{ padding: '6px 16px', fontSize: '11px', color: '#6B7280', fontWeight: 600 }}>
            Move to map
          </div>
          {maps
            .filter((m) => m.name !== currentMap)
            .map((m) => (
              <div
                key={m.name}
                style={itemStyle}
                onMouseEnter={(e) => (e.currentTarget.style.background = '#283040')}
                onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                onClick={() => onMoveToMap(deviceId, m.name)}
              >
                <span>{'\u{27A1}'}</span>
                <span>{m.label || m.name}</span>
              </div>
            ))}
        </>
      )}
      <div style={{ height: '1px', background: '#374151', margin: '4px 0' }} />
      <div
        style={{ ...itemStyle, color: '#EF4444' }}
        onMouseEnter={(e) => (e.currentTarget.style.background = '#283040')}
        onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
        onClick={handleBlacklist}
      >
        <span>{'\u{1F5D1}'}</span>
        <span>Remove Device</span>
      </div>
    </div>
  );
}
