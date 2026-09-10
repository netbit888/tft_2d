# -*- coding: utf-8 -*-
"""从腾讯金铲铲官方 CDN 下载羁绊图标到 assets/traits/<羁绊id>.png。

数据源（与 tools/fetch_official_traits.py、tools/sync_official_stats.py 同源）：
- basicConfig.js 决定当前 mode/season
- versiondataconfig.js 给出 race.js / job.js / trait.js 地址
- 上述配置每条都带 picture 字段，即为官方羁绊图标直链，形如
  https://game.gtimg.cn/images/lol/act/jkzlk/mode18s19/trait/s18_trait_icon_elderwood.png

落地规则：文件名用游戏内羁绊 id（data/traits.json 的键，如 450 / 342），
绘制层 render/trait_art.py 按 id 找图，缺图自动回退程序化六边形。

用法：
    python tools/fetch_trait_icons.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import fetch_official_traits as official  # noqa: E402

OUT = ROOT / "assets" / "traits"
UA = {"User-Agent": "Mozilla/5.0 (tft_2d jkzlk trait icons)",
      "Referer": "https://jcc.qq.com/"}


def load_trait_ids() -> set[str]:
    """本项目 data/traits.json 里的全部羁绊 id（转成字符串）。"""
    raw = json.loads((ROOT / "data" / "traits.json").read_text(encoding="utf-8"))
    return {str(k) for k in raw}


def collect_pictures(ver: dict) -> dict[str, str]:
    """汇总 羁绊id -> 图标URL；race/job 用自身 id，trait 用 checkId 归一化。"""
    out: dict[str, str] = {}
    for name in ("race", "job", "trait"):
        obj = official.load_or_fetch(ver, name)
        for item in obj.get("data", {}).values():
            pic = item.get("picture")
            if not pic:
                continue
            key = str(item.get("checkId") or item["id"])
            out.setdefault(key, pic)  # race/job 优先，trait 只补缺
    return out


def fetch_one(tid: str, url: str) -> tuple[str, bool, str]:
    for attempt in (1, 2):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
            if raw[:4] != b"\x89PNG":
                return tid, False, "非 PNG"
            (OUT / f"{tid}.png").write_bytes(raw)
            return tid, True, ""
        except Exception as e:  # noqa: BLE001
            if attempt == 2:
                return tid, False, repr(e)[:120]
    return tid, False, "?"


def main() -> None:
    ver = official.current_ver()
    print(f"当前版本 {ver['version']}-{ver['season']} (mode={ver.get('mode')})")

    target = load_trait_ids()
    pics = collect_pictures(ver)
    print(f"本项目羁绊 {len(target)} 个，官方提供图标 {len(pics)} 个")

    OUT.mkdir(parents=True, exist_ok=True)
    jobs = [(tid, pics[tid]) for tid in sorted(target) if tid in pics]
    missing = sorted(target - set(pics))

    ok, fail = 0, []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(fetch_one, tid, url): tid for tid, url in jobs}
        for fut in as_completed(futs):
            tid, success, err = fut.result()
            if success:
                ok += 1
            else:
                fail.append((tid, err))
    for tid, err in fail:
        print(f"  [失败] {tid}: {err}")
    for tid in missing:
        print(f"  [无图标] {tid}: 官方配置未提供 picture，绘制层将回退程序化六边形")
    print(f"下载完成：成功 {ok} / {len(jobs)}，落地目录 {OUT}")


if __name__ == "__main__":
    main()
