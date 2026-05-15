import type { DeviceInfo, LinkInfo } from '../stores/networkStore';

export function endpointDevice(endpoint: string): string {
  return endpoint.split(':')[0] || endpoint;
}

export function devicesForMap(
  devices: DeviceInfo[],
  links: LinkInfo[],
  mapName: string,
  hiddenDevices: Set<string>,
): DeviceInfo[] {
  const visibleIds = new Set(
    devices
      .filter((device) => !hiddenDevices.has(device.id) && (device.map === mapName || device.pinned))
      .map((device) => device.id),
  );
  const knownIds = new Set(devices.map((device) => device.id));

  for (const link of links) {
    if (link.map !== mapName) continue;
    const from = endpointDevice(link.from);
    const to = endpointDevice(link.to);
    if (!hiddenDevices.has(from) && knownIds.has(from)) visibleIds.add(from);
    if (!hiddenDevices.has(to) && knownIds.has(to)) visibleIds.add(to);
  }

  return devices.filter((device) => visibleIds.has(device.id));
}

export function linksForMap(
  links: LinkInfo[],
  devices: DeviceInfo[],
  mapName: string,
  hiddenDevices: Set<string>,
): LinkInfo[] {
  const knownIds = new Set(devices.map((device) => device.id));
  const mapDeviceIds = new Set(
    devices
      .filter((device) => device.map === mapName || device.pinned)
      .map((device) => device.id),
  );

  return links.filter((link) => {
    const from = endpointDevice(link.from);
    const to = endpointDevice(link.to);
    if (hiddenDevices.has(from) || hiddenDevices.has(to)) return false;
    if (!knownIds.has(from) || !knownIds.has(to)) return false;
    if (link.map) return link.map === mapName;
    return mapDeviceIds.has(from) && mapDeviceIds.has(to);
  });
}
