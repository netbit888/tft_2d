"""图形界面入口：python app.py

操作：点商店卡片购买 -> 从备战席拖到棋盘上场 -> 点开战。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import Game  # noqa: E402
from render.app import App  # noqa: E402


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="自走棋 1v1 图形界面")
    ap.add_argument("--seed", type=int, default=None, help="对局随机种子")
    ap.add_argument("--no-log", action="store_true", help="不在控制台打印战斗日志")
    ap.add_argument(
        "--scale",
        type=int,
        default=None,
        help="界面缩放因子（1=1280x800，2=2560x1600），不传则按屏幕自动选择",
    )
    ap.add_argument(
        "--players",
        type=int,
        default=1,
        help="玩家数量（1=1v1 对战，8=8 人局）",
    )
    args = ap.parse_args(argv)

    game = Game(seed=args.seed, num_players=args.players)
    game.begin_round()
    App(game, log_to_console=not args.no_log, scale=args.scale).run()


if __name__ == "__main__":
    main()
