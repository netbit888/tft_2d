"""战斗模拟器：固定步长 tick 推进，产出事件日志。

设计要点：
- 与渲染完全解耦，可在无窗口环境跑完整场战斗；
- 固定 20 tick/s，与帧率无关，保证同种子结果可复现；
- 战斗过程写入事件流，渲染层只负责回放。

特效参数集中在本文件顶部，数值对齐官方 equip.js（金铲铲 mode18）的 desc/basicDesc。
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
from .items import item_effect
from .models import (
    AS_CAP,
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
# --- 旧关键字（神器/历史沿用）---
CRIT_DMG_BONUS = 0.25        # crit_damage：暴击伤害 +0.25
ARMOR_PEN_PCT = 0.30         # armor_pen：普攻无视目标 30% 护甲
MAGIC_RESIST_PCT = 0.30      # magic_resist：受到的魔法伤害 -30%
LIFESTEAL_PCT = 0.25         # lifesteal：普攻吸血比例
SPELL_VAMP_PCT = 0.25        # spell_vamp：技能吸血比例
CLEAVE_PCT = 0.50            # aoe_cleave：普攻对目标邻格溅射 50% 伤害
THORNS_PCT = 0.20            # thorns：被普攻命中时反弹已结算伤害的 20%
MULTI_SHOT_PCT = 0.40        # multi_shot：分裂弓副目标伤害比例
REGEN_PCT = 0.02             # regen：每秒回复最大生命 2%
REVIVE_HP_PCT = 0.50         # revive：复活时回复 50% 最大生命
ON_CAST_AD = 0.20            # on_cast_buff：三相施法后强化期内普攻 +20%
ON_CAST_DUR = 6.0            # 三相强化持续秒数
MANA_AP_STEP = 15.0          # mana_ap：大天使（旧）每次施法 +15 法强
AP_AMP_PCT = 0.35            # ap_amp：帽子（旧）施法时仅基础法强 +35%
SLOW_AURA_RANGE = 2          # slow_aura：冰心减速光环半径
SLOW_AURA_REDUCE = 0.25      # 光环内敌人攻速 -25%
STONEPLATE_PER = 10          # stoneplate：石画鬼石板甲，每被一个敌人锁定，护甲/魔抗各 +10

# --- 成装特效参数（对齐官方 equip.js）---
GW_REDUCE = 0.33             # 重伤：治疗/吸血 -33%
BURN_PCT = 0.01              # 灼烧：每秒 = 目标最大生命 1%（真实伤害）
SHRED_PCT = 0.30             # 护甲/魔抗击碎：抗性 -30%
OMNIVAMP_ALLY_PCT = 0.20     # 海克斯科技枪刃：为最低血友军治疗 = 造成伤害 20%
SHOJIN_MANA = 5.0            # 朔极之矛：每次普攻 +5 法力
NASHORS_MANA = 2.0           # 纳什之牙：每次普攻 +2 法力
NASHORS_MANA_CRIT = 4.0      # 纳什之牙：暴击额外 +4 法力
EON_HP_PCT = 0.40            # 夜之锋刃：40% 生命触发
EON_UNTAUNT = 1.0            # 不可选取持续（秒）
EON_HEAL_MISSING = 0.15      # 治疗 15% 已损失生命
BT_HP_PCT = 0.50             # 汲取剑：50% 生命触发护盾
BT_SHIELD_PCT = 0.30         # 护盾 = 30% 最大生命
BT_SHIELD_DUR = 5.0
STK_HP_PCT = 0.60            # 斯特拉克：60% 生命触发护盾
STK_SHIELD_PCT = 0.40        # 护盾 = 40% 最大生命
STK_SHIELD_DUR = 4.0
RB_BURN_DUR = 5.0            # 红霸符：灼烧/重伤 5 秒
MORELLO_BURN_DUR = 10.0      # 莫雷洛秘典：10 秒
SUNFIRE_BURN_DUR = 10.0      # 日炎斗篷：10 秒
SUNFIRE_INTERVAL = 2.0       # 日炎：每 2 秒灼烧 2 格内一名敌人
SUNFIRE_RANGE = 2
SV_REGEN_MISSING = 0.02      # 振奋盔甲：每秒回复 2% 已损失生命
DC_INTERVAL = 2.0            # 巨龙之爪：每 2 秒
DC_REGEN_PCT = 0.025         # 回复 2.5% 最大生命
BRAMBLE_REFLECT = 100.0      # 棘刺背心：被攻击命中对邻格造成 100 魔法伤害
BRAMBLE_CD = 2.0             # 冷却 2 秒
BRAMBLE_ATK_REDUCE = 0.05    # 使来自攻击的伤害 -5%
SH_BASE_DR = 0.05            # 坚定之心：+5% 减伤
SH_HIGH_DR = 0.15            # >50% 生命时 15% 减伤
SH_HIGH_HP = 0.50
CG_SHIELD_PCT = 0.25         # 冕卫：开局护盾 25% 最大生命
CG_SHIELD_DUR = 8.0
CG_AP_AFTER = 0.25           # 护盾到期 +25% 法术加成
PV_START_MANA = 20.0         # 圣盾使的誓约：开局 +20 法力
PV_HP_PCT = 0.40
PV_MANA = 15.0               # 40% 生命时 +15 法力
PV_SHIELD_PCT = 0.20         # 并获 20% 最大生命护盾
ARCH_INTERVAL = 5.0          # 大天使之杖：每 5 秒
ARCH_AP_PCT = 0.20           # +20% 法术加成
TITANS_STEP = 0.02           # 泰坦：每层 +2% AD / +2% AP
TITANS_MAX = 25
TITANS_FULL_AMP = 0.10       # 满层 +10% 伤害增幅
KRAKEN_STEP = 0.035          # 海妖之怒：每次攻击 +3.5% AD
KRAKEN_MAX = 15
KRAKEN_AS = 0.15             # 15 次攻击后 +15% 攻速
QS_AS_PER_SEC = 0.03         # 水银：每秒 +3% 攻速
QS_CC_IMMUNE = 18.0          # 开局 18 秒控制免疫
RAMP_PER_SEC = 0.07          # 鬼索：每秒 +7% 可叠攻速
LASH_STEP = 0.05             # 强袭者的链枷：暴击 +5% 增伤
LASH_MAX = 4
LASH_DUR = 5.0
BB_AMP = 0.10                # 蓝霸符：全来源 +10% AD / AP
HOJ_ADAP = 0.18              # 正义之手：+18% AD / AP（>50% 生命翻倍）
HOJ_VAMP = 0.15              # 正义之手：+15% 全能吸血（<50% 生命翻倍）
IONIC_RANGE = 2              # 离子火花：2 格内 30% 魔抗击碎
TWILIGHT_RANGE = 2           # 薄暮法袍：2 格内 30% 护甲削减
TWILIGHT_SELF_ARMOR = 15.0   # 开局 15 秒 +15 护甲/魔抗
TWILIGHT_DUR = 15.0
AH_MANA_PCT = 0.15           # 适应性头盔：从所有来源 +15% 法力
AH_TANK_ARMOR = 30.0         # 坦克/战士：+30 护甲/魔抗
AH_OTHER_AMP = 0.10          # 其它：+10% AD / AP
GIANT_SLAYER_RATIO = 1.5     # 巨人捕手：目标生命 ≥ 自身 1.5 倍
GIANT_SLAYER_PCT = 0.15      # 对抗坦克 +15% 增伤


def effective_attack_speed(u: Unit) -> float:
    """单位当前实际攻速（次/秒），封顶到全局上限 AS_CAP。

    叠层（羊刀/水银/海妖）与攻速装备/羁绊%在同一“基础攻速”上的加性加成：
    effective = 面板攻速 + 基础攻速 × 叠层。
    """
    return min(u.attack_speed + u.base_attack_speed * u.as_stack, AS_CAP)


def _is_melee(u: Unit) -> bool:
    """近战判定：用攻击距离近似“坦克/战士”角色定位（适应性头盔用）。"""
    return u.attack_range <= 1


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

        self._init_effects()

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

        for u in self.units:
            if u.alive and u.transit:
                self._glide(u)

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
                    continue
                u.attack_timer += DT
                interval = 1.0 / max(effective_attack_speed(u), 0.05)
                if self._slowed_by_aura(u):  # 冰心减速光环
                    interval /= 1.0 - SLOW_AURA_REDUCE
                if u.attack_timer >= interval:
                    u.attack_timer -= interval
                    attacks.append((u, target))
            else:
                dest = self._plan_step(u, target, occ)
                if dest is not None:
                    occ.pop(u.cell, None)
                    occ[dest] = u
                    moves.append((u, dest))

        # 动态属性刷新必须在攻击结算前（石像鬼集火双抗 / 各类叠层 / 光环）
        self._refresh_dynamic()

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

    # ---------- 初始化：一次性标记（开局护盾/法力/控制免疫/正义之手）----------

    def _init_effects(self) -> None:
        for u in self.units:
            u.efx.clear()
            u.efx["ad0"] = u.ad
            u.efx["ap0"] = u.ap
            u.efx["amp0"] = u.damage_amp
            u.efx["omni0"] = u.omnivamp
            if "crown_guard" in u.effects:  # 冕卫：开局护盾 25% 最大生命，8 秒
                self._grant_shield(u, u.max_hp * CG_SHIELD_PCT, CG_SHIELD_DUR)
            if "protectors_vow" in u.effects:  # 圣盾使的誓约：开局 +20 法力
                self._gain_mana(u, PV_START_MANA, mult=False)
            if "quicksilver" in u.effects:  # 水银：开局 18 秒控制免疫
                u.efx["cc_t"] = QS_CC_IMMUNE
            if "twilight_veil" in u.effects:  # 薄暮法袍：开局 15 秒自身 +15 双抗
                u.efx["tw_t"] = TWILIGHT_DUR
            if "hand_of_justice" in u.effects:  # 正义之手：每场随机二选一
                u.efx["hoj"] = "adap" if self.rng.random() < 0.5 else "vamp"

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
        u.cell = dest
        u.transit = True

    def _glide(self, u: Unit) -> None:
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
                EV_MOVE, name=u.name, team=u.team, uid=u.uid,
                x=round(cx, 2), y=round(cy, 2),
            )

    def _plan_step(
        self, u: Unit, target: Unit, occ: dict[tuple[int, int], Unit]
    ) -> tuple[int, int] | None:
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
        cur: tuple[int, int] = goal
        while prev[cur] != start:
            parent = prev[cur]
            if parent is None:
                break
            cur = parent
        return cur

    def _acquire(self, u: Unit) -> Unit | None:
        """锁定最近敌人；目标存活期间不换目标（不可选取单位不选）。"""
        current = self.by_uid.get(u.target_uid) if u.target_uid else None
        if current is not None and current.alive and current.untargetable_t <= 0:
            return current

        best: list[Unit] = []
        best_d = float("inf")
        for o in self.units:
            if not o.alive or o.team == u.team or o.transit or o.untargetable_t > 0:
                continue
            d = float(grid.hex_distance(u.cell, o.cell))
            if d < best_d - 1e-6:
                best, best_d = [o], d
            elif abs(d - best_d) <= 1e-6:
                best.append(o)
        if not best:
            u.target_uid = None
            return None
        chosen = best[0] if len(best) <= 1 else self.rng.choice(best)
        u.target_uid = chosen.uid if chosen else None
        return chosen

    # ---------- 动态属性刷新 ----------

    def _refresh_dynamic(self) -> None:
        """每 tick 攻击结算前重算动态属性：石像鬼集火双抗、各类 % 加成与减伤。"""
        for u in self.units:
            if not u.alive:
                continue
            e = u.efx

            # 护甲 / 魔抗
            armor, mr = u.base_armor, u.base_magic_resist
            if "stoneplate" in u.effects:
                n = sum(
                    1 for o in self.units
                    if o.alive and o.team != u.team and o.target_uid == u.uid
                )
                armor += STONEPLATE_PER * n
                mr += STONEPLATE_PER * n
            if "adaptive_helm" in u.effects and _is_melee(u):
                armor += AH_TANK_ARMOR
                mr += AH_TANK_ARMOR
            if "twilight_veil" in u.effects and e.get("tw_t", 0.0) > 0:
                armor += TWILIGHT_SELF_ARMOR
                mr += TWILIGHT_SELF_ARMOR
            u.armor, u.magic_resist = armor, mr

            # 物理 / 法术 % 加成（每 tick 从基准重算，不累加）
            ad_pct = ap_pct = 0.0
            if "blue_buff" in u.effects:
                ad_pct += BB_AMP
                ap_pct += BB_AMP
            if "titans_resolve" in u.effects:
                ad_pct += TITANS_STEP * e.get("titans", 0)
                ap_pct += TITANS_STEP * e.get("titans", 0)
            if "kraken_slayer" in u.effects:
                ad_pct += KRAKEN_STEP * e.get("kraken", 0)
            if "archangels_staff" in u.effects:
                ap_pct += ARCH_AP_PCT * e.get("arch", 0)
            if "crown_guard" in u.effects and e.get("crown_ap", False):
                ap_pct += CG_AP_AFTER
            if "adaptive_helm" in u.effects and not _is_melee(u):
                ad_pct += AH_OTHER_AMP
                ap_pct += AH_OTHER_AMP
            if "hand_of_justice" in u.effects and e.get("hoj") == "adap":
                b = HOJ_ADAP * (2.0 if u.hp_ratio > SH_HIGH_HP else 1.0)
                ad_pct += b
                ap_pct += b
            u.ad = e["ad0"] * (1.0 + ad_pct)
            u.ap = e["ap0"] * (1.0 + ap_pct)

            # 伤害增幅
            amp = e["amp0"]
            if "titans_resolve" in u.effects and e.get("titans_full", False):
                amp += TITANS_FULL_AMP
            if "chain_lash" in u.effects and e.get("lash", 0) > 0:
                amp += LASH_STEP * e["lash"]
            u.damage_amp = amp

            # 全能吸血
            omni = e["omni0"]
            if "hand_of_justice" in u.effects and e.get("hoj") == "vamp":
                omni += HOJ_VAMP * (2.0 if u.hp_ratio < SH_HIGH_HP else 1.0)
            u.omnivamp = omni

    # ---------- 攻击 ----------

    def _attack(self, u: Unit, target: Unit) -> None:
        self._emit(
            EV_ATTACK, name=u.name, team=u.team, uid=u.uid, target=target.name,
            sx=round(u.x, 3), sy=round(u.y, 3),
            tx=round(target.x, 3), ty=round(target.y, 3),
        )

        raw = u.ad
        if u.three_t > 0:  # 三相之力（神器）：施法后普攻强化
            raw += u.base_ad * ON_CAST_AD
        crit = self.rng.random() < u.crit_chance
        if crit:
            mult = CRIT_MULTIPLIER + (CRIT_DMG_BONUS if "crit_damage" in u.effects else 0.0)
            raw *= mult
        dealt = self._deal_damage(u, target, raw, "physical", crit=crit)

        # 法力：普攻基础 + 朔极之矛/纳什之牙附加
        bonus_mana = 0.0
        if "spear_of_shojin" in u.effects:
            bonus_mana += SHOJIN_MANA
        if "nashors_tooth" in u.effects:
            bonus_mana += NASHORS_MANA + (NASHORS_MANA_CRIT if crit else 0.0)
        self._gain_mana(u, MANA_PER_ATTACK + bonus_mana)

        if u.alive:
            # 饮血剑（旧关键字）：普攻吸血
            if dealt > 0 and "lifesteal" in u.effects:
                self._heal(u, dealt * LIFESTEAL_PCT)
            # 分裂弓（旧）
            if "multi_shot" in u.effects:
                second = self._pick_split_target(u, target)
                if second is not None:
                    self._deal_damage(u, second, raw * MULTI_SHOT_PCT, "physical")
            # 巨型九头蛇（神器）：邻格溅射
            if "aoe_cleave" in u.effects:
                for nb in self._cleave_targets(target):
                    self._deal_damage(u, nb, raw * CLEAVE_PCT, "physical")
            # 泰坦的坚决：攻击也叠层
            if "titans_resolve" in u.effects:
                self._stack_titans(u)
            # 海妖之怒：每次攻击 +3.5% AD，至多 15 次
            if "kraken_slayer" in u.effects:
                e = u.efx
                if e.get("kraken", 0) < KRAKEN_MAX:
                    e["kraken"] = e.get("kraken", 0) + 1
                    if e["kraken"] >= KRAKEN_MAX and not e.get("kraken_done"):
                        e["kraken_done"] = True
                        u.as_stack += KRAKEN_AS
            # 强袭者的链枷：暴击叠伤害增幅（5 秒，至多 4 层）
            if crit and "chain_lash" in u.effects:
                e = u.efx
                e["lash"] = min(LASH_MAX, e.get("lash", 0) + 1)
                e["lash_t"] = LASH_DUR

        if u.alive and u.mana >= u.max_mana and target.alive:
            self._cast(u, target)

    def _cast(self, u: Unit, target: Unit) -> None:
        ab = u.ability
        u.mana = 0.0
        power = ability_power(u)
        if "ap_amp" in u.effects:
            base = u.base_ap
            extra = max(0.0, u.ap - base)
            power = ab.value + (base * (1.0 + AP_AMP_PCT) + extra) * ab.ratio

        crit = False
        if ab.type in ("nuke", "aoe") and "ability_crit" in u.effects:
            if self.rng.random() < u.crit_chance:
                power *= CRIT_MULTIPLIER
                crit = True

        if ab.type == "nuke":
            self._emit(
                EV_CAST, name=u.name, team=u.team, uid=u.uid, ability=ab.name,
                target=target.name, tx=round(target.x, 3), ty=round(target.y, 3),
            )
            dealt = self._deal_damage(u, target, power, "magic", crit=crit)
            self._spell_vamp(u, dealt)
        elif ab.type == "aoe":
            hits = [
                o for o in self.units
                if o.alive and o.team != u.team
                and grid.hex_distance(o.cell, target.cell) <= ab.radius
            ]
            self._emit(
                EV_CAST, name=u.name, team=u.team, uid=u.uid, ability=ab.name,
                target=target.name, hits=len(hits),
                tx=round(target.x, 3), ty=round(target.y, 3),
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
                    EV_HEAL, name=u.name, team=u.team, uid=u.uid, ability=ab.name,
                    target=ally.name, tuid=ally.uid, amount=healed, hp_left=ally.hp,
                    tx=round(ally.x, 3), ty=round(ally.y, 3),
                )

        if "mana_ap" in u.effects:      # 大天使（旧关键字）
            u.ap += MANA_AP_STEP
        if "on_cast_buff" in u.effects:  # 三相之力（神器）
            u.three_t = ON_CAST_DUR

    # ---------- 伤害结算 ----------

    def _deal_damage(
        self, source: Unit, target: Unit, raw: float, kind: str, crit: bool = False
    ) -> float:
        if not target.alive or raw <= 0:
            return 0.0

        # 抗性（真实伤害无视抗性）
        if kind == "true":
            resist = 0.0
        else:
            resist = target.armor if kind == "physical" else target.magic_resist
            if kind == "physical" and target.armor_shred_t > 0:
                resist *= 1.0 - SHRED_PCT
            if kind == "magic" and target.mr_shred_t > 0:
                resist *= 1.0 - SHRED_PCT
            if kind == "physical" and "armor_pen" in source.effects:
                resist *= 1.0 - ARMOR_PEN_PCT

        amount = mitigate(raw * (1.0 + source.damage_amp), resist)

        # 伤害减免
        dr = target.dmg_reduce
        if "steadfast_heart" in target.effects:
            dr += SH_HIGH_DR if target.hp_ratio > SH_HIGH_HP else SH_BASE_DR
        if kind == "physical" and "bramble_vest" in target.effects:
            dr += BRAMBLE_ATK_REDUCE
        if dr > 0:
            amount *= max(0.0, 1.0 - dr)

        # 龙牙（旧关键字）：受到魔法伤害降低
        if kind == "magic" and "magic_resist" in target.effects:
            amount *= 1.0 - MAGIC_RESIST_PCT
        # 巨人捕手：对抗高生命目标额外增伤
        if (
            "giant_slayer" in source.effects
            and target.max_hp >= source.max_hp * GIANT_SLAYER_RATIO
        ):
            amount *= 1.0 + GIANT_SLAYER_PCT

        # 命中挂负面：灼烧 / 重伤（红霸符·莫雷洛秘典）/ 击碎（轻语·虚空之杖）
        if target.alive and amount > 0:
            if "red_buff" in source.effects:
                self._apply_burn(source, target, RB_BURN_DUR)
                target.gw_t = max(target.gw_t, RB_BURN_DUR)
            if "morellonomicon" in source.effects:
                self._apply_burn(source, target, MORELLO_BURN_DUR)
                target.gw_t = max(target.gw_t, MORELLO_BURN_DUR)
            if "last_whisper" in source.effects:
                target.armor_shred_t = max(target.armor_shred_t, 3.0)
            if "void_staff" in source.effects:
                target.mr_shred_t = max(target.mr_shred_t, 5.0)

        # 护盾先于生命吸收
        if target.shield > 0 and amount > 0:
            absorbed = min(target.shield, amount)
            target.shield -= absorbed
            amount -= absorbed

        target.hp -= amount
        self._emit(
            EV_DAMAGE, source=source.name, suid=source.uid, target=target.name,
            tuid=target.uid, team=source.team, kind=kind, amount=amount, crit=crit,
            hp_left=max(0.0, target.hp), tx=round(target.x, 3), ty=round(target.y, 3),
        )

        # 全能吸血（攻击+技能通用）；海克斯科技枪刃额外治疗最低血友军
        if amount > 0 and source.alive:
            if source.omnivamp > 0:
                self._heal(source, amount * source.omnivamp)
            if "hextech_gunblade" in source.effects:
                self._heal_lowest_ally(source, amount * OMNIVAMP_ALLY_PCT)

        if target.hp <= 0.0:
            if "revive" in target.effects and not target.revived:  # 守护天使
                target.revived = True
                target.hp = target.max_hp * REVIVE_HP_PCT
            else:
                target.hp = 0.0
                target.alive = False
                self._emit(EV_DEATH, name=target.name, team=target.team, uid=target.uid)
        else:
            self._gain_mana(target, MANA_ON_TAKE_HIT)

        # 反伤：棘刺背心（100 魔法伤害，2 秒 CD）/ 荆棘之甲（旧）
        if kind == "physical" and amount > 0 and source.alive and target.alive:
            if "bramble_vest" in target.effects and target.efx.get("bramble_cd", 0.0) <= 0:
                target.efx["bramble_cd"] = BRAMBLE_CD
                for nb in self._adjacent_enemies(target):
                    self._deal_damage(target, nb, BRAMBLE_REFLECT, "magic")
            if "thorns" in target.effects:
                self._deal_damage(target, source, amount * THORNS_PCT, "magic")

        # 受击触发：泰坦叠层 + 低血护盾/灵刃
        if target.alive and amount > 0:
            self._on_take_damage(target)
        return amount

    def _on_take_damage(self, u: Unit) -> None:
        if "titans_resolve" in u.effects:
            self._stack_titans(u)
        e = u.efx
        r = u.hp_ratio
        if "bloodthirster" in u.effects and r <= BT_HP_PCT and not e.get("bt_used"):
            e["bt_used"] = True
            self._grant_shield(u, u.max_hp * BT_SHIELD_PCT, BT_SHIELD_DUR)
        if "steraks_gage" in u.effects and r <= STK_HP_PCT and not e.get("stk_used"):
            e["stk_used"] = True
            self._grant_shield(u, u.max_hp * STK_SHIELD_PCT, STK_SHIELD_DUR)
        if "protectors_vow" in u.effects and r <= PV_HP_PCT and not e.get("pv_used"):
            e["pv_used"] = True
            self._gain_mana(u, PV_MANA, mult=False)
            self._grant_shield(u, u.max_hp * PV_SHIELD_PCT, 99.0)
        if "edge_of_night" in u.effects and r <= EON_HP_PCT and not e.get("eon_used"):
            e["eon_used"] = True
            u.untargetable_t = EON_UNTAUNT
            u.burn_t = u.gw_t = u.armor_shred_t = u.mr_shred_t = 0.0
            self._heal(u, (u.max_hp - u.hp) * EON_HEAL_MISSING)

    def _stack_titans(self, u: Unit) -> None:
        e = u.efx
        if e.get("titans", 0) < TITANS_MAX:
            e["titans"] = e.get("titans", 0) + 1
            if e["titans"] >= TITANS_MAX:
                e["titans_full"] = True

    # ---------- 辅助 ----------

    def _gain_mana(self, u: Unit, amount: float, mult: bool = True) -> None:
        """法力获取统一入口：适应性头盔从所有来源额外 +15% 法力。"""
        if amount <= 0:
            return
        if mult and "adaptive_helm" in u.effects:
            amount *= 1.0 + AH_MANA_PCT
        u.mana = min(u.max_mana, u.mana + amount)

    def _grant_shield(self, u: Unit, amount: float, dur: float) -> None:
        if amount <= 0 or not u.alive:
            return
        u.shield += amount
        u.shield_t = max(u.shield_t, dur)

    def _heal_lowest_ally(self, u: Unit, amount: float) -> None:
        allies = self.alive_units(u.team)
        if not allies:
            return
        ally = min(allies, key=lambda a: a.hp_ratio)
        self._heal(ally, amount)

    def _apply_burn(self, source: Unit, target: Unit, dur: float) -> None:
        target.burn_t = max(target.burn_t, dur)
        target.burn_dps = max(target.burn_dps, target.max_hp * BURN_PCT)
        target.burn_src = source.uid

    def _spell_vamp(self, u: Unit, dealt: float) -> None:
        if dealt > 0 and "spell_vamp" in u.effects and u.alive:
            self._heal(u, dealt * SPELL_VAMP_PCT)

    def _heal(self, u: Unit, amount: float) -> float:
        """治疗统一入口：重伤会削减目标的治疗与吸血。"""
        if amount <= 0.0 or not u.alive:
            return 0.0
        if u.gw_t > 0:
            amount *= 1.0 - GW_REDUCE
        healed = min(amount, max(0.0, u.max_hp - u.hp))
        if healed > 0.0:
            u.hp += healed
        return healed

    # ---------- 每秒持续结算 ----------

    def _apply_status(self) -> None:
        """每秒一次：灼烧 DoT / 回血 / 光环 / 计时衰减。"""
        if self.tick % TICK_RATE != 0:
            return
        for u in self.units:
            if not u.alive:
                continue
            e = u.efx
            # 灼烧（真实伤害，秒伤 = 目标最大生命 1%）
            if u.burn_t > 0 and u.burn_dps > 0:
                src = self.by_uid.get(u.burn_src)
                if src is not None:
                    self._deal_damage(src, u, u.burn_dps, "true")
                u.burn_t = max(0.0, u.burn_t - 1.0)
            if u.gw_t > 0:
                u.gw_t = max(0.0, u.gw_t - 1.0)
            if u.three_t > 0:
                u.three_t = max(0.0, u.three_t - 1.0)
            if u.untargetable_t > 0:
                u.untargetable_t = max(0.0, u.untargetable_t - 1.0)
            if u.armor_shred_t > 0:
                u.armor_shred_t = max(0.0, u.armor_shred_t - 1.0)
            if u.mr_shred_t > 0:
                u.mr_shred_t = max(0.0, u.mr_shred_t - 1.0)
            # 护盾到期
            if u.shield > 0 and u.shield_t >= 0:
                u.shield_t -= 1.0
                if u.shield_t <= 0:
                    u.shield = 0.0
                    u.shield_t = -1.0
                    if "crown_guard" in u.effects:  # 冕卫：护盾到期 +25% 法术加成
                        e["crown_ap"] = True
            # 每秒计时器
            if e.get("bramble_cd", 0.0) > 0:
                e["bramble_cd"] = max(0.0, e["bramble_cd"] - 1.0)
            if e.get("cc_t", 0.0) > 0:
                e["cc_t"] = max(0.0, e["cc_t"] - 1.0)
            if e.get("tw_t", 0.0) > 0:
                e["tw_t"] = max(0.0, e["tw_t"] - 1.0)
            if e.get("lash_t", 0.0) > 0:
                e["lash_t"] = max(0.0, e["lash_t"] - 1.0)
                if e["lash_t"] <= 0:
                    e["lash"] = 0
            # 回血类
            if "spirit_visage" in u.effects:  # 振奋盔甲：每秒回 2% 已损失生命
                self._heal(u, (u.max_hp - u.hp) * SV_REGEN_MISSING)
            if "dragons_claw" in u.effects:  # 巨龙之爪：每 2 秒回 2.5% 最大生命
                e["dc_t"] = e.get("dc_t", 0.0) + 1.0
                if e["dc_t"] >= DC_INTERVAL:
                    e["dc_t"] -= DC_INTERVAL
                    self._heal(u, u.max_hp * DC_REGEN_PCT)
            # 叠层类
            if "ramping_as" in u.effects:  # 鬼索：每秒 +7%（按件数）
                blades = sum(1 for iid in u.equip_ids if item_effect(iid) == "ramping_as")
                u.as_stack += RAMP_PER_SEC * max(1, blades)
            if "quicksilver" in u.effects:  # 水银：每秒 +3% 叠攻速
                u.as_stack += QS_AS_PER_SEC
            if "archangels_staff" in u.effects:  # 大天使：每 5 秒 +20% 法术加成
                e["arch_t"] = e.get("arch_t", 0.0) + 1.0
                if e["arch_t"] >= ARCH_INTERVAL:
                    e["arch_t"] -= ARCH_INTERVAL
                    e["arch"] = e.get("arch", 0) + 1
            if "sunfire_cape" in u.effects:  # 日炎：每 2 秒灼烧 2 格内一名敌人
                e["sf_t"] = e.get("sf_t", 0.0) + 1.0
                if e["sf_t"] >= SUNFIRE_INTERVAL:
                    e["sf_t"] -= SUNFIRE_INTERVAL
                    foes = [
                        o for o in self.units
                        if o.alive and o.team != u.team
                        and grid.hex_distance(o.cell, u.cell) <= SUNFIRE_RANGE
                    ]
                    if foes:
                        tgt = self.rng.choice(foes)
                        self._apply_burn(u, tgt, SUNFIRE_BURN_DUR)
                        tgt.gw_t = max(tgt.gw_t, SUNFIRE_BURN_DUR)

        # 光环类：离子火花（魔抗击碎）/ 薄暮法袍（护甲削减）
        self._apply_shred_auras()

    def _apply_shred_auras(self) -> None:
        for u in self.units:
            if not u.alive:
                continue
            for o in self.units:
                if not o.alive or o.team == u.team:
                    continue
                d = grid.hex_distance(o.cell, u.cell)
                if "ionic_spark" in u.effects and d <= IONIC_RANGE:
                    o.mr_shred_t = max(o.mr_shred_t, 1.0)
                if "twilight_veil" in u.effects and d <= TWILIGHT_RANGE:
                    o.armor_shred_t = max(o.armor_shred_t, 1.0)

    def _slowed_by_aura(self, u: Unit) -> bool:
        for o in self.units:
            if (
                o.alive and o.team != u.team and "slow_aura" in o.effects
                and grid.hex_distance(u.cell, o.cell) <= SLOW_AURA_RANGE
            ):
                return True
        return False

    def _pick_split_target(self, u: Unit, main: Unit) -> Unit | None:
        best: Unit | None = None
        best_d = float("inf")
        for o in self.units:
            if (
                o.alive and o.team != u.team and o is not main and not o.transit
                and grid.hex_distance(u.cell, o.cell) <= u.attack_range
            ):
                d = grid.hex_distance(u.cell, o.cell)
                if d < best_d:
                    best, best_d = o, d
        return best

    def _cleave_targets(self, target: Unit) -> list[Unit]:
        """目标邻格（六边形距离 1）的同阵营其它单位（不含目标自身）。"""
        return [
            o for o in self.units
            if o.alive and o.team == target.team and o is not target
            and grid.hex_distance(o.cell, target.cell) <= 1
        ]

    def _adjacent_enemies(self, u: Unit) -> list[Unit]:
        """u 邻格（六边形距离 1）的存活敌人（棘刺背心反伤用）。"""
        return [
            o for o in self.units
            if o.alive and o.team != u.team
            and grid.hex_distance(o.cell, u.cell) <= 1
        ]

    def _teams_alive(self) -> set[str]:
        return {u.team for u in self.units if u.alive}

    def _check_end(self) -> None:
        teams = self._teams_alive()
        if len(teams) > 1:
            if self.tick >= self.max_ticks:
                self._finish(self._by_hp(), timeout=True)
            return
        winner = next(iter(teams)) if len(teams) == 1 else None
        self._finish(winner)

    def _by_hp(self) -> str | None:
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
        teams = {u.team for u in self.units}
        survivors: dict[str, int] = {t: 0 for t in teams}
        hp_left: dict[str, float] = {t: 0.0 for t in teams}
        for t in self._teams_alive():
            survivors[t] = len(self.alive_units(t))
            hp_left[t] = sum(u.hp for u in self.alive_units(t))
        self.result = CombatResult(
            winner=winner, ticks=self.tick, survivors=survivors,
            hp_left=hp_left, timeout=timeout,
        )
