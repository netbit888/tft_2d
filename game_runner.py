"""TFT2D 游戏运行器：通过命令行与游戏交互，保存/加载对局状态。

用法：
    python game_runner.py new [--seed N] [--players N]
    python game_runner.py state
    python game_runner.py buy <index>
    python game_runner.py sell <board|bench> <index>
    python game_runner.py refresh
    python game_runner.py buyxp
    python game_runner.py move <board|bench> <index> <board|bench> [col] [row]
    python game_runner.py equip <item_index> <board|bench> <piece_index>
    python game_runner.py combine <item_a> <item_b>
    python game_runner.py lock
    python game_runner.py battle
    python game_runner.py next
"""
from __future__ import annotations

import json
import os
import pickle
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from core import Game, buy, buy_xp, refresh_shop
from core.deploy import move_piece
from core.items import MAX_ITEMS_PER_PIECE, ItemInstance, combine_key, item_name
from core.loader import load_traits, load_units
from core.player import piece_slots
from core.shop import sell_piece
from core.traits import count_traits_from_tids, describe

SAVE_FILE = Path(__file__).parent / "_game_state.pkl"

# ---- 状态管理 ----

def save_game(game: Game, phase: str) -> None:
    with open(SAVE_FILE, "wb") as f:
        pickle.dump({"game": game, "phase": phase}, f)

def load_game() -> tuple[Game, str] | None:
    if not SAVE_FILE.exists():
        return None
    with open(SAVE_FILE, "rb") as f:
        data = pickle.load(f)
    return data["game"], data["phase"]

# ---- 序列化 ----

def piece_dict(piece, index: int) -> dict:
    tpl = load_units()[piece.tid]
    traits_data = load_traits()
    return {
        "index": index,
        "name": tpl.name,
        "cost": tpl.cost,
        "star": piece.star,
        "pos": list(piece.pos) if piece.pos else None,
        "equip": [item_name(it.item_id) for it in piece.equip],
        "traits": [traits_data.get(t, {}).get("name", t) for t in tpl.traits],
        "slots": piece_slots(piece),
    }

def full_state(game: Game, phase: str) -> dict:
    you = game.you
    enemy = game.enemy
    tpl = load_units()
    td = load_traits()

    # 羁绊
    tids = [p.tid for p in you.board]
    counts = count_traits_from_tids(tids, tpl)
    you_traits = describe(counts, td)
    enemy_tids = [p.tid for p in enemy.board]
    enemy_counts = count_traits_from_tids(enemy_tids, tpl)
    enemy_traits = describe(enemy_counts, td)

    # 商店
    shop = []
    for i, s in enumerate(game.shop_you.slots):
        if s.sold:
            shop.append({"index": i, "sold": True})
        else:
            t = tpl[s.tid]
            shop.append({
                "index": i, "name": t.name, "cost": s.cost, "sold": False,
                "traits": [td.get(tr, {}).get("name", tr) for tr in t.traits],
            })

    return {
        "round": game.round,
        "phase": phase,
        "over": game.is_over(),
        "you": {
            "name": you.name, "hp": you.hp, "gold": you.gold,
            "level": you.level, "xp": you.xp,
            "board_cap": you.board_cap, "board_pop": you.board_pop,
            "streak": you.streak, "locked": you.locked,
            "board": [piece_dict(p, i) for i, p in enumerate(you.board)],
            "bench": [{"index": i, "name": load_units()[p.tid].name, "star": p.star,
                        "equip": [item_name(it.item_id) for it in p.equip]}
                       for i, p in enumerate(you.bench)],
            "item_bench": [{"index": i, "name": item_name(it.item_id), "item_id": it.item_id}
                           for i, it in enumerate(you.item_bench)],
            "traits": you_traits,
        },
        "enemy": {
            "name": enemy.name, "hp": enemy.hp, "gold": enemy.gold,
            "level": enemy.level,
            "board_cap": enemy.board_cap, "board_pop": enemy.board_pop,
            "board": [{"index": i, "name": load_units()[p.tid].name,
                        "star": p.star,
                        "traits": [td.get(t, {}).get("name", t) for t in load_units()[p.tid].traits]}
                       for i, p in enumerate(enemy.board)],
            "traits": enemy_traits,
        },
        "shop": shop,
    }

