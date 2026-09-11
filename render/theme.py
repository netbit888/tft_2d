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

    # 左侧面板拆成“页签栏 + 内容区”：窄按钮栏竖排「羁绊 / 装备」，
    # 点哪个页签，右侧内容区就显示哪个（羁绊详情 / 装备栏）。
    side_pad = 14 * s
    side_tab_w = 52 * s
    side_tab_gap = 8 * s
    side_btn = 46 * s
    side_btn_gap = 10 * s
    side_content_x = side_pad + side_tab_w + side_tab_gap
    side_content_w = side_w - side_pad * 2 - side_tab_w - side_tab_gap
    side_panel_y = top_h + 12 * s
    side_panel_h = board_area_h - 24 * s
    side_line_h = 40 * s  # 羁绊行高（含六边形图标）
    trait_hex = 32 * s  # 羁绊六边形图标边长

    board_cols, board_rows = 7, 8
    # 六边形（尖顶朝上）蜂窝棋盘 + 2.5D 透视：
    # 远端行（屏幕顶部，disp=0）缩到 persp_far、近端行（底部，disp=7）到 persp_near，
    # 行距按缩放积分排布（近处行距大、远处行距小），横向向棋盘中轴收敛。
    persp_far = 0.72
    persp_near = 1.0
    hex_r = 38 * s  # 原 33：透视后远端≈27、近端 38，整体占幅与原棋盘相当
    col_step = int(round(hex_r * 1.732))  # 横向邻格中心距 = sqrt(3) * r
    row_step = int(round(hex_r * 1.5))    # 相邻行中心距 = 1.5 * r
    cell = hex_r * 2                      # 棋子/动效仍按“格子”概念缩放
    board_w = board_cols * col_step + col_step  # 列跨距 + 错位/顶点留白
    # 透视后总高 = (far+near) * (hex_r + row_step * 行距数 / 2)，行距积分见 board_view._persp_row_y
    board_h = int(round((persp_far + persp_near) * (hex_r + row_step * (board_rows - 1) / 2)))
    board_x = (win_w - board_w) // 2
    board_y = top_h + (board_area_h - board_h) // 2

    bench_slots = 8
    bench_cell = 84 * s
    bench_gap = 12 * s
    bench_w = bench_slots * bench_cell + (bench_slots - 1) * bench_gap
    bench_x = (win_w - bench_w) // 2
    bench_y = top_h + board_area_h + 8 * s

    # 商店改为「弹出式浮层」：点右下金币球打开，卡面坐标即浮层内那一行。
    # shop_x/shop_y 仍是卡面左上角，命中检测直接复用。
    shop_slots = 5
    shop_card_w = 160 * s
    shop_card_h = 112 * s
    shop_gap = 12 * s
    shop_w = shop_slots * shop_card_w + (shop_slots - 1) * shop_gap
    shop_h = shop_card_h
    shop_panel_w = 920 * s
    shop_panel_h = 316 * s
    shop_panel_x = (win_w - shop_panel_w) // 2
    shop_panel_y = (win_h - shop_panel_h) // 2
    shop_x = shop_panel_x + (shop_panel_w - shop_w) // 2
    shop_y = shop_panel_y + 58 * s

    # 浮层：右上关闭 + 底部「刷新 / 锁定」两枚按钮
    shop_btn_w, shop_btn_h = 150 * s, 44 * s
    shop_btn_y = shop_panel_y + 232 * s
    shop_refresh_x = shop_panel_x + 60 * s
    shop_lock_x = shop_refresh_x + shop_btn_w + 24 * s
    shop_close_w = 34 * s
    shop_close_x = shop_panel_x + shop_panel_w - shop_close_w - 14 * s
    shop_close_y = shop_panel_y + 14 * s

    # 浮层：刷新概率一行（费用方块 + 百分比）
    shop_odds_x = shop_panel_x + 190 * s
    shop_odds_y = shop_panel_y + 176 * s
    shop_odds_gap = 124 * s
    shop_odds_box = 20 * s

    # 拖到最底部空条 = 卖出（原来商店所占的位置，商店搬走后留白）
    sell_zone_x = side_w + 20 * s
    sell_zone_w = shop_w
    sell_zone_y = bench_y + bench_cell + 30 * s
    sell_zone_h = win_h - sell_zone_y

    # ---------- 底部 HUD 两球（左下经验球 / 右下金币球） ----------
    ball_r = 52 * s
    ball_y = win_h - 92 * s
    xp_ball_x = 96 * s
    gold_ball_x = win_w - 96 * s

    pad = 18 * s

    # ---------- 右侧区域（从上到下：战况面板 → 装备栏 → 商店旁按钮） ----------
    roster_w = 200 * s
    roster_x = win_w - roster_w - 12 * s
    roster_y = top_h + 12 * s
    roster_row_h = 30 * s

    # 装备栏：每页 3 列 x 4 行网格（库存超一页后用滚轮翻页，背包不设上限），
    # 面板自上而下：标题条（含翻页指示）→ 网格。
    # 页签切到「装备」时，整块面板铺在左侧内容区（网格水平居中）。
    item_cols, item_rows = 3, 4
    item_cell = 40 * s
    item_gap = 8 * s
    item_title_h = 30 * s
    item_foot = 6 * s
    item_grid_w = item_cols * item_cell + (item_cols - 1) * item_gap
    item_grid_h = item_rows * item_cell + (item_rows - 1) * item_gap
    item_pad_x = max(12 * s, (side_content_w - item_grid_w) // 2)
    item_w = side_content_w
    item_h = side_panel_h
    item_x = side_content_x
    item_y = side_panel_y

    # ---------- 右下角（开战；左下买经验、商店买卖都搬到两个球上了） ----------
    side_btn_w = 110 * s
    fight_x = win_w - side_btn_w - 12 * s
    fight_h = 52 * s
    fight_y = ball_y - ball_r - 86 * s  # 悬在右下金币球上方

    # ---------- 成装自选台（部署期 F2 打开） ----------
    armory_cols = 7
    armory_cell = int(84 * s)
    armory_step_x = int(96 * s)
    armory_step_y = int(92 * s)
    armory_pad = int(20 * s)
    armory_title_h = int(46 * s)
    armory_tab_h = int(40 * s)
    armory_foot_h = int(52 * s)

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
        # 羁绊颜色改为运行时按官方稀有度字段(color)映射 RARITY 边缘色（见 board_view.trait_color）
        "TRAIT_FALLBACK": (124, 132, 148),
        # ---------- 字体 ----------
        "FS_TITLE": int(26 * s),
        "FS_NORMAL": int(20 * s),
        "FS_SMALL": int(16 * s),
        "FS_TINY": int(13 * s),
        "FS_MICRO": int(11 * s),
        "FS_PIECE": int(18 * s),
        # ---------- 棋盘（蜂窝六边形） ----------
        "BOARD_COLS": board_cols,
        "BOARD_ROWS": board_rows,
        "CELL": cell,
        "HEX_R": hex_r,
        "HEX_COL_STEP": col_step,
        "HEX_ROW_STEP": row_step,
        "BOARD_W": board_w,
        "BOARD_H": board_h,
        "BOARD_X": board_x,
        "BOARD_Y": board_y,
        "TILE_INSET": 2 * s,  # 六边形地砖之间留的缝
        "PIECE_RATIO": 0.74,  # 头像直径 / 格子边长
        "PERSP_FAR": persp_far,   # 远端行（屏幕顶部）透视缩放
        "PERSP_NEAR": persp_near,  # 近端行（屏幕底部）透视缩放
        "PIECE_LIFT": 0.14,  # 立式棋子上移量 / 头像边长（脚下留出阴影位）
        # ---------- 备战席 ----------
        "BENCH_SLOTS": bench_slots,
        "BENCH_CELL": bench_cell,
        "BENCH_GAP": bench_gap,
        "BENCH_W": bench_w,
        "BENCH_X": bench_x,
        "BENCH_Y": bench_y,
        # ---------- 商店（弹出式浮层：卡面 + 概率 + 刷新 / 锁定） ----------
        "SHOP_SLOTS": shop_slots,
        "SHOP_CARD_W": shop_card_w,
        "SHOP_CARD_H": shop_card_h,
        "SHOP_GAP": shop_gap,
        "SHOP_W": shop_w,
        "SHOP_X": shop_x,
        "SHOP_Y": shop_y,
        "SHOP_H": shop_h,
        "SHOP_PANEL_X": shop_panel_x,
        "SHOP_PANEL_Y": shop_panel_y,
        "SHOP_PANEL_W": shop_panel_w,
        "SHOP_PANEL_H": shop_panel_h,
        "SHOP_CLOSE_X": shop_close_x,
        "SHOP_CLOSE_Y": shop_close_y,
        "SHOP_CLOSE_W": shop_close_w,
        "SHOP_REFRESH_X": shop_refresh_x,
        "SHOP_REFRESH_Y": shop_btn_y,
        "SHOP_REFRESH_W": shop_btn_w,
        "SHOP_REFRESH_H": shop_btn_h,
        "SHOP_LOCK_X": shop_lock_x,
        "SHOP_LOCK_Y": shop_btn_y,
        "SHOP_LOCK_W": shop_btn_w,
        "SHOP_LOCK_H": shop_btn_h,
        "SHOP_ODDS_X": shop_odds_x,
        "SHOP_ODDS_Y": shop_odds_y,
        "SHOP_ODDS_GAP": shop_odds_gap,
        "SHOP_ODDS_BOX": shop_odds_box,
        # ---------- 卖出区（拖到最底部空条） ----------
        "SELL_ZONE_X": sell_zone_x,
        "SELL_ZONE_Y": sell_zone_y,
        "SELL_ZONE_W": sell_zone_w,
        "SELL_ZONE_H": sell_zone_h,
        # ---------- 底部 HUD 两球 ----------
        "BALL_R": ball_r,
        "XP_BALL_X": xp_ball_x,
        "XP_BALL_Y": ball_y,
        "GOLD_BALL_X": gold_ball_x,
        "GOLD_BALL_Y": ball_y,
        # ---------- 顶栏（仅余高度，供棋盘/横幅定位；顶栏本身已移除） ----------
        "TOP_H": top_h,
        "PAD": pad,
        # ---------- 右下角按钮 ----------
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
        # ---------- 左侧面板（页签栏 + 内容区） ----------
        "SIDE_W": side_w,
        "BOARD_AREA_H": board_area_h,
        "SIDE_PAD": side_pad,
        "SIDE_TAB_W": side_tab_w,
        "SIDE_TAB_GAP": side_tab_gap,
        "SIDE_BTN": side_btn,
        "SIDE_BTN_GAP": side_btn_gap,
        "SIDE_CONTENT_X": side_content_x,
        "SIDE_CONTENT_W": side_content_w,
        "SIDE_PANEL_Y": side_panel_y,
        "SIDE_PANEL_H": side_panel_h,
        "SIDE_LINE_H": side_line_h,
        "TRAIT_HEX": trait_hex,
        # ---------- 提示行（放在备战席与商店之间，不再和商店卡重叠） ----------
        "HINT_Y": bench_y + bench_cell + 8 * s,
        # ---------- 装备栏（左侧内容区，标题 + 每页 3x4 网格，背包不限量） ----------
        "ITEM_CELL": item_cell,
        "ITEM_GAP": item_gap,
        "ITEM_COLS": item_cols,
        "ITEM_ROWS": item_rows,
        "ITEM_PAD_X": item_pad_x,
        "ITEM_TITLE_H": item_title_h,
        "ITEM_BENCH_W": item_w,
        "ITEM_BENCH_H": item_h,
        "ITEM_BENCH_X": item_x,
        "ITEM_BENCH_Y": item_y,
        # ---------- 成装自选台（F2） ----------
        "ARMORY_COLS": armory_cols,
        "ARMORY_CELL": armory_cell,
        "ARMORY_STEP_X": armory_step_x,
        "ARMORY_STEP_Y": armory_step_y,
        "ARMORY_PAD": armory_pad,
        "ARMORY_TITLE_H": armory_title_h,
        "ARMORY_TAB_H": armory_tab_h,
        "ARMORY_FOOT_H": armory_foot_h,
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


set_scale(1)
