"""图形界面主循环。

操作：
  点商店卡片        购买（进入备战席）
  备战席 -> 棋盘     上场
  棋盘内拖动         交换位置
  棋盘 -> 备战席     下场
  右键棋子 / 拖到商店  卖出
  拖装备到棋子       装备
  装备栏内拖动       合成（两件基础装备）
  开战               自动补位 -> 电脑运营 -> 战斗 -> 结算
  升级按钮           花 4 金买 4 经验提升人口上限

支持 1v1 与 8 人局（--players 8）。8 人局每回合两两配对打 1v1。
"""

from __future__ import annotations

import math

import pygame

from core import ai_take_turn, ai_equip, ai_upgrade_check, buy_xp
from core.deploy import auto_seat, move_piece, piece_at
from core.events import EV_CAST, EV_DEATH, EV_END, EV_HEAL, format_event
from core.items import (
    MAX_ITEMS_PER_PIECE,
    combined_item_id,
    is_base_item,
    item_name,
)
from core.loader import load_traits, load_units
from core.shop import REFRESH_COST, buy, refresh_shop, sell_piece
from core.traits import count_traits_from_tids

from . import theme
from .assets import enable_dpi_awareness, render, text
from .battle_view import BattleView
from .board_view import (
    _clear_caches,
    cell_at,
    cell_rect,
    draw_deploy_highlight,
    draw_grid,
    draw_piece,
    draw_placements,
    visual_from_tid,
)
from .info import draw_tip
from .item_view import (
    draw_combine_candidates,
    draw_item_bench,
    draw_roster,
    item_slot_at,
    item_slot_rect,
)
from .shop_view import (
    bench_slot_at,
    bench_slot_rect,
    draw_bench,
    draw_shop,
    shop_card_at,
    shop_card_rect,
)
from .widgets import Button, bar, dim_overlay, panel, tooltip

HINT = "左键单击棋子查看详情 / 左键拖拽摆位 / 右键卖出 / 拖装备到棋子 / 装备栏拖两件合成 / ESC 退出"


