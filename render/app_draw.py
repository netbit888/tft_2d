"""纯绘制方法（AppDrawMixin）。

顶栏 / 血条 / 羁绊面板 / 棋盘队伍 / 悬停详情层 / 装备栏 / 特效飘字 /
回合横幅 / 结算面板等所有 draw_*。只读 self 状态并写屏，不改变游戏状态。
配合 AppStateMixin 一起被 render.app.App 多继承使用；不引用 app.py。
"""

from __future__ import annotations

import math

import pygame

from core.deploy import auto_seat
from core.items import (
    MAX_ITEMS_PER_PIECE,
    is_base_item,
    is_special_item,
    item_name,
)
from core.loader import load_traits, load_units
from core.traits import count_traits_from_tids

from . import theme
from .armory_view import draw_armory
from .assets import render, text
from .board_view import (
    cell_at,
    cell_rect,
    draw_deploy_highlight,
    draw_piece,
    draw_placements,
    trait_color,
    visual_from_tid,
)
from .champ_view import draw_champ_picker
from .info import (
    combine_preview_records,
    draw_tip,
    item_records,
    trait_records,
    unit_records,
)
from .item_view import (
    draw_combine_candidates,
    draw_item_bench,
    draw_item_icon,
    draw_roster,
    item_slot_at,
)
from .hud_view import draw_gold_ball, draw_xp_ball
from .shop_view import bench_slot_rect, draw_shop_popup
from .trait_art import draw_trait_icon
from .widgets import bar, dim_overlay, panel, tooltip

HINT = "左下经验球买经验 / 右下金币球开商店 / 左侧页签切换 羁绊/装备 / 单击棋子看详情 / 拖拽摆位 / 拖到最底部空条卖出 / 拖装备到棋子 / ESC 退出"


