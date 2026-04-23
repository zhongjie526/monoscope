"""Advanced fraud detection patterns inspired by Neo4j Graph Summit APAC 2023.

Patterns:
1. Fund Cycling — rapid receive → send within short windows
2. Betweenness / Bridge Wallets — intermediaries connecting clusters
3. 2-Hop Sybil Expansion — expand known sybil clusters by 1 tx hop
4. Rapid Cash-Out — receive large amount, send >90% quickly
5. Shared Contract Clustering — wallets interacting with same rare targets
"""

import logging
from collections import defaultdict
from fastapi import APIRouter

from app.database import db
from app.routers.fraud import FraudAlert, _get_cached, _set_cached

logger = logging.getLogger(__name__)

router = APIRouter()


# ── 1. Fund Cycling Detection ──────────────────────────────────────────

@router.get("/fund-cycling", response_model=list[FraudAlert])
async def detect_fund_cycling(window_seconds: int = 60, min_value: float = 1000):
    """Detect wallets that receive and forward funds rapidly (within N seconds).

    Pattern: Wallet receives MON → sends similar amount within `window_seconds`.
    Classic money laundering / mixer behaviour.
    """
    cache_key = f"cycling:{window_seconds}:{min_value}"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    result = await db.aquery(
        """
        MATCH (sender:Wallet)-[:SENT]->(tx_in:Transaction)-[:TO]->(w:Wallet)
        WHERE tx_in.value >= $min_value
        MATCH (w)-[:SENT]->(tx_out:Transaction)-[:TO]->(receiver:Wallet)
        WHERE tx_out.timestamp >= tx_in.timestamp
          AND tx_out.timestamp <= tx_in.timestamp + $window
          AND tx_out.value >= tx_in.value * 0.8
          AND sender.address <> receiver.address
        WITH w, sender, receiver, tx_in, tx_out,
             tx_out.timestamp - tx_in.timestamp AS delay_secs
        RETURN w.address AS relay,
               sender.address AS from_addr,
               receiver.address AS to_addr,
               tx_in.value AS in_value,
               tx_out.value AS out_value,
               delay_secs,
               tx_in.hash AS in_hash,
               tx_out.hash AS out_hash
        ORDER BY delay_secs ASC
        LIMIT 50
        """,
        {"window": window_seconds, "min_value": min_value},
    )

    # Group by relay wallet
    relays: dict[str, list] = defaultdict(list)
    for r in result:
        relays[r["relay"]].append(r)

    alerts = []
    for relay, instances in relays.items():
        alerts.append(
            FraudAlert(
                pattern="fund_cycling",
                severity="critical" if len(instances) > 3 else "high",
                wallets=[relay] + list({i["from_addr"] for i in instances} | {i["to_addr"] for i in instances}),
                description=(
                    f"Fund cycling: {relay} relayed {len(instances)} transactions "
                    f"(receive→forward within {window_seconds}s, values ≥{min_value} MON)"
                ),
                evidence={
                    "relay": relay,
                    "instance_count": len(instances),
                    "fastest_delay_secs": min(i["delay_secs"] for i in instances),
                    "total_relayed": sum(i["in_value"] for i in instances),
                    "sample": instances[:5],
                },
            )
        )
    alerts.sort(key=lambda a: a.evidence.get("instance_count", 0), reverse=True)
    _set_cached(cache_key, alerts)
    return alerts


# ── 2. Bridge Wallet Detection (Betweenness Proxy) ────────────────────

