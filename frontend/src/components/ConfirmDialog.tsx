/**
 * Confirmation dialog for destructive actions (blacklist/remove).
 */

interface ConfirmDialogProps {
  title: string;
  message: string;
  confirmLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({ title, message, confirmLabel = 'Remove', onConfirm, onCancel }: ConfirmDialogProps) {
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
        minWidth: '320px',
        maxWidth: '400px',
        boxShadow: '0 12px 40px rgba(0,0,0,0.6)',
      }} onClick={(e) => e.stopPropagation()}>
        <div style={{ fontSize: '16px', fontWeight: 700, color: '#F9FAFB', marginBottom: '12px' }}>
          {title}
        </div>
        <div style={{ fontSize: '13px', color: '#9CA3AF', lineHeight: 1.5, marginBottom: '20px' }}>
          {message}
        </div>
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
            onClick={onConfirm}
            style={{
              padding: '8px 16px',
              background: '#991B1B',
              border: '1px solid #EF4444',
              borderRadius: '6px',
              color: '#FCA5A5',
              fontSize: '13px',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
