export function formatTimestamp(ts: number | null) {
  if (!ts) return '—';
  return new Date(ts * 1000).toLocaleString();
}

export function formatMON(value: number) {
  if (value >= 1000) return `${(value / 1000).toFixed(2)}K`;
  return value.toFixed(4);
}

export const KNOWN_METHODS: Record<string, string> = {
  '0x84994fec': 'Delegate',
  '0xa9059cbb': 'Transfer',
  '0x095ea7b3': 'Approve',
  '0x23b872dd': 'TransferFrom',
  '0x573c1ce0': 'GetDelegator',
  '0x4fd66050': 'GetDelegations',
};

export function formatMethod(method: string | null) {
  if (!method) return '—';
  return KNOWN_METHODS[method] || method;
}
