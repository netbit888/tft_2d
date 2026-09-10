"""AI 对战文字直播：逐回合展示 AI 买棋/升星/装备/战斗全过程。

用法：
    python tools/live_blog.py                    # 1v1
    python tools/live_blog.py --players 8        # 8 人局
    python tools/live_blog.py --seed 42          # 指定种子
    python tools/live_blog.py --slow             # 慢放（每回合停顿）
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from core import Game, load_traits, load_units  # noqa: E402
from core.ai import ai_equip, ai_take_turn, ai_upgrade_check  # noqa: E402
from core.events import EV_CAST, EV_DEATH, EV_END, EV_HEAL, format_event  # noqa: E402
from core.traits import count_traits_from_tids, describe  # noqa: E402


SEP = "=" * 70
SUB = "-" * 70


def run_all_ai_ops(game: Game) -> dict[str, list[str]]:
    """让所有 AI 运营一回合，返回 {玩家名: 操作日志列表}。"""
    result: dict[str, list[str]] = {}
    for i, p in enumerate(game.players):
        if not p.is_alive:
            continue
        logs: list[str] = []
        gold_before = p.gold
        level_before = p.level
        logs += ai_take_turn(p, game.shops[i], game.rng)
        logs += ai_equip(p, game.rng)
        ai_upgrade_check(p, game.round)
        if p.level > level_before:
            logs.append(f"升级到 Lv{p.level}（-{4 * (p.level - level_before)} 金）")
        result[p.name] = logs
    game.last_ai_log = []  # 清空，避免重复
    return result


def print_player_simple(p) -> None:
    """简洁打印玩家状态。"""
    templates = load_units()
    board_names = [f"{templates[p.tid].name}{'⭐'*p.star}" for p in p.board]
    bench_names = [f"{templates[p.tid].name}{'⭐'*p.star}" for p in p.bench]
    print(f"  💰 {p.gold:2d}金  📊Lv{p.level}  👥{p.board_pop}/{p.board_cap}  ❤️{p.hp:3d}HP")
    print(f"  ⚔️  场上({len(p.board)}): {' '.join(board_names[:6])}")
    if bench_names:
        print(f"  🪑 备战({len(p.bench)}): {' '.join(bench_names[:6])}")


def print_player_traits(p) -> None:
    """打印玩家激活的羁绊。"""
    templates = load_units()
    traits_data = load_traits()
    tids = [p.tid for p in p.board]
    if not tids:
        return
    traits = count_traits_from_tids(tids, templates)
    active = []
    for tid, count in sorted(traits.items()):
        tdef = traits_data.get(tid)
        if tdef:
            desc = describe(tdef, count)
            if desc:
                active.append(desc)
    if active:
        print(f"  🔗 羁绊: {' | '.join(active[:5])}")


def print_ops(logs: list[str]) -> None:
    """打印 AI 操作列表。"""
    if not logs:
        print("    （本回合无操作）")
        return
    for log in logs[:8]:
        print(f"    ▶ {log}")
    if len(logs) > 8:
        print(f"    ... 还有 {len(logs) - 8} 项")


def print_battle_summary(combat, blue_name: str, red_name: str) -> None:
    """打印战斗摘要。"""
    templates = load_units()

    deaths = [e for e in combat.events if e.type == EV_DEATH]
    casts = [e for e in combat.events if e.type == EV_CAST]
    end_event = next((e for e in combat.events if e.type == EV_END), None)

    # 统计双方阵亡
    blue_deaths = [e for e in deaths if e.data.get("team") == "blue"]
    red_deaths = [e for e in deaths if e.data.get("team") == "red"]

    winner = end_event.data.get("winner") if end_event else None
    winner_cn = blue_name if winner == "blue" else red_name if winner == "red" else "平局"

    print(f"  🏆 {winner_cn} 胜  |  ⏱️ {end_event.time:.1f}秒" if end_event else "")
    print(f"  💀 阵亡: {blue_name} {len(blue_deaths)}人 / {red_name} {len(red_deaths)}人")

    if casts:
        cast_names = list({e.data.get("ability", "") for e in casts})
        print(f"  ✨ 技能: {len(casts)}次释放（{', '.join(cast_names[:5])}）")

    if deaths:
        print(f"  阵亡名单:")
        for e in deaths[:6]:
            team_cn = blue_name if e.data["team"] == "blue" else red_name
            print(f"    - [{team_cn}] {e.data['name']}")
        if len(deaths) > 6:
            print(f"    ... 还有 {len(deaths) - 6} 人")


def live_blog_1v1(game: Game, slow: bool = False) -> None:
    """1v1 文字直播。"""
    game.begin_round()
    you = game.players[0]
    enemy = game.players[1]

    round_num = 1
    while not game.is_over():
        print()
        print(SEP)
        print(f"  🎮 回合 {game.round} / {game.MAX_ROUND}  （1v1）")
        print(SEP)
        print()

        # ---- 部署前状态 ----
        print("📋 【部署前】")
        print()
        print(f"  【{you.name}】")
        print_player_simple(you)
        print_player_traits(you)
        print()
        print(f"  【{enemy.name}】")
        print_player_simple(enemy)
        print_player_traits(enemy)
        print()

        if slow:
            time.sleep(0.8)

        # ---- AI 运营 ----
        print(SUB)
        print("🤖 【AI 运营】")
        print()
        ops = run_all_ai_ops(game)

        print(f"  【{you.name}】")
        print_ops(ops.get(you.name, []))
        print()
        print(f"  【{enemy.name}】")
        print_ops(ops.get(enemy.name, []))
        print(SUB)
        print()

        if slow:
            time.sleep(1.0)

        # ---- 战斗 ----
        print("⚔️  【战斗】")
        print()

        combat = game.start_battle()
        if combat is not None:
            result = combat.run()
            print_battle_summary(combat, you.name, enemy.name)
        print()

        # ---- 结算 ----
        outcome = game.finish_battle(combat)
        print(SUB)
        print(f"  📊 {outcome['settle_msg']}")
        if outcome["drops"]:
            print(f"  🎁 装备掉落: {len(outcome['drops'])} 件")
        if outcome["eliminated"]:
            names = [p.name for p in outcome["eliminated"]]
            print(f"  💀 淘汰: {', '.join(names)}")
        print(f"  ❤️  {you.name} {you.hp} HP   |   {enemy.name} {enemy.hp} HP")
        print(SUB)

        if outcome["over"]:
            print()
            print("🎊 游戏结束！")
            print(f"   {game.winner()}")
            print()
            break

        if slow:
            time.sleep(1.5)

        game.advance_round()


def live_blog_8p(game: Game, slow: bool = False) -> None:
    """8 人局文字直播。"""
    game.begin_round()
    templates = load_units()

    while not game.is_over():
        alive = [p for p in game.players if p.is_alive]

        print()
        print(SEP)
        print(f"  🎮 回合 {game.round} / {game.MAX_ROUND}  （{len(alive)} 人存活）")
        print(SEP)
        print()

        # ---- 血量排名 ----
        print("🏆 【血量排名】")
        ranked = sorted(game.players, key=lambda p: (-p.hp, -p.level))
        for i, p in enumerate(ranked):
            status = "❌" if not p.is_alive else "  "
            you_mark = " 👤" if p is game.players[0] else ""
            print(f"  {status} 第{i+1:2d}名{you_mark} {p.name:<6}  {p.hp:3d}HP  Lv{p.level}  场上{len(p.board)}人")
        print()

        if slow:
            time.sleep(0.5)

        # ---- AI 运营 ----
        print("🤖 【AI 运营】")
        print()
        ops = run_all_ai_ops(game)

        # 显示前 4 名玩家的操作
        alive_ranked = sorted([p for p in game.players if p.is_alive], key=lambda p: -p.hp)
        for p in alive_ranked[:4]:
            logs = ops.get(p.name, [])
            print(f"  【{p.name}】💰{p.gold}金 Lv{p.level}  场上{len(p.board)}人")
            print_ops(logs)
            print()

        if len(alive_ranked) > 4:
            print(f"  ... 还有 {len(alive_ranked) - 4} 位玩家在操作")
            print()

        if slow:
            time.sleep(1.0)

        # ---- 战斗 ----
        print("⚔️  【战斗】")
        print(f"  本回合 {len(game.pairings)} 组对战")
        print()

        combat = game.start_battle()  # AI 之间的战斗即时结算

        # 显示玩家本人的战斗（如果还活着）
        if game.players[0].is_alive and combat is not None:
            opp = game.players[game.current_opponent]
            print(f"  ━━ 你的比赛: {game.players[0].name} vs {opp.name} ━━")
            result = combat.run()
            print_battle_summary(combat, game.players[0].name, opp.name)
            print()
        elif not game.players[0].is_alive:
            print(f"  （你已被淘汰，继续观战中...）")
            print()

        # ---- 结算 ----
        outcome = game.finish_battle(combat)
        print(SUB)
        if outcome["eliminated"]:
            names = [p.name for p in outcome["eliminated"]]
            print(f"  💀 本回合淘汰: {', '.join(names)}")
        alive_now = sum(1 for p in game.players if p.is_alive)
        print(f"  剩余: {alive_now} 人")
        if game.players[0].is_alive:
            rank = sorted(game.players, key=lambda p: -p.hp).index(game.players[0]) + 1
            print(f"  你当前排名: 第 {rank} 名  ({game.players[0].hp} HP)")
        print(SUB)

        if outcome["over"]:
            print()
            print("🎊 游戏结束！")
            final_ranking = sorted(game.players, key=lambda p: (-p.hp, -p.level))
            for i, p in enumerate(final_ranking):
                medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else "  "
                print(f"   {medal} 第{i+1}名: {p.name:<6} ({p.hp:3d} HP, Lv{p.level})")
            print()
            break

        if slow:
            time.sleep(1.5)

        game.advance_round()


def main():
    ap = argparse.ArgumentParser(description="AI 对战文字直播")
    ap.add_argument("--seed", type=int, default=None, help="随机种子")
    ap.add_argument("--players", type=int, default=1, help="1=1v1, 8=8人局")
    ap.add_argument("--slow", action="store_true", help="慢放（每回合停顿）")
    args = ap.parse_args()

    num_players = max(2, int(args.players))
    if args.players == 1:
        num_players = 2

    game = Game(seed=args.seed, num_players=num_players)

    print(SEP)
    print("  🎮 TFT 2D - AI 对战文字直播")
    print(f"  模式: {'1v1' if num_players == 2 else f'{num_players}人局'}")
    if args.seed is not None:
        print(f"  种子: {args.seed}")
    print(SEP)
    print()
    print("  即将开始...")
    if args.slow:
        time.sleep(1.5)

    if num_players == 2:
        live_blog_1v1(game, slow=args.slow)
    else:
        live_blog_8p(game, slow=args.slow)

    print()
    print(SEP)
    print("  直播结束")
    print(SEP)


if __name__ == "__main__":
    main()
