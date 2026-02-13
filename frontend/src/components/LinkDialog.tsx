/**
 * Dialog for creating a manual link between two devices.
 */

import { useState } from 'react';

interface LinkDialogProps {
  fromDevice: string;
  toDevice: string;
  onConfirm: (data: { fromIf: string; toIf: string; speed: number; type: string }) => void;
  onCancel: () => void;
}

export function LinkDialog({ fromDevice, toDevice, onConfirm, onCancel }: LinkDialogProps) {
  const [fromIf, setFromIf] = useState('');
  const [toIf, setToIf] = useState('');
  const [speed, setSpeed] = useState(1000);
  const [linkType, setLinkType] = useState('wired');

  const handleSubmit = () => {
    onConfirm({
      fromIf: fromIf || 'port',
      toIf: toIf || 'port',
      speed,
      type: linkType,
    });
  };

  const inputStyle: React.CSSProperties = {
    width: '100%',
    padding: '8px 12px',
    background: '#111827',
    border: '1px solid #374151',
    borderRadius: '6px',
    color: '#E5E7EB',
    fontSize: '13px',
    outline: 'none',
    boxSizing: 'border-box',
  };

  const labelStyle: React.CSSProperties = {
    fontSize: '11px',
    color: '#6B7280',
    textTransform: 'uppercase',
    marginBottom: '4px',
    display: 'block',
  };

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      zIndex: 2000,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'rgba(0,0,0,0.6)',
      fontFamily: 'Inter, system-ui, sans-serif',
    }} onClick={onCancel}>
      <div style={{
        background: '#1F2937',
        border: '1px solid #374151',
        borderRadius: '12px',
        padding: '24px',
        minWidth: '380px',
        maxWidth: '440px',
        boxShadow: '0 12px 40px rgba(0,0,0,0.6)',
      }} onClick={(e) => e.stopPropagation()}>
        <div style={{ fontSize: '16px', fontWeight: 700, color: '#F9FAFB', marginBottom: '16px' }}>
          Create Link
        </div>

        {/* From device */}
        <div style={{ marginBottom: '12px' }}>
          <label style={labelStyle}>From Device</label>
          <div style={{ fontSize: '14px', color: '#D1D5DB', fontWeight: 600, marginBottom: '6px' }}>
            {fromDevice}
          </div>
          <input
            type="text"
            placeholder="Interface (e.g. ether1, sfp-sfpplus1)"
            value={fromIf}
            onChange={(e) => setFromIf(e.target.value)}
            style={inputStyle}
          />
        </div>

        {/* To device */}
        <div style={{ marginBottom: '12px' }}>
          <label style={labelStyle}>To Device</label>
          <div style={{ fontSize: '14px', color: '#D1D5DB', fontWeight: 600, marginBottom: '6px' }}>
            {toDevice}
          </div>
          <input
            type="text"
            placeholder="Interface (e.g. ether1, sfp-sfpplus1)"
            value={toIf}
            onChange={(e) => setToIf(e.target.value)}
            style={inputStyle}
          />
        </div>

        {/* Speed + Type row */}
        <div style={{ display: 'flex', gap: '12px', marginBottom: '20px' }}>
          <div style={{ flex: 1 }}>
            <label style={labelStyle}>Speed (Mbps)</label>
            <input
              type="number"
              value={speed}
              onChange={(e) => setSpeed(parseInt(e.target.value) || 1000)}
              style={inputStyle}
            />
          </div>
          <div style={{ flex: 1 }}>
            <label style={labelStyle}>Type</label>
            <select
              value={linkType}
              onChange={(e) => setLinkType(e.target.value)}
              style={{ ...inputStyle, cursor: 'pointer' }}
            >
              <option value="wired">Wired</option>
              <option value="wireless">Wireless</option>
              <option value="vpn">VPN</option>
            </select>
          </div>
        </div>

        {/* Buttons */}
        <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
          <button
            onClick={onCancel}
            style={{
              padding: '8px 16px',
              background: '#374151',
              border: '1px solid #4B5563',
              borderRadius: '6px',
              color: '#D1D5DB',
              fontSize: '13px',
              cursor: 'pointer',
            }}
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            style={{
              padding: '8px 16px',
              background: '#1D4ED8',
              border: '1px solid #3B82F6',
              borderRadius: '6px',
              color: '#DBEAFE',
              fontSize: '13px',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Create Link
          </button>
        </div>
      </div>
    </div>
  );
}
