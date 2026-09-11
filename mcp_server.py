"""TFT2D MCP Server：让 AI Agent 通过 MCP 协议操作自走棋游戏。

通过 stdio 与 Agent 通信，Agent 可以调用工具来买棋、卖棋、刷新商店、
升级、移动棋子、装备、合成、开战、推进回合——完整玩一局自走棋。

依赖：mcp>=2.0（pip install mcp）
运行：python mcp_server.py（作为子进程由 MCP 客户端启动）
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.mcpserver import MCPServer

from core import Game, buy, buy_xp, refresh_shop, sell
from core.deploy import move_piece, piece_at
from core.items import ItemInstance, combine_key, item_name
from core.loader import load_traits, load_units
from core.player import piece_label, piece_slots, try_upgrade
from core.shop import sell_piece
from core.traits import count_traits_from_tids, describe

mcp = MCPServer("tft2d")

# 全局游戏实例（单局模式）
_game: Game | None = None
_phase: str = "idle"  # idle → deploy → battle → result → over


def _require_game() -> Game:
    global _game
    if _game is None:
        raise RuntimeError("没有进行中的对局，请先调用 new_game")
    return _game


def _require_deploy() -> Game:
    g = _require_game()
    if _phase != "deploy":
        raise RuntimeError(f"当前阶段是 {_phase}，只有在 deploy（运营）阶段才能操作")
    return g


def _piece_to_dict(piece, index: int, on_board: bool = True) -> dict:
    tpl = load_units()[piece.tid]
    traits_data = load_traits()
    trait_names = [traits_data.get(t, {}).get("name", t) for t in tpl.traits]
    return {
        "index": index,
        "tid": piece.tid,
        "name": tpl.name,
        "cost": tpl.cost,
        "star": piece.star,
        "pos": list(piece.pos) if piece.pos else None,
        "equip": [item_name(it.item_id) for it in piece.equip],
        "traits": trait_names,
        "slots": piece_slots(piece),
    }


def _player_state(player, is_you: bool, full: bool = True) -> dict:
    data = {
        "name": player.name,
        "hp": player.hp,
        "gold": player.gold,
        "level": player.level,
        "xp": player.xp,
        "board_cap": player.board_cap,
        "board_pop": player.board_pop,
        "streak": player.streak,
        "alive": player.is_alive,
    }
    if is_you:
        data["board"] = [_piece_to_dict(p, i) for i, p in enumerate(player.board)]
        data["bench"] = [
            {
                "index": i,
                "tid": p.tid,
                "name": load_units()[p.tid].name,
                "star": p.star,
                "equip": [item_name(it.item_id) for it in p.equip],
            }
            for i, p in enumerate(player.bench)
        ]
        data["item_bench"] = [
            {"index": i, "item_id": it.item_id, "name": item_name(it.item_id)}
            for i, it in enumerate(player.item_bench)
        ]
        data["locked"] = player.locked
        # 羁绊
        tids = [p.tid for p in player.board]
        counts = count_traits_from_tids(tids, load_units())
        data["traits"] = describe(counts, load_traits())
    elif full:
        # 对手完整可见
        data["board"] = [_piece_to_dict(p, i) for i, p in enumerate(player.board)]
        data["bench_count"] = len(player.bench)
        tids = [p.tid for p in player.board]
        counts = count_traits_from_tids(tids, load_units())
        data["traits"] = describe(counts, load_traits())
    return data


def _shop_state(game: Game) -> list[dict]:
    slots = []
    for i, item in enumerate(game.shop_you.slots):
        if item.sold:
            slots.append({"index": i, "sold": True})
        else:
            tpl = load_units()[item.tid]
            traits_data = load_traits()
            trait_names = [traits_data.get(t, {}).get("name", t) for t in tpl.traits]
            slots.append({
                "index": i,
                "tid": item.tid,
                "name": tpl.name,
                "cost": item.cost,
                "sold": False,
                "traits": trait_names,
            })
    return slots


def _full_state(game: Game) -> dict:
    return {
        "round": game.round,
        "phase": _phase,
        "over": game.is_over(),
        "you": _player_state(game.you, is_you=True, full=True),
        "enemy": _player_state(game.enemy, is_you=False, full=True),
        "shop": _shop_state(game),
    }


# ==================== 工具实现 ====================


@mcp.tool()
def new_game(seed: int | None = None, num_players: int = 1) -> str:
    """开始一局新对局。seed 为随机种子（可复现），num_players=1 为 1v1，8 为八人局。"""
    global _game, _phase
    _game = Game(seed=seed, num_players=num_players)
    _game.begin_round()
    _phase = "deploy"
    return f"新对局开始！回合 1，你 {_game.you.hp} HP，金币 {_game.you.gold}。\n{state()}"


@mcp.tool()
def state() -> str:
    """获取当前完整局面状态：回合、阶段、双方 HP/金币/等级/棋盘/备战席/装备栏、商店、羁绊。"""
    g = _require_game()
    import json

    return json.dumps(_full_state(g), ensure_ascii=False, indent=2)


@mcp.tool()
def buy_unit(index: int) -> str:
    """购买商店中指定位置的棋子（0-4）。棋子会进入备战席，自动触发三合一升星。"""
    g = _require_deploy()
    msg = buy(g.you, g.shop_you, index)
    g.you.promote_from_bench()
    return msg


@mcp.tool()
def sell_unit(location: str = "board", index: int = 0) -> str:
    """卖出棋子。location='board' 卖场上第 index 个棋子，'bench' 卖备战席第 index 个。"""
    g = _require_deploy()
    if location == "board":
        if not (0 <= index < len(g.you.board)):
            return f"场上没有第 {index} 个棋子（共 {len(g.you.board)} 个）"
        return sell_piece(g.you, g.you.board[index])
    elif location == "bench":
        if not (0 <= index < len(g.you.bench)):
            return f"备战席没有第 {index} 个棋子（共 {len(g.you.bench)} 个）"
        return sell_piece(g.you, g.you.bench[index])
    return "location 必须是 'board' 或 'bench'"


@mcp.tool()
def refresh() -> str:
    """花费 2 金币刷新商店。"""
    g = _require_deploy()
    return refresh_shop(g.you, g.shop_you)


@mcp.tool()
def buy_experience() -> str:
    """花费 4 金币购买经验值（+4 XP），自动升级。"""
    g = _require_deploy()
    return buy_xp(g.you)


@mcp.tool()
def move(location: str, index: int, dest: str, col: int = 0, row: int = 0) -> str:
    """移动棋子。location='board'/'bench' 指定来源，index 为来源棋子序号。
    dest='board' 移到棋盘格 (col, row)，dest='bench' 移到备战席第 index 位。"""
    g = _require_deploy()
    if location == "board":
        if not (0 <= index < len(g.you.board)):
            return f"场上没有第 {index} 个棋子"
        piece = g.you.board[index]
    elif location == "bench":
        if not (0 <= index < len(g.you.bench)):
            return f"备战席没有第 {index} 个棋子"
        piece = g.you.bench[index]
    else:
        return "location 必须是 'board' 或 'bench'"

    if dest == "board":
        result = move_piece(g.you, piece, ("board", (col, row)), team="blue")
    elif dest == "bench":
        result = move_piece(g.you, piece, ("bench", col), team="blue")
    else:
        return "dest 必须是 'board' 或 'bench'"

    return result.message if result.message else "移动完成"


@mcp.tool()
def equip(item_index: int, piece_location: str = "board", piece_index: int = 0) -> str:
    """将装备栏第 item_index 件装备装到指定棋子上。
    piece_location='board' 装到场上第 piece_index 个棋子，='bench' 装到备战席。"""
    g = _require_deploy()
    if not (0 <= item_index < len(g.you.item_bench)):
        return f"装备栏没有第 {item_index} 件装备（共 {len(g.you.item_bench)} 件）"

    if piece_location == "board":
        if not (0 <= piece_index < len(g.you.board)):
            return f"场上没有第 {piece_index} 个棋子"
        piece = g.you.board[piece_index]
    elif piece_location == "bench":
        if not (0 <= piece_index < len(g.you.bench)):
            return f"备战席没有第 {piece_index} 个棋子"
        piece = g.you.bench[piece_index]
    else:
        return "piece_location 必须是 'board' 或 'bench'"

    from core.items import MAX_ITEMS_PER_PIECE

    if len(piece.equip) >= MAX_ITEMS_PER_PIECE:
        name = load_units()[piece.tid].name
        return f"{name} 已带满装备（{MAX_ITEMS_PER_PIECE}件），无法再装"

    item = g.you.item_bench.pop(item_index)
    piece.equip.append(item)
    pname = load_units()[piece.tid].name
    iname = item_name(item.item_id)
    return f"{iname} 已装备到 {pname}"


@mcp.tool()
def combine_items(item_a_index: int, item_b_index: int) -> str:
    """合成两件基础装备栏中的装备。返回合成结果。"""
    g = _require_deploy()
    bench = g.you.item_bench
    if not (0 <= item_a_index < len(bench)):
        return f"装备栏没有第 {item_a_index} 件"
    if not (0 <= item_b_index < len(bench)):
        return f"装备栏没有第 {item_b_index} 件"
    if item_a_index == item_b_index:
        return "不能选同一件装备"

    a, b = bench[item_a_index], bench[item_b_index]
    key = combine_key(a.item_id, b.item_id)
    if key is None:
        return f"{item_name(a.item_id)} 与 {item_name(b.item_id)} 无法合成"

    # 移除两件，添加合成件
    bench.remove(a)
    bench.remove(b)
    bench.append(ItemInstance(key))
    return f"合成成功：{item_name(a.item_id)} + {item_name(b.item_id)} → {item_name(key)}"


@mcp.tool()
def toggle_lock() -> str:
    """锁定/解锁商店。锁定后回合结束不自动刷新。"""
    g = _require_deploy()
    g.you.locked = not g.you.locked
    return f"商店已{'锁定' if g.you.locked else '解锁'}"


@mcp.tool()
def start_battle() -> str:
    """开始战斗阶段：AI 运营 → 自动配对 → 自动结算所有战斗。返回战斗结果和扣血。
    调用后进入 result 阶段，需调用 advance_round 进入下一回合。"""
    global _phase
    g = _require_game()
    if _phase != "deploy":
        return f"当前阶段是 {_phase}，只有 deploy 阶段才能开战"

    _phase = "battle"
    logs = g.run_ai_ops()
    combat = g.start_battle()

    if combat is None:
        outcome = g.finish_battle(None)
        _phase = "result"
        result_text = outcome["settle_msg"]
    else:
        combat.run()
        outcome = g.finish_battle(combat)
        _phase = "result"
        result_text = outcome["settle_msg"]
        # 战斗事件摘要
        from core.events import EV_CAST, EV_DEATH, EV_END, format_event

        events_summary = []
        for e in combat.events:
            if e.type in (EV_CAST, EV_DEATH, EV_END):
                events_summary.append(format_event(e))
        if events_summary:
            result_text += "\n战斗日志：\n  " + "\n  ".join(events_summary[-20:])

    if outcome.get("drops"):
        drops_text = "、".join(
            item_name(item_id) for _, item_id in outcome["drops"]
        )
        result_text += f"\n装备掉落：{drops_text}"

    if outcome.get("eliminated"):
        names = ", ".join(p.name for p in outcome["eliminated"])
        result_text += f"\n淘汰：{names}"

    if outcome.get("over"):
        _phase = "over"
        result_text += f"\n对局结束！{g.winner()}"
    else:
        result_text += "\n阶段：result。调用 advance_round 进入下一回合。"

    return result_text


@mcp.tool()
def advance_round() -> str:
    """结束当前回合，进入下一回合（发金币、利息、刷商店）。"""
    global _phase
    g = _require_game()
    if _phase != "result":
        return f"当前阶段是 {_phase}，只有 result 阶段才能推进回合"

    g.advance_round()
    _phase = "deploy"
    return f"进入回合 {g.round}。金币 {g.you.gold}，等级 {g.you.level}。"


if __name__ == "__main__":
    mcp.run()
