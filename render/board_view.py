"""棋盘与棋子的绘制。

坐标说明：core 里己方（blue）占 row 0-3（屏幕下半）、敌方（red）占 row 4-7（屏幕上半）；
绘制时把行号翻转（display_row = 7 - core_row），让己方显示在下半部分。

棋盘画成蜂窝六边形：尖顶六边形逐列排开，相邻行整体错半格（odd-r 偏移）。
core 的战斗/摆位仍按 7x8 行列逻辑坐标算，绘制层只负责把 (col,row) 翻译成屏幕点，
命中判定改为点是否落在对应六边形内。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import pygame

from core.loader import load_traits, load_units

from . import theme
from .assets import font, text_shadow
from .item_art import draw_item_badge
from .widgets import bar, hp_color

# ---------- 坐标换算（蜂窝六边形，odd-r + 2.5D 透视） ----------

_COS30 = 0.86602540378


def core_row_to_display(core_row: int) -> int:
    return theme.BOARD_ROWS - 1 - core_row


def display_row_to_core(display_row: int) -> int:
    return theme.BOARD_ROWS - 1 - display_row


def row_scale(disp: float) -> float:
    """屏幕行的透视缩放：disp=0 最远（顶部）→ PERSP_FAR，disp=ROWS-1 最近 → PERSP_NEAR。"""
    n1 = max(1, theme.BOARD_ROWS - 1)
    t = min(1.0, max(0.0, disp / n1))
    return theme.PERSP_FAR + (theme.PERSP_NEAR - theme.PERSP_FAR) * t


def scale_at(core_row: float) -> float:
    """core 行坐标（允许浮点，战斗插值用）所在深度的透视缩放。"""
    return row_scale(theme.BOARD_ROWS - 1 - core_row)


def _persp_row_y(disp: float) -> float:
    """纵向按缩放积分：近处行距大、远处行距小；disp 连续可微，战斗滑行平滑。"""
    n1 = max(1, theme.BOARD_ROWS - 1)
    d = min(float(n1), max(0.0, disp))
    return theme.HEX_ROW_STEP * (
        theme.PERSP_FAR * d + (theme.PERSP_NEAR - theme.PERSP_FAR) * d * d / (2 * n1)
    )


def hex_point(col: float, core_row: float) -> tuple[float, float]:
    """core 坐标 -> 屏幕坐标，col/core_row 允许是浮点（战斗插值用）。

    2.5D 透视：横向以棋盘中轴为灭点轴按行缩放收敛（近宽远窄），
    纵向行距随缩放积分排布；行错位仍用余弦在整数行之间平滑过渡。
    """
    disp = theme.BOARD_ROWS - 1 - core_row
    sc = row_scale(disp)
    # 偶数行错 0、奇数行错半列，行间用余弦平滑过渡
    shift = theme.HEX_COL_STEP * 0.5 * (0.5 - 0.5 * math.cos(math.pi * disp))
    x_base = theme.BOARD_X + theme.HEX_COL_STEP * (col + 1.0) + shift
    center_x = theme.BOARD_X + theme.BOARD_W / 2
    x = center_x + (x_base - center_x) * sc
    y = theme.BOARD_Y + theme.HEX_R * theme.PERSP_FAR + _persp_row_y(disp)
    return x, y


def cell_center(col: int, core_row: int) -> tuple[int, int]:
    """某个格子中心的屏幕坐标（传 core 坐标）。"""
    x, y = hex_point(float(col), float(core_row))
    return int(round(x)), int(round(y))


def cell_rect(col: int, core_row: int) -> pygame.Rect:
    """某个格子的屏幕包围盒（传 core 坐标），棋子按它居中绘制；尺寸随深度缩放。"""
    cx, cy = cell_center(col, core_row)
    size = max(8, int(theme.CELL * row_scale(theme.BOARD_ROWS - 1 - core_row)))
    return pygame.Rect(cx - size // 2, cy - size // 2, size, size)


def cell_rect_at(col: float, core_row: float) -> pygame.Rect:
    """浮点坐标处的透视格子矩形（战斗插值用：尺寸跟随所在深度的缩放）。"""
    x, y = hex_point(col, core_row)
    size = max(8, int(theme.CELL * scale_at(core_row)))
    return pygame.Rect(int(x) - size // 2, int(y) - size // 2, size, size)


def cell_polygon(col: int, core_row: int, shrink: int = 0) -> list[tuple[int, int]]:
    """尖顶六边形的六个顶点（从最上点顺时针），返回整数坐标；半径随深度缩放。"""
    cx, cy = cell_center(col, core_row)
    sc = row_scale(theme.BOARD_ROWS - 1 - core_row)
    r = max(1, int(round(theme.HEX_R * sc - theme.TILE_INSET - shrink)))
    w = int(round(_COS30 * r))
    half = (r + 1) // 2
    return [
        (cx, cy - r),
        (cx + w, cy - half),
        (cx + w, cy + half),
        (cx, cy + r),
        (cx - w, cy + half),
        (cx - w, cy - half),
    ]


def _in_polygon(px: float, py: float, pts) -> bool:
    """射线法点是否在多边形内。"""
    inside = False
    n = len(pts)
    j = n - 1
    for i in range(n):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if (yi > py) != (yj > py):
            cross = (xj - xi) * (py - yi) / ((yj - yi) or 1e-9) + xi
            if px < cross:
                inside = not inside
        j = i
    return inside


def cell_at(pos) -> tuple[int, int] | None:
    """屏幕坐标 -> (col, core_row)，不在任何六边形内返回 None。

    全量遍历 56 个六边形做包含测试，逻辑简单、不会漏边角。
    """
    x, y = pos
    for core_row in range(theme.BOARD_ROWS):
        for col in range(theme.BOARD_COLS):
            if _in_polygon(x, y, cell_polygon(col, core_row)):
                return col, core_row
    return None


# ---------- 棋子外观 ----------


@dataclass
class PieceVisual:
    """绘制一个棋子所需的全部信息（与 core 的数据结构解耦）。"""

    name: str
    team: str  # blue / red
    tag: str  # 职业单字，如"战"
    tag_color: tuple
    hp_ratio: float = 1.0
    mana_ratio: float = 0.0
    star: int = 1
    alive: bool = True
    tid: str = ""
    cost: int = 1
    show_bars: bool = False  # 只有战斗阶段画血条/蓝条


def trait_color(tid: str) -> tuple:
    """羁绊色：官方同步的用 color 稀有度（1灰~5金）映射 RARITY 边缘色，其余回退。"""
    info = load_traits().get(tid)
    if info is None:
        return theme.TRAIT_FALLBACK
    spec = str(info.get("color", ""))
    digits = [
        int(x) for x in spec.split("|")
        if x.strip().lstrip("-").isdigit() and int(x) > 0
    ]
    rarity_level = max(digits) if digits else 0
    if rarity_level in theme.RARITY:
        return theme.RARITY[rarity_level]["edge"]
    return theme.TRAIT_FALLBACK


def trait_tag(traits: tuple[str, ...]) -> tuple[str, tuple]:
    """取第一个羁绊作为角标（单字 + 颜色）。"""
    if not traits:
        return "兵", theme.TRAIT_FALLBACK
    traits_data = load_traits()
    tid = traits[0]
    name = traits_data.get(tid, {}).get("name", tid)
    return name[0], trait_color(tid)


def visual_from_tid(tid: str, star: int, team: str) -> PieceVisual:
    tpl = load_units()[tid]
    tag, color = trait_tag(tpl.traits)
    return PieceVisual(
        name=tpl.name, team=team, tag=tag, tag_color=color, star=star, tid=tid, cost=tpl.cost
    )


def visual_from_piece(piece, team: str) -> PieceVisual:
    """从玩家棋子构造外观（运营阶段用）。"""
    return visual_from_tid(piece.tid, piece.star, team)


def visual_from_unit(unit) -> PieceVisual:
    """从战斗单位构造外观（战斗阶段用）。"""
    tpl = load_units()[unit.tid]
    tag, color = trait_tag(tpl.traits)
    return PieceVisual(
        name=unit.name,
        team=unit.team,
        tag=tag,
        tag_color=color,
        hp_ratio=unit.hp_ratio,
        mana_ratio=(unit.mana / unit.max_mana if unit.max_mana else 0.0),
        star=unit.star,
        alive=unit.alive,
        tid=unit.tid,
        cost=tpl.cost,
        show_bars=True,
    )


# ---------- 头像（静态，全部缓存） ----------

# SSAA：棋盘/头像/闪光盘这类静态资产，先在 _SSAA_FACTOR 倍分辨率上绘制
# 再平滑缩小，消除 pygame.draw 几何边缘的锯齿。只在缓存生成时多花一次时间，每帧零开销。
_SSAA_FACTOR = 2

_AVATAR_CACHE: dict[tuple, pygame.Surface] = {}
_FLASH_CACHE: dict[int, pygame.Surface] = {}

# 棋子贴图：assets/units/<tid>.png（与 units.json 的 id 对齐）。
# 有图时头像核心用贴图内嵌，缺图自动回退程序化头像，文件缺失只探测一次（负缓存）。
_UNIT_TEX_DIR = Path(__file__).resolve().parent.parent / "assets" / "units"
_TEX_CACHE: dict[str, pygame.Surface | None] = {}


def _avatar_texture(tid: str) -> pygame.Surface | None:
    """加载棋子贴图；无文件/加载失败返回 None 并负缓存，不阻塞游戏。"""
    if tid in _TEX_CACHE:
        return _TEX_CACHE[tid]
    tex = None
    path = _UNIT_TEX_DIR / f"{tid}.png"
    if path.is_file():
        try:
            raw = pygame.image.load(str(path))
        except pygame.error:
            raw = None
        if raw is not None:
            try:
                tex = raw.convert_alpha()
            except pygame.error:
                tex = raw  # 视频未初始化等场景：原图含透明通道也可直接使用
    _TEX_CACHE[tid] = tex
    return tex


def _clear_caches() -> None:
    _AVATAR_CACHE.clear()
    _FLASH_CACHE.clear()
    _TEX_CACHE.clear()
    _SHOP_ART_CACHE.clear()
    _GRID_CACHE.clear()
    _SHADOW_CACHE.clear()


def _avatar(v: PieceVisual, size: int) -> pygame.Surface:
    """生成一个棋子头像：队伍光环 + 稀有度描边 + 星级，核心为贴图或程序首字。

    棋子在一局里外观不变（除了星级和生死），所以整张图缓存下来，
    每帧只做一次 blit，高分辨率下这是最大的一笔性能节省。

    贴图规则（有图显图，没图按原先方式显示）：
    - assets/units/<tid>.png 存在：头像核心用贴图圆形裁切内嵌；
    - 缺图 / 阵亡：回退“渐变底 + 首字”程序化头像，观感与旧版一致。

    SSAA：先在 _SSAA_FACTOR 倍分辨率上绘制，再平滑缩小回目标尺寸，
    让圆边/圆环/渐变这些 pygame.draw 几何的边缘不带锯齿。
    """
    key = (v.tid, v.star, v.team, size, v.alive)
    cached = _AVATAR_CACHE.get(key)
    if cached is not None:
        return cached

    ss = _SSAA_FACTOR
    tex = _avatar_texture(v.tid) if v.alive else None  # 阵亡强制走灰色程序头像
    hi = _avatar_raw(v, size * ss, theme.S * ss, tex)
    img = hi if ss <= 1 else pygame.transform.smoothscale(hi, (size, size))
    _AVATAR_CACHE[key] = img
    return img


def _paste_texture_core(
    surf: pygame.Surface, c: tuple[int, int], inner_r: int, tex: pygame.Surface
) -> None:
    """把棋子贴图缩放到内圆并圆形裁切，贴进头像核心。

    mask 用 per-pixel alpha 相乘把圆外裁成透明；本层画在 SSAA 高分辨率
    surface 上，最后随整图平滑缩小，圆形边缘不带锯齿。
    """
    d = max(2, inner_r * 2)
    if tex.get_size() == (d, d):
        img = tex
    else:
        img = pygame.transform.smoothscale(tex, (d, d))
    mask = pygame.Surface((d, d), pygame.SRCALPHA)
    pygame.draw.circle(mask, (255, 255, 255, 255), (d // 2, d // 2), d // 2)
    img = img.copy()
    img.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    surf.blit(img, (c[0] - d // 2, c[1] - d // 2))


def _avatar_raw(
    v: PieceVisual, size: int, s: int, tex: pygame.Surface | None = None
) -> pygame.Surface:
    """绘制头像主体；s 是线宽/偏移的基准缩放（SSAA 时同步放大）。

    tex 提供时核心用贴图（不再画渐变底与首字），否则沿用程序化几何头像；
    队伍光环 / 稀有度描边 / 星级环 / 顶部金星在两种模式下都保留。
    """
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    c = (size // 2, size // 2)
    r = size // 2
    team_color = theme.TEAM_COLORS.get(v.team, theme.TRAIT_FALLBACK)
    if not v.alive:
        team_color = (96, 99, 110)

    # 队伍光环（外圈），用来在棋盘上一眼区分敌我
    pygame.draw.circle(surf, theme.shade(team_color, 0.55), c, r)
    pygame.draw.circle(surf, (10, 11, 15), c, r - max(1, 2 * s))

    inner_r = r - max(2, 3 * s)
    if tex is not None and inner_r >= 1:
        # 有贴图：圆形裁切内嵌
        _paste_texture_core(surf, c, inner_r, tex)
    elif inner_r > 2:
        # 无贴图回退：羁绊色渐变底（一圈圈同心圆近似径向渐变）
        trait = v.tag_color
        outer = theme.mix(trait, (18, 20, 27), 0.55)
        bright = theme.mix(trait, (255, 255, 255), 0.32)
        if not v.alive:
            outer = (52, 54, 62)
            bright = (96, 99, 110)
        steps = max(6, inner_r // 3)
        for i in range(steps):
            t = i / max(1, steps - 1)
            rr = int(inner_r * (1 - i / steps))
            if rr <= 0:
                break
            pygame.draw.circle(surf, theme.mix(outer, bright, t), c, rr)

    # 稀有度描边 + 星级环（画在核心之上，贴图/渐变两种模式都可见）
    rar = theme.rarity(v.cost)
    pygame.draw.circle(surf, rar["edge"], c, r - s, width=max(2, 3 * s))
    star_ring = theme.STAR_RING.get(v.star)
    if star_ring:
        pygame.draw.circle(surf, star_ring, c, r - max(3, 4 * s), width=max(1, 2 * s))

    # 首字：仅无贴图时绘制（贴图本身已提供形象）
    if v.name and tex is None and inner_r > 2:
        fs = max(10, int(size * 0.52))
        glyph = v.name[0]
        dark = font(fs).render(glyph, True, (12, 13, 18))
        light = font(fs).render(glyph, True, (255, 255, 255) if v.alive else (170, 173, 182))
        surf.blit(dark, (c[0] - dark.get_width() // 2, c[1] - dark.get_height() // 2 + max(1, s)))
        surf.blit(light, (c[0] - light.get_width() // 2, c[1] - light.get_height() // 2))

    # 星级（顶部一排金星）
    if v.star > 1:
        pip = max(2, int(size * 0.075))
        gap = int(pip * 2.2)
        total = (v.star - 1) * gap
        py = c[1] - r - max(2, 2 * s)
        for i in range(v.star):
            px = c[0] - total // 2 + i * gap
            pygame.draw.circle(surf, (12, 13, 18), (px, py), pip + max(1, s))
            pygame.draw.circle(surf, theme.GOLD, (px, py), pip)

    return surf


def _flash_disc(size: int) -> pygame.Surface:
    """受击闪白用的白色圆盘，按尺寸缓存（同样做 SSAA，边缘平滑）。"""
    cached = _FLASH_CACHE.get(size)
    if cached is None:
        ss = _SSAA_FACTOR
        hi = pygame.Surface((size * ss, size * ss), pygame.SRCALPHA)
        pygame.draw.circle(
            hi, (255, 255, 255, 255), (size * ss // 2, size * ss // 2), size * ss // 2
        )
        cached = hi if ss <= 1 else pygame.transform.smoothscale(hi, (size, size))
        _FLASH_CACHE[size] = cached
    return cached


# ---------- 立式棋子（2.5D billboard） ----------

_SHADOW_CACHE: dict[int, pygame.Surface] = {}


def _shadow_ellipse(size: int) -> pygame.Surface:
    """棋子脚下的椭圆落地阴影，按尺寸缓存（SSAA 平滑边缘）。"""
    cached = _SHADOW_CACHE.get(size)
    if cached is None:
        ss = _SSAA_FACTOR
        w = max(4, size)
        h = max(3, int(size * 0.30))
        hi = pygame.Surface((w * ss, h * ss), pygame.SRCALPHA)
        pygame.draw.ellipse(hi, (0, 0, 0, 105), hi.get_rect())
        cached = hi if ss <= 1 else pygame.transform.smoothscale(hi, (w, h))
        _SHADOW_CACHE[size] = cached
    return cached


def piece_lift(size: int) -> int:
    """立式棋子相对格心的上移量（脚下留出阴影位）。"""
    return int(size * theme.PIECE_LIFT)


def piece_feet_y(rect: pygame.Rect) -> int:
    """立式棋子脚底（头像下缘）的 y：装备徽章基线跟着它走，绘制与命中共用。"""
    size = piece_size(rect)
    return rect.centery + size // 2 - piece_lift(size)


def piece_size(rect: pygame.Rect, scale: float = 1.0) -> int:
    return max(8, int(min(rect.width, rect.height) * theme.PIECE_RATIO * scale))


# ---------- 商店卡卡面（整卡立绘，静态缓存） ----------

# 商店卡片不画棋盘那种小圆头像，而是把贴图按“填满卡片”的构图铺开：
# - 有贴图：原图等比放大至 cover 整卡，居中裁掉溢出部分，不变形；
# - 无贴图：稀有度纵向渐变铺底 + 放大程序头像，等补图后无缝切换；
# - 底部压一条渐暗带放名字，保证任何亮色立绘下都可读；
# - 整卡按圆角裁切，整张静态缓存，每帧只 blit 一次。
_SHOP_ART_CACHE: dict[tuple, pygame.Surface] = {}


def shop_card_art(tid: str, size: tuple[int, int], radius: int = 0) -> pygame.Surface:
    """生成并缓存一张商店卡的静态主体（底图 + 底部名字带）。"""
    key = (tid, size[0], size[1], radius)
    cached = _SHOP_ART_CACHE.get(key)
    if cached is not None:
        return cached

    w, h = size
    layer = pygame.Surface(size, pygame.SRCALPHA)
    tpl = load_units()[tid]
    tex = _avatar_texture(tid)

    if tex is not None:
        # 有贴图：cover 铺满，居中裁边，不拉伸变形
        tw, th = tex.get_size()
        scale = max(w / tw, h / th)
        cw, ch = max(1, int(round(tw * scale))), max(1, int(round(th * scale)))
        img = pygame.transform.smoothscale(tex, (cw, ch)) if (cw, ch) != (tw, th) else tex
        layer.blit(img, ((w - cw) // 2, (h - ch) // 2))
    else:
        # 无贴图：整卡按稀有度做纵向渐变，中央放大程序头像（与棋盘同源）
        v = visual_from_tid(tid, 1, "blue")
        rar = theme.rarity(tpl.cost)
        top = theme.mix(rar["fill"], (255, 255, 255), 0.06)
        bottom = theme.mix(rar["fill"], (8, 10, 15), 0.82)
        for yy in range(h):
            t = yy / max(1, h - 1)
            pygame.draw.line(layer, theme.mix(top, bottom, t), (0, yy), (w - 1, yy))

        d = max(10, int(h * 0.66))
        cx, cy = w // 2, int(h * 0.46)
        # 头像先从渐变里“浮”出来：一圈柔和暗衬 + 落影
        pygame.draw.circle(layer, (0, 0, 0, 26), (cx, cy + 2), d // 2 + 5)
        pygame.draw.circle(layer, (0, 0, 0, 46), (cx, cy + 2), d // 2 + 2)
        pygame.draw.circle(layer, (0, 0, 0, 90), (cx, cy + 3), d // 2)
        av = _avatar(v, d)
        layer.blit(av, (cx - av.get_width() // 2, cy - av.get_height() // 2))

    # 底部渐暗带 + 名字（放进同一张缓存，避免每帧重画文字）
    bh = max(10, int(h * 0.30))
    band_y = h - bh
    for yy in range(bh):
        a = int(225 * ((yy + 1) / bh) ** 1.35)
        pygame.draw.line(layer, (0, 0, 0, a), (0, band_y + yy), (w - 1, band_y + yy))

    fs = theme.FS_NORMAL
    text_shadow(layer, tpl.name, fs, (240, 242, 248), (max(4, int(w * 0.075)), band_y + max(1, (bh - fs) // 2)))

    # 圆角裁切，避免立绘直角顶出卡框
    if radius > 0:
        mask = pygame.Surface(size, pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255), (0, 0, w, h), border_radius=radius)
        layer.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

    _SHOP_ART_CACHE[key] = layer
    return layer


def draw_piece(
    surface: pygame.Surface,
    rect: pygame.Rect,
    v: PieceVisual,
    ghost: bool = False,
    scale: float = 1.0,
    flash: float = 0.0,
    alpha: float = 1.0,
) -> None:
    """在给定矩形里画一个立式棋子（2.5D billboard）。

    先在格心画椭圆落地阴影，再把头像上移 PIECE_LIFT“站”在阴影上，
    上移量控制在自身六边形范围内（点头不会越界到上一行，点击归属不变）。

    ghost=True   半透明（拖拽预览，不画阴影）；
    scale>1      放大（拖拽跟手 / 吸附反馈）；
    flash>0      受击闪白强度（0~1，战斗阶段用）；
    alpha<1      整体淡出（阵亡时用，阴影同步淡出）。
    """
    size = piece_size(rect, scale)
    av = _avatar(v, size)
    cx, cy = rect.center
    lift = piece_lift(size)
    top = cy - size // 2 - lift

    if ghost:
        layer = av.copy()
        layer.set_alpha(170)
        surface.blit(layer, (cx - size // 2, top))
        return

    if alpha < 1.0:
        k = max(0.0, min(1.0, alpha))
        sh = _shadow_ellipse(size).copy()
        sh.set_alpha(int(255 * k))
        surface.blit(sh, (cx - sh.get_width() // 2, cy + int(size * 0.28) - sh.get_height() // 2))
        layer = av.copy()
        layer.set_alpha(int(255 * k))
        surface.blit(layer, (cx - size // 2, top))
        return

    # 落地阴影垫在脚下，头像“站”上去
    sh = _shadow_ellipse(size)
    surface.blit(sh, (cx - sh.get_width() // 2, cy + int(size * 0.28) - sh.get_height() // 2))
    surface.blit(av, (cx - size // 2, top))

    if flash > 0:
        disc = _flash_disc(size)
        disc.set_alpha(int(190 * min(1.0, flash)))
        surface.blit(disc, (cx - size // 2, top))

    if v.show_bars and v.alive:
        s = theme.S
        bar_w = int(size * 0.8)
        hp_h = max(4, int(7 * s))
        mp_h = max(2, int(3 * s))
        top_bar = cy + size // 2 - lift + max(1, s)  # 紧跟立式棋子脚底
        bar(
            surface,
            pygame.Rect(cx - bar_w // 2, top_bar, bar_w, hp_h),
            v.hp_ratio,
            hp_color(v.hp_ratio),
            bg=(12, 13, 18),
            radius=hp_h // 2,
        )
        bar(
            surface,
            pygame.Rect(cx - bar_w // 2, top_bar + hp_h + max(1, s), bar_w, mp_h),
            v.mana_ratio,
            theme.MANA_BLUE,
            bg=(12, 13, 18),
            radius=mp_h // 2,
        )


# ---------- 棋盘 ----------

_GRID_CACHE: dict[int, pygame.Surface] = {}

# 底板（透视平台）外扩边距：凸包向外膨胀后仍要落在缓存 surface 内
_GRID_MARGIN = 16


def draw_grid(surface: pygame.Surface) -> None:
    """画 7x8 蜂窝六边形棋盘（2.5D 透视）。静态整块缓存，每帧一次 blit。"""
    key = theme.S
    cached = _GRID_CACHE.get(key)
    if cached is None:
        cached = _render_grid()
        _GRID_CACHE[key] = cached
    m = _GRID_MARGIN * theme.S
    surface.blit(cached, (theme.BOARD_X - m, theme.BOARD_Y - m))


def _convex_hull(points) -> list[tuple[float, float]]:
    """单调链凸包；用于把全部六边形顶点包成一块透视平台底板。"""
    pts = sorted({(round(x, 1), round(y, 1)) for x, y in points})
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _render_grid() -> pygame.Surface:
    """以 _SSAA_FACTOR 倍分辨率生成静态透视棋盘，再平滑缩小回目标尺寸。

    底板不再用矩形面板，而是取全部六边形顶点的凸包向外膨胀一圈，
    得到一块正好贴合“近宽远窄”梯形的平台；六边形按行缩放逐格绘制。
    surface 四周留 _GRID_MARGIN 边距放膨胀后的底板，其余区域透明。
    """
    s = theme.S
    ss = _SSAA_FACTOR
    m = _GRID_MARGIN * s
    w, h = (theme.BOARD_W + 2 * m) * ss, (theme.BOARD_H + 2 * m) * ss
    surf = pygame.Surface((w, h), pygame.SRCALPHA)

    def local(pt) -> tuple[float, float]:
        """屏幕坐标 -> 缓存 surface 内的 SSAA 局部坐标。"""
        return ((pt[0] - theme.BOARD_X + m) * ss, (pt[1] - theme.BOARD_Y + m) * ss)

    # 1) 底板：全部六边形顶点的凸包，沿板心放射方向向外膨胀 pad
    all_pts: list[tuple[float, float]] = []
    for core_row in range(theme.BOARD_ROWS):
        for col in range(theme.BOARD_COLS):
            all_pts.extend(local(p) for p in cell_polygon(col, core_row))
    hull = _convex_hull(all_pts)
    cx, cy = w / 2, h / 2
    pad = 10 * s * ss

    def inflate(x: float, y: float, d: float):
        r = math.hypot(x - cx, y - cy) or 1.0
        return (x + (x - cx) / r * d, y + (y - cy) / r * d)

    slab = [inflate(x, y, pad) for x, y in hull]
    inner = [inflate(x, y, -2 * s * ss) for x, y in hull]
    pygame.draw.polygon(surf, theme.BORDER_SOFT, slab)
    pygame.draw.polygon(surf, (24, 27, 35), inner)

    # 2) 六边形地砖（己方下半屏偏蓝、敌方上半屏偏红，棋盘格交替深浅）
    own_top = theme.BOARD_ROWS // 2  # 己方 core row 0..3
    for core_row in range(theme.BOARD_ROWS):
        for col in range(theme.BOARD_COLS):
            pts = [local(p) for p in cell_polygon(col, core_row)]
            if core_row < own_top:  # 己方半场（屏幕下半）
                base = theme.SELF_ROW_TINT if (col + core_row) % 2 == 0 else theme.shade(
                    theme.SELF_ROW_TINT, 0.82
                )
            else:
                base = theme.ENEMY_ROW_TINT if (col + core_row) % 2 == 0 else theme.shade(
                    theme.ENEMY_ROW_TINT, 0.82
                )
            # 远端行整体调暗，强化纵深
            depth = 1.0 - 0.16 * (1.0 - row_scale(theme.BOARD_ROWS - 1 - core_row))
            base = theme.shade(base, depth)
            pygame.draw.polygon(surf, base, pts)
            # 内侧暗一点，做出一点厚度
            ly = sum(p[1] for p in pts) / len(pts)
            inner_pts = [(x, ly + (y - ly) * 0.88) for x, y in pts]
            pygame.draw.polygon(surf, theme.shade(base, 0.86), inner_pts)
            pygame.draw.polygon(surf, theme.BORDER, pts, width=max(1, s * ss))

    # 3) 中线（两军交火分界）：落在 core row 3/4 之间，位置与宽度按两行极值插值
    def row_extents(core_row: int):
        pts: list[tuple[float, float]] = []
        for col in (0, theme.BOARD_COLS - 1):
            pts.extend(local(p) for p in cell_polygon(col, core_row))
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return min(xs), max(xs), min(ys), max(ys)

    l3, r3, _, b3 = row_extents(3)
    l4, r4, t4, _ = row_extents(4)
    mid_y = (b3 + t4) / 2
    pygame.draw.line(
        surf, theme.ACCENT, ((l3 + l4) / 2, mid_y), ((r3 + r4) / 2, mid_y), max(2, 2 * s * ss)
    )

    if ss > 1:
        return pygame.transform.smoothscale(surf, (theme.BOARD_W + 2 * m, theme.BOARD_H + 2 * m))
    return surf


def draw_deploy_highlight(surface: pygame.Surface, accent=None, t: float = 0.0) -> None:
    """拖拽摆位时高亮己方半场四行（core_row 0..3）的六边形边框。"""
    accent = accent or theme.ACCENT
    pulse = 0.55 + 0.45 * math.sin(t * 6.0)
    color = theme.mix(theme.shade(accent, 0.7), (255, 255, 255), 0.25 * pulse)
    for core_row in range(theme.BOARD_ROWS // 2):
        for col in range(theme.BOARD_COLS):
            pygame.draw.polygon(
                surface, color, cell_polygon(col, core_row, shrink=theme.TILE_INSET), width=max(2, 2 * theme.S)
            )


def draw_placements(surface: pygame.Surface, placements: list[dict], team: str) -> None:
    """把一支队伍按布阵画到棋盘上（按投影 y 远→近排序，近处棋子压住远处）。

    placements 是 auto_place / build_team 的产出：[{"id", "star", "pos", "equip"}, ...]
    """
    # 2.5D 透视下必须按深度排序绘制，否则列表顺序会让近处棋子被远处棋子遮挡
    ordered = sorted(placements, key=lambda p: hex_point(p["pos"][0], p["pos"][1])[1])
    for p in ordered:
        col, row = int(p["pos"][0]), int(p["pos"][1])
        v = visual_from_tid(p["id"], int(p.get("star", 1)), team)
        draw_piece(surface, cell_rect(col, row), v)
        equip = p.get("equip", [])
        if equip:
            _draw_equip_badges(surface, cell_rect(col, row), equip)


def _draw_equip_badges(surface: pygame.Surface, rect: pygame.Rect, equip: list) -> None:
    """在棋子脚下画装备小图标：有贴图显示缩略图，缺图回退菱形（成装金色）。"""
    n = min(len(equip), 3)
    gap = max(10, int(12 * theme.S))
    start_x = rect.centerx - (n - 1) * gap // 2
    y = piece_feet_y(rect) - max(4, int(5 * theme.S))
    for k in range(n):
        it = equip[k]
        cx = start_x + k * gap
        draw_item_badge(surface, (cx, y), it.item_id)