@router.get("/bridge-wallets", response_model=list[FraudAlert])
async def detect_bridge_wallets(min_unique_sources: int = 5, min_unique_targets: int = 5):
    """Detect wallets that act as intermediaries (high betweenness proxy).

    Instead of full betweenness centrality (requires GDS), we use a proxy:
    wallets with many unique senders AND many unique recipients that
    don't overlap much — i.e., they bridge separate communities.
    """
    cache_key = f"bridge:{min_unique_sources}:{min_unique_targets}"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    result = await db.aquery(
        """
        MATCH (src:Wallet)-[:SENT]->(tx_in:Transaction)-[:TO]->(w:Wallet)
        WITH w, collect(DISTINCT src.address) AS sources
        WHERE size(sources) >= $min_sources
        MATCH (w)-[:SENT]->(tx_out:Transaction)-[:TO]->(dst:Wallet)
        WITH w, sources, collect(DISTINCT dst.address) AS targets
        WHERE size(targets) >= $min_targets
        WITH w, sources, targets,
             size(sources) AS in_degree,
             size(targets) AS out_degree,
             size([s IN sources WHERE s IN targets]) AS overlap
        WITH w, in_degree, out_degree, overlap,
             toFloat(overlap) / toFloat(size(sources) + size(targets) - overlap) AS jaccard
        WHERE jaccard < 0.3
        RETURN w.address AS address,
               in_degree, out_degree, overlap, jaccard
        ORDER BY (in_degree + out_degree) DESC
        LIMIT 20
        """,
        {"min_sources": min_unique_sources, "min_targets": min_unique_targets},
    )

    alerts = []
    for r in result:
        bridge_score = (r["in_degree"] + r["out_degree"]) * (1 - r["jaccard"])
        alerts.append(
            FraudAlert(
                pattern="bridge_wallet",
                severity="high" if bridge_score > 50 else "medium",
                wallets=[r["address"]],
                description=(
                    f"Bridge wallet: {r['address']} connects {r['in_degree']} senders → "
                    f"{r['out_degree']} recipients (only {r['overlap']} overlap, "
                    f"Jaccard {r['jaccard']:.2f})"
                ),
                evidence={
                    "in_degree": r["in_degree"],
                    "out_degree": r["out_degree"],
                    "overlap": r["overlap"],
                    "jaccard_similarity": round(r["jaccard"], 3),
                    "bridge_score": round(bridge_score, 1),
                },
            )
        )
    _set_cached(cache_key, alerts)
    return alerts


# ── 3. Rapid Cash-Out Detection ───────────────────────────────────────

@router.get("/rapid-cashout", response_model=list[FraudAlert])
async def detect_rapid_cashout(window_blocks: int = 50, drain_pct: float = 0.9):
    """Detect wallets that receive a large sum and drain >90% quickly.

    Pattern: Wallet receives big inflow → sends out ≥90% within N blocks.
    Typical of compromised wallets or planned extraction.
    """
    cache_key = f"cashout:{window_blocks}:{drain_pct}"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    result = await db.aquery(
        """
        MATCH (tx_in:Transaction)-[:TO]->(w:Wallet)
        WHERE tx_in.value > 10000
        WITH w, tx_in
        ORDER BY tx_in.value DESC
        WITH w, collect({val: tx_in.value, block: tx_in.block_number, hash: tx_in.hash})[0] AS biggest_in
        MATCH (w)-[:SENT]->(tx_out:Transaction)
        WHERE tx_out.block_number >= biggest_in.block
          AND tx_out.block_number <= biggest_in.block + $window_blocks
        WITH w, biggest_in,
             sum(tx_out.value) AS total_out,
             count(tx_out) AS out_count
        WHERE total_out >= biggest_in.val * $drain_pct
        RETURN w.address AS address,
               biggest_in.val AS inflow,
               total_out,
               out_count,
               biggest_in.block AS in_block,
               biggest_in.hash AS in_hash
        ORDER BY inflow DESC
        LIMIT 30
        """,
        {"window_blocks": window_blocks, "drain_pct": drain_pct},
    )

    alerts = []
    for r in result:
        pct = (r["total_out"] / r["inflow"]) * 100 if r["inflow"] > 0 else 0
        alerts.append(
            FraudAlert(
                pattern="rapid_cashout",
                severity="critical" if pct > 95 else "high",
                wallets=[r["address"]],
                description=(
                    f"Rapid cash-out: {r['address']} received {r['inflow']:.0f} MON "
                    f"and drained {pct:.0f}% ({r['total_out']:.0f} MON) "
                    f"within {window_blocks} blocks ({r['out_count']} txs)"
                ),
                evidence={
                    "inflow": r["inflow"],
                    "total_outflow": r["total_out"],
                    "drain_percentage": round(pct, 1),
                    "outbound_tx_count": r["out_count"],
                    "in_block": r["in_block"],
                    "in_hash": r["in_hash"],
                },
            )
        )
    _set_cached(cache_key, alerts)
    return alerts


