/**
 * SVG device icons for network topology map.
 * Each icon is a clean white SVG designed for dark backgrounds.
 * A small status-indicator dot is composited in the bottom-right corner.
 */

/** SVG paths for each device type (drawn inside a 48x48 viewBox, centered). */
const DEVICE_SVG: Record<string, string> = {
  // Router: classic router icon — box with two upward arrows
  router: `
    <rect x="8" y="20" width="32" height="20" rx="3" fill="none" stroke="#E5E7EB" stroke-width="2"/>
    <line x1="14" y1="26" x2="14" y2="34" stroke="#9CA3AF" stroke-width="1.5"/>
    <line x1="20" y1="26" x2="20" y2="34" stroke="#9CA3AF" stroke-width="1.5"/>
    <line x1="26" y1="26" x2="26" y2="34" stroke="#9CA3AF" stroke-width="1.5"/>
    <line x1="32" y1="26" x2="32" y2="34" stroke="#9CA3AF" stroke-width="1.5"/>
    <circle cx="37" cy="36" r="2" fill="#60A5FA"/>
    <path d="M16 20 L16 10 L12 14" fill="none" stroke="#60A5FA" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M32 20 L32 10 L36 14" fill="none" stroke="#60A5FA" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M16 10 L20 14" fill="none" stroke="#60A5FA" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M32 10 L28 14" fill="none" stroke="#60A5FA" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
  `,

  // Switch: network switch — rectangular with port indicators
  switch: `
    <rect x="4" y="16" width="40" height="20" rx="3" fill="none" stroke="#E5E7EB" stroke-width="2"/>
    <rect x="9" y="22" width="4" height="6" rx="1" fill="#9CA3AF"/>
    <rect x="16" y="22" width="4" height="6" rx="1" fill="#9CA3AF"/>
    <rect x="23" y="22" width="4" height="6" rx="1" fill="#9CA3AF"/>
    <rect x="30" y="22" width="4" height="6" rx="1" fill="#9CA3AF"/>
    <rect x="37" y="22" width="4" height="6" rx="1" fill="#60A5FA"/>
    <circle cx="11" cy="31" r="1.5" fill="#22C55E"/>
    <circle cx="18" cy="31" r="1.5" fill="#22C55E"/>
    <circle cx="25" cy="31" r="1.5" fill="#22C55E"/>
    <circle cx="32" cy="31" r="1.5" fill="#6B7280"/>
    <circle cx="39" cy="31" r="1.5" fill="#60A5FA"/>
  `,

  // AP: access point — dome with WiFi signal waves
  ap: `
    <ellipse cx="24" cy="34" rx="12" ry="6" fill="none" stroke="#E5E7EB" stroke-width="2"/>
    <line x1="24" y1="28" x2="24" y2="22" stroke="#E5E7EB" stroke-width="2"/>
    <circle cx="24" cy="20" r="3" fill="none" stroke="#E5E7EB" stroke-width="2"/>
    <path d="M15 16 A12 12 0 0 1 33 16" fill="none" stroke="#60A5FA" stroke-width="1.5" stroke-linecap="round"/>
    <path d="M11 12 A16 16 0 0 1 37 12" fill="none" stroke="#60A5FA" stroke-width="1.5" stroke-linecap="round" opacity="0.7"/>
    <path d="M7 8 A20 20 0 0 1 41 8" fill="none" stroke="#60A5FA" stroke-width="1.5" stroke-linecap="round" opacity="0.4"/>
  `,

  // Server: server tower with drive bays
  server: `
    <rect x="12" y="6" width="24" height="36" rx="3" fill="none" stroke="#E5E7EB" stroke-width="2"/>
    <line x1="12" y1="18" x2="36" y2="18" stroke="#E5E7EB" stroke-width="1.5"/>
    <line x1="12" y1="30" x2="36" y2="30" stroke="#E5E7EB" stroke-width="1.5"/>
    <rect x="16" y="10" width="12" height="3" rx="1" fill="#9CA3AF"/>
    <circle cx="32" cy="11.5" r="1.5" fill="#22C55E"/>
    <rect x="16" y="22" width="12" height="3" rx="1" fill="#9CA3AF"/>
    <circle cx="32" cy="23.5" r="1.5" fill="#60A5FA"/>
    <rect x="16" y="34" width="12" height="3" rx="1" fill="#9CA3AF"/>
    <circle cx="32" cy="35.5" r="1.5" fill="#6B7280"/>
  `,

  // Other: generic device — monitor/screen
  other: `
    <rect x="8" y="8" width="32" height="24" rx="3" fill="none" stroke="#E5E7EB" stroke-width="2"/>
    <rect x="12" y="12" width="24" height="16" rx="1" fill="#1F2937" stroke="#9CA3AF" stroke-width="1"/>
    <line x1="24" y1="32" x2="24" y2="38" stroke="#E5E7EB" stroke-width="2"/>
    <line x1="16" y1="38" x2="32" y2="38" stroke="#E5E7EB" stroke-width="2" stroke-linecap="round"/>
    <circle cx="24" cy="20" r="3" fill="none" stroke="#60A5FA" stroke-width="1.5"/>
    <path d="M22 22 L26 22" stroke="#60A5FA" stroke-width="1.5" stroke-linecap="round"/>
  `,
};

/** Image cache: key = `${type}-${color}`, value = data URL. */
const imageCache = new Map<string, string>();

/**
 * Generate a composite SVG data URL for a device node.
 * Contains the device icon centered with a small status-indicator dot
 * in the bottom-right corner.
 */
export function getDeviceImageUrl(deviceType: string, statusColor: string): string {
  const key = `${deviceType}-${statusColor}`;
  const cached = imageCache.get(key);
  if (cached) return cached;

  const iconSvg = DEVICE_SVG[deviceType] || DEVICE_SVG.other;

  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="72" height="72" viewBox="0 0 72 72">
  <!-- Dark background circle for contrast -->
  <circle cx="36" cy="36" r="34" fill="#1F2937" stroke="#374151" stroke-width="1.5"/>
  <!-- Device icon (48x48 centered in 72x72) -->
  <g transform="translate(12, 12)">
    ${iconSvg}
  </g>
  <!-- Status indicator dot (bottom-right) -->
  <circle cx="58" cy="58" r="9" fill="${statusColor}" stroke="#111827" stroke-width="2.5"/>
</svg>`;

  const url = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
  imageCache.set(key, url);
  return url;
}

/** Pre-warm the cache for common combinations. */
export function preloadDeviceImages(colors: string[]): void {
  const types = Object.keys(DEVICE_SVG);
  for (const type of types) {
    for (const color of colors) {
      getDeviceImageUrl(type, color);
    }
  }
}