class App:
    PHASE_DEPLOY = "deploy"
    PHASE_BATTLE = "battle"
    PHASE_RESULT = "result"
    PHASE_OVER = "over"

    def __init__(self, game, log_to_console: bool = True, scale: int | None = None) -> None:
        # 必须在 pygame.init() 之前声明 DPI 感知，否则 2560x1600 会被系统再缩放糊掉
        enable_dpi_awareness()
        pygame.init()

        info = pygame.display.Info()
        picked = scale if scale else theme.auto_scale(info.current_w, info.current_h)
        self.scale = theme.set_scale(picked)
        if scale and self.scale != scale:
            print(f"[提示] 缩放被限制为 {self.scale}x（支持 {theme.MIN_SCALE}~{theme.MAX_SCALE}）")
        print(f"[界面] 缩放 {self.scale}x -> 窗口 {theme.WINDOW_W}x{theme.WINDOW_H}")

        _clear_caches()
        pygame.display.set_caption(f"自走棋 1v1  ({theme.WINDOW_W}x{theme.WINDOW_H})")
        self.screen = pygame.display.set_mode((theme.WINDOW_W, theme.WINDOW_H))
        self.clock = pygame.time.Clock()
        self.game = game
        self.log_to_console = log_to_console

        self.running = True
        self.phase = self.PHASE_DEPLOY
        self.message = ""
        self.result_title = ""
        self.result_lines: list[str] = []
        self.drag: dict | None = None  # {"kind":"piece"|"item", "origin", "mouse", ...}
        self.battle: BattleView | None = None
        self.floaters: list[dict] = []  # 金币变动飘字
        self.fx: list[dict] = []  # 升星闪光 / 卡片飞入
        self.time = 0.0
        self.gold_shown = float(game.you.gold)
        self.banner: dict | None = None  # 回合横幅
        self.hover_item: int | None = None
        self.xp_held = False  # 升级按钮是否被按住（长按连升）
        self.xp_cd = 0.0  # 长按连升冷却
        # 左键单击详情：press 记录按下起点，原地松开判为单击
        self._press: dict | None = None
        self.detail: dict | None = None  # {"owner": Player, "piece": Piece}

        # 悬停信息层：每帧由 draw_teams/_draw_traits 更新
        self._seat_blue: dict = {}
        self._seat_red: dict = {}
        self._trait_hits: list = []

        self._init_buttons()

    def _init_buttons(self) -> None:
        op_w, op_h = theme.OP_W, theme.OP_H
        # 左下角操作区：刷新 + 购买经验
        self.btn_refresh = Button(
            (theme.OP_X, theme.OP_REFRESH_Y, op_w, op_h), f"刷新 {REFRESH_COST}金", theme.ACCENT
        )
        self.btn_xp = Button(
            (theme.OP_X, theme.OP_XP_Y, op_w, op_h), "购买经验 4", (210, 150, 70)
        )
        # 右下角：锁定商店 + 开战
        self.btn_lock = Button(
            (theme.LOCK_X, theme.LOCK_Y, theme.SIDE_BTN_W, theme.LOCK_H), "锁定", theme.BORDER
        )
        self.btn_fight = Button(
            (theme.FIGHT_X, theme.FIGHT_Y, theme.SIDE_BTN_W, theme.FIGHT_H), "开战", (86, 190, 130), pulse=True
        )
        self.btn_next = Button(
            (0, 0, theme.BTN_NEXT_W, theme.BTN_NEXT_H), "下一回合", theme.ACCENT, pulse=True
        )

    # ================= 主循环 =================

    def run(self) -> None:
        while self.running:
            dt = self.clock.tick(theme.FPS) / 1000.0
            self.time += dt
            for event in pygame.event.get():
                self.handle_event(event)
            if self.phase == self.PHASE_BATTLE and self.battle is not None:
                self.battle.update(dt)
            self._update_held_xp(dt)
            self._update_fx(dt)
            self.draw()
        pygame.quit()

    def _update_held_xp(self, dt: float) -> None:
        """升级按钮长按连升：按住不放时按冷却连续买经验。"""
        if not self.xp_held or self.phase != self.PHASE_DEPLOY:
            return
        self.xp_cd -= dt
        if self.xp_cd > 0:
            return
        # 鼠标仍按住且在按钮上才继续
        if not pygame.mouse.get_pressed()[0]:
            self.xp_held = False
            return
        if not self.btn_xp.rect.collidepoint(pygame.mouse.get_pos()):
            self.xp_held = False
            return
        self._do_upgrade()
        self.xp_cd = 0.12

    def _do_upgrade(self) -> None:
        before = self.game.you.gold
        self.message = buy_xp(self.game.you)
        self._push_gold_delta(before)

    def _update_fx(self, dt: float) -> None:
        for f in self.floaters + self.fx:
            f["life"] -= dt
        self.floaters = [f for f in self.floaters if f["life"] > 0]
        self.fx = [f for f in self.fx if f["life"] > 0]
        if self.banner is not None:
            self.banner["life"] -= dt
            if self.banner["life"] <= 0:
                self.banner = None

        # 金币数字滚动
        target = float(self.game.you.gold)
        if abs(target - self.gold_shown) < 0.5:
            self.gold_shown = target
        else:
            self.gold_shown += (target - self.gold_shown) * min(1.0, dt * 9)

    # ================= 事件 =================

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.QUIT:
            self.running = False
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if self.detail is not None:  # 先关详情，再按才退出
                self.detail = None
                return
            self.running = False
            return

        if self.phase == self.PHASE_DEPLOY:
            # 松开鼠标：停止长按连升
            if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                self.xp_held = False

            if self.btn_refresh.handle(event):
                before = self.game.you.gold
                self.message = refresh_shop(self.game.you, self.game.shop_you)
                self._push_gold_delta(before)
            elif self.btn_xp.handle(event):
                self._do_upgrade()  # 单击立即升一次
                self.xp_held = True  # 按住不放则由 _update_held_xp 连升
            elif self.btn_lock.handle(event):
                you = self.game.you
                you.locked = not you.locked
                self.message = "商店已锁定（下回合不刷新）" if you.locked else "商店已解锁"
            elif self.btn_fight.handle(event):
                self.start_battle()
            else:
                self.handle_deploy(event)
        elif self.phase == self.PHASE_BATTLE and self.battle is not None:
            self.battle.handle_event(event)
        elif self.phase in (self.PHASE_RESULT, self.PHASE_OVER):
            if self.btn_next.handle(event):
                if self.phase == self.PHASE_OVER:
                    self.running = False
                else:
                    self.next_round()

    def handle_deploy(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                idx = shop_card_at(event.pos)
                if idx is not None:
                    self.buy_card(idx)
                    return
                iidx = item_slot_at(event.pos)
                if iidx is not None and iidx < len(self.game.you.item_bench):
                    self.start_item_drag(iidx)
                    return
                # 不立即拖拽：记下起点，原地松开判定为单击棋子；移动超过阈值才转拖拽
                self._press = {"pos": event.pos}
            elif event.button == 3:  # 右键卖出
                self.sell_at(event.pos)
        elif event.type == pygame.MOUSEMOTION:
            if self.drag:
                self.drag["mouse"] = event.pos
            elif self._press is not None:
                px, py = self._press["pos"]
                x, y = event.pos
                if math.hypot(x - px, y - py) > max(4, int(6 * theme.S)):
                    self.start_drag(self._press["pos"])
                    self._press = None
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self._press is not None:
                pos = self._press["pos"]
                self._press = None
                self._on_piece_click(pos)
            elif self.drag:
                if self.drag.get("kind") == "item":
                    self.drop_item(event.pos)
                else:
                    self.drop(event.pos)

    def _hit_piece(self, pos):
        """屏幕坐标上的棋子及其所属玩家（棋盘蓝/红、你方备战席），没有返回 None。"""
        you = self.game.you
        cell = cell_at(pos)
        if cell is not None:
            p = self._seat_blue.get(cell)
            if p is not None:
                return you, p
            p = self._seat_red.get(cell)
            if p is not None:
                return self.game.enemy, p
        idx = bench_slot_at(pos)
        if idx is not None and idx < len(you.bench):
            return you, you.bench[idx]
        return None

    def _on_piece_click(self, pos) -> None:
        """左键单击开关棋子详情：点棋子打开/切换，点同一棋子或空白处关闭。"""
        hit = self._hit_piece(pos)
        if hit is None:
            self.detail = None
            return
        owner, piece = hit
        if self.detail and self.detail["owner"] is owner and self.detail["piece"] is piece:
            self.detail = None
        else:
            self.detail = {"owner": owner, "piece": piece}

    # ================= 运营阶段交互 =================

    def piece_at_board(self, col: int, row: int):
        """该格子的己方棋子（含自动补位、还没手动落位的）。"""
        p = piece_at(self.game.you, col, row)
        if p is not None:
            return p
        return self._seat_blue.get((col, row))

    def start_drag(self, pos) -> None:
        you = self.game.you
        idx = bench_slot_at(pos)
        if idx is not None and idx < len(you.bench):
            piece = you.bench[idx]
            self.drag = {"kind": "piece", "piece": piece, "origin": "bench", "mouse": pos, "slot": idx}
            return
        cell = cell_at(pos)
        if cell is not None:
            piece = self.piece_at_board(*cell)
            if piece is not None:
                self.drag = {
                    "kind": "piece",
                    "piece": piece,
                    "origin": "board",
                    "mouse": pos,
                    "pos": piece.pos,
                }

    def start_item_drag(self, index: int) -> None:
        """从装备栏拖起一件装备。"""
        it = self.game.you.item_bench[index]
        self.drag = {"kind": "item", "item": it, "slot": index, "mouse": (0, 0)}

    def drop_item(self, pos) -> None:
        """放下装备：到棋子=装备，到装备栏=合成/重排，否则放回。"""
        drag, self.drag = self.drag, None
        you = self.game.you
        item = drag["item"]

        # 拖到棋盘/备战席的棋子身上 = 装备
        target = self._piece_at_screen(pos)
        if target is not None:
            if len(target.equip) >= MAX_ITEMS_PER_PIECE:
                self.message = f"{item_name(item.item_id)} 无法装备：已满 {MAX_ITEMS_PER_PIECE} 件"
                return
            you.item_bench.remove(item)
            target.equip.append(item)
            self.message = f"{item_name(item.item_id)} 已装备"
            return

        # 拖到装备栏另一个格子 = 合成（两件基础装备）
        dest = item_slot_at(pos)
        if dest is not None and dest < len(you.item_bench):
            other = you.item_bench[dest]
            if other is item:
                return
            key = combined_item_id(item.item_id, other.item_id)
            if key:
                you.item_bench.remove(item)
                you.item_bench.remove(other)
                from core.items import ItemInstance

                # 记录两件基础件：卖出装备的棋子时才能拆回（否则基础件凭空消失）
                parts = tuple(key.split("+", 1))
                you.item_bench.append(ItemInstance(key, components=parts))
                self.message = f"合成 {item_name(key)}！"
                self.fx.append(
                    {
                        "kind": "star",
                        "pos": (theme.ITEM_BENCH_X + theme.ITEM_BENCH_W // 2, theme.ITEM_BENCH_Y + 30 * theme.S),
                        "cost": 3,
                        "life": 0.7,
                        "total": 0.7,
                    }
                )
                return
            # 不可合成：交换位置
            self.message = "无法合成，已放回"
            return

        self.message = "放回了原处"

    def _piece_at_screen(self, pos):
        """屏幕坐标上的棋子（优先棋盘，再备战席）。"""
        you = self.game.you
        cell = cell_at(pos)
        if cell is not None:
            p = self.piece_at_board(*cell)
            if p is not None:
                return p
        idx = bench_slot_at(pos)
        if idx is not None and idx < len(you.bench):
            return you.bench[idx]
        return None

    def drop(self, pos) -> None:
        drag, self.drag = self.drag, None
        piece = drag["piece"]
        you = self.game.you

        cell = cell_at(pos)
        if cell is not None:
            self._feedback(move_piece(you, piece, ("board", cell), "blue"))
            return

        idx = bench_slot_at(pos)
        if idx is not None:
            self._feedback(move_piece(you, piece, ("bench", idx), "blue"))
            return

        if pos[1] >= theme.SHOP_Y - 10 * theme.S:  # 拖到商店区域 = 卖出
            before = you.gold
            self.message = sell_piece(you, piece)
            self._push_gold_delta(before)
            return

        self.message = "放回了原处"

    def _feedback(self, result) -> None:
        """只有真的动了才覆盖提示，避免原地不动刷掉上一条有效信息。"""
        if result.message:
            self.message = result.message

    # ---------- 购买与动效 ----------

    @staticmethod
    def _star_map(player) -> dict[str, int]:
        out: dict[str, int] = {}
        for p in list(player.board) + list(player.bench):
            out[p.tid] = max(out.get(p.tid, 0), p.star)
        return out

    def _piece_screen_pos(self, tid: str, star: int):
        you = self.game.you
        for p in you.board:
            if p.tid == tid and p.star == star and p.pos is not None:
                return cell_rect(*p.pos).center
        for i, p in enumerate(you.bench):
            if p.tid == tid and p.star == star:
                return bench_slot_rect(i).center
        return None

    def buy_card(self, idx: int) -> None:
        you = self.game.you
        shop = self.game.shop_you
        item = shop.slots[idx] if 0 <= idx < len(shop.slots) else None
        tid = item.tid if item is not None else None

        before = you.gold
        bench_before = len(you.bench)
        stars_before = self._star_map(you)

        self.message = buy(you, shop, idx)
        self._push_gold_delta(before)

        if tid is None or you.gold == before:
            return  # 没买成（金币不足 / 已售出 / 备战席满）

        # 卡片飞入备战席
        dst = bench_slot_rect(min(bench_before, theme.BENCH_SLOTS - 1)).center
        self.fx.append(
            {
                "kind": "fly",
                "tid": tid,
                "a": shop_card_rect(idx).center,
                "b": dst,
                "life": 0.42,
                "total": 0.42,
            }
        )

        # 升星闪光
        for tid2, star in self._star_map(you).items():
            if star > stars_before.get(tid2, 0):
                pos = self._piece_screen_pos(tid2, star)
                if pos is not None:
                    cost = load_units()[tid2].cost
                    self.fx.append(
                        {"kind": "star", "pos": pos, "cost": cost, "life": 0.7, "total": 0.7}
                    )

    def _push_gold_delta(self, before: int) -> None:
        delta = self.game.you.gold - before
        if delta == 0:
            return
        sign = "+" if delta > 0 else ""
        color = theme.HP_GREEN if delta > 0 else (255, 196, 90)
        self.floaters.append(
            {
                "text": f"{sign}{delta} 金",
                "x": theme.GOLD_X + 40 * theme.S,
                "y": 46 * theme.S,
                "life": 1.0,
                "total": 1.0,
                "color": color,
            }
        )

    def _close_detail_of(self, piece) -> None:
        if self.detail is not None and self.detail["piece"] is piece:
            self.detail = None

    def sell_at(self, pos) -> None:
        you = self.game.you
        before = you.gold
        cell = cell_at(pos)
        if cell is not None:
            piece = self.piece_at_board(*cell)
            if piece is not None:
                self.message = sell_piece(you, piece)
                self._push_gold_delta(before)
                self._close_detail_of(piece)
                return
        idx = bench_slot_at(pos)
        if idx is not None and idx < len(you.bench):
            piece = you.bench[idx]
            self.message = sell_piece(you, piece)
            self._push_gold_delta(before)
            self._close_detail_of(piece)

    # ================= 战斗与回合 =================

    def start_battle(self) -> None:
        """进入战斗回放；动画播完后由 finish_battle 接管结算。

        8 人局：先让所有 AI 运营 + 配对，再打玩家 vs 当前对手的 1v1；
        其余 AI 对局直接结算（不逐场回放，只更新战况）。
        """
        g = self.game
        self.detail = None  # 进入战斗先收起棋子详情

        # 所有 AI 运营
        for i, p in enumerate(g.players):
            if i == 0 or not p.is_alive:
                continue
            ai_take_turn(p, g.shops[i], g.rng)
            ai_equip(p, g.rng)
            ai_upgrade_check(p, g.round)

        g.prepare_battle()
        g.make_pairings()

        # 非玩家参与的 AI 对局：直接结算，更新战况
        for a, b in g.pairings:
            if a != 0 and b != 0:
                c = g.fight_pair(a, b)
                r = c.run() if c is not None else None
                g.settle_pair(a, b, r)

        combat = g.fight()
        if combat is None:
            self.finish_battle(None)
            return
        self.battle = BattleView(combat, on_finish=self.finish_battle)
        self.phase = self.PHASE_BATTLE

    def finish_battle(self, combat) -> None:
        g = self.game
        result = combat.result if combat is not None else None

        if combat is not None and self.log_to_console:
            print(f"\n===== 回合 {g.round} 战斗 =====")
            for e in combat.events:
                if e.type in (EV_CAST, EV_HEAL, EV_DEATH, EV_END):
                    print("  " + format_event(e))

        settle_msg = g.settle(result)

        # 掉落装备
        drops = g.drop_items_for_round()
        if drops:
            settle_msg += f"（掉落 {len(drops)} 件装备）"

        # 淘汰判定
        for p in g.players:
            if p.hp <= 0:
                p.alive = False

        self.result_title = self._title_of(result)
        self.result_lines = [
            settle_msg,
            f"你 {g.you.hp} HP   对手 {g.enemy.hp} HP",
        ]
        self.phase = self.PHASE_OVER if g.is_over() else self.PHASE_RESULT

        if self.phase == self.PHASE_OVER:
            self.result_lines.append(g.winner())
            self.btn_next.label = "退出"
        else:
            self.btn_next.label = "下一回合"
        self.btn_next.rect.size = (theme.BTN_NEXT_W, theme.BTN_NEXT_H)
        self.btn_next.rect.center = (theme.WINDOW_W // 2, theme.WINDOW_H // 2 + 88 * theme.S)

    def _title_of(self, result) -> str:
        if result is None:
            return "本回合无人应战"
        if result.winner == "blue":
            return "本回合胜利"
        if result.winner == "red":
            return "本回合失败"
        return "本回合平局"

    def next_round(self) -> None:
        self.game.round += 1
        self.game.begin_round()
        self.phase = self.PHASE_DEPLOY
        self.message = ""
        self.detail = None
        self.banner = {"text": f"回合 {self.game.round}", "life": 1.25, "total": 1.25}

    # ================= 绘制 =================

    def draw(self) -> None:
        deploying = self.phase == self.PHASE_DEPLOY
        self.btn_fight.enabled = deploying
        self.btn_refresh.enabled = deploying
        self.btn_xp.enabled = deploying
        self.btn_lock.enabled = deploying

        self.screen.fill(theme.BG)
        self.draw_topbar()
        self.draw_op_buttons()
        self.draw_hp_row()
        self.draw_trait_panel()

        if self.phase == self.PHASE_BATTLE and self.battle is not None:
            self.battle.draw(self.screen)
        else:
            draw_grid(self.screen)
            self.draw_teams()
            draw_bench(self.screen, self.visible_bench())
            draw_shop(self.screen, self.game.shop_you.slots)
            self.draw_hints()
            self.draw_drag()

        self.draw_item_bench_ui()
        self.draw_roster_ui()
        self.draw_side_buttons()
        self.draw_fx()
        self.draw_floaters()

        # 悬停详情 tooltip 置于最上层（结果/回合横幅之前）
        if self.phase == self.PHASE_DEPLOY:
            self._draw_hover_layer()

        if self.phase in (self.PHASE_RESULT, self.PHASE_OVER):
            self.draw_result()
        self.draw_banner()
        pygame.display.flip()

    def draw_op_buttons(self) -> None:
        """左下角：刷新 + 购买经验按钮（金铲铲风格垂直堆叠）。"""
        if self.phase != self.PHASE_DEPLOY:
            return
        self.btn_refresh.draw(self.screen, self.time)
        self.btn_xp.draw(self.screen, self.time)

    def draw_side_buttons(self) -> None:
        """右下角：锁定商店 + 开战按钮。"""
        if self.phase != self.PHASE_DEPLOY:
            return
        # 锁定按钮状态
        you = self.game.you
        if you.locked:
            self.btn_lock.label = "已锁定"
            self.btn_lock.color = theme.GOLD
        else:
            self.btn_lock.label = "锁定商店"
            self.btn_lock.color = theme.BORDER
        self.btn_lock.draw(self.screen, self.time)
        self.btn_fight.draw(self.screen, self.time)

    def draw_item_bench_ui(self) -> None:
        """装备栏面板；拖基础装备时给可合成的目标格描金框。"""
        if self.phase != self.PHASE_DEPLOY:
            return
        draw_item_bench(self.screen, self.game.you.item_bench, hover=self.hover_item)
        drag = self.drag
        if drag and drag.get("kind") == "item" and is_base_item(drag["item"].item_id):
            draw_combine_candidates(
                self.screen, self.game.you.item_bench, drag["item"], drag["slot"]
            )

    def draw_roster_ui(self) -> None:
        """8 人战况面板。"""
        draw_roster(self.screen, self.game)

    # ---------- 顶栏 ----------

    def draw_topbar(self) -> None:
        """顶栏三段式：等级+经验（左）、刷新概率（中）、金币+利息（右）。"""
        panel(self.screen, (0, 0, theme.WINDOW_W, theme.TOP_H), theme.PANEL, radius=0)
        pygame.draw.line(
            self.screen, theme.BORDER, (0, theme.TOP_H), (theme.WINDOW_W, theme.TOP_H), 1
        )
        g = self.game
        you = g.you

        # ---- 左：回合 + 等级 + 经验 ----
        text(self.screen, f"回合 {g.round}", theme.FS_TINY, theme.TEXT_DIM, (theme.ROUND_X, theme.ROUND_Y))
        text(self.screen, f"{you.level}级", theme.FS_TITLE, theme.TEXT, (theme.LEVEL_X, theme.LEVEL_Y))
        self.draw_level(you)

        # ---- 中：刷新概率 ----
        self.draw_odds(you.level)

        # ---- 右：金币 + 利息 ----
        text(self.screen, "◎", theme.FS_TITLE, theme.GOLD, (theme.GOLD_X, theme.GOLD_Y))
        gold = int(round(self.gold_shown))
        img = render(str(gold), theme.FS_TITLE, theme.GOLD)
        self.screen.blit(img, (theme.GOLD_X + 26 * theme.S, theme.GOLD_Y))
        interest = self.game.interest_of(gold)
        interest_color = theme.GOLD if interest > 0 else theme.TEXT_DIM
        text(
            self.screen,
            f"利息 +{interest}",
            theme.FS_TINY,
            interest_color,
            (theme.INTEREST_X, theme.INTEREST_Y),
        )

    def draw_level(self, you) -> None:
        """等级旁的经验进度条 + 数字。"""
        from core.player import xp_needed_for_level

        if you.level >= 9:
            text(self.screen, "MAX", theme.FS_TINY, theme.GOLD, (theme.XP_TEXT_X, theme.XP_TEXT_Y))
            return
        need = xp_needed_for_level(you.level + 1)
        xp_rect = pygame.Rect(theme.XP_BAR_X, theme.XP_BAR_Y, theme.XP_BAR_W, theme.XP_BAR_H)
        bar(
            self.screen,
            xp_rect,
            you.xp / max(1, need),
            (210, 150, 70),
            bg=(28, 30, 38),
            radius=theme.XP_BAR_H // 2,
        )
        text(
            self.screen,
            f"{you.xp}/{need}",
            theme.FS_TINY,
            theme.TEXT_DIM,
            (theme.XP_TEXT_X, theme.XP_TEXT_Y),
        )

    def draw_odds(self, level: int) -> None:
        """顶栏中部：当前等级各费用棋子的刷新概率。"""
        from core.player import odds_for_level

        odds = odds_for_level(level)
        x = theme.ODDS_X
        for cost in sorted(odds):
            pct = odds[cost]
            color = theme.rarity(cost)["edge"]
            box = pygame.Rect(x, theme.ODDS_Y, theme.ODDS_BOX, theme.ODDS_BOX)
            panel(self.screen, box, color, radius=max(2, 4 * theme.S))
            text(self.screen, str(cost), theme.FS_MICRO, (255, 255, 255), box.center, center=True)
            pct_color = theme.TEXT if pct > 0 else theme.TEXT_DIM
            text(
                self.screen,
                f"{pct}%",
                theme.FS_TINY,
                pct_color,
                (x + theme.ODDS_BOX + 5 * theme.S, theme.ODDS_Y + 1 * theme.S),
            )
            x += theme.ODDS_GAP

    def draw_hp_row(self) -> None:
        """备战席上方一行：你/对手血条 + 上场数。"""
        g = self.game
        self.draw_hp_bar("你", theme.HP1_X, g.you.hp, theme.TEAM_COLORS["blue"])
        board_count = len(g.you.board)
        cap = g.you.board_cap
        pop_color = theme.GOLD if board_count >= cap else theme.TEXT_DIM
        text(
            self.screen,
            f"上场 {board_count}/{cap}",
            theme.FS_TINY,
            pop_color,
            (theme.POP_X, theme.HP_BAR_Y - 2 * theme.S),
        )
        self.draw_hp_bar("对手", theme.HP2_X, g.enemy.hp, theme.TEAM_COLORS["red"])

    def draw_hp_bar(self, label: str, x: int, hp: int, color) -> None:
        text(self.screen, label, theme.FS_SMALL, theme.TEXT_DIM, (x, theme.HP_BAR_Y - 3 * theme.S))
        rect = pygame.Rect(x + 40 * theme.S, theme.HP_BAR_Y, theme.HP_BAR_W, theme.HP_BAR_H)
        bar(self.screen, rect, hp / 100.0, color, bg=(28, 30, 38), radius=rect.height // 2)
        text(
            self.screen,
            str(hp),
            theme.FS_SMALL,
            theme.TEXT,
            (rect.x + rect.width // 2, rect.y + rect.height // 2),
            center=True,
        )

    # ---------- 左侧羁绊面板 ----------

    def draw_trait_panel(self) -> None:
        rect = pygame.Rect(
            theme.SIDE_PAD,
            theme.TOP_H + 12 * theme.S,
            theme.SIDE_W - theme.SIDE_PAD * 2,
            theme.BOARD_AREA_H - 24 * theme.S,
        )
        panel(self.screen, rect, theme.PANEL, radius=10, border=theme.BORDER)
        self._trait_hits = []

        y = rect.y + 12 * theme.S
        for title, player in (("你的羁绊", self.game.you), ("电脑的羁绊", self.game.enemy)):
            text(self.screen, title, theme.FS_NORMAL, theme.TEXT, (rect.x + 12 * theme.S, y))
            y += 32 * theme.S
            y = self._draw_traits(player, rect.x + 12 * theme.S, y, rect.width - 24 * theme.S)
            y += 18 * theme.S

        pool = self.game.pool
        if pool is not None:
            text(
                self.screen,
                f"卡池剩余 {pool.total_left()} / {pool.total_capacity()}",
                theme.FS_TINY,
                theme.TEXT_DIM,
                (rect.x + 12 * theme.S, rect.bottom - 22 * theme.S),
            )

    def _draw_traits(self, player, x: int, y: int, width: int) -> int:
        """画一栏羁绊：色块 + 名称 + 档位进度，返回结束时的 y。"""
        traits_data = load_traits()
        counts = count_traits_from_tids([p.tid for p in player.board], load_units())
        s = theme.S
        dot = theme.TRAIT_DOT

        if not counts:
            text(self.screen, "（暂无）", theme.FS_TINY, theme.TEXT_DIM, (x, y))
            return y + theme.SIDE_LINE_H

        for tid, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
            info = traits_data.get(tid)
            if info is None:
                continue
            color = theme.TRAIT_COLORS.get(tid, theme.TRAIT_FALLBACK)
            tiers = [t["count"] for t in info.get("tiers", [])]
            active = any(count >= t for t in tiers)

            # 记录整行命中区，供悬停详情 tooltip 使用
            self._trait_hits.append((pygame.Rect(x, y, width, theme.SIDE_LINE_H), tid, count))

            box = pygame.Rect(x, y + (theme.SIDE_LINE_H - dot) // 2, dot, dot)
            panel(
                self.screen,
                box,
                color if active else theme.shade(color, 0.4),
                radius=max(2, dot // 4),
                border=(12, 13, 18),
                width=1,
            )

            name_color = theme.TEXT if active else theme.TEXT_DIM
            text(self.screen, info["name"], theme.FS_SMALL, name_color, (x + dot + 8 * s, y))
            text(
                self.screen,
                str(count),
                theme.FS_SMALL,
                name_color,
                (x + dot + 8 * s + 52 * s, y),
            )

            # 档位进度小菱形
            px = x + dot + 8 * s + 72 * s
            py = y + theme.SIDE_LINE_H // 2
            for need in tiers:
                half = max(3, int(5 * s))
                pts = [(px, py - half), (px + half, py), (px, py + half), (px - half, py)]
                pygame.draw.polygon(
                    self.screen, theme.GOLD if count >= need else (52, 56, 68), pts
                )
                pygame.draw.polygon(self.screen, (12, 13, 18), pts, width=1)
                px += max(6, int(11 * s))
            y += theme.SIDE_LINE_H
        return y

    # ---------- 棋盘 / 队伍 ----------

    def drawing_piece(self):
        return self.drag["piece"] if self.drag else None

    def visible_bench(self):
        p = self.drawing_piece()
        return [x for x in self.game.you.bench if x is not p]

    def draw_teams(self) -> None:
        g = self.game
        skip = self.drawing_piece()
        you_board = [p for p in g.you.board if p is not skip]
        self._seat_blue = self._draw_team(you_board, "blue")
        self._seat_red = self._draw_team(g.enemy.board, "red")

    def _draw_team(self, pieces, team: str) -> dict:
        """按站位画一队，并返回 格子 -> 棋子 的反查表（命中/详情用）。"""
        seat = auto_seat(pieces, team)
        placements = [
            {"id": p.tid, "star": p.star, "pos": [col, row], "equip": p.equip} for p, (col, row) in seat
        ]
        draw_placements(self.screen, placements, team)
        return {tuple(pos): p for p, pos in seat}

    def draw_hints(self) -> None:
        you = self.game.you
        msgs = [HINT]
        if you.bench:
            msgs.append(f"备战席还有 {len(you.bench)} 个棋子未上场（开战会自动补位）")
        if self.message:
            msgs.append(self.message)
        text(self.screen, "   |   ".join(msgs), theme.FS_TINY, theme.TEXT_DIM, (theme.PAD, theme.HINT_Y))

    def draw_drag(self) -> None:
        drag = self.drag
        if not drag:
            return
        # 装备拖拽：单独绘制跟手装备图标
        if drag.get("kind") == "item":
            self._draw_item_drag(drag)
            return
        piece = drag["piece"]
        v = visual_from_tid(piece.tid, piece.star, "blue")
        mouse = drag["mouse"]

        # 己方半场高亮，提示合法落点
        draw_deploy_highlight(self.screen, t=self.time)

        # 原位置半透明占位，避免拖走后格子"凭空消失"
        if drag["origin"] == "board" and drag.get("pos"):
            draw_piece(self.screen, cell_rect(*drag["pos"]), v, ghost=True)

        # 悬停格半透明预览
        cell = self._hover_cell()
        if cell is not None and self.piece_at_board(*cell) is None:
            draw_piece(self.screen, cell_rect(*cell), v, ghost=True)

        # 拖到商店区域：描红 + 卖出金额提示
        if mouse[1] >= theme.SHOP_Y - 10 * theme.S:
            shop_rect = pygame.Rect(
                theme.SHOP_X - 8 * theme.S,
                theme.SHOP_Y - 8 * theme.S,
                theme.SHOP_W + 16 * theme.S,
                theme.SHOP_H + 16 * theme.S,
            )
            pygame.draw.rect(
                self.screen, theme.HP_RED, shop_rect, width=2, border_radius=12 * theme.S
            )
            copies = 3 ** (piece.star - 1)
            value = load_units()[piece.tid].cost * copies
            tooltip(self.screen, f"卖出 +{value} 金", (mouse[0] + 12 * theme.S, theme.SHOP_Y - 34 * theme.S))

        # 跟手棋子（略放大）
        size = theme.CELL
        r = pygame.Rect(0, 0, size, size)
        r.center = mouse
        draw_piece(self.screen, r, v, scale=1.10)

    def _draw_item_drag(self, drag) -> None:
        """跟手装备图标 + 目标高亮。"""
        from .item_view import draw_item_icon

        mouse = drag["mouse"]
        item_id = drag["item"].item_id
        r = pygame.Rect(0, 0, theme.ITEM_CELL, theme.ITEM_CELL)
        r.center = mouse
        draw_item_icon(self.screen, r, item_id)

        # 图标只是首字不可读，跟随时把完整名字标在下方
        text(
            self.screen,
            item_name(item_id),
            theme.FS_TINY,
            theme.TEXT,
            (mouse[0], r.bottom + 8 * theme.S),
            center=True,
        )

        # 悬停棋子高亮，提示可装备
        target = self._piece_at_screen(mouse)
        if target is not None:
            # 找到棋子的屏幕中心
            if target.pos is not None and target in self.game.you.board:
                center = cell_rect(*target.pos).center
            else:
                idx = self.game.you.bench.index(target) if target in self.game.you.bench else -1
                center = bench_slot_rect(idx).center if idx >= 0 else r.center
            if len(target.equip) >= MAX_ITEMS_PER_PIECE:
                pygame.draw.circle(self.screen, theme.HP_RED, center, theme.CELL // 2, width=2)
            else:
                pygame.draw.circle(self.screen, theme.HP_GREEN, center, theme.CELL // 2, width=2)

    # ---------- 悬停信息层 ----------

    def _bench_base_counts(self) -> dict[str, int]:
        """当前装备栏里各基础装备的数量（合成配方提示用）。"""
        counts: dict[str, int] = {}
        for it in self.game.you.item_bench:
            if is_base_item(it.item_id):
                counts[it.item_id] = counts.get(it.item_id, 0) + 1
        return counts

    def _hover_target(self):
        """返回当前鼠标所指区域的信息 (records, accent)；只保留羁绊行与装备栏的悬停。"""
        from .info import item_records, trait_records

        mouse = pygame.mouse.get_pos()
        you = self.game.you

        # 左侧羁绊行：说明 + 各档位阈值
        for rect, tid, count in self._trait_hits:
            if rect.collidepoint(mouse):
                return trait_records(tid, count), theme.TRAIT_COLORS.get(tid, theme.TRAIT_FALLBACK)

        # 装备栏：属性 + 特效 + 当前能合的配方
        iidx = item_slot_at(mouse)
        if iidx is not None and iidx < len(you.item_bench):
            item_id = you.item_bench[iidx].item_id
            records = item_records(item_id, have=self._bench_base_counts())
            accent = theme.GOLD if "+" in item_id else theme.ACCENT
            return records, accent
        return None

    def _detail_anchor(self):
        """单击选中的棋子当前应锚定的屏幕中心；棋子已不在场上返回 None。"""
        d = self.detail
        if d is None:
            return None
        owner, p = d["owner"], d["piece"]
        for seat, who in ((self._seat_blue, self.game.you), (self._seat_red, self.game.enemy)):
            if who is not owner:
                continue
            for cell, q in seat.items():
                if q is p:
                    return cell_rect(*cell).center
        if p.pos is not None:
            col, row = int(round(p.pos[0])), int(round(p.pos[1]))
            if col in range(theme.BOARD_COLS) and row in range(theme.BOARD_ROWS) and p in owner.board:
                return cell_rect(col, row).center
        if p in owner.bench:
            return bench_slot_rect(owner.bench.index(p)).center
        return None

    def _draw_hover_layer(self) -> None:
        """信息层统统一画在最上层：棋子详情由左键单击开关，羁绊行/装备栏保留悬停。"""
        s = theme.S
        mouse = pygame.mouse.get_pos()

        # 单击打开的棋子详情（棋盘 + 备战席，蓝/红都行）
        if self.detail is not None:
            anchor = self._detail_anchor()
            if anchor is None:
                self.detail = None
            else:
                from .info import unit_records

                owner, p = self.detail["owner"], self.detail["piece"]
                records = unit_records(owner, p)
                accent = theme.GOLD if p.star >= 3 else theme.rarity(load_units()[p.tid].cost)["edge"]
                px, py = anchor
                draw_tip(
                    self.screen,
                    records,
                    (px + int(14 * s), py - int(30 * s)),
                    accent=accent,
                )

        # 拖装备时的合成结果预览
        if self.drag is not None:
            if self.drag.get("kind") == "item":
                self._drag_combine_tip()
            return

        # 悬停 tooltip：羁绊行 / 装备栏
        ctx = self._hover_target()
        if ctx is not None:
            records, accent = ctx
            draw_tip(self.screen, records, (mouse[0] + 12 * s, mouse[1]), accent=accent)

    def _drag_combine_tip(self) -> None:
        """拖一件基础装备悬停在另一件上：显示合成结果预览。"""
        from .info import combine_preview_records

        drag = self.drag
        you = self.game.you
        idx = item_slot_at(drag["mouse"])
        if idx is None or idx >= len(you.item_bench) or idx == drag["slot"]:
            return
        other = you.item_bench[idx]
        if other is drag["item"]:
            return
        records = combine_preview_records(drag["item"].item_id, other.item_id)
        if records:
            mouse = drag["mouse"]
            draw_tip(self.screen, records, (mouse[0] + 12 * theme.S, mouse[1]), accent=theme.GOLD)

    def _hover_cell(self):
        if not self.drag:
            return None
        cell = cell_at(self.drag["mouse"])
        if cell is None:
            return None
        col, row = cell
        if row >= theme.BOARD_ROWS // 2:  # 只能己方半场四行（core_row 0..3）
            return None
        return cell

    # ---------- 特效 ----------

    def draw_floaters(self) -> None:
        for f in self.floaters:
            t = 1 - f["life"] / f["total"]
            y = f["y"] - theme.FLOAT_RISE * t
            text(self.screen, f["text"], theme.FS_SMALL, f["color"], (f["x"], int(y)), center=True)

    def draw_fx(self) -> None:
        for fx in self.fx:
            if fx["kind"] == "fly":
                self._draw_fly(fx)
            elif fx["kind"] == "star":
                self._draw_star(fx)

    def _draw_fly(self, fx) -> None:
        t = 1 - fx["life"] / fx["total"]
        ease = 1 - (1 - t) ** 2
        x = fx["a"][0] + (fx["b"][0] - fx["a"][0]) * ease
        y = fx["a"][1] + (fx["b"][1] - fx["a"][1]) * ease
        y -= math.sin(math.pi * t) * 60 * theme.S
        size = int(theme.BENCH_CELL * (1.1 - 0.35 * t))
        v = visual_from_tid(fx["tid"], 1, "blue")
        r = pygame.Rect(0, 0, size, size)
        r.center = (int(x), int(y))
        draw_piece(self.screen, r, v)

    def _draw_star(self, fx) -> None:
        t = 1 - fx["life"] / fx["total"]
        pos = fx["pos"]
        cost = fx.get("cost", 1)
        color = theme.rarity(cost)["edge"]
        radius = max(2, int(theme.CELL * 0.55 * (0.35 + 0.75 * t)))
        alpha = int(230 * (1 - t))
        size = radius * 2 + 14 * theme.S
        lay = pygame.Surface((size, size), pygame.SRCALPHA)
        c = size // 2
        pygame.draw.circle(lay, (*color, alpha), (c, c), radius, width=max(3, int(3 * theme.S)))

        # 十字星光
        if t < 0.6:
            for a in (0, 90, 180, 270):
                rad = math.radians(a)
                dx, dy = math.cos(rad), math.sin(rad)
                pygame.draw.line(
                    lay,
                    (*color, alpha),
                    (c + dx * 8 * theme.S, c + dy * 8 * theme.S),
                    (c + dx * (radius * 1.6), c + dy * (radius * 1.6)),
                    max(2, int(2 * theme.S)),
                )
        self.screen.blit(lay, (pos[0] - c, pos[1] - c))

    def draw_banner(self) -> None:
        if self.banner is None:
            return
        b = self.banner
        t = 1 - b["life"] / b["total"]
        alpha = 255 if t < 0.7 else int(255 * (1 - (t - 0.7) / 0.3))
        img = render(b["text"], theme.FS_TITLE, theme.TEXT)
        img.set_alpha(alpha)
        pad = 20 * theme.S
        w = img.get_width() + pad * 2
        h = img.get_height() + pad
        box = pygame.Rect(0, 0, w, h)
        box.center = (theme.WINDOW_W // 2, theme.TOP_H + theme.BOARD_AREA_H // 2)
        layer = pygame.Surface((w, h), pygame.SRCALPHA)
        layer.fill((12, 14, 20, min(190, alpha)))
        self.screen.blit(layer, box.topleft)
        self.screen.blit(img, (box.x + pad, box.y + pad // 2))

    def draw_result(self) -> None:
        self.screen.blit(dim_overlay((theme.WINDOW_W, theme.WINDOW_H)), (0, 0))

        rect = pygame.Rect(0, 0, theme.RESULT_W, theme.RESULT_H)
        rect.center = (theme.WINDOW_W // 2, theme.WINDOW_H // 2)
        panel(self.screen, rect, theme.PANEL, radius=14, border=theme.BORDER)

        color = theme.TEXT
        if "胜利" in self.result_title:
            color = theme.HP_GREEN
        elif "失败" in self.result_title:
            color = theme.HP_RED
        text(
            self.screen,
            self.result_title,
            theme.FS_TITLE,
            color,
            (rect.centerx, rect.y + 30 * theme.S),
            center=True,
        )

        y = rect.y + 82 * theme.S
        for line in self.result_lines:
            text(self.screen, line, theme.FS_SMALL, theme.TEXT, (rect.centerx, y), center=True)
            y += 28 * theme.S

        self.btn_next.draw(self.screen, self.time)
