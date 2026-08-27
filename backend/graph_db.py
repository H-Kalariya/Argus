"""
Medusa Identity Graph — Tiered Network Fraud Detection

Design (per master plan Part 3):
- HARD links: deterministic same-entity signals (phone, email, PAN/Aadhaar,
  bank account, card fingerprint).
- SOFT links: behavioral / probabilistic signals that accumulate evidence
  (device fingerprint, IP, failed-liveness events, geolocation).
- Tiered velocity windows catch fraud operating at different speeds:
    Tier 1 (bot-speed):   same device/IP + 3+ signals in 15 min  -> BLOCK
    Tier 2 (human-speed): same device/IP + 2+ accounts in 24h    -> STEP-UP
    Tier 3 (long-game):   same fingerprint/IP across 3-7 days    -> FLAG/REVIEW

Storage: SQLite (zero-infra, demoable). NetworkX is built on top for graph
queries and cluster/community views. Schema is intentionally simple so it can
be lifted into Neo4j/TigerGraph for production scale without a rewrite.
"""

import sqlite3
import os
import time
from datetime import datetime, timezone
import networkx as nx

DB_PATH = os.path.join(os.path.dirname(__file__), "medusa_graph.db")

HARD_LINK_TYPES = {"phone", "email", "pan", "aadhaar", "bank_account", "card_fingerprint"}
SOFT_LINK_TYPES = {"device_fingerprint", "ip_address", "failed_liveness", "geolocation"}

# Weight per soft-link type, used to accumulate a soft-link risk score.
SOFT_WEIGHTS = {
    "device_fingerprint": 1.0,
    "ip_address": 0.6,
    "failed_liveness": 1.5,
    "geolocation": 0.4,
}


def _now() -> float:
    return time.time()


