"""图形界面入口：python app.py

无参数先进入游戏主页（HomeView），点“开始游戏”进 8 人局，对局结束回主页；
带 --players 参数直达对应模式（脚本/测试兼容：1=1v1，8=8 人局）。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import Game  # noqa: E402
from render.app import App  # noqa: E402
from render.home import ACTION_QUIT, MODE_START, HomeView  # noqa: E402


def _run_one(num_players: int, seed: int | None, scale: int | None, log: bool) -> None:
    """跑一局；结束（终局结算/ESC）即返回，pygame 生命周期交给外层。"""
    game = Game(seed=seed, num_players=num_players)
    game.begin_round()
    App(game, log_to_console=log, scale=scale).run()


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="自走棋图形界面（无参数进入游戏主页）")
    ap.add_argument("--seed", type=int, default=None, help="对局随机种子")
    ap.add_argument("--no-log", action="store_true", help="不在控制台打印战斗日志")
    ap.add_argument(
        "--scale",
        type=int,
        default=None,
        help="界面缩放因子（1=1280x800，2=2560x1600），不传默认 1x 小窗",
    )
    ap.add_argument(
        "--players",
        type=int,
        default=None,
        help="直达模式：1=1v1 对战，8=8 人局；不传则进入游戏主页（开始游戏=8 人局）",
    )
    args = ap.parse_args(argv)
    log = not args.no_log

    try:
        if args.players is not None:
            # 脚本/测试兼容：带 --players 直达对应模式，结束即退出程序
            _run_one(8 if args.players == 8 else 1, args.seed, args.scale, log)
            return

        # 无参数：主页 → 8 人局 → 回主页 循环
        while True:
            home = HomeView(scale=args.scale, seed=args.seed)
            action = home.run()
            if action in (ACTION_QUIT, None):
                break
            if action == MODE_START:
                _run_one(8, args.seed, args.scale, log)
    finally:
        import pygame

        pygame.quit()


if __name__ == "__main__":
    main()
