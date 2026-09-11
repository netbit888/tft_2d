"""图形界面入口（App 骨架 + 主循环）。

职责：把 Game 的“单一真源”驱动接到 pygame 界面上 ——
  部署交互 / 成装自选台 / 拖拽购买在 render.app_state 的 AppStateMixin，
  各类 UI 绘制在 render.app_draw 的 AppDrawMixin，
  本模块只保留：初始化、主循环、战斗回放/回合推进状态机与 draw() 编排。

操作：
  右下金币球          打开/关闭商店浮层（浮层内刷新 / 锁定 / 点卡购买）
  左下经验球          点（或长按）花金币买经验提升人口上限
  备战席 -> 棋盘       上场
  棋盘内拖动           交换位置
  棋盘 -> 备战席       下场
  右键棋子 / 拖到最底部空条  卖出
  拖装备到棋子         装备
  装备栏内拖动         合成（两件基础装备）
  开战                 自动补位 -> 电脑运营 -> 战斗 -> 结算

支持 1v1 与 8 人局（--players 8）。8 人局每回合两两配对打 1v1。
"""

from __future__ import annotations

import pygame

from core import buy_xp
from core.events import EV_CAST, EV_DEATH, EV_END, EV_HEAL, format_event

from . import theme
from .app_draw import AppDrawMixin
from .app_state import AppStateMixin
from .assets import enable_dpi_awareness
from .audio import Audio
from .battle_view import BattleView
from .board_view import _clear_caches, draw_grid
from .hud_view import xp_ball_hit
from .shop_view import draw_bench
from .widgets import Button


