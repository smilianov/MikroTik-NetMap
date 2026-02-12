/**
 * Error Boundary — catches rendering errors and shows a recovery UI
 * instead of a white screen.
 */

import { Component, type ReactNode, type ErrorInfo } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[ErrorBoundary] Rendering error:', error, info.componentStack);
  }

  handleReload = () => {
    window.location.reload();
  };

  handleDismiss = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100vh',
          background: '#111827',
          color: '#E5E7EB',
          fontFamily: 'Inter, system-ui, sans-serif',
          padding: '24px',
          textAlign: 'center',
        }}>
          <div style={{ fontSize: '48px', marginBottom: '16px' }}>!</div>
          <h1 style={{ fontSize: '20px', fontWeight: 700, marginBottom: '8px', color: '#F9FAFB' }}>
            Something went wrong
          </h1>
          <p style={{ fontSize: '14px', color: '#9CA3AF', marginBottom: '24px', maxWidth: '400px' }}>
            The dashboard encountered an unexpected error. You can try reloading the page or dismissing this message.
          </p>
          {this.state.error && (
            <pre style={{
              fontSize: '12px',
              color: '#EF4444',
              background: '#1F2937',
              padding: '12px',
              borderRadius: '6px',
              maxWidth: '600px',
              overflow: 'auto',
              marginBottom: '24px',
              textAlign: 'left',
            }}>
              {this.state.error.message}
            </pre>
          )}
          <div style={{ display: 'flex', gap: '12px' }}>
            <button
              onClick={this.handleReload}
              style={{
                padding: '10px 20px',
                background: '#2563EB',
                color: '#fff',
                border: 'none',
                borderRadius: '6px',
                fontSize: '14px',
                cursor: 'pointer',
              }}
            >
              Reload Page
            </button>
            <button
              onClick={this.handleDismiss}
              style={{
                padding: '10px 20px',
                background: '#374151',
                color: '#D1D5DB',
                border: '1px solid #4B5563',
                borderRadius: '6px',
                fontSize: '14px',
                cursor: 'pointer',
              }}
            >
              Dismiss
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
