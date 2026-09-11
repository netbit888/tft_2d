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
from .board_view import (
    cell_at,
    cell_rect_at,
    draw_grid,
    draw_piece,
    hex_point,
    scale_at,
    visual_from_unit,
)
from .info import battle_unit_records, draw_tip
from .widgets import Button, panel

# ---------- 坐标 ----------


def board_pos(x: float, y: float) -> tuple[float, float]:
    """core 的棋盘坐标（浮点）-> 屏幕像素（与备战/布阵同一套蜂窝映射）。"""
    return hex_point(x, y)


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

    def __init__(self, combat, on_finish, names: dict | None = None) -> None:
        self.combat = combat
        self.on_finish = on_finish
        # 双方玩家名（{"blue": 名字, "red": 名字}），展示在战斗详情首行
        self.names = names or {}
        # 点选查看详情的单位（左键单击棋子打开/切换/关闭）
        self.detail_unit = None
        self.detail_anchor = None  # 打开时点击位置的屏幕坐标，详情面板固定在这里

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

        # 伤害统计：增量扫描事件流聚合（跳过战斗/直接算完也能拿到完整统计）
        self._stats_scanned = 0
        self._stats: dict[str, dict[int, float]] = {
            "dmg": {}, "taken": {}, "heal": {}, "casts": {}
        }
        self.show_recap = False  # Tab 开关（结算画面固定显示）

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
        if event.type == pygame.KEYDOWN and event.key == pygame.K_TAB:
            self.show_recap = not self.show_recap

        # 棋盘交互：左键点击棋子开/切详情，点空白处关闭（暂停后可以细看数值）
        if (
            not self.done
            and event.type == pygame.MOUSEBUTTONDOWN
            and event.button == 1
        ):
            u = self._hit_unit(event.pos)
            self.detail_unit = None if u is None or u is self.detail_unit else u
            self.detail_anchor = event.pos

    def skip(self) -> None:
        """直接算完战斗，不看动画。"""
        while not self.combat.finished:
            self.combat.step()
        self._scan_events()
        self.floaters.clear()
        self.rings.clear()
        self.bolts.clear()
        self.finish()

    # ---------- 伤害统计 ----------

    def _scan_events(self) -> None:
        """增量扫描战斗事件流，聚合 uid -> 伤害/承伤/治疗/施法。"""
        events = self.combat.events
        if self._stats_scanned > len(events):  # 不可能，防御一下
            self._stats_scanned = 0
        for e in events[self._stats_scanned:]:
            d = e.data
            if e.type == EV_DAMAGE:
                self._stats["dmg"][d.get("suid", -1)] = (
                    self._stats["dmg"].get(d.get("suid", -1), 0.0) + d["amount"]
                )
                self._stats["taken"][d.get("tuid", -1)] = (
                    self._stats["taken"].get(d.get("tuid", -1), 0.0) + d["amount"]
                )
            elif e.type == EV_HEAL:
                uid = d.get("uid", -1)
                self._stats["heal"][uid] = self._stats["heal"].get(uid, 0.0) + d["amount"]
            elif e.type == EV_CAST:
                uid = d.get("uid", -1)
                self._stats["casts"][uid] = self._stats["casts"].get(uid, 0.0) + 1
        self._stats_scanned = len(events)

    def stats_rows(self) -> list[dict]:
        """按队伍返回统计行（伤害降序），供 recap 面板 / 结算画面使用。"""
        self._scan_events()
        rows = []
        for u in self.combat.units:
            uid = u.uid
            dmg = self._stats["dmg"].get(uid, 0.0)
            if dmg <= 0 and self._stats["taken"].get(uid, 0.0) <= 0:
                continue  # 没参与战斗的单位不列
            rows.append(
                {
                    "team": u.team,
                    "name": u.name,
                    "star": u.star,
                    "dmg": dmg,
                    "taken": self._stats["taken"].get(uid, 0.0),
                    "heal": self._stats["heal"].get(uid, 0.0),
                    "casts": int(self._stats["casts"].get(uid, 0.0)),
                }
            )
        rows.sort(key=lambda r: (-r["dmg"], r["team"], r["name"]))
        return rows

    def finish(self) -> None:
        if self.done:
            return
        self.done = True
        self.on_finish(self.combat)

    def update(self, dt: float) -> None:
        self._update_fx(dt)
        self._scan_events()  # 统计聚合与动画解耦：跳过/暂停都不漏
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

    def _hit_unit(self, pos):
        """屏幕坐标 -> 被点中的存活战斗单位；没有则返回 None。

        先按所在六边形格找（格子化战斗每格至多一个存活单位），
        滑行途中的单位没踩在格心，再按屏幕距离兜底（限制一个格子内）。
        """
        cell = cell_at(pos)
        if cell is not None:
            for u in self.combat.units:
                if u.alive and u.cell == cell:
                    return u
        best, best_d = None, 1e9
        for u in self.combat.units:
            if not u.alive:
                continue
            px, py = board_pos(u.x, u.y)
            thr = theme.CELL * 0.85 * scale_at(u.y)  # 命中半径随所在深度缩放
            d = (px - pos[0]) ** 2 + (py - pos[1]) ** 2
            if d < min(best_d, thr * thr):
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
            victim = self.combat.by_uid.get(d.get("tuid"))
            if victim is None:
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
        if self.show_recap:
            self.draw_recap(surface)
        if self.detail_unit is not None and not self.done:
            self._draw_detail(surface)

    def draw_recap(self, surface: pygame.Surface) -> None:
        """Tab 开关的战斗中伤害统计面板（悬在控制条上方）。"""
        from .recap import draw_recap

        w, h = 680 * theme.S, 300 * theme.S
        rect = pygame.Rect(0, 0, w, h)
        rect.centerx = theme.WINDOW_W // 2
        rect.bottom = theme.WINDOW_H - theme.CTRL_H - 8 * theme.S
        draw_recap(surface, self.stats_rows(), rect, title="伤害统计（Tab 收起）")

    def _draw_detail(self, surface: pygame.Surface) -> None:
        """把点选单位的实时详情面板画在最上层（固定在与单位绑定的锚点旁）。"""
        u = self.detail_unit
        if u is None or self.detail_anchor is None:
            return
        side = self.names.get(u.team, "己方" if u.team == "blue" else "敌方")
        accent = theme.TEAM_COLORS.get(u.team, theme.GOLD)
        draw_tip(surface, battle_unit_records(u, side), self.detail_anchor, accent=accent)

    def draw_units(self, surface: pygame.Surface) -> None:
        alpha = min(1.0, self.acc / DT) if not self.combat.finished else 1.0
        rows = []  # (绘制深度 y, 单位, rect, 阵亡淡出参数)
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

            rect = cell_rect_at(ix, iy)  # 尺寸按插值坐标所在深度透视缩放
            rect.center = (round(sx), round(sy))  # 位置含近战突进偏移（屏幕空间）
            rows.append((sy, u, rect, fade))

        # 2.5D 透视：按投影 y 远→近排序，近处棋子压住远处（跨队伍统一排序）
        for _, u, rect, fade in sorted(rows, key=lambda r: r[0]):
            if fade is not None:
                k = fade / self.FADE_TIME  # 1 -> 0
                cell_px = rect.width
                shrink = int(cell_px * 0.25 * (1 - k))
                rect = rect.inflate(-shrink, -shrink)
                rect.y += int(cell_px * 0.22 * (1 - k))
                draw_piece(surface, rect, visual_from_unit(u), alpha=0.15 + 0.55 * k)
                continue

            draw_piece(surface, rect, visual_from_unit(u), flash=self.flashes.get(u.uid, 0.0) / self.FLASH_TIME)
            if u is self.detail_unit:
                pygame.draw.circle(
                    surface,
                    theme.GOLD,
                    rect.center,
                    rect.width // 2,
                    width=max(2, int(2 * theme.S)),
                )

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
        status = f"第 {c.tick} tick / {c.tick / 20:.1f}s    当前 {self.speed}x    Tab=伤害统计"
        if self.paused:
            status += "（已暂停）"
        text(
            surface,
            status,
            theme.FS_SMALL,
            theme.TEXT_DIM,
            (theme.PAD, theme.WINDOW_H - theme.CTRL_H + int(18 * theme.S)),
        )
