"""命令行对局入口：你（blue）对战人机（red）。

玩法：每回合刷商店 -> 你购买/卖出 -> 电脑自动运营 -> 自动开战 -> 输方扣血 -> 下一回合。
先手打空对方 100 血即获胜。

用法：
    python play.py            随机开局
    python play.py --seed 7   指定种子（便于复现同一局）
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from core import (  # noqa: E402
    Game,
    buy,
    load_traits,
    load_units,
    refresh_shop,
    sell,
)
from core.events import (  # noqa: E402
    EV_CAST,
    EV_DEATH,
    EV_END,
    EV_HEAL,
    EV_MOVE,
    format_event,
)
from core.player import piece_label  # noqa: E402
from core.traits import count_traits_from_tids, describe  # noqa: E402

LINE = "=" * 60
SUBLINE = "-" * 60


def clear() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def trait_panel(tids: list[str]) -> str:
    counts = count_traits_from_tids(tids, load_units())
    lines = describe(counts, load_traits())
    return "，".join(lines) if lines else "无"


def render(game: Game, message: str = "") -> None:
    clear()
    you, foe = game.you, game.enemy
    print(LINE)
    print(f" 回合 {game.round}        你 {you.hp} HP  |  电脑 {foe.hp} HP  |  金币 {you.gold}")
    print(LINE)

    print(f"你的阵容（人口 {you.board_pop}/{you.board_cap}）：")
    if you.board:
        for i, p in enumerate(you.board, 1):
            print(f"  {i}. {piece_label(p)}")
    else:
        print("  （空）")
    print(f"  羁绊：{trait_panel([p.tid for p in you.board])}")

    if you.bench:
        print(f"备战席：{'，'.join(piece_label(p) for p in you.bench)}")

    print(f"\n电脑阵容（人口 {foe.board_pop}/{foe.board_cap}）：")
    print("  " + ("，".join(piece_label(p) for p in foe.board) if foe.board else "（空）"))
    print(f"  羁绊：{trait_panel([p.tid for p in foe.board])}")

    print(SUBLINE)
    print(f"商店（刷新 2 金）：")
    owned = {p.tid for p in you.board} | {p.tid for p in you.bench}
    traits_data = load_traits()
    for i, item in enumerate(game.shop_you.slots, 1):
        if item.sold:
            print(f"  [{i}] --- 已购入")
        else:
            tpl = load_units()[item.tid]
            names = "/".join(traits_data.get(t, {}).get("name", t) for t in tpl.traits)
            dup = "  [已拥有]" if item.tid in owned else ""
            print(f"  [{i}] {tpl.name:<4} {item.cost}金  {names}{dup}")
    print(SUBLINE)
    print("操作：[1-5]购买  [r]刷新  [s序号]卖出(如 s1)  [回车]开战  [q]退出")
    if message:
        print(f">> {message}")


def print_log(combat, full: bool = False) -> None:
    for e in combat.events:
        if e.type == EV_MOVE:
            continue
        if not full and e.type not in (EV_CAST, EV_HEAL, EV_DEATH, EV_END):
            continue
        print("  " + format_event(e))


def ask(prompt: str) -> str:
    """读取一行输入；输入流关闭时按退出处理，避免抛 EOFError。"""
    try:
        return input(prompt).strip().lower()
    except EOFError:
        return "q"


def battle_phase(game: Game, interactive: bool = True) -> None:
    """战斗阶段：AI 运营 → 补位/配对（AI 互打即时结算）→ 玩家对局 → 结算。

    走的是 core.Game 的“单一真源”流程，与图形界面、无头仿真完全一致。
    """
    print(SUBLINE)
    logs = game.run_ai_ops()
    if logs:
        print("电脑的运营：" + "；".join(logs))

    combat = game.start_battle()
    if combat is None:
        print("\n（有一方没有上场棋子，跳过战斗）")
    else:
        combat.run()

    outcome = game.finish_battle(combat)
    print(outcome["settle_msg"])

    if combat is not None:
        print("--- 战斗日志 ---")
        print_log(combat)
        print("--- 战斗结束 ---")

    if combat is not None and interactive:
        cmd = ask("\n回车继续，输入 v 查看完整战斗日志 > ")
        if cmd == "v":
            clear()
            print_log(combat, full=True)
            ask("\n回车继续 > ")


def auto_play(game: Game) -> None:
    """双方都由 AI 运营，走 Game.play_auto_match 整局驱动器跑完（自测/平衡用）。"""

    def on_round(g: Game, outcome: dict) -> None:
        msg = outcome["settle_msg"]
        print(
            f"回合 {outcome['round']:>2} | 你 {g.you.hp:>3} HP"
            f"  电脑 {g.enemy.hp:>3} HP | {msg}"
        )

    summary = game.play_auto_match(on_round=on_round)
    print(LINE)
    print(f" 对局结束：{game.winner()}")
    print(f" 共 {summary['rounds']} 回合")
    print(LINE)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="自走棋 1v1 命令行对局")
    ap.add_argument("--seed", type=int, default=None, help="对局随机种子")
    ap.add_argument("--auto", action="store_true", help="双方均由 AI 操作，自动跑完整局")
    args = ap.parse_args(argv)

    game = Game(seed=args.seed)
    if args.auto:
        auto_play(game)
        return

    message = ""
    game.begin_round()  # 第 1 回合发初始金币 + 刷商店

    while not game.is_over():
        # ---- 玩家运营 ----
        while True:
            render(game, message)
            message = ""
            cmd = ask("操作 > ")

            if cmd in ("", "f", "fight"):
                break
            if cmd in ("q", "quit", "exit"):
                print("已退出对局。")
                return
            if cmd == "r":
                message = refresh_shop(game.you, game.shop_you)
            elif cmd.startswith("s") and cmd[1:].isdigit():
                message = sell(game.you, int(cmd[1:]))
            elif cmd.isdigit():
                message = buy(game.you, game.shop_you, int(cmd) - 1)
                # 命令行没有拖拽，买了直接上场（图形界面是手动拖）
                game.you.promote_from_bench()
            else:
                message = "无法识别的操作"

        # ---- 战斗阶段（AI 运营 + 开战 + 结算，全部在 Game 内完成）----
        battle_phase(game)
        if game.is_over() or game.round >= game.MAX_ROUND:
            break
        game.advance_round()

    clear()
    print(LINE)
    print(f" 对局结束：{game.winner()}")
    print(f" 最终比分：你 {game.you.hp} HP  |  电脑 {game.enemy.hp} HP  （共 {game.round} 回合）")
    print(LINE)


if __name__ == "__main__":
    main()