def print_state(game: Game, phase: str) -> None:
    s = full_state(game, phase)
    print(json.dumps(s, ensure_ascii=False, indent=2))

# ---- 命令处理 ----

def cmd_new(args):
    seed = None
    players = 1
    i = 0
    while i < len(args):
        if args[i] == "--seed" and i + 1 < len(args):
            seed = int(args[i + 1]); i += 2
        elif args[i] == "--players" and i + 1 < len(args):
            players = int(args[i + 1]); i += 2
        else:
            i += 1

    game = Game(seed=seed, num_players=players)
    game.begin_round()
    phase = "deploy"
    save_game(game, phase)
    print(f"新对局开始！种子={seed}")
    print_state(game, phase)

def cmd_state():
    data = load_game()
    if data is None:
        print("没有进行中的对局"); return
    game, phase = data
    print_state(game, phase)

def cmd_buy(args):
    data = load_game()
    if data is None:
        print("没有进行中的对局"); return
    game, phase = data
    if phase != "deploy":
        print(f"当前阶段是 {phase}，只有 deploy 阶段才能购买"); return
    idx = int(args[0])
    msg = buy(game.you, game.shop_you, idx)
    game.you.promote_from_bench()
    save_game(game, phase)
    print(msg)
    print_state(game, phase)

def cmd_sell(args):
    data = load_game()
    if data is None:
        print("没有进行中的对局"); return
    game, phase = data
    if phase != "deploy":
        print(f"当前阶段是 {phase}，只有 deploy 阶段才能卖出"); return
    loc = args[0]
    idx = int(args[1])
    if loc == "board":
        if 0 <= idx < len(game.you.board):
            msg = sell_piece(game.you, game.you.board[idx])
        else:
            msg = f"场上没有第 {idx} 个棋子"
    elif loc == "bench":
        if 0 <= idx < len(game.you.bench):
            msg = sell_piece(game.you, game.you.bench[idx])
        else:
            msg = f"备战席没有第 {idx} 个棋子"
    else:
        msg = "location 必须是 board 或 bench"
    save_game(game, phase)
    print(msg)
    print_state(game, phase)

def cmd_refresh():
    data = load_game()
    if data is None:
        print("没有进行中的对局"); return
    game, phase = data
    if phase != "deploy":
        print(f"当前阶段是 {phase}，只有 deploy 阶段才能刷新"); return
    msg = refresh_shop(game.you, game.shop_you)
    save_game(game, phase)
    print(msg)
    print_state(game, phase)

def cmd_buyxp():
    data = load_game()
    if data is None:
        print("没有进行中的对局"); return
    game, phase = data
    if phase != "deploy":
        print(f"当前阶段是 {phase}，只有 deploy 阶段才能买经验"); return
    msg = buy_xp(game.you)
    save_game(game, phase)
    print(msg)
    print_state(game, phase)

def cmd_move(args):
    data = load_game()
    if data is None:
        print("没有进行中的对局"); return
    game, phase = data
    if phase != "deploy":
        print(f"当前阶段是 {phase}，只有 deploy 阶段才能移动"); return
    src_loc = args[0]
    src_idx = int(args[1])
    dest_loc = args[2]
    if src_loc == "board":
        piece = game.you.board[src_idx]
    else:
        piece = game.you.bench[src_idx]
    if dest_loc == "board":
        col = int(args[3]); row = int(args[4])
        result = move_piece(game.you, piece, ("board", (col, row)), team="blue")
    else:
        result = move_piece(game.you, piece, ("bench", src_idx), team="blue")
    save_game(game, phase)
    print(result.message or "移动完成")
    print_state(game, phase)

def cmd_equip(args):
    data = load_game()
    if data is None:
        print("没有进行中的对局"); return
    game, phase = data
    if phase != "deploy":
        print(f"当前阶段是 {phase}，只有 deploy 阶段才能装备"); return
    item_idx = int(args[0])
    loc = args[1]
    piece_idx = int(args[2])
    if loc == "board":
        piece = game.you.board[piece_idx]
    else:
        piece = game.you.bench[piece_idx]
    if len(piece.equip) >= MAX_ITEMS_PER_PIECE:
        print(f"{load_units()[piece.tid].name} 已带满装备"); return
    item = game.you.item_bench.pop(item_idx)
    piece.equip.append(item)
    save_game(game, phase)
    print(f"{item_name(item.item_id)} 装备到 {load_units()[piece.tid].name}")
    print_state(game, phase)

