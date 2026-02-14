/**
 * Login page component.
 */

import { useState } from 'react';
import { useAuthStore } from '../stores/authStore';

export function LoginPage() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const { login, loginError, clearError } = useAuthStore();
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    clearError();
    setLoading(true);
    await login(username, password);
    setLoading(false);
  };

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      minHeight: '100vh',
      background: '#111827',
      fontFamily: 'Inter, system-ui, sans-serif',
    }}>
      <div style={{
        background: '#1F2937',
        borderRadius: '10px',
        padding: '32px',
        width: '340px',
        border: '1px solid #374151',
      }}>
        <h1 style={{
          fontSize: '1.3rem',
          color: '#F9FAFB',
          textAlign: 'center',
          marginBottom: '4px',
        }}>
          MikroTik NetMap
        </h1>
        <p style={{
          color: '#6B7280',
          fontSize: '0.8rem',
          textAlign: 'center',
          marginBottom: '24px',
        }}>
          Network Topology Dashboard
        </p>
        <form onSubmit={handleSubmit}>
          <label style={{ display: 'block', color: '#9CA3AF', fontSize: '0.8rem', marginBottom: '4px' }}>
            Username
          </label>
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            autoFocus
            style={{
              width: '100%',
              padding: '8px 10px',
              borderRadius: '6px',
              border: '1px solid #374151',
              background: '#111827',
              color: '#E5E7EB',
              fontSize: '0.9rem',
              marginBottom: '14px',
              outline: 'none',
              boxSizing: 'border-box',
            }}
          />
          <label style={{ display: 'block', color: '#9CA3AF', fontSize: '0.8rem', marginBottom: '4px' }}>
            Password
          </label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            style={{
              width: '100%',
              padding: '8px 10px',
              borderRadius: '6px',
              border: '1px solid #374151',
              background: '#111827',
              color: '#E5E7EB',
              fontSize: '0.9rem',
              marginBottom: '14px',
              outline: 'none',
              boxSizing: 'border-box',
            }}
          />
          <button
            type="submit"
            disabled={loading}
            style={{
              width: '100%',
              padding: '10px',
              border: 'none',
              borderRadius: '6px',
              background: '#22C55E',
              color: '#fff',
              fontSize: '0.95rem',
              cursor: loading ? 'wait' : 'pointer',
              fontWeight: 600,
              opacity: loading ? 0.7 : 1,
            }}
          >
            {loading ? 'Logging in...' : 'Log In'}
          </button>
        </form>
        {loginError && (
          <div style={{
            color: '#EF4444',
            fontSize: '0.8rem',
            textAlign: 'center',
            marginTop: '10px',
          }}>
            {loginError}
          </div>
        )}
      </div>
    </div>
  );
}