class AppDrawMixin:
    """纯绘制：HUD / 棋盘队伍 / 悬停层 / 特效 / 结果面板。"""

    def draw_armory(self) -> None:
        """把装备自选台（当前页）画在信息层之上。"""
        draw_armory(self.screen, self.armory_tab)

    def draw_champ_picker(self) -> None:
        """把棋子自选栏（当前费用页）画在信息层之上。"""
        draw_champ_picker(self.screen, self.picker_cost)

    def draw_hud(self) -> None:
        """底部 HUD：左下经验球 + 右下金币球（仅部署期显示）。"""
        if self.phase != self.PHASE_DEPLOY:
            return
        draw_xp_ball(self.screen, self.game.you, self.time)
        draw_gold_ball(self.screen, self.game.you, self.time, gold=self.gold_shown)

    def draw_shop_popup(self) -> None:
        """商店浮层：点右下金币球打开，遮罩 + 面板（卡面 / 概率 / 刷新 / 锁定 / 关闭）。"""
        if self.phase != self.PHASE_DEPLOY or not self.shop_open:
            return
        draw_shop_popup(
            self.screen,
            self.game.shop_you.slots,
            self.game.you.level,
            hints=self._shop_hints(),
            locked=self.game.you.locked,
            t=self.time,
        )

    def draw_side_buttons(self) -> None:
        """右下角：开战按钮（刷新/锁定已随商店移入浮层）。"""
        if self.phase != self.PHASE_DEPLOY:
            return
        self.btn_fight.draw(self.screen, self.time)

    def _draw_item_page(self) -> None:
        """装备页：装备栏面板铺满左侧内容区。"""
        you = self.game.you
        self._trait_hits = []  # 切到装备页后羁绊行不再可悬停
        draw_item_bench(
            self.screen, you.item_bench, hover=self.hover_item, scroll=self.item_scroll
        )
        drag = self.drag
        if drag and drag.get("kind") == "item" and is_base_item(drag["item"].item_id):
            draw_combine_candidates(
                self.screen,
                you.item_bench,
                drag["item"],
                drag["slot"],
                scroll=self.item_scroll,
            )

    def draw_roster_ui(self) -> None:
        """8 人战况面板：支持点击行切换观察视角。"""
        # 未开战不透露本回合对手配对（黄色框等），开战/结算后再标出
        opp_marker = None if self.phase == self.PHASE_DEPLOY else self.game.current_opponent
        self._roster_rows = draw_roster(
            self.screen,
            self.game,
            selected=self._view_index(),
            current_opp=opp_marker,
        )

    def draw_hp_row(self) -> None:
        """备战席上方一行：你/对手血条 + 上场人口。

        需求：未开战（部署阶段）且看自己时不显示本回合对手的血条，
        对手信息只在我方开战/结算后，或玩家在战况面板主动选择某位对手时出现。
        上场人口按“弈子栏位”计：远古巨龙等大型单位占 2 个人口。
        """
        g = self.game
        self.draw_hp_bar("你", theme.HP1_X, g.you.hp, theme.TEAM_COLORS["blue"])
        pop_now = g.you.board_pop
        cap = g.you.board_cap
        pop_color = theme.GOLD if pop_now >= cap else theme.TEXT_DIM
        text(
            self.screen,
            f"人口 {pop_now}/{cap}",
            theme.FS_TINY,
            pop_color,
            (theme.POP_X, theme.HP_BAR_Y - 2 * theme.S),
        )

        if not self._opponent_visible():
            return  # 未开战且看自己：隐藏本回合对手信息
        target = self._bar_target()
        viewing = self._view_index() != 0
        self.draw_hp_bar(
            target.name,
            theme.HP2_X,
            target.hp,
            theme.TEAM_COLORS["red"],
            label_color=theme.GOLD if viewing else None,
        )
        # 部署阶段给右侧血条画一个可点击的提示框（观察电脑 / 返回自己）
        if self.phase == self.PHASE_DEPLOY:
            zone = self._hp2_zone()
            hovered = zone.collidepoint(pygame.mouse.get_pos())
            pygame.draw.rect(
                self.screen,
                theme.GOLD if hovered else theme.BORDER,
                zone,
                width=1,
                border_radius=8,
            )

    def draw_hp_bar(self, label: str, x: int, hp: int, color, label_color=None) -> None:
        text(
            self.screen,
            label,
            theme.FS_SMALL,
            label_color if label_color is not None else theme.TEXT_DIM,
            (x, theme.HP_BAR_Y - 3 * theme.S),
        )
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

    def _side_panel_rect(self) -> pygame.Rect:
        """左侧内容区矩形（页签栏右侧那一块）。"""
        return pygame.Rect(
            theme.SIDE_CONTENT_X,
            theme.SIDE_PANEL_Y,
            theme.SIDE_CONTENT_W,
            theme.SIDE_PANEL_H,
        )

    def draw_side_panel(self) -> None:
        """左侧面板：窄页签栏（羁绊/装备）+ 内容区，点哪个页签就显示哪个。"""
        from .side_view import draw_side_tabs

        draw_side_tabs(self.screen, self.side_tab, self.time)
        if self.side_tab == "items":
            self._draw_item_page()
        else:
            self._draw_trait_page()

    def _draw_trait_page(self) -> None:
        """羁绊页：当前观察对象的阵容羁绊（六边形图标 + 名称 + 人数/下一档）。"""
        rect = self._side_panel_rect()
        panel(self.screen, rect, theme.PANEL, radius=10, border=theme.BORDER)
        self._trait_hits = []

        s = theme.S
        # 阵容羁绊：选谁（观察谁）就只显示谁的，不把两人的羁绊并排显示。
        # 默认看自己 -> “你的羁绊”；在战况面板/血条点选了某玩家 -> 只显示该玩家的。
        viewing = self._view_player()
        title = "你的羁绊" if self._view_index() == 0 else f"{viewing.name} 的羁绊"
        text(self.screen, title, theme.FS_SMALL, theme.TEXT, (rect.x + 10 * s, rect.y + 8 * s))

        self._draw_traits(
            viewing,
            rect.x + 10 * s,
            rect.y + 32 * s,
            rect.width - 20 * s,
            limit_y=rect.bottom - 26 * s,
        )

    def _draw_traits(self, player, x: int, y: int, width: int, limit_y: int | None = None) -> int:
        """画一栏羁绊：六边形图标 + 名称 + 已激活人数/下一档，返回结束时的 y。"""
        traits_data = load_traits()
        counts = count_traits_from_tids([p.tid for p in player.board], load_units())
        s = theme.S
        hex_size = theme.TRAIT_HEX
        line_h = theme.SIDE_LINE_H

        if not counts:
            text(self.screen, "（暂无）", theme.FS_TINY, theme.TEXT_DIM, (x, y))
            return y + line_h

        right = x + width
        for tid, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
            info = traits_data.get(tid)
            if info is None:
                continue
            if limit_y is not None and y + line_h > limit_y:
                break  # 阵容羁绊太多时截断，避免溢出面板底部
            levels = [
                int(n)
                for n in (info.get("levels") or [t["count"] for t in info.get("tiers", [])])
            ]
            active = bool(levels) and count >= levels[0]
            nxt = next((n for n in levels if count < n), None)

            cy = y + line_h // 2
            # 记录整行命中区，供悬停详情 tooltip 使用
            self._trait_hits.append((pygame.Rect(x, y, width, line_h), tid, count))

            draw_trait_icon(self.screen, (x + hex_size // 2, cy), hex_size, tid, active=active)

            name_color = theme.TEXT if active else theme.TEXT_DIM
            img = render(info["name"], theme.FS_SMALL, name_color)
            self.screen.blit(img, (x + hex_size + 8 * s, cy - img.get_height() // 2))

            label = f"{count}/{nxt}" if nxt is not None else f"{count}"
            cnt_color = theme.GOLD if active else theme.TEXT_DIM
            cimg = render(label, theme.FS_TINY, cnt_color)
            self.screen.blit(cimg, cimg.get_rect(midright=(right, cy)))

            y += line_h
        return y

    def drawing_piece(self):
        """当前正在拖拽的棋子；只有棋子拖拽（kind=="piece"）才返回。

        拖装备（kind=="item"）时字典没有 piece 键——这里必须返回 None，
        否则 draw_teams / visible_bench 会对装备拖拽取 drag["piece"] 抛 KeyError。
        注意：即使装备是从棋子身上拖起的（换装），源棋子也仍在原位要正常绘制，
        因此不能按“有没有 piece 键”判断，只能按 kind。
        """
        drag = self.drag
        if drag and drag.get("kind") == "piece":
            return drag.get("piece")
        return None

    def visible_bench(self):
        p = self.drawing_piece()
        return [x for x in self.game.you.bench if x is not p]

    def draw_teams(self) -> None:
        """需求1：默认只显示自己的棋子；点选某电脑后切换到只显示该电脑的棋子。

        开战/回放阶段由 BattleView 画双方，不受这里影响（“开战后双方可见”）。
        """
        skip = self.drawing_piece()
        self._seat_blue = {}
        self._seat_red = {}
        owner = self._red_owner()
        if owner is None:  # 默认视角：自己
            you_board = [p for p in self.game.you.board if p is not skip]
            self._seat_blue = self._draw_team(you_board, "blue")
        else:  # 观察某台电脑：显示其红色半场
            tboard = [p for p in owner.board if p is not skip]
            self._seat_red = self._draw_team(tboard, "red")

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
        msgs = [HINT, "F2=装备自选台", "F3=棋子自选栏"]
        if you.bench:
            msgs.append(f"备战席还有 {len(you.bench)} 个棋子未上场（开战会自动补位）")
        # 需求1：观察视角提示
        if self._view_index() != 0:
            msgs.append(f"正在观察 {self._view_player().name} 的棋子，点右侧血条返回自己")
        elif self.phase == self.PHASE_DEPLOY:
            # 未开战不显示本回合对手信息；战况面板选择谁即显示谁的阵容
            msgs.append("未开战不显示本回合对手信息（战况面板点名字可看其棋盘与羁绊）")
        else:
            msgs.append("点右侧血条可查看电脑的棋盘")
        if self.message:
            msgs.append(self.message)
        text(self.screen, "   |   ".join(msgs), theme.FS_TINY, theme.TEXT_DIM, (theme.PAD, theme.HINT_Y))

    def draw_drag(self) -> None:
        """拖拽场景提示层（画在棋盘层）：落点高亮 / 原位置占位 / 卖出提示。

        与"跟手对象"分开：跟手棋子与装备图标由 draw_drag_icon 在所有面板
        之后绘制，保证不会被装备栏 / 按钮等遮挡（需求3）。
        """
        drag = self.drag
        if not drag or drag.get("kind") == "item":
            return  # 装备拖拽没有棋盘场景提示，跟手部分统一交给 draw_drag_icon
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

        # 拖到最底部空条（商店搬走后的留白）：描红 + 卖出金额提示
        if self._sell_zone().collidepoint(mouse):
            pygame.draw.rect(
                self.screen, theme.HP_RED, self._sell_zone(), width=2, border_radius=12 * theme.S
            )
            copies = 3 ** (piece.star - 1)
            value = load_units()[piece.tid].cost * copies
            tooltip(
                self.screen,
                f"卖出 +{value} 金",
                (mouse[0] + 12 * theme.S, self._sell_zone().y - 34 * theme.S),
            )

    def draw_drag_icon(self) -> None:
        """跟手对象层：拖拽中的棋子 / 装备图标，在全部面板之后绘制（需求3）。

        独立成层后，无论把装备拖到装备栏、右侧按钮区还是商店上方，跟手
        图标始终最上层、不会被遮挡。
        """
        drag = self.drag
        if not drag:
            return
        if drag.get("kind") == "item":
            self._draw_item_drag(drag)
            return
        piece = drag["piece"]
        v = visual_from_tid(piece.tid, piece.star, "blue")
        r = pygame.Rect(0, 0, theme.CELL, theme.CELL)
        r.center = drag["mouse"]
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

        # 悬停棋子高亮：金粗圈=可与身上散件合成（松手即合成）；绿=可装备；
        # 红=已满 3 件；金制拆卸器则提示"可卸下装备"
        target = self._piece_at_screen(mouse)
        if target is not None:
            # 找到棋子的屏幕中心
            if target.pos is not None and target in self.game.you.board:
                center = cell_rect(*target.pos).center
            else:
                idx = self.game.you.bench.index(target) if target in self.game.you.bench else -1
                center = bench_slot_rect(idx).center if idx >= 0 else r.center
            # 金制拆卸器：提示"可卸下装备"（金圈），不按装备栏上限提示
            if is_special_item(item_id):
                color = theme.GOLD if target.equip else theme.TEXT_DIM
                pygame.draw.circle(self.screen, color, center, theme.CELL // 2, width=2)
            elif drag.get("piece") is not target and self._piece_combine_mate(target, drag["item"]) is not None:
                pygame.draw.circle(self.screen, theme.GOLD, center, theme.CELL // 2, width=3)
            elif len(target.equip) >= MAX_ITEMS_PER_PIECE:
                pygame.draw.circle(self.screen, theme.HP_RED, center, theme.CELL // 2, width=2)
            else:
                pygame.draw.circle(self.screen, theme.HP_GREEN, center, theme.CELL // 2, width=2)

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
                return trait_records(tid, count), trait_color(tid)

        # 装备栏（只有装备页可见）：属性 + 特效 + 当前能合的配方
        if self.side_tab == "items":
            iidx = item_slot_at(mouse, self.item_scroll, len(you.item_bench))
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
        for seat, who in ((self._seat_blue, self.game.you), (self._seat_red, self._red_owner())):
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
        """拖一件基础装备时的合成结果预览：
        1) 悬停在装备栏另一件上；
        2) 悬停在"身上带可合成散件"的棋子上（需求2，松手即合成并装备）。
        """
        from .info import combine_preview_records

        drag = self.drag
        you = self.game.you
        item = drag["item"]
        mouse = drag["mouse"]
        tip_pos = (mouse[0] + 12 * theme.S, mouse[1])

        # 装备栏（只有装备页可见）：与另一件基础装备合成
        idx = (
            item_slot_at(mouse, self.item_scroll, len(you.item_bench))
            if self.side_tab == "items"
            else None
        )
        if idx is not None and idx < len(you.item_bench) and idx != drag["slot"]:
            other = you.item_bench[idx]
            if other is not item:
                records = combine_preview_records(item.item_id, other.item_id)
                if records:
                    draw_tip(self.screen, records, tip_pos, accent=theme.GOLD)
                return

        # 棋子：与它身上的散件合成（同样显示合成详情）
        target = self._piece_at_screen(mouse)
        if target is not None and drag.get("piece") is not target:
            mate = self._piece_combine_mate(target, item)
            if mate is not None:
                records = combine_preview_records(item.item_id, mate.item_id)
                if records:
                    name = load_units()[target.tid].name
                    records.append((f"松手合成并装备到 {name}", theme.FS_TINY, theme.TEXT_DIM))
                    draw_tip(self.screen, records, tip_pos, accent=theme.GOLD)

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

    def draw_floaters(self) -> None:
        for f in self.floaters:
            t = 1 - f["life"] / f["total"]
            y = f["y"] - theme.FLOAT_RISE * t
            text(self.screen, f["text"], theme.FS_SMALL, f["color"], (f["x"], int(y)), center=True)

    def draw_fx(self) -> None:
        for fx in self.fx:
            if fx["kind"] == "star":
                self._draw_star(fx)

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

        # 伤害统计：本回合战斗的复盘（数据来自事件流聚合，跳过战斗也有）
        if self.battle is not None:
            from .recap import draw_recap

            rows = self.battle.stats_rows()
            if rows:
                recap = pygame.Rect(0, 0, 680 * theme.S, 270 * theme.S)
                recap.centerx = theme.WINDOW_W // 2
                recap.bottom = theme.WINDOW_H - 10 * theme.S
                draw_recap(self.screen, rows, recap, title="本回合伤害统计")
