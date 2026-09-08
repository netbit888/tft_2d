"""装备系统：基础装备、合成、属性加成与掉落。

所有数据来自 data/items.json，改数值不用动代码。
一件高级装备 = 两件基础装备合成；基础装备也可直接装备（只有基础属性）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

MAX_ITEMS_PER_PIECE = 3
ITEM_BENCH_CAP = 12  # 玩家装备栏上限

# 掉落节奏：从第 2 回合起，每回合掉落概率
DROP_CHANCE = 0.6
FIRST_DROP_ROUND = 2

_cache: dict | None = None


def load_items() -> dict:
    global _cache
    if _cache is None:
        with open(DATA_DIR / "items.json", "r", encoding="utf-8") as f:
            _cache = json.load(f)
    return _cache


def is_base_item(item_id: str) -> bool:
    return item_id in load_items()["base"]


def base_item_ids() -> list[str]:
    return list(load_items()["base"].keys())


def combine_key(a: str, b: str) -> str | None:
    """两个基础装备 id -> 合成高级装备 id；不可合成（或含高级件）返回 None。"""
    if not (is_base_item(a) and is_base_item(b)):
        return None
    # 合成公式与顺序无关
    key1 = f"{a}+{b}"
    key2 = f"{b}+{a}"
    combine = load_items()["combine"]
    if key1 in combine:
        return key1
    if key2 in combine:
        return key2
    return None


def combined_item_id(a: str, b: str) -> str | None:
    """返回合成后的高级装备 id（如 "sword+bow"），不可合成返回 None。"""
    return combine_key(a, b)


def item_name(item_id: str) -> str:
    items = load_items()
    if item_id in items["base"]:
        return items["base"][item_id]["name"]
    if item_id in items["combine"]:
        return items["combine"][item_id]["name"]
    return item_id


def item_stats(item_id: str) -> dict:
    """装备的属性加成（直接作用于棋子最终属性）。"""
    items = load_items()
    if item_id in items["base"]:
        return items["base"][item_id]["stats"]
    if item_id in items["combine"]:
        return items["combine"][item_id]["stats"]
    return {}


def item_effect(item_id: str) -> str:
    """特殊效果标识（combat 层消费）。"""
    items = load_items()
    if item_id in items["combine"]:
        return items["combine"][item_id].get("effect", "none")
    return "none"


@dataclass
class ItemInstance:
    """玩家持有的一件装备。

    item_id 可以是基础装备 id，也可以是合成公式 key（如 "sword+bow"）。
    高级装备记录组成它的两个基础件，卖出时拆回基础件。
    """

    item_id: str
    components: tuple[str, str] | None = None  # 高级装备的两件基础件


@dataclass
class ItemBench:
    """玩家的装备栏：存放待装备的基础/高级装备。"""

    items: list[ItemInstance] = field(default_factory=list)

    def add(self, item_id: str) -> bool:
        if len(self.items) >= ITEM_BENCH_CAP:
            return False
        comp = (item_id.split("+")[0], item_id.split("+")[1]) if "+" in item_id else None
        self.items.append(ItemInstance(item_id, components=comp))
        return True

    def remove(self, item: ItemInstance) -> bool:
        if item in self.items:
            self.items.remove(item)
            return True
        return False


def piece_equip_stats(equip: list[ItemInstance]) -> dict:
    """汇总一件棋子身上所有装备的属性加成。"""
    total: dict[str, float] = {}
    for it in equip:
        for k, v in item_stats(it.item_id).items():
            total[k] = total.get(k, 0.0) + v
    return total


def drop_item(rng) -> str | None:
    """按概率掉落一件随机基础装备；不掉落返回 None。"""
    if rng.random() > DROP_CHANCE:
        return None
    return rng.choice(base_item_ids())
