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
                interval = 1.0 / max(u.attack_speed, 0.05)
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
        crit = self.rng.random() < u.crit_chance
        if crit:
            raw *= CRIT_MULTIPLIER
        self._deal_damage(u, target, raw, "physical", crit=crit)

        # 本次攻击已在决策阶段确定，即使攻击者本 tick 内阵亡也照常结算（可同归于尽）
        u.mana = min(u.max_mana, u.mana + MANA_PER_ATTACK)
        # 目标已被这次普攻打掉时保留法力，下一 tick 换目标再放技能
        if u.mana >= u.max_mana and target.alive:
            self._cast(u, target)

    def _cast(self, u: Unit, target: Unit) -> None:
        ab = u.ability
        u.mana = 0.0
        power = ability_power(u)

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
            self._deal_damage(u, target, power, "magic")

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
            for o in hits:
                self._deal_damage(u, o, power, "magic")

        elif ab.type == "heal":
            allies = self.alive_units(u.team)
            if not allies:
                return
            ally = min(allies, key=lambda a: a.hp_ratio)
            healed = min(power, ally.max_hp - ally.hp)
            ally.hp += healed
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

    def _deal_damage(
        self,         source: Unit, target: Unit, raw: float, kind: str, crit: bool = False
    ) -> float:
        if not target.alive:
            return 0.0
        resist = target.armor if kind == "physical" else target.magic_resist
        amount = mitigate(raw * (1.0 + source.damage_amp), resist)
        target.hp -= amount

        # 装备特效：吸血 / 法术吸血
        if source.lifesteal > 0 and source.alive:
            heal = amount * source.lifesteal
            heal = min(heal, source.max_hp - source.hp)
            if heal > 0:
                source.hp += heal

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
            target.hp = 0.0
            target.alive = False
            self._emit(EV_DEATH, name=target.name, team=target.team, uid=target.uid)
        else:
            target.mana = min(target.max_mana, target.mana + MANA_ON_TAKE_HIT)
        return amount

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
