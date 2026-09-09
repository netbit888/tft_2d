"""数值模型回归测试：

- 攻速随星级轻成长（AS_STAR_MULTIPLIER = 1.0 / 1.1 / 1.25），护甲/魔抗/法强不随星；
- compute_stats 输出星级白板基础值（base_*，不含羁绊与装备），供“特效吃基础”使用；
- 羊刀叠层 / 三相 / 帽子：加成只作用于佩戴者的星级白板基础值，
  不因装备、羁绊、大天使叠层等额外属性被放大。
"""

from __future__ import annotations

import pytest

from core import Combat, build_team, load_units
from core.combat import ON_CAST_AD, effective_attack_speed
from core.items import ItemInstance
from core.models import AS_CAP, AS_STAR_MULTIPLIER
from core.stats import compute_stats
from core.traits import TraitMods

DART = "s18_varus"  # 攻速 0.8 的 1 费远程
WISP = "s18_karma"  # 基础法强 15 的法师


def _stats(tid: str, star: int, mods: TraitMods | None = None, items: dict | None = None):
    return compute_stats(load_units()[tid], star, mods or TraitMods(), items)


def _magic_damage(c) -> list[float]:
    return [e.data["amount"] for e in c.events if e.data.get("kind") == "magic"]


def _physical_damage(c) -> list[float]:
    return [e.data["amount"] for e in c.events if e.data.get("kind") == "physical"]


# ---------- 攻速星级成长 ----------


def test_attack_speed_grows_with_star():
    """攻速按星级档位轻成长：1/2/3 星 = 基础 × 1.0/1.1/1.25。"""
    as0 = load_units()[DART].attack_speed  # 0.8
    for star in (1, 2, 3):
        panel = _stats(DART, star)["attack_speed"]
        assert panel == pytest.approx(as0 * AS_STAR_MULTIPLIER[star]), f"{star} 星攻速档位错误"


def test_hp_ad_grow_but_ap_armor_mr_not_with_star():
    """生命/攻击随星翻倍成长；法强/护甲/魔抗不受星级影响。"""
    for tid in (DART, WISP):
        tpl = load_units()[tid]
        base = _stats(tid, 1)
        three = _stats(tid, 3)
        assert three["max_hp"] == pytest.approx(base["max_hp"] * 3.24)
        assert three["ad"] == pytest.approx(base["ad"] * 3.24)
        assert three["ap"] == pytest.approx(base["ap"])
        assert three["armor"] == pytest.approx(base["armor"])
        assert three["magic_resist"] == pytest.approx(base["magic_resist"])


# ---------- 星级白板基础值（不含羁绊/装备） ----------


def test_base_stats_exclude_traits_and_items():
    """base_* = 模板 × 星级档位：羁绊百分比与装备加成都不进入基础值。"""
    s = _stats(
        DART,
        2,
        mods=TraitMods(attack_speed_pct=0.5, ad_pct=0.25, hp_pct=0.1),
        items={"attack_speed_pct": 0.3, "ad_flat": 10, "hp_flat": 150},
    )
    tpl = load_units()[DART]
    assert s["base_max_hp"] == pytest.approx(tpl.hp * 1.8)
    assert s["base_ad"] == pytest.approx(tpl.ad * 1.8)
    assert s["base_ap"] == pytest.approx(tpl.ap)
    assert s["base_attack_speed"] == pytest.approx(tpl.attack_speed * 1.1)
    # 面板则包含加成：% 乘基础、固定值相加
    assert s["max_hp"] == pytest.approx(s["base_max_hp"] * 1.1 + 150)
    assert s["ad"] == pytest.approx(s["base_ad"] * 1.25 + 10)
    assert s["attack_speed"] == pytest.approx(s["base_attack_speed"] * (1.0 + 0.5 + 0.3))


def test_build_team_writes_base_fields_into_unit():
    """建队时 Unit 上应带星级白板基础值（供战斗中特效读取）。"""
    u = build_team([{"id": WISP, "star": 3, "pos": [0, 0]}], "blue")[0]
    tpl = load_units()[WISP]
    assert u.base_max_hp == pytest.approx(tpl.hp * 3.24)
    assert u.base_ad == pytest.approx(tpl.ad * 3.24)
    assert u.base_ap == pytest.approx(tpl.ap)
    assert u.base_attack_speed == pytest.approx(tpl.attack_speed * 1.25)
    assert u.attack_speed == pytest.approx(u.base_attack_speed)  # 无装备/羁绊


# ---------- 羊刀：叠层加在基础攻速上 ----------


def test_ramping_as_stacks_on_base_attack_speed():
    """羊刀叠层 = 基础攻速 × 叠层百分比，与装备攻速%加性叠加，不互相乘。"""
    tpl = load_units()[DART]
    base_as = tpl.attack_speed * AS_STAR_MULTIPLIER[3]
    u = build_team(
        [{"id": DART, "star": 3, "pos": [0, 0], "equip": [ItemInstance("bow+bow")]}],
        "blue",
    )[0]
    # 3 星基础攻速 = 官方基础攻速 × 1.25；羊刀自带 +30% → 面板 ×1.3
    assert u.base_attack_speed == pytest.approx(base_as)
    assert u.attack_speed == pytest.approx(base_as * 1.3)
    u.as_stack = 0.30  # 相当于 5 次命中（每次 +6%）
    # 加性：面板 + 基础×0.30；若乘性则会是 (×1.3)×(×1.3)，更高
    assert effective_attack_speed(u) == pytest.approx(base_as * 1.6)


