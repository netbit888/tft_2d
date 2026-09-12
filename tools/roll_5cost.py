"""验证：10 级时能否（以及多大概率）D 出 3 星 5 费。

直接复用真实游戏内核（core.Shop / core.Pool / core.Player / core.shop.buy），
不做任何概率重写——这里的数字就是游戏里真实会发生的。

用法：
    python tools/roll_5cost.py                跑默认场景并打印概率表
    python tools/roll_5cost.py --trials 5000  每场景蒙特卡洛次数（默认 3000）
    python tools/roll_5cost.py --gold 50 100 150 200 250 300  指定金币预算扫点

机制速查（全部来自真实代码）：
    10 级商店概率 {1费:3, 2费:7, 3费:18, 4费:37, 5费:35}，刷新 2 金 / 次，共 5 槽位。
    5 费卡池每种 9 张（共享），3 星需同棋子 9 张 → 必须把 9 张全拿到。
    商店在该费用内均匀抽一个不同棋子 id（shop.py: rng.choice(tiers[cost])），
    故满池时单槽位目标 5 费概率 = 35% × 1/10 = 3.5%。
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from core import (  # noqa: E402
    REFRESH_COST,
    Player,
    Pool,
    Rng,
    Shop,
    buy,
    load_units,
    refresh_shop,
)
from core.player import odds_for_level  # noqa: E402

TARGET = "s18_elderdragon"  # 远古巨龙；任意 5 费均可，概率结构完全相同
FIVE_COST_IDS = [tid for tid, tpl in load_units().items() if tpl.cost == 5]
N_FIVE = len(FIVE_COST_IDS)  # 10
COST_5 = 5


def per_slot_prob(level: int, distinct_five: int) -> float:
    """单槽位刷出目标 5 费的概率 = 5 费档概率 × 1/该档内不同 5 费数。"""
    return (odds_for_level(level)[5] / 100.0) / distinct_five


def expected_refreshes(level: int, distinct_five: int) -> float:
    """9 张的理论期望刷新次数（负二项均值）。"""
    p_slot = per_slot_prob(level, distinct_five)
    return 9.0 / (Shop.SIZE * p_slot)


def make_pool(target_left: int = 9, others_to_zero: int = 0) -> Pool:
    """构造卡池：

    - target_left：目标剩余张数（<9 时 3 星不可能）；
    - others_to_zero：把前 others_to_zero 个其它 5 费置 0（模拟被同行买空，缩桶）。
    """
    pool = Pool.create()
    pool.remaining[TARGET] = min(target_left, pool.capacity[TARGET])
    others = [t for t in FIVE_COST_IDS if t != TARGET]
    for t in others[:others_to_zero]:
        pool.remaining[t] = 0
    return pool


def simulate_once(
    gold: int,
    level: int = 10,
    target_left: int = 9,
    others_to_zero: int = 0,
    seed: int | None = None,
) -> dict:
    """单次试验：预算内反复刷新并购买目标，返回是否 3 星及消耗。"""
    rng = Rng(seed)
    pool = make_pool(target_left, others_to_zero)
    player = Player("tester", level=level, gold=gold, pool=pool)
    shop = Shop(rng, pool)

    copies = 0
    refreshes = 0
    gold_spent = 0
    while player.gold >= REFRESH_COST and copies < 9:
        refresh_shop(player, shop)
        refreshes += 1
        gold_spent += REFRESH_COST
        for idx, item in shop.available():
            if item.tid == TARGET and player.gold >= item.cost:
                buy(player, shop, idx)
                copies += 1
                gold_spent += item.cost

    star3 = any(
        p.tid == TARGET and p.star == 3 for p in player.board + player.bench
    )
    return {
        "success": star3,
        "copies": copies,
        "refreshes": refreshes,
        "gold_spent": gold_spent,
    }


def run_trials(gold, trials, seed_base=0, **kw) -> dict:
    wins = 0
    refresh_list: list[int] = []
    gold_list: list[int] = []
    for i in range(trials):
        r = simulate_once(gold, seed=seed_base + i, **kw)
        if r["success"]:
            wins += 1
            refresh_list.append(r["refreshes"])
            gold_list.append(r["gold_spent"])
    n = len(refresh_list)
    return {
        "success_rate": wins / trials,
        "median_refresh": statistics.median(refresh_list) if n else float("nan"),
        "median_gold": statistics.median(gold_list) if n else float("nan"),
        "p90_refresh": sorted(refresh_list)[int(n * 0.9) - 1] if n else float("nan"),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="10 级 D 出 3 星 5 费的概率验证")
    ap.add_argument("--trials", type=int, default=3000, help="每场景蒙特卡洛次数")
    ap.add_argument("--gold", type=int, nargs="+", default=[50, 100, 150, 200, 250, 300])
    ap.add_argument("--seed", type=int, default=20240912)
    args = ap.parse_args(argv)

    bar = "=" * 78
    print(bar)
    print("机制速查（来自真实代码）")
    print(bar)
    print(f"10 级商店概率：1费3% / 2费7% / 3费18% / 4费37% / 5费35%")
    print(f"刷新 {REFRESH_COST} 金/次，共 {Shop.SIZE} 槽位；5 费 {N_FIVE} 种、每种 9 张、单价 {COST_5} 金；3 星需同棋子 9 张")
    print(f"满池单槽位目标 5 费概率 = 35% × 1/{N_FIVE} = {per_slot_prob(10, N_FIVE):.2%}")
    print(f"满池单次刷新期望张数 = 5 × {per_slot_prob(10, N_FIVE):.4f} = {5*per_slot_prob(10, N_FIVE):.3f} 张")
    print(f"9 张理论期望刷新 ≈ {expected_refreshes(10, N_FIVE):.1f} 次，期望花费 ≈ {expected_refreshes(10, N_FIVE)*REFRESH_COST + 9*COST_5:.0f} 金")
    print()

    # 场景 1：满池、只 D 目标，金币预算扫点
    print(bar)
    print(f"场景 1：10 级 · 满池 · 只 D 目标 · 各 {args.trials} 次")
    print(bar)
    print(f"{'金币预算':>8} {'3星成功率':>10} {'成功中位刷新':>12} {'成功中位花费':>12} {'成功90%刷新':>12}")
    for g in args.gold:
        r = run_trials(g, args.trials, seed_base=args.seed)
        print(
            f"{g:>8} {r['success_rate']:>10.2%} {r['median_refresh']:>12.1f} "
            f"{r['median_gold']:>12.0f} {r['p90_refresh']:>12.0f}"
        )
    print()

    # 场景 2：目标被抢（硬上限）
    print(bar)
    print("场景 2：目标被同行抢走部分张数（10 级 · 其它 5 费满 · 300 金）")
    print(bar)
    for left in (9, 8, 7, 5, 3):
        r = run_trials(300, args.trials, seed_base=args.seed, target_left=left)
        verdict = "可能" if r["success_rate"] > 0 else "不可能（硬上限）"
        print(f"目标剩余 {left}/9 → 3 星成功率 {r['success_rate']:.2%}  {verdict}")
    print()

    # 场景 3：缩桶——其它 5 费被买空，桶内 5 费种类变少
    print(bar)
    print("场景 3：其它 5 费被买空、桶内种类变少（10 级 · 目标 9/9 · 100 金 · 只 D 目标）")
    print(bar)
    print(f"{'桶内不同5费数':>12} {'单槽位目标概率':>14} {'理论期望刷新':>12} {'3星成功率':>10}")
    for distinct in (10, 5, 3, 2, 1):
        others_to_zero = N_FIVE - distinct  # 桶内 distinct 种 = 目标 1 + 其它 distinct-1
        r = run_trials(100, args.trials, seed_base=args.seed, others_to_zero=others_to_zero)
        print(
            f"{distinct:>12} {per_slot_prob(10, distinct):>14.2%} "
            f"{expected_refreshes(10, distinct):>12.1f} {r['success_rate']:>10.2%}"
        )
    print()

    # 场景 4：等级对比
    print(bar)
    print(f"场景 4：不同等级下满池 D 目标（300 金 · 只 D 目标 · 各 {args.trials} 次）")
    print(bar)
    print(f"{'等级':>6} {'5费概率':>8} {'单槽位目标概率':>14} {'3星成功率':>10}")
    for lv in (8, 9, 10):
        r = run_trials(300, args.trials, seed_base=args.seed, level=lv)
        print(f"{lv:>6} {odds_for_level(lv)[5]:>6}% {per_slot_prob(lv, N_FIVE):>14.2%} {r['success_rate']:>10.2%}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
