"""核心逻辑层：纯 Python，不依赖任何渲染库，可在命令行跑完整局。"""

from .ai import ai_equip, ai_take_turn, ai_upgrade_check
from .combat import Combat, DT, TICK_RATE
from .deploy import MoveResult, assign_positions, auto_place, move_piece, own_rows, piece_at
from .events import Event
from .game import Game
from .loader import build_team, load_traits, load_units
from .models import CombatResult, Unit, UnitTemplate
from .player import (
    MAX_BENCH,
    MAX_LEVEL,
    MAX_STAR,
    Piece,
    Player,
    board_cap_for_level,
    buy_xp,
    try_upgrade,
    upgrade_cost,
    xp_needed_for_level,
)
from .pool import Pool
from .rng import Rng
from .shop import REFRESH_COST, Shop, buy, refresh_shop, sell
from .traits import count_traits, count_traits_from_tids

__all__ = [
    "Combat",
    "DT",
    "TICK_RATE",
    "Event",
    "Game",
    "ai_take_turn",
    "ai_equip",
    "ai_upgrade_check",
    "assign_positions",
    "auto_place",
    "move_piece",
    "piece_at",
    "own_rows",
    "MoveResult",
    "build_team",
    "load_traits",
    "load_units",
    "CombatResult",
    "Piece",
    "Player",
    "Unit",
    "UnitTemplate",
    "Rng",
    "Shop",
    "buy",
    "sell",
    "refresh_shop",
    "REFRESH_COST",
    "MAX_BENCH",
    "MAX_LEVEL",
    "MAX_STAR",
    "try_upgrade",
    "board_cap_for_level",
    "buy_xp",
    "upgrade_cost",
    "xp_needed_for_level",
    "Pool",
    "count_traits",
    "count_traits_from_tids",
]
