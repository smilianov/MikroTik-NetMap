/**
 * Zustand store for network state (devices, links, ping data, traffic).
 */

import { create } from 'zustand';
import { type Threshold, DEFAULT_THRESHOLDS } from '../utils/colorThresholds';

export interface DeviceInfo {
  id: string;
  name: string;
  host: string;
  type: string;
  profile: string;
  map: string;
  position: { x: number; y: number };
}

export interface PingData {
  id: string;
  lastSeen: string | null;
  rttMs: number | null;
  isAlive: boolean;
}

export interface LinkInfo {
  from: string;
  to: string;
  speed: number;
  type: string;
}

export interface InterfaceTraffic {
  rxBps: number;
  txBps: number;
}

/** device_id → interface_name → traffic stats */
export type TrafficData = Record<string, Record<string, InterfaceTraffic>>;

interface NetworkState {
  // Config from server.
  devices: DeviceInfo[];
  links: LinkInfo[];
  thresholds: Threshold[];

  // Real-time ping state.
  pingData: Record<string, PingData>;

  // Real-time traffic state.
  trafficData: TrafficData;

  // UI state.
  selectedDevice: string | null;
  currentMap: string;
  wsConnected: boolean;

  // Actions.
  setConfig: (devices: DeviceInfo[], links: LinkInfo[], thresholds: Threshold[]) => void;
  updatePingState: (devices: PingData[]) => void;
  updateTraffic: (interfaces: TrafficData) => void;
  updateDevicePosition: (deviceId: string, position: { x: number; y: number }) => void;
  mergeTopology: (
    addedDevices: DeviceInfo[],
    addedLinks: LinkInfo[],
    removedLinks: string[],
  ) => void;
  selectDevice: (deviceId: string | null) => void;
  setCurrentMap: (mapName: string) => void;
  setWsConnected: (connected: boolean) => void;
}

export const useNetworkStore = create<NetworkState>((set) => ({
  devices: [],
  links: [],
  thresholds: DEFAULT_THRESHOLDS,
  pingData: {},
  trafficData: {},
  selectedDevice: null,
  currentMap: 'main',
  wsConnected: false,

  setConfig: (devices, links, thresholds) =>
    set({
      devices,
      links,
      thresholds: thresholds.length > 0 ? thresholds : DEFAULT_THRESHOLDS,
    }),

  updatePingState: (devices) =>
    set((state) => {
      const updated = { ...state.pingData };
      for (const d of devices) {
        updated[d.id] = d;
      }
      return { pingData: updated };
    }),

  updateTraffic: (interfaces) => set({ trafficData: interfaces }),

  updateDevicePosition: (deviceId, position) =>
    set((state) => ({
      devices: state.devices.map((d) =>
        d.id === deviceId ? { ...d, position } : d,
      ),
    })),

  mergeTopology: (addedDevices, addedLinks, removedLinks) =>
    set((state) => {
      // Merge new devices (skip duplicates).
      const existingIds = new Set(state.devices.map((d) => d.id));
      const newDevices = addedDevices.filter((d) => !existingIds.has(d.id));

      // Build a set of removed link IDs for filtering.
      const removedSet = new Set(removedLinks);

      // Remove old links and add new ones.
      const filteredLinks = state.links.filter(
        (l) => !removedSet.has(`${l.from}-${l.to}`),
      );

      // Deduplicate added links.
      const existingLinkKeys = new Set(filteredLinks.map((l) => `${l.from}-${l.to}`));
      const newLinks = addedLinks.filter(
        (l) => !existingLinkKeys.has(`${l.from}-${l.to}`),
      );

      return {
        devices: [...state.devices, ...newDevices],
        links: [...filteredLinks, ...newLinks],
      };
    }),

  selectDevice: (deviceId) => set({ selectedDevice: deviceId }),
  setCurrentMap: (mapName) => set({ currentMap: mapName }),
  setWsConnected: (connected) => set({ wsConnected: connected }),
}));
