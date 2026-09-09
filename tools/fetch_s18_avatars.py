# -*- coding: utf-8 -*-
"""从腾讯金铲铲 S18 官方素材 CDN 下载棋子头像到 assets/units/<tid>.png。

数据来源说明：
- dataj.cc（金铲铲大数据站）展示的英雄图片直链腾讯官方 CDN，路径规律：
  https://game.gtimg.cn/images/lol/act/jkzlk/mode18s19/hero/s18_head_<英文>.png
- tools/tft_s18_heads.json 固化“单位 id -> S18 头像文件名”映射（由 data/units.json
  的中文名与 dataj 首页数据比对生成，个别单位名不同用 CDN 命名规则补齐）。

用法：
    python tools/fetch_s18_avatars.py

输出：
- 覆盖/补齐 assets/units/<tid>.png（原始 96x96，游戏端圆形裁切后依然够用）
- 根目录 棋子头像总览.png（网格预览核对）
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import pygame  # noqa: E402

BASE = "https://game.gtimg.cn/images/lol/act/jkzlk/mode18s19/hero/"
MAP = json.loads((ROOT / "tools" / "tft_s18_heads.json").read_text(encoding="utf-8"))
OUT = ROOT / "assets" / "units"
UA = {"User-Agent": "Mozilla/5.0 (tft_2d jkzlk s18 fetch)"}


def load_units() -> list[dict]:
    return json.loads((ROOT / "data" / "units.json").read_text(encoding="utf-8"))


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
            err = repr(e)[:120]
            if attempt == 2:
                return tid, False, err
    return tid, False, "?"  # 不可达


def main() -> None:
    if not pygame.get_init():
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        pygame.init()
    OUT.mkdir(parents=True, exist_ok=True)

    units = load_units()
    jobs = []
    missing = []
    for u in units:
        ent = MAP.get(u["id"])
        if not ent:
            missing.append((u["id"], u["name"], "无映射"))
            continue
        jobs.append((u["id"], ent["url"]))
    print(f"共 {len(units)} 枚棋子，准备下载 {len(jobs)} 张 S18 头像…")

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
    for tid, name, why in missing:
        print(f"  [无映射] {tid} {name}: {why}")
    print(f"下载完成：成功 {ok} / {len(jobs)}")

    # 网格总览
    cols = 10
    cell, icon, pad = 168, 128, 10
    rows = (len(units) + cols - 1) // cols
    sheet = pygame.Surface((cols * cell, rows * cell + 24), pygame.SRCALPHA)
    sheet.fill((20, 22, 30, 255))
    font_path = None
    for cand in (
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/msyhc.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "/System/Library/Fonts/PingFang.ttc",
    ):
        if Path(cand).is_file():
            font_path = cand
            break
    label_font = pygame.font.Font(font_path, 18) if font_path else None
    for i, u in enumerate(units):
        c, r = i % cols, i // cols
        x, y = c * cell, r * cell
        pygame.draw.rect(sheet, (35, 40, 55), (x, y + 24, cell, cell - 24), border_radius=8)
        tex = pygame.image.load(str(OUT / f"{u['id']}.png"))
        small = pygame.transform.smoothscale(tex, (icon, icon))
        sheet.blit(small, (x + (cell - icon) // 2, y + 24 + (cell - 24 - icon) // 2))
        if label_font is not None:
            name = u["name"][:3] + "…" if len(u["name"]) > 4 else u["name"]
            img = label_font.render(name, True, (230, 232, 240))
            sheet.blit(img, img.get_rect(center=(x + cell // 2, y + 12)))
    preview = ROOT / "棋子头像总览.png"
    pygame.image.save(sheet, str(preview))
    print("总览图:", preview)


if __name__ == "__main__":
    main()
