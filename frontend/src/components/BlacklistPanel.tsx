/**
 * Blacklist management panel — shows blacklisted devices with unblacklist option.
 */

import { useEffect, useState } from 'react';
import { getBlacklisted, unblacklistDevice, type BlacklistedEntry } from '../api/visibility';

interface BlacklistPanelProps {
  onClose: () => void;
}

export function BlacklistPanel({ onClose }: BlacklistPanelProps) {
  const [entries, setEntries] = useState<BlacklistedEntry[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchList = async () => {
    try {
      const data = await getBlacklisted();
      setEntries(data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchList();
  }, []);

  const handleUnblacklist = async (id: string) => {
    await unblacklistDevice(id);
    setEntries((prev) => prev.filter((e) => e.id !== id));
  };

  return (
    <div style={{
      position: 'fixed',
      top: 0,
      right: 0,
      bottom: 0,
      width: '360px',
      background: '#1F2937',
      borderLeft: '1px solid #374151',
      zIndex: 1500,
      display: 'flex',
      flexDirection: 'column',
      fontFamily: 'Inter, system-ui, sans-serif',
      boxShadow: '-8px 0 24px rgba(0,0,0,0.4)',
    }}>
      {/* Header */}
      <div style={{
        padding: '16px 20px',
        borderBottom: '1px solid #374151',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
      }}>
        <div style={{ fontSize: '15px', fontWeight: 700, color: '#F9FAFB' }}>
          Blacklisted Devices
        </div>
        <button
          onClick={onClose}
          style={{
            background: 'none',
            border: 'none',
            color: '#6B7280',
            fontSize: '20px',
            cursor: 'pointer',
            padding: '0 4px',
          }}
        >
          &times;
        </button>
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 16px' }}>
        {loading ? (
          <div style={{ color: '#6B7280', fontSize: '13px', padding: '20px 0', textAlign: 'center' }}>
            Loading...
          </div>
        ) : entries.length === 0 ? (
          <div style={{ color: '#6B7280', fontSize: '13px', padding: '20px 0', textAlign: 'center' }}>
            No blacklisted devices
          </div>
        ) : (
          entries.map((entry) => (
            <div key={entry.id} style={{
              padding: '12px',
              background: '#111827',
              borderRadius: '8px',
              marginBottom: '8px',
              border: '1px solid #374151',
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                  <div style={{ fontSize: '13px', fontWeight: 600, color: '#E5E7EB' }}>
                    {entry.id}
                  </div>
                  {entry.host && (
                    <div style={{ fontSize: '11px', color: '#6B7280', marginTop: '2px' }}>
                      {entry.host}
                      {entry.mac ? ` (${entry.mac})` : ''}
                    </div>
                  )}
                  {entry.reason && (
                    <div style={{ fontSize: '11px', color: '#9CA3AF', marginTop: '4px', fontStyle: 'italic' }}>
                      {entry.reason}
                    </div>
                  )}
                  <div style={{ fontSize: '10px', color: '#4B5563', marginTop: '4px' }}>
                    {new Date(entry.blacklisted_at).toLocaleString()}
                  </div>
                </div>
                <button
                  onClick={() => handleUnblacklist(entry.id)}
                  style={{
                    padding: '4px 10px',
                    background: '#065F46',
                    border: '1px solid #059669',
                    borderRadius: '4px',
                    color: '#6EE7B7',
                    fontSize: '11px',
                    cursor: 'pointer',
                    whiteSpace: 'nowrap',
                  }}
                >
                  Restore
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
