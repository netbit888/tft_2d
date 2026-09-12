# -*- coding: utf-8 -*-
"""从金铲铲官方 equip.js 同步「散件 + 成装」的名称/数值/特效到 data/items.json。

数据源：tools/_jcc_raw/equip_18.18.2-S19.json
（官方 mode18 快照，取自 versiondataconfig.js 的 equipurl；与 dataj.cc 同源）。

- 散件：按 BASE_ID 映射用官方 basicDesc 覆盖 stats（我方既有展示名保留，新件取官方名）。
- 成装：按配方（synthesis1+synthesis2）匹配官方「成型装备」，写 name/stats/effect/desc。
- 冠冕（金铲铲 / 金锅锅 / 金锅铲）现已补齐对应散件，一并纳入。
- 数值来自官方 basicDesc（自动解析）+ desc 中的「获得X%最大生命值」。
- 特效关键字由 SPEC 表指定（core/combat.py 消费），官方原文存进 desc 字段供 UI 展示。

用法：
    python tools/sync_official_items.py            # dry-run，打印将改动
    python tools/sync_official_items.py --apply    # 写入 data/items.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAP = ROOT / "tools" / "_jcc_raw" / "equip_18.18.2-S19.json"
ITEMS = ROOT / "data" / "items.json"

# 我方散件 id -> 官方散件 id（顺序即 items.json 的 base 表顺序）
BASE_ID = {
    "sword": "1001", "bow": "1002", "wand": "1003", "tear": "1004",
    "chain": "1005", "cloak": "1006", "belt": "1007", "glove": "1009",
    "spatula": "1008", "pan": "1010",
}
OFF_TO_OUR = {v: k for k, v in BASE_ID.items()}

# 我方合成 key -> 特效关键字（core/combat.py 消费）。none = 无战斗特效。
SPEC = {
    "sword+sword": "none",              # 锐利之刃   纯数值
    "sword+bow":   "giant_slayer",      # 巨人捕手   对抗坦克增伤
    "sword+wand":  "hextech_gunblade",  # 海克斯科技枪刃
    "sword+chain": "edge_of_night",     # 夜之锋刃
    "sword+cloak": "bloodthirster",     # 汲取剑
    "sword+belt":  "steraks_gage",      # 斯特拉克的挑战护手
    "sword+tear":  "spear_of_shojin",   # 朔极之矛
    "sword+glove": "ability_crit",      # 无尽之刃

    "bow+bow":     "red_buff",          # 红霸符
    "bow+wand":    "ramping_as",        # 鬼索的狂暴之刃
    "bow+chain":   "titans_resolve",    # 泰坦的坚决
    "bow+cloak":   "kraken_slayer",     # 海妖之怒
    "bow+belt":    "nashors_tooth",     # 纳什之牙
    "bow+tear":    "void_staff",        # 虚空之杖
    "bow+glove":   "last_whisper",      # 最后的轻语

    "wand+wand":   "none",              # 班克斯的魔法帽 纯数值
    "wand+chain":  "crown_guard",       # 冕卫
    "wand+cloak":  "ionic_spark",       # 离子火花
    "wand+belt":   "morellonomicon",    # 莫雷洛秘典
    "wand+tear":   "archangels_staff",  # 大天使之杖
    "wand+glove":  "ability_crit",      # 珠光护手

    "chain+chain": "bramble_vest",      # 棘刺背心
    "chain+cloak": "stoneplate",        # 石像鬼石板甲
    "chain+belt":  "sunfire_cape",      # 日炎斗篷
    "chain+tear":  "protectors_vow",    # 圣盾使的誓约
    "chain+glove": "steadfast_heart",   # 坚定之心

    "cloak+cloak": "dragons_claw",      # 巨龙之爪
    "cloak+belt":  "twilight_veil",     # 薄暮法袍
    "cloak+tear":  "adaptive_helm",     # 适应性头盔
    "cloak+glove": "quicksilver",       # 水银

    "belt+belt":   "warmogs_armor",     # 狂徒铠甲
    "belt+tear":   "spirit_visage",     # 振奋盔甲
    "belt+glove":  "chain_lash",        # 强袭者的链枷

    "tear+tear":   "blue_buff",         # 蓝霸符
    "tear+glove":  "hand_of_justice",   # 正义之手
    "glove+glove": "none",              # 秘法手套 超出战斗系统

    # 冠冕（金铲铲 / 金锅锅 / 金锅铲）：队伍 +1 最大队伍规模
    "spatula+spatula": "team_size",     # 金铲铲冠冕
    "pan+pan":         "team_size",     # 金锅锅冠冕
    "spatula+pan":     "team_size",     # 金锅铲冠冕
}

STAT_PATTERNS = [
    (r"([+-]\d+)生命上限", "hp_flat", 1),
    (r"([+-]\d+)护甲", "armor_flat", 1),
    (r"([+-]\d+)魔法抗性", "mr_flat", 1),
    (r"([+-]\d+)物理加成", "ad_flat", 1),
    (r"([+-]\d+)法术加成", "ap_flat", 1),
    (r"([+-]\d+)法力回复", "mana_regen", 1),
    (r"([+-]?\d+(?:\.\d+)?)%攻击速度", "attack_speed_pct", 0.01),
    (r"([+-]?\d+(?:\.\d+)?)%暴击率", "crit_flat", 0.01),
    (r"([+-]?\d+(?:\.\d+)?)%全能吸血", "omnivamp", 0.01),
    (r"([+-]?\d+(?:\.\d+)?)%伤害增幅", "damage_amp", 0.01),
    (r"([+-]?\d+(?:\.\d+)?)%伤害减免", "dmg_reduce", 0.01),
]


def parse_stats(basic: str, desc: str = "") -> dict:
    out: dict[str, float] = {}
    for pat, key, scale in STAT_PATTERNS:
        m = re.search(pat, basic)
        if m:
            out[key] = round(float(m.group(1)) * scale, 4)
    m = re.search(r"获得(\d+(?:\.\d+)?)%最大生命值", desc)
    if m:
        out["hp_pct"] = round(float(m.group(1)) / 100.0, 4)
    return out


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    snap = json.loads(SNAP.read_text(encoding="utf-8"))
    all_recs = list(snap["data"].values())
    by_id = {str(r["id"]): r for r in all_recs}

    by_recipe: dict[str, dict] = {}
    for r in all_recs:
        if r.get("type") != "成型装备":
            continue
        a = OFF_TO_OUR.get(str(r["synthesis1"]))
        b = OFF_TO_OUR.get(str(r["synthesis2"]))
        if a and b:
            by_recipe[f"{a}+{b}"] = r
            by_recipe[f"{b}+{a}"] = r  # 配方与顺序无关

    items = json.loads(ITEMS.read_text(encoding="utf-8"))
    old_base = items["base"]

    # ---- 散件 ----
    new_base: dict[str, dict] = {}
    print(f"{'散件 id':14s} {'名称':<8} 官方 basicDesc")
    print("-" * 70)
    for our_id, off_id in BASE_ID.items():
        r = by_id.get(off_id)
        stats = parse_stats(r["basicDesc"]) if r else {}
        name = old_base.get(our_id, {}).get("name") or (r["name"] if r else our_id)
        new_base[our_id] = {"name": name, "stats": stats}
        print(f"{our_id:14s} {name:<8} {r['basicDesc'] if r else '(官方无此件)'}  -> {stats}")

    # ---- 成装 ----
    new_combine: dict[str, dict] = {}
    missing: list[str] = []
    print(f"\n{'成装 key':16s} {'官方名':<12} {'特效':<18} 属性")
    print("-" * 100)
    for key, eff in SPEC.items():
        r = by_recipe.get(key)
        if r is None:
            missing.append(key)
            print(f"{key:16s} !! 官方无此配方")
            continue
        stats = parse_stats(r["basicDesc"], r["desc"])
        entry = {"name": r["name"], "stats": stats, "effect": eff}
        if r["desc"].strip():
            entry["desc"] = r["desc"].strip()
        new_combine[key] = entry
        print(f"{key:16s} {r['name']:<12} {eff:<18} {stats}")
    if missing:
        print(f"\n!! 未匹配配方 {len(missing)}: {missing}")

    items["base"] = new_base
    items["combine"] = new_combine
    if not args.apply:
        print(f"\n[dry-run] 散件 {len(new_base)} / 成装 {len(new_combine)}；确认请加 --apply")
        return
    ITEMS.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n[已写入] {ITEMS}（散件 {len(new_base)} / 成装 {len(new_combine)}）")


if __name__ == "__main__":
    main()