class MedusaIdentityGraph:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        cur = self.conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                user_id TEXT PRIMARY KEY,
                label TEXT,
                created_at REAL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                signal_type TEXT NOT NULL,      -- e.g. device_fingerprint, email
                signal_value TEXT NOT NULL,     -- the actual value
                link_class TEXT NOT NULL,       -- 'hard' or 'soft'
                weight REAL DEFAULT 1.0,
                created_at REAL NOT NULL
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_edges_signal ON edges(signal_type, signal_value)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_edges_user ON edges(user_id)")
        self.conn.commit()

    # ---- Mutations ----
    def add_account(self, user_id: str, label: str = "", created_at: float = None):
        self.conn.execute(
            "INSERT OR IGNORE INTO accounts (user_id, label, created_at) VALUES (?, ?, ?)",
            (user_id, label, created_at if created_at is not None else _now()),
        )
        self.conn.commit()

    def add_signal(
        self,
        user_id: str,
        signal_type: str,
        signal_value: str,
        link_class: str = None,
        weight: float = None,
        created_at: float = None,
    ):
        """Attach a signal (hard or soft link) to an account."""
        if link_class is None:
            link_class = "hard" if signal_type in HARD_LINK_TYPES else "soft"
        if weight is None:
            weight = SOFT_WEIGHTS.get(signal_type, 1.0)
        self.conn.execute(
            """INSERT INTO edges (user_id, signal_type, signal_value, link_class, weight, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, signal_type, signal_value, link_class, weight,
             created_at if created_at is not None else _now()),
        )
        self.conn.commit()

    # ---- Queries ----
    def accounts_sharing_signal(self, signal_type: str, signal_value: str):
        rows = self.conn.execute(
            "SELECT DISTINCT user_id FROM edges WHERE signal_type=? AND signal_value=?",
            (signal_type, signal_value),
        ).fetchall()
        return [r["user_id"] for r in rows]

    def check_velocity_tiers(self, signal_type: str, signal_value: str):
        """Evaluate the three velocity tiers for accounts sharing a given signal."""
        now = _now()
        rows = self.conn.execute(
            """SELECT user_id, created_at FROM edges
               WHERE signal_type=? AND signal_value=?""",
            (signal_type, signal_value),
        ).fetchall()

        # Distinct accounts and their earliest association time with this signal.
        first_seen = {}
        for r in rows:
            uid = r["user_id"]
            first_seen[uid] = min(first_seen.get(uid, r["created_at"]), r["created_at"])

        def count_within(seconds):
            return sum(1 for t in first_seen.values() if now - t <= seconds)

        n_15min = count_within(15 * 60)
        n_24h = count_within(24 * 3600)
        n_7d = count_within(7 * 24 * 3600)

        # Total number of signal-association events (not distinct accounts) in 15 min,
        # used for the "3+ signals in 15 min" bot-speed test.
        events_15min = sum(1 for r in rows if now - r["created_at"] <= 15 * 60)

        tier1 = events_15min >= 3 and n_15min >= 1
        tier2 = n_24h >= 2
        # Long-game: accounts spread across days (not all in the last 24h) but within a week.
        span_days = 0.0
        if first_seen:
            span_days = (max(first_seen.values()) - min(first_seen.values())) / (24 * 3600)
        tier3 = n_7d >= 3 and span_days >= 3 and not tier1

        return {
            "tier1_triggered": tier1,
            "tier2_triggered": tier2,
            "tier3_triggered": tier3,
            "accounts_15min": n_15min,
            "accounts_24h": n_24h,
            "accounts_7d": n_7d,
            "events_15min": events_15min,
            "span_days": round(span_days, 2),
        }

    def get_soft_link_score(self, signal_type: str, signal_value: str) -> float:
        """Accumulated soft-link evidence score for a signal cluster."""
        rows = self.conn.execute(
            """SELECT weight FROM edges
               WHERE signal_value=? AND signal_type=? AND link_class='soft'""",
            (signal_value, signal_type),
        ).fetchall()
        return round(sum(r["weight"] for r in rows), 2)

    # ---- Graph view ----
    def build_networkx(self) -> nx.Graph:
        """Build a bipartite-ish graph: account nodes + signal nodes, edges between."""
        g = nx.Graph()
        accts = self.conn.execute("SELECT user_id, label FROM accounts").fetchall()
        for a in accts:
            g.add_node(f"acct:{a['user_id']}", kind="account", label=a["label"], user_id=a["user_id"])

        edges = self.conn.execute("SELECT * FROM edges").fetchall()
        for e in edges:
            sig_node = f"sig:{e['signal_type']}:{e['signal_value']}"
            if sig_node not in g:
                g.add_node(sig_node, kind="signal", signal_type=e["signal_type"], signal_value=e["signal_value"], link_class=e["link_class"])
            g.add_edge(f"acct:{e['user_id']}", sig_node, link_class=e["link_class"], signal_type=e["signal_type"])
        return g

    def clusters(self):
        """Return connected components that contain more than one account (potential rings)."""
        g = self.build_networkx()
        out = []
        for comp in nx.connected_components(g):
            acct_nodes = [n for n in comp if n.startswith("acct:")]
            if len(acct_nodes) >= 2:
                out.append(sorted(comp))
        return out

    def reset(self):
        self.conn.execute("DELETE FROM edges")
        self.conn.execute("DELETE FROM accounts")
        self.conn.commit()

    def close(self):
        self.conn.close()


def assess_transaction(user_id, signal_type, signal_value, liveness_result, medusa_artifact_score, graph: MedusaIdentityGraph):
    """Risk decision engine (master plan Part 3)."""
    if liveness_result == "FAILED":
        graph.add_signal(user_id, "failed_liveness", signal_value, "soft", SOFT_WEIGHTS["failed_liveness"])

    tiers = graph.check_velocity_tiers(signal_type, signal_value)
    soft_score = graph.get_soft_link_score(signal_type, signal_value)
    total_risk = soft_score * 0.3 + medusa_artifact_score * 0.7

    if tiers["tier1_triggered"] or medusa_artifact_score > 5.0:
        decision = {"action": "BLOCK", "reason": "Bot-speed attack or high artifact score"}
    elif tiers["tier2_triggered"] or total_risk > 3.0:
        decision = {"action": "STEP_UP_CHALLENGE", "reason": "Suspicious pattern"}
    elif tiers["tier3_triggered"]:
        decision = {"action": "FLAG_FOR_REVIEW", "reason": "Long-term mule network pattern"}
    else:
        decision = {"action": "APPROVE", "reason": "Low risk"}

    decision.update({
        "tiers": tiers,
        "soft_score": soft_score,
        "medusa_artifact_score": medusa_artifact_score,
        "total_risk": round(total_risk, 2),
    })
    return decision
