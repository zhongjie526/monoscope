"""Fraud detection endpoints — graph-based pattern analysis.

Uses two layers:
  - TRANSACTED: lightweight summary edge (Wallet→Wallet) for fast traversal
  - SENT/TO via Transaction node: full detail for drill-down

This dual-layer approach gives O(wallets) fraud scans instead of O(transactions).
"""

from fastapi import APIRouter
from pydantic import BaseModel

from app.database import db

router = APIRouter()


class FraudAlert(BaseModel):
    pattern: str
    severity: str
    wallets: list[str]
    description: str
    evidence: dict | None = None


class WalletRisk(BaseModel):
    address: str
    risk_score: float
    flags: list[str]
    details: str


# ── Wash Trading Detection ─────────────────────────────────────────────

@router.get("/wash-trading", response_model=list[FraudAlert])
async def detect_wash_trading(min_round_trips: int = 2):
    """Detect bidirectional fund flows (A⇄B) — wash trading signal.

    Uses TRANSACTED summary edges for speed — no variable-length paths.
    """
    result = db.query(
        """
        MATCH (a:Wallet)-[ab:TRANSACTED]->(b:Wallet)-[ba:TRANSACTED]->(a)
        WHERE a.address < b.address
          AND ab.tx_count + ba.tx_count >= $min_round_trips
        RETURN a.address AS wallet_a,
               b.address AS wallet_b,
               ab.tx_count AS a_to_b_count,
               ba.tx_count AS b_to_a_count,
               ab.total_value AS a_to_b_value,
               ba.total_value AS b_to_a_value,
               ab.tx_count + ba.tx_count AS total_txs
        ORDER BY total_txs DESC
        LIMIT 50
        """,
        {"min_round_trips": min_round_trips},
    )

    alerts = []
    for r in result:
        alerts.append(
            FraudAlert(
                pattern="wash_trading",
                severity="high" if r["total_txs"] > 10 else "medium",
                wallets=[r["wallet_a"], r["wallet_b"]],
                description=(
                    f"Bidirectional flows: {r['wallet_a'][:10]}... ⇄ {r['wallet_b'][:10]}... "
                    f"({r['a_to_b_count']}→ / {r['b_to_a_count']}←, "
                    f"{r['a_to_b_value']:.1f} / {r['b_to_a_value']:.1f} MON)"
                ),
                evidence={
                    "a_to_b": {"count": r["a_to_b_count"], "value": r["a_to_b_value"]},
                    "b_to_a": {"count": r["b_to_a_count"], "value": r["b_to_a_value"]},
                },
            )
        )
    return alerts


# ── Sybil Cluster Detection ────────────────────────────────────────────

@router.get("/sybil-clusters", response_model=list[FraudAlert])
async def detect_sybil_clusters(min_cluster_size: int = 5):
    """Detect wallets that funded many other wallets (fan-out pattern)."""
    result = db.query(
        """
        MATCH (funder:Wallet)-[:TRANSACTED]->(funded:Wallet)
        WITH funder, COUNT(funded) AS cluster_size,
             COLLECT(funded.address)[..20] AS funded_wallets,
             SUM(funder.last_seen - funder.first_seen) AS _
        WHERE cluster_size >= $min_cluster_size
        RETURN funder.address AS funder,
               funded_wallets,
               cluster_size
        ORDER BY cluster_size DESC
        LIMIT 20
        """,
        {"min_cluster_size": min_cluster_size},
    )

    alerts = []
    for r in result:
        alerts.append(
            FraudAlert(
                pattern="sybil_cluster",
                severity="critical" if r["cluster_size"] > 20 else "high",
                wallets=[r["funder"]] + r["funded_wallets"][:10],
                description=f"Fan-out: {r['funder'][:10]}... sent to {r['cluster_size']} unique wallets",
                evidence={
                    "funder": r["funder"],
                    "cluster_size": r["cluster_size"],
                    "sample": r["funded_wallets"][:10],
                },
            )
        )
    return alerts


# ── High Velocity Detection ────────────────────────────────────────────

