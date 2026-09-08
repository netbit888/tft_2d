"""战斗模拟器：固定步长 tick 推进，产出事件日志。

设计要点：
- 与渲染完全解耦，可在无窗口环境跑完整场战斗；
- 固定 20 tick/s，与帧率无关，保证同种子结果可复现；
- 战斗过程写入事件流，渲染层只负责回放。
"""

from __future__ import annotations

from . import grid
from .events import (
    EV_ATTACK,
    EV_CAST,
    EV_DAMAGE,
    EV_DEATH,
    EV_END,
    EV_HEAL,
    EV_MOVE,
    Event,
)
from .models import (
    CRIT_MULTIPLIER,
    MANA_ON_TAKE_HIT,
    MANA_PER_ATTACK,
    CombatResult,
    Unit,
)
from .rng import Rng
from .stats import ability_power, mitigate, snapshot

TICK_RATE = 20
DT = 1.0 / TICK_RATE
DEFAULT_MAX_TICKS = TICK_RATE * 45  # 45 秒上限，超时按剩余血量判胜负

# ---------- 装备特效参数 ----------
# data/items.json 只声明 effect 名，具体数值集中在此，方便统一调平衡。
CRIT_DMG_BONUS = 0.25        # crit_damage：暴击伤害 +0.25（暴击 1.5 → 1.75）
ARMOR_PEN_PCT = 0.30         # armor_pen：普攻无视目标 30% 护甲
MAGIC_RESIST_PCT = 0.30      # magic_resist：受到的魔法伤害 -30%
LIFESTEAL_PCT = 0.25         # lifesteal：普攻吸血比例
SPELL_VAMP_PCT = 0.25        # spell_vamp：技能吸血比例
CLEAVE_PCT = 0.50            # aoe_cleave：普攻对目标邻格溅射 50% 伤害
THORNS_PCT = 0.20            # thorns：被普攻命中时反弹已结算伤害的 20%
MULTI_SHOT_PCT = 0.40        # multi_shot：分裂弓副目标伤害比例
GW_DUR = 6.0                 # grievous_wounds：重伤持续秒数
GW_REDUCE = 0.50             # 重伤期间治疗/吸血 -50%
BURN_DUR = 3.0               # burn：目标燃烧持续秒数
BURN_AD_PCT = 0.15           # 燃烧秒伤 = 佩戴者攻击力 * 15%
REGEN_PCT = 0.02             # regen：每秒回复最大生命 2%
REVIVE_HP_PCT = 0.50         # revive：复活时回复 50% 最大生命
RAMP_STEP = 0.08             # ramping_as：羊刀每次命中叠 +8% 攻速
RAMP_CAP = 0.64              # 羊刀攻速叠加上限 +64%
ON_CAST_AD = 0.20            # on_cast_buff：三相施法后强化期内普攻 +20%
ON_CAST_DUR = 6.0            # 三相强化持续秒数
MANA_AP_STEP = 15.0          # mana_ap：大天使每次施法永久 +15 法强
GIANT_SLAYER_RATIO = 1.5     # giant_slayer：目标最大生命 ≥ 自身 1.5 倍触发
GIANT_SLAYER_PCT = 0.25      # 对高生命目标额外伤害 +25%
AP_AMP_PCT = 0.35            # ap_amp：灭世者的死亡之帽，施法时法强 +35%
SLOW_AURA_RANGE = 2          # slow_aura：冰心减速光环半径（六边形格）
SLOW_AURA_REDUCE = 0.25      # 光环内敌人攻速 -25%


