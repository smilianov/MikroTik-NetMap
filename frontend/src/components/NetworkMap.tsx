/**
 * Main network topology map using vis-network.
 * Renders devices as image nodes with status-indicator dots,
 * links as edges with traffic-coloured lines and animated particles,
 * and supports drag-to-reposition with persistence.
 */

import { useEffect, useRef, useCallback, useState } from 'react';
import { Network, DataSet } from 'vis-network/standalone';
import { useNetworkStore } from '../stores/networkStore';
import { getPingColor, getTrafficColor } from '../utils/colorThresholds';
import { getDeviceImageUrl, preloadDeviceImages } from '../utils/deviceIcons';
import { sendWsMessage } from '../hooks/useWebSocket';
import { formatBandwidth } from '../utils/formatters';
import { ContextMenu } from './ContextMenu';
import { ConfirmDialog } from './ConfirmDialog';
import { LinkDialog } from './LinkDialog';
import { blacklistDevice as apiBlacklist } from '../api/visibility';
import { createLink as apiCreateLink, deleteLink as apiDeleteLink } from '../api/links';

/** Link dash pattern per link type. */
const LINK_DASHES: Record<string, boolean | number[]> = {
  wired: false,
  wireless: [10, 10],
  vpn: [4, 4],
};

/** Link width based on speed (Mbps). */
function linkWidth(speed: number): number {
  if (speed >= 25000) return 6;
  if (speed >= 10000) return 4;
  if (speed >= 1000) return 2.5;
  return 1.5;
}

/** Particle state for traffic animation on a single edge. */
interface Particle {
  t: number; // 0..1 position along edge
  speed: number; // t units per second
}

