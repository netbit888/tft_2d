"""整局驱动器（play_auto_match）的确定性 / 终止性回归测试。

这些测试锁定的正是"单一真源"回合流程：GUI、CLI、无头仿真全部经由
Game.run_ai_ops / start_battle / finish_battle / advance_round 走同一条路径。
"""

from __future__ import annotations

from core import Game


def _run_sig(game: Game, max_rounds: int = 40):
    """跑完整局，记录每个回合后的血量变化作为“指纹”。"""
    sig: list = []

    def on_round(g: Game, outcome: dict) -> None:
        sig.append((g.round, tuple(p.hp for p in g.players), outcome["over"]))

    game.play_auto_match(on_round=on_round, max_rounds=max_rounds)
    return sig, game.winner(), game.round


def test_same_seed_is_deterministic():
    a, b = Game(seed=123, num_players=4), Game(seed=123, num_players=4)
    sa, wa, ra = _run_sig(a)
    sb, wb, rb = _run_sig(b)
    assert sa == sb
    assert wa == wb
    assert ra == rb


def test_1v1_auto_terminates_and_reports_winner():
    g = Game(seed=7)
    summary = g.play_auto_match()
    assert summary["rounds"] >= 1
    assert g.winner()  # 胜负文本非空
    assert g.round <= g.MAX_ROUND


def test_8p_auto_reaches_eliminations():
    g = Game(seed=1, num_players=8)
    g.play_auto_match()
    # 8 人局应当有人被淘汰（或恰好打满上限）
    assert any(not p.is_alive for p in g.players) or g.round >= g.MAX_ROUND


def test_resolution_returns_structured_summary():
    """结算阶段返回统一摘要（GUI/CLI/无头一致消费），且运营/配对阶段不扣血。"""
    g = Game(seed=11)
    g.begin_round()
    before = [p.hp for p in g.players]
    g.run_ai_ops(drive_player=True)
    combat = g.start_battle()
    assert [p.hp for p in g.players] == before, "运营/配对阶段不应扣血"
    outcome = g.finish_battle(combat)
    assert set(outcome) >= {"result", "settle_msg", "drops", "eliminated", "over"}
