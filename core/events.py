"""战斗事件日志。

战斗过程不直接驱动画面，而是产出一份事件流。渲染层负责把这份日志"慢放"出来，
服务器、复盘工具、平衡脚本消费的是同一份数据。
"""

from __future__ import annotations

from dataclasses import dataclass, field

EV_MOVE = "move"
EV_ATTACK = "attack"
EV_DAMAGE = "damage"
EV_CAST = "cast"
EV_HEAL = "heal"
EV_DEATH = "death"
EV_END = "end"

# 命令行日志默认打印这些事件（move 每 tick 都有，太吵）
LOG_DEFAULT = (EV_DAMAGE, EV_CAST, EV_HEAL, EV_DEATH, EV_END)


@dataclass
class Event:
    tick: int
    type: str
    data: dict = field(default_factory=dict)

    @property
    def time(self) -> float:
        """事件发生的时间（秒），按 20 tick/s 换算。"""
        return self.tick / 20.0


def format_event(e: Event) -> str:
    """把事件格式化成一行人类可读的日志。"""
    d = e.data
    t = f"[{e.time:5.2f}s]"

    if e.type == EV_MOVE:
        return f"{t} {d['name']}({d['team']}) 移动到 ({d['x']}, {d['y']})"
    if e.type == EV_ATTACK:
        return f"{t} {d['name']}({d['team']}) 攻击 {d['target']}"
    if e.type == EV_DAMAGE:
        crit = " [暴击]" if d["crit"] else ""
        kind = "物理" if d["kind"] == "physical" else "法术"
        return (
            f"{t} {d['source']} -> {d['target']} {kind}伤害 {d['amount']:.1f}{crit}"
            f"（{d['target']} 剩余 {d['hp_left']:.1f}）"
        )
    if e.type == EV_CAST:
        extra = f"，命中 {d['hits']} 个目标" if d.get("hits") else f"，目标 {d['target']}"
        return f"{t} {d['name']}({d['team']}) 施放【{d['ability']}】{extra}"
    if e.type == EV_HEAL:
        return (
            f"{t} {d['name']}({d['team']}) 治疗 {d['target']} {d['amount']:.1f}"
            f"（{d['target']} 剩余 {d['hp_left']:.1f}）"
        )
    if e.type == EV_DEATH:
        return f"{t} {d['name']}({d['team']}) 阵亡"
    if e.type == EV_END:
        return f"{t} 战斗结束：{d['result']}"
    return f"{t} {e.type} {d}"
