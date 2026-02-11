/**
 * Graduated ping color system.
 * Computes device node color from last_seen timestamp in real-time.
 */

export interface Threshold {
  maxSeconds: number;
  color: string;
  label: string;
}

/** Default thresholds — overridden by server config. */
export const DEFAULT_THRESHOLDS: Threshold[] = [
  { maxSeconds: 35, color: '#22C55E', label: 'Online' },
  { maxSeconds: 70, color: '#FFFF00', label: 'Degraded' },
  { maxSeconds: 105, color: '#FFD700', label: '' },
  { maxSeconds: 135, color: '#FF8C00', label: '' },
  { maxSeconds: 165, color: '#FF6600', label: '' },
  { maxSeconds: 195, color: '#CC4400', label: '' },
  { maxSeconds: 345, color: '#EF4444', label: 'Down' },
];

/** Never-seen colour (grey). */
const UNKNOWN_COLOR = '#6B7280';

/**
 * Get the current color for a device based on how long since it was last seen.
 * Called at animation frame rate for smooth transitions.
 */
export function getPingColor(
  lastSeen: string | null,
  thresholds: Threshold[] = DEFAULT_THRESHOLDS,
): string {
  if (!lastSeen) return UNKNOWN_COLOR;

  const elapsedMs = Date.now() - new Date(lastSeen).getTime();
  const elapsedSec = elapsedMs / 1000;

  if (elapsedSec < 0) return thresholds[0].color; // clock skew

  for (const t of thresholds) {
    if (elapsedSec <= t.maxSeconds) {
      return t.color;
    }
  }

  return thresholds[thresholds.length - 1].color;
}

/**
 * Get a status label for a device.
 */
export function getPingLabel(
  lastSeen: string | null,
  thresholds: Threshold[] = DEFAULT_THRESHOLDS,
): string {
  if (!lastSeen) return 'Unknown';

  const elapsedMs = Date.now() - new Date(lastSeen).getTime();
  const elapsedSec = elapsedMs / 1000;

  for (const t of thresholds) {
    if (elapsedSec <= t.maxSeconds) {
      return t.label || 'Online';
    }
  }

  return 'Down';
}

/**
 * Get pulse animation speed based on elapsed time.
 * Returns CSS animation-duration value.
 */
export function getPulseSpeed(lastSeen: string | null): string | null {
  if (!lastSeen) return null;

  const elapsedSec = (Date.now() - new Date(lastSeen).getTime()) / 1000;

  if (elapsedSec <= 35) return null; // solid green, no pulse
  if (elapsedSec <= 70) return '2s';
  if (elapsedSec <= 105) return '1.5s';
  if (elapsedSec <= 135) return '1s';
  if (elapsedSec <= 195) return '0.5s';
  if (elapsedSec <= 345) return '0.3s';
  return null; // solid red, no pulse
}

/** Default edge colour (no traffic data). */
const EDGE_IDLE_COLOR = '#4B5563';

/** Traffic utilisation colour bands. */
const TRAFFIC_COLORS: { maxPct: number; color: string }[] = [
  { maxPct: 1, color: EDGE_IDLE_COLOR },
  { maxPct: 25, color: '#22C55E' },
  { maxPct: 50, color: '#FFFF00' },
  { maxPct: 75, color: '#FF8C00' },
  { maxPct: 100, color: '#EF4444' },
];

/**
 * Get edge colour based on traffic utilisation percentage (0-100+).
 * 0% → grey, 1-25% → green, 25-50% → yellow, 50-75% → orange, 75%+ → red.
 */
export function getTrafficColor(utilizationPct: number): string {
  if (utilizationPct <= 0) return EDGE_IDLE_COLOR;
  for (const band of TRAFFIC_COLORS) {
    if (utilizationPct <= band.maxPct) return band.color;
  }
  return TRAFFIC_COLORS[TRAFFIC_COLORS.length - 1].color;
}
