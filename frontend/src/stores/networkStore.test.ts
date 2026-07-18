import { beforeEach, describe, expect, it } from 'vitest';
import { useNetworkStore, type DeviceInfo, type LinkInfo } from './networkStore';

function makeDevice(id: string, overrides: Partial<DeviceInfo> = {}): DeviceInfo {
  return {
    id,
    name: id,
    host: `${id}.example.com`,
    type: 'router',
    profile: 'edge',
    map: 'main',
    position: { x: 0, y: 0 },
    ...overrides,
  };
}

function makeLink(from: string, to: string, overrides: Partial<LinkInfo> = {}): LinkInfo {
  return { from, to, speed: 1000, type: 'wired', ...overrides };
}

describe('networkStore mergeTopology', () => {
  beforeEach(() => {
    useNetworkStore.setState({
      devices: [makeDevice('a'), makeDevice('b')],
      links: [makeLink('a:ether1', 'b:ether1')],
    });
  });

  it('adds new devices and links', () => {
    useNetworkStore.getState().mergeTopology(
      [makeDevice('c')],
      [makeLink('b:ether2', 'c:ether1')],
      [],
    );

    const state = useNetworkStore.getState();
    expect(state.devices.map((d) => d.id)).toEqual(['a', 'b', 'c']);
    expect(state.links).toHaveLength(2);
    expect(state.links[1]).toMatchObject({ from: 'b:ether2', to: 'c:ether1' });
  });

  it('removes links by from-to key', () => {
    useNetworkStore.getState().mergeTopology([], [], ['a:ether1-b:ether1']);

    expect(useNetworkStore.getState().links).toHaveLength(0);
  });

  it('removes devices and skips re-adding them in the same update', () => {
    useNetworkStore.getState().mergeTopology(
      [makeDevice('a', { host: 'new-a.example.com' })],
      [],
      [],
      ['a'],
    );

    const state = useNetworkStore.getState();
    expect(state.devices.map((d) => d.id)).toEqual(['b']);
  });

  it('merges updated devices into existing entries', () => {
    useNetworkStore.getState().mergeTopology(
      [],
      [],
      [],
      [],
      [makeDevice('a', { host: 'renamed.example.com' })],
    );

    const device = useNetworkStore.getState().devices.find((d) => d.id === 'a');
    expect(device?.host).toBe('renamed.example.com');
    expect(device?.name).toBe('a');
  });

  it('appends updated devices that do not exist yet', () => {
    useNetworkStore.getState().mergeTopology([], [], [], [], [makeDevice('z')]);

    expect(useNetworkStore.getState().devices.map((d) => d.id)).toEqual(['a', 'b', 'z']);
  });

  it('deduplicates added links that already exist', () => {
    useNetworkStore.getState().mergeTopology(
      [],
      [makeLink('a:ether1', 'b:ether1', { speed: 10000 })],
      [],
    );

    const state = useNetworkStore.getState();
    expect(state.links).toHaveLength(1);
    expect(state.links[0].speed).toBe(1000);
  });

  it('merges added devices into existing entries instead of duplicating', () => {
    useNetworkStore.getState().mergeTopology(
      [makeDevice('a', { discovered: true })],
      [],
      [],
    );

    const state = useNetworkStore.getState();
    expect(state.devices).toHaveLength(2);
    expect(state.devices.find((d) => d.id === 'a')?.discovered).toBe(true);
  });
});
