"""数据模型：棋子模板与对局中的棋子实例。"""

from __future__ import annotations

from dataclasses import dataclass, field

# 星级倍率：1 星为基准，每升一星属性约翻倍
STAR_MULTIPLIER: dict[int, float] = {1: 1.0, 2: 1.8, 3: 3.24}
# 攻速星级档位：攻速随星级轻成长（低攻速单位升星手感不受大影响）
AS_STAR_MULTIPLIER: dict[int, float] = {1: 1.0, 2: 1.1, 3: 1.25}

CRIT_MULTIPLIER = 1.5

# 全局攻速上限（次/秒）：含装备/羁绊/羊刀叠层在内的实际攻速不得超过它
AS_CAP = 5.0

MANA_PER_ATTACK = 10.0
MANA_ON_TAKE_HIT = 6.0


@dataclass(frozen=True)
class AbilityDef:
    """技能模板。M1 只做三种：单体爆发、范围伤害、治疗。"""

    type: str = "nuke"  # nuke | aoe | heal
    name: str = "重击"
    value: float = 0.0
    ratio: float = 0.0  # 法术强度加成系数
    radius: int = 1


@dataclass(frozen=True)
class UnitTemplate:
    """棋子模板，来自 data/units.json。"""

    id: str
    name: str
    cost: int
    traits: tuple[str, ...]
    hp: float
    ad: float
    attack_speed: float
    attack_range: int
    armor: int
    magic_resist: int
    move_speed: float
    max_mana: float
    starting_mana: float = 0.0
    ap: float = 0.0  # 基础法强，法师系的技能伤害保底
    crit_chance: float = 0.05
    ability: AbilityDef = AbilityDef()
    slots: int = 1  # 上场占用的弈子栏位（人口），大型单位（远古巨龙）为 2
    trait_extra: dict = field(default_factory=dict)  # 羁绊计数合计贡献（缺省每羁绊 1），如 {"454": 2} 表示远古巨龙对峡谷野怪按 2 计


@dataclass
class Unit:
    """对局中的棋子实例。属性已包含星级、羁绊与装备加成。"""

    uid: int = 0
    tid: str = ""
    name: str = ""
    team: str = "blue"
    star: int = 1
    traits: tuple[str, ...] = ()

    max_hp: float = 0.0
    hp: float = 0.0
    ad: float = 0.0
    ap: float = 0.0
    armor: float = 0.0
    magic_resist: float = 0.0
    attack_speed: float = 0.0
    # 星级白板基础值（= 模板 × 星级档位，不含羁绊与装备加成）：
    # “特效吃基础”的装备（羊刀/三相/帽子）以此为基准，不与装备/羁绊加成互相放大。
    base_max_hp: float = 0.0
    base_ad: float = 0.0
    base_ap: float = 0.0
    base_attack_speed: float = 0.0
    attack_range: int = 1
    move_speed: float = 0.0
    max_mana: float = 0.0
    mana: float = 0.0
    crit_chance: float = 0.0
    damage_amp: float = 0.0
    lifesteal: float = 0.0
    ability: AbilityDef = AbilityDef()
    effects: frozenset = frozenset()  # 装备特殊效果集合
    # 装备清单（item_id 序列，可重复）：供详情展示与"按件数生效"的特效（如羊刀叠加）使用
    equip_ids: tuple[str, ...] = ()
    max_star: int = 1

    x: float = 0.0
    y: float = 0.0
    # 战斗格子化（需求3）：cell 是当前“占据/预定”的六边形格(col,row)；
    # transit 表示逻辑格已切到 cell、但画面位置还在按移速滑向 cell 中心。
    cell: tuple[int, int] = (0, 0)
    transit: bool = False

    alive: bool = True
    attack_timer: float = 0.0
    target_uid: int | None = None

    # 装备特效运行期状态（每场战斗由 Combat 读写，构建时保持默认）
    as_stack: float = 0.0  # 羊刀叠加攻速（相对基础攻速的加性百分比，不与攻速装备/羁绊互乘）
    three_t: float = 0.0   # 三相之力：施法后普攻强化剩余秒数
    burn_t: float = 0.0    # 燃烧剩余秒数
    burn_dps: float = 0.0  # 燃烧每秒伤害（由施加者写入）
    burn_src: int = 0      # 燃烧施加者 uid
    gw_t: float = 0.0      # 重伤剩余秒数，期间受治疗/吸血减半
    revived: bool = False  # 守护天使是否已消耗

    @property
    def pos(self) -> tuple[float, float]:
        return (self.x, self.y)

    @property
    def hp_ratio(self) -> float:
        return self.hp / self.max_hp if self.max_hp > 0 else 0.0


@dataclass
class CombatResult:
    winner: str | None  # blue | red | None(平局)
    ticks: int
    survivors: dict[str, int] = field(default_factory=dict)
    hp_left: dict[str, float] = field(default_factory=dict)
    timeout: bool = False
