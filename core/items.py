"""装备系统：基础装备、合成、属性加成与掉落。

所有数据来自 data/items.json，改数值不用动代码。
一件高级装备 = 两件基础装备合成；基础装备也可直接装备（只有基础属性）。
"""

from __future__ import annotations

from dataclasses import dataclass

from .dataio import load_json as _load_json

MAX_ITEMS_PER_PIECE = 3  # 单个棋子最多携带装备数
# 玩家装备栏背包不设容量上限：GUI 用"每页 3x4 + 滚轮"浏览全部装备。

# 掉落节奏：从第 2 回合起，每回合掉落概率
DROP_CHANCE = 0.6
FIRST_DROP_ROUND = 2

# 特殊工具装备：只能通过 GUI 的成装自选台获得，不进属性/战斗结算。
# 金制拆卸器：拖到棋子身上卸下其全部装备回装备栏，道具本身不消耗（不限次数）。
SPECIAL_ITEMS = {
    "gold_remover": "金制拆卸器",
}
GOLD_REMOVER = "gold_remover"


def is_special_item(item_id: str) -> bool:
    """是否特殊工具装备（金制拆卸器等），不是基础件也不是可合成的成装。"""
    return item_id in SPECIAL_ITEMS


def special_item_ids() -> list[str]:
    return list(SPECIAL_ITEMS.keys())

def load_items() -> dict:
    """读取 items.json（含 base / combine 两表），由 core.dataio 统一缓存。"""
    return _load_json("items.json")


def is_base_item(item_id: str) -> bool:
    return item_id in load_items()["base"]


def is_artifact_item(item_id: str) -> bool:
    """是否神器（守护天使/三相/九头蛇/冰心等具名强力件，成装自选台单独成页，不进合成）。"""
    return item_id in load_items()["artifacts"]


def base_item_ids() -> list[str]:
    return list(load_items()["base"].keys())


def artifact_item_ids() -> list[str]:
    return list(load_items()["artifacts"].keys())


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


def first_combine_with(item_id: str, others) -> str | None:
    """在一批装备中找第一件能与 item_id 合成的基础件，返回其 id。

    顺序敏感：把"身上/栏里的装备顺序"传进来即可获得确定性的首选合成对象；
    item_id 非基础件或找不到可合成目标时返回 None。
    """
    if not is_base_item(item_id):
        return None
    for oid in others:
        if combine_key(item_id, oid):
            return oid
    return None


def item_name(item_id: str) -> str:
    items = load_items()
    if item_id in items["base"]:
        return items["base"][item_id]["name"]
    if item_id in items["combine"]:
        return items["combine"][item_id]["name"]
    if item_id in items["artifacts"]:
        return items["artifacts"][item_id]["name"]
    special = SPECIAL_ITEMS.get(item_id)
    if special is not None:
        return special
    return item_id


def item_stats(item_id: str) -> dict:
    """装备的属性加成（直接作用于棋子最终属性）。"""
    items = load_items()
    if item_id in items["base"]:
        return items["base"][item_id]["stats"]
    if item_id in items["combine"]:
        return items["combine"][item_id]["stats"]
    if item_id in items["artifacts"]:
        return items["artifacts"][item_id]["stats"]
    return {}


def item_effect(item_id: str) -> str:
    """特殊效果标识（combat 层消费）。"""
    items = load_items()
    if item_id in items["combine"]:
        return items["combine"][item_id].get("effect", "none")
    if item_id in items["artifacts"]:
        return items["artifacts"][item_id].get("effect", "none")
    return "none"


def item_desc(item_id: str) -> str:
    """装备的官方特效原文（来自官方 equip.js，供详情展示；无则为空串）。"""
    items = load_items()
    if item_id in items["combine"]:
        return items["combine"][item_id].get("desc", "")
    if item_id in items["artifacts"]:
        return items["artifacts"][item_id].get("desc", "")
    return ""


@dataclass
class ItemInstance:
    """玩家持有的一件装备。

    item_id 可以是基础装备 id，也可以是合成公式 key（如 "sword+bow"）。
    高级装备自动记录组成它的两件基础件（components 自描述，供配方展示与
    未来的拆卸功能使用；卖出棋子时装备一律整件回栏、不再拆散）。
    """

    item_id: str
    components: tuple[str, str] | None = None  # 高级装备的两件基础件

    def __post_init__(self) -> None:
        if self.components is None and "+" in self.item_id:
            self.components = tuple(self.item_id.split("+", 1))


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
