"""属性与伤害计算。

所有数值公式集中在此，方便调平衡时只改一处。
"""

from __future__ import annotations

from .models import STAR_MULTIPLIER, Unit, UnitTemplate
from .traits import TraitMods


def compute_stats(
    tpl: UnitTemplate, star: int, mods: TraitMods, item_stats: dict | None = None
) -> dict:
    """棋子最终属性 = 模板 * 星级倍率 * (1 + 百分比加成) + 固定加成 + 装备加成。

    攻速、护甲、魔抗不随星级成长（与金铲铲一致）。
    """
    it = item_stats or {}
    mult = STAR_MULTIPLIER.get(star, 1.0)
    max_hp = tpl.hp * mult * (1.0 + mods.hp_pct) + mods.hp_flat + it.get("hp_flat", 0)
    ad = tpl.ad * mult * (1.0 + mods.ad_pct) + mods.ad_flat + it.get("ad_flat", 0)
    ap = tpl.ap + mods.ap_flat + it.get("ap_flat", 0)
    return {
        "max_hp": max_hp,
        "ad": ad,
        "ap": ap,
        "armor": tpl.armor + mods.armor_flat + it.get("armor_flat", 0),
        "magic_resist": tpl.magic_resist + mods.mr_flat + it.get("mr_flat", 0),
        "attack_speed": tpl.attack_speed
        * (1.0 + mods.attack_speed_pct + it.get("attack_speed_pct", 0)),
        "crit_chance": min(1.0, tpl.crit_chance + mods.crit_flat + it.get("crit_flat", 0)),
        "damage_amp": mods.damage_amp,
    }


def mitigate(raw: float, resist: float) -> float:
    """护甲/魔抗减伤：实际伤害 = 原始伤害 * 100 / (100 + 抗性)。"""
    return raw * 100.0 / (100.0 + max(resist, 0.0))


def ability_power(u: Unit) -> float:
    """技能威力 = 基础值 + 法强 * 系数。"""
    return u.ability.value + u.ap * u.ability.ratio


def snapshot(u: Unit) -> dict:
    """给渲染层用的轻量状态快照。"""
    return {
        "uid": u.uid,
        "name": u.name,
        "team": u.team,
        "x": u.x,
        "y": u.y,
        "hp": u.hp,
        "max_hp": u.max_hp,
        "mana": u.mana,
        "max_mana": u.max_mana,
        "alive": u.alive,
        "star": u.star,
    }
