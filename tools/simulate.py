"""命令行战斗工具（M1）。

用法：
    python tools/simulate.py                 跑一场默认对局并打印日志
    python tools/simulate.py --seed 7        指定随机种子
    python tools/simulate.py --verbose       连移动事件也打印
    python tools/simulate.py --bench 1000    批量随机对局，输出棋子/羁绊胜率
    python tools/simulate.py --mirror 200    镜像对称局自检（内核方向性偏差检测）
    python tools/simulate.py --fullgame 20 --players 8
                                            8 人局全自动整局仿真（走经济/运营/配对）
    python tools/simulate.py --check         校验 data/*.json 数据完整性
"""

from __future__ import annotations

import argparse
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Windows 控制台默认是 GBK，这里强制 UTF-8，否则中文日志会乱码
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from core import Combat, Game, build_team, load_traits, load_units  # noqa: E402
from core.dataio import check_data  # noqa: E402
from core.events import LOG_DEFAULT, EV_MOVE, format_event  # noqa: E402
from core.grid import AUTO_ROW_ORDER  # noqa: E402
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
    front_row, back_row = AUTO_ROW_ORDER[team]["front"][0], AUTO_ROW_ORDER[team]["back"][0]
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
            bp.append({"id": uid, "star": 1, "pos": [col, AUTO_ROW_ORDER["blue"][slot][0]]})
            # 六边形奇偶行错半格：纵向镜像时列号需取 6-col 才是真正的棋盘镜像
            rp.append({"id": uid, "star": 1, "pos": [6 - col, AUTO_ROW_ORDER["red"][slot][0]]})

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


def run_fullgame(matches: int, seed: int, players: int) -> None:
    """整局全自动仿真：所有玩家由 AI 运营（含经济/升级/配对/装备掉落）。

    输出：
    - 名次分布（第 0 位玩家，便于看站位公平性）
    - 平均回合数与平均存活人数（节奏是否健康）
    - 全玩家场上出场占用最多的棋子（谁在主导环境）

    对局的每一回合由 Game.play_auto_match 驱动——与 GUI/CLI 完全同源，
    因此这里的统计能代表真实对局体验。
    """
    rng = random.Random(seed)
    placements: Counter = Counter()  # 第 0 位玩家的名次分布
    durations: list[int] = []
    alive_rounds = 0  # “存活玩家回合”总次数（利用率分母）
    fielded: Counter = Counter()  # 棋子被放在场上的总次数
    rounds_total = 0

    def placements_of(g: Game) -> list[int]:
        """按血量(再按等级)从强到弱返回玩家下标。"""
        return [
            i for i, _ in sorted(enumerate(g.players), key=lambda t: (-t[1].hp, -t[1].level))
        ]

    for _ in range(matches):
        game = Game(seed=rng.randint(0, 2**31 - 1), num_players=players)
        last_rank = None

        def collect(g: Game, outcome: dict) -> None:
            nonlocal last_rank, alive_rounds
            last_rank = placements_of(g)
            alive_rounds += sum(1 for p in g.players if p.is_alive)
            for p in g.players:
                if p.is_alive:
                    for pc in p.board:
                        fielded[pc.tid] += 1

        game.play_auto_match(on_round=collect)
        rank = last_rank or placements_of(game)
        placements[rank.index(0) + 1] += 1
        durations.append(game.round)
        rounds_total += game.round

    names = {k: v.name for k, v in load_units().items()}
    print(f"\n{players} 人整局全 AI 仿真 {matches} 场（种子 {seed}）")
    print("-" * 56)
    rank_str = " ".join(f"{i}名{placements.get(i, 0)}场" for i in range(1, players + 1))
    print(f"第 0 位玩家名次分布：{rank_str}")
    print(f"平均对局回合数：{sum(durations) / len(durations):.1f}")
    print(f"平均每回合存活玩家：{alive_rounds / max(rounds_total, 1):.2f}")
    print("-" * 56)
    print(f"{'棋子':<6}{'场均携带数':>10}{'定位':>20}")
    top = fielded.most_common(10)
    denom = max(alive_rounds, 1)
    for k, v in top:
        print(f"{names.get(k, k):<6}{v / denom:>9.2f}    ~环境主导单位")
    if fielded:
        min_v = min(fielded.values())
        low = [k for k, _ in fielded.items() if fielded[k] == min_v][:5]
        for k in low:
            print(f"{names.get(k, k):<6}{min_v / denom:>9.2f}    ~几乎无人使用")
    print("-" * 56)


def run_data_check() -> int:
    """校验 data/*.json，有问题返回非 0 退出码（供脚本/CI 门禁）。"""
    errors = check_data()
    if not errors:
        print("数据自检通过：traits / units / level / pool / items 均无问题。")
        return 0
    print(f"数据自检发现 {len(errors)} 个问题：")
    for e in errors:
        print("  - " + e)
    return 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="自走棋战斗模拟器（M1 内核）")
    ap.add_argument("--seed", type=int, default=42, help="战斗随机种子")
    ap.add_argument("--verbose", action="store_true", help="打印移动事件")
    ap.add_argument("--bench", type=int, metavar="N", help="批量跑 N 场随机对局做平衡统计")
    ap.add_argument("--mirror", type=int, metavar="N", help="跑 N 场镜像对称局做内核自检")
    ap.add_argument("--fullgame", type=int, metavar="N", help="跑 N 场整局全自动仿真（玩家也由 AI 运营）")
    ap.add_argument("--players", type=int, default=8, help="整局仿真的玩家人数（默认 8）")
    ap.add_argument("--size", type=int, default=4, help="批量对局每方棋子数量")
    ap.add_argument("--check", action="store_true", help="校验 data/*.json 数据完整性")
    args = ap.parse_args(argv)

    if args.check:
        return run_data_check()
    elif args.fullgame:
        run_fullgame(args.fullgame, args.seed, args.players)
    elif args.bench:
        run_bench(args.bench, args.seed, args.size)
    elif args.mirror:
        run_mirror(args.mirror, args.seed, args.size)
    else:
        run_single(DEFAULT_BLUE, DEFAULT_RED, args.seed, args.verbose)
    return 0


if __name__ == "__main__":
    sys.exit(main())
