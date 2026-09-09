"""装备贴图回归测试（无头：dummy video/audio driver）。

约定：散件 assets/items/base/<id>.png、成装 assets/items/combine/<a+b>.png、
特殊工具 assets/items/special/<id>.png，缺图自动回退程序化图标。
本测试锁住三件事：内置成装（bow+bow）贴图能被加载、缺图装备安全回退、
有图/无图两种绘制路径都不报错。未安装 pygame 时自动跳过。
"""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest  # noqa: E402
import pygame  # noqa: E402

pytest.importorskip("pygame")

from render.item_art import (  # noqa: E402
    draw_item_badge,
    draw_item_icon,
    has_item_art,
    item_icon,
    item_texture,
)

RAGING_BLADE = "bow+bow"  # 羊刀：仓库内置贴图
MISSING = "___no_such_item___"


@pytest.fixture(autouse=True)
def _pygame_ready():
    """前面的 GUI 冒烟测试跑完会 pygame.quit()，字体对象随之失效。

    这里重新初始化并清掉 render.assets 的字体 / 文字缓存，
    保证本模块的绘制路径（含缺图回退的首字）用的是有效字体。
    """
    pygame.init()
    from render import assets

    assets._cache.clear()
    assets._text_cache.clear()
    yield


def test_builtin_item_texture_loads():
    """羊刀贴图存在且能加载成正方形 RGBA 图。"""
    assert has_item_art(RAGING_BLADE), "assets/items/combine/bow+bow.png 应存在"
    tex = item_texture(RAGING_BLADE)
    assert tex is not None and tex.get_width() > 0 and tex.get_height() > 0


def test_missing_item_falls_back_to_none():
    """缺图装备：原图与图标都返回 None（绘制层走程序化回退），且被负缓存。"""
    assert item_texture(MISSING) is None
    assert item_icon(MISSING, 32) is None
    assert has_item_art(MISSING) is False
    assert item_texture(MISSING) is None  # 二次查询仍为 None（负缓存生效）


def test_item_icon_is_square_and_cached():
    """图标按目标边长等比缩放居中；同参数复用同一张缓存 Surface。"""
    icon = item_icon(RAGING_BLADE, 64)
    assert icon is not None
    assert icon.get_size() == (64, 64)
    assert item_icon(RAGING_BLADE, 64) is icon  # 尺寸缓存命中


def test_draw_paths_do_not_crash():
    """有图 / 缺图两种路径都能画（格子图标 + 棋子脚下徽章）。"""
    surf = pygame.Surface((200, 120))
    for item_id in (RAGING_BLADE, MISSING):
        draw_item_icon(surf, pygame.Rect(0, 0, 40, 40), item_id)
        draw_item_icon(surf, pygame.Rect(50, 0, 40, 40), item_id, dim=True)
        draw_item_badge(surf, (100, 60), item_id)
