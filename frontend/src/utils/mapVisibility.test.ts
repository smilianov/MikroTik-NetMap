import { describe, expect, it } from 'vitest';
import type { DeviceInfo, LinkInfo } from '../stores/networkStore';
import { devicesForMap, endpointDevice, linksForMap } from './mapVisibility';

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

describe('endpointDevice', () => {
  it('strips the interface suffix', () => {
    expect(endpointDevice('router1:ether1')).toBe('router1');
  });

  it('returns the whole string when no suffix', () => {
    expect(endpointDevice('router1')).toBe('router1');
  });

  it('keeps only the first segment for multi-colon endpoints', () => {
    expect(endpointDevice('router1:sfp-sfpplus1:extra')).toBe('router1');
  });
});

describe('devicesForMap', () => {
  const devices = [
    makeDevice('a', { map: 'main' }),
    makeDevice('b', { map: 'branch' }),
    makeDevice('c', { map: 'branch', pinned: true }),
  ];

  it('returns only devices on the requested map (plus pinned)', () => {
    const result = devicesForMap(devices, [], 'main', new Set());
    expect(result.map((d) => d.id)).toEqual(['a', 'c']);
  });

  it('includes pinned devices on every map', () => {
    const result = devicesForMap(devices, [], 'main', new Set());
    expect(result.map((d) => d.id)).toContain('c');
  });

  it('excludes hidden devices', () => {
    const result = devicesForMap(devices, [], 'branch', new Set(['b']));
    expect(result.map((d) => d.id)).toEqual(['c']);
  });

  it('pulls in devices referenced by links on the map', () => {
    // 'a' is on main, but a branch-map link connects it to 'b'.
    const links = [makeLink('a:ether1', 'b:ether1', { map: 'branch' })];
    const result = devicesForMap(devices, links, 'branch', new Set());
    expect(result.map((d) => d.id).sort()).toEqual(['a', 'b', 'c']);
  });

  it('does not pull in hidden link endpoints', () => {
    const links = [makeLink('a:ether1', 'b:ether1', { map: 'branch' })];
    const result = devicesForMap(devices, links, 'branch', new Set(['a']));
    expect(result.map((d) => d.id)).not.toContain('a');
  });
});

describe('linksForMap', () => {
  const devices = [
    makeDevice('a', { map: 'main' }),
    makeDevice('b', { map: 'main' }),
    makeDevice('c', { map: 'branch' }),
  ];

  it('keeps links whose endpoints are both on the map', () => {
    const links = [makeLink('a:ether1', 'b:ether1')];
    expect(linksForMap(links, devices, 'main', new Set())).toHaveLength(1);
    expect(linksForMap(links, devices, 'branch', new Set())).toHaveLength(0);
  });

  it('uses the link map when set', () => {
    const links = [makeLink('a:ether1', 'c:ether1', { map: 'branch' })];
    expect(linksForMap(links, devices, 'branch', new Set())).toHaveLength(1);
    expect(linksForMap(links, devices, 'main', new Set())).toHaveLength(0);
  });

  it('drops links with hidden or unknown endpoints', () => {
    const links = [
      makeLink('a:ether1', 'b:ether1'),
      makeLink('a:ether2', 'ghost:ether1'),
    ];
    expect(linksForMap(links, devices, 'main', new Set(['b']))).toHaveLength(0);
    expect(linksForMap(links, devices, 'main', new Set())).toHaveLength(1);
  });
});
