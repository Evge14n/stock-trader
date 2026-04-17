from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

import structlog

from agents.python import paper_broker

log = structlog.get_logger(__name__)

_VOTE_PATTERN = re.compile(r"([a-z_][a-z0-9_]*):(buy|sell)@(\d+\.\d+)")


@dataclass
class VoterRecord:
    voter: str
    wins: int
    losses: int
    total_pnl: float

    @property
    def total(self) -> int:
        return self.wins + self.losses

    @property
    def win_rate(self) -> float:
        return self.wins / self.total if self.total else 0.0

    @property
    def avg_pnl(self) -> float:
        return self.total_pnl / self.total if self.total else 0.0


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS voter_stats (
            voter TEXT PRIMARY KEY,
            wins INTEGER NOT NULL DEFAULT 0,
            losses INTEGER NOT NULL DEFAULT 0,
            total_pnl REAL NOT NULL DEFAULT 0,
            last_updated TEXT
        )
    """)


def parse_voters(reasoning: str) -> list[tuple[str, str]]:
    if not reasoning:
        return []
    matches = _VOTE_PATTERN.findall(reasoning)
    return [(m[0], m[1]) for m in matches]


def record_trade_outcome(reasoning: str, pnl: float) -> int:
    voters = parse_voters(reasoning)
    if not voters:
        return 0

    from datetime import datetime

    now = datetime.now().isoformat()
    try:
        with sqlite3.connect(paper_broker._db_path()) as conn:
            conn.row_factory = sqlite3.Row
            _ensure_table(conn)
            for voter, _action in voters:
                existing = conn.execute(
                    "SELECT wins, losses, total_pnl FROM voter_stats WHERE voter = ?",
                    (voter,),
                ).fetchone()
                if existing:
                    wins = existing["wins"] + (1 if pnl > 0 else 0)
                    losses = existing["losses"] + (1 if pnl <= 0 else 0)
                    total = existing["total_pnl"] + pnl
                    conn.execute(
                        "UPDATE voter_stats SET wins = ?, losses = ?, total_pnl = ?, last_updated = ? WHERE voter = ?",
                        (wins, losses, total, now, voter),
                    )
                else:
                    conn.execute(
                        "INSERT INTO voter_stats (voter, wins, losses, total_pnl, last_updated) VALUES (?,?,?,?,?)",
                        (
                            voter,
                            1 if pnl > 0 else 0,
                            1 if pnl <= 0 else 0,
                            pnl,
                            now,
                        ),
                    )
            conn.commit()
    except Exception as e:
        log.warning("voter_stats_record_failed", error=str(e))
        return 0
    return len(voters)


def get_all_stats() -> list[VoterRecord]:
    try:
        with sqlite3.connect(paper_broker._db_path()) as conn:
            conn.row_factory = sqlite3.Row
            _ensure_table(conn)
            rows = conn.execute(
                "SELECT voter, wins, losses, total_pnl FROM voter_stats ORDER BY (wins + losses) DESC"
            ).fetchall()
    except Exception:
        return []
    return [VoterRecord(voter=r["voter"], wins=r["wins"], losses=r["losses"], total_pnl=r["total_pnl"]) for r in rows]


def get_weight(voter: str, min_trades: int = 5) -> float:
    try:
        with sqlite3.connect(paper_broker._db_path()) as conn:
            conn.row_factory = sqlite3.Row
            _ensure_table(conn)
            row = conn.execute(
                "SELECT wins, losses FROM voter_stats WHERE voter = ?",
                (voter,),
            ).fetchone()
    except Exception:
        return 1.0

    if not row:
        return 1.0
    total = row["wins"] + row["losses"]
    if total < min_trades:
        return 1.0

    win_rate = row["wins"] / total
    if win_rate >= 0.6:
        return 1.15
    if win_rate >= 0.5:
        return 1.05
    if win_rate >= 0.4:
        return 0.9
    return 0.75


def apply_weights_to_votes(votes: list) -> list:
    for v in votes:
        w = get_weight(v.source)
        v.confidence = min(0.95, v.confidence * w)
    return votes


def reset_all() -> None:
    try:
        with sqlite3.connect(paper_broker._db_path()) as conn:
            _ensure_table(conn)
            conn.execute("DELETE FROM voter_stats")
            conn.commit()
    except Exception:
        pass
