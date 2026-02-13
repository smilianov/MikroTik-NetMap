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

  // Visibility state.
  hiddenDevices: Set<string>;
  blacklistedDevices: string[];

  // UI state.
  selectedDevice: string | null;
  sidebarVisible: boolean;
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
    removedDevices?: string[],
  ) => void;
  setVisibility: (hidden: string[], blacklisted: string[]) => void;
  removeDevice: (deviceId: string) => void;
  selectDevice: (deviceId: string | null) => void;
  toggleSidebar: () => void;
  setCurrentMap: (mapName: string) => void;
  setWsConnected: (connected: boolean) => void;
}

export const useNetworkStore = create<NetworkState>((set) => ({
  devices: [],
  links: [],
  thresholds: DEFAULT_THRESHOLDS,
  pingData: {},
  trafficData: {},
  hiddenDevices: new Set<string>(),
  blacklistedDevices: [],
  selectedDevice: null,
  sidebarVisible: false,
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

  mergeTopology: (addedDevices, addedLinks, removedLinks, removedDevices) =>
    set((state) => {
      // Remove devices if requested.
      const removedDevSet = new Set(removedDevices || []);
      let baseDevices = removedDevSet.size > 0
        ? state.devices.filter((d) => !removedDevSet.has(d.id))
        : state.devices;

      // Merge new devices (skip duplicates).
      const existingIds = new Set(baseDevices.map((d) => d.id));
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
        devices: [...baseDevices, ...newDevices],
        links: [...filteredLinks, ...newLinks],
      };
    }),

  setVisibility: (hidden, blacklisted) =>
    set({ hiddenDevices: new Set(hidden), blacklistedDevices: blacklisted }),

  removeDevice: (deviceId) =>
    set((state) => ({
      devices: state.devices.filter((d) => d.id !== deviceId),
      links: state.links.filter((l) => {
        const fromDev = l.from.split(':')[0];
        const toDev = l.to.split(':')[0];
        return fromDev !== deviceId && toDev !== deviceId;
      }),
    })),

  selectDevice: (deviceId) => set({ selectedDevice: deviceId }),
  toggleSidebar: () => set((state) => ({ sidebarVisible: !state.sidebarVisible })),
  setCurrentMap: (mapName) => set({ currentMap: mapName }),
  setWsConnected: (connected) => set({ wsConnected: connected }),
}));
