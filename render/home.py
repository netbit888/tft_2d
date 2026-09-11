"""游戏主页（HomeView）：菜单循环的门厅。

布局（简洁版）：
- 标题上移居中（TFT 2D GAME + 副标题）；
- 右下角一颗大号“开始游戏”球（8 人局，主入口，金色呼吸描边）；
- 左下角贴边“退出游戏”球；
- 背景：少量棋子头像缓慢漂浮（限制在左侧区域，避开标题与按钮）。

生命周期约定：HomeView 自带窗口与主循环，返回 "start"/"quit" 交给外层
菜单循环（app.main）创建 Game + App；App 结束只关自己的循环，不 quit pygame，
由外层决定回到主页还是退出程序。
"""

from __future__ import annotations

import math
import random

import pygame

from . import theme
from .assets import enable_dpi_awareness, font
from .audio import Audio
from .board_view import _clear_caches, visual_from_tid

MODE_START = "start"  # 开始游戏（8 人局）
ACTION_QUIT = "quit"

# 主页球体：开始球为主入口（大一号），退出球贴左下角
HOME_BALL_R = 66  # * theme.S


class HomeView:
    """主页：返回 MODE_START 或 ACTION_QUIT；窗口尺寸与 App 一致。"""

    def __init__(self, scale: int | None = None, seed: int | None = None, fullscreen: bool = True) -> None:
        enable_dpi_awareness()
        try:
            pygame.mixer.pre_init(22050, -16, 2, 512)
        except Exception:
            pass
        pygame.init()
        self._set_window_icon()

        # 默认全屏：FULLSCREEN | SCALED 把固定内部分辨率(1280x800)缩放到整屏；
        # 普通窗口传 fullscreen=False（命令行 --windowed）。
        self.fullscreen = fullscreen
        picked = scale if scale else 2
        self.scale = theme.set_scale(picked)
        _clear_caches()
        pygame.display.set_caption(f"TFT 2D GAME  ({theme.WINDOW_W}x{theme.WINDOW_H})")
        self.screen = theme.create_display(self.fullscreen)
        self.clock = pygame.time.Clock()
        self.time = 0.0

        self.audio = Audio()
        if self.audio.enabled:
            self.audio.music.play("deploy")

        # 漂浮棋子背景：固定种子，数量克制；限制在左侧区域，避开球与标题
        rng = random.Random(seed if seed is not None else 20240601)
        from core.loader import load_units

        tids = sorted(load_units().keys())
        picked_tids = rng.sample(tids, min(5, len(tids)))
        self.floaters = []
        for i, tid in enumerate(picked_tids):
            self.floaters.append(
                {
                    "v": visual_from_tid(tid, rng.randint(1, 3), "blue" if i % 2 else "red"),
                    "bx": rng.uniform(0.08, 0.55),  # 左侧区域（窗口比例，避开右侧球）
                    "by": rng.uniform(0.12, 0.72),
                    "amp": rng.uniform(6, 14),  # 漂浮幅度 px
                    "spd": rng.uniform(0.25, 0.55),  # 漂浮速度
                    "phase": rng.uniform(0, math.tau),
                    "size": int(rng.uniform(44, 72) * theme.S),
                }
            )

    def _set_window_icon(self) -> None:
        """窗口图标：assets/icon.ico（存在才设置，缺失静默跳过）。"""
        from pathlib import Path

        icon = Path(__file__).resolve().parent.parent / "assets" / "icon.ico"
        if icon.is_file():
            try:
                pygame.display.set_icon(pygame.image.load(str(icon)))
            except pygame.error:
                pass

    # ---------- 布局 ----------

    def _ball_r(self) -> int:
        return HOME_BALL_R * theme.S

    def _start_ball_center(self) -> tuple[int, int]:
        """开始球：右下角，主入口。"""
        s = theme.S
        r = self._ball_r() + int(14 * s)  # primary 加成，与绘制一致
        return theme.WINDOW_W - r - int(52 * s), theme.WINDOW_H - r - int(52 * s)

    def _quit_ball_center(self) -> tuple[int, int]:
        """退出球：左下角贴边（小一号）。"""
        s = theme.S
        r = int(self._ball_r() * 0.72)
        return r + int(40 * s), theme.WINDOW_H - r - int(40 * s)

    def _hit_radius(self, primary: bool) -> int:
        r = self._ball_r()
        return r + (int(14 * theme.S) if primary else -int(r * 0.28))

    # ---------- 主循环 ----------

    def run(self) -> str:
        while True:
            dt = self.clock.tick(theme.FPS) / 1000.0
            self.time += dt
            for event in pygame.event.get():
                action = self._handle(event)
                if action is not None:
                    if self.audio.enabled:
                        self.audio.sfx.play("equip")
                    return action
            if self.audio.enabled:
                self.audio.update(dt)
            self._draw()
            pygame.display.flip()

    def _handle(self, event: pygame.event.Event) -> str | None:
        if event.type == pygame.QUIT:
            return ACTION_QUIT
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            return ACTION_QUIT  # 主页 ESC 直接退出（不再有上层可回）
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            x, y = self._start_ball_center()
            if math.hypot(event.pos[0] - x, event.pos[1] - y) <= self._hit_radius(True):
                return MODE_START
            x, y = self._quit_ball_center()
            if math.hypot(event.pos[0] - x, event.pos[1] - y) <= self._hit_radius(False):
                return ACTION_QUIT
        return None

    # ---------- 绘制 ----------

    def _draw(self) -> None:
        s = theme.S
        self.screen.fill(theme.BG)

        # 背景：漂浮棋子（暗化处理，垫在最底层）
        self._draw_floaters()

        # 标题：上移居中 + 副标题
        title_font = font(int(96 * s))
        img = title_font.render("TFT 2D GAME", True, theme.GOLD)
        shadow = title_font.render("TFT 2D GAME", True, (10, 11, 15))
        cx, cy = theme.WINDOW_W // 2, int(theme.WINDOW_H * 0.28)
        self.screen.blit(shadow, (cx - img.get_width() // 2 + 3 * s, cy - img.get_height() // 2 + 3 * s))
        self.screen.blit(img, (cx - img.get_width() // 2, cy - img.get_height() // 2))
        sub = font(theme.FS_NORMAL).render("类金铲铲自走棋 · 8 人局 · 纯 Python + pygame-ce", True, theme.TEXT_DIM)
        self.screen.blit(sub, (cx - sub.get_width() // 2, cy + img.get_height() // 2 + 10 * s))

        mouse = pygame.mouse.get_pos()
        self._draw_ball(
            self._start_ball_center(),
            "开始游戏",
            "8 人局 · 你 + 7 台电脑",
            theme.ACCENT,
            mouse,
            primary=True,
        )
        self._draw_ball(
            self._quit_ball_center(), "退出游戏", "关闭程序", (216, 96, 96), mouse
        )

    def _draw_floaters(self) -> None:
        """背景漂浮棋子头像：正弦上下漂浮；避开标题的横向带。"""
        from .board_view import _avatar

        title_band = (0.16, 0.42)  # 标题竖向占位（窗口比例），头像不让进
        for f in self.floaters:
            av = _avatar(f["v"], f["size"])
            wob = math.sin(self.time * f["spd"] + f["phase"])
            by = f["by"] + wob * f["amp"] / theme.WINDOW_H
            if title_band[0] < by < title_band[1] and 0.22 < f["bx"] < 0.78:
                continue  # 会压到标题：这一帧不画
            x = f["bx"] * theme.WINDOW_W - f["size"] // 2
            y = by * theme.WINDOW_H - f["size"] // 2
            dim = av.copy()
            dim.set_alpha(46 + int(8 * wob))
            self.screen.blit(dim, (x, y))

    def _draw_ball(
        self, center, label: str, desc: str, color, mouse, primary: bool = False
    ) -> None:
        """一颗主页球：圆盘 + 描边 + 悬停放大 + 球面文字 + 球下描述。

        primary=True（开始游戏）比普通球大一圈并带金色呼吸描边。
        """
        s = theme.S
        cx, cy = center
        hovered = math.hypot(mouse[0] - cx, mouse[1] - cy) <= self._hit_radius(primary)
        boost = int(14 * s) if primary else -int(self._ball_r() * 0.28)
        r = self._ball_r() + boost + (int(6 * s) if hovered else 0)

        pygame.draw.circle(self.screen, (9, 11, 16), (cx, cy), r + int(3 * s))
        pygame.draw.circle(self.screen, theme.PANEL, (cx, cy), r)
        rim = color if hovered else theme.BORDER
        if primary:
            pulse = 0.5 + 0.5 * math.sin(self.time * 3.0)
            rim = theme.mix(theme.GOLD, color, 0.35 + 0.3 * pulse)
            if hovered:
                rim = theme.GOLD
        pygame.draw.circle(self.screen, rim, (cx, cy), r, width=max(3, int(4 * s)))
        pygame.draw.circle(self.screen, theme.BG_SOFT, (cx, cy), r - int(8 * s))

        # 球面主文字（按字宽自适应缩到球内）
        fs = int((38 if primary else 26) * s)
        while fs > 12 * s:
            img = font(fs).render(label, True, theme.TEXT if (hovered or primary) else theme.TEXT_DIM)
            if img.get_width() <= r * 1.7:
                break
            fs -= 2
        self.screen.blit(img, (cx - img.get_width() // 2, cy - img.get_height() // 2))

        # 球下描述小字
        dimg = font(theme.FS_TINY).render(desc, True, theme.TEXT_DIM)
        self.screen.blit(dimg, (cx - dimg.get_width() // 2, cy + r + int(8 * s)))
