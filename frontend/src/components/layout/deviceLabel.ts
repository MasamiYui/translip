/** Compress a verbose backend device string (e.g. "MPS (Apple Silicon)") to a short badge label. */
export function shortDeviceLabel(device: string): string {
  if (device.startsWith('MPS')) return 'MPS'
  if (device.startsWith('CUDA')) return 'CUDA'
  if (device.startsWith('CPU')) return 'CPU'
  return device
}
