# -*- coding: utf-8 -*-
"""从金铲铲官方 equip.js 同步「成装」的数值/名称/特效到 data/items.json。

数据源：tools/_jcc_raw/equip_18.18.2-S19.json
（官方 mode18 快照，取自 versiondataconfig.js 的 equipurl；与 dataj.cc 同源）。

- 按配方（synthesis1+synthesis2）把我方 36 个合成 key 与官方 39 件「成型装备」对齐；
  金铲铲/金锅锅冠冕因我方没有对应散件而跳过。
- 数值来自官方 basicDesc（自动解析）+ desc 中的「获得X%最大生命值」。
- 特效关键字由本脚本 SPEC 表指定（core/combat.py 消费），官方原文存进 desc 字段供 UI 展示。

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

# 官方基础件 id -> 我方基础件 id
BASE_ID = {
    "1001": "sword", "1002": "bow", "1003": "wand", "1004": "tear",
    "1005": "chain", "1006": "cloak", "1007": "belt", "1009": "glove",
}

# 我方合成 key -> 特效关键字（core/combat.py 消费）。none = 无战斗特效。
SPEC = {
    "sword+sword": "none",              # 锐利之刃   纯数值
    "sword+bow":   "giant_slayer",      # 巨人捕手   对抗坦克增伤
    "sword+wand":  "hextech_gunblade",  # 海克斯科技枪刃
    "sword+chain": "edge_of_night",     # 夜之锋刃
    "sword+cloak": "bloodthirster",     # 汲取剑(原饮血剑)
    "sword+belt":  "steraks_gage",      # 斯特拉克的挑战护手
    "sword+tear":  "spear_of_shojin",   # 朔极之矛
    "sword+glove": "ability_crit",      # 无尽之刃

    "bow+bow":     "red_buff",          # 红霸符
    "bow+wand":    "ramping_as",        # 鬼索的狂暴之刃
    "bow+chain":   "titans_resolve",    # 泰坦的坚决
    "bow+cloak":   "kraken_slayer",     # 海妖之怒
    "bow+belt":    "nashors_tooth",     # 纳什之牙
    "bow+tear":    "void_staff",        # 虚空之杖(原斯塔缇克电刃)
    "bow+glove":   "last_whisper",      # 最后的轻语

    "wand+wand":   "none",              # 班克斯的魔法帽(原灭世者的死亡之帽) 纯数值
    "wand+chain":  "crown_guard",       # 冕卫
    "wand+cloak":  "ionic_spark",       # 离子火花
    "wand+belt":   "morellonomicon",    # 莫雷洛秘典
    "wand+tear":   "archangels_staff",  # 大天使之杖
    "wand+glove":  "ability_crit",      # 珠光护手

    "chain+chain": "bramble_vest",      # 棘刺背心(原荆棘背心)
    "chain+cloak": "stoneplate",        # 石像鬼石板甲
    "chain+belt":  "sunfire_cape",      # 日炎斗篷
    "chain+tear":  "protectors_vow",    # 圣盾使的誓约
    "chain+glove": "steadfast_heart",   # 坚定之心

    "cloak+cloak": "dragons_claw",      # 巨龙之爪
    "cloak+belt":  "twilight_veil",     # 薄暮法袍
    "cloak+tear":  "adaptive_helm",     # 适应性头盔
    "cloak+glove": "quicksilver",       # 水银(原水银饰带)

    "belt+belt":   "warmogs_armor",     # 狂徒铠甲
    "belt+tear":   "spirit_visage",     # 振奋盔甲
    "belt+glove":  "chain_lash",        # 强袭者的链枷

    "tear+tear":   "blue_buff",         # 蓝霸符
    "tear+glove":  "hand_of_justice",   # 正义之手
    "glove+glove": "none",              # 秘法手套(原窃贼手套) 超出战斗系统
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


def parse_stats(basic: str, desc: str) -> dict:
    out: dict[str, float] = {}
    for pat, key, scale in STAT_PATTERNS:
        m = re.search(pat, basic)
        if m:
            out[key] = round(float(m.group(1)) * scale, 4)
    # desc 里的「获得X%最大生命值」也计入属性
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
    recs = [r for r in snap["data"].values() if r.get("type") == "成型装备"]

    by_recipe: dict[str, dict] = {}
    for r in recs:
        a, b = BASE_ID.get(str(r["synthesis1"])), BASE_ID.get(str(r["synthesis2"]))
        if a and b:
            by_recipe[f"{a}+{b}"] = r
            by_recipe[f"{b}+{a}"] = r  # 配方与顺序无关

    items = json.loads(ITEMS.read_text(encoding="utf-8"))
    combine = items["combine"]

    new_combine: dict[str, dict] = {}
    print(f"{'key':14s} {'官方名':<12} {'特效':<18} 属性")
    print("-" * 100)
    missing = []
    for key in combine:  # 保持现有顺序
        r = by_recipe.get(key)
        if r is None:
            missing.append(key)
            new_combine[key] = combine[key]
            print(f"{key:14s} !! 官方无此配方，保持原样")
            continue
        stats = parse_stats(r["basicDesc"], r["desc"])
        eff = SPEC.get(key, "none")
        entry = {"name": r["name"], "stats": stats, "effect": eff}
        if r["desc"].strip():
            entry["desc"] = r["desc"].strip()
        new_combine[key] = entry
        print(f"{key:14s} {r['name']:<12} {eff:<18} {stats}")
    if missing:
        print(f"\n!! 未匹配配方 {len(missing)}: {missing}")

    items["combine"] = new_combine
    if not args.apply:
        print("\n[dry-run] 以上为预览；确认请加 --apply")
        return
    ITEMS.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n[已写入] {ITEMS}")


if __name__ == "__main__":
    main()
