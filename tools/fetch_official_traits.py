# -*- coding: utf-8 -*-
"""拉取金铲铲官方羁绊配置存档并打印名称清单。

数据源链与 tools/sync_official_stats.py 同源：
- basicConfig.js 决定当前 mode/season
- versiondataconfig.js 版本索引给出 race.js / job.js / trait.js / chess.js 地址

英雄 JSON 中每个棋子的官方羁绊用数字 id 表示：
- species  → race.js（种族，如 永恒之森）
- class    → job.js（职业，可能多个用 | 分隔）
现代版本另有整合表 trait.js（id 为复合 id，含 checkId 指向 job/race）。

用法：
    python tools/fetch_official_traits.py        # 下载/读取存档，打印全名清单与棋手归属样例
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAP = ROOT / "tools" / "_jcc_raw"
BASE = "https://game.gtimg.cn/images/lol/act/jkzlk/js"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
      "Referer": "https://jcc.qq.com/"}


def http_text(url: str) -> str:
    raw = urllib.request.urlopen(
        urllib.request.Request(url, headers=UA), timeout=60).read()
    for enc in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "ignore")


def load_js(url: str) -> dict:
    txt = http_text(url)
    m = re.search(r"(\{.*\}|\[.*\])\s*$", txt, re.S)
    return json.loads(m.group(1))


def current_ver() -> dict:
    cfg = http_text("https://jcc.qq.com/data-js/basicConfig.js")
    mode = re.search(r"var\s+mode\s*=\s*['\"]([^'\"]+)", cfg).group(1)
    season = re.search(r"var\s+season\s*=\s*['\"]([^'\"]+)", cfg).group(1)
    txt = http_text(
        "https://game.gtimg.cn/images/lol/act/jkzlk/js/config/versiondataconfig.js")
    recs = json.loads(re.search(r"(\[.*\])\s*$", txt, re.S).group(1))
    today = __import__("datetime").date.today().isoformat()
    pool = [r for r in recs
            if str(r.get("mode")) == mode
            and str(r.get("season", "")).lower() == season.lower()
            and str(r.get("version_start_time", ""))[:10] <= today]
    return max(pool, key=lambda r: r.get("version_start_time", ""))


def snap_path(ver: dict, name: str) -> Path:
    p = SNAP / f"{name}_{ver['version']}-{ver['season']}.json"
    SNAP.mkdir(parents=True, exist_ok=True)
    return p


def load_or_fetch(ver: dict, name: str) -> dict:
    p = snap_path(ver, name)
    if p.exists():
        print(f"[读档] {p.name}")
        return json.loads(p.read_text(encoding="utf-8"))
    obj = load_js(f"{BASE}{ver[f'{name}url']}")
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[下载] {name}.js -> {p.name}（{len(obj.get('data', {}))} 条）")
    return obj


def dump_names(obj: dict, title: str):
    data = obj.get("data", {})
    print(f"\n== {title} ({len(data)}) ==")
    for i, item in enumerate(sorted(data.values(), key=lambda x: int(x["id"]))):
        print(f"  {item['id']:>6}  {item.get('name')}  "
              f"tiers={item.get('numList', item.get('num', '-'))}"
              f"  {str(item.get('prefix', ''))[:40]}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ver = current_ver()
    print(f"当前版本 {ver['version']}-{ver['season']} (mode={ver.get('mode')})")
    race = load_or_fetch(ver, "race")
    job = load_or_fetch(ver, "job")
    load_or_fetch(ver, "trait")

    dump_names(race, "种族 race.js")
    dump_names(job, "职业 job.js")

    # 我方棋子官方羁绊归属样例（奥恩/阿卡丽/拉克丝）
    chess = load_or_fetch(ver, "hero")
    heros = chess["data"].values()
    by_name = {}
    for r in heros:
        if str(r["id"]).startswith("1") and str(r.get("showHeroTag")) == "1":
            by_name.setdefault(r["name"], []).append(r)
    rname = {k: v["name"] for k, v in race["data"].items()}
    jname = {k: v["name"] for k, v in job["data"].items()}
    print("\n== 我方棋子 -> 官方羁绊归属 ==")
    units = json.loads((ROOT / "data" / "units.json").read_text(encoding="utf-8"))
    for u in units:
        r = (by_name.get(u["name"]) or [None])[0]
        if not r:
            print(f"  {u['name']:8s} 无官方记录")
            continue
        sp = [rname.get(s) for s in str(r["species"]).split("|") if rname.get(s)]
        cl = [jname.get(c) for c in str(r["class"]).split("|") if jname.get(c)]
        print(f"  {u['name']:8s} 种族={sp} 职业={cl}")


if __name__ == "__main__":
    main()
