"""统一 JSON 配置读取（叶子模块，不依赖本项目任何其它模块）。

历史问题：level.json / items.json / pool.json 曾被 player.py、items.py、pool.py
各自打开解析、各自缓存，路径基址、解析逻辑重复且容易漂移。

这里把 data/*.json 的磁盘 IO 收口为唯一入口：
- 唯一路径基准 DATA_DIR；
- 进程内单缓存：同一文件只解析一次；
- check_data()：启动/测试用的数据自检（引用完整性、数值形状、拼写错误）。

注意：羁绊加成与装备统计校验所用白名单与 core/stats.TraitMods、
core/combat 中消费的 effect 关键字对齐，改动规则时需要同步此处。
"""

from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

_cache: dict[str, dict | list] = {}

# 与 core/stats.TraitMods 字段对齐的羁绊/装备可用属性（mods/stats 的 key 白名单）
ALLOWED_STAT_KEYS = {
    "hp_flat", "hp_pct",
    "ad_flat", "ad_pct",
    "ap_flat",
    "armor_flat", "mr_flat",
    "attack_speed_pct",
    "crit_flat",
    "damage_amp",
    "mana_flat",
    "mana_regen",  # 每秒额外法力回复
    "omnivamp",    # 全能吸血（攻击+技能通用）
    "dmg_reduce",  # 伤害减免
}

# core/combat 实际会消费的装备 effect 关键字
SUPPORTED_EFFECTS = {
    "none",
    # 旧关键字（神器/历史沿用）
    "crit_damage", "armor_pen", "lifesteal", "magic_resist", "aoe_cleave",
    "on_cast_buff", "ramping_as", "thorns", "multi_shot", "ap_amp",
    "grievous_wounds", "mana_ap", "revive", "burn", "slow_aura",
    "regen", "spell_vamp", "giant_slayer", "ability_crit", "stoneplate",
    # 成装各具名特效（对齐官方 equip.js）
    "hextech_gunblade", "edge_of_night", "bloodthirster", "steraks_gage",
    "spear_of_shojin", "red_buff", "titans_resolve", "kraken_slayer",
    "nashors_tooth", "void_staff", "last_whisper", "crown_guard",
    "ionic_spark", "morellonomicon", "archangels_staff", "bramble_vest",
    "sunfire_cape", "protectors_vow", "steadfast_heart", "dragons_claw",
    "twilight_veil", "adaptive_helm", "quicksilver", "warmogs_armor",
    "spirit_visage", "chain_lash", "blue_buff", "hand_of_justice",
    "team_size",  # 冠冕：队伍 +1 最大队伍规模
}


def load_json(name: str) -> dict | list:
    """读取 data/{name} 的 JSON 并进程内缓存（文件缺失抛 FileNotFoundError）。"""
    if name not in _cache:
        path = DATA_DIR / name
        with open(path, "r", encoding="utf-8") as f:
            _cache[name] = json.load(f)
    return _cache[name]


def clear_cache() -> None:
    """清空缓存（测试隔离 / 热重载用）。"""
    _cache.clear()


