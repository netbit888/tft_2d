"""部署/运营期交互状态（AppStateMixin）。

观察视角切换、键盘/鼠标事件分发、成装自选台（F2）、备战席拖拽摆位、
装备装卸与合成、买卡/卖卡/买经验等全部“改变状态”的交互。
配合 AppDrawMixin 一起被 render.app.App 多继承使用；不引用 app.py，
因此不存在循环导入。
"""

from __future__ import annotations

import math

import pygame

from core.deploy import move_piece, piece_at
from core.items import (
    ITEM_BENCH_CAP,
    MAX_ITEMS_PER_PIECE,
    ItemInstance,
    combined_item_id,
    is_special_item,
    item_name,
)
from core.loader import load_units
from core.player import next_star_if_buy
from core.shop import buy, refresh_shop, sell_piece

from . import theme
from .armory_view import armory_geometry
from .board_view import cell_at, cell_rect
from .item_view import item_slot_at
from .shop_view import bench_slot_at, bench_slot_rect, shop_card_at, shop_card_rect


class AppStateMixin:
    """部署/运营期全部交互（观察视角、事件分发、拖拽、自选台、买卖）。"""

    def _view_index(self) -> int:
        g = self.game
        if 0 < self._view < len(g.players):
            return self._view
        return 0

    def _view_player(self):
        """当前观察到的玩家（view=自己时即自己）。"""
        return self.game.players[self._view_index()]

    def _red_owner(self):
        """部署阶段画在红色半场的玩家；观察自己（默认）时返回 None=不显示对手。"""
        idx = self._view_index()
        if idx == 0:
            return None
        return self.game.players[idx]

    def _bar_target(self):
        """右侧血条显示的对象：默认显示本回合配对对手（含电脑编号），观察电脑时显示该电脑。"""
        g = self.game
        idx = self._view_index()
        if idx != 0:
            return g.players[idx]
        return g.players[g.current_opponent]

    def _set_view(self, idx: int) -> None:
        g = self.game
        if idx < 0 or idx >= len(g.players):
            return
        if idx != 0 and not g.players[idx].is_alive:
            return
        if self._view != idx:
            self._view = idx
            self.detail = None  # 换人观察时收起旧详情

    def _toggle_view(self) -> None:
        g = self.game
        if self._view_index() == 0:
            opp = g.current_opponent
            if g.players[opp].is_alive:
                self._set_view(opp)
        else:
            self._set_view(0)

    def _hp2_zone(self) -> pygame.Rect:
        """右侧血条（标签+条+数字）整体的点击区：1v1 用它切换观察视角。"""
        return pygame.Rect(
            theme.HP2_X - 8 * theme.S,
            theme.HP_BAR_Y - 16 * theme.S,
            40 * theme.S + theme.HP_BAR_W + 16 * theme.S,
            theme.HP_BAR_H + 22 * theme.S,
        )

    def _shop_hints(self) -> list[int]:
        """每张未售商店卡：再买一张能否触发升星（返回合成目标 2/3 星，否则 0）。"""
        shop = self.game.shop_you
        out = [0] * len(shop.slots)
        for i, item in enumerate(shop.slots):
            if not item.sold:
                out[i] = next_star_if_buy(self.game.you, item.tid)
        return out

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.QUIT:
            self.running = False
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_m:
            if self.audio.enabled:
                muted = self.audio.toggle_muted()
                self.message = "已静音（再按 M 恢复）" if muted else "已恢复声音"
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if self.armory_open:  # 先关自选台，再关详情，最后才退出
                self._toggle_armory()
                return
            if self.detail is not None:
                self.detail = None
                return
            self.running = False
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_F2 and self.phase == self.PHASE_DEPLOY:
            self._toggle_armory()
            return

        if self.phase == self.PHASE_DEPLOY:
            # 松开鼠标：停止长按连升（自选台打开时同样要停）
            if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                self.xp_held = False
            if self.armory_open:
                self._armory_event(event)
                return

            if self.btn_refresh.handle(event):
                before = self.game.you.gold
                self.message = refresh_shop(self.game.you, self.game.shop_you)
                self._push_gold_delta(before)
                self.audio.sfx.play("refresh" if self.game.you.gold < before else "error")
            elif self.btn_xp.handle(event):
                self._do_upgrade()  # 单击立即升一次
                self.xp_held = True  # 按住不放则由 _update_held_xp 连升
            elif self.btn_lock.handle(event):
                you = self.game.you
                you.locked = not you.locked
                self.message = "商店已锁定（下回合不刷新）" if you.locked else "商店已解锁"
                self.audio.sfx.play("lock")
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
                # 观察视角切换（需求1）：右侧血条 / 战况面板行
                if self._hp2_zone().collidepoint(event.pos):
                    self._toggle_view()
                    return
                for row_rect, pidx in self._roster_rows:
                    if row_rect.collidepoint(event.pos):
                        self._set_view(pidx)
                        return
                idx = shop_card_at(event.pos)
                if idx is not None:
                    self.buy_card(idx)
                    return
                iidx = item_slot_at(event.pos)
                if iidx is not None and iidx < len(self.game.you.item_bench):
                    self.start_item_drag(iidx)
                    return
                # 棋子身上的装备徽章：直接拖起（可换装 / 拖回装备栏卸下 / 参与合成）
                src = self._piece_equip_drag_source(event.pos)
                if src is not None:
                    piece, k = src
                    self.drag = {
                        "kind": "item",
                        "item": piece.equip[k],
                        "src": "piece",
                        "piece": piece,
                        "slot": k,
                        "mouse": event.pos,
                    }
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

    def _toggle_armory(self) -> None:
        """F2 / ESC / 关闭按钮 / 点面板外：开关成装自选台。

        打开时中断进行中的拖拽与单击详情，防止面板挡住的操作误触发底层事件。
        """
        if self.phase != self.PHASE_DEPLOY:
            return
        self.armory_open = not self.armory_open
        if self.armory_open:
            self.drag = None
            self._press = None
            self.detail = None
            self.xp_held = False  # 中止可能的"长按买经验"

    def _armory_event(self, event) -> None:
        """自选台打开时独占点击：点格获得装备，点 ✕ / 面板外关闭。"""
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return
        g = armory_geometry()
        pos = event.pos
        if g["close"].collidepoint(pos):
            self._toggle_armory()
            return
        if not g["panel"].collidepoint(pos):
            self._toggle_armory()
            return
        for cell in g["cells"]:
            if cell["rect"].collidepoint(pos):
                self._grant_from_armory(cell["item_id"])
                return

    def _grant_from_armory(self, item_id: str) -> None:
        """点击自选台格子：放入一件到装备栏（可连点，任意数量）。

        金制拆卸器比较特殊：装备栏已有则不再重复获取（它不消耗）。
        """
        you = self.game.you
        if is_special_item(item_id):
            if any(it.item_id == item_id for it in you.item_bench):
                self.message = "装备栏已有金制拆卸器（不消耗，无需重复获取）"
                return
            you.item_bench.append(ItemInstance(item_id))
            self.message = f"获得 {item_name(item_id)}：拖到棋子身上卸下其全部装备（不消耗）"
            self.audio.sfx.play("buy")
            return
        if len(you.item_bench) >= ITEM_BENCH_CAP:
            self.message = f"装备栏已满（{ITEM_BENCH_CAP} 格），先给棋子装备或腾出位置"
            self.audio.sfx.play("error")
            return
        you.item_bench.append(ItemInstance(item_id))
        self.message = f"获得 {item_name(item_id)}（可继续点击，每次 1 件）"
        self.audio.sfx.play("buy")

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
                owner = self._red_owner()  # 8 人局可观察任意电脑，不能写死 g.enemy
                if owner is not None:
                    return owner, p
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
        self.drag = {
            "kind": "item",
            "item": it,
            "src": "bench",
            "slot": index,
            "mouse": (0, 0),
        }

    def _equip_badge_at(self, pos, rect: pygame.Rect, n: int) -> int | None:
        """命中棋子装备徽章的序号（几何与棋盘/备战席绘制一致）；没命中返回 None。"""
        n = min(n, 3)
        gap = max(10, int(12 * theme.S))
        start_x = rect.centerx - (n - 1) * gap // 2
        y = rect.bottom - max(4, int(5 * theme.S))
        half = max(8, int(8 * theme.S))
        for k in range(n):
            cx = start_x + k * gap
            if abs(pos[0] - cx) <= half and abs(pos[1] - y) <= half:
                return k
        return None

    def _piece_equip_drag_source(self, pos):
        """命中己方棋子身上的装备徽章：返回 (piece, equip_index)，否则 None。"""
        you = self.game.you
        cell = cell_at(pos)
        if cell is not None:
            p = self.piece_at_board(*cell)
            if p is not None and p.equip:
                k = self._equip_badge_at(pos, cell_rect(*cell), len(p.equip))
                if k is not None:
                    return p, k
        idx = bench_slot_at(pos)
        if idx is not None and idx < len(you.bench):
            p = you.bench[idx]
            if p.equip:
                k = self._equip_badge_at(pos, bench_slot_rect(idx), len(p.equip))
                if k is not None:
                    return p, k
        return None

    def drop_item(self, pos) -> None:
        """放下装备：到棋子=装备/换装，到装备栏=合成/卸下，否则放回原处。"""
        drag, self.drag = self.drag, None
        you = self.game.you
        item = drag["item"]
        src = drag.get("src", "bench")
        src_piece = drag.get("piece")

        # 特殊工具（金制拆卸器）：不走装备/合成逻辑，整体交给专用方法处理
        if is_special_item(item.item_id):
            self._use_remover(item, pos)
            return

        def take_out() -> None:
            """从拖拽源移出装备（装备栏 / 棋子身上）。"""
            if src == "bench":
                you.item_bench.remove(item)
            elif src_piece is not None and item in src_piece.equip:
                src_piece.equip.remove(item)

        # 拖到棋盘/备战席的棋子身上 = 装备 / 换装
        target = self._piece_at_screen(pos)
        if target is not None:
            if target is src_piece:
                self.message = "已放回"
                return
            if len(target.equip) >= MAX_ITEMS_PER_PIECE:
                self.message = f"{item_name(item.item_id)} 无法装备：已满 {MAX_ITEMS_PER_PIECE} 件"
                self.audio.sfx.play("error")
                return
            take_out()
            target.equip.append(item)
            if src == "piece":
                self.message = f"{item_name(item.item_id)} 已换装"
            else:
                self.message = f"{item_name(item.item_id)} 已装备"
            self.audio.sfx.play("equip")
            return

        # 拖到装备栏：空格=卸下/放回，有装备的格子=尝试合成
        from core.items import ITEM_BENCH_CAP, ItemInstance

        dest = item_slot_at(pos)
        if dest is not None and dest < ITEM_BENCH_CAP:
            if dest < len(you.item_bench):
                other = you.item_bench[dest]
                if other is item:
                    return
                key = combined_item_id(item.item_id, other.item_id)
                if key:
                    take_out()
                    you.item_bench.remove(other)
                    # 记录两件基础件：卖出装备的棋子时才能拆回（否则基础件凭空消失）
                    parts = tuple(key.split("+", 1))
                    you.item_bench.append(ItemInstance(key, components=parts))
                    self.message = f"合成 {item_name(key)}！"
                    self.audio.sfx.play("combine")
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
                self.message = "无法合成，已放回"
                return
            # 空装备栏格：从棋子身上卸下放入装备栏
            if src == "piece":
                take_out()
                you.item_bench.append(item)
                self.message = f"{item_name(item.item_id)} 已卸下放入装备栏"
                return
        self.message = "放回了原处"

    def _use_remover(self, item, pos) -> None:
        """金制拆卸器使用：拖到棋子身上 = 卸下其全部装备回装备栏。

        道具本身不消耗（不限次数）；拖到非棋子位置也直接放回原处。
        卸下的装备插入装备栏栏首，保证立即可见。
        """
        you = self.game.you
        target = self._piece_at_screen(pos)
        if target is None:
            self.message = f"{item_name(item.item_id)}：请拖到棋子身上使用（不消耗）"
            return
        if not target.equip:
            self.message = f"该棋子没有装备，{item_name(item.item_id)} 未消耗"
            return
        moved = list(target.equip)
        target.equip.clear()
        you.item_bench[0:0] = moved
        names = "、".join(item_name(it.item_id) for it in moved)
        self.message = (
            f"{item_name(item.item_id)}：已卸下 {len(moved)} 件装备回装备栏（{names}）"
        )
        self.audio.sfx.play("equip")

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
            if you.gold > before:
                self.audio.sfx.play("sell")
            return

        self.message = "放回了原处"

    def _feedback(self, result) -> None:
        """只有真的动了才覆盖提示，避免原地不动刷掉上一条有效信息。"""
        if result.message:
            self.message = result.message

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
            if tid is not None:
                self.audio.sfx.play("error")  # 有目标卡却没扣钱：购买失败
            return  # 没买成（金币不足 / 已售出 / 备战席满）

        self.audio.sfx.play("buy")
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
                    self.audio.sfx.play("star")

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
                if you.gold > before:
                    self.audio.sfx.play("sell")
                return
        idx = bench_slot_at(pos)
        if idx is not None and idx < len(you.bench):
            piece = you.bench[idx]
            self.message = sell_piece(you, piece)
            self._push_gold_delta(before)
            self._close_detail_of(piece)
            if you.gold > before:
                self.audio.sfx.play("sell")
