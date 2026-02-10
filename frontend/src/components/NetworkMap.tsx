/**
 * Main network topology map using vis-network.
 * Renders devices as image nodes with status-indicator dots
 * and links as edges with real-time updates.
 */

import { useEffect, useRef, useCallback } from 'react';
import { Network, DataSet } from 'vis-network/standalone';
import { useNetworkStore } from '../stores/networkStore';
import { getPingColor } from '../utils/colorThresholds';
import { getDeviceImageUrl, preloadDeviceImages } from '../utils/deviceIcons';

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

export function NetworkMap() {
  const containerRef = useRef<HTMLDivElement>(null);
  const networkRef = useRef<Network | null>(null);
  const nodesRef = useRef<DataSet<any>>(new DataSet());
  const edgesRef = useRef<DataSet<any>>(new DataSet());
  const animFrameRef = useRef<number>(0);

  const { devices, links, pingData, thresholds, selectDevice } = useNetworkStore();

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

  // Animation loop: update node images at ~10fps from pingData.
  const updateNodes = useCallback(() => {
    const nodes = nodesRef.current;

    for (const dev of devices) {
      const ping = pingData[dev.id];
      const color = getPingColor(ping?.lastSeen ?? null, thresholds);
      const imageUrl = getDeviceImageUrl(dev.type, color);
      const rtt = ping?.rttMs;
      const lastSeen = ping?.lastSeen;

      // Compute uptime/downtime label.
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

    animFrameRef.current = requestAnimationFrame(() => {
      setTimeout(() => {
        animFrameRef.current = requestAnimationFrame(updateNodes);
      }, 100);
    });
  }, [devices, pingData, thresholds]);

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
