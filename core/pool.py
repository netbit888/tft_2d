"""公共卡池：双方共享同一份棋子库存。

意义在于"抢棋子"——你拿走了，对面就刷不到了，这是自走棋运营博弈的核心之一。
卡池数量按费用配置（data/pool.json），改数值不用动代码。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .loader import DATA_DIR, load_units

DEFAULT_COPIES = {"1": 12, "2": 8, "3": 6}


def load_pool_config() -> dict:
    path = DATA_DIR / "pool.json"
    if not path.exists():
        return {"copies_by_cost": DEFAULT_COPIES}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@dataclass
class Pool:
    """每种棋子的剩余数量。"""

    remaining: dict[str, int] = field(default_factory=dict)
    capacity: dict[str, int] = field(default_factory=dict)

    @classmethod
    def create(cls, copies_by_cost: dict | None = None) -> "Pool":
        cfg = copies_by_cost or load_pool_config().get("copies_by_cost", DEFAULT_COPIES)
        remaining = {
            tid: int(cfg.get(str(tpl.cost), 6)) for tid, tpl in load_units().items()
        }
        return cls(remaining=remaining, capacity=dict(remaining))

    def count(self, tid: str) -> int:
        return self.remaining.get(tid, 0)

    def take(self, tid: str, n: int = 1) -> bool:
        """取走 n 张，库存不足时返回 False（不扣除）。"""
        if self.remaining.get(tid, 0) < n:
            return False
        self.remaining[tid] -= n
        return True

    def give(self, tid: str, n: int = 1) -> None:
        """归还 n 张，不会超过初始总量。"""
        cap = self.capacity.get(tid, 0)
        self.remaining[tid] = min(cap, self.remaining.get(tid, 0) + n)

    def available(self) -> list[str]:
        """还有剩余的棋子 id 列表。"""
        return [tid for tid, n in self.remaining.items() if n > 0]

    def total_left(self) -> int:
        return sum(self.remaining.values())

    def total_capacity(self) -> int:
        return sum(self.capacity.values())
