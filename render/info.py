"""信息层：悬停详情 tooltip 的文案与绘制。

给此前"只有名字没有内涵"的 UI 补上决策信息：
- 商店卡 / 棋盘 / 备战席的棋子：属性、主动技能、蓝量、当前羁绊/装备下的实际数值；
- 装备：属性、特效、可用配方（合成提示的信息底座）；
- 左侧羁绊行的悬停：羁绊说明与各档位阈值。

记录格式统一为 (text, size, color) 三元组，由 draw_tip 一次性渲染成
圆角深色面板；文案全部来自 data/*.json，不复制数值。
"""

from __future__ import annotations

import pygame

from core.combat import effective_attack_speed
from core.items import (
    combine_key,
    is_special_item,
    item_effect,
    item_name,
    item_stats,
    piece_equip_stats,
)
from core.loader import load_traits, load_units
from core.models import MANA_ON_TAKE_HIT, MANA_PER_ATTACK
from core.stats import compute_stats
from core.traits import TraitMods, count_traits_from_tids, trait_mods_by_trait

from . import theme
from .assets import render

# ---------- 数值 -> 文案 ----------

_STAT_LABELS = {
    "ad_flat": "攻击力",
    "attack_speed_pct": "攻击速度",
    "ap_flat": "法强",
    "armor_flat": "护甲",
    "mr_flat": "魔抗",
    "hp_flat": "生命值",
    "hp_pct": "生命值",
    "ad_pct": "攻击力",
    "mana_flat": "所需法力",
    "crit_flat": "暴击率",
    "damage_amp": "伤害",
}

# 装备特殊效果的设计文案（data/items.json 的 effect 字段）
_EFFECT_TEXT = {
    "crit_damage": "特效：暴击伤害提高",
    "armor_pen": "特效：攻击无视目标部分护甲",
    "lifesteal": "特效：普攻吸血（回复伤害的 25%）",
    "magic_resist": "特效：受到的魔法伤害降低",
    "aoe_cleave": "特效：普攻对目标周围敌人造成溅射伤害",
    "on_cast_buff": "特效：施放技能后普攻强化（+20% 基础攻击）",
    "ramping_as": "特效：每次命中叠基础攻速 +6%，多把更快，无叠层上限（全局攻速上限 5/秒）",
    "thorns": "特效：受到攻击时反弹部分伤害",
    "multi_shot": "特效：普攻分裂攻击额外目标",
    "ap_amp": "特效：施法时基础法强提高（不吃羁绊/装备/大天使加成的法强）",
    "grievous_wounds": "特效：伤害目标并降低其受到的治疗",
    "mana_ap": "特效：施放技能后法强提升",
    "revive": "特效：首次阵亡后复活并恢复部分生命",
    "burn": "特效：攻击使目标持续燃烧",
    "slow_aura": "特效：减缓周围敌人的速度",
    "regen": "特效：每秒回复少量生命",
    "spell_vamp": "特效：技能吸血（回复伤害的 25%）",
    "giant_slayer": "特效：对高生命目标造成额外伤害",
    "ability_crit": "特效：技能可以暴击",
}