# ── 4. 2-Hop Sybil Expansion ─────────────────────────────────────────

@router.get("/sybil-expansion", response_model=list[FraudAlert])
async def detect_sybil_expansion(min_cluster_size: int = 5):
    """Expand known sybil clusters by 1 transaction hop.

    Phase 1: Find fan-out clusters (existing sybil detection).
    Phase 2: Find wallets that transacted with cluster members
             but aren't in the cluster → potential accomplices.
    """
    cache_key = f"sybil_exp:{min_cluster_size}"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    result = await db.aquery(
        """
        // Phase 1: Find fan-out funders (sybil hubs)
        MATCH (funder:Wallet)-[:SENT]->(:Transaction)-[:TO]->(funded:Wallet)
        WITH funder, collect(DISTINCT funded.address) AS funded_wallets
        WHERE size(funded_wallets) >= $min_cluster_size

        // Phase 2: Find wallets 1 hop away from funded wallets
        UNWIND funded_wallets AS funded_addr
        MATCH (funded:Wallet {address: funded_addr})-[:SENT]->(tx:Transaction)-[:TO]->(outsider:Wallet)
        WHERE outsider.address <> funder.address
          AND NOT outsider.address IN funded_wallets
        WITH funder, funded_wallets, outsider,
             count(tx) AS tx_count, sum(tx.value) AS total_value
        WHERE tx_count >= 2
        RETURN funder.address AS funder,
               size(funded_wallets) AS cluster_size,
               outsider.address AS accomplice,
               tx_count,
               total_value
        ORDER BY cluster_size DESC, tx_count DESC
        LIMIT 50
        """,
        {"min_cluster_size": min_cluster_size},
    )

    # Group by funder
    groups: dict[str, list] = defaultdict(list)
    funder_sizes: dict[str, int] = {}
    for r in result:
        groups[r["funder"]].append(r)
        funder_sizes[r["funder"]] = r["cluster_size"]

    alerts = []
    for funder, accomplices in groups.items():
        accomplice_addrs = [a["accomplice"] for a in accomplices[:10]]
        alerts.append(
            FraudAlert(
                pattern="sybil_expansion",
                severity="critical" if len(accomplices) > 5 else "high",
                wallets=[funder] + accomplice_addrs,
                description=(
                    f"Sybil expansion: {funder} has {funder_sizes[funder]} funded wallets. "
                    f"Found {len(accomplices)} potential accomplices 1-hop away "
                    f"(wallets transacting with cluster members but not funded directly)"
                ),
                evidence={
                    "funder": funder,
                    "cluster_size": funder_sizes[funder],
                    "accomplice_count": len(accomplices),
                    "accomplices": [
                        {
                            "address": a["accomplice"],
                            "tx_count": a["tx_count"],
                            "total_value": a["total_value"],
                        }
                        for a in accomplices[:10]
                    ],
                },
            )
        )
    _set_cached(cache_key, alerts)
    return alerts


# ── 5. Shared Target Clustering ───────────────────────────────────────

@router.get("/shared-targets", response_model=list[FraudAlert])
async def detect_shared_targets(min_senders: int = 5):
    """Find wallets that receive from many of the same senders (coordinated).

    If multiple wallets all receive from the same set of senders,
    they're likely controlled by the same entity (sybil / wash).
    """
    cache_key = f"shared_targets:{min_senders}"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    result = await db.aquery(
        """
        MATCH (sender:Wallet)-[:SENT]->(tx:Transaction)-[:TO]->(target:Wallet)
        WITH target, collect(DISTINCT sender.address) AS senders
        WHERE size(senders) >= $min_senders
        WITH target, senders, size(senders) AS sender_count
        ORDER BY sender_count DESC
        LIMIT 30
        RETURN target.address AS target,
               sender_count,
               senders[..10] AS sample_senders
        """,
        {"min_senders": min_senders},
    )

    alerts = []
    for r in result:
        alerts.append(
            FraudAlert(
                pattern="shared_target",
                severity="medium" if r["sender_count"] < 20 else "high",
                wallets=[r["target"]] + r["sample_senders"],
                description=(
                    f"Shared target: {r['target']} received from "
                    f"{r['sender_count']} unique senders (possible aggregator/mixer)"
                ),
                evidence={
                    "target": r["target"],
                    "sender_count": r["sender_count"],
                    "sample_senders": r["sample_senders"],
                },
            )
        )
    _set_cached(cache_key, alerts)
    return alerts