@router.get("/high-velocity", response_model=list[FraudAlert])
async def detect_high_velocity(min_txs_per_hour: int = 60):
    """Detect wallets with bot-like transaction velocity."""
    result = db.query(
        """
        MATCH (w:Wallet)
        WHERE w.last_seen > w.first_seen
        WITH w,
             // Use TRANSACTED edges to count total outbound txs
             [(w)-[r:TRANSACTED]->() | r.tx_count] AS counts
        WITH w, REDUCE(s = 0, c IN counts | s + c) AS total_txs
        WHERE total_txs >= 10
        WITH w, total_txs,
             toFloat(total_txs) / ((w.last_seen - w.first_seen) / 3600.0) AS txs_per_hour
        WHERE txs_per_hour >= $min_txs_per_hour
        RETURN w.address AS address,
               total_txs AS tx_count,
               txs_per_hour,
               w.first_seen AS first_seen,
               w.last_seen AS last_seen
        ORDER BY txs_per_hour DESC
        LIMIT 30
        """,
        {"min_txs_per_hour": min_txs_per_hour},
    )

    alerts = []
    for r in result:
        alerts.append(
            FraudAlert(
                pattern="high_velocity",
                severity="medium",
                wallets=[r["address"]],
                description=f"Bot-like: {r['address'][:10]}... sent {r['tx_count']} txs ({r['txs_per_hour']:.0f}/hr)",
                evidence={
                    "tx_count": r["tx_count"],
                    "txs_per_hour": round(r["txs_per_hour"], 1),
                    "window_seconds": r["last_seen"] - r["first_seen"],
                },
            )
        )
    return alerts


# ── Wallet Risk Score ──────────────────────────────────────────────────

@router.get("/risk/{address}", response_model=WalletRisk)
async def get_wallet_risk(address: str):
    """Calculate risk score using TRANSACTED summary edges (fast)."""
    address = address.lower()

    result = db.query(
        """
        MATCH (w:Wallet {address: $address})

        // Fan-out via TRANSACTED
        OPTIONAL MATCH (w)-[out:TRANSACTED]->(recipient:Wallet)
        WITH w, COUNT(recipient) AS fan_out,
             COALESCE(SUM(out.tx_count), 0) AS total_sent_txs

        // Fan-in
        OPTIONAL MATCH (sender:Wallet)-[:TRANSACTED]->(w)
        WITH w, fan_out, total_sent_txs, COUNT(sender) AS fan_in

        // Bidirectional partners (wash trading signal)
        OPTIONAL MATCH (w)-[:TRANSACTED]->(partner:Wallet)-[:TRANSACTED]->(w)
        WITH w, fan_out, fan_in, total_sent_txs,
             COUNT(partner) AS circular_partners

        // Velocity
        WITH w, fan_out, fan_in, total_sent_txs, circular_partners,
             CASE WHEN w.last_seen > w.first_seen AND total_sent_txs > 1
                  THEN toFloat(total_sent_txs) / ((w.last_seen - w.first_seen) / 3600.0)
                  ELSE 0.0 END AS txs_per_hour

        RETURN w.address AS address,
               fan_out, fan_in, circular_partners,
               total_sent_txs, txs_per_hour,
               w.labels AS labels
        """,
        {"address": address},
    )

    if not result:
        return WalletRisk(
            address=address, risk_score=0.0, flags=[], details="Wallet not found"
        )

    r = result[0]
    flags = []
    score = 0.0

    cp = r["circular_partners"] or 0
    if cp > 0:
        flags.append(f"circular_flows:{cp}")
        score += min(cp * 0.15, 0.4)

    fo = r["fan_out"] or 0
    if fo > 20:
        flags.append(f"high_fan_out:{fo}")
        score += 0.2

    fi = r["fan_in"] or 0
    if fi > 50:
        flags.append(f"high_fan_in:{fi}")
        score += 0.1

    vel = r["txs_per_hour"] or 0
    if vel > 60:
        flags.append(f"high_velocity:{vel:.0f}/hr")
        score += 0.2

    score = min(score, 1.0)

    severity = "clean"
    if score >= 0.7:
        severity = "high risk"
    elif score >= 0.4:
        severity = "medium risk"
    elif score >= 0.1:
        severity = "low risk"

    return WalletRisk(
        address=address,
        risk_score=round(score, 2),
        flags=flags,
        details=severity,
    )
