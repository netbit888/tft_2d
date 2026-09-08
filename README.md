# tft_2d —— 自走棋 1v1 / 8 人局图形化模拟器

一个用纯 Python + pygame-ce 写的类“金铲铲”自走棋。核心规则逻辑（`core/`）不依赖任何第三方库，
既可以在图形界面里玩，也可以纯命令行跑完整局，还能批量做平衡统计与内核自检。

## 功能特性

- **50 枚棋子 / 8 种羁绊 / 装备合成**：数据全部放在 `data/*.json`，调数值不用改代码。
- **共享卡池**：每名玩家的商店从同一个公共卡池抽牌，1v1 或 8 人局语义一致。
- **8 人局**：8 名玩家共享卡池，每回合两两配对打 1v1，败者扣血、淘汰，直至剩下赢家。
- **8 行蜂窝六边形棋盘（7×8）**：蓝方（你）布阵在屏幕下方 4 行，红方（敌方）在屏幕上方 4 行，
  相邻行错半格，行与行之间呈蜂窝交错排布。
- **战前布阵**：拖拽摆位、自动补位（近战贴交火线、远程靠后，排满自动退后一行）。
- **实时战斗回放**：棋子按格子移动、普攻、施法，带血条/弹道/光环/伤害数字等演出。
- **确定性随机**：`--seed` 可复现同一局，便于调平衡与排查。
- **程序化生成的 BGM 与音效**：部署/布阵与开战两段循环 BGM、回合胜/负小段，
  以及买卖/合成/刷新/升星等 UI 音效；无音频设备自动静音降级，`M` 键随时静音。
- **统一启动器 + 可安装工程化**：`python launcher.py gui / play / sim` 一条命令访问全部玩法与工具；
  `pyproject.toml` 支持 `pip install -e .` 后直接用 `tft2d`、`tft2d-gui`、`tft2d-sim` 命令启动（见下）。

## 环境要求

