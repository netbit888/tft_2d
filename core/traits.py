"""羁绊计算。

规则（M1 简化版）：
- 同名棋子只计一次（与金铲铲一致）；
- 取满足条件的最高档位；
- 加成只作用于拥有该羁绊的棋子。
"""

from __future__ import annotations

from dataclasses import dataclass, fields

from .models import Unit


@dataclass
class TraitMods:
    """一组属性加成，多个羁绊之间做加法叠加。"""

    hp_flat: float = 0.0
    hp_pct: float = 0.0
    ad_flat: float = 0.0
    ad_pct: float = 0.0
    ap_flat: float = 0.0
    armor_flat: float = 0.0
    mr_flat: float = 0.0
    attack_speed_pct: float = 0.0
    crit_flat: float = 0.0
    damage_amp: float = 0.0

    def __add__(self, other: "TraitMods") -> "TraitMods":
        return TraitMods(**{f.name: getattr(self, f.name) + getattr(other, f.name) for f in fields(self)})


EMPTY = TraitMods()


def count_traits_from_tids(tids: list[str], templates: dict) -> dict[str, int]:
    """直接从棋子 id 列表统计羁绊（同名只计一次），给 AI 评估和 UI 展示用。"""
    seen: set[str] = set()
    counts: dict[str, int] = {}
    for tid in tids:
        if tid in seen:
            continue
        seen.add(tid)
        tpl = templates.get(tid)
        if tpl is None:
            continue
        for t in tpl.traits:
            counts[t] = counts.get(t, 0) + 1
    return counts


def count_traits(units: list[Unit]) -> dict[str, int]:
    """统计场上羁绊数量，同名棋子只计一次。"""
    seen: set[str] = set()
    counts: dict[str, int] = {}
    for u in units:
        if u.tid in seen:
            continue
        seen.add(u.tid)
        for t in u.traits:
            counts[t] = counts.get(t, 0) + 1
    return counts


def active_tier(trait_def: dict, count: int) -> dict | None:
    """返回满足条件的最高档位定义。"""
    best = None
    for tier in trait_def.get("tiers", []):
        if count >= tier["count"]:
            if best is None or tier["count"] > best["count"]:
                best = tier
    return best


def trait_mods_by_trait(counts: dict[str, int], traits_data: dict) -> dict[str, TraitMods]:
    """把羁绊数量换算成每个羁绊生效的加成。"""
    result: dict[str, TraitMods] = {}
    for trait_id, count in counts.items():
        trait_def = traits_data.get(trait_id)
        if trait_def is None:
            continue
        tier = active_tier(trait_def, count)
        if tier is None:
            continue
        result[trait_id] = TraitMods(**tier.get("mods", {}))
    return result


def mods_for_unit(unit: Unit, mods_by_trait: dict[str, TraitMods]) -> TraitMods:
    """汇总某个棋子吃到的全部羁绊加成。"""
    total = TraitMods()
    for t in unit.traits:
        total = total + mods_by_trait.get(t, EMPTY)
    return total


def describe(counts: dict[str, int], traits_data: dict) -> list[str]:
    """生成羁绊面板文案，例如「战士 2（+12 攻击力）」。"""
    lines = []
    for trait_id, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        trait_def = traits_data.get(trait_id)
        if trait_def is None:
            continue
        tier = active_tier(trait_def, count)
        if tier is None:
            continue
        key_map = {
            "ad_flat": "攻击力",
            "ad_pct": "攻击力",
            "ap_flat": "法强",
            "armor_flat": "护甲",
            "mr_flat": "魔抗",
            "attack_speed_pct": "攻速",
            "crit_flat": "暴击率",
            "hp_flat": "生命值",
            "hp_pct": "生命值",
            "damage_amp": "伤害",
        }
        parts = []
        for k, v in tier.get("mods", {}).items():
            label = key_map.get(k, k)
            value = f"{v * 100:.0f}%" if k.endswith("_pct") else f"{v:g}"
            parts.append(f"+{value} {label}")
        lines.append(f"{trait_def['name']} {count}（{'，'.join(parts)}）")
    return lines
