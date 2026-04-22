import type { TransactionRecord, WalletRisk } from '../types';

// ── Transaction Summary helpers ──────────────────────────────────────

export interface TxSummaryPeriod {
  label: string;
  inCount: number;
  outCount: number;
  inValue: number;
  outValue: number;
}

export function computeTxSummary(txs: TransactionRecord[], address: string): TxSummaryPeriod[] {
  const now = Date.now() / 1000;
  const periods = [
    { label: '24 Hours', cutoff: now - 86400 },
    { label: '7 Days', cutoff: now - 7 * 86400 },
    { label: '30 Days', cutoff: now - 30 * 86400 },
    { label: 'All Time', cutoff: 0 },
  ];
  const addr = address.toLowerCase();
  return periods.map(({ label, cutoff }) => {
    let inCount = 0, outCount = 0, inValue = 0, outValue = 0;
    for (const tx of txs) {
      if (tx.timestamp < cutoff) continue;
      if (tx.from_addr === addr) {
        outCount++;
        outValue += tx.value;
      } else if (tx.to_addr === addr) {
        inCount++;
        inValue += tx.value;
      }
    }
    return { label, inCount, outCount, inValue, outValue };
  });
}

// ── Risk Profile helpers ────────────────────────────────────────────

export interface RiskAnalysis {
  score: number; // 0-10
  level: 'clean' | 'low' | 'medium' | 'high' | 'critical';
  color: string;
  factors: { name: string; detail: string; weight: number }[];
}

export function analyzeRisk(
  txs: TransactionRecord[],
  address: string,
  risk: WalletRisk | null,
): RiskAnalysis {
  const addr = address.toLowerCase();
  const factors: RiskAnalysis['factors'] = [];
  let rawScore = 0;

  // Factor 1: Circular flows / wash trading (from graph if indexed)
  if (risk && risk.flags.length > 0) {
    for (const flag of risk.flags) {
      if (flag.startsWith('circular_flows')) {
        const count = parseInt(flag.split(':')[1]) || 0;
        const w = Math.min(count * 1.5, 4);
        factors.push({ name: 'Circular Flows', detail: `${count} bidirectional partner(s) detected`, weight: w });
        rawScore += w;
      } else if (flag.startsWith('high_fan_out')) {
        const count = parseInt(flag.split(':')[1]) || 0;
        factors.push({ name: 'High Fan-Out', detail: `Sent to ${count} unique wallets`, weight: 2 });
        rawScore += 2;
      } else if (flag.startsWith('high_velocity')) {
        factors.push({ name: 'High Velocity', detail: flag.replace('high_velocity:', '') + ' tx/hr', weight: 2 });
        rawScore += 2;
      }
    }
  }

  // Factor 2: Transaction pattern analysis (from Monadscan data)
  if (txs.length > 0) {
    const uniqueCounterparties = new Set<string>();
    let selfTxCount = 0;
    let roundTripPartners = new Set<string>();
    const sentTo = new Set<string>();
    const receivedFrom = new Set<string>();
    let totalIn = 0, totalOut = 0;
    const timestamps: number[] = [];

    for (const tx of txs) {
      timestamps.push(tx.timestamp);
      if (tx.from_addr === addr) {
        sentTo.add(tx.to_addr);
        totalOut += tx.value;
        if (tx.to_addr === addr) selfTxCount++;
        uniqueCounterparties.add(tx.to_addr);
      } else {
        receivedFrom.add(tx.from_addr);
        totalIn += tx.value;
        uniqueCounterparties.add(tx.from_addr);
      }
    }

    // Round-trip detection
    for (const a of sentTo) {
      if (receivedFrom.has(a)) roundTripPartners.add(a);
    }
    if (roundTripPartners.size > 0) {
      const w = Math.min(roundTripPartners.size * 1, 3);
      factors.push({ name: 'Round-Trip Transfers', detail: `${roundTripPartners.size} address(es) with both in+out flows`, weight: w });
      rawScore += w;
    }

    // Self-transfers
    if (selfTxCount > 0) {
      factors.push({ name: 'Self-Transfers', detail: `${selfTxCount} transaction(s) sent to self`, weight: 2 });
      rawScore += 2;
    }

    // Velocity (if enough txs)
    if (timestamps.length >= 5) {
      const minT = Math.min(...timestamps);
      const maxT = Math.max(...timestamps);
      const hours = Math.max((maxT - minT) / 3600, 0.1);
      const txPerHour = timestamps.length / hours;
      if (txPerHour > 60) {
        factors.push({ name: 'Bot-Like Speed', detail: `${txPerHour.toFixed(0)} tx/hr`, weight: 2 });
        rawScore += 2;
      } else if (txPerHour > 20) {
        factors.push({ name: 'High Frequency', detail: `${txPerHour.toFixed(0)} tx/hr`, weight: 1 });
        rawScore += 1;
      }
    }

    // Value symmetry (wash trading signal)
    if (totalIn > 0 && totalOut > 0) {
      const ratio = Math.min(totalIn, totalOut) / Math.max(totalIn, totalOut);
      if (ratio > 0.9 && txs.length > 4) {
        factors.push({ name: 'Value Symmetry', detail: `In/Out ratio ${(ratio * 100).toFixed(0)}% — possible wash trading`, weight: 2 });
        rawScore += 2;
      }
    }

    // Diversity (low diversity = suspicious)
    if (txs.length > 10 && uniqueCounterparties.size <= 3) {
      factors.push({ name: 'Low Diversity', detail: `${txs.length} txs with only ${uniqueCounterparties.size} counterpart(s)`, weight: 1.5 });
      rawScore += 1.5;
    }
  }

  // If no factors found, it's clean
  if (factors.length === 0) {
    factors.push({ name: 'No Risk Signals', detail: 'No suspicious patterns detected', weight: 0 });
  }

  const score = Math.min(Math.round(rawScore * 10) / 10, 10);
  let level: RiskAnalysis['level'] = 'clean';
  let color = '#22c55e';
  if (score >= 8) { level = 'critical'; color = '#dc2626'; }
  else if (score >= 5) { level = 'high'; color = '#f97316'; }
  else if (score >= 3) { level = 'medium'; color = '#f59e0b'; }
  else if (score > 0) { level = 'low'; color = '#3b82f6'; }

  return { score, level, color, factors };
}
