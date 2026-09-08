"""种子化随机。

抽卡与战斗必须使用相互独立的随机流：否则一次战斗重算会污染后续抽卡序列，
导致回放、复盘、服务器校验都对不上。
"""

from __future__ import annotations

import random
from typing import Sequence, TypeVar

T = TypeVar("T")


class Rng:
    """对 random.Random 的薄封装，便于将来替换实现或记录调用序列。"""

    def __init__(self, seed: int | None = None) -> None:
        self.seed = seed
        self._r = random.Random(seed)

    def random(self) -> float:
        return self._r.random()

    def randint(self, a: int, b: int) -> int:
        return self._r.randint(a, b)

    def choice(self, seq: Sequence[T]) -> T:
        return self._r.choice(seq)

    def shuffle(self, seq: list) -> None:
        self._r.shuffle(seq)

    def weighted_choice(self, items: Sequence[T], weights: Sequence[float]) -> T:
        return self._r.choices(list(items), weights=list(weights), k=1)[0]
