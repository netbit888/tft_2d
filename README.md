# tft_2d —— 类金铲铲自走棋模拟器（1v1 / 8 人局）

一个纯 Python + [pygame-ce](https://pygame-ce.github.io/) 实现的“金铲铲”风格自走棋。
核心规则逻辑（`core/`）零第三方依赖：既能开图形界面对战，也能纯命令行跑完整局，
还可以批量跑平衡统计与内核自检。

## 功能特性

- **50 枚棋子 / 8 种羁绊 / 8 件散件 → 36 件成装**：数值全部放在 `data/*.json`，
  调平衡不碰代码；`tools/dump_tables.py` 可一键导出《数值总览.md》。
- **共享卡池**：所有玩家的商店从同一个公共卡池抽牌，1v1 与 8 人局语义一致。
- **两种对战模式**：1v1（你 + 电脑）与 8 人局（你 + 7 电脑，两两配对、败者扣血淘汰）。
- **8 行蜂窝六边形棋盘（7×8）**：己方（蓝）在下 4 行、敌方（红）在上 4 行，
  行间错半格呈蜂窝排布；命中判定按六边形点包含计算。
- **棋子美术双轨制**：每个棋子默认有“羁绊色渐变底 + 单字”程序头像；
  放入 `assets/units/<tid>.png` 后自动切贴图。棋盘/备战席显示圆形头像，
  **商店卡展示整卡立绘**（贴图铺满卡面，无贴图自动回退，见“棋子贴图”一节）。
- **战前布阵**：拖拽摆位、自动补位（近战贴交火线、远程靠后）。
- **实时战斗回放**：寻路移动、普攻、技能、弹道、光环、飘字与血条动画。
- **确定性随机**：`--seed` 可完整复现同一局，便于调平衡与排查。
- **程序化音频**：纯标准库合成 BGM 与 UI 音效；无音频设备自动降级，`M` 键静音。
- **统一启动器与可安装工程**：`python launcher.py <子命令>` 一条命令访问全部玩法；
  `pip install -e .` 后可直接用 `tft2d` / `tft2d-gui` / `tft2d-play` / `tft2d-sim` 命令启动。

## 环境要求

- Python 3.11+
- 图形界面依赖：`pygame-ce>=2.5.0`

```bash
pip install -r requirements.txt      # 图形界面
pip install -e ".[dev]"              # （可选）装成命令 + pytest
```

> `core/` 战斗内核零第三方依赖：只装 pygame-ce 就能跑图形版；完全不装也能跑 `play.py` 命令行版。

## 快速开始

Windows 下直接双击，脚本会自动补装依赖：

| 文件 | 作用 |
| --- | --- |
| `start_gui.bat` | 图形界面 1v1 对战 |
| `start_gui_8p.bat` | 图形界面 8 人局 |
| `run.bat` | 菜单：图形界面 / 命令行对局 / 自动演示 / 平衡统计 / 内核自检 |

### 统一启动器

```bash
python launcher.py gui [--seed N] [--players 1|8] [--scale 1|2] [--no-log]   # 图形界面
python launcher.py play [--seed N] [--auto]                                  # 命令行 1v1（纯 core）
python launcher.py sim [--seed N] [--check|--bench N|--mirror N|--fullgame N] # 模拟工具
```

子命令参数原样转发给对应入口，因此 `python app.py`、`python play.py`、
`python tools/simulate.py` 单独调用效果相同（`play` 的别名是 `cli`）。

### 常用命令行

```bash
python app.py                    # 图形界面 1v1
python app.py --seed 7           # 指定种子，复现同一局
python app.py --players 8        # 图形界面 8 人局
python app.py --scale 2          # 高分屏 2x 缩放（不传则自动选择）
python play.py --seed 7 --auto   # 命令行：双方 AI 全自动跑完整局
```

## 图形界面操作

| 操作 | 效果 |
| --- | --- |
| 左键单击 商店卡 | 购买棋子（落入备战席）；卡上金色呼吸框 + “升 N 星”徽章 = 再买一张即可合成 |
| 左键按住拖动 | 拖拽摆位：备战席 ↔ 棋盘、棋盘内换位；悬停显示落点高亮 |
| 左键单击（原地松开）棋子 | 打开 / 切换该棋子详情；点空白处或 `ESC` 关闭 |
| 右键单击 棋子 / 备战席 | 卖出换金币 |
| 左键拖动 装备 → 棋子 | 穿装备；基础件拖到已带散件的棋子上可现场合成 |
| 拖两件基础装备到装备栏同格 | 合成成装；拖到装备栏空格则卸下棋子身上的装备 |
| 装备栏滚轮 | 背包不设上限，超过一页（3×4）时滚动翻页浏览 |
| `F2` | 打开 / 关闭成装自选台（部署阶段） |
| 点击 右侧血条（1v1）/ 战况面板行（8 人局） | 切换观察视角，查看某电脑的棋盘与羁绊 |
| 按钮：刷新 / 升级（可长按连升）/ 锁定 / 开战 | 运营操作 |
| `ESC` | 依次关闭：自选台 → 棋子详情 → 退出游戏 |
| `M` | 静音 / 恢复声音 |

商店卡在棋盘下方整排展示：**卡面 = 棋子形象 + 底部名字带**；卡片按费用套稀有度配色
（1 灰 / 2 绿 / 3 蓝 / 4 紫 / 5 金），已购卡片直接变灰显示“已购入”。

### 玩法节奏

每回合为「运营 → 布阵 → 开战」。3 张同名棋子自动升星（上限 3 星）；羁绊只统计上阵棋子。

- 刷新商店 2 金币；锁定后下回合不自动刷新。
- 升级固定 4 金币 / 4 经验，每回合自然 +2 经验，人口上限 9。
- 各等级抽卡费用概率见 `data/level.json` 的 `odds`（已对齐金铲铲现行节奏）。

## 棋子贴图

棋子美术遵循“**有图显图，缺图自动回退**”，无需任何配置：

- 资源路径：`assets/units/<tid>.png`，`<tid>` 与 `data/units.json` 中的 `id` 严格对应。
  仓库内置 1 费棋子 `shade`（影刃）作为示例贴图。
- **推荐格式**：方形 PNG、透明底、主体居中（头/肩大致落在画面竖向中线附近），
  主体约占画面宽 60% ~ 80%。绘制时按场景裁切，建议给头部上方留出约 10% 安全边距。
- 显示形态分两种：
  - **棋盘 / 备战席**：把贴图裁进圆形头像，外圈保留队伍光环、稀有度描边、星级金星与血条；
  - **商店卡**：整卡立绘——原图等比放大铺满整张卡（cover 居中裁切，不变形），
    底部压渐暗带放名字，费用徽章 / 升星提示叠在卡面之上。
- 缺少贴图时：棋盘侧回退“羁绊色渐变底 + 首字”程序头像；商店卡回退
  “稀有度纵向渐变底 + 放大程序头像”，两种形态都保持布局完整、不报错。
- 阵亡的棋子仍强制走灰色程序头像，语义不变。
- 注意贴图存在负缓存：运行中放入的图片需**重启游戏**才生效。

## 战斗内核模拟工具

```bash
# 校验 data/*.json 数据完整性（0 = 通过，供 CI/脚本门禁）
python launcher.py sim --check

# 单局战斗（默认双方各 4 枚随机镜像棋子）
python launcher.py sim

# 批量 N 场随机对局做平衡统计（蓝/红胜率 + 平均时长）
python launcher.py sim --bench 3000

# 批量 N 场镜像对称局做内核自检（两侧胜率差应落在 ±3% 内）
python launcher.py sim --mirror 3000

# 整局全自动仿真：8 人局全部 AI 运营，输出名次分布/节奏/环境
python launcher.py sim --fullgame 20 --players 8
```

## 数值总览

`tools/dump_tables.py` 把 `data/*.json` 的全部平衡数值（棋子属性、羁绊档位、
装备配方、人口经验曲线、抽卡概率、代码内平衡常量）导出成一张中文 Markdown 总览表，
供只读查阅，**请勿手改生成文件**：

```bash
python tools/dump_tables.py                    # 生成到项目根目录《数值总览.md》
python tools/dump_tables.py 任意路径/文件.md    # 指定输出路径
```

## 音频与音效

BGM 与 UI 音效全部由 `tools/gen_audio.py` 程序化合成（纯标准库、固定种子可复现），
产物在 `assets/audio/`：

```bash
python tools/gen_audio.py                 # 重建全部
python tools/gen_audio.py bgm_battle      # 只重建指定文件
```

播放行为：布阵阶段循环部署曲，点“开战”切战斗曲，回合结束播一次胜/负小段后淡回部署曲；
买 / 卖 / 合成 / 刷新 / 锁定 / 升星等操作有对应音效；`M` 键全局静音，
无音频设备或资源缺失时自动降级静音，不影响运行。

## 项目结构

```
tft_2d/
├─ launcher.py             # 统一启动器：gui / play / sim 一条命令入口
├─ app.py / play.py        # 图形界面入口、命令行对局入口（也可被 launcher 调用）
├─ pyproject.toml          # 工程元数据：依赖 / 入口命令（pip install 后可用 tft2d 等）
├─ requirements.txt
├─ start_gui.bat / start_gui_8p.bat / run.bat   # Windows 快捷启动（1v1 / 8 人局 / 菜单）
├─ core/                   # ── 核心规则层：纯 Python，零第三方依赖 ──
│  ├─ game.py              #   单一真源驱动器：run_ai_ops / start_battle / finish_battle / advance_round
│  ├─ combat.py            #   战斗内核：行动序列、寻路/普攻/技能/事件回放
│  ├─ player.py            #   玩家：金币、血量、人口、升星、备战席
│  ├─ shop.py / pool.py    #   商店刷新 / 共享卡池抽牌
│  ├─ loader.py / dataio.py#   数据加载 / 统一 JSON 缓存与数据自检 check_data()
│  ├─ traits.py / items.py #   羁绊统计、装备合成与效果
│  ├─ grid.py / deploy.py  #   棋盘网格行带（8 行）、摆位落点校验与自动补位
│  ├─ models.py / events.py#   战斗模型与事件定义
│  ├─ stats.py / rng.py    #   属性计算 / 可复现随机
│  └─ ai.py                #   AI 运营（买/卖/升星/穿装）
├─ render/                 # ── 图形界面层（pygame-ce）──
│  ├─ app.py               #   App 骨架：主循环、战斗回放状态机、draw() 编排
│  ├─ app_state.py         #   部署期交互：观察视角 / 事件分发 / 拖拽 / 买卖 / 自选台（F2）
│  ├─ app_draw.py          #   全部绘制编排：HUD/棋盘/悬停层/特效/结算/战况面板
│  ├─ theme.py             #   布局/配色/字体主题（蜂窝棋盘尺寸在此推导）
│  ├─ board_view.py        #   六边形棋盘与棋子头像绘制；贴图/程序头像双轨与商店卡立绘层
│  ├─ battle_view.py       #   实时战斗回放（平滑移动、弹道、血条、飘字）
│  ├─ shop_view.py         #   商店卡 / 备战席绘制
│  ├─ armory_view.py       #   成装自选台
│  ├─ item_view.py         #   装备栏
│  ├─ info.py              #   各类详情 tooltip 内容与绘制
│  ├─ assets.py            #   文字渲染与贴图缓存
│  ├─ audio.py             #   背景乐 / UI 音效（无设备自动降级静音）
│  └─ widgets.py           #   按钮 / 进度条 / 面板等小部件
├─ data/                   # 全部数值配置（改平衡只需动这里）
│  ├─ units.json           #   50 枚棋子：费用、属性、羁绊、技能
│  ├─ traits.json          #   8 种羁绊的档位与加成
│  ├─ items.json           #   8 件散件 + 36 件两两合成成装
│  ├─ pool.json            #   卡池构成
│  └─ level.json           #   9 级人口经验曲线 + 各费用刷新概率
├─ assets/
│  ├─ audio/               #   程序化生成的 BGM / 音效 WAV（tools/gen_audio.py 重建）
│  └─ units/               #   棋子贴图：按 <tid>.png 命名（内置 shade 示例）
├─ tests/                  # pytest 回归：数据完整性 / 驱动器确定性 / 内核不变量 / GUI 冒烟
└─ tools/
   ├─ simulate.py          # 战斗模拟：单局 / --bench / --mirror / --fullgame / --check
   ├─ dump_tables.py       # 数值总览生成器：data/*.json → 《数值总览.md》
   └─ gen_audio.py         # 纯标准库合成全部音频资源
```

## 数值与平衡调整

平衡参数都在 `data/` 下按需修改：

- 棋子与技能：`data/units.json`
- 羁绊档位：`data/traits.json`
- 装备与合成：`data/items.json`
- 人口 / 升级曲线与抽卡概率：`data/level.json`
- 散落在代码里的战斗常量（暴击倍率、利息、掉装备概率、装备特效系数等）：
  改代码并参考《数值总览.md》附录 C 定位

改完建议先 `python launcher.py sim --check` 校验数据，再跑 `--bench` 看胜率、
`--mirror` 确认内核无方向性偏差；需要把新数值做成可读清单时执行
`python tools/dump_tables.py` 重新生成总览。
