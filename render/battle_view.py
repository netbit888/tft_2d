"""战斗回放：把 core 产出的事件流"慢放"成动画。

要点：
- core 是 20 tick/s，渲染是 60fps，所以要在两个 tick 之间做位置插值，否则棋子会一格一格跳；
- 动画完全由事件驱动（飘字、突进、弹道、技能圈、受击闪白、技能横幅），逻辑层不知道动画的存在；
- 速度可调、可暂停、可跳过——每天看十几场战斗，必须有跳过；
- 高分辨率下飘字/技能圈全部预渲染或缓存，避免每帧新建 Surface 和重复渲染文字。
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

import pygame

from core.combat import DT
from core.events import EV_ATTACK, EV_CAST, EV_DAMAGE, EV_DEATH, EV_HEAL

from . import theme
from .assets import font, text
from .board_view import draw_grid, draw_piece, visual_from_unit
from .widgets import Button, panel

# ---------- 坐标 ----------


def board_pos(x: float, y: float) -> tuple[float, float]:
    """core 的棋盘坐标（浮点）-> 屏幕像素。y 需要翻转：己方在屏幕下方。"""
    disp = (theme.BOARD_ROWS - 1) - y
    return (
        theme.BOARD_X + (x + 0.5) * theme.CELL,
        theme.BOARD_Y + (disp + 0.5) * theme.CELL,
    )


def event_pos(data: dict) -> tuple[float, float]:
    return board_pos(data["tx"], data["ty"])


# ---------- 特效 ----------


@dataclass
class Floater:
    s: str
    pos: tuple[float, float]
    color: tuple
    life: float = 0.8
    big: bool = False
    total: float = 0.8
    dx: float = 0.0  # 横向散开，避免多个飘字完全重叠
    img: pygame.Surface = field(default=None, repr=False)  # 预渲染好的文字


@dataclass
class Ring:
    pos: tuple[float, float]
    radius: float
    life: float = 0.45
    total: float = 0.45
    color: tuple = (158, 112, 222)


@dataclass
class Bolt:
    a: tuple[float, float]
    b: tuple[float, float]
    life: float = 0.18
    total: float = 0.18
    color: tuple = (235, 240, 250)


_RING_CACHE: dict[tuple, pygame.Surface] = {}


def _ring_sprite(radius: int, width: int, color: tuple) -> pygame.Surface:
    """技能圈底图：固定半径画一次，之后靠缩放 + alpha 复用。"""
    key = (radius, width, color)
    surf = _RING_CACHE.get(key)
    if surf is None:
        size = radius * 2 + width * 2 + 4
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(
            surf, (*color, 255), (size // 2, size // 2), radius, width=width
        )
        _RING_CACHE[key] = surf
    return surf


# ---------- 回放控制器 ----------


class BattleView:
    SPEEDS = (1, 2, 4)
    FADE_TIME = 0.45  # 阵亡后尸体停留时间
    FLASH_TIME = 0.16  # 受击闪白时长
    BANNER_TIME = 1.1  # 技能横幅停留时长

    def __init__(self, combat, on_finish) -> None:
        self.combat = combat
        self.on_finish = on_finish

        self.acc = 0.0
        self.speed = 1
        self.paused = False
        self.done = False
        self.processed = 0
        self.finish_delay = 0.9

        self.prev = {u.uid: (u.x, u.y) for u in combat.units}
        self.floaters: list[Floater] = []
        self.rings: list[Ring] = []
        self.bolts: list[Bolt] = []
        self.bumps: dict[int, list] = {}  # uid -> [剩余时间, dirx, diry]
        self.fades: dict[int, float] = {}  # uid -> 剩余淡出时间
        self.flashes: dict[int, float] = {}  # uid -> 剩余闪白时间
        self.banner: dict | None = None

        self._init_buttons()

    def _init_buttons(self) -> None:
        w, h = theme.BTN_CTRL_W, theme.BTN_CTRL_H
        gap = theme.BTN_CTRL_GAP
        total = w * 5 + gap * 4
        x = (theme.WINDOW_W - total) // 2
        y = theme.WINDOW_H - theme.CTRL_H + (theme.CTRL_H - h) // 2
        self.btn_pause = Button((x, y, w, h), "暂停")
        self.btns_speed = [
            Button((x + (w + gap) * (i + 1), y, w, h), f"{s}x") for i, s in enumerate(self.SPEEDS)
        ]
        self.btn_skip = Button((x + (w + gap) * 4, y, w, h), "跳过", (220, 120, 90))

    # ---------- 更新 ----------

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.btn_pause.handle(event):
            self.paused = not self.paused
            self.btn_pause.label = "继续" if self.paused else "暂停"
        for btn, spd in zip(self.btns_speed, self.SPEEDS):
            if btn.handle(event):
                self.speed = spd
                self.paused = False
                self.btn_pause.label = "暂停"
        if self.btn_skip.handle(event):
            self.skip()

    def skip(self) -> None:
        """直接算完战斗，不看动画。"""
        while not self.combat.finished:
            self.combat.step()
        self.floaters.clear()
        self.rings.clear()
        self.bolts.clear()
        self.finish()

    def finish(self) -> None:
        if self.done:
            return
        self.done = True
        self.on_finish(self.combat)

    def update(self, dt: float) -> None:
        self._update_fx(dt)
        if self.done or self.paused:
            return

        self.acc += dt * self.speed
        guard = 0
        while self.acc >= DT and not self.combat.finished and guard < 80:
            self.acc -= DT
            guard += 1
            self._step()

        if self.combat.finished:
            self.finish_delay -= dt
            if self.finish_delay <= 0:
                self.finish()

    def _step(self) -> None:
        c = self.combat
        self.prev = {u.uid: (u.x, u.y) for u in c.units}
        c.step()
        for e in c.events[self.processed :]:
            self._on_event(e)
        self.processed = len(c.events)

    def _unit_near(self, tx: float, ty: float):
        """按坐标找回被打的单位（伤害事件只有名字没有 uid）。"""
        best, best_d = None, 1e9
        for u in self.combat.units:
            d = (u.x - tx) ** 2 + (u.y - ty) ** 2
            if d < best_d:
                best, best_d = u, d
        return best

    def _on_event(self, e) -> None:
        d = e.data

        if e.type == EV_ATTACK:
            u = self.combat.by_uid.get(d.get("uid"))
            if u is None:
                return
            src = board_pos(d["sx"], d["sy"])
            dst = board_pos(d["tx"], d["ty"])
            if u.attack_range > 1:
                self.bolts.append(Bolt(src, dst))
            else:
                dx, dy = dst[0] - src[0], dst[1] - src[1]
                dist = math.hypot(dx, dy) or 1.0
                self.bumps[u.uid] = [0.18, dx / dist, dy / dist]

        elif e.type == EV_DAMAGE:
            if d["kind"] == "magic":
                color = (186, 130, 240)
            elif d["crit"]:
                color = theme.GOLD
            else:
                color = (238, 240, 245)
            self.push_floater(
                Floater(f"-{d['amount']:.0f}", event_pos(d), color, big=d["crit"])
            )
            victim = self._unit_near(d["tx"], d["ty"])
            if victim is not None:
                self.flashes[victim.uid] = self.FLASH_TIME
            if d["crit"]:
                self.rings.append(
                    Ring(event_pos(d), theme.CELL * 0.34, life=0.3, total=0.3, color=theme.GOLD)
                )

        elif e.type == EV_CAST:
            self.rings.append(Ring(event_pos(d), theme.CELL * 0.75))
            who = self.combat.by_uid.get(d.get("uid"))
            self.banner = {
                "text": f"{d.get('name', '')} 施放【{d.get('ability', '')}】",
                "team": who.team if who is not None else "blue",
                "life": self.BANNER_TIME,
                "total": self.BANNER_TIME,
            }

        elif e.type == EV_HEAL:
            self.push_floater(Floater(f"+{d['amount']:.0f}", event_pos(d), theme.HP_GREEN))

        elif e.type == EV_DEATH:
            self.fades[d["uid"]] = self.FADE_TIME

    def push_floater(self, f: Floater) -> None:
        """加一个飘字：文字提前渲染好（每帧只 blit），横向随机散开并限制同屏数量。"""
        size = theme.FS_NORMAL if f.big else theme.FS_SMALL
        f.img = font(size).render(f.s, True, f.color).convert_alpha()
        f.dx = random.uniform(-14, 14) * theme.S
        self.floaters.append(f)
        if len(self.floaters) > 36:
            self.floaters.pop(0)

    def _update_fx(self, dt: float) -> None:
        for f in self.floaters:
            f.life -= dt
        self.floaters = [f for f in self.floaters if f.life > 0]

        for r in self.rings:
            r.life -= dt
        self.rings = [r for r in self.rings if r.life > 0]

        for b in self.bolts:
            b.life -= dt
        self.bolts = [b for b in self.bolts if b.life > 0]

        for uid in list(self.bumps):
            self.bumps[uid][0] -= dt
            if self.bumps[uid][0] <= 0:
                del self.bumps[uid]

        for uid in list(self.fades):
            self.fades[uid] -= dt
            if self.fades[uid] <= 0:
                del self.fades[uid]

        for uid in list(self.flashes):
            self.flashes[uid] -= dt
            if self.flashes[uid] <= 0:
                del self.flashes[uid]

        if self.banner is not None:
            self.banner["life"] -= dt
            if self.banner["life"] <= 0:
                self.banner = None

    # ---------- 绘制 ----------

    def draw(self, surface: pygame.Surface) -> None:
        draw_grid(surface)
        self.draw_units(surface)
        self.draw_fx(surface)
        self.draw_banner(surface)
        self.draw_controls(surface)

    def draw_units(self, surface: pygame.Surface) -> None:
        alpha = min(1.0, self.acc / DT) if not self.combat.finished else 1.0
        for u in self.combat.units:
            fade = self.fades.get(u.uid)
            if not u.alive and fade is None:
                continue

            px, py = self.prev.get(u.uid, (u.x, u.y))
            cx, cy = u.x, u.y
            ix, iy = px + (cx - px) * alpha, py + (cy - py) * alpha
            sx, sy = board_pos(ix, iy)

            bump = self.bumps.get(u.uid)
            if bump:
                t = bump[0] / 0.18  # 1 -> 0
                push = math.sin(t * math.pi) * theme.BUMP_PUSH
                sx += bump[1] * push
                sy += bump[2] * push

            rect = pygame.Rect(0, 0, theme.CELL, theme.CELL)
            rect.center = (sx, sy)

            if fade is not None:
                k = fade / self.FADE_TIME  # 1 -> 0
                rect = rect.inflate(-int(theme.CELL * 0.25 * (1 - k)), -int(theme.CELL * 0.25 * (1 - k)))
                rect.y += int(theme.CELL * 0.22 * (1 - k))
                draw_piece(surface, rect, visual_from_unit(u), alpha=0.15 + 0.55 * k)
                continue

            draw_piece(surface, rect, visual_from_unit(u), flash=self.flashes.get(u.uid, 0.0) / self.FLASH_TIME)

    def draw_fx(self, surface: pygame.Surface) -> None:
        width = max(3, int(3 * theme.S))
        for r in self.rings:
            t = 1 - r.life / r.total
            radius = max(2, int(r.radius * (0.35 + 0.65 * t)))
            alpha = int(220 * (1 - t))
            base = _ring_sprite(int(r.radius), width, r.color)
            size = radius * 2 + width * 2 + 4
            img = pygame.transform.scale(base, (size, size))
            img.set_alpha(alpha)
            surface.blit(img, (r.pos[0] - size // 2, r.pos[1] - size // 2))

        for b in self.bolts:
            t = b.life / b.total
            x = b.a[0] + (b.b[0] - b.a[0]) * (1 - t)
            y = b.a[1] + (b.b[1] - b.a[1]) * (1 - t)
            pygame.draw.line(surface, b.color, (x, y), b.b, max(2, 2 * theme.S))
            pygame.draw.circle(surface, b.color, (int(x), int(y)), max(3, int(4 * theme.S)))

        for f in self.floaters:
            t = 1 - f.life / f.total
            y = f.pos[1] - theme.FLOAT_RISE * t - f.img.get_height()
            f.img.set_alpha(int(255 * (1 - t * t)))
            surface.blit(f.img, (f.pos[0] + f.dx - f.img.get_width() // 2, y))

    def draw_banner(self, surface: pygame.Surface) -> None:
        if self.banner is None:
            return
        b = self.banner
        t = 1 - b["life"] / b["total"]
        alpha = 255 if t < 0.6 else int(255 * (1 - (t - 0.6) / 0.4))
        color = theme.TEAM_COLORS.get(b["team"], theme.ACCENT)
        img = font(theme.FS_NORMAL).render(b["text"], True, color)
        img.set_alpha(alpha)
        pad = 12 * theme.S
        w = img.get_width() + pad * 2
        h = img.get_height() + pad
        box = pygame.Rect(0, 0, w, h)
        box.centerx = theme.WINDOW_W // 2
        box.y = theme.TOP_H + int(6 * theme.S)
        layer = pygame.Surface((w, h), pygame.SRCALPHA)
        layer.fill((12, 14, 20, min(210, alpha)))
        surface.blit(layer, box.topleft)
        surface.blit(img, (box.x + pad, box.y + pad // 2))

    def draw_controls(self, surface: pygame.Surface) -> None:
        rect = pygame.Rect(0, theme.WINDOW_H - theme.CTRL_H, theme.WINDOW_W, theme.CTRL_H)
        panel(surface, rect, theme.PANEL, radius=0)
        pygame.draw.line(surface, theme.BORDER, (0, rect.y), (theme.WINDOW_W, rect.y), 1)

        self.btn_pause.draw(surface)
        for btn in self.btns_speed:
            btn.draw(surface)
        self.btn_skip.draw(surface)

        c = self.combat
        status = f"第 {c.tick} tick / {c.tick / 20:.1f}s    当前 {self.speed}x"
        if self.paused:
            status += "（已暂停）"
        text(
            surface,
            status,
            theme.FS_SMALL,
            theme.TEXT_DIM,
            (theme.PAD, theme.WINDOW_H - theme.CTRL_H + int(18 * theme.S)),
        )
