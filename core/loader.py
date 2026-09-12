"""数值加载与建队。

所有数值来自 data/*.json，改平衡不需要动代码。
磁盘 IO 与缓存统一收口在 core.dataio（唯一入口）；本模块负责把原始 JSON
加工成游戏运行时需要的类型化结构（UnitTemplate / 队伍 Unit）。
"""

from __future__ import annotations

from . import traits as trait_mod
from .dataio import DATA_DIR, load_json as _load_json  # noqa: F401  DATA_DIR 保留兼容导出
from .items import item_effect, piece_equip_stats
from .models import AbilityDef, Unit, UnitTemplate
from .stats import compute_stats

_units_cache: dict[str, UnitTemplate] | None = None


def load_traits() -> dict:
    return _load_json("traits.json")


def load_units() -> dict[str, UnitTemplate]:
    global _units_cache
    if _units_cache is not None:
        return _units_cache
    raw = _load_json("units.json")
    templates: dict[str, UnitTemplate] = {}
    for item in raw:
        ab = item.get("ability", {})
        templates[item["id"]] = UnitTemplate(
            id=item["id"],
            name=item["name"],
            cost=item.get("cost", 1),
            traits=tuple(item.get("traits", ())),
            hp=float(item["hp"]),
            ad=float(item["ad"]),
            attack_speed=float(item.get("attack_speed", 0.7)),
            attack_range=int(item.get("attack_range", 1)),
            armor=int(item.get("armor", 20)),
            magic_resist=int(item.get("magic_resist", 20)),
            ap=float(item.get("ap", 0)),
            move_speed=float(item.get("move_speed", 1.1)),
            max_mana=float(item.get("max_mana", 60)),
            starting_mana=float(item.get("starting_mana", 0)),
            crit_chance=float(item.get("crit_chance", 0.05)),
            ability=AbilityDef(
                type=ab.get("type", "nuke"),
                name=ab.get("name", "重击"),
                value=float(ab.get("value", 0)),
                ratio=float(ab.get("ratio", 0)),
                radius=int(ab.get("radius", 1)),
            ),
            slots=int(item.get("slots", 1) or 1),
            trait_extra=dict(item.get("trait_extra", {})),
        )
    _units_cache = templates
    return templates


def build_team(placements: list[dict], team: str) -> list[Unit]:
    """根据布阵创建一支队伍，并应用羁绊加成。

    placements 形如 [{"id": "s18_ornn", "star": 1, "pos": [col, row]}, ...]
    """
    templates = load_units()
    traits_data = load_traits()

    units: list[Unit] = []
    for p in placements:
        tpl = templates[p["id"]]
        star = int(p.get("star", 1))
        col, row = p.get("pos", [0, 0])
        equip = p.get("equip", [])
        effects = frozenset(item_effect(it.item_id) for it in equip if item_effect(it.item_id) != "none")
        units.append(
            Unit(
                tid=tpl.id,
                name=tpl.name,
                team=team,
                star=star,
                traits=tpl.traits,
                max_hp=tpl.hp,
                hp=tpl.hp,
                ad=tpl.ad,
                attack_speed=tpl.attack_speed,
                attack_range=tpl.attack_range,
                move_speed=tpl.move_speed,
                max_mana=tpl.max_mana,
                mana=tpl.starting_mana,
                ability=tpl.ability,
                effects=effects,
                equip_ids=tuple(it.item_id for it in equip),
                x=float(col),
                y=float(row),
            )
        )

    # 羁绊 + 装备加成：先统计、再统一应用
    counts = trait_mod.count_traits(units)
    mods_by_trait = trait_mod.trait_mods_by_trait(counts, traits_data)
    for u, p in zip(units, placements):
        tpl = templates[p["id"]]
        star = int(p.get("star", 1))
        mods = trait_mod.mods_for_unit(u, mods_by_trait)
        equip = p.get("equip", [])
        item_mods = piece_equip_stats(equip)
        s = compute_stats(tpl, star, mods, item_mods)
        u.max_hp = s["max_hp"]
        u.hp = s["max_hp"]
        u.ad = s["ad"]
        u.ap = s["ap"]
        u.armor = s["armor"]
        u.magic_resist = s["magic_resist"]
        u.attack_speed = s["attack_speed"]
        u.crit_chance = s["crit_chance"]
        u.damage_amp = s["damage_amp"]
        # 星级白板基础值（不含羁绊/装备）：供羊刀/三相/帽子等“特效吃基础”的装备引用
        u.base_max_hp = s["base_max_hp"]
        u.base_ad = s["base_ad"]
        u.base_ap = s["base_ap"]
        u.base_attack_speed = s["base_attack_speed"]
        # 眼泪系装备：加法加蓝量（之前误写成减法，导致扣蓝），
        # 并让棋子开局即带这部分蓝，使其更快放技能（与 TFT 泪水系一致）。
        mana_flat = item_mods.get("mana_flat", 0.0)
        u.max_mana = max(0.0, tpl.max_mana + mana_flat)
        u.mana = min(u.mana + mana_flat, u.max_mana)
        # 装备特效统一由 combat 层消费：吸血/法吸在普攻/技能入口各自结算
    return units