def check_data() -> list[str]:
    """校验 data/*.json 的引用完整性，返回问题列表（空 = 全部通过）。"""
    errors: list[str] = []
    try:
        traits = load_json("traits.json")
        units = load_json("units.json")
        items = load_json("items.json")
        pool = load_json("pool.json")
        level = load_json("level.json")
    except FileNotFoundError as exc:
        return [f"缺少数据文件：{exc}"]

    # ---- traits.json ----
    # 两种形态：
    # - 官方同步羁绊：kind/levels/color/desc + implemented=false（效果未实装，无 mods）
    # - 旧式自设羁绊：tiers[{count, mods}]（真正会给属性加成）
    for tid, data in traits.items():
        if not isinstance(data, dict) or not data.get("name"):
            errors.append(f"羁绊 {tid} 缺少 name")
            continue
        kind = data.get("kind")
        if kind is not None and kind not in ("race", "job", "custom"):
            errors.append(f"羁绊 {tid} kind 非法：{kind}")
        levels = data.get("levels")
        if levels is not None:
            if (
                not isinstance(levels, list)
                or not levels
                or any(not isinstance(x, int) or x < 1 for x in levels)
                or levels != sorted(levels)
            ):
                errors.append(f"羁绊 {tid} levels 应为递增正整数列表：{levels}")
            if not isinstance(data.get("implemented", False), bool):
                errors.append(f"羁绊 {tid} implemented 应为布尔值")
        for i, tier in enumerate(data.get("tiers", [])):
            count = tier.get("count")
            if not isinstance(count, int) or count < 1:
                errors.append(f"羁绊 {tid} 第 {i + 1} 档 count 非法：{tier}")
            for k in tier.get("mods", {}):
                if k not in ALLOWED_STAT_KEYS:
                    errors.append(f"羁绊 {tid} 使用了未知属性 {k}")
        if levels is None and not data.get("tiers"):
            errors.append(f"羁绊 {tid} 既无 levels 也无 tiers")

    # ---- units.json ----
    ids = [u.get("id") for u in units]
    if len(ids) != len(set(ids)):
        errors.append("units.json 存在重复 id")
    for u in units:
        uid = u.get("id", "?")
        if not isinstance(uid, str) or not uid:
            errors.append("units.json 存在缺少 id 的单位")
            continue
        if u.get("cost", 1) not in (1, 2, 3, 4, 5):
            errors.append(f"单位 {uid} cost 非法：{u.get('cost')}")
        for t in u.get("traits", ()):
            if t not in traits:
                errors.append(f"单位 {uid} 引用不存在的羁绊 {t}")
        for key in ("hp", "ad"):
            if not isinstance(u.get(key), (int, float)) or u[key] <= 0:
                errors.append(f"单位 {uid} {key} 非法：{u.get(key)}")
        ab = u.get("ability") or {}
        if ab.get("type") not in ("nuke", "aoe", "heal"):
            errors.append(f"单位 {uid} ability.type 非法：{ab.get('type')}")
        if u.get("max_mana", 0) and u.get("starting_mana", 0) > u["max_mana"]:
            errors.append(f"单位 {uid} starting_mana > max_mana")

    # ---- level.json ----
    levels = level.get("levels", [])
    if len(levels) != 10:
        errors.append(f"level.json levels 应为 10 级，实际 {len(levels)} 条")
    for i, row in enumerate(levels, start=1):
        if row.get("level") != i or not isinstance(row.get("board_cap"), int) or not isinstance(
            row.get("xp_needed"), int
        ):
            errors.append(f"level.json 第 {i} 条形状非法：{row}")
    odds = level.get("odds", {})
    for lv in range(1, 11):
        arr = odds.get(str(lv))
        if not isinstance(arr, list) or len(arr) != 5 or abs(sum(arr) - 100) > 1e-6:
            errors.append(f"level.json odds[{lv}] 应为 5 项且合计 100：{arr}")

    # ---- pool.json ----
    copies = pool.get("copies_by_cost", {})
    for cost in ("1", "2", "3", "4", "5"):
        if not isinstance(copies.get(cost), int) or copies[cost] < 1:
            errors.append(f"pool.json copies_by_cost 缺少/非法 cost {cost}")

    # ---- items.json ----
    bases = items.get("base", {})
    if len(bases) != 10:
        errors.append(f"基础装备数量应为 10，实际 {len(bases)}")
    for iid, data in bases.items():
        if not data.get("name"):
            errors.append(f"基础装备 {iid} 缺少 name")
        for k in data.get("stats", {}):
            if k not in ALLOWED_STAT_KEYS:
                errors.append(f"基础装备 {iid} 使用未知属性 {k}")
    combine = items.get("combine", {})
    for key, data in combine.items():
        parts = key.split("+")
        if len(parts) != 2 or any(part not in bases for part in parts):
            errors.append(f"合成公式 {key} 未使用两个基础装备")
        if not data.get("name"):
            errors.append(f"合成装备 {key} 缺少 name")
        for k in data.get("stats", {}):
            if k not in ALLOWED_STAT_KEYS:
                errors.append(f"合成装备 {key} 使用未知属性 {k}")
        effect = data.get("effect", "none")
        if effect not in SUPPORTED_EFFECTS:
            errors.append(f"合成装备 {key} 使用了战斗层未支持的 effect：{effect}")

    # ---- artifacts.json（神器）----
    artifacts = items.get("artifacts", {})
    for aid, data in artifacts.items():
        if not data.get("name"):
            errors.append(f"神器 {aid} 缺少 name")
        for k in data.get("stats", {}):
            if k not in ALLOWED_STAT_KEYS:
                errors.append(f"神器 {aid} 使用未知属性 {k}")
        effect = data.get("effect", "none")
        if effect not in SUPPORTED_EFFECTS:
            errors.append(f"神器 {aid} 使用了战斗层未支持的 effect：{effect}")

    return errors
