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
  parent?: string;
  discovered?: boolean;
  pinned?: boolean;
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
  confirmed?: boolean;
  manual?: boolean;
}

export interface MapInfo {
  name: string;
  label: string;
  parent: string | null;
  background: string | null;
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
  maps: MapInfo[];

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
  setConfig: (devices: DeviceInfo[], links: LinkInfo[], thresholds: Threshold[], maps?: MapInfo[]) => void;
  updatePingState: (devices: PingData[]) => void;
  updateTraffic: (interfaces: TrafficData) => void;
  updateDevicePosition: (deviceId: string, position: { x: number; y: number }) => void;
  mergeTopology: (
    addedDevices: DeviceInfo[],
    addedLinks: LinkInfo[],
    removedLinks: string[],
    removedDevices?: string[],
    updatedDevices?: DeviceInfo[],
  ) => void;
  setVisibility: (hidden: string[], blacklisted: string[]) => void;
  removeDevice: (deviceId: string) => void;
  selectDevice: (deviceId: string | null) => void;
  toggleSidebar: () => void;
  setCurrentMap: (mapName: string) => void;
  updateDeviceMap: (deviceId: string, map: string) => void;
  updateMapLabel: (mapName: string, label: string) => void;
  setMaps: (maps: MapInfo[]) => void;
  setWsConnected: (connected: boolean) => void;
}

export const useNetworkStore = create<NetworkState>((set) => ({
  devices: [],
  links: [],
  thresholds: DEFAULT_THRESHOLDS,
  maps: [{ name: 'main', label: 'Network Overview', parent: null, background: null }],
  pingData: {},
  trafficData: {},
  hiddenDevices: new Set<string>(),
  blacklistedDevices: [],
  selectedDevice: null,
  sidebarVisible: false,
  currentMap: 'main',
  wsConnected: false,

  setConfig: (devices, links, thresholds, maps) =>
    set({
      devices,
      links,
      thresholds: thresholds.length > 0 ? thresholds : DEFAULT_THRESHOLDS,
      ...(maps && maps.length > 0 ? { maps } : {}),
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

  mergeTopology: (addedDevices, addedLinks, removedLinks, removedDevices, updatedDevices) =>
    set((state) => {
      // Remove devices if requested.
      const removedDevSet = new Set(removedDevices || []);
      const baseDevices = removedDevSet.size > 0
        ? state.devices.filter((d) => !removedDevSet.has(d.id))
        : state.devices;

      // Merge updated + added devices by ID.
      const mergedDeviceMap = new Map(baseDevices.map((d) => [d.id, d]));

      for (const dev of (updatedDevices || [])) {
        if (removedDevSet.has(dev.id)) continue;
        const existing = mergedDeviceMap.get(dev.id);
        mergedDeviceMap.set(dev.id, existing ? { ...existing, ...dev } : dev);
      }
      for (const dev of addedDevices) {
        if (removedDevSet.has(dev.id)) continue;
        const existing = mergedDeviceMap.get(dev.id);
        mergedDeviceMap.set(dev.id, existing ? { ...existing, ...dev } : dev);
      }

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
        devices: Array.from(mergedDeviceMap.values()),
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
  updateDeviceMap: (deviceId, map) =>
    set((state) => ({
      devices: state.devices.map((d) =>
        d.id === deviceId ? { ...d, map } : d,
      ),
    })),
  updateMapLabel: (mapName, label) =>
    set((state) => ({
      maps: state.maps.map((m) =>
        m.name === mapName ? { ...m, label } : m,
      ),
    })),
  setMaps: (maps) => set({ maps }),
  setWsConnected: (connected) => set({ wsConnected: connected }),
}));
