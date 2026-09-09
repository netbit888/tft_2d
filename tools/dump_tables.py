# -*- coding: utf-8 -*-
"""数值总览生成器：把 data/*.json 的全部平衡数值导出为一张 Markdown 总览表。

用法：
    python tools/dump_tables.py            # 输出到项目根目录《数值总览.md》
    python tools/dump_tables.py 任意路径   # 指定输出文件路径

产物仅用于只读查阅；要改数值请直接编辑 data/*.json
（tools/simulate.py --check 可校验数据完整性）。散落在代码里的平衡常量
以“附录 C”形式一并列出并标注出处，改数值前先确认是改 json 还是改代码。
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from core.dataio import load_json  # noqa: E402
from core.game import Game  # noqa: E402
from core.items import DROP_CHANCE, FIRST_DROP_ROUND, MAX_ITEMS_PER_PIECE  # noqa: E402
from core.loader import load_traits, load_units  # noqa: E402
from core.models import (  # noqa: E402
    AS_STAR_MULTIPLIER,
    CRIT_MULTIPLIER,
    MANA_ON_TAKE_HIT,
    MANA_PER_ATTACK,
    STAR_MULTIPLIER,
)
from core.shop import REFRESH_COST  # noqa: E402

# ---------------------------------------------------------------------------
# 字段中文对照
# ---------------------------------------------------------------------------

_STAT_LABEL = {
    "hp_flat": "生命值",
    "hp_pct": "生命值",
    "ad_flat": "攻击力",
    "ad_pct": "攻击力",
    "ap_flat": "法强",
    "armor_flat": "护甲",
    "mr_flat": "魔抗",
    "attack_speed_pct": "攻速",
    "crit_flat": "暴击率",
    "mana_flat": "蓝量",
    "damage_amp": "伤害",
}

# 成装特殊效果 => 说明。具体生效数值见附录 C 的 core/combat.py 常量。
_EFFECT_NOTES = {
    "crit_damage": "暴击伤害提高",
    "armor_pen": "普攻无视目标部分护甲",
    "lifesteal": "普攻吸血",
    "magic_resist": "受到的魔法伤害降低",
    "aoe_cleave": "普攻对目标邻格溅射",
    "on_cast_buff": "施法后强化普攻（三相之力）",
    "ramping_as": "每次命中叠攻速（羊刀）",
    "multi_shot": "普攻追加攻击另一敌人（分裂弓）",
    "thorns": "被普攻命中反弹伤害",
    "ap_amp": "施法时法强按比例提高（帽子）",
    "grievous_wounds": "命中给目标挂重伤，削减治疗/吸血",
    "mana_ap": "每次施法永久叠法强（大天使）",
    "revive": "首次阵亡复活并回复生命（守护天使）",
    "burn": "命中使目标持续燃烧",
    "slow_aura": "光环减速周围敌人攻速（冰心）",
    "regen": "每秒回复最大生命（狂徒）",
    "spell_vamp": "技能伤害吸血（科技枪）",
    "giant_slayer": "对高生命目标额外增伤（巨人杀手）",
    "ability_crit": "技能可暴击（珠光护手）",
}

_AB_TYPE = {"nuke": "单体", "aoe": "范围", "heal": "治疗"}


def fmt_stat(key: str, value: float) -> str:
    """单个属性键值 -> 中文文本，如 ad_flat:10 -> "+10 攻击力"。
    _pct / crit_flat / damage_amp 在 json 里都是 0~1 的比例，按百分比显示。"""
    if key == "crit_flat" or key.endswith("_pct") or key == "damage_amp":
        return f"+{value * 100:g}% {_STAT_LABEL.get(key, key)}"
    return f"+{value:g} {_STAT_LABEL.get(key, key)}"


def fmt_mods(mods: dict) -> str:
    return "，".join(fmt_stat(k, v) for k, v in mods.items())


def trait_name(traits_data: dict, tid: str) -> str:
    d = traits_data.get(tid) or {}
    return d.get("name") or tid


def ability_cell(ab) -> str:
    """技能 -> "震荡波·范围 基础120，法强×0.6，半径1" 样式的单格文本。"""
    bits = []
    if ab.value:
        bits.append(f"基础{ab.value:g}")
    if ab.ratio:
        bits.append(f"法强×{ab.ratio:g}")
    if ab.radius and (ab.type == "aoe" or ab.radius > 1):
        bits.append(f"半径{ab.radius}")
    head = f"{ab.name}·{_AB_TYPE.get(ab.type, ab.type)}"
    return head + ("：" + "，".join(bits) if bits else "")


def md_table(headers: list[str], rows: list[list[str]]) -> str:
    """把列表渲染成 GFM 表格文本（单元格内管道符统一转义，防破坏列）。"""
    def esc(s: str) -> str:
        return s.replace("|", "\\|").replace("\n", " ")

    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("|" + "---|" * len(headers))
    for row in rows:
        assert len(row) == len(headers), (headers, row)
        lines.append("| " + " | ".join(esc(c) for c in row) + " |")
    return "\n".join(lines) + "\n"


def _num(v: float) -> str:
    return f"{v:g}"


# ---------------------------------------------------------------------------
# 各章节
# ---------------------------------------------------------------------------


def section_units(traits_data: dict) -> str:
    templates = load_units()  # dict[str, UnitTemplate]，按 data 顺序
    by_cost: dict[int, list] = {}
    for tpl in templates.values():
        by_cost.setdefault(tpl.cost, []).append(tpl)

    headers = [
        "id", "名称", "羁绊", "生命", "攻击", "攻速", "射程",
        "护甲", "魔抗", "移速", "蓝量", "技能（伤害类型）",
    ]
    out = []
    total = 0
    for cost in sorted(by_cost):
        group = by_cost[cost]
        out.append(f"\n### {cost} 费棋子（{len(group)} 个）\n")
        rows = []
        for t in group:
            traits = "、".join(trait_name(traits_data, x) for x in t.traits)
            rows.append([
                t.id, t.name, traits,
                _num(t.hp), _num(t.ad), f"{t.attack_speed:.2f}", str(t.attack_range),
                str(t.armor), str(t.magic_resist), _num(t.move_speed), _num(t.max_mana),
                ability_cell(t.ability),
            ])
        out.append(md_table(headers, rows))
        total += len(group)

    note = (
        "\n> 上表为 1 星、无装备、无羁绊的裸值。生命/攻击随星级成长"
        f"（×{STAR_MULTIPLIER}），攻速按星级档位轻成长"
        f"（×{AS_STAR_MULTIPLIER}），护甲/魔抗不随星级成长。"
        "蓝量 = 满蓝所需值，满蓝自动放技能；技能基础值即无法强时的威力。\n"
    )
    return f"\n## 一、棋子\n\n全场棋子 {total} 个。\n" + "\n".join(out) + note


def _trait_cell(data: dict) -> str:
    """羁绊展示文案：旧式自设(有 tiers/mods)给加成文本，官方同步的给描述+未实装标注。"""
    parts = []
    if data.get("tiers"):
        for tier in data["tiers"]:
            parts.append(f"**{tier['count']} 人**：{fmt_mods(tier.get('mods', {}))}")
    return "；".join(parts)


def section_traits(traits_data: dict) -> str:
    templates = load_units()
    intro = (
        "\n## 二、羁绊（官方名称与归属已同步，效果未实装）\n"
        "\n> 棋子归属与羁绊名称同步官方赛季数据（生成：`tools/build_official_traits.py`，"
        "数据源见 `tools/fetch_official_traits.py`）。"
        "**官方同名羁绊的效果本作未实装**：战斗不提供任何属性加成，仅保留官方名称、"
        "种族/职业归属与人数档位，作为图鉴与运营参考；原自设羁绊（战士/护卫/法师/迅捷/"
        "刺客/骑士/猎手/统领）已全部移除。\n"
    )
    labels = {"race": "种族", "job": "职业"}
    order = ["race", "job"]
    extra_kind = [k for k in set(traits_data[k].get("kind", "custom")
                                 for k in traits_data) - set(order)]
    kind_seq = order + sorted(extra_kind)

    out = [intro]
    total = 0
    for kind in kind_seq:
        items = [(tid, d) for tid, d in traits_data.items() if d.get("kind", "custom") == kind]
        if not items:
            continue
        total += len(items)
        out.append(f"\n### {labels.get(kind, kind)}羁绊（{len(items)} 个）\n")
        headers = ["id", "名称", "人数档位", "描述", "状态", "携带棋子（按 json 顺序）"]
        rows = []
        for tid, data in items:
            members = [t.name for t in templates.values() if tid in t.traits]
            levels = "、".join(f"{x} 人" for x in data.get("levels", [])) or "—"
            effect = _trait_cell(data)
            desc = data.get("desc") or data.get("detail", "") or ""
            if effect:
                desc = f"{desc}（{effect}）" if desc else effect
            status = "已实装" if data.get("implemented") else "未实装"
            rows.append([
                tid, data.get("name", tid), levels, desc, status,
                f"{len(members)} 个：{'、'.join(members) if members else '—'}",
            ])
        out.append(md_table(headers, rows))
    if not kind_seq:
        out.append("（无）")
    return "".join(out)


def section_base_items() -> str:
    items = load_json("items.json")
    bases = items["base"]
    headers = ["id", "名称", "属性"]
    rows = [[iid, data["name"], fmt_mods(data.get("stats", {}))] for iid, data in bases.items()]
    return (
        "\n## 三、散件（基础装备）\n\n"
        "散件可直接装备（只有基础属性），也可以两两合成成装。\n"
        + md_table(headers, rows)
    )


def section_combine_items() -> str:
    items = load_json("items.json")
    combine = items["combine"]
    bases = items["base"]
    headers = ["id（配方）", "名称", "属性合计", "特殊效果"]
    rows = []
    for key, data in combine.items():
        a, b = key.split("+", 1)
        recipe = f"{bases[a]['name']} + {bases[b]['name']}"
        eff = data.get("effect", "none")
        note = _EFFECT_NOTES.get(eff, "")
        rows.append([f"`{key}`<br>{recipe}", data["name"], fmt_mods(data.get("stats", {})), note or "—"])
    return (
        "\n## 四、成装（合成装备）\n\n"
        "公式与顺序无关（`sword+bow` = `bow+sword`）。属性为两件散件相加后再给额外加成后的最终值，"
        "特殊效果的具体数值系数见附录 C（core/combat.py）。\n"
        + md_table(headers, rows)
    )


def section_shop_curve() -> str:
    level = load_json("level.json")
    pool = load_json("pool.json")
    levels = level["levels"]
    odds = level["odds"]
    upgrade_xp = level["upgrade_xp"]
    upgrade_cost = level["upgrade_cost"]

    # 累计经验：升到某级所需累计 = 之前各级 xp_needed 之和（本级 xp 用于升下一级）
    out = ["\n## 五、商店与经济曲线\n\n"]

    # 经验/人口
    headers = ["等级", "人口上限", "升至下一级所需经验", "只靠买经验约需金币", "累计已投入经验"]
    rows = []
    cum = 0
    for lv in sorted(levels, key=lambda x: x["level"]):
        need = lv["xp_needed"]
        cum += need
        buys = math.ceil(need / upgrade_xp) * upgrade_cost
        rows.append([str(lv["level"]), str(lv["board_cap"]), _num(need), str(buys), str(cum)])
    out.append("#### 5.1 人口与经验\n")
    out.append(
        "说明：每回合自动 +2 经验（见附录 C）；手动买经验每次花 "
        f"{upgrade_cost} 金得 {upgrade_xp} 经验，多买不找回。下表“只靠买经验约需金币”把本级经验折算成整数次购买。\n"
    )
    out.append(md_table(headers, rows))

    # 商店概率
    headers = ["等级", "1 费(%)", "2 费(%)", "3 费(%)", "4 费(%)", "5 费(%)"]
    rows = []
    for lv in sorted(levels, key=lambda x: x["level"]):
        arr = [str(x) for x in odds.get(str(lv["level"]), [])]
        while len(arr) < 5:
            arr.append("0")
        rows.append([str(lv["level"])] + arr)
    out.append("\n#### 5.2 商店刷新概率\n")
    out.append("刷新一次商店固定花 " + _num(REFRESH_COST) + " 金（见附录 C）。\n")
    out.append(md_table(headers, rows))

    # 卡池
    copies = pool["copies_by_cost"]
    headers = ["费用", "卡池总张数"]
    rows = [[c, str(copies[c])] for c in sorted(copies, key=int)]
    out.append("\n#### 5.3 公共卡池张数（8 人局共享）\n")
    out.append("所有玩家共用一个卡池，买走即减少，卖出/淘汰归还；3 星需要同一棋子 9 张。\n")
    out.append(md_table(headers, rows))
    return "".join(out)


def appendix_code_constants() -> str:
    """附录 C：散落在代码里的平衡常量（json 之外最常被调的部分）。"""
    lines = [
        "\n## 附录 C：代码内平衡常量（不在 json，改这里要动代码）\n",
        "> 这些数值不在 data/*.json，是代码写死的参数。下表给出当前值、含义与出处，方便定位。\n",
    ]
    headers = ["常量（文件:行号附近）", "当前值", "含义"]
    rows = [
        ["models.py: STAR_MULTIPLIER", str(STAR_MULTIPLIER), "生命/攻击的星级倍率：1/2/3 星"],
        ["models.py: AS_STAR_MULTIPLIER", str(AS_STAR_MULTIPLIER), "攻速星级档位：1/2/3 星"],
        ["models.py: CRIT_MULTIPLIER", _num(CRIT_MULTIPLIER), "暴击伤害倍率"],
        ["models.py: MANA_PER_ATTACK", _num(MANA_PER_ATTACK), "每次普攻回蓝"],
        ["models.py: MANA_ON_TAKE_HIT", _num(MANA_ON_TAKE_HIT), "每次被命中回蓝"],
        ["items.py: MAX_ITEMS_PER_PIECE", str(MAX_ITEMS_PER_PIECE), "单个棋子最多装备数"],
        ["items.py: DROP_CHANCE", _num(DROP_CHANCE), "每回合掉落装备概率（第 2 回合起）"],
        ["items.py: FIRST_DROP_ROUND", str(FIRST_DROP_ROUND), "最早可掉落装备的回合"],
        ["game.py: START_GOLD / ROUND_INCOME", f"{Game.START_GOLD} / {Game.ROUND_INCOME}", "开局金币 / 每回合固定收入"],
        ["game.py: BASE_DAMAGE / DAMAGE_PER_UNIT", f"{Game.BASE_DAMAGE} / {Game.DAMAGE_PER_UNIT}", "战败扣血：固定 + 对方存活数×每单位"],
        ["game.py: MAX_ROUND", str(Game.MAX_ROUND), "最大回合数"],
        ["game.py: NATURAL_XP", str(Game.NATURAL_XP), "每回合自动获得经验"],
        ["game.py: INTEREST_PER / MAX_INTEREST", f"{Game.INTEREST_PER} / {Game.MAX_INTEREST}", "每存 10 金 +1 利息，上限 5"],
        ["shop.py: REFRESH_COST", _num(REFRESH_COST), "刷新商店固定费用"],
        ["stats.py: mitigate()", "100/(100+抗性)", "护甲/魔抗减伤公式"],
        ["stats.py: ability_power()", "value + 法强×ratio", "技能威力公式"],
        ["combat.py: TICK_RATE", "20", "战斗模拟 20 tick/s，战斗上限 45 秒"],
    ]
    lines.append(md_table(headers, rows))

    # 装备特效数值参数
    headers = ["装备特效常量（combat.py 顶部）", "当前值", "含义"]
    effect_rows = [
        ("CRIT_DMG_BONUS", 0.25, "crit_damage 无尽：暴击 1.5→1.75"),
        ("ARMOR_PEN_PCT", 0.30, "破甲弓：无视 30% 护甲"),
        ("MAGIC_RESIST_PCT", 0.30, "龙牙：受到的魔法伤害 -30%"),
        ("LIFESTEAL_PCT", 0.25, "饮血：普攻吸血 25%"),
        ("SPELL_VAMP_PCT", 0.25, "科技枪：技能吸血 25%"),
        ("CLEAVE_PCT", 0.50, "九头蛇：溅射 50% 伤害"),
        ("THORNS_PCT", 0.20, "反甲/荆棘：反弹 20%"),
        ("MULTI_SHOT_PCT", 0.40, "分裂弓：副目标 40% 伤害"),
        ("GW_DUR / GW_REDUCE", "6.0 / 0.50", "重伤持续 6 秒，治疗/吸血 -50%"),
        ("BURN_DUR / BURN_AD_PCT", "3.0 / 0.15", "日炎：燃烧 3 秒，秒伤=攻击×15%"),
        ("REGEN_PCT", 0.02, "狂徒：每秒回最大生命 2%"),
        ("REVIVE_HP_PCT", 0.50, "守护天使：复活回 50% 血"),
        ("RAMP_STEP", "0.06", "羊刀：每次命中叠 +6% 攻速（加在基础攻速上，无叠层上限，实际攻速由 AS_CAP 封顶）"),
        ("ON_CAST_AD / ON_CAST_DUR", "0.20 / 6.0", "三相：施法后 6 秒普攻 +20%（吃佩戴者基础攻击）"),
        ("MANA_AP_STEP", 15.0, "大天使：每次施法永久 +15 法强"),
        ("GIANT_SLAYER_RATIO / GIANT_SLAYER_PCT", "1.5 / 0.25", "巨人杀手：目标生命≥自身 1.5 倍时增伤 25%"),
        ("AP_AMP_PCT", 0.35, "帽子：施法时仅基础法强 +35%（不吃羁绊/装备/大天使的法强）"),
        ("SLOW_AURA_RANGE / SLOW_AURA_REDUCE", "2 / 0.25", "冰心：半径 2 格敌人攻速 -25%"),
    ]
    eff_rows = []
    for name, val, desc in effect_rows:
        eff_rows.append([f"`{name}`", str(val), desc])
    lines.append("\n#### 装备特效数值（改平衡常来这调）\n")
    lines.append(md_table(headers, eff_rows))
    return "".join(lines)


def build_markdown() -> str:
    items = load_json("items.json")
    level = load_json("level.json")
    traits_data = load_traits()
    units = load_units()

    n_units = len(units)
    by_cost = {}
    for u in units.values():
        by_cost[u.cost] = by_cost.get(u.cost, 0) + 1
    cost_summary = "、".join(f"{c}费×{by_cost[c]}" for c in sorted(by_cost))

    header = [
        "# 数值总览\n",
        "> 由 `tools/dump_tables.py` 自动生成，**不要手改本文件**。",
        "> 修改数值请编辑 `data/*.json`（校验：`python tools/simulate.py --check`）；重新生成：`python tools/dump_tables.py`。\n",
        "数据快照：",
        f"- 棋子：{n_units} 个（{cost_summary}）",
        f"- 羁绊：{len(traits_data)} 个",
        f"- 装备：散件 {len(items['base'])} 件、成装 {len(items['combine'])} 件（金制拆卸器等特殊工具是代码常量，不在此列）",
        f"- 人口等级：{len(level['levels'])} 级",
    ]
    return "\n".join(header) + "\n" + section_units(traits_data) + section_traits(traits_data) \
        + section_base_items() + section_combine_items() + section_shop_curve() \
        + appendix_code_constants()


def main() -> None:
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "数值总览.md"
    out_path = out_path if out_path.is_absolute() else Path.cwd() / out_path
    content = build_markdown()
    out_path.write_text(content, encoding="utf-8")
    print(f"已生成：{out_path}")
    print(f"行数：{content.count(chr(10)) + 1}")


if __name__ == "__main__":
    main()
