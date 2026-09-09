# -*- coding: utf-8 -*-
"""同步金铲铲官方白板属性到 data/units.json。

数据源：金铲铲官网公开数据链
- basicConfig:  https://jcc.qq.com/data-js/basicConfig.js      （当前 mode/赛季）
- 版本索引:     https://game.gtimg.cn/images/lol/act/jkzlk/js/config/versiondataconfig.js
- 英雄数据:     https://game.gtimg.cn/images/lol/act/jkzlk/js/<herourl>  （chess.js）
官方英雄 JSON 中同一英雄按“星级型号”拆多条：id 前缀 1/2/3/4 = 1~4 星，
showHeroTag=1 是正式显示体（同名皮肤/变体为 tag=0 副本）。
units.json 存 1 星基准，与官方 ×1.8/×3.24 星级成长一致，因此取“前缀 1 + tag=1”一条。

同步范围（按需 --fields 裁剪）：
- hp/ad/attack_speed/attack_range/armor/magic_resist/crit_chance/蓝量  ← 官方 1 星白板
- ability.name                                                        ← 官方技能名
保留：cost、traits、ap、move_speed、ability.type/value/ratio/radius（技能效果）。

用法：
    python tools/sync_official_stats.py              # dry-run，打印将改动
    python tools/sync_official_stats.py --apply      # 实际写入 units.json
    python tools/sync_official_stats.py --fields hp,ad,ability.name --apply  # 只同步指定项
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parent.parent
SNAP_DIR = ROOT / "tools" / "_jcc_raw"
GAME = "https://game.gtimg.cn/images/lol/act/jkzlk/js/"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
      "Referer": "https://jcc.qq.com/"}

FIELD_MAP = {
    "hp": "initHP",
    "ad": "initAttackDamage",
    "attack_speed": "attackSpeed",
    "attack_range": "attackRange",
    "armor": "armor",
    "magic_resist": "magicResist",
    "crit_chance": "criticalStrikeChance",  # 值在循环里按 /100 折算
    "starting_mana": "initMP",
    "max_mana": "maxMP",
}

# 我方棋子名与官方名称不一致的少数棋子：{我方名: 官方名}
NAME_OVERRIDE = {
    "锋喙鸟": "深红锋喙鸟",  # 官方为 Crimson Raptor 中文名
}


def http_text(url: str) -> str:
    req = urllib.request.Request(url, headers=UA)
    raw = urllib.request.urlopen(req, timeout=60).read()
    for enc in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "ignore")


def load_official() -> dict:
    """优先读本地快照，否则在线抓最新生效版本并存档。"""
    cand = sorted(SNAP_DIR.glob("chess_*.json"))
    if cand:
        print(f"[源] 使用本地官方快照 {cand[-1].name}")
        return json.loads(cand[-1].read_text(encoding="utf-8"))
    cfg = http_text("https://jcc.qq.com/data-js/basicConfig.js")
    mode = re.search(r"\bvar\s+mode\s*=\s*['\"]([^'\"]+)", cfg).group(1)
    season = re.search(r"\bvar\s+season\s*=\s*['\"]([^'\"]+)", cfg).group(1)
    idx_txt = http_text(
        "https://game.gtimg.cn/images/lol/act/jkzlk/js/config/versiondataconfig.js"
    )
    m = re.search(r"=\s*(\{.*\}|\[.*\])\s*;?\s*$", idx_txt, re.S)
    idx = json.loads(m.group(1))
    recs = idx if isinstance(idx, list) else (idx.get("data") or list(idx.values())[0])
    today = date.today().isoformat()
    pool = [r for r in recs if str(r.get("mode")) == mode
            and str(r.get("season", "")).lower() == season.lower()
            and str(r.get("version_start_time", ""))[:10] <= today]
    pick = max(pool, key=lambda r: r.get("version_start_time", ""))
    url = urljoin(GAME, str(pick["herourl"]).lstrip("/"))
    txt = http_text(url)
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    name = f"chess_{pick['version']}-{pick['season']}.json"
    (SNAP_DIR / name).write_text(txt, encoding="utf-8")
    print(f"[源] 在线抓取官方 {url} -> {SNAP_DIR / name}")
    return json.loads(txt)


def num(v):
    return float(v) if "." in str(v) else int(v)


def pick_official(recs) -> dict:
    """name -> {字段: 值}；取该英雄 1 星正式体（id 以 1 开头且 showHeroTag=1）。"""
    out = {}
    for r in recs:
        hid = str(r["id"])
        if hid.startswith("1") and str(r.get("showHeroTag")) == "1":
            out[r["name"]] = r  # 每名应唯一
    return out


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="实际写回 units.json")
    ap.add_argument("--fields", default="",
                    help="只同步指定项，逗号分隔，如 hp,ad,ability.name")
    args = ap.parse_args()

    want = {f.strip() for f in args.fields.split(",") if f.strip()} or None
    snap = load_official()
    off1 = pick_official(snap["data"].values())
    print(f"[源] 官方英雄(1星正式体) {len(off1)} 个")

    units_path = ROOT / "data" / "units.json"
    units = json.loads(units_path.read_text(encoding="utf-8"))

    changed, miss, price_diff = [], [], []
    for u in units:
        off = off1.get(NAME_OVERRIDE.get(u["name"], u["name"]))
        if off is None:
            miss.append((u["id"], u["name"]))
            continue
        d = {}
        for f, k in FIELD_MAP.items():
            if want is not None and f not in want:
                continue
            if f == "crit_chance":
                v = round(int(off["criticalStrikeChance"]) / 100.0, 3)
            else:
                v = num(off[k])
            if u.get(f) != v:
                d[f] = (u.get(f), v)
        if (want is None or "ability.name" in want) and u["ability"]["name"] != off["skillName"]:
            d["ability.name"] = (u["ability"]["name"], off["skillName"])
        if d:
            changed.append((u["id"], u["name"], d))
        if int(off.get("price", 0)) != int(u["cost"]):
            price_diff.append((u["id"], u["name"], u["cost"], int(off.get("price", 0))))

    print(f"\n将改动 {len(changed)} 个棋子\n")
    for tid, name, d in changed:
        for f, (old, new) in d.items():
            mark = "~" if isinstance(old, (int, float)) and isinstance(new, (int, float)) and old else " "
            print(f"  {tid:14s} {name:6s} {f:14s} {old} {mark}> {new}")
    if miss:
        print(f"\n!! 官方无同名棋子 {len(miss)}: {miss}")
    if price_diff:
        print("\n[费用差异-仅提示不覆盖]")
        for tid, name, my, of in price_diff:
            print(f"  {tid:14s} {name:6s} 我方{my} 官方{of}")

    if not changed:
        print("无需改动。")
        return
    if not args.apply:
        print(f"\n[dry-run] 以上为预览；确认请加 --apply（保存前备份可看 git diff）")
        return

    # 写回
    for tid, name, d in changed:
        u = next(x for x in units if x["id"] == tid)
        for f, (_old, new) in d.items():
            if f == "ability.name":
                u["ability"]["name"] = new
            else:
                u[f] = new
    units_path.write_text(
        json.dumps(units, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\n[已写入] {units_path}（{len(changed)} 个棋子）")


if __name__ == "__main__":
    main()
