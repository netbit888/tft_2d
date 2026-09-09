"""图形界面冒烟测试（无头：dummy video/audio driver）。

覆盖 App 构造 → 购买/升级 → 开战（战斗回放分支）与 F2 装备自选台双页，
用于在重构 UI 层后快速确认状态机与核心驱动仍能串起来。未安装 pygame 时自动跳过。
pygame 生命周期由模块级 fixture 统一收尾：中途 quit 会令已缓存的字体对象失效，
导致后续用例报 "font module quit"。
"""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest  # noqa: E402
import pygame  # noqa: E402

pytest.importorskip("pygame")


@pytest.fixture(scope="module", autouse=True)
def _pygame_lifecycle():
    """模块内所有用例跑完后统一清理，避免中途 quit 破坏字体/贴图缓存。"""
    yield
    pygame.quit()


def _make_app():
    from core import Game
    from render.app import App

    game = Game(seed=3)
    game.begin_round()
    app = App(game, log_to_console=False, scale=1)
    return app


def test_app_deploy_and_battle_flow():
    app = _make_app()
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


def test_armory_two_tabs():
    """F2 自选台双页：打开（成装页）→ 切到散件页 → 点格子获得基础装备，两页均可绘制。"""
    from core.items import ItemInstance, is_base_item

    from render.armory_view import armory_entries, armory_geometry

    app = _make_app()
    # F2 打开自选台：默认在成装页（37 项）
    app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F2))
    assert app.armory_open and app.armory_tab == 0
    assert len(armory_entries(0)) == 37

    # 点顶部「散件」tab 切页
    tab1 = armory_geometry(0)["tabs"][1]
    app.handle_event(
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=tab1["rect"].center)
    )
    assert app.armory_tab == 1
    base_entries = armory_entries(1)
    assert len(base_entries) == 8

    # 点散件页第一格：获得一件基础装备
    before = len(app.game.you.item_bench)
    first = armory_geometry(1)["cells"][0]
    app.handle_event(
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=first["rect"].center)
    )
    assert len(app.game.you.item_bench) == before + 1
    got = app.game.you.item_bench[-1]
    assert got.item_id == base_entries[0]
    assert is_base_item(got.item_id) and isinstance(got, ItemInstance)

    # 成装页 / 散件页各画一帧不出错
    app.armory_tab = 0
    app.draw()
    app.armory_tab = 1
    app.draw()

    # ESC 关闭
    app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    assert not app.armory_open
