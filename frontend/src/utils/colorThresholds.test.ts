import { describe, expect, it } from 'vitest';
import {
  DEFAULT_THRESHOLDS,
  getPingColor,
  getPingLabel,
  getPulseSpeed,
  getTrafficColor,
  type Threshold,
} from './colorThresholds';

const TEST_THRESHOLDS: Threshold[] = [
  { maxSeconds: 10, color: '#green', label: 'Online' },
  { maxSeconds: 20, color: '#yellow', label: '' },
  { maxSeconds: 30, color: '#red', label: 'Down' },
];

function seenSecondsAgo(seconds: number): string {
  return new Date(Date.now() - seconds * 1000).toISOString();
}

describe('getPingColor', () => {
  it('returns grey for never-seen devices', () => {
    expect(getPingColor(null)).toBe('#6B7280');
  });

  it('returns the first threshold colour for recently-seen devices', () => {
    expect(getPingColor(seenSecondsAgo(5), TEST_THRESHOLDS)).toBe('#green');
  });

  it('walks the threshold bands as elapsed time grows', () => {
    expect(getPingColor(seenSecondsAgo(15), TEST_THRESHOLDS)).toBe('#yellow');
    expect(getPingColor(seenSecondsAgo(25), TEST_THRESHOLDS)).toBe('#red');
  });

  it('clamps to the last threshold colour beyond the final band', () => {
    expect(getPingColor(seenSecondsAgo(3600), TEST_THRESHOLDS)).toBe('#red');
  });

  it('treats clock skew (future timestamp) as online', () => {
    expect(getPingColor(seenSecondsAgo(-60), TEST_THRESHOLDS)).toBe('#green');
  });

  it('uses the default thresholds when none are given', () => {
    expect(getPingColor(seenSecondsAgo(5))).toBe(DEFAULT_THRESHOLDS[0].color);
  });
});

describe('getPingLabel', () => {
  it('returns Unknown for never-seen devices', () => {
    expect(getPingLabel(null)).toBe('Unknown');
  });

  it('falls back to Online for bands without a label', () => {
    expect(getPingLabel(seenSecondsAgo(15), TEST_THRESHOLDS)).toBe('Online');
  });

  it('returns Down beyond the final band', () => {
    expect(getPingLabel(seenSecondsAgo(3600), TEST_THRESHOLDS)).toBe('Down');
  });
});

describe('getPulseSpeed', () => {
  it('returns null for never-seen and for the fastest band', () => {
    expect(getPulseSpeed(null)).toBeNull();
    expect(getPulseSpeed(seenSecondsAgo(5))).toBeNull();
  });

  it('speeds up as the device ages', () => {
    expect(getPulseSpeed(seenSecondsAgo(50))).toBe('2s');
    expect(getPulseSpeed(seenSecondsAgo(100))).toBe('1.5s');
    expect(getPulseSpeed(seenSecondsAgo(200))).toBe('0.3s');
  });

  it('stops pulsing past the last band', () => {
    expect(getPulseSpeed(seenSecondsAgo(400))).toBeNull();
  });
});

describe('getTrafficColor', () => {
  it('returns grey for no traffic', () => {
    expect(getTrafficColor(0)).toBe('#4B5563');
    expect(getTrafficColor(-5)).toBe('#4B5563');
  });

  it('maps utilisation bands to colours', () => {
    expect(getTrafficColor(1)).toBe('#4B5563'); // first band boundary is still idle
    expect(getTrafficColor(2)).toBe('#22C55E');
    expect(getTrafficColor(25)).toBe('#22C55E');
    expect(getTrafficColor(40)).toBe('#FFFF00');
    expect(getTrafficColor(60)).toBe('#FF8C00');
    expect(getTrafficColor(90)).toBe('#EF4444');
  });

  it('clamps over-100% utilisation to the hottest colour', () => {
    expect(getTrafficColor(150)).toBe('#EF4444');
  });
});
