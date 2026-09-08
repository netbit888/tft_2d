"""界面主题：缩放、颜色、布局常量。

所有像素尺寸都从 1280x800 的设计稿乘 S（缩放因子）派生，
改分辨率只需要 set_scale(2)（-> 2560x1600），绘制逻辑不用碰。

硬编码魔法数字一律不要写进 render/ 的其他文件，需要新常量就加进 _layout()。
"""

from __future__ import annotations

DESIGN_W, DESIGN_H = 1280, 800
MIN_SCALE, MAX_SCALE = 1, 2

# set_scale() 之后才有意义，这里先给个初值，避免静态检查报未定义
S = 1
WINDOW_W, WINDOW_H = DESIGN_W, DESIGN_H
FPS = 60


def mix(a, b, t: float):
    """两个颜色按 t 插值。"""
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def shade(color, t: float):
    """t<1 变暗，t>1 提亮。"""
    return tuple(max(0, min(255, int(c * t))) for c in color)


# ---------- 稀有度（金铲铲风格：按费用分档） ----------

RARITY = {
    1: {"name": "普通", "edge": (154, 160, 176), "fill": (36, 39, 48), "glow": (206, 212, 226)},
    2: {"name": "稀有", "edge": (74, 180, 112), "fill": (28, 46, 38), "glow": (128, 226, 158)},
    3: {"name": "史诗", "edge": (76, 148, 240), "fill": (28, 40, 64), "glow": (128, 190, 255)},
    4: {"name": "大师", "edge": (180, 112, 240), "fill": (42, 30, 62), "glow": (216, 160, 255)},
    5: {"name": "传说", "edge": (244, 194, 86), "fill": (58, 46, 24), "glow": (255, 226, 148)},
}
RARITY_FALLBACK = RARITY[1]

# 星级描边：2 星银，3 星金
STAR_RING = {1: None, 2: (198, 206, 218), 3: (250, 212, 112)}


def rarity(cost: int) -> dict:
    return RARITY.get(int(cost), RARITY_FALLBACK)


