/**
 * Display formatting utilities.
 */

/** Format uptime or downtime duration from seconds. */
export function formatDuration(seconds: number): string {
  if (seconds < 0) return '—';

  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);

  if (days > 0) return `${days}d ${hours}h ${minutes}m`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m ${secs}s`;
  return `${secs}s`;
}

/** Format elapsed time since a timestamp as "missing since" text. */
export function formatMissingSince(lastSeen: string | null): string {
  if (!lastSeen) return 'Never seen';
  const elapsed = (Date.now() - new Date(lastSeen).getTime()) / 1000;
  if (elapsed <= 5) return '';
  return `Missing: ${formatDuration(elapsed)}`;
}

/** Format bandwidth in human-readable units. */
export function formatBandwidth(bps: number): string {
  if (bps >= 1e9) return `${(bps / 1e9).toFixed(1)} Gbps`;
  if (bps >= 1e6) return `${(bps / 1e6).toFixed(1)} Mbps`;
  if (bps >= 1e3) return `${(bps / 1e3).toFixed(1)} Kbps`;
  return `${Math.round(bps)} bps`;
}

/** Format RTT in ms. */
export function formatRtt(rttMs: number | null): string {
  if (rttMs === null) return '—';
  if (rttMs < 1) return '<1 ms';
  return `${rttMs.toFixed(1)} ms`;
}