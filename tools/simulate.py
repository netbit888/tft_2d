"""命令行战斗工具（M1）。

用法：
    python tools/simulate.py                 跑一场默认对局并打印日志
    python tools/simulate.py --seed 7        指定随机种子
    python tools/simulate.py --verbose       连移动事件也打印
    python tools/simulate.py --bench 1000    批量随机对局，输出棋子/羁绊胜率
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Windows 控制台默认是 GBK，这里强制 UTF-8，否则中文日志会乱码
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from core import Combat, build_team, load_traits, load_units  # noqa: E402
from core.events import LOG_DEFAULT, EV_MOVE, format_event  # noqa: E402
from core.grid import TEAM_ROWS  # noqa: E402
from core.traits import count_traits, describe  # noqa: E402

# 默认演示阵容：蓝方偏防守，红方偏爆发
DEFAULT_BLUE = [
    {"id": "ironwall", "star": 1, "pos": [2, 1]},
    {"id": "stonefist", "star": 1, "pos": [3, 1]},
    {"id": "sunarrow", "star": 1, "pos": [2, 0]},
    {"id": "pyro", "star": 1, "pos": [4, 0]},
]
DEFAULT_RED = [
    {"id": "wolfclaw", "star": 1, "pos": [2, 2]},
    {"id": "venom", "star": 1, "pos": [4, 2]},
    {"id": "frost", "star": 1, "pos": [3, 3]},
    {"id": "priest", "star": 1, "pos": [2, 3]},
]


def print_team(placements: list[dict], team: str) -> None:
    units = build_team(placements, team)
    traits_data = load_traits()
    label = "蓝方" if team == "blue" else "红方"
    print(f"\n{label}阵容：")
    for u in units:
        print(
            f"  {u.name:<4} {u.star}星  HP {u.max_hp:6.0f}  AD {u.ad:5.1f}  "
            f"攻速 {u.attack_speed:.2f}  射程 {u.attack_range}  "
            f"护甲 {u.armor:.0f}  魔抗 {u.magic_resist:.0f}  法强 {u.ap:.0f}"
        )
    lines = describe(count_traits(units), traits_data)
    print("  羁绊：" + ("，".join(lines) if lines else "无"))


def run_single(blue_pl, red_pl, seed: int | None, verbose: bool = False) -> None:
    blue = build_team(blue_pl, "blue")
    red = build_team(red_pl, "red")

    print("=" * 60)
    print_team(blue_pl, "blue")
    print_team(red_pl, "red")

    combat = Combat(blue, red, seed=seed)
    result = combat.run()

    print("\n战斗过程：")
    shown = LOG_DEFAULT if not verbose else None
    for e in combat.events:
        if shown is None or e.type in shown or (verbose and e.type == EV_MOVE):
            print("  " + format_event(e))

    print("\n" + "=" * 60)
    text = {"blue": "蓝方胜利", "red": "红方胜利", None: "平局"}[result.winner]
    print(f"结果：{text}   用时 {result.ticks / 20:.2f}s")
    print(
        f"存活：蓝方 {result.survivors['blue']} 人（剩余血量 {result.hp_left['blue']:.0f}） / "
        f"红方 {result.survivors['red']} 人（剩余血量 {result.hp_left['red']:.0f}）"
    )
    if result.timeout:
        print("注意：本场超时，按剩余血量比例判定")


def random_placements(rng: random.Random, team: str, pool: list[str], size: int) -> list[dict]:
    """随机布阵：近战放前排，远程放后排，列不重复。"""
    picks = rng.sample(pool, size)
    front_row, back_row = TEAM_ROWS[team]["front"], TEAM_ROWS[team]["back"]
    cols = rng.sample(range(7), size)
    templates = load_units()
    out = []
    for uid, col in zip(picks, cols):
        tpl = templates[uid]
        row = back_row if tpl.attack_range > 1 else front_row
        out.append({"id": uid, "star": 1, "pos": [col, row]})
    return out


def run_bench(n: int, seed: int, size: int = 4) -> None:
    rng = random.Random(seed)
    pool = list(load_units().keys())
    names = {k: v.name for k, v in load_units().items()}

    games: dict[str, int] = {k: 0 for k in pool}
    wins: dict[str, int] = {k: 0 for k in pool}
    durations: list[float] = []
    draws = 0
    timeouts = 0
    blue_wins = 0

    for _ in range(n):
        bp = random_placements(rng, "blue", pool, size)
        rp = random_placements(rng, "red", pool, size)
        combat = Combat(
            build_team(bp, "blue"),
            build_team(rp, "red"),
            seed=rng.randint(0, 2**31 - 1),
        )
        r = combat.run()
        durations.append(r.ticks / 20)
        if r.timeout:
            timeouts += 1
        if r.winner is None:
            draws += 1
        for p, team in [(p, "blue") for p in bp] + [(p, "red") for p in rp]:
            games[p["id"]] += 1
        if r.winner == "blue":
            blue_wins += 1
            for p in bp:
                wins[p["id"]] += 1
        elif r.winner == "red":
            for p in rp:
                wins[p["id"]] += 1

    print(f"\n批量对局 {n} 场（每方 {size} 个棋子，种子 {seed}）")
    print("-" * 52)
    print(f"{'棋子':<6}{'出场':>6}{'胜场':>6}{'胜率':>9}")
    rows = sorted(pool, key=lambda k: -(wins[k] / games[k] if games[k] else 0))
    for k in rows:
        if not games[k]:
            continue
        rate = wins[k] / games[k]
        print(f"{names[k]:<6}{games[k]:>6}{wins[k]:>6}{rate:>8.1%}")
    print("-" * 52)
    print(f"平均战斗时长：{sum(durations) / len(durations):.2f}s")
    print(f"平局率：{draws / n:.1%}   超时率：{timeouts / n:.1%}   蓝方（先手方）胜率：{blue_wins / n:.1%}")


def run_mirror(n: int, seed: int, size: int = 4) -> None:
    """镜像自检：双方棋子与站位完全对称，胜率理论上应各占 50%。

    若明显偏离 50%，说明战斗内核存在方向性偏差（行动顺序、坐标、判定顺序等），
    这是必须先修的 bug，而不是数值平衡问题。
    """
    rng = random.Random(seed)
    pool = list(load_units().keys())
    tpls = load_units()
    stat = {"blue": 0, "red": 0, "draw": 0}
    durations: list[float] = []

    for _ in range(n):
        picks = rng.sample(pool, size)
        cols = rng.sample(range(7), size)
        bp, rp = [], []
        for uid, col in zip(picks, cols):
            slot = "back" if tpls[uid].attack_range > 1 else "front"
            bp.append({"id": uid, "star": 1, "pos": [col, TEAM_ROWS["blue"][slot]]})
            rp.append({"id": uid, "star": 1, "pos": [col, TEAM_ROWS["red"][slot]]})  # 上下镜像

        r = Combat(
            build_team(bp, "blue"), build_team(rp, "red"), seed=rng.randint(0, 2**31 - 1)
        ).run()
        stat[r.winner or "draw"] += 1
        durations.append(r.ticks / 20)

    print(f"\n镜像自检 {n} 场（双方阵容与站位完全对称，种子 {seed}）")
    print("-" * 52)
    print(f"蓝方胜 {stat['blue'] / n:.1%}   红方胜 {stat['red'] / n:.1%}   平局 {stat['draw'] / n:.1%}")
    print(f"平均战斗时长：{sum(durations) / len(durations):.2f}s")
    print("判定：两侧差距应在 ±3% 内，否则内核存在方向性 bug")


def main() -> None:
    ap = argparse.ArgumentParser(description="自走棋战斗模拟器（M1 内核）")
    ap.add_argument("--seed", type=int, default=42, help="战斗随机种子")
    ap.add_argument("--verbose", action="store_true", help="打印移动事件")
    ap.add_argument("--bench", type=int, metavar="N", help="批量跑 N 场随机对局做平衡统计")
    ap.add_argument("--mirror", type=int, metavar="N", help="跑 N 场镜像对称局做内核自检")
    ap.add_argument("--size", type=int, default=4, help="批量对局每方棋子数量")
    args = ap.parse_args()

    if args.bench:
        run_bench(args.bench, args.seed, args.size)
    elif args.mirror:
        run_mirror(args.mirror, args.seed, args.size)
    else:
        run_single(DEFAULT_BLUE, DEFAULT_RED, args.seed, args.verbose)


if __name__ == "__main__":
    main()