def cmd_combine(args):
    data = load_game()
    if data is None:
        print("没有进行中的对局"); return
    game, phase = data
    if phase != "deploy":
        print(f"当前阶段是 {phase}，只有 deploy 阶段才能合成"); return
    a_idx = int(args[0]); b_idx = int(args[1])
    bench = game.you.item_bench
    a, b = bench[a_idx], bench[b_idx]
    key = combine_key(a.item_id, b.item_id)
    if key is None:
        print(f"{item_name(a.item_id)} 与 {item_name(b.item_id)} 无法合成"); return
    bench.remove(a); bench.remove(b)
    bench.append(ItemInstance(key))
    save_game(game, phase)
    print(f"合成：{item_name(a.item_id)} + {item_name(b.item_id)} → {item_name(key)}")
    print_state(game, phase)

def cmd_lock():
    data = load_game()
    if data is None:
        print("没有进行中的对局"); return
    game, phase = data
    if phase != "deploy":
        print(f"当前阶段是 {phase}"); return
    game.you.locked = not game.you.locked
    save_game(game, phase)
    print(f"商店已{'锁定' if game.you.locked else '解锁'}")

def cmd_battle():
    data = load_game()
    if data is None:
        print("没有进行中的对局"); return
    game, phase = data
    if phase != "deploy":
        print(f"当前阶段是 {phase}，只有 deploy 阶段才能开战"); return
    phase = "battle"
    logs = game.run_ai_ops()
    if logs:
        print("电脑运营：" + "；".join(logs))
    combat = game.start_battle()
    if combat is None:
        outcome = game.finish_battle(None)
        print("（一方没有棋子，跳过战斗）")
    else:
        combat.run()
        outcome = game.finish_battle(combat)
        from core.events import EV_CAST, EV_DEATH, EV_END, format_event
        events = [format_event(e) for e in combat.events if e.type in (EV_CAST, EV_DEATH, EV_END)]
        if events:
            print("--- 战斗日志 ---")
            for e in events[-15:]:
                print("  " + e)
    print(f"结算：{outcome['settle_msg']}")
    if outcome.get("drops"):
        drops = "、".join(item_name(i) for _, i in outcome["drops"])
        print(f"装备掉落：{drops}")
    if outcome.get("eliminated"):
        print(f"淘汰：{', '.join(p.name for p in outcome['eliminated'])}")
    if outcome.get("over"):
        phase = "over"
        print(f"对局结束！{game.winner()}")
    else:
        phase = "result"
        print("阶段：result。调用 next 进入下一回合。")
    save_game(game, phase)

def cmd_next():
    data = load_game()
    if data is None:
        print("没有进行中的对局"); return
    game, phase = data
    if phase != "result":
        print(f"当前阶段是 {phase}，只有 result 阶段才能推进回合"); return
    game.advance_round()
    phase = "deploy"
    save_game(game, phase)
    print(f"进入回合 {game.round}，金币 {game.you.gold}")
    print_state(game, phase)

# ---- 入口 ----

def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    cmd = sys.argv[1]
    args = sys.argv[2:]
    try:
        if cmd == "new": cmd_new(args)
        elif cmd == "state": cmd_state()
        elif cmd == "buy": cmd_buy(args)
        elif cmd == "sell": cmd_sell(args)
        elif cmd == "refresh": cmd_refresh()
        elif cmd == "buyxp": cmd_buyxp()
        elif cmd == "move": cmd_move(args)
        elif cmd == "equip": cmd_equip(args)
        elif cmd == "combine": cmd_combine(args)
        elif cmd == "lock": cmd_lock()
        elif cmd == "battle": cmd_battle()
        elif cmd == "next": cmd_next()
        else: print(f"未知命令：{cmd}")
    except Exception as e:
        print(f"错误：{e}")

if __name__ == "__main__":
    main()
