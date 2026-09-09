# -*- coding: utf-8 -*-
"""把棋子羁绊归属改为官方 S19 体系并重写 data/traits.json。

背景（方案 A）：引擎只同步官方「名称与归属」，官方羁绊效果一律标注未实现，
战斗不再有羁绊属性加成；原自设 9 羁绊（战士/护卫/法师/迅捷/刺客/骑士/猎手/统领）
停用并从数据中移除。

数据源（本地快照，先跑 tools/fetch_official_traits.py 生成）：
- tools/_jcc_raw/hero_18.18.1c-S19.json   官方英雄（species=种族id, class=职业id）
- tools/_jcc_raw/race_18.18.1c-S19.json   种族表
- tools/_jcc_raw/job_18.18.1c-S19.json    职业表

产物：
- data/units.json  每个棋子的 traits 改为官方羁绊 id 列表（种族在前、职业在后）
- data/traits.json 只含“我方棋子里实际出现的官方羁绊”，字段：
    name/kind(race|job)/levels(官方人数档)/color(官方稀有度)/desc/detail/implemented=false

用法：
    python tools/build_official_traits.py      # 写回 data/ 并打印对照
    python tools/build_official_traits.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAP = ROOT / "tools" / "_jcc_raw"

# 我方棋子名与官方名不一致的少数棋子（与 sync_official_stats 保持一致）
NAME_OVERRIDE = {
    "锋喙鸟": "深红锋喙鸟",
}

KIND_TAG = {  # 决定文档/显示顺序
    "job": "职业",
    "race": "种族",
}


def load_snap(tag: str) -> dict:
    cands = sorted(SNAP.glob(f"{tag}_*.json"))
    if not cands:
        print(f"!! 缺少 {tag}_*.json，先运行 tools/fetch_official_traits.py")
        sys.exit(1)
    print(f"[源] {cands[-1].name}")
    return json.loads(cands[-1].read_text(encoding="utf-8"))


def pick_official(recs) -> dict:
    """name -> 该英雄 1 星正式体（与 sync_official_stats 同规则）。"""
    out: dict[str, dict] = {}
    for r in recs:
        if str(r["id"]).startswith("1") and str(r.get("showHeroTag")) == "1":
            out[r["name"]] = r
    return out


def split_ids(v) -> list[str]:
    """'348|346' / 450 / -1 / None -> 正整数 id 列表（升序保序）。"""
    if v is None:
        return []
    out = []
    for part in str(v).split("|"):
        s = part.strip()
        if s.lstrip("-").isdigit() and int(s) > 0:
            out.append(str(int(s)))
    return out


def parse_levels(item: dict) -> list[int]:
    txt = str(item.get("numList") or item.get("num") or "")
    out = [int(x) for x in txt.split("|") if x.strip().isdigit() and int(x) > 0]
    return out


def clean(text) -> str:
    if not text:
        return ""
    return " ".join(str(text).replace("\n", " ").split())


# 官方文案里夹带的动态占位符/进度提示（无信息量，清洗时整句丢弃）
_DROP_MARKERS = (
    "选择一把武器", "已选择进化", "已赚取的金币", "已赚取",
    "下个商店", "参与击杀数", "当前：", "进度：", "种子：",
)


def humanize(text) -> str:
    """把官方一段长文案清洗成可读文本：去重复句、去占位符句。"""
    if not text:
        return ""
    seen: list[str] = []
    uniq: set[str] = set()
    for seg in re.split(r"[。！？!?]", str(text)):
        seg = seg.strip(" |\t\u3000（")
        if not seg:
            continue
        if any(m in seg for m in _DROP_MARKERS):
            continue
        if seg in uniq:
            continue
        uniq.add(seg)
        seen.append(seg)
    return "。".join(seen)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只打印不写盘")
    args = ap.parse_args()

    heroes = pick_official(load_snap("hero")["data"].values())
    race = load_snap("race")["data"]
    job = load_snap("job")["data"]
    print(f"[源] 官方 1 星正式体 {len(heroes)} 个，种族 {len(race)}，职业 {len(job)}")

    # 官方种族/职业 name 与 id 双向表
    name_of = {k: v["name"] for k, v in race.items()}
    name_of.update({k: v["name"] for k, v in job.items()})
    def_of = {k: ("race", v) for k, v in race.items()}
    def_of.update({k: ("job", v) for k, v in job.items()})

    units_src = ROOT / "data" / "units.json"
    units = json.loads(units_src.read_text(encoding="utf-8"))

    plan: list[dict] = []
    empty, missing_id = [], []
    for u in units:
        off = heroes.get(NAME_OVERRIDE.get(u["name"], u["name"]))
        if off is None:
            plan.append({"id": u["id"], "name": u["name"],
                         "old": u.get("traits", []), "new": []})
            empty.append((u["id"], u["name"]))
            continue
        tid = split_ids(off.get("species")) + split_ids(off.get("class"))
        bad = [i for i in tid if i not in def_of]
        if bad:
            missing_id.append((u["id"], u["name"], off["name"], bad))
        plan.append({"id": u["id"], "name": u["name"],
                     "old": u.get("traits", []), "new": tid})

    # ---- 输出对照 ----
    print(f"\n{'id':12s} {'名称':8s} 旧羁绊 -> 新羁绊")
    for p in plan:
        old = "、".join(p["old"]) or "—"
        new = "、".join(name_of.get(x, x) for x in p["new"]) or "（无官方归属）"
        flag = "" if p["new"] else "  <== 无匹配!"
        print(f"{p['id']:12s} {p['name']:8s} {old} -> {new}{flag}")
    if empty:
        print(f"\n!! 无官方英雄记录的棋子 {len(empty)} 个：{empty}")
    if missing_id:
        print(f"!! 引用了未知官方羁绊 id：{missing_id}")

    if args.dry_run:
        print("\n[dry-run] 未写盘。")
        return

    # ---- 写 units.json：仅替换 traits 数组 ----
    by_name_map = {p["id"]: p["new"] for p in plan}
    n_changed = 0
    for u in units:
        new_t = by_name_map[u["id"]]
        if u.get("traits", []) != new_t:
            u["traits"] = new_t
            n_changed += 1
    units_src.write_text(
        json.dumps(units, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\n[写盘] {units_src.name}：{n_changed} 个棋子更新 traits")

    # ---- 汇总我方用到哪些官方羁绊（保留 json 顺序=units 顺序，去重） ----
    used: list[str] = []
    for p in plan:
        for x in p["new"]:
            if x not in used:
                used.append(x)
    used.sort(key=lambda i: (def_of[i][0], int(i)))  # 种族在前、id 升序

    traits_out: dict[str, dict] = {}
    for i in used:
        kind, item = def_of[i]
        raw = item.get("prefix") or item.get("desc2") or ""
        traits_out[i] = {
            "name": item["name"],
            "kind": kind,
            "levels": parse_levels(item) or [1],
            "color": clean(item.get("color", "")),
            "desc": humanize(raw),
            "implemented": False,
        }

    traits_path = ROOT / "data" / "traits.json"
    traits_path.write_text(
        json.dumps(traits_out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"[写盘] {traits_path.name}：{len(traits_out)} 个官方羁绊（implemented=false）")

    # ---- 摘要 ----
    by_kind: dict[str, int] = {}
    for v in traits_out.values():
        by_kind[v["kind"]] = by_kind.get(v["kind"], 0) + 1
    print(f"  分布：{by_kind}；涉及棋子 {len([p for p in plan if p['new']])}/{len(plan)}")


if __name__ == "__main__":
    main()
