"""属性与伤害计算。

所有数值公式集中在此，方便调平衡时只改一处。
"""

from __future__ import annotations

from .models import AS_CAP, AS_STAR_MULTIPLIER, STAR_MULTIPLIER, Unit, UnitTemplate
from .traits import TraitMods


def compute_stats(
    tpl: UnitTemplate, star: int, mods: TraitMods, item_stats: dict | None = None
) -> dict:
    """棋子最终属性与星级白板基础值。

    公式（面板 = 基础 × (1 + 百分比加成) + 固定加成 + 装备加成）：
    - 星级白板基础值：生命/攻击 × STAR_MULTIPLIER，攻速 × AS_STAR_MULTIPLIER
      （1.0/1.1/1.25），法强/护甲/魔抗不随星级成长；
    - 百分比加成（羁绊/装备）只作用在基础值上，不与固定加成互相放大；
    - 返回值含 base_max_hp/base_ad/base_ap/base_attack_speed（不含羁绊与装备的
      星级白板），供“特效吃基础”的装备（羊刀/三相/帽子）引用。
    """
    it = item_stats or {}
    mult = STAR_MULTIPLIER.get(star, 1.0)
    as_mult = AS_STAR_MULTIPLIER.get(star, 1.0)

    base_max_hp = tpl.hp * mult
    base_ad = tpl.ad * mult
    base_ap = tpl.ap  # 法强不随星级成长（与现行为一致）
    base_attack_speed = tpl.attack_speed * as_mult

    max_hp = base_max_hp * (1.0 + mods.hp_pct) + mods.hp_flat + it.get("hp_flat", 0)
    ad = base_ad * (1.0 + mods.ad_pct) + mods.ad_flat + it.get("ad_flat", 0)
    ap = base_ap + mods.ap_flat + it.get("ap_flat", 0)
    return {
        "max_hp": max_hp,
        "ad": ad,
        "ap": ap,
        "armor": tpl.armor + mods.armor_flat + it.get("armor_flat", 0),
        "magic_resist": tpl.magic_resist + mods.mr_flat + it.get("mr_flat", 0),
        # 攻速%加成与基础攻速相乘后封顶全局上限
        "attack_speed": min(
            base_attack_speed
            * (1.0 + mods.attack_speed_pct + it.get("attack_speed_pct", 0)),
            AS_CAP,
        ),
        "crit_chance": min(1.0, tpl.crit_chance + mods.crit_flat + it.get("crit_flat", 0)),
        "damage_amp": mods.damage_amp,
        "base_max_hp": base_max_hp,
        "base_ad": base_ad,
        "base_ap": base_ap,
        "base_attack_speed": base_attack_speed,
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
