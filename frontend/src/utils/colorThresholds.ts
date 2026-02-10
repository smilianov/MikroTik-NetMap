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
  { maxSeconds: 5, color: '#22C55E', label: 'Online' },
  { maxSeconds: 10, color: '#FFFF00', label: 'Degraded' },
  { maxSeconds: 15, color: '#FFD700', label: '' },
  { maxSeconds: 20, color: '#FF8C00', label: '' },
  { maxSeconds: 25, color: '#FF6600', label: '' },
  { maxSeconds: 30, color: '#CC4400', label: '' },
  { maxSeconds: 180, color: '#EF4444', label: 'Down' },
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

  if (elapsedSec <= 5) return null; // solid green, no pulse
  if (elapsedSec <= 10) return '2s';
  if (elapsedSec <= 15) return '1.5s';
  if (elapsedSec <= 20) return '1s';
  if (elapsedSec <= 30) return '0.5s';
  if (elapsedSec <= 180) return '0.3s';
  return null; // solid red, no pulse
}