# 羁绊档位加成文案（与 core.traits.describe 同源）
_TIER_LABELS = {
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


def _mods_text(mods: dict) -> str:
    parts = []
    for k, v in mods.items():
        label = _TIER_LABELS.get(k, k)
        if k.endswith("_pct") or k == "crit_flat":
            parts.append(f"+{v * 100:.0f}% {label}")
        else:
            parts.append(f"+{v:g} {label}")
    return "，".join(parts)


def item_stat_text(key: str, value: float) -> str:
    """装备单条属性文案，负收益字段单独处理（mana_flat 是减蓝耗）。"""
    if key == "mana_flat":
        return f"-{value:g} {_STAT_LABELS[key]}"
    if key in ("attack_speed_pct", "hp_pct", "ad_pct", "crit_flat"):
        return f"+{value * 100:.0f}% {_STAT_LABELS.get(key, key)}"
    return f"+{value:g} {_STAT_LABELS.get(key, key)}"


# ---------- 单位 / 棋子 tooltip ----------


def _trait_names(tids: tuple[str, ...]) -> str:
    traits_data = load_traits()
    return " · ".join(traits_data.get(t, {}).get("name", t) for t in tids)


def _effective_stats(player, piece) -> tuple[dict, float]:
    """玩家某个棋子的实际数值（星级 + 已激活羁绊 + 装备）。

    备战席的棋子也会预演它上场后的羁绊效果，方便玩家决定要不要上。
    返回 (属性字典, 蓝量上限)。
    """
    tpl = load_units()[piece.tid]
    tids = [p.tid for p in player.board]
    if not any(p is piece for p in player.board):
        tids.append(piece.tid)  # 备战席：按"已上场"预演
    counts = count_traits_from_tids(tids, load_units())
    by_trait = trait_mods_by_trait(counts, load_traits())

    mods = TraitMods()
    for t in tpl.traits:
        mods = mods + by_trait.get(t, TraitMods())

    stats = compute_stats(tpl, piece.star, mods, piece_equip_stats(piece.equip))
    mana_flat = piece_equip_stats(piece.equip).get("mana_flat", 0)
    max_mana = max(0.0, tpl.max_mana - mana_flat)
    return stats, max_mana


def _ability_records(ability, ap: float, max_mana: float) -> list:
    tpl = load_units()
    _ = tpl  # 占位避免误用
    ab = ability
    power = ab.value + ap * ab.ratio
    records: list = [(f"主动 · {ab.name}", theme.FS_SMALL, theme.GOLD)]

    if ab.type == "nuke":
        desc = f"对锁定的敌人造成 {power:.0f} 点魔法伤害"
    elif ab.type == "aoe":
        desc = f"对目标及其周围 {ab.radius} 格内敌人造成 {power:.0f} 点魔法伤害"
    elif ab.type == "heal":
        desc = f"为血量最低的友军恢复 {power:.0f} 点生命"
    else:
        desc = f"造成 {power:.0f} 点伤害"
    records.append((desc, theme.FS_SMALL, theme.TEXT))

    if ab.ratio > 0:
        records.append(
            (f"基础 {ab.value:.0f} + 法强×{ab.ratio * 100:.0f}%", theme.FS_TINY, theme.TEXT_DIM)
        )
    if max_mana > 0:
        records.append(
            (
                f"满 {max_mana:.0f} 蓝自动施放（普攻回 {MANA_PER_ATTACK:.0f} 蓝，受击回 {MANA_ON_TAKE_HIT:.0f} 蓝）",
                theme.FS_MICRO,
                theme.TEXT_DIM,
            )
        )
    return records


def _stats_records(stats: dict, tpl) -> list:
    s = theme.S
    crit = stats["crit_chance"] * 100
    return [
        (
            f"生命 {stats['max_hp']:.0f}    攻击 {stats['ad']:.0f}    法强 {stats['ap']:.0f}",
            theme.FS_SMALL,
            theme.TEXT,
        ),
        (
            f"护甲 {stats['armor']:.0f}    魔抗 {stats['magic_resist']:.0f}    攻速 {stats['attack_speed']:.2f}",
            theme.FS_SMALL,
            theme.TEXT,
        ),
        (
            f"射程 {tpl.attack_range} 格    暴击 {crit:.0f}%",
            theme.FS_TINY,
            theme.TEXT_DIM,
        ),
    ]


def _title_color(cost: int, star: int) -> tuple:
    """星级高于费用本身的分量时优先金色标题（3 星一定是金色）。"""
    if star >= 3:
        return theme.GOLD
    return theme.rarity(cost)["edge"]


def unit_records(player, piece) -> list:
    """己方/敌方阵营棋子的详情（含羁绊与装备后的实际数值）。"""
    tpl = load_units()[piece.tid]
    star = piece.star
    stats, max_mana = _effective_stats(player, piece)

    star_suffix = " ★" * star if star > 1 else ""
    records: list = [
        (f"{tpl.name}{star_suffix}", theme.FS_NORMAL, _title_color(tpl.cost, star)),
        (
            f"{tpl.cost} 费 · {_trait_names(tpl.traits)}",
            theme.FS_TINY,
            theme.TEXT_DIM,
        ),
    ]
    records += _ability_records(tpl.ability, stats["ap"], max_mana)
    records += _stats_records(stats, tpl)

    if piece.equip:
        names = "、".join(item_name(it.item_id) for it in piece.equip)
        records.append((f"装备：{names}", theme.FS_TINY, theme.HP_GREEN))
    return records


def battle_unit_records(u, side_label: str = "") -> list:
    """战斗中点选单位的实时详情：数值随战斗进度刷新（暂停后可以逐帧细看）。

    战斗单位自身已含星级/羁绊/装备折算后的属性；当前攻速按羊刀叠层实时
    结算（与 combat 出手节奏同一函数，封顶全局上限 AS_CAP）。
    """
    tpl = load_units()[u.tid]
    star = u.star
    title = f"{tpl.name}{' ★' * star if star > 1 else ''}"
    if not u.alive:
        title += "（已阵亡）"
    records = [
        (title, theme.FS_NORMAL, _title_color(tpl.cost, star)),
    ]
    meta = f"{tpl.cost} 费 · {_trait_names(tpl.traits)}"
    if side_label:
        meta += f" · {side_label}"
    records.append((meta, theme.FS_TINY, theme.TEXT_DIM))

    records.append(
        (
            f"生命 {u.hp:.0f} / {u.max_hp:.0f}    法力 {u.mana:.0f} / {u.max_mana:.0f}",
            theme.FS_SMALL,
            theme.TEXT,
        )
    )
    records.append(
        (
            f"攻击 {u.ad:.0f}    攻速 {effective_attack_speed(u):.2f}/秒    法强 {u.ap:.0f}",
            theme.FS_SMALL,
            theme.TEXT,
        )
    )
    if u.as_stack > 0.0:
        records.append(
            (
                f"羊刀叠层：基础攻速提高 +{u.as_stack * 100:.0f}%",
                theme.FS_TINY,
                theme.GOLD,
            )
        )
    records.append(
        (
            f"护甲 {u.armor:.0f}    魔抗 {u.magic_resist:.0f}    射程 {tpl.attack_range} 格",
            theme.FS_TINY,
            theme.TEXT_DIM,
        )
    )
    records.append(
        (
            f"暴击 {u.crit_chance * 100:.0f}%    移速 {u.move_speed:.2f}",
            theme.FS_TINY,
            theme.TEXT_DIM,
        )
    )
    records += _ability_records(u.ability, u.ap, u.max_mana)

    if u.equip_ids:
        names = "、".join(item_name(iid) for iid in u.equip_ids)
        records.append((f"装备：{names}", theme.FS_TINY, theme.HP_GREEN))
    # 装备特效说明（同件/同类只列一次）
    seen: set[str] = set()
    for iid in u.equip_ids:
        eff = item_effect(iid)
        if eff == "none" or eff in seen:
            continue
        seen.add(eff)
        records.append((_EFFECT_TEXT.get(eff, f"特效：{eff}"), theme.FS_TINY, theme.GOLD))
    return records


# ---------- 装备 tooltip ----------


def item_records(item_id: str, have: dict[str, int] | None = None) -> list:
    """装备详情。have 是当前装备栏各基础装备的数量，用于只列出'现在凑得齐'的配方。"""
    if is_special_item(item_id):
        return [
            (item_name(item_id), theme.FS_NORMAL, theme.GOLD),
            ("特殊工具 · 非装备，无属性加成", theme.FS_TINY, theme.TEXT_DIM),
            ("拖到棋子身上：卸下其全部装备回装备栏", theme.FS_TINY, theme.GOLD),
            ("道具不消耗，可无限次使用", theme.FS_TINY, theme.TEXT_DIM),
        ]

    base = item_stats(item_id)
    advanced = "+" in item_id
    records: list = [
        (item_name(item_id), theme.FS_NORMAL, theme.GOLD if advanced else theme.TEXT)
    ]

    if advanced:
        c1, c2 = item_id.split("+", 1)
        records.append(
            (f"合成装备 · 由 {item_name(c1)} + {item_name(c2)} 合成", theme.FS_TINY, theme.TEXT_DIM)
        )
    else:
        records.append(("基础装备", theme.FS_TINY, theme.TEXT_DIM))

    for k, v in base.items():
        records.append((item_stat_text(k, v), theme.FS_SMALL, theme.TEXT))

    effect = item_effect(item_id)
    if effect and effect != "none":
        records.append(
            (_EFFECT_TEXT.get(effect, f"特效：{effect}"), theme.FS_TINY, theme.GOLD)
        )

    if not advanced and have:
        recipes = _achievable_recipes(item_id, have)
        if recipes:
            records.append(("可合成：", theme.FS_TINY, theme.GOLD))
            for line in recipes:
                records.append((line, theme.FS_MICRO, theme.TEXT_DIM))
    return records


def _achievable_recipes(item_id: str, have: dict[str, int]) -> list[str]:
    """列出某基础装备当前能合出的配方（需要装备栏里有对应素材）。"""
    from core.items import load_items

    combine = load_items()["combine"]
    lines: list[str] = []
    for key in combine:
        a, b = key.split("+", 1)
        if a == item_id:
            need = have.get(b, 0)
            if b == item_id:
                need -= 1  # 自己这件不算
            if need >= 1:
                lines.append(f"{item_name(a)} + {item_name(b)} → {item_name(key)}")
        elif b == item_id:
            need = have.get(a, 0)
            if a == item_id:
                need -= 1
            if need >= 1:
                lines.append(f"{item_name(a)} + {item_name(b)} → {item_name(key)}")
    return lines


def combine_preview_records(a: str, b: str) -> list:
    """拖一件基础装备到另一件上时的合成结果预览。"""
    combined = combine_key(a, b)
    records: list = []
    if combined is None:
        return records
    records.append(
        (f"{item_name(a)} + {item_name(b)} → {item_name(combined)}", theme.FS_SMALL, theme.GOLD)
    )
    for k, v in item_stats(combined).items():
        records.append((item_stat_text(k, v), theme.FS_SMALL, theme.TEXT))
    effect = item_effect(combined)
    if effect and effect != "none":
        records.append(
            (_EFFECT_TEXT.get(effect, f"特效：{effect}"), theme.FS_TINY, theme.GOLD)
        )
    return records


# ---------- 羁绊 tooltip ----------


def trait_records(trait_id: str, count: int) -> list:
    info = load_traits().get(trait_id)
    if info is None:
        return []
    color = theme.TRAIT_COLORS.get(trait_id, theme.TRAIT_FALLBACK)
    records: list = [
        (f"{info['name']} 羁绊（当前 {count} 个单位）", theme.FS_SMALL, color),
        (info.get("desc", ""), theme.FS_TINY, theme.TEXT_DIM),
    ]
    for tier in info.get("tiers", []):
        need = tier["count"]
        achieved = count >= need
        records.append(
            (
                f"{need} 个单位：{_mods_text(tier.get('mods', {}))}",
                theme.FS_TINY,
                theme.GOLD if achieved else theme.TEXT_DIM,
            )
        )
    return records


# ---------- 渲染 ----------


def draw_tip(surface: pygame.Surface, records, pos, accent=None) -> None:
    """把记录渲染成圆角 tooltip。pos 是首选左上角，超出窗口会自动反翻。"""
    if not records:
        return
    s = theme.S
    gap = 3 * s
    pad_x = 10 * s
    pad_y = 8 * s

    imgs = [(render(t, size, color), color) for t, size, color in records]
    w = max((i.get_width() for i, _ in imgs), default=0) + pad_x * 2
    h = sum(i.get_height() for i, _ in imgs) + gap * (len(imgs) - 1) + pad_y * 2

    rect = pygame.Rect(int(pos[0]), int(pos[1]), w, h)
    if rect.right > theme.WINDOW_W - 4:
        rect.right = int(pos[0])
    if rect.bottom > theme.WINDOW_H - 4:
        rect.bottom = int(pos[1])
    rect.x = max(4, rect.x)
    rect.y = max(4, rect.y)

    pygame.draw.rect(surface, (14, 16, 23), rect, border_radius=8)
    pygame.draw.rect(surface, theme.BORDER, rect, width=1, border_radius=8)

    # 标题色侧条，让不同类别的 tooltip 一眼可分
    accent = accent or imgs[0][1]
    bar_w = max(2, int(3 * s))
    bar = pygame.Rect(rect.x + max(1, bar_w // 2), rect.y + pad_y, bar_w, rect.height - pad_y * 2)
    pygame.draw.rect(surface, accent, bar, border_radius=bar_w)

    x = rect.x + pad_x + int(6 * s)
    y = rect.y + pad_y
    for img, _ in imgs:
        surface.blit(img, (x, y))
        y += img.get_height() + gap