# ── Composite Risk Score ──────────────────────────────────────────────

@router.get("/risk-scores", response_model=list[dict])
async def compute_risk_scores(limit: int = 50):
    """Compute composite risk scores for wallets based on multiple signals.

    Signals:
    - High tx velocity (txs per hour)
    - Fan-out ratio (unique recipients vs total txs)
    - Bridge behaviour (many sources AND targets with low overlap)
    - Fund cycling (receive→forward within 60s)
    - Rapid cash-out behaviour
    """
    cache_key = f"risk:{limit}"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    result = await db.aquery(
        """
        MATCH (w:Wallet)-[:SENT]->(tx:Transaction)
        WITH w, count(tx) AS sent_count, sum(tx.value) AS total_sent,
             min(tx.timestamp) AS first_ts, max(tx.timestamp) AS last_ts
        WHERE sent_count >= 3
        WITH w, sent_count, total_sent, first_ts, last_ts,
             CASE WHEN last_ts > first_ts
                  THEN toFloat(sent_count) / ((last_ts - first_ts) / 3600.0)
                  ELSE toFloat(sent_count) END AS txs_per_hour

        OPTIONAL MATCH (w)-[:SENT]->(tx2:Transaction)-[:TO]->(dst:Wallet)
        WITH w, sent_count, total_sent, txs_per_hour,
             count(DISTINCT dst.address) AS unique_recipients

        OPTIONAL MATCH (src:Wallet)-[:SENT]->(:Transaction)-[:TO]->(w)
        WITH w, sent_count, total_sent, txs_per_hour, unique_recipients,
             count(DISTINCT src.address) AS unique_senders

        WITH w, sent_count, total_sent, txs_per_hour,
             unique_recipients, unique_senders,
             toFloat(unique_recipients) / toFloat(sent_count) AS fanout_ratio,
             // Bridge proxy: high senders AND recipients
             CASE WHEN unique_senders >= 3 AND unique_recipients >= 3
                  THEN (unique_senders + unique_recipients) / 2.0
                  ELSE 0.0 END AS bridge_proxy

        // Composite score (0-1 range)
        WITH w.address AS address,
             sent_count, total_sent, txs_per_hour,
             unique_recipients, unique_senders,
             fanout_ratio, bridge_proxy,
             // Weighted components
             CASE WHEN txs_per_hour > 100 THEN 0.3
                  WHEN txs_per_hour > 30 THEN 0.2
                  WHEN txs_per_hour > 10 THEN 0.1
                  ELSE 0.0 END AS velocity_score,
             CASE WHEN unique_recipients > 100 THEN 0.3
                  WHEN unique_recipients > 20 THEN 0.2
                  WHEN unique_recipients > 10 THEN 0.1
                  ELSE 0.0 END AS fanout_score,
             CASE WHEN bridge_proxy > 20 THEN 0.2
                  WHEN bridge_proxy > 10 THEN 0.1
                  ELSE 0.0 END AS bridge_score

        WITH address, sent_count, total_sent, txs_per_hour,
             unique_recipients, unique_senders,
             velocity_score + fanout_score + bridge_score AS risk_score,
             velocity_score, fanout_score, bridge_score
        WHERE risk_score > 0
        RETURN address, risk_score, sent_count, total_sent,
               round(txs_per_hour * 10) / 10 AS txs_per_hour,
               unique_recipients, unique_senders,
               velocity_score, fanout_score, bridge_score
        ORDER BY risk_score DESC
        LIMIT $limit
        """,
        {"limit": limit},
    )

    _set_cached(cache_key, result)
    return result