def test_ramping_as_respects_global_cap():
    """羊刀叠层再多也被全局攻速上限 AS_CAP 封顶。"""
    u = build_team(
        [{"id": DART, "star": 3, "pos": [0, 0], "equip": [ItemInstance("bow+bow")]}],
        "blue",
    )[0]
    u.as_stack = 99.0
    assert effective_attack_speed(u) == pytest.approx(AS_CAP)


# ---------- 三相之力：普攻强化吃基础攻击 ----------


def _single_duel(blue_pl: dict, red_pl: dict, mutate=None) -> tuple[object, object]:
    blue = build_team([blue_pl], "blue")
    red = build_team([red_pl], "red")
    if mutate is not None:
        mutate(blue, red)
    c = Combat(blue, red, seed=7)
    c.events.clear()
    return c, c.by_uid[1], c.by_uid[2]


def test_three_force_buff_scales_with_base_ad_only():
    """三相 +20% 只放大佩戴者基础攻击；装备提供的额外 AD 不参与放大。"""
    target_tpl = load_units()["s18_ornn"]
    stone = load_units()["s18_camille"]
    base_ad = stone.ad  # 佩戴者 1 星基础攻击（官方同步值）
    equip_ad_flat = 10  # 三相自带 +10 攻击

    def run(three_active: bool):
        c, atk, tgt = _single_duel(
            {"id": "s18_camille", "star": 1, "pos": [0, 0], "equip": [ItemInstance("sword+tear")]},
            {"id": "s18_ornn", "star": 1, "pos": [5, 5]},
            mutate=lambda b, r: (
                setattr(b[0], "crit_chance", 0.0),
                setattr(b[0], "three_t", 1.0 if three_active else 0.0),
            ),
        )
        c._attack(atk, tgt)
        assert len(_physical_damage(c)) == 1
        return c, _physical_damage(c)[0]

    # 面板攻击 = 基础 + 三相 10；强化增量 = 基础攻击 × 20%（不吃装备额外 AD）
    c, dmg_active = run(True)
    expected_raw = base_ad + equip_ad_flat + base_ad * ON_CAST_AD
    expected = expected_raw * 100.0 / (100.0 + target_tpl.armor)
    assert dmg_active == pytest.approx(expected)

    # 旧式“整面板 ×1.2”会更高：验证当前实现确实只吃基础攻击
    old_raw = (base_ad + equip_ad_flat) * (1.0 + ON_CAST_AD)
    old_dmg = old_raw * 100.0 / (100.0 + target_tpl.armor)
    assert old_dmg > expected + 1.0


# ---------- 帽子：只放大基础法强 ----------


def test_deathcap_only_amplifies_base_ap():
    """帽子施法增益只乘基础法强：装备给的 +20 法强不被帽子放大。"""
    # wisp：基础法强 15；帽子 ap_flat +20 → 面板法强 35
    c, atk, tgt = _single_duel(
        {"id": WISP, "star": 1, "pos": [0, 0], "equip": [ItemInstance("wand+wand")]},
        {"id": "s18_ornn", "star": 1, "pos": [5, 5]},
    )
    assert atk.ap == pytest.approx(15 + 20)
    c._cast(atk, tgt)
    magic = _magic_damage(c)
    assert magic, "应产生一次技能魔法伤害"

    # 新公式：15×1.35 + (35-15) = 40.25 有效法强
    ab = load_units()[WISP].ability
    eff_ap = 15 * 1.35 + (atk.ap - atk.base_ap)
    power = ab.value + eff_ap * ab.ratio
    expected = power * 100.0 / (100.0 + load_units()["s18_ornn"].magic_resist)
    assert magic[-1] == pytest.approx(expected)

    # 旧式“整面板 ×1.35”会明显更大：验证帽子没吃装备法强
    old_power = (ab.value + atk.ap * ab.ratio) * 1.35
    assert magic[-1] < old_power * 100.0 / (100.0 + load_units()["s18_ornn"].magic_resist) - 1.0


def test_deathcap_has_no_effect_without_base_ap():
    """基础法强为 0 的物理棋子戴帽子：没有额外法强增益，只吃到 ap_flat。"""
    rogue = load_units()["s18_xayah"]  # 无 ap 字段 → 基础法强 0
    assert rogue.ap == 0.0
    c, atk, tgt = _single_duel(
        {"id": "s18_xayah", "star": 1, "pos": [0, 0], "equip": [ItemInstance("wand+wand")]},
        {"id": "s18_ornn", "star": 1, "pos": [5, 5]},
    )
    assert atk.base_ap == 0.0 and atk.ap == pytest.approx(20.0)
    c._cast(atk, tgt)
    magic = _magic_damage(c)
    assert magic, "技能应能施放"
    # 无基础法强 → 帽子不放大任何东西：有效法强 = 装备 ap_flat 20
    ab = rogue.ability
    expected = ab.value + 20.0 * ab.ratio
    expected = expected * 100.0 / (100.0 + load_units()["s18_ornn"].magic_resist)
    assert magic[-1] == pytest.approx(expected)
