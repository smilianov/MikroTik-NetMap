import { useEffect } from 'react';
import { useAuthStore } from './stores/authStore';
import { useWebSocket } from './hooks/useWebSocket';
import { NetworkMap } from './components/NetworkMap';
import { StatusBar } from './components/StatusBar';
import { Sidebar } from './components/Sidebar';
import { DevicePanel } from './components/DevicePanel';
import { LoginPage } from './components/LoginPage';
import { useNetworkStore } from './stores/networkStore';

function App() {
  const { initialized, authenticated, authEnabled, checkAuth } = useAuthStore();

  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  if (!initialized) {
    return (
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100vh',
        background: '#111827',
        color: '#6B7280',
        fontFamily: 'Inter, system-ui, sans-serif',
      }}>
        Loading...
      </div>
    );
  }

  if (authEnabled && !authenticated) {
    return <LoginPage />;
  }

  return <Dashboard />;
}

function Dashboard() {
  useWebSocket();
  const sidebarVisible = useNetworkStore((s) => s.sidebarVisible);

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100vh',
      background: '#111827',
      color: '#E5E7EB',
    }}>
      <StatusBar />
      <div style={{ display: 'flex', flex: 1, position: 'relative', overflow: 'hidden' }}>
        {sidebarVisible && <Sidebar />}
        <div style={{ flex: 1, position: 'relative' }}>
          <NetworkMap />
          <DevicePanel />
        </div>
      </div>
    </div>
  );
}

export default App;
