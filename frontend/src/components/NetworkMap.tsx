/**
 * Main network topology map using vis-network.
 * Renders devices as image nodes with status-indicator dots,
 * links as edges with traffic-coloured lines and animated particles,
 * and supports drag-to-reposition with persistence.
 */

import { useEffect, useRef, useCallback } from 'react';
import { Network, DataSet } from 'vis-network/standalone';
import { useNetworkStore } from '../stores/networkStore';
import { getPingColor, getTrafficColor } from '../utils/colorThresholds';
import { getDeviceImageUrl, preloadDeviceImages } from '../utils/deviceIcons';
import { sendWsMessage } from '../hooks/useWebSocket';
import { formatBandwidth } from '../utils/formatters';

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

  // Refs for data accessed inside afterDrawing callback (registered once).
  const linksRef = useRef(useNetworkStore.getState().links);
  const trafficDataRef = useRef(useNetworkStore.getState().trafficData);

  const { devices, links, pingData, trafficData, thresholds, selectDevice } =
    useNetworkStore();

  // Keep refs in sync.
  useEffect(() => {
    linksRef.current = links;
  }, [links]);
  useEffect(() => {
    trafficDataRef.current = trafficData;
  }, [trafficData]);

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
        dragNodes: true, // Phase 3: drag-to-reposition
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

    // Single click → deselect.
    network.on('click', (params) => {
      if (params.nodes.length === 0) {
        selectDevice(null);
      }
    });

    // Drag-to-reposition → send position update via WebSocket.
    network.on('dragEnd', (params) => {
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

  // Sync devices → vis nodes when config changes.
  useEffect(() => {
    const nodes = nodesRef.current;
    const existingIds = new Set(nodes.getIds());
    const configIds = new Set(devices.map((d) => d.id));

    for (const dev of devices) {
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

    // Remove nodes no longer in config.
    for (const id of existingIds) {
      if (!configIds.has(id as string)) {
        nodes.remove(id);
      }
    }
  }, [devices, thresholds]); // Don't include pingData — handled by animation loop.

  // Sync links → vis edges.
  useEffect(() => {
    const edges = edgesRef.current;
    edges.clear();

    for (const link of links) {
      const fromDev = link.from.split(':')[0];
      const toDev = link.to.split(':')[0];
      const fromIf = link.from.split(':')[1] || '';
      const toIf = link.to.split(':')[1] || '';

      edges.add({
        id: `${link.from}-${link.to}`,
        from: fromDev,
        to: toDev,
        width: linkWidth(link.speed),
        dashes: LINK_DASHES[link.type] ?? false,
        label: `${link.speed >= 1000 ? `${link.speed / 1000}G` : `${link.speed}M`}`,
        title: `${fromDev}:${fromIf} ↔ ${toDev}:${toIf}\nSpeed: ${link.speed} Mbps`,
      });
    }
  }, [links]);

  // Animation loop: update node images + edge colours at ~10fps.
  const updateNodes = useCallback(() => {
    const nodes = nodesRef.current;
    const edges = edgesRef.current;

    // Update node images from ping data.
    for (const dev of devices) {
      const ping = pingData[dev.id];
      const color = getPingColor(ping?.lastSeen ?? null, thresholds);
      const imageUrl = getDeviceImageUrl(dev.type, color);
      const rtt = ping?.rttMs;
      const lastSeen = ping?.lastSeen;

      let statusLine = '';
      if (lastSeen) {
        const elapsed = (Date.now() - new Date(lastSeen).getTime()) / 1000;
        if (elapsed <= 5) {
          statusLine = rtt !== null && rtt !== undefined ? `${rtt.toFixed(1)} ms` : '';
        } else if (elapsed < 60) {
          statusLine = `Missing: ${Math.round(elapsed)}s`;
        } else if (elapsed < 3600) {
          statusLine = `Missing: ${Math.round(elapsed / 60)}m`;
        } else {
          statusLine = `Missing: ${Math.round(elapsed / 3600)}h`;
        }
      } else {
        statusLine = 'Never seen';
      }

      nodes.update({
        id: dev.id,
        label: `<b>${dev.name}</b>\n${dev.host}\n${statusLine}`,
        image: imageUrl,
      });
    }

    // Update edge colours from traffic data.
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
    }

    // Trigger redraw for particle animation.
    networkRef.current?.redraw();

    animFrameRef.current = requestAnimationFrame(() => {
      setTimeout(() => {
        animFrameRef.current = requestAnimationFrame(updateNodes);
      }, 100);
    });
  }, [devices, links, pingData, trafficData, thresholds]);

  // Start/restart animation loop when dependencies change.
  useEffect(() => {
    cancelAnimationFrame(animFrameRef.current);
    if (devices.length > 0) {
      animFrameRef.current = requestAnimationFrame(updateNodes);
    }
    return () => cancelAnimationFrame(animFrameRef.current);
  }, [updateNodes]);

  return (
    <div
      ref={containerRef}
      style={{
        width: '100%',
        height: '100%',
        background: '#111827',
        borderRadius: '8px',
      }}
    />
  );
}