class Combat:
    def __init__(
        self,
        blue: list[Unit],
        red: list[Unit],
        seed: int | None = None,
        max_ticks: int = DEFAULT_MAX_TICKS,
    ) -> None:
        self.units: list[Unit] = []
        self.by_uid: dict[int, Unit] = {}
        for u in list(blue) + list(red):
            u.uid = len(self.units) + 1
            u.cell = (int(round(u.x)), int(round(u.y)))
            u.transit = False
            self.units.append(u)
            self.by_uid[u.uid] = u

        self.rng = Rng(seed)
        self.seed = seed
        self.events: list[Event] = []
        self.tick = 0
        self.max_ticks = max_ticks
        self.finished = False
        self.result: CombatResult | None = None

    # ---------- 对外接口 ----------

    def run(self) -> CombatResult:
        """一次性跑完整场战斗。"""
        while not self.finished:
            self.step()
        assert self.result is not None
        return self.result

    def step(self) -> None:
        """推进一个 tick。渲染层也可以按真实时间逐 tick 调用它。"""
        if self.finished:
            return
        self.tick += 1

        # 先统一决策、后统一结算：同一 tick 内的攻击全部生效，
        # 不会因为出手顺序靠前就抹掉对方的攻击（允许同归于尽）。
        # 移动按六边形格进行（需求3）：先让正在滑行的单位落位/继续滑行，
        # 再基于“每格一子”的占格表做移动与攻击决策。
        for u in self.units:
            if u.alive and u.transit:
                self._glide(u)

        # 占格表：每个六边形格同时最多存在一个存活单位（transit 单位占“预定”格）
        occ: dict[tuple[int, int], Unit] = {u.cell: u for u in self.units if u.alive}

        moves: list[tuple[Unit, tuple[int, int]]] = []
        attacks: list[tuple[Unit, Unit]] = []

        for u in self.units:
            if not u.alive or u.transit:
                continue
            target = self._acquire(u)
            if target is None:
                continue
            if self._in_range(u, target):
                if target.transit:
                    # 目标正滑向预定格：站在射程内等它落格，避免“打半路”的错位
                    continue
                u.attack_timer += DT
                # 羊刀叠攻速：interval 按累积攻速计算
                interval = 1.0 / max(u.attack_speed * (1.0 + u.as_stack), 0.05)
                if self._slowed_by_aura(u):  # 冰心减速光环
                    interval /= 1.0 - SLOW_AURA_REDUCE
                if u.attack_timer >= interval:
                    u.attack_timer -= interval
                    attacks.append((u, target))
            else:
                dest = self._plan_step(u, target, occ)
                if dest is not None:
                    # 立刻让出旧格并占住新格，杜绝同 tick 两个单位抢同一格
                    occ.pop(u.cell, None)
                    occ[dest] = u
                    moves.append((u, dest))

        # 奇偶 tick 交替结算顺序，抵消残余的先后手效应
        if self.tick % 2 == 0:
            moves.reverse()
            attacks.reverse()

        for u, dest in moves:
            self._start_move(u, dest)
        for u, target in attacks:
            self._attack(u, target)

        if not self.finished:
            self._apply_status()
            self._check_end()

    def alive_units(self, team: str | None = None) -> list[Unit]:
        return [u for u in self.units if u.alive and (team is None or u.team == team)]

    def snapshots(self) -> list[dict]:
        return [snapshot(u) for u in self.units]

    # ---------- 内部逻辑 ----------

    def _emit(self, type_: str, **data) -> None:
        self.events.append(Event(self.tick, type_, data))

    def _in_range(self, u: Unit, target: Unit) -> bool:
        """射程判定改为六边形格距离；滑行未落格时不可攻击。"""
        return (
            not u.transit
            and grid.hex_distance(u.cell, target.cell) <= u.attack_range
        )

    def _start_move(self, u: Unit, dest: tuple[int, int]) -> None:
        """逻辑格立即切到 dest（调用方已保证该格空闲唯一），画面随后滑行过去。"""
        u.cell = dest
        u.transit = True

    def _glide(self, u: Unit) -> None:
        """把画面位置按移速平滑滑到当前逻辑格中心；完整落格后发一次移动事件。"""
        cx, cy = float(u.cell[0]), float(u.cell[1])
        dx, dy = cx - u.x, cy - u.y
        dist = (dx * dx + dy * dy) ** 0.5
        if dist < 1e-6:
            u.x, u.y = cx, cy
            u.transit = False
            return
        step = min(u.move_speed * DT, dist)
        if step < dist:
            u.x += dx / dist * step
            u.y += dy / dist * step
        else:
            u.x, u.y = cx, cy
            u.transit = False
            self._emit(
                EV_MOVE,
                name=u.name,
                team=u.team,
                uid=u.uid,
                x=round(cx, 2),
                y=round(cy, 2),
            )

    def _plan_step(
        self,
        u: Unit,
        target: Unit,
        occ: dict[tuple[int, int], Unit],
    ) -> tuple[int, int] | None:
        """六边形格寻路：避开其它单位，找一条通往“目标落在攻击距离内”的空格
        的最短路径，返回第一步要走的格子；无路可走时原地等待（返回 None）。
        """
        from collections import deque

        start = u.cell
        if occ.get(start) is not None and occ[start] is not u:
            return None
        prev: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
        queue: deque[tuple[int, int]] = deque([start])
        tcell = target.cell
        goal: tuple[int, int] | None = None
        while queue:
            node = queue.popleft()
            if node != start and grid.hex_distance(node, tcell) <= u.attack_range:
                goal = node
                break
            for nb in grid.hex_neighbors(node):
                if nb in prev:
                    continue
                holder = occ.get(nb)
                if holder is not None and holder is not u:
                    continue
                prev[nb] = node
                queue.append(nb)
        if goal is None:
            return None
        # 回溯到紧邻起点的那一步
        cur: tuple[int, int] = goal
        while prev[cur] != start:
            parent = prev[cur]
            if parent is None:
                break
            cur = parent
        return cur

    def _acquire(self, u: Unit) -> Unit | None:
        """锁定最近敌人；目标存活期间不换目标，避免来回抖动。

        新目标只在“已落格（非 transit）”的敌人里挑选：滑行中的单位位置
        尚未到达其逻辑格，瞄准它会带来画面错位。
        """
        current = self.by_uid.get(u.target_uid) if u.target_uid else None
        if current is not None and current.alive:
            return current

        best: list[Unit] = []
        best_d = float("inf")
        for o in self.units:
            if not o.alive or o.team == u.team or o.transit:
                continue
            d = float(grid.hex_distance(u.cell, o.cell))
            if d < best_d - 1e-6:
                best, best_d = [o], d
            elif abs(d - best_d) <= 1e-6:
                best.append(o)
        # 全部敌人都在滑行（尚未落格）时本 tick 无可选目标，原地等待
        if not best:
            u.target_uid = None
            return None
        # 多个敌人等距时随机选取，避免固定顺序带来的方向性偏差
        chosen = best[0] if len(best) <= 1 else self.rng.choice(best)
        u.target_uid = chosen.uid if chosen else None
        return chosen

    def _attack(self, u: Unit, target: Unit) -> None:
        # 坐标一并写入事件，渲染层据此定位突进/弹道/飘字
        self._emit(
            EV_ATTACK,
            name=u.name,
            team=u.team,
            uid=u.uid,
            target=target.name,
            sx=round(u.x, 3),
            sy=round(u.y, 3),
            tx=round(target.x, 3),
            ty=round(target.y, 3),
        )

        raw = u.ad
        if u.three_t > 0:  # 三相之力：施法后普攻强化
            raw *= 1.0 + ON_CAST_AD
        crit = self.rng.random() < u.crit_chance
        if crit:
            # 无尽之刃：暴击伤害提高（叠加到倍率上）
            mult = CRIT_MULTIPLIER + (CRIT_DMG_BONUS if "crit_damage" in u.effects else 0.0)
            raw *= mult
        dealt = self._deal_damage(u, target, raw, "physical", crit=crit)

        u.mana = min(u.max_mana, u.mana + MANA_PER_ATTACK)

        # 后续触发类特效只在攻击者仍存活时结算（可能已被荆棘反弹致死）
        if u.alive:
            # 饮血剑：普攻吸血（吸血量受目标/自己身上的重伤削减）
            if dealt > 0 and "lifesteal" in u.effects:
                self._heal(u, dealt * LIFESTEAL_PCT)
            # 日炎斗篷：命中使目标持续燃烧（秒伤 = 佩戴者攻击力 * 15%）
            if target.alive and "burn" in u.effects:
                target.burn_t = BURN_DUR
                target.burn_dps = max(target.burn_dps, u.ad * BURN_AD_PCT)
                target.burn_src = u.uid
            # 分裂弓：追加攻击射程内最近的另一个敌人
            if "multi_shot" in u.effects:
                second = self._pick_split_target(u, target)
                if second is not None:
                    self._deal_damage(u, second, raw * MULTI_SHOT_PCT, "physical")
            # 巨型九头蛇：对目标邻格的敌人溅射
            if "aoe_cleave" in u.effects:
                for nb in self._cleave_targets(target):
                    self._deal_damage(u, nb, raw * CLEAVE_PCT, "physical")
            # 羊刀：每次命中叠加攻速
            if "ramping_as" in u.effects:
                u.as_stack = min(RAMP_CAP, u.as_stack + RAMP_STEP)

        # 目标已被这次普攻打掉时保留法力，下一 tick 换目标再放技能
        if u.alive and u.mana >= u.max_mana and target.alive:
            self._cast(u, target)

    def _cast(self, u: Unit, target: Unit) -> None:
        ab = u.ability
        u.mana = 0.0
        power = ability_power(u)
        # 灭世者的死亡之帽：法强按比例提高（作用于本次技能威力，含大天使叠层）
        if "ap_amp" in u.effects:
            power *= 1.0 + AP_AMP_PCT

        # 珠光护手：技能可暴击（仅伤害类技能；全场一次掷骰决定本次技能是否暴击）
        crit = False
        if ab.type in ("nuke", "aoe") and "ability_crit" in u.effects:
            if self.rng.random() < u.crit_chance:
                power *= CRIT_MULTIPLIER
                crit = True

        if ab.type == "nuke":
            self._emit(
                EV_CAST,
                name=u.name,
                team=u.team,
                uid=u.uid,
                ability=ab.name,
                target=target.name,
                tx=round(target.x, 3),
                ty=round(target.y, 3),
            )
            dealt = self._deal_damage(u, target, power, "magic", crit=crit)
            self._spell_vamp(u, dealt)

        elif ab.type == "aoe":
            hits = [
                o
                for o in self.units
                if o.alive
                and o.team != u.team
                and grid.hex_distance(o.cell, target.cell) <= ab.radius
            ]
            self._emit(
                EV_CAST,
                name=u.name,
                team=u.team,
                uid=u.uid,
                ability=ab.name,
                target=target.name,
                hits=len(hits),
                tx=round(target.x, 3),
                ty=round(target.y, 3),
            )
            total = 0.0
            for o in hits:
                total += self._deal_damage(u, o, power, "magic", crit=crit)
            self._spell_vamp(u, total)

        elif ab.type == "heal":
            allies = self.alive_units(u.team)
            if allies:
                ally = min(allies, key=lambda a: a.hp_ratio)
                healed = self._heal(ally, min(power, ally.max_hp - ally.hp))
                self._emit(
                    EV_HEAL,
                    name=u.name,
                    team=u.team,
                    uid=u.uid,
                    ability=ab.name,
                    target=ally.name,
                    amount=healed,
                    hp_left=ally.hp,
                    tx=round(ally.x, 3),
                    ty=round(ally.y, 3),
                )

        # 施法联动装备：大天使之杖永久叠法强、三相之力开启普攻强化
        if "mana_ap" in u.effects:
            u.ap += MANA_AP_STEP
        if "on_cast_buff" in u.effects:
            u.three_t = ON_CAST_DUR

    def _deal_damage(
        self, source: Unit, target: Unit, raw: float, kind: str, crit: bool = False
    ) -> float:
        if not target.alive:
            return 0.0

        # 破甲弓：普攻无视目标部分护甲
        resist = target.armor if kind == "physical" else target.magic_resist
        if kind == "physical" and "armor_pen" in source.effects:
            resist *= 1.0 - ARMOR_PEN_PCT

        amount = mitigate(raw * (1.0 + source.damage_amp), resist)

        # 龙牙：受到的魔法伤害降低
        if kind == "magic" and "magic_resist" in target.effects:
            amount *= 1.0 - MAGIC_RESIST_PCT
        # 巨人杀手：对高生命目标造成额外伤害
        if (
            "giant_slayer" in source.effects
            and target.max_hp >= source.max_hp * GIANT_SLAYER_RATIO
        ):
            amount *= 1.0 + GIANT_SLAYER_PCT
        # 莫雷洛秘典：命中给目标挂重伤（削减其后续治疗/吸血）
        if "grievous_wounds" in source.effects:
            target.gw_t = GW_DUR

        target.hp -= amount
        self._emit(
            EV_DAMAGE,
            source=source.name,
            target=target.name,
            team=source.team,
            kind=kind,
            amount=amount,
            crit=crit,
            hp_left=max(0.0, target.hp),
            tx=round(target.x, 3),
            ty=round(target.y, 3),
        )

        if target.hp <= 0.0:
            # 守护天使：首次阵亡复活并回复 50% 生命
            if "revive" in target.effects and not target.revived:
                target.revived = True
                target.hp = target.max_hp * REVIVE_HP_PCT
            else:
                target.hp = 0.0
                target.alive = False
                self._emit(EV_DEATH, name=target.name, team=target.team, uid=target.uid)
        else:
            target.mana = min(target.max_mana, target.mana + MANA_ON_TAKE_HIT)

        # 荆棘之甲/反甲：被普攻命中时向攻击者反弹已结算伤害的一部分（反弹为魔法伤害，不会再次触发）
        if kind == "physical" and "thorns" in target.effects and amount > 0 and source.alive:
            self._deal_damage(target, source, amount * THORNS_PCT, "magic")
        return amount

    def _spell_vamp(self, u: Unit, dealt: float) -> None:
        """海克斯科技枪刃：技能伤害吸血（科技枪与饮血剑从此可区分）。"""
        if dealt > 0 and "spell_vamp" in u.effects and u.alive:
            self._heal(u, dealt * SPELL_VAMP_PCT)

    def _heal(self, u: Unit, amount: float) -> float:
        """治疗统一入口：重伤（莫雷洛）会削减目标的治疗与吸血。"""
        if amount <= 0.0 or not u.alive:
            return 0.0
        if u.gw_t > 0:
            amount *= 1.0 - GW_REDUCE
        healed = min(amount, max(0.0, u.max_hp - u.hp))
        if healed > 0.0:
            u.hp += healed
        return healed

    def _apply_status(self) -> None:
        """每秒一次的持续特效结算：燃烧 DoT / 回血 / 计时衰减。"""
        if self.tick % TICK_RATE != 0:
            return
        for u in self.units:
            if not u.alive:
                continue
            if u.burn_t > 0 and u.burn_dps > 0:
                src = self.by_uid.get(u.burn_src)
                if src is not None:
                    self._deal_damage(src, u, u.burn_dps, "magic")
                u.burn_t -= 1.0
            if u.gw_t > 0:
                u.gw_t = max(0.0, u.gw_t - 1.0)
            if u.three_t > 0:
                u.three_t = max(0.0, u.three_t - 1.0)
            # 狂徒铠甲：每秒回复少量生命
            if "regen" in u.effects:
                self._heal(u, u.max_hp * REGEN_PCT)

    def _slowed_by_aura(self, u: Unit) -> bool:
        """冰心减速光环：佩戴者周围（SLOW_AURA_RANGE 格内）的敌人攻速降低。"""
        for o in self.units:
            if (
                o.alive
                and o.team != u.team
                and "slow_aura" in o.effects
                and grid.hex_distance(u.cell, o.cell) <= SLOW_AURA_RANGE
            ):
                return True
        return False

    def _pick_split_target(self, u: Unit, main: Unit) -> Unit | None:
        """分裂弓的副目标：射程内最近、且与主目标不同的存活敌人。"""
        best: Unit | None = None
        best_d = float("inf")
        for o in self.units:
            if (
                o.alive
                and o.team != u.team
                and o is not main
                and not o.transit
                and grid.hex_distance(u.cell, o.cell) <= u.attack_range
            ):
                d = grid.hex_distance(u.cell, o.cell)
                if d < best_d:
                    best, best_d = o, d
        return best

    def _cleave_targets(self, target: Unit) -> list[Unit]:
        """九头蛇溅射：目标邻格（六边形距离 1）的其它敌人（= 目标同阵营、非目标自身）。

        注意：不能选 o.team != target.team —— 那会把攻击者（近战贴脸时）也算进去，
        造成“溅射打到自己”。溅射目标是“目标身旁扎堆的敌阵”。
        """
        return [
            o
            for o in self.units
            if o.alive
            and o.team == target.team
            and o is not target
            and grid.hex_distance(o.cell, target.cell) <= 1
        ]

    def _teams_alive(self) -> set[str]:
        """还有存活单位的队伍集合。"""
        return {u.team for u in self.units if u.alive}

    def _check_end(self) -> None:
        teams = self._teams_alive()
        if len(teams) > 1:
            if self.tick >= self.max_ticks:
                self._finish(self._by_hp(), timeout=True)
            return
        # 只剩一支队伍（或全灭）
        winner = next(iter(teams)) if len(teams) == 1 else None
        self._finish(winner)

    def _by_hp(self) -> str | None:
        """超时时按剩余血量比例判定。"""
        scores: dict[str, float] = {}
        for u in self.alive_units():
            scores[u.team] = scores.get(u.team, 0.0) + u.hp_ratio
        if not scores:
            return None
        best = max(scores.values())
        tops = [t for t, v in scores.items() if abs(v - best) < 1e-6]
        if len(tops) != 1:
            return None
        return tops[0]

    def _finish(self, winner: str | None, timeout: bool = False) -> None:
        self.finished = True
        text = {"blue": "蓝方胜利", "red": "红方胜利", None: "平局"}.get(
            winner, f"{winner} 胜利" if winner else "平局"
        )
        if timeout:
            text += "（超时判定）"
        self._emit(EV_END, winner=winner, result=text, ticks=self.tick)
        # 队伍键补全（败方记 0），避免消费方因“全灭方缺键”报 KeyError
        teams = {u.team for u in self.units}
        survivors: dict[str, int] = {t: 0 for t in teams}
        hp_left: dict[str, float] = {t: 0.0 for t in teams}
        for t in self._teams_alive():
            survivors[t] = len(self.alive_units(t))
            hp_left[t] = sum(u.hp for u in self.alive_units(t))
        self.result = CombatResult(
            winner=winner,
            ticks=self.tick,
            survivors=survivors,
            hp_left=hp_left,
            timeout=timeout,
        )
