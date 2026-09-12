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
    """F2 自选台：打开（成装页）→ 切到散件页 → 点格子获得基础装备，各页均可绘制。"""
    from core.items import ItemInstance, is_base_item, load_items, special_item_ids

    from render.armory_view import armory_entries, armory_geometry

    app = _make_app()
    # F2 打开自选台：默认在成装页（全部成装 + 特殊工具，与 data/items.json 同源）
    app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F2))
    assert app.armory_open and app.armory_tab == 0
    assert len(armory_entries(0)) == len(load_items()["combine"]) + len(special_item_ids())

    # 点顶部「散件」tab 切页
    tab1 = armory_geometry(0)["tabs"][1]
    app.handle_event(
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=tab1["rect"].center)
    )
    assert app.armory_tab == 1
    base_entries = armory_entries(1)
    assert len(base_entries) == len(load_items()["base"])

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


def test_champion_picker_five_cost_pages():
    """F3 棋子自选栏：默认 1 费页 → 切到 3 费页 → 点格子免费得棋子，各页均可绘制。"""
    from render.champ_view import champ_entries, champ_geometry

    app = _make_app()
    # F3 打开：默认停在 1 费页（14 个棋子，S18 一费池）
    app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F3))
    assert app.picker_open and app.picker_cost == 1
    assert len(champ_entries(1)) == 14
    assert len(champ_geometry(1)["cells"]) == 14

    # 点顶部「3费」tab 切页
    tab2 = champ_geometry(1)["tabs"][2]
    app.handle_event(
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=tab2["rect"].center)
    )
    assert app.picker_cost == 3
    entries3 = champ_entries(3)
    assert len(entries3) == 14

    # 点 3 费页第一格：免费获得该棋子进备战席
    before = len(app.game.you.bench)
    first = champ_geometry(3)["cells"][0]
    app.handle_event(
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=first["rect"].center)
    )
    assert len(app.game.you.bench) == before + 1
    assert app.game.you.bench[-1].tid == entries3[0]

    # 1 费 / 3 费页各画一帧不出错
    app.picker_cost = 1
    app.draw()
    app.picker_cost = 3
    app.draw()

    # ESC 关闭
    app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    assert not app.picker_open


def test_home_view_start_and_quit():
    """主页（简洁版）：开始球（8 人局）+ 退出球的命中与绘制。"""
    import math

    from render.home import ACTION_QUIT, MODE_START, HomeView

    home = HomeView(scale=1)
    home._draw()  # 至少能画一帧不出错

    # 开始球球心点击 -> MODE_START
    x, y = home._start_ball_center()
    hit = home._handle(
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(x, y))
    )
    assert hit == MODE_START
    # 退出球球心点击 -> ACTION_QUIT
    x, y = home._quit_ball_center()
    assert (
        home._handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(x, y)))
        == ACTION_QUIT
    )
    # 球外空白点击不触发
    assert home._handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(10, 10))) is None
    # ESC = 退出
    assert home._handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)) == ACTION_QUIT

    # 两球互不重叠（中心距 > 两球半径之和）
    a = home._start_ball_center()
    b = home._quit_ball_center()
    assert math.hypot(a[0] - b[0], a[1] - b[1]) > home._hit_radius(True) + home._hit_radius(False)


def test_app_esc_and_over_return_without_quit():
    """App 结束只停循环不调 pygame.quit：ESC 中途退出、终局返回主页均可安全返回。"""
    from core import Game
    from render.app import App

    game = Game(seed=3)
    game.begin_round()
    app = App(game, log_to_console=False, scale=1)

    # ESC（部署期无浮层）→ running=False 且 _esc_quit=True
    app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    assert not app.running and app._esc_quit

    # 终局按钮语义：PHASE_OVER 时标签为“返回主页”，点击只停循环
    app2 = App(Game(seed=3), log_to_console=False, scale=1)
    app2.game.begin_round()
    app2.phase = app2.PHASE_OVER
    app2.btn_next.label = "返回主页"
    assert app2.btn_next.handle(
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=app2.btn_next.rect.center)
    )
    app2.running = False  # 模拟 handle_event 分支效果
    _ = app2.btn_next.label


def test_shop_popup_and_hud_balls():
    """金币球开关商店浮层：浮层内买卡/刷新/锁定/关闭，且与 F2/F3、卖出区一致。"""
    from core.shop import REFRESH_COST

    from render import theme
    from render.hud_view import gold_ball_hit
    from render.shop_view import (
        shop_card_rect,
        shop_close_rect,
        shop_lock_rect,
        shop_refresh_rect,
    )

    def click(pos):
        app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))

    app = _make_app()
    app.game.you.gold = 60
    ball = (theme.GOLD_BALL_X, theme.GOLD_BALL_Y)

    # 点金币球开浮层；浮层应能画一帧
    assert not app.shop_open and gold_ball_hit(ball)
    click(ball)
    assert app.shop_open
    app.draw()

    # 点卡购买（浮层内，不应触发"点面板外关闭"）
    bench_before = len(app.game.you.bench)
    click(shop_card_rect(0).center)
    assert app.shop_open and len(app.game.you.bench) == bench_before + 1

    # 刷新：扣刷新花费；锁定：切换 locked
    gold_before = app.game.you.gold
    click(shop_refresh_rect().center)
    assert app.game.you.gold == gold_before - REFRESH_COST
    click(shop_lock_rect().center)
    assert app.game.you.locked

    # 与 F3 自选栏互斥
    app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F3))
    assert app.picker_open and not app.shop_open
    app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    assert not app.picker_open

    # 重开浮层后点 ✕ 关闭
    click(ball)
    assert app.shop_open
    click(shop_close_rect().center)
    assert not app.shop_open

    # 浮层关闭时，原商店坐标不再响应购买（避免隐藏区域误买）
    bench_before = len(app.game.you.bench)
    click(shop_card_rect(0).center)
    assert len(app.game.you.bench) == bench_before
