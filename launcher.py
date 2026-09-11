"""统一启动入口：一个命令访问全部玩法与工具。

用法（源码目录 / 安装后 `tft2d` 命令均可）：
    python launcher.py gui                 # 图形界面（默认全屏；可加 --players 8 / --seed / --scale / --windowed）
    python launcher.py play --seed 7       # 命令行 1v1（纯 core，无 pygame 依赖）
    python launcher.py play --auto         # 双方 AI 全自动跑完整局
    python launcher.py sim --check         # 校验 data/*.json 数据完整性
    python launcher.py sim --bench 1000    # 批量随机对局做平衡统计
    python launcher.py sim --mirror 300    # 镜像对称局内核自检
    python launcher.py sim --fullgame 20 --players 8   # 整局全自动仿真

子命令后的参数会原样转发给对应入口（app.py / play.py / tools/simulate.py），
因此各入口既可直接 `python xxx.py` 运行，也可经本启动器统一调用。
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

COMMANDS = {
    "gui": ("app", "main", "图形界面 1v1（--players 8 开 8 人局）"),
    "play": ("play", "main", "命令行 1v1（纯 core，无 pygame 依赖）"),
    "cli": ("play", "main", "命令行 1v1（play 的别名）"),
    "sim": ("tools.simulate", "main", "战斗模拟 / 批量统计 / 整局仿真 / 数据自检"),
}


def _help() -> str:
    width = max(len(name) for name in COMMANDS) + 2
    rows = "\n".join(
        f"  {name:<{width}}{desc}" for name, (_, _, desc) in COMMANDS.items()
    )
    return f"可用子命令：\n{rows}\n\n直接运行参数可加 -h 查看各入口的详细选项，例如：\n  python launcher.py gui -h"


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help", "help"):
        print(__doc__.strip().splitlines()[0])
        print(_help())
        return 0 if args else 2
    name = args[0]
    if name not in COMMANDS:
        print(f"未知子命令：{name}\n\n{_help()}")
        return 2
    module_name, func_name, _ = COMMANDS[name]
    mod = importlib.import_module(module_name)
    fn = getattr(mod, func_name)
    code = fn(args[1:])
    return code if isinstance(code, int) else 0


if __name__ == "__main__":
    raise SystemExit(main())