- Python 3.11+（Windows 建议勾选 *Add to PATH*）
- 图形界面依赖：[pygame-ce](https://pygame-ce.github.io/) ≥ 2.5

```bash
pip install -r requirements.txt
```

> `core/`（战斗内核）零第三方依赖，只装 pygame-ce 也能跑 `play.py` 命令行版。

## 快速开始

Windows 下双击即可，脚本会自动补装依赖：

| 文件 | 作用 |
| --- | --- |
| `start_gui.bat` | 图形界面 1v1 对战 |
| `start_gui_8p.bat` | 图形界面 8 人局 |
| `run.bat` | 菜单：图形界面 / 命令行对局 / 自动演示 / 平衡统计 / 内核自检 |

> 三个脚本都是调用统一启动器 `python launcher.py <子命令>`，子命令会原样转发参数，
> 因此「双击 .bat」与「手动命令行」行为完全一致。

### 统一启动器 `launcher.py`

```bash
python launcher.py gui [--seed N] [--players 1|8] [--scale 1|2] [--no-log]   # 图形界面
python launcher.py play [--seed N] [--auto]                                  # 命令行 1v1（无 pygame）
python launcher.py sim [--seed N] [--check|--bench N|--mirror N|--fullgame N] # 工具：数据自检/平衡/镜像/整局仿真
```

也可以直接运行各入口（`app.py` / `play.py` / `tools/simulate.py`），效果相同。

### 安装为命令（可选）

想全局使用 `tft2d` 命令，或为后续打包做准备：

```bash
pip install -e ".[dev]"     # 可编辑安装（含 pytest），之后可直接敲 tft2d / tft2d-gui / tft2d-play / tft2d-sim
```

也可以直接用命令行：

```bash
# 图形界面 1v1
python app.py

# 指定随机种子（复现同一局）
python app.py --seed 7

# 图形界面 8 人局
python app.py --players 8

# 2x 高分屏缩放
python app.py --scale 2

# 命令行文字版（随机/指定种子/双方全自动）
python play.py
python play.py --seed 7
python play.py --seed 7 --auto
```

### 图形界面命令行参数（`app.py`）

| 参数 | 说明 |
| --- | --- |
| `--seed N` | 对局随机种子 |
| `--players 1\|8` | 玩家数：1 = 1v1（你 + 电脑），8 = 8 人局（你 + 7 电脑） |
| `--scale 1\|2` | 界面缩放，不传则按屏幕自动选择 |
| `--no-log` | 不在控制台打印战斗日志 |

## 图形界面操作

| 操作 | 效果 |
| --- | --- |
| **左键单击** 商店卡片 | 购买该棋子（出现在下方备战席） |
| **左键按住拖动** | 拖拽摆位：备战席 ↔ 棋盘、棋盘内换位；拖到己方半场高亮区即可落子 |
| **左键单击（原地松开）** 棋子 | 打开/切换该棋子详情；再点同一棋子、点空白处或按 `ESC` 关闭（棋盘上敌我双方均可） |
| **右键单击** 棋子/备战席 | 卖出换金币 |
| 悬停 左侧羁绊栏 / 装备栏 | 查看羁绊效果与装备详情（装备栏还会列出当前凑得齐的合成配方） |
| **左键拖动** 装备到棋子 | 穿装备（可叠加多件）；拖基础件到身上带散件的棋子可直接合成并显示合成详情 |
| 拖动 两件基础装备 到装备栏同一格 | 合成高级装备；拖到装备栏空格则把棋子身上的装备卸下 |
| 装备栏背包 | 不设容量上限：库存超过一页（3x4）后，鼠标悬停面板滚动滚轮翻页浏览 |
| 按钮：刷新 / 升级（可长按连升）/ 锁定 / 开战 | 运营操作 |
| `ESC` | 先关闭棋子详情，再按一次退出游戏 |
| `M` | 静音 / 恢复声音（背景乐 + 音效） |

> 商店卡采用极简样式：只显示**名字 + 费用 + 稀有度描边**，选中/已购入状态直观可见。
> 蓝色 = 你的布阵区（屏幕下方 4 行），红色 = 敌方布阵区（屏幕上方 4 行）。

### 玩法节奏

每回合分「运营 → 布阵 → 开战」：买棋子、上人口、凑羁绊，然后自动打一场实时战斗。
3 张同名棋子会自动升星（上限 3 星，属性随星级与羁绊修正）；羁绊只看上阵棋子的同羁绊数量。

- 刷新商店：2 金币；锁定商店后下回合不自动刷新。
- 升级：固定 4 金币买 4 经验；每回合自然获得 2 经验，人口上限 9。
- 费用刷新概率已对齐金铲铲现行节奏（见 `data/level.json` 的 `odds`）。

## 战斗内核模拟工具

统一启动器与直接调用等价（`python launcher.py sim …` 与 `python tools/simulate.py …`）：

```bash
# 校验 data/*.json 数据完整性（0 = 通过，供 CI/脚本门禁）
python launcher.py sim --check

# 跑一场单局（默认双方各 4 枚随机镜像棋子）
python launcher.py sim

# 批量 N 场随机对局做平衡统计（蓝/红胜率 + 平均时长）
python launcher.py sim --bench 3000

# 批量 N 场镜像对称局做内核自检（两侧胜率差应在 ±3% 内）
python launcher.py sim --mirror 3000

# 整局全自动仿真：8 人局所有玩家由 AI 运营，输出名次分布/节奏/环境棋子占用
python launcher.py sim --fullgame 20 --players 8
```

## 棋子贴图（可选）

棋盘、备战席、商店卡等棋子头像支持外部贴图：**有图显图，没图自动按原先的程序化头像显示**。

- 资源路径：`assets/units/<tid>.png`（`<tid>` 与 `data/units.json` 中的 `id` 严格对齐）。
- 推荐格式：方形 PNG，透明底，主体居中、占画面直径约 80%；绘制时会被自动裁剪到圆形头像内，队伍光环/稀有度描边/星级金星/血条照常保留。
- 阵亡或缺少贴图时，棋子会回退到现有的“羁绊色渐变底 + 首字”程序化头像，与旧版表现完全一致，不会报错。

## 音频与音效

背景乐与 UI 音效全部由 `tools/gen_audio.py` 程序化合成（纯标准库、零依赖、
固定种子可复现），产物在 `assets/audio/`。需要调整或重建资源：

```bash
python tools/gen_audio.py                               # 重建全部
python tools/gen_audio.py bgm_battle sfx_combine        # 只重建指定文件
```

播放行为：

- 部署/布阵阶段循环 `bgm_deploy`，点“开战”切 `bgm_battle`；回合结束播一次
  victory/defeat 小段，随后自动淡回部署曲。
- UI 音效覆盖买/卖/装备合成/穿装/刷新/锁定/升星（人口或三合一）/无效操作。
- 全局 `M` 键静音；无音频设备或资源缺失时自动降级为静音，不影响游戏运行。

## 项目结构

```
tft_2d/
├─ launcher.py             # 统一启动器：gui / play / sim 一条命令入口
├─ pyproject.toml          # 工程元数据：依赖 / 入口命令（pip install 后可用 tft2d 等）
├─ app.py / play.py        # 图形界面入口、命令行对局入口（也可被 launcher 调用）
├─ requirements.txt
├─ start_gui.bat / start_gui_8p.bat / run.bat   # Windows 快捷启动（1v1 / 8 人局 / 菜单）
├─ core/                   # ── 核心规则层：纯 Python，零第三方依赖 ──
│  ├─ game.py              #   单一真源驱动器：run_ai_ops / start_battle / finish_battle / advance_round
│  ├─ combat.py            #   战斗内核：行动序列、寻路/普攻/技能/事件回放
│  ├─ player.py            #   玩家：金币、血量、人口、升星、备战席
│  ├─ shop.py / pool.py    #   商店刷新 / 共享卡池抽牌
│  ├─ loader.py            #   加载 units/traits/items 数据
│  ├─ dataio.py            #   统一 JSON 读取缓存 + 数据自检 check_data()
│  ├─ traits.py / items.py #   羁绊统计、装备合成与效果
│  ├─ grid.py              #   棋盘网格常量与行带（8 行 / 双方各 4 行）
│  ├─ deploy.py            #   摆位：手动落点校验、自动补位
│  ├─ models.py / events.py#   战斗模型与事件定义
│  ├─ stats.py / rng.py    #   属性计算 / 可复现随机
│  └─ ai.py                #   AI 运营（买/卖/升星/穿装）
├─ render/                 # ── 图形界面层（pygame-ce）──
│  ├─ app.py               #   App 骨架：主循环、战斗回放状态机、draw() 编排
│  ├─ app_state.py         #   AppStateMixin：部署交互（视角/事件/自选台/拖拽/买卖）
│  ├─ app_draw.py          #   AppDrawMixin：全部绘制（HUD/棋盘/悬停层/特效/结算）
│  ├─ theme.py             #   布局/配色/字体主题（蜂窝棋盘尺寸在此推导）
│  ├─ board_view.py        #   六边形棋盘绘制与 (行列↔屏幕) 坐标换算
│  ├─ battle_view.py       #   实时战斗回放（平滑移动、弹道、血条、飘字）
│  ├─ shop_view.py         #   商店卡 / 备战席绘制
│  ├─ armory_view.py       #   成装自选台（F2）
│  ├─ item_view.py         #   装备栏
│  ├─ info.py              #   各类详情 tooltip 内容与绘制
│  ├─ assets.py            #   文字渲染与贴图缓存
│  ├─ audio.py             #   背景乐/UI 音效（无设备自动降级静音）
│  └─ widgets.py           #   按钮/进度条/面板等小部件
├─ data/                   # 全部数值配置（改平衡只需动这里）
│  ├─ units.json           #   50 枚棋子：费用、属性、羁绊、技能
│  ├─ traits.json          #   8 种羁绊的档位与加成
│  ├─ items.json           #   8 件基础装备 + 两两合成的高级装备与特效
│  ├─ pool.json            #   卡池构成
│  └─ level.json           #   人口经验曲线 + 各费用刷新概率
├─ assets/
│  ├─ audio/               #   程序化生成的 BGM / 音效 WAV（tools/gen_audio.py 重建）
│  └─ units/               #   可选：棋子头像贴图，按 <tid>.png 命名
├─ tests/                  # pytest 回归：数据完整性 / 驱动器确定性 / 内核不变量 / GUI 冒烟
└─ tools/
   ├─ simulate.py          # 战斗模拟：单局 / --bench 平衡 / --mirror 自检 / --fullgame 整局仿真 / --check 数据自检
   └─ gen_audio.py         # 纯标准库合成全部音频资源（见“音频与音效”）
```

## 数值与平衡调整

所有平衡参数都在 `data/` 下，按需修改即可，例如：

- 调棋子/技能：`data/units.json`
- 调羁绊档位：`data/traits.json`
- 调合成装备与特效：`data/items.json`
- 调人口/升级曲线与抽卡概率：`data/level.json`

改完后建议跑一轮 `--bench` 看胜率，再跑 `--mirror` 确认内核无方向性偏差。