class App(AppDrawMixin, AppStateMixin):
    # 相位常量被 AppStateMixin/AppDrawMixin 引用（走 self.PHASE_*）
    PHASE_DEPLOY = "deploy"

    PHASE_BATTLE = "battle"

    PHASE_RESULT = "result"

    PHASE_OVER = "over"

    def __init__(self, game, log_to_console: bool = True, scale: int | None = None) -> None:
        # 必须在 pygame.init() 之前声明 DPI 感知，否则 2560x1600 会被系统再缩放糊掉
        enable_dpi_awareness()
        # 音频：用与 WAV 资源一致的采样率先设定 mixer（失败不影响启动）
        try:
            pygame.mixer.pre_init(22050, -16, 2, 512)
        except Exception:
            pass
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
        self.fx: list[dict] = []  # 升星闪光
        self.time = 0.0
        self.gold_shown = float(game.you.gold)
        self.banner: dict | None = None  # 回合横幅
        self.hover_item: int | None = None
        self.item_scroll = 0  # 装备栏背包滚动偏移（无上限背包，鼠标悬停滚轮翻页）
        self.side_tab = "traits"  # 左侧面板页签：traits=羁绊 / items=装备
        self.armory_open = False  # 装备自选台（F2 唤出/关闭）
        self.armory_tab = 0  # 自选台当前页：0=成装，1=散件（重开时保留上次页）
        self.picker_open = False  # 棋子自选栏（F3 唤出/关闭）
        self.picker_cost = 1  # 棋子自选栏当前费用页 1~5（重开时保留上次页）
        self.shop_open = False  # 商店浮层（点右下金币球唤出/关闭）
        self.xp_held = False  # 经验球是否被按住（长按连升）
        self.xp_cd = 0.0  # 长按连升冷却
        # 左键单击详情：press 记录按下起点，原地松开判为单击
        self._press: dict | None = None
        self.detail: dict | None = None  # {"owner": Player, "piece": Piece}

        # 观察视角（需求1）：默认 0=自己；>0 表示点选了某台电脑观察其棋盘/羁绊
        self._view = 0
        self._roster_rows: list = []  # 战况面板可点行的命中区 [(rect, index)]

        # 音频：先开部署曲；无声卡/缺资源则整体禁用，不影响运行
        self.audio = Audio()
        if self.audio.enabled:
            self.audio.music.play("deploy")

        # 悬停信息层：每帧由 draw_teams/_draw_traits 更新
        self._seat_blue: dict = {}
        self._seat_red: dict = {}
        self._trait_hits: list = []

        self._init_buttons()

    def _init_buttons(self) -> None:
        # 右下角：开战按钮（刷新 / 购买经验 / 锁定已分别并入商店浮层与双球）
        self.btn_fight = Button(
            (theme.FIGHT_X, theme.FIGHT_Y, theme.SIDE_BTN_W, theme.FIGHT_H), "开战", (86, 190, 130), pulse=True
        )
        self.btn_next = Button(
            (0, 0, theme.BTN_NEXT_W, theme.BTN_NEXT_H), "下一回合", theme.ACCENT, pulse=True
        )

    def run(self) -> None:
        while self.running:
            dt = self.clock.tick(theme.FPS) / 1000.0
            self.time += dt
            for event in pygame.event.get():
                self.handle_event(event)
            if self.audio.enabled:
                self.audio.update(dt)
            if self.phase == self.PHASE_BATTLE and self.battle is not None:
                self.battle.update(dt)
            self._update_held_xp(dt)
            self._update_fx(dt)
            self.draw()
        pygame.quit()

    def _update_held_xp(self, dt: float) -> None:
        """经验球长按连升：按住不放时按冷却连续买经验。"""
        if (
            not self.xp_held
            or self.phase != self.PHASE_DEPLOY
            or self.armory_open
            or self.picker_open
            or self.shop_open
        ):
            return
        self.xp_cd -= dt
        if self.xp_cd > 0:
            return
        # 鼠标仍按住且在经验球上才继续
        if not pygame.mouse.get_pressed()[0] or not xp_ball_hit(pygame.mouse.get_pos()):
            self.xp_held = False
            return
        self._do_upgrade()
        self.xp_cd = 0.12

    def _do_upgrade(self) -> None:
        before = self.game.you.gold
        level_before = self.game.you.level
        self.message = buy_xp(self.game.you)
        self._push_gold_delta(before)
        if self.game.you.level > level_before:  # 人口上限提升
            self.audio.sfx.play("star")

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

    def start_battle(self) -> None:
        """进入战斗回放；动画播完后由 finish_battle 接管结算。

        规则推进全部交给 Game 的“单一真源”：AI 运营 → 补位/配对 →
        AI 对局即时结算；玩家本人的对局以 Combat 返回，交给 BattleView 逐帧回放。
        """
        g = self.game
        self.detail = None  # 进入战斗先收起棋子详情
        self.shop_open = False  # 商店浮层不进战斗
        self.xp_held = False

        self.audio.sfx.play("fight")
        self.audio.music.play("battle")

        g.run_ai_ops()  # 所有存活 AI 运营（买棋/上阵/穿戴/升级）

        combat = g.start_battle()  # 补位/配对 + AI 互打即时结算
        if combat is None:
            self.finish_battle(None)
            return
        self.battle = BattleView(
            combat,
            on_finish=self.finish_battle,
            names={"blue": g.you.name, "red": g.players[g.current_opponent].name},
        )
        self.phase = self.PHASE_BATTLE

    def finish_battle(self, combat) -> None:
        g = self.game
        outcome = g.finish_battle(combat)  # 结算 + 掉落 + 淘汰判定（内核单一真源）
        result = outcome["result"]

        if combat is None:
            # 一方无棋子直接结算：清掉旧战斗对象，结算画面不显示过期伤害统计
            self.battle = None

        if combat is not None and self.log_to_console:
            print(f"\n===== 回合 {g.round} 战斗 =====")
            for e in combat.events:
                if e.type in (EV_CAST, EV_HEAL, EV_DEATH, EV_END):
                    print("  " + format_event(e))

        settle_msg = outcome["settle_msg"]
        if outcome["drops"]:
            settle_msg += f"（掉落 {len(outcome['drops'])} 件装备）"

        # 正在观察的电脑被淘汰则回到自己视角
        idx = self._view_index()
        if idx != 0 and not g.players[idx].is_alive:
            self._view = 0

        self.result_title = self._title_of(result)
        opp = g.players[g.current_opponent]  # 本回合真实对手（8 人局每回合变化）
        self.result_lines = [
            settle_msg,
            f"你 {g.you.hp} HP   {opp.name} {opp.hp} HP",
        ]
        self.phase = self.PHASE_OVER if outcome["over"] else self.PHASE_RESULT

        # 战歌切回：一次性 victory/defeat jingle，播完自动回部署曲（终局则保持安静）
        if result is None:
            self.audio.music.play("deploy")
        else:
            after = "deploy" if self.phase != self.PHASE_OVER else None
            if result.winner == "blue":
                self.audio.music.play_once("victory", after=after)
            elif result.winner == "red":
                self.audio.music.play_once("defeat", after=after)
            else:
                self.audio.music.play("deploy")

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
        self.game.advance_round()  # 回合号 +1 并发放下一回合收入（内核单一真源）
        self.phase = self.PHASE_DEPLOY
        self._view = 0  # 新回合默认回到自己视角
        self._roster_rows = []
        self.shop_open = False  # 新回合收起商店浮层
        self.xp_held = False
        self.audio.music.play("deploy")
        self.message = ""
        self.detail = None
        self.banner = {"text": f"回合 {self.game.round}", "life": 1.25, "total": 1.25}

    def draw(self) -> None:
        deploying = self.phase == self.PHASE_DEPLOY
        self.btn_fight.enabled = deploying

        self.screen.fill(theme.BG)
        self.draw_hp_row()
        self.draw_side_panel()

        if self.phase == self.PHASE_BATTLE and self.battle is not None:
            self.battle.draw(self.screen)
        else:
            draw_grid(self.screen)
            self.draw_teams()
            draw_bench(self.screen, self.visible_bench())
            self.draw_hints()
            self.draw_drag()

        self.draw_roster_ui()
        self.draw_side_buttons()
        self.draw_hud()
        self.draw_fx()
        self.draw_floaters()

        # 悬停详情 tooltip 置于最上层（结果/回合横幅之前）；自选台/自选栏/商店浮层打开时不画，避免被遮罩透出
        if (
            self.phase == self.PHASE_DEPLOY
            and not self.armory_open
            and not self.picker_open
            and not self.shop_open
        ):
            self._draw_hover_layer()

        # 商店浮层：遮罩 + 面板（点右下金币球唤出），独占鼠标事件
        self.draw_shop_popup()

        # 装备自选台（F2）/ 棋子自选栏（F3）：画在信息层之上，独占鼠标事件
        if self.armory_open:
            self.draw_armory()
        elif self.picker_open:
            self.draw_champ_picker()

        if self.phase in (self.PHASE_RESULT, self.PHASE_OVER):
            self.draw_result()
        self.draw_banner()
        # 需求3：拖拽中"跟手对象"最后绘制，保证无论拖到装备栏/按钮/商店上方都不被遮挡
        self.draw_drag_icon()
        pygame.display.flip()
