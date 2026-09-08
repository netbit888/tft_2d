"""图形界面冒烟测试（无头：dummy video/audio driver）。

覆盖 App 构造 → 购买/升级 → 开战（战斗回放分支），用于在重构 UI 层后
快速确认状态机与核心驱动仍能串起来。未安装 pygame 时自动跳过。
"""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest  # noqa: E402
import pygame  # noqa: E402

pytest.importorskip("pygame")


def _make_app():
    from core import Game
    from render.app import App

    game = Game(seed=3)
    game.begin_round()
    app = App(game, log_to_console=False, scale=1)
    return app


def test_app_deploy_and_battle_flow():
    app = _make_app()
    try:
        app.game.you.gold = 60
        app._do_upgrade()  # 买经验：升级到 2 级
        assert app.game.you.level >= 2

        app.buy_card(0)  # 买一张卡进备战席
        app.game.you.promote_from_bench()  # 上场
        assert app.game.you.board

        app.start_battle()  # 应进入战斗回放（而非直接结算）
        assert app.phase == app.PHASE_BATTLE
        assert app.battle is not None
        app.draw()  # 至少能画一帧不出错
    finally:
        pygame.quit()
