# -*- coding: utf-8 -*-
"""从 Riot Data Dragon 下载棋子头像到 assets/units/<tid>.png。

用法：
    python tools/fetch_unit_portraits.py

匹配规则：
- 遍历 data/units.json，以每枚棋子的中文名为准，与 ddragon zh_CN
  冠军数据 champion.json 的中文名做精确匹配；
- 个别棋子名与官方中文名不同（如 易 -> 易大师）在 KEY_OVERRIDE 里
  直接写死 champion key；
- 官方头像只覆盖召唤师英雄。野怪/原创棋子（峡谷迅捷蟹、魔沼蛙、
  远古石甲虫、苍蓝哨戒 等）不在 champion.json 中，自动跳过并打印，
  游戏内继续走已有的程序化首字回退，绝不硬凑。

下载后同时导出根目录 棋子头像总览.png（网格预览，便于一眼核对覆盖）。
输出统一放大为 256x256，游戏端按内圆圆形裁切后依旧清晰。
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import pygame  # noqa: E402

DD = "https://ddragon.leagueoflegends.com"
OUT = ROOT / "assets" / "units"
SIZE = 256
UA = {"User-Agent": "Mozilla/5.0 (tft_2d portrait fetch)"}

# 中文昵称与官方中文名不一致的少数棋子：{棋子名: champion key}
KEY_OVERRIDE = {
    "易": "MasterYi",  # 官方中文名显示为"易大师"
}


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def get_json(url: str):
    return json.loads(get(url).decode("utf-8"))


def load_units() -> list[dict]:
    return json.loads((ROOT / "data" / "units.json").read_text(encoding="utf-8"))


def resolve_champion(zh_name: str, data: dict, zh_index: dict) -> tuple[str, str] | None:
    """返回 (champion key, image full)。匹配失败返回 None。"""
    key = KEY_OVERRIDE.get(zh_name)
    if key is not None:
        ent = data.get(key)
        if ent is not None:
            return key, ent["image"]["full"]
        return None
    hit = zh_index.get(zh_name)
    if hit is None:
        return None
    key, ent = hit
    return key, ent["image"]["full"]


def save_avatar(tid: str, raw: bytes) -> bool:
    """校验图片并统一缩放到 SIZE，落盘 assets/units/<tid>.png。"""
    if raw[:4] != b"\x89PNG":
        return False
    try:
        tex = pygame.image.load(BytesIO(raw))
    except pygame.error as e:
        print(f"     [解码失败] {tid}: {e!r:.60}")
        return False
    if tex.get_size() != (SIZE, SIZE):
        tex = pygame.transform.smoothscale(tex, (SIZE, SIZE))
    pygame.image.save(tex, str(OUT / f"{tid}.png"))
    return True


def build_preview(units: list[dict], covered: set[str]) -> Path:
    """把所有有头像的棋子拼成一张网格总览图（根目录 棋子头像总览.png）。"""
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
        # 费用角标色块（1~5 费由浅到金）
        pygame.draw.rect(
            sheet, (35, 40, 55), (x, y + 24, cell, cell - 24), border_radius=8
        )
        if u["id"] in covered:
            tex = pygame.image.load(str(OUT / f"{u['id']}.png"))
            small = pygame.transform.smoothscale(tex, (icon, icon))
            sheet.blit(small, (x + (cell - icon) // 2, y + 24 + (cell - 24 - icon) // 2))
        else:
            pygame.draw.rect(
                sheet, (58, 62, 78), (x + 20, y + 40, cell - 40, cell - 40), border_radius=8
            )
        if label_font is not None:
            name = u["name"][:4]
            if len(u["name"]) > 4:
                name = u["name"][:3] + "…"
            img = label_font.render(name, True, (230, 232, 240))
            sheet.blit(img, img.get_rect(center=(x + cell // 2, y + 12)))
    path = ROOT / "棋子头像总览.png"
    pygame.image.save(sheet, str(path))
    return path


def main() -> None:
    if not pygame.get_init():
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        pygame.init()
    OUT.mkdir(parents=True, exist_ok=True)

    units = load_units()
    print(f"共 {len(units)} 枚棋子，读取最新 Data Dragon 冠军数据…")
    version = get_json(f"{DD}/api/versions.json")[0]
    ch = get_json(f"{DD}/cdn/{version}/data/zh_CN/champion.json").get("data", {})
    # 注意 ddragon zh_CN 的字段：name=称号（暗裔剑魔），title=短名（亚托克斯），
    # 游戏内昵称对齐短名，因此用 title 建立索引。
    zh_index: dict[str, tuple[str, dict]] = {}
    for k, e in ch.items():
        zh_index.setdefault(e["title"], (k, e))
    print(f"版本 {version}：官方冠军 {len(ch)} 个\n[下载]")

    covered: set[str] = set()
    ok = miss = 0
    for u in units:
        tid, zh = u["id"], u["name"]
        resolved = resolve_champion(zh, ch, zh_index)
        if resolved is None:
            print(f"  [跳过] {tid:14s} {zh}  ← 非英雄，保留程序化回退")
            miss += 1
            continue
        ckey, img = resolved
        url = f"{DD}/cdn/{version}/img/champion/{urllib.parse.quote(img, safe='-_ .')}"
        try:
            raw = get(url)
        except Exception as e:  # noqa: BLE001
            print(f"  [下载失败] {tid:14s} {zh} -> {ckey}: {e!r:.60}")
            miss += 1
            continue
        if not save_avatar(tid, raw):
            print(f"  [文件异常] {tid:14s} {zh} -> {ckey}")
            miss += 1
            continue
        covered.add(tid)
        print(f"  [OK] {tid:14s} {zh} -> {ckey} ({img})")
        ok += 1

    preview = build_preview(units, covered)
    print(f"\n完成：成功 {ok}，跳过/失败 {miss}；输出 {OUT}；总览 {preview}")


if __name__ == "__main__":
    main()
