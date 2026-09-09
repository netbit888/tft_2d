# -*- coding: utf-8 -*-
"""从 Riot Data Dragon 下载 TFT 装备官方图标到 assets/items/。

用法：
    python tools/fetch_item_icons.py

按仓库约定分类写入 assets/items/ 子目录（同名覆盖）：
    base/    散件：   <key>.png        如 base/sword.png、base/tear.png
    combine/ 成装：   <a>+<b>.png      如 combine/sword+glove.png
    special/ 特殊工具：gold_remover.png

自动挑选多个最新版本里中文名覆盖最全的版本；名称做宽松匹配并打印
“目标名 -> 官方名”对照表，便于人工核对。输出统一为 128x128。
"""
from __future__ import annotations

import difflib
import json
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

from core.dataio import load_json  # noqa: E402

DD = "https://ddragon.leagueoflegends.com"
OUT = ROOT / "assets" / "items"
SIZE = 128
UA = {"User-Agent": "Mozilla/5.0 (tft_2d asset fetch)"}
VERSION_CANDIDATES = 8  # 用最新的前 8 个版本依次挑选


def get(url: str):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def get_json(url: str):
    return json.loads(get(url).decode("utf-8"))


def norm(s: str) -> str:
    for ch in " ··—-—":
        s = s.replace(ch, "")
    return s


def build_targets() -> tuple[dict[str, str], set[str]]:
    """返回 ({文件名键: 中文名}, 基础件 id 集合)。"""
    d = load_json(ROOT / "data" / "items.json")
    t: dict[str, str] = {}
    for k, v in d["base"].items():
        t[k] = v["name"]
    for k, v in d["combine"].items():
        t[k] = v["name"]
    t["gold_remover"] = "金制拆卸器"
    return t, set(d["base"])


def match_item(target: str, entries: list[dict]) -> dict | None:
    """依次尝试：精确 -> 归一相等 -> difflib 近似，返回条目。"""
    names = [e.get("name", "") for e in entries]
    if target in names:
        return entries[names.index(target)]
    n = norm(target)
    for e in entries:
        if norm(e.get("name", "")) == n:
            return e
    cand = difflib.get_close_matches(target, names, n=1, cutoff=0.5)
    if cand:
        return entries[names.index(cand[0])]
    return None


def pick_version(targets: dict[str, str]) -> tuple[str, list[dict], list[str]]:
    vers = get_json(f"{DD}/api/versions.json")
    best: tuple[int, str, list[dict], list[str]] = (-1, "", [], [])
    for v in vers[:VERSION_CANDIDATES]:
        try:
            data = get_json(f"{DD}/cdn/{v}/data/zh_CN/tft-item.json").get("data", {})
        except Exception as e:  # noqa: BLE001
            print(f"[skip] {v}: {e!r:.60}")
            continue
        entries = list(data.values())
        miss = [t for t in targets.values() if match_item(t, entries) is None]
        print(f"版本 {v}: 命中 {len(targets) - len(miss)}/{len(targets)}"
              + (f"  缺: {'、'.join(miss)}" if miss else ""))
        if len(targets) - len(miss) > best[0]:
            best = (len(targets) - len(miss), v, entries, miss)
        if not miss:
            break
    return best[1], best[2], best[3]


def download_icon(entry: dict) -> bytes | None:
    full = entry.get("image", {}).get("full", "")
    if not full:
        return None
    url = f"{DD}/cdn/{version}/img/tft-item/{urllib.parse.quote(full, safe='-_ .')}"
    try:
        raw = get(url)
    except Exception as e:  # noqa: BLE001
        print(f"   [下载失败] {url}: {e!r:.60}")
        return None
    return raw if raw[:4] == b"\x89PNG" or raw[:2] in (b"\xff\xd8", b"BM") else None


def save_scaled(sub: str, name: str, raw: bytes) -> bool:
    folder = OUT / sub
    folder.mkdir(parents=True, exist_ok=True)
    try:
        tex = pygame.image.load(BytesIO(raw))
        if tex.get_size() != (SIZE, SIZE):
            tex = pygame.transform.smoothscale(tex, (SIZE, SIZE))
        pygame.image.save(tex, str(folder / name))
        return True
    except Exception as e:  # noqa: BLE001
        print(f"   [缩放失败] {name}: {e!r:.60}")
        folder.joinpath(name).write_bytes(raw)  # 兜底保存原尺寸
        return True


def main() -> None:
    global version
    if not pygame.get_init():
        import os
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        pygame.init()

    targets, base_ids = build_targets()
    print(f"共 {len(targets)} 件 (含金制拆卸器)\n[挑版本]")
    version, entries, _ = pick_version(targets)
    if not version:
        print("没有可用版本，中止。")
        sys.exit(1)
    print(f"\n选用版本 {version}，开始下载：")

    def subdir_of(key: str) -> str:
        if key == "gold_remover":
            return "special"
        return "base" if key in base_ids else "combine"

    used = {}
    ok = fail = 0
    for key, zh in targets.items():
        ent = match_item(zh, entries)
        fname = f"{key}.png"
        if ent is None:
            print(f"  [未匹配] {fname}  {zh}")
            fail += 1
            continue
        off = ent.get("name", "")
        if off in used and used[off] != key:
            print(f"  [重复?] {fname}  {zh} -> {off} (已被 {used[off]} 占用)")
        used[off] = key
        raw = download_icon(ent)
        if raw is None:
            print(f"  [失败] {fname}  {zh} -> {off}")
            fail += 1
            continue
        sub = subdir_of(key)
        if save_scaled(sub, fname, raw):
            print(f"  [OK] {sub}/{fname}  {zh} -> {off}")
            ok += 1

    print(f"\n完成: 成功 {ok}, 失败/未匹配 {fail}，输出目录 {OUT}")


if __name__ == "__main__":
    main()