export function NetworkMap() {
  const containerRef = useRef<HTMLDivElement>(null);
  const networkRef = useRef<Network | null>(null);
  const nodesRef = useRef<DataSet<any>>(new DataSet());
  const edgesRef = useRef<DataSet<any>>(new DataSet());
  const animFrameRef = useRef<number>(0);

  // Particle animation state.
  const particlesRef = useRef<Map<string, Particle[]>>(new Map());
  const lastFrameTimeRef = useRef<number>(performance.now());

  // Drag lock state: locked by default (nodes can't be dragged).
  const [dragUnlocked, setDragUnlocked] = useState(false);
  const dragUnlockedRef = useRef(false);

  // Pause entire animation loop while dragging for smooth performance.
  const isDraggingRef = useRef(false);

  // Cache last computed node/edge state to avoid redundant DataSet updates.
  const lastNodeLabelsRef = useRef<Map<string, string>>(new Map());
  const lastNodeImagesRef = useRef<Map<string, string>>(new Map());
  const lastEdgeColorsRef = useRef<Map<string, string>>(new Map());

  // Refs for data accessed inside afterDrawing callback (registered once).
  const linksRef = useRef(useNetworkStore.getState().links);
  const trafficDataRef = useRef(useNetworkStore.getState().trafficData);

  const { devices, links, pingData, trafficData, thresholds, hiddenDevices, selectDevice, sidebarVisible, toggleSidebar, wsConnected } =
    useNetworkStore();

  // Context menu state.
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; deviceId: string } | null>(null);
  // Confirm dialog state (for blacklist).
  const [confirmTarget, setConfirmTarget] = useState<string | null>(null);
  // Link creation mode.
  const [linkMode, setLinkMode] = useState(false);
  const [linkFirstDevice, setLinkFirstDevice] = useState<string | null>(null);
  const [linkDialog, setLinkDialog] = useState<{ from: string; to: string } | null>(null);
  const linkModeRef = useRef(false);
  const linkFirstDeviceRef = useRef<string | null>(null);
  // Edge context menu state (for right-click on edges).
  const [edgeContextMenu, setEdgeContextMenu] = useState<{ x: number; y: number; edgeId: string; isManual: boolean } | null>(null);

  // Keep refs in sync.
  useEffect(() => {
    linksRef.current = links;
  }, [links]);
  useEffect(() => {
    trafficDataRef.current = trafficData;
  }, [trafficData]);
  useEffect(() => {
    linkModeRef.current = linkMode;
    linkFirstDeviceRef.current = linkFirstDevice;
  }, [linkMode, linkFirstDevice]);

  // Escape key → cancel link mode or close edge context menu.
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (linkMode) {
          setLinkMode(false);
          setLinkFirstDevice(null);
        }
        setEdgeContextMenu(null);
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [linkMode]);

  // Pre-warm image cache with all threshold colors.
  useEffect(() => {
    const colors = thresholds.map((t) => t.color);
    colors.push('#6B7280'); // unknown/grey
    preloadDeviceImages(colors);
  }, [thresholds]);

  // Initialize vis-network on mount.
  useEffect(() => {
    if (!containerRef.current) return;

    const options = {
      physics: {
        enabled: false, // Use fixed positions from config
      },
      interaction: {
        hover: true,
        tooltipDelay: 200,
        zoomView: true,
        dragView: true,
        dragNodes: false, // Toggled via lock/unlock button
      },
      nodes: {
        font: {
          size: 13,
          face: 'Inter, system-ui, sans-serif',
          color: '#E5E7EB',
          multi: 'html',
        },
        borderWidth: 0,
        shapeProperties: {
          useBorderWithImage: false,
          useImageSize: false,
        },
        shadow: {
          enabled: true,
          color: 'rgba(0,0,0,0.4)',
          size: 8,
          x: 2,
          y: 2,
        },
      },
      edges: {
        color: { color: '#4B5563', hover: '#9CA3AF', highlight: '#60A5FA' },
        smooth: { enabled: true, type: 'continuous', roundness: 0.2 },
        font: {
          size: 11,
          color: '#9CA3AF',
          strokeWidth: 3,
          strokeColor: '#1F2937',
          align: 'top',
        },
      },
    };

    const network = new Network(
      containerRef.current,
      { nodes: nodesRef.current, edges: edgesRef.current },
      options,
    );

    // Double-click → select device for detail panel.
    network.on('doubleClick', (params) => {
      if (params.nodes.length > 0) {
        selectDevice(params.nodes[0]);
      }
    });

    // Single click → deselect or handle link mode.
    network.on('click', (params) => {
      setEdgeContextMenu(null);
      if (linkModeRef.current && params.nodes.length > 0) {
        const nodeId = params.nodes[0] as string;
        if (!linkFirstDeviceRef.current) {
          setLinkFirstDevice(nodeId);
        } else if (nodeId !== linkFirstDeviceRef.current) {
          setLinkDialog({ from: linkFirstDeviceRef.current, to: nodeId });
          setLinkFirstDevice(null);
          setLinkMode(false);
        }
        return;
      }
      if (params.nodes.length === 0) {
        selectDevice(null);
      }
    });

    // Right-click → context menu (nodes or edges).
    network.on('oncontext', (params) => {
      params.event.preventDefault();
      const rect = containerRef.current!.getBoundingClientRect();
      const x = params.event.clientX ?? (params.pointer.DOM.x + rect.left);
      const y = params.event.clientY ?? (params.pointer.DOM.y + rect.top);

      if (params.nodes.length > 0) {
        const nodeId = params.nodes[0] as string;
        setContextMenu({ x, y, deviceId: nodeId });
        setEdgeContextMenu(null);
      } else if (params.edges.length > 0) {
        const edgeId = params.edges[0] as string;
        // Check if the edge is a manual link.
        const curLinks = linksRef.current;
        const link = curLinks.find((l) => `${l.from}-${l.to}` === edgeId);
        if (link?.manual) {
          setEdgeContextMenu({ x, y, edgeId, isManual: true });
          setContextMenu(null);
        }
      }
    });

    // Pause animation loop during drag for smooth performance.
    network.on('dragStart', (params) => {
      if (params.nodes.length > 0) {
        isDraggingRef.current = true;
      }
    });

    // Drag-to-reposition → send position update via WebSocket.
    network.on('dragEnd', (params) => {
      isDraggingRef.current = false;
      if (params.nodes.length > 0) {
        const nodeId = params.nodes[0] as string;
        const pos = network.getPosition(nodeId);
        sendWsMessage({
          type: 'position_update',
          device_id: nodeId,
          position: { x: Math.round(pos.x), y: Math.round(pos.y) },
        });
      }
    });

    // Particle animation: draw traffic flow on top of edges.
    network.on('afterDrawing', (ctx: CanvasRenderingContext2D) => {
      const now = performance.now();
      const dt = (now - lastFrameTimeRef.current) / 1000;
      lastFrameTimeRef.current = now;

      const curLinks = linksRef.current;
      const curTraffic = trafficDataRef.current;

      for (const link of curLinks) {
        const edgeId = `${link.from}-${link.to}`;
        const fromDev = link.from.split(':')[0];
        const toDev = link.to.split(':')[0];
        const fromIf = link.from.split(':').slice(1).join(':');
        const toIf = link.to.split(':').slice(1).join(':');

        // Get traffic for this link from either side.
        const fromTraffic = curTraffic[fromDev]?.[fromIf];
        const toTraffic = curTraffic[toDev]?.[toIf];
        const maxBps = Math.max(
          fromTraffic?.txBps || 0,
          fromTraffic?.rxBps || 0,
          toTraffic?.txBps || 0,
          toTraffic?.rxBps || 0,
        );

        if (maxBps <= 0) {
          particlesRef.current.delete(edgeId);
          continue;
        }

        // Get node positions in network coordinates.
        let fromPos: { x: number; y: number };
        let toPos: { x: number; y: number };
        try {
          fromPos = network.getPosition(fromDev);
          toPos = network.getPosition(toDev);
        } catch {
          continue;
        }

        // Compute utilisation for particle count and speed.
        const speedBps = link.speed * 1_000_000;
        const utilPct = speedBps > 0 ? (maxBps / speedBps) * 100 : 0;
        const targetCount = Math.min(5, Math.max(1, Math.ceil(utilPct / 20)));
        const particleSpeed = 0.3 + Math.min(utilPct / 100, 1) * 0.7;
        const color = getTrafficColor(utilPct);

        // Manage particle pool for this edge.
        let particles = particlesRef.current.get(edgeId) || [];
        while (particles.length < targetCount) {
          particles.push({ t: Math.random(), speed: particleSpeed });
        }
        if (particles.length > targetCount) {
          particles = particles.slice(0, targetCount);
        }

        // Draw particles.
        ctx.save();
        ctx.fillStyle = color;
        ctx.globalAlpha = 0.85;
        for (const p of particles) {
          p.t += p.speed * dt;
          if (p.t > 1) p.t -= 1;

          const x = fromPos.x + (toPos.x - fromPos.x) * p.t;
          const y = fromPos.y + (toPos.y - fromPos.y) * p.t;

          ctx.beginPath();
          ctx.arc(x, y, 3, 0, Math.PI * 2);
          ctx.fill();
        }
        ctx.restore();

        particlesRef.current.set(edgeId, particles);
      }
    });

    networkRef.current = network;

    return () => {
      cancelAnimationFrame(animFrameRef.current);
      network.destroy();
    };
  }, [selectDevice]);

  // Toggle drag mode when lock state changes.
  useEffect(() => {
    dragUnlockedRef.current = dragUnlocked;
    networkRef.current?.setOptions({ interaction: { dragNodes: dragUnlocked } });
  }, [dragUnlocked]);

  // Sync devices → vis nodes when config changes (filter hidden devices).
  useEffect(() => {
    const nodes = nodesRef.current;
    const existingIds = new Set(nodes.getIds());
    const visibleDevices = devices.filter((d) => !hiddenDevices.has(d.id));
    const configIds = new Set(visibleDevices.map((d) => d.id));

    for (const dev of visibleDevices) {
      const ping = pingData[dev.id];
      const color = getPingColor(ping?.lastSeen ?? null, thresholds);
      const imageUrl = getDeviceImageUrl(dev.type, color);

      const nodeData = {
        id: dev.id,
        label: `<b>${dev.name}</b>\n${dev.host}`,
        shape: 'image',
        image: imageUrl,
        size: 32,
        x: dev.position.x,
        y: dev.position.y,
        title: `${dev.name} (${dev.host})\nType: ${dev.type}\nProfile: ${dev.profile}`,
      };

      if (existingIds.has(dev.id)) {
        nodes.update(nodeData);
      } else {
        nodes.add(nodeData);
      }
    }

    // Remove nodes no longer in config or hidden.
    for (const id of existingIds) {
      if (!configIds.has(id as string)) {
        nodes.remove(id);
      }
    }
  }, [devices, thresholds, hiddenDevices]); // Don't include pingData — handled by animation loop.

  // Sync links → vis edges (incremental, filter hidden device links).
  useEffect(() => {
    const edges = edgesRef.current;
    const existingIds = new Set(edges.getIds());
    const newIds = new Set<string>();

    // Filter out links where either endpoint is hidden.
    const visibleLinks = links.filter((l) => {
      const fromDev = l.from.split(':')[0];
      const toDev = l.to.split(':')[0];
      return !hiddenDevices.has(fromDev) && !hiddenDevices.has(toDev);
    });

    for (const link of visibleLinks) {
      const edgeId = `${link.from}-${link.to}`;
      newIds.add(edgeId);

      const fromDev = link.from.split(':')[0];
      const toDev = link.to.split(':')[0];
      const fromIf = link.from.split(':').slice(1).join(':');
      const toIf = link.to.split(':').slice(1).join(':');

      // Build edge label: speed + abbreviated interface names for confirmed links.
      const speedLabel = link.speed >= 1000 ? `${link.speed / 1000}G` : `${link.speed}M`;
      const ifLabel = (fromIf && fromIf !== 'auto' && toIf && toIf !== 'auto')
        ? `${fromIf} \u2194 ${toIf}`
        : '';
      const edgeLabel = ifLabel ? `${speedLabel}\n${ifLabel}` : speedLabel;

      // Confirmed status label.
      const statusTag = link.manual ? ' [manual]' : link.confirmed ? '' : ' [unconfirmed]';

      // Dash pattern: unconfirmed links get a distinct dash, manual links get blue-ish.
      let dashes: boolean | number[] = LINK_DASHES[link.type] ?? false;
      if (!link.confirmed && !link.manual && link.type === 'wired') {
        dashes = [6, 6];
      }

      const edgeData = {
        id: edgeId,
        from: fromDev,
        to: toDev,
        width: linkWidth(link.speed),
        dashes,
        label: edgeLabel,
        title: `${fromDev}:${fromIf} \u2194 ${toDev}:${toIf}\nSpeed: ${link.speed} Mbps${statusTag}`,
      };

      if (existingIds.has(edgeId)) {
        edges.update(edgeData);
      } else {
        edges.add(edgeData);
      }
    }

    // Remove edges no longer in links.
    for (const id of existingIds) {
      if (!newIds.has(id as string)) {
        edges.remove(id);
        lastEdgeColorsRef.current.delete(id as string);
        particlesRef.current.delete(id as string);
      }
    }
  }, [links, hiddenDevices]);

  // Animation loop: update node images + edge colours only when changed,
  // and redraw for particle animation. Self-throttled to ~10fps via timestamp.
  const lastAnimTimeRef = useRef(0);
  const ANIM_INTERVAL_MS = 100; // ~10fps

  const updateNodes = useCallback(() => {
    const now = performance.now();

    // Self-throttle: skip if less than ANIM_INTERVAL_MS since last real update.
    if (now - lastAnimTimeRef.current < ANIM_INTERVAL_MS) {
      animFrameRef.current = requestAnimationFrame(updateNodes);
      return;
    }
    lastAnimTimeRef.current = now;

    // Skip data updates while drag mode is unlocked for smooth repositioning.
    if (dragUnlockedRef.current || isDraggingRef.current) {
      animFrameRef.current = requestAnimationFrame(updateNodes);
      return;
    }

    const nodes = nodesRef.current;
    const edges = edgesRef.current;
    let anyChanged = false;

    // Update node images from ping data — only when label or image changed.
    const visDevices = devices.filter((d) => !hiddenDevices.has(d.id));
    for (const dev of visDevices) {
      const ping = pingData[dev.id];
      const color = getPingColor(ping?.lastSeen ?? null, thresholds);
      const imageUrl = getDeviceImageUrl(dev.type, color);
      const rtt = ping?.rttMs;
      const lastSeen = ping?.lastSeen;

      let statusLine = '';
      if (lastSeen) {
        const elapsed = (Date.now() - new Date(lastSeen).getTime()) / 1000;
        if (elapsed <= 35) {
          statusLine = rtt !== null && rtt !== undefined ? `${rtt.toFixed(1)} ms` : '';
        } else if (elapsed < 195) {
          statusLine = `Missing: ${Math.round(elapsed)}s`;
        } else if (elapsed < 3600) {
          statusLine = `Missing: ${Math.round(elapsed / 60)}m`;
        } else {
          statusLine = `Missing: ${Math.round(elapsed / 3600)}h`;
        }
      } else {
        statusLine = 'Never seen';
      }

      const label = `<b>${dev.name}</b>\n${dev.host}\n${statusLine}`;
      const prevLabel = lastNodeLabelsRef.current.get(dev.id);
      const prevImage = lastNodeImagesRef.current.get(dev.id);

      if (label !== prevLabel || imageUrl !== prevImage) {
        nodes.update({ id: dev.id, label, image: imageUrl });
        lastNodeLabelsRef.current.set(dev.id, label);
        lastNodeImagesRef.current.set(dev.id, imageUrl);
        anyChanged = true;
      }
    }

    // Update edge colours from traffic data — only when colour changed.
    for (const link of links) {
      const edgeId = `${link.from}-${link.to}`;
      const fromDev = link.from.split(':')[0];
      const fromIf = link.from.split(':').slice(1).join(':');
      const toDev = link.to.split(':')[0];
      const toIf = link.to.split(':').slice(1).join(':');

      const fromTraffic = trafficData[fromDev]?.[fromIf];
      const toTraffic = trafficData[toDev]?.[toIf];
      const maxBps = Math.max(
        fromTraffic?.txBps || 0,
        fromTraffic?.rxBps || 0,
        toTraffic?.txBps || 0,
        toTraffic?.rxBps || 0,
      );

      const speedBps = link.speed * 1_000_000;
      const utilPct = speedBps > 0 ? (maxBps / speedBps) * 100 : 0;
      const edgeColor = getTrafficColor(utilPct);

      const prevColor = lastEdgeColorsRef.current.get(edgeId);
      if (edgeColor !== prevColor) {
        // Build traffic tooltip.
        const txBps = fromTraffic?.txBps || toTraffic?.rxBps || 0;
        const rxBps = fromTraffic?.rxBps || toTraffic?.txBps || 0;
        const trafficLabel =
          txBps > 0 || rxBps > 0
            ? `\nTX: ${formatBandwidth(txBps)}\nRX: ${formatBandwidth(rxBps)}`
            : '';

        edges.update({
          id: edgeId,
          color: { color: edgeColor, hover: '#9CA3AF', highlight: '#60A5FA' },
          title: `${fromDev}:${fromIf} ↔ ${toDev}:${toIf}\nSpeed: ${link.speed} Mbps${trafficLabel}`,
        });
        lastEdgeColorsRef.current.set(edgeId, edgeColor);
        anyChanged = true;
      }
    }

    // Only redraw if something changed or particles are active.
    if (anyChanged || particlesRef.current.size > 0) {
      networkRef.current?.redraw();
    }

    animFrameRef.current = requestAnimationFrame(updateNodes);
  }, [devices, links, pingData, trafficData, thresholds]);

  // Start/restart animation loop when dependencies change.
  useEffect(() => {
    cancelAnimationFrame(animFrameRef.current);
    if (devices.length > 0) {
      animFrameRef.current = requestAnimationFrame(updateNodes);
    }
    return () => cancelAnimationFrame(animFrameRef.current);
  }, [updateNodes]);

  const handleZoomIn = () => {
    const net = networkRef.current;
    if (!net) return;
    const scale = net.getScale();
    net.moveTo({ scale: scale * 1.3, animation: { duration: 200, easingFunction: 'easeInOutQuad' } });
  };

  const handleZoomOut = () => {
    const net = networkRef.current;
    if (!net) return;
    const scale = net.getScale();
    net.moveTo({ scale: scale / 1.3, animation: { duration: 200, easingFunction: 'easeInOutQuad' } });
  };

  const handleFitAll = () => {
    networkRef.current?.fit({ animation: { duration: 300, easingFunction: 'easeInOutQuad' } });
  };

  const btnStyle: React.CSSProperties = {
    width: '36px',
    height: '36px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: '#1F2937',
    border: '1px solid #374151',
    borderRadius: '6px',
    color: '#D1D5DB',
    fontSize: '18px',
    cursor: 'pointer',
    userSelect: 'none',
  };

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      <div
        ref={containerRef}
        style={{
          width: '100%',
          height: '100%',
          background: '#111827',
          borderRadius: '8px',
        }}
      />
      {/* Top-left controls: LIVE indicator + sidebar toggle */}
      <div style={{
        position: 'absolute',
        top: '12px',
        left: '12px',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: '6px',
        zIndex: 50,
      }}>
        <div style={{
          ...btnStyle,
          width: '36px',
          height: '20px',
          fontSize: '9px',
          fontWeight: 700,
          letterSpacing: '0.5px',
          cursor: 'default',
          background: wsConnected ? '#065F46' : '#991B1B',
          color: wsConnected ? '#6EE7B7' : '#FCA5A5',
          border: wsConnected ? '1px solid #065F46' : '1px solid #991B1B',
        }}>
          {wsConnected ? 'LIVE' : 'OFF'}
        </div>
        <button
          onClick={toggleSidebar}
          style={{
            ...btnStyle,
            background: sidebarVisible ? '#374151' : '#1F2937',
            border: sidebarVisible ? '1px solid #60A5FA' : '1px solid #374151',
            color: sidebarVisible ? '#60A5FA' : '#D1D5DB',
            fontSize: '16px',
          }}
          title={sidebarVisible ? 'Hide device list' : 'Show device list'}
        >
          &#9776;
        </button>
      </div>
      {/* Map controls */}
      <div style={{
        position: 'absolute',
        top: '12px',
        right: '12px',
        display: 'flex',
        flexDirection: 'column',
        gap: '6px',
        zIndex: 50,
      }}>
        <button
          onClick={() => setDragUnlocked((v) => !v)}
          style={{
            ...btnStyle,
            background: dragUnlocked ? '#374151' : '#1F2937',
            color: dragUnlocked ? '#F59E0B' : '#D1D5DB',
            border: dragUnlocked ? '1px solid #F59E0B' : '1px solid #374151',
          }}
          title={dragUnlocked ? 'Lock positions (disable drag)' : 'Unlock positions (enable drag)'}
        >
          {dragUnlocked ? '\u{1F513}' : '\u{1F512}'}
        </button>
        <button
          onClick={() => {
            if (linkMode) {
              setLinkMode(false);
              setLinkFirstDevice(null);
            } else {
              setLinkMode(true);
              setLinkFirstDevice(null);
            }
          }}
          style={{
            ...btnStyle,
            background: linkMode ? '#1E3A5F' : '#1F2937',
            color: linkMode ? '#60A5FA' : '#D1D5DB',
            border: linkMode ? '1px solid #3B82F6' : '1px solid #374151',
            fontSize: '14px',
          }}
          title={linkMode ? 'Cancel link creation (Esc)' : 'Create manual link'}
        >
          {'\u{1F517}'}
        </button>
        <button onClick={handleZoomIn} style={btnStyle} title="Zoom in">+</button>
        <button onClick={handleZoomOut} style={btnStyle} title="Zoom out">&minus;</button>
        <button onClick={handleFitAll} style={{ ...btnStyle, fontSize: '13px', fontWeight: 700 }} title="Fit all">
          [ ]
        </button>
      </div>

      {/* Link mode indicator */}
      {linkMode && (
        <div style={{
          position: 'absolute',
          bottom: '16px',
          left: '50%',
          transform: 'translateX(-50%)',
          background: '#1E3A5F',
          border: '1px solid #3B82F6',
          borderRadius: '8px',
          padding: '8px 16px',
          color: '#DBEAFE',
          fontSize: '13px',
          fontWeight: 600,
          zIndex: 50,
          whiteSpace: 'nowrap',
        }}>
          {linkFirstDevice
            ? `Click second device to link with "${linkFirstDevice}" (Esc to cancel)`
            : 'Click first device to start link (Esc to cancel)'}
        </div>
      )}

      {/* Right-click context menu */}
      {contextMenu && (
        <ContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          deviceId={contextMenu.deviceId}
          onClose={() => setContextMenu(null)}
          onBlacklist={(id) => setConfirmTarget(id)}
        />
      )}

      {/* Confirm dialog for blacklist/remove */}
      {confirmTarget && (
        <ConfirmDialog
          title="Remove Device"
          message={`Are you sure you want to remove "${confirmTarget}"? It will be blacklisted and will not reappear on the map.`}
          confirmLabel="Remove"
          onCancel={() => setConfirmTarget(null)}
          onConfirm={async () => {
            await apiBlacklist(confirmTarget);
            setConfirmTarget(null);
          }}
        />
      )}

      {/* Edge context menu (manual links only) */}
      {edgeContextMenu && (
        <div
          style={{
            position: 'fixed',
            left: edgeContextMenu.x,
            top: edgeContextMenu.y,
            background: '#1F2937',
            border: '1px solid #374151',
            borderRadius: '8px',
            padding: '4px 0',
            zIndex: 1000,
            boxShadow: '0 4px 16px rgba(0,0,0,0.5)',
            minWidth: '140px',
            fontFamily: 'Inter, system-ui, sans-serif',
          }}
          onClick={() => setEdgeContextMenu(null)}
        >
          <div
            style={{
              padding: '8px 16px',
              fontSize: '13px',
              color: '#FCA5A5',
              cursor: 'pointer',
            }}
            onMouseEnter={(e) => (e.currentTarget.style.background = '#374151')}
            onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
            onClick={async () => {
              await apiDeleteLink(edgeContextMenu.edgeId);
              setEdgeContextMenu(null);
            }}
          >
            Delete Link
          </div>
        </div>
      )}

      {/* Link creation dialog */}
      {linkDialog && (
        <LinkDialog
          fromDevice={linkDialog.from}
          toDevice={linkDialog.to}
          onCancel={() => setLinkDialog(null)}
          onConfirm={async (data) => {
            const from = `${linkDialog.from}:${data.fromIf}`;
            const to = `${linkDialog.to}:${data.toIf}`;
            await apiCreateLink(from, to, data.speed, data.type);
            setLinkDialog(null);
          }}
        />
      )}
    </div>
  );
}
