"""AI 观战模式：所有玩家（包括"你"）都由 AI 自动运营，自动推进回合。

用法：
    python app_auto.py                 # 1v1 AI 观战
    python app_auto.py --players 8     # 8 人局 AI 观战
    python app_auto.py --seed 7        # 指定种子（可复现）
    python app_auto.py --speed 2.0     # 加速（每回合结算后停留时间，默认 1.5 秒）

作为模块被 app.py 复用时（主页“AI 观战”入口）：对局结束只停本循环，
由外层菜单循环决定回到主页还是退出。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pygame

from core import Game
from render.app import App
from render import theme


class AutoApp(App):
    """自动观战版 App：部署阶段自动让 AI 运营并开战，结算后自动下一回合。"""

    def __init__(
        self,
        game: Game,
        log_to_console: bool = True,
        scale: int | None = None,
        result_delay: float = 1.5,
        fullscreen: bool = True,
    ) -> None:
        super().__init__(game, log_to_console=log_to_console, scale=scale, fullscreen=fullscreen)
        pygame.display.set_caption(f"自走棋 AI 观战  ({theme.WINDOW_W}x{theme.WINDOW_H})")
        self.result_delay = result_delay  # 结算画面停留秒数
        self._deploy_delay = 0.8  # 部署阶段停留秒数（让你看到 AI 买了什么）
        self._auto_timer = 0.0
        self._auto_state = "deploy_wait"  # deploy_wait → battle → result_wait → over

    def update(self, dt: float) -> None:
        super().update(dt)

        # 自动推进状态机
        if self.phase == self.PHASE_DEPLOY:
            self._auto_timer += dt
            if self._auto_timer >= self._deploy_delay:
                self._auto_timer = 0.0
                self._auto_start_battle()
        elif self.phase == self.PHASE_RESULT:
            self._auto_timer += dt
            if self._auto_timer >= self.result_delay:
                self._auto_timer = 0.0
                self.next_round()
        elif self.phase == self.PHASE_OVER:
            # 游戏结束，停留一会儿后退出
            self._auto_timer += dt
            if self._auto_timer >= 5.0:
                self.running = False

    def _auto_start_battle(self) -> None:
        """AI 运营玩家位，然后开战。"""
        g = self.game
        # 让玩家位（索引 0）也由 AI 运营一回合
        from core.ai import ai_equip, ai_take_turn, ai_upgrade_check

        p = g.players[0]
        if p.is_alive:
            ai_take_turn(p, g.shops[0], g.rng)
            ai_equip(p, g.rng)
            ai_upgrade_check(p, g.round)

        # 其余 AI 正常运营（通过 run_ai_ops，但跳过玩家 0 因为我们已经手动跑过了）
        # 直接调用 start_battle 里会再调 run_ai_ops，所以我们改成手动流程
        # 为了不破坏原有结构，我们用一个小技巧：先 drive 玩家，再调 start_battle
        # 但 start_battle 里的 run_ai_ops 不会重复跑玩家 0（drive_player 默认 False）
        # 所以我们直接调 start_battle 即可——它会跑 AI（不含玩家0）然后开战
        # 而玩家 0 我们已经在上面手动跑过了
        self.start_battle()


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="自走棋 AI 观战模式（全自动）")
    ap.add_argument("--seed", type=int, default=None, help="对局随机种子")
    ap.add_argument("--no-log", action="store_true", help="不在控制台打印战斗日志")
    ap.add_argument(
        "--scale",
        type=int,
        default=None,
        help="界面缩放因子（1=1280x800，2=2560x1600），不传默认 2x（更清晰）",
    )
    ap.add_argument(
        "--windowed",
        action="store_true",
        help="用普通窗口而非默认全屏",
    )
    ap.add_argument(
        "--players",
        type=int,
        default=1,
        help="玩家数量（1=1v1 对战，8=8 人局）",
    )
    ap.add_argument(
        "--speed",
        type=float,
        default=1.5,
        help="结算画面停留秒数（越大越慢，默认 1.5）",
    )
    args = ap.parse_args(argv)

    num_players = max(2, int(args.players))
    if args.players == 1:
        num_players = 2

    game = Game(seed=args.seed, num_players=num_players)
    game.begin_round()
    try:
        AutoApp(
            game,
            log_to_console=not args.no_log,
            scale=args.scale,
            result_delay=args.speed,
            fullscreen=not args.windowed,
        ).run()
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
