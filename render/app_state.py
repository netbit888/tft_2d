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
    MAX_ITEMS_PER_PIECE,
    ItemInstance,
    combined_item_id,
    is_special_item,
    item_name,
)
from core.loader import load_units
from core.player import MAX_BENCH, Piece, next_star_if_buy, try_upgrade
from core.shop import buy, refresh_shop, sell_piece

from . import theme
from .armory_view import armory_geometry
from .board_view import cell_at, cell_rect, piece_feet_y
from .champ_view import champ_entries, champ_geometry
from .hud_view import gold_ball_hit, xp_ball_hit
from .item_view import item_slot_at
from .shop_view import (
    bench_slot_at,
    bench_slot_rect,
    shop_card_at,
    shop_close_rect,
    shop_lock_rect,
    shop_panel_rect,
    shop_refresh_rect,
)
from .side_view import side_tab_at


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

    def _opponent_visible(self) -> bool:
        """右侧“本回合对手”信息是否可见。

        需求：未开战（部署阶段）且看自己时不显示本回合对手；
        一旦开战/进入结算，或玩家主动在战况面板选择某位玩家观察时即可见。
        """
        return self.phase != self.PHASE_DEPLOY or self._view_index() != 0

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
            self._esc_quit = True  # 关窗 = 中途退出，菜单循环据此回主页/退出
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_m:
            if self.audio.enabled:
                muted = self.audio.toggle_muted()
                self.message = "已静音（再按 M 恢复）" if muted else "已恢复声音"
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if self.phase == self.PHASE_BATTLE:  # 战斗中 ESC 只收起战斗详情，不退出
                if self.battle is not None:
                    self.battle.detail_unit = None
                return
            if self.armory_open:  # 先关自选台，再关详情，最后才退出
                self._toggle_armory()
                return
            if self.picker_open:  # 棋子自选栏同理，优先级高于详情
                self._toggle_picker()
                return
            if self.shop_open:  # 商店浮层次之
                self._toggle_shop()
                return
            if self.detail is not None:
                self.detail = None
                return
            # 部署期 ESC（无任何浮层/详情时）= 中途退回主页
            self.running = False
            self._esc_quit = True
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_F2 and self.phase == self.PHASE_DEPLOY:
            self._toggle_armory()
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_F3 and self.phase == self.PHASE_DEPLOY:
            self._toggle_picker()
            return

        if self.phase == self.PHASE_DEPLOY:
            # 松开鼠标：停止长按连升（自选台/浮层打开时同样要停）
            if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                self.xp_held = False
            if self.armory_open:
                self._armory_event(event)
                return
            if self.picker_open:
                self._picker_event(event)
                return
            if self.shop_open:
                self._shop_event(event)
                return

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if xp_ball_hit(event.pos):  # 经验球：立即升一次，按住则由 _update_held_xp 连升
                    self._do_upgrade()
                    self.xp_held = True
                    return
                if gold_ball_hit(event.pos):  # 金币球：开关商店浮层
                    self._toggle_shop()
                    return
            if self.btn_fight.handle(event):
                self.start_battle()
            else:
                self.handle_deploy(event)
        elif self.phase == self.PHASE_BATTLE and self.battle is not None:
            self.battle.handle_event(event)
        elif self.phase in (self.PHASE_RESULT, self.PHASE_OVER):
            if self.btn_next.handle(event):
                if self.phase == self.PHASE_OVER:
                    self.running = False  # 终局“返回主页”：自然结束，菜单循环回主页
                else:
                    self.next_round()

    def handle_deploy(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEWHEEL:
            self._scroll_item_bench(event)
            return
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                # 左侧页签（羁绊 / 装备）：切换内容区显示，优先级最高
                tab = side_tab_at(event.pos)
                if tab is not None:
                    self.set_side_tab(tab)
                    return
                # 观察视角切换：右侧血条（部署期看自己时对手栏隐藏，故不可点）/ 战况面板行
                if self._opponent_visible() and self._hp2_zone().collidepoint(event.pos):
                    self._toggle_view()
                    return
                for row_rect, pidx in self._roster_rows:
                    if row_rect.collidepoint(event.pos):
                        self._set_view(pidx)
                        return
                # 商店卡只在浮层里可买（见 _shop_event），此处不再响应
                # 装备栏只在「装备」页可拖起，羁绊页时左侧区域不响应装备操作
                if self.side_tab == "items":
                    iidx = item_slot_at(event.pos, self.item_scroll, len(self.game.you.item_bench))
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

    def set_side_tab(self, key: str) -> None:
        """切换左侧面板页签（traits=羁绊 / items=装备）。

        切换时收起进行中的拖拽与单击详情，避免把上一位页的坐标误判到新页面上。
        """
        from .item_view import clamp_scroll

        if key not in ("traits", "items") or key == self.side_tab:
            return
        self.side_tab = key
        self.drag = None
        self._press = None
        self.hover_item = None
        self.item_scroll = clamp_scroll(self.item_scroll, len(self.game.you.item_bench))

    def _scroll_item_bench(self, event) -> None:
        """鼠标悬停在装备栏面板上时用滚轮翻页（背包无上限，每页 3x4 格）。"""
        from .item_view import clamp_scroll

        you = self.game.you
        if self.side_tab != "items" or self.armory_open or not you.item_bench:
            return
        panel = pygame.Rect(
            theme.ITEM_BENCH_X,
            theme.ITEM_BENCH_Y,
            theme.ITEM_BENCH_W,
            theme.ITEM_BENCH_H,
        )
        if not panel.collidepoint(pygame.mouse.get_pos()):
            return
        step = theme.ITEM_COLS  # 每滚一格滚动一行
        dy = getattr(event, "y", 0)
        self.item_scroll = clamp_scroll(self.item_scroll - dy * step, len(you.item_bench))

    def _toggle_armory(self) -> None:
        """F2 / ESC / 关闭按钮 / 点面板外：开关成装自选台。

        打开时中断进行中的拖拽与单击详情，防止面板挡住的操作误触发底层事件；
        同时收起棋子自选栏（两面板互斥）。
        """
        if self.phase != self.PHASE_DEPLOY:
            return
        self.armory_open = not self.armory_open
        if self.armory_open:
            self.picker_open = False
            self.shop_open = False
            self.drag = None
            self._press = None
            self.detail = None
            self.xp_held = False  # 中止可能的"长按买经验"

    def _toggle_picker(self) -> None:
        """F3 / ESC / 关闭按钮 / 点面板外：开关棋子自选栏（1~5 费五页，免费领棋子）。

        与装备自选台互斥；打开时同样中断拖拽与详情。
        """
        if self.phase != self.PHASE_DEPLOY:
            return
        self.picker_open = not self.picker_open
        if self.picker_open:
            self.armory_open = False
            self.shop_open = False
            self.drag = None
            self._press = None
            self.detail = None
            self.xp_held = False  # 中止可能的"长按买经验"

    def _toggle_shop(self) -> None:
        """金币球 / ESC / 关闭 ✕ / 点面板外：开关商店浮层。

        打开时中断拖拽与详情，并与自选台、自选栏互斥；浮层期间独占鼠标。
        """
        if self.phase != self.PHASE_DEPLOY:
            return
        self.shop_open = not self.shop_open
        if self.shop_open:
            self.armory_open = False
            self.picker_open = False
            self.drag = None
            self._press = None
            self.detail = None
            self.xp_held = False  # 中止可能的"长按买经验"

    def _shop_event(self, event) -> None:
        """商店浮层打开时独占点击：买卡 / 刷新 / 锁定，点 ✕ 或面板外关闭。"""
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return
        pos = event.pos
        if shop_close_rect().collidepoint(pos):
            self._toggle_shop()
            return
        if not shop_panel_rect().collidepoint(pos):
            self._toggle_shop()
            return
        if shop_refresh_rect().collidepoint(pos):
            before = self.game.you.gold
            self.message = refresh_shop(self.game.you, self.game.shop_you)
            self._push_gold_delta(before)
            self.audio.sfx.play("refresh" if self.game.you.gold < before else "error")
            return
        if shop_lock_rect().collidepoint(pos):
            you = self.game.you
            you.locked = not you.locked
            self.message = "商店已锁定（下回合不刷新）" if you.locked else "商店已解锁"
            self.audio.sfx.play("lock")
            return
        idx = shop_card_at(pos)
        if idx is not None:
            self.buy_card(idx)

    def _armory_event(self, event) -> None:
        """自选台打开时独占点击：切页 / 点格获得装备，点 ✕ / 面板外关闭。"""
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return
        g = armory_geometry(self.armory_tab)
        pos = event.pos
        if g["close"].collidepoint(pos):
            self._toggle_armory()
            return
        if not g["panel"].collidepoint(pos):
            self._toggle_armory()
            return
        for t in g["tabs"]:
            if t["rect"].collidepoint(pos):
                self.armory_tab = t["tab"]
                return
        for cell in g["cells"]:
            if cell["rect"].collidepoint(pos):
                self._grant_from_armory(cell["entry"])
                return

    def _picker_event(self, event) -> None:
        """棋子自选栏打开时独占点击：切页 / 点格免费领棋子，点 ✕ / 面板外关闭。"""
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return
        g = champ_geometry(self.picker_cost)
        pos = event.pos
        if g["close"].collidepoint(pos):
            self._toggle_picker()
            return
        if not g["panel"].collidepoint(pos):
            self._toggle_picker()
            return
        for t in g["tabs"]:
            if t["rect"].collidepoint(pos):
                self.picker_cost = t["tab"] + 1  # tab 顺序即 1~5 费
                return
        for cell in g["cells"]:
            if cell["rect"].collidepoint(pos):
                self._grant_from_picker(cell["entry"])
                return

    def _grant_from_picker(self, tid: str) -> None:
        """点击棋子自选栏格子：免费获得 1 个到备战席（可连点），凑齐 3 张自动升星。"""
        you = self.game.you
        if len(you.bench) >= MAX_BENCH:
            self.message = "备战席已满，先上阵或卖掉一个棋子"
            self.audio.sfx.play("error")
            return
        name = load_units()[tid].name
        you.bench.append(Piece(tid))
        upgrades = try_upgrade(you)
        if upgrades:
            self.message = f"免费获得 {name}：" + "、".join(upgrades)
            self.audio.sfx.play("star")
        else:
            self.message = f"免费获得 {name}，已放入备战席"
            self.audio.sfx.play("buy")

    def _grant_from_armory(self, item_id: str) -> None:
        """点击自选台格子：放入一件到装备栏（可连点，任意数量，背包无上限）。

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
        you.item_bench.append(ItemInstance(item_id))
        self.message = f"获得 {item_name(item_id)}（装备栏共 {len(you.item_bench)} 件，可继续点击）"
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
        y = piece_feet_y(rect) - max(4, int(5 * theme.S))
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
        """放下装备：到棋子=合成/装备/换装，到装备栏=合成/卸下，否则放回原处。"""
        drag, self.drag = self.drag, None
        you = self.game.you
        item = drag["item"]
        src = drag.get("src", "bench")
        src_piece = drag.get("piece")

        # 特殊工具（金制拆卸器）：不走装备/合成逻辑，整体交给专用方法处理
        if is_special_item(item.item_id):
            self._use_remover(item, pos)
            return

        def pop_item(seq: list, target) -> bool:
            """按对象身份移除（同值基础装备可能有多件，用 == 移除会误删）。"""
            for k, x in enumerate(seq):
                if x is target:
                    del seq[k]
                    return True
            if target in seq:  # 兜底：值相同也接受
                seq.remove(target)
                return True
            return False

        def take_out() -> None:
            """从拖拽源移出装备（装备栏 / 棋子身上）。"""
            if src == "bench":
                pop_item(you.item_bench, item)
            elif src_piece is not None:
                pop_item(src_piece.equip, item)

        # 拖到棋盘/备战席的棋子身上
        target = self._piece_at_screen(pos)
        if target is not None:
            if target is src_piece:
                self.message = "已放回"
                return
            # 需求2：拖基础件到"身上带散件"的棋子 → 与第一件可合成散件自动合成
            mate = self._piece_combine_mate(target, item)
            if mate is not None:
                key = combined_item_id(item.item_id, mate.item_id)
                take_out()
                pop_item(target.equip, mate)
                target.equip.append(ItemInstance(key, components=tuple(key.split("+", 1))))
                center = self._piece_center_screen(target)
                if center is not None:
                    self.fx.append(
                        {"kind": "star", "pos": center, "cost": 3, "life": 0.7, "total": 0.7}
                    )
                name = load_units()[target.tid].name
                self.message = f"合成 {item_name(key)}！已装备到 {name}"
                self.audio.sfx.play("combine")
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

        # 拖到装备栏：有装备的格=合成/放回，可见空格=从棋子身上卸下。
        # 装备栏背包无上限，命中检测统一走"当前滚动窗口 -> 绝对下标"。
        from .item_view import clamp_scroll

        self.item_scroll = clamp_scroll(self.item_scroll, len(you.item_bench))
        # 只有「装备」页可见时才把“落在左侧内容区”判为放回/卸下，羁绊页不误触
        dest = (
            item_slot_at(pos, self.item_scroll, len(you.item_bench))
            if self.side_tab == "items"
            else None
        )
        if dest is not None:
            if dest < len(you.item_bench):
                other = you.item_bench[dest]
                if other is item:
                    return
                key = combined_item_id(item.item_id, other.item_id)
                if key:
                    take_out()
                    pop_item(you.item_bench, other)
                    you.item_bench.append(ItemInstance(key, components=tuple(key.split("+", 1))))
                    self.message = f"合成 {item_name(key)}！"
                    self.audio.sfx.play("combine")
                    self.fx.append(
                        {
                            "kind": "star",
                            "pos": (
                                theme.ITEM_BENCH_X + theme.ITEM_BENCH_W // 2,
                                theme.ITEM_BENCH_Y + theme.ITEM_TITLE_H // 2,
                            ),
                            "cost": 3,
                            "life": 0.7,
                            "total": 0.7,
                        }
                    )
                    return
                self.message = "无法合成，已放回"
                return
            # 可见空格：从棋子身上卸下放入装备栏
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
        self.item_scroll = 0  # 卸下装备插在栏首，滚回顶部立即可见
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

    def _piece_combine_mate(self, target, item):
        """target 身上第一件能与 item 合成的基础件；无则返回 None。

        需求2：拖一件基础装备到"身上带着散件"的棋子时，与它身上的散件
        直接合成（顺序取 target.equip 里靠前的可合成件，结果确定可预期）。
        """
        for o in target.equip:
            if combined_item_id(item.item_id, o.item_id):
                return o
        return None

    def _piece_center_screen(self, p):
        """棋子当前所在位置的屏幕中心（棋盘 / 备战席），用于合成闪光定位。"""
        if p.pos is not None and p in self.game.you.board:
            col, row = int(round(p.pos[0])), int(round(p.pos[1]))
            if col in range(theme.BOARD_COLS) and row in range(theme.BOARD_ROWS):
                return cell_rect(col, row).center
        if p in self.game.you.bench:
            return bench_slot_rect(self.game.you.bench.index(p)).center
        return None

    def _sell_zone(self) -> pygame.Rect:
        """卖出区：备战席下方那条空白（原商店位置，商店搬进浮层后留白）。"""
        return pygame.Rect(
            theme.SELL_ZONE_X,
            theme.SELL_ZONE_Y,
            theme.SELL_ZONE_W,
            theme.SELL_ZONE_H,
        )

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

        if self._sell_zone().collidepoint(pos):  # 拖到最底部空条 = 卖出
            before = you.gold
            self.message = sell_piece(you, piece)
            self.item_scroll = 0  # 回栏装备插在栏首，滚回顶部立即可见
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
        stars_before = self._star_map(you)

        self.message = buy(you, shop, idx)
        self._push_gold_delta(before)

        if tid is None or you.gold == before:
            if tid is not None:
                self.audio.sfx.play("error")  # 有目标卡却没扣钱：购买失败
            return  # 没买成（金币不足 / 已售出 / 备战席满）

        self.audio.sfx.play("buy")

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
                "x": theme.GOLD_BALL_X,
                "y": theme.GOLD_BALL_Y - theme.BALL_R - 26 * theme.S,
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
                self.item_scroll = 0  # 回栏装备插在栏首，滚回顶部立即可见
                self._push_gold_delta(before)
                self._close_detail_of(piece)
                if you.gold > before:
                    self.audio.sfx.play("sell")
                return
        idx = bench_slot_at(pos)
        if idx is not None and idx < len(you.bench):
            piece = you.bench[idx]
            self.message = sell_piece(you, piece)
            self.item_scroll = 0
            self._push_gold_delta(before)
            self._close_detail_of(piece)
            if you.gold > before:
                self.audio.sfx.play("sell")