def _layout(s: int) -> dict:
    """按缩放因子生成全部尺寸常量。"""
    win_w, win_h = DESIGN_W * s, DESIGN_H * s

    top_h = 64 * s
    board_area_h = 470 * s
    side_w = 268 * s

    board_cols, board_rows = 7, 4
    cell = 92 * s
    board_w = board_cols * cell
    board_h = board_rows * cell
    board_x = side_w + (win_w - side_w - board_w) // 2
    board_y = top_h + (board_area_h - board_h) // 2

    bench_slots = 8
    bench_cell = 84 * s
    bench_gap = 12 * s
    bench_w = bench_slots * bench_cell + (bench_slots - 1) * bench_gap
    bench_x = (win_w - bench_w) // 2
    bench_y = top_h + board_area_h + 8 * s

    shop_slots = 5
    shop_card_w = 160 * s
    shop_card_h = 112 * s
    shop_gap = 12 * s
    shop_w = shop_slots * shop_card_w + (shop_slots - 1) * shop_gap
    shop_h = 148 * s
    shop_y = win_h - shop_h + 12 * s
    shop_x = side_w + 20 * s  # 商店左对齐，右侧留给装备栏/按钮

    pad = 18 * s

    # ---------- 右侧区域（从上到下：战况面板 → 装备栏 → 商店旁按钮） ----------
    roster_w = 200 * s
    roster_x = win_w - roster_w - 12 * s
    roster_y = top_h + 12 * s
    roster_row_h = 30 * s

    # 装备栏：3 列 x 4 行网格，放在战况面板下方
    item_cols, item_rows = 3, 4
    item_cell = 40 * s
    item_gap = 8 * s
    item_w = item_cols * item_cell + (item_cols - 1) * item_gap
    item_h = item_rows * item_cell + (item_rows - 1) * item_gap
    item_x = win_w - item_w - 12 * s
    item_y = roster_y + roster_row_h * 9 + 24 * s  # 战况面板最多 8 行 + 标题

    # ---------- 顶栏三段式 ----------
    # 左：回合 + 等级 + 经验
    round_x, round_y = pad, 2 * s
    level_x, level_y = pad, 12 * s
    xp_bar_x, xp_bar_y = 70 * s, 27 * s
    xp_bar_w, xp_bar_h = 90 * s, 9 * s
    xp_text_x, xp_text_y = 166 * s, 23 * s
    # 中：刷新概率
    odds_x = 330 * s
    odds_y = 24 * s
    odds_gap = 116 * s
    odds_box = 18 * s
    # 右：金币 + 利息
    gold_x = win_w - 190 * s
    gold_y = 4 * s
    interest_x = win_w - 190 * s
    interest_y = 42 * s

    # ---------- 左下角操作区（购买经验 / 刷新） ----------
    op_x = 14 * s
    op_w = 120 * s
    op_h = 38 * s
    op_gap = 10 * s
    op_refresh_y = 536 * s
    op_xp_y = 536 * s + op_h + op_gap

    # ---------- 右下角（锁定 / 开战） ----------
    side_btn_w = 110 * s
    lock_x = win_w - side_btn_w - 12 * s
    lock_y = shop_y
    lock_h = 38 * s
    fight_x = win_w - side_btn_w - 12 * s
    fight_y = shop_y + shop_card_h - 52 * s
    fight_h = 52 * s

    # ---------- HP 血条（备战席上方一行） ----------
    hp_bar_y = bench_y - 30 * s
    hp_bar_w = 150 * s
    hp_bar_h = 14 * s
    hp1_x = 300 * s
    hp2_x = 620 * s
    pop_x = 520 * s

    return {
        # ---------- 窗口 ----------
        "S": s,
        "WINDOW_W": win_w,
        "WINDOW_H": win_h,
        "FPS": 60,
        # ---------- 颜色 ----------
        "BG": (16, 18, 24),
        "BG_SOFT": (22, 25, 33),
        "PANEL": (30, 33, 42),
        "PANEL_LIGHT": (42, 46, 58),
        "BORDER": (62, 68, 84),
        "BORDER_SOFT": (48, 53, 66),
        "TEXT": (233, 236, 243),
        "TEXT_DIM": (150, 157, 174),
        "ACCENT": (86, 158, 255),
        "GOLD": (244, 196, 80),
        "HP_GREEN": (76, 200, 110),
        "HP_YELLOW": (232, 192, 72),
        "HP_RED": (226, 84, 84),
        "MANA_BLUE": (86, 158, 240),
        "TEAM_COLORS": {"blue": (78, 138, 236), "red": (230, 92, 92)},
        "GRID_A": (46, 50, 63),
        "GRID_B": (38, 42, 53),
        "SELF_ROW_TINT": (54, 68, 98),
        "ENEMY_ROW_TINT": (78, 52, 60),
        "TRAIT_COLORS": {
            "warrior": (216, 98, 78),
            "guardian": (86, 142, 214),
            "mage": (158, 112, 222),
            "swift": (86, 192, 142),
        },
        "TRAIT_FALLBACK": (124, 132, 148),
        # ---------- 字体 ----------
        "FS_TITLE": int(26 * s),
        "FS_NORMAL": int(20 * s),
        "FS_SMALL": int(16 * s),
        "FS_TINY": int(13 * s),
        "FS_MICRO": int(11 * s),
        "FS_PIECE": int(18 * s),
        # ---------- 棋盘 ----------
        "BOARD_COLS": board_cols,
        "BOARD_ROWS": board_rows,
        "CELL": cell,
        "BOARD_W": board_w,
        "BOARD_H": board_h,
        "BOARD_X": board_x,
        "BOARD_Y": board_y,
        "TILE_INSET": 2 * s,  # 菱形地砖之间留的缝
        "PIECE_RATIO": 0.74,  # 头像直径 / 格子边长
        # ---------- 备战席 ----------
        "BENCH_SLOTS": bench_slots,
        "BENCH_CELL": bench_cell,
        "BENCH_GAP": bench_gap,
        "BENCH_W": bench_w,
        "BENCH_X": bench_x,
        "BENCH_Y": bench_y,
        # ---------- 商店 ----------
        "SHOP_SLOTS": shop_slots,
        "SHOP_CARD_W": shop_card_w,
        "SHOP_CARD_H": shop_card_h,
        "SHOP_GAP": shop_gap,
        "SHOP_W": shop_w,
        "SHOP_X": shop_x,
        "SHOP_Y": shop_y,
        "SHOP_H": shop_h,
        # ---------- 顶栏（三段式） ----------
        "TOP_H": top_h,
        "PAD": pad,
        # 左：等级 + 经验
        "ROUND_X": round_x,
        "ROUND_Y": round_y,
        "LEVEL_X": level_x,
        "LEVEL_Y": level_y,
        "XP_BAR_X": xp_bar_x,
        "XP_BAR_Y": xp_bar_y,
        "XP_BAR_W": xp_bar_w,
        "XP_BAR_H": xp_bar_h,
        "XP_TEXT_X": xp_text_x,
        "XP_TEXT_Y": xp_text_y,
        # 中：刷新概率
        "ODDS_X": odds_x,
        "ODDS_Y": odds_y,
        "ODDS_GAP": odds_gap,
        "ODDS_BOX": odds_box,
        # 右：金币 + 利息
        "GOLD_X": gold_x,
        "GOLD_Y": gold_y,
        "INTEREST_X": interest_x,
        "INTEREST_Y": interest_y,
        # ---------- 左下角操作区 ----------
        "OP_X": op_x,
        "OP_W": op_w,
        "OP_H": op_h,
        "OP_REFRESH_Y": op_refresh_y,
        "OP_XP_Y": op_xp_y,
        # ---------- 右下角按钮 ----------
        "LOCK_X": lock_x,
        "LOCK_Y": lock_y,
        "LOCK_H": lock_h,
        "FIGHT_X": fight_x,
        "FIGHT_Y": fight_y,
        "FIGHT_H": fight_h,
        "SIDE_BTN_W": side_btn_w,
        # ---------- HP 血条（备战席上方） ----------
        "HP_BAR_Y": hp_bar_y,
        "HP_BAR_W": hp_bar_w,
        "HP_BAR_H": hp_bar_h,
        "HP1_X": hp1_x,
        "HP2_X": hp2_x,
        "POP_X": pop_x,
        # ---------- 侧边羁绊面板 ----------
        "SIDE_W": side_w,
        "BOARD_AREA_H": board_area_h,
        "SIDE_PAD": 14 * s,
        "SIDE_LINE_H": 22 * s,
        "TRAIT_DOT": 16 * s,
        # ---------- 提示行（放在备战席与商店之间，不再和商店卡重叠） ----------
        "HINT_Y": bench_y + bench_cell + 8 * s,
        # ---------- 装备栏（右侧中部 3x4 网格） ----------
        "ITEM_CELL": item_cell,
        "ITEM_GAP": item_gap,
        "ITEM_COLS": item_cols,
        "ITEM_ROWS": item_rows,
        "ITEM_BENCH_W": item_w,
        "ITEM_BENCH_H": item_h,
        "ITEM_BENCH_X": item_x,
        "ITEM_BENCH_Y": item_y,
        # ---------- 8 人战况面板 ----------
        "ROSTER_W": roster_w,
        "ROSTER_X": roster_x,
        "ROSTER_Y": roster_y,
        "ROSTER_ROW_H": roster_row_h,
        # ---------- 结算面板 ----------
        "RESULT_W": 520 * s,
        "RESULT_H": 230 * s,
        "BTN_NEXT_W": 150 * s,
        "BTN_NEXT_H": 42 * s,
        # ---------- 战斗控制条 ----------
        "CTRL_H": 74 * s,
        "BTN_CTRL_W": 84 * s,
        "BTN_CTRL_H": 34 * s,
        "BTN_CTRL_GAP": 12 * s,
        # ---------- 动效 ----------
        "FLOAT_RISE": 30 * s,  # 飘字上浮距离
        "BUMP_PUSH": 13 * s,  # 近战突进位移
        "ANIM_FAST": 0.18,
        "ANIM_MID": 0.45,
        "ANIM_SLOW": 0.9,
    }


def set_scale(scale: int) -> int:
    """应用缩放因子，返回实际生效值（会被限制在 1~2）。"""
    s = max(MIN_SCALE, min(MAX_SCALE, int(scale)))
    globals().update(_layout(s))
    return s


def auto_scale(avail_w: int, avail_h: int) -> int:
    """按可用屏幕尺寸挑一个整数缩放因子（宁小勿大，避免窗口超出屏幕）。"""
    return max(MIN_SCALE, min(MAX_SCALE, min(avail_w // DESIGN_W, avail_h // DESIGN_H)))


set_scale(1)
