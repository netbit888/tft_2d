# tft_2d —— 类金铲铲自走棋模拟器（1v1 / 8 人局 / AI 观战 / Agent 对战）

一个纯 Python + [pygame-ce](https://pygame-ce.github.io/) 实现的"金铲铲"风格自走棋。
核心规则逻辑（`core/`）零第三方依赖，因此同一套内核支撑了四种完全不同的玩法入口：

| 你想…… | 用这个 |
| --- | --- |
| 自己上手玩 | `python app.py` 图形界面（1v1 / 8 人局） |
| 看 AI 互殴 | `python app_auto.py` AI 全自动观战 |
| 用命令行玩 | `python game_runner.py` 逐回合存档式运营 |
| 让 AI Agent 玩 | `python mcp_server.py` MCP 服务器（Agent 通过工具调用完整打一局） |
| 跑平衡 / 自检 | `python launcher.py sim` 批量模拟与数据校验 |

数值全部放在 `data/*.json`，调平衡不碰代码；`tools/` 下另有一键拉取官方
（Data Dragon / 金铲铲官网）棋子头像、羁绊图标、装备图标的素材工具。

## 功能特性

- **64 枚棋子 / 34 个官方羁绊 / 8 件散件 → 36 件成装**：数值全部放在 `data/*.json`，
  调平衡不碰代码；`tools/dump_tables.py` 可一键导出《数值总览.md》。
- **官方同步**：棋子白板属性与技能名对齐官方 S19；棋子归属与羁绊名称也同步官方
  （种族 + 职业）。**官方同名羁绊的效果绝大多数未实装**——战斗不提供属性加成，
  仅保留名称、归属与人数档位作为展示与运营参考（生成工具
  `tools/fetch_official_traits.py`、`tools/build_official_traits.py`、`tools/sync_official_stats.py`）。
- **唯一已实装的例外——顶级掠食者（471）**：携带单位「远古巨龙」按大型单位规则
  占用 **2 个人口（弈子栏位）**，并为【峡谷野怪】羁绊**合计提供 +2 计数**
  （单只即按 2 计，不再叠加自身），详见"玩法节奏"。
- **大型单位占人口**：普通棋子占 1 个人口，远古巨龙占 2；手动上阵、自动补位、
  升星回场、AI 运营与界面"人口 X/Y"展示全部按人口（弈子栏位）判断。
- **共享卡池**：所有玩家的商店从同一个公共卡池抽牌，1v1 与 8 人局语义一致。
- **两种对战规模**：1v1（你 + 电脑）与 8 人局（你 + 7 电脑，两两配对、败者扣血淘汰）。
- **8 行蜂窝六边形棋盘（7×8）+ 2.5D 透视**：己方（蓝）在下 4 行、敌方（红）在上 4 行，
  行间错半格呈蜂窝排布；棋盘按透视渲染——远端行缩小、近端行放大、横向向中轴收敛，
  底板是贴合"近宽远窄"的梯形平台；棋子带椭圆落地阴影立式呈现（billboard），
  尺寸随所在深度缩放。命中判定按六边形点包含计算，透视参数集中在 `theme.py`
  （`PERSP_FAR/NEAR`、`PIECE_LIFT`），拖拽/点选/战斗插值与投影自动一致。
- **星级数值模型**：生命/攻击随星翻倍成长，攻速按档位轻成长（×1.0/1.1/1.25），
  护甲/魔抗/法强不随星；羊刀、帽子等"按自身属性百分比强化"的特效统一
  只吃星级白板基础值，不与装备加成互相放大（详见"数值与平衡"）。
- **战斗内实时详情**：开战后左键点选任意棋子即可查看实时面板（攻速含羊刀叠层、
  与出手节奏同源），便于暂停逐帧观察装备特效与数值变化。
- **观察视角（选谁看谁）**：点右侧血条 / 8 人局战况面板行即可切换观察对象，
  棋盘、阵容羁绊面板、对手信息条都跟随该玩家——**选谁就只显示谁的阵容**，不把
  两人的羁绊并排显示。部署阶段看自己时不提前透露本回合对手。
- **羁绊图标 / 装备贴图 / 棋子美术双轨制**：一律"有图显图、缺图程序化回退"，
  官方素材可用 `tools/` 脚本一键下载（见"美术资源"）。
- **战前布阵**：拖拽摆位、自动补位（近战贴交火线、远程靠后；按人口容量补位）。
- **实时战斗回放**：寻路移动、普攻、技能、弹道、光环、飘字与血条动画；
  绘制按投影深度排序（近处棋子正确遮挡远处），事件流聚合的**伤害统计**
  （每枚棋子的伤害/承伤/治疗/施法，战斗中 `Tab` 开关，结算画面固定显示）。
- **经济可视化**：金币球上方实时显示下回合收入预估（固定收入 + 利息，
  口径与结算引擎一致），利息 > 0 时金色高亮，存钱收益一目了然。
- **确定性随机**：`--seed` 可完整复现同一局，便于调平衡与排查。
- **程序化音频**：纯标准库合成 BGM 与 UI 音效；无音频设备自动降级，`M` 键静音。
- **统一启动器与可安装工程**：`python launcher.py <子命令>` 一条命令访问全部玩法；
  `pip install -e .` 后可直接用 `tft2d` / `tft2d-gui` / `tft2d-play` / `tft2d-sim` 命令启动。

## 环境要求

- Python 3.11+
- 图形界面依赖：`pygame-ce>=2.5.0`
- MCP 服务器额外依赖：`mcp`（仅 `mcp_server.py` 需要）

```bash
pip install -r requirements.txt      # 图形界面
pip install mcp                      # （可选）MCP Agent 对战
pip install -e ".[dev]"              # （可选）装成命令 + pytest
```

> `core/` 战斗内核零第三方依赖：只装 pygame-ce 就能跑图形版；完全不装也能跑
> `play.py` / `game_runner.py` 命令行版。

## 快速开始

Windows 下直接双击，脚本会自动补装依赖：

| 文件 | 作用 |
| --- | --- |
| `start_gui.bat` | 进入游戏主页（开始游戏 = 8 人局） |
| `run.bat` | 菜单：图形界面 / 命令行对局 / 自动演示 / 平衡统计 / 内核自检 |

### 玩法一：图形界面（自己玩）

```bash
python app.py                    # 进入游戏主页，点“开始游戏”进 8 人局（默认全屏 + 2x 缩放）
python app.py --players 1        # 直达 1v1（跳过主页，脚本/测试兼容）
python app.py --players 8        # 直达 8 人局
python app.py --seed 7           # 指定种子，复现同一局
python app.py --scale 2          # 2x 缩放（默认即 2x；1=1280x800 小分辨率）
python app.py --windowed         # 退回普通窗口（默认全屏）
```

游戏主页（`render/home.py`）：居中大字标题 + 背景少量漂浮棋子，右下角一颗大号
**开始游戏**球（8 人局，金色呼吸描边），左下角贴边**退出游戏**球。对局结束
（终局结算 / ESC / 关窗）回到主页而非退出程序，主页 ESC 或退出球才真正关闭。
窗口图标取自 `assets/icon.ico`。

### 玩法二：AI 全自动观战

所有玩家（包括"你"的座位）都交给 AI 运营，自动开战、自动推进回合，
你只管看 AI 怎么买棋、升星、穿装、打架：

```bash
python app_auto.py               # 1v1 AI 观战
python app_auto.py --players 8   # 8 人局 AI 观战
python app_auto.py --seed 7      # 指定种子（可复现）
python app_auto.py --speed 0.5   # 结算停留秒数（默认 1.5，越小越快）
```

另有无界面的文字直播版 `python tools/live_blog.py`，逐回合在终端打印
AI 的买/卖/升星/装备操作与战斗日志（`--players 8`、`--seed N`、`--slow` 慢放）。

### 玩法三：命令行运营（game_runner.py）

逐命令运营一局，每步操作后把整个对局 pickle 到 `_game_state.pkl`，
适合脚本驱动或手动逐步推演：

```bash
python game_runner.py new --seed 7      # 开新局（也可 --players 8）
python game_runner.py state             # 查看当前完整局面（JSON）
python game_runner.py buy 0             # 买商店第 0 张卡
python game_runner.py sell board 0      # 卖场上/备战席第 0 个棋子
python game_runner.py refresh           # 刷商店（2 金）
python game_runner.py buyxp             # 买经验（4 金 +4 XP）
python game_runner.py move bench 0 board 3 2   # 备战席 0 → 棋盘 (col=3,row=2)
python game_runner.py equip 0 board 0   # 装备栏第 0 件穿给场上第 0 个棋子
python game_runner.py combine 0 1       # 合成装备栏第 0、1 件
python game_runner.py lock              # 锁定/解锁商店
python game_runner.py battle            # AI 运营 + 开战 + 结算（打印战斗日志）
python game_runner.py next              # 进入下一回合
```

阶段流转为 `deploy → battle → result → deploy …`，多数操作只在 deploy 阶段可用，
`state` 输出的 `phase` 字段随时可查。

### 玩法四：MCP Server —— 让 AI Agent 来玩

`mcp_server.py` 把整局游戏封装成一组 MCP 工具，AI Agent（Claude Desktop、
QwenWork 等任意 MCP 客户端）可以通过工具调用从零打完一局自走棋：

```bash
pip install mcp
python mcp_server.py             # stdio 方式启动，由 MCP 客户端拉起
```

提供的工具：`new_game` / `state` / `buy_unit` / `sell_unit` / `refresh` /
`buy_experience` / `move` / `equip` / `combine_items` / `toggle_lock` /
`start_battle` / `advance_round`。

客户端配置（以项目根 `.mcp.json` 为例，按本机 Python 路径修改）：

```json
{
  "mcpServers": {
    "tft2d": {
      "command": "python",
      "args": ["mcp_server.py"],
      "cwd": "<项目根目录>"
    }
  }
}
```

对局状态保存在服务器进程内存中（单局模式）；`state` 返回的 JSON 包含双方
HP/金币/等级、你方棋盘/备战席/装备栏、商店、羁绊与阶段，Agent 据此决策。

### 统一启动器

```bash
python launcher.py gui [--seed N] [--players 1|8] [--scale 1|2] [--no-log]   # 图形界面
python launcher.py play [--seed N] [--auto]                                  # 命令行 1v1（纯 core）
python launcher.py sim [--seed N] [--check|--bench N|--mirror N|--fullgame N] # 模拟工具
```

子命令参数原样转发给对应入口，因此 `python app.py`、`python play.py`、
`python tools/simulate.py` 单独调用效果相同（`play` 的别名是 `cli`）。

## 图形界面操作

| 操作 | 效果 |
| --- | --- |
| 左键单击 右下金币球 | 打开 / 关闭商店浮层（球面显示当前金币） |
| 商店浮层内 左键单击 卡 | 购买棋子（落入备战席）；卡上金色呼吸框 + "升 N 星"徽章 = 再买一张即可合成 |
| 商店浮层内 刷新 / 锁定按钮 | 刷新一次 2 金；锁定后下回合不自动刷新 |
| 左键单击 左下经验球 | 花 4 金买 4 经验；**按住不放可长按连升**（球面显示等级与经验进度） |
| 左键按住拖动 | 拖拽摆位：备战席 ↔ 棋盘、棋盘内换位；悬停显示落点高亮 |
| 左键单击（原地松开）棋子 | 部署期打开 / 切换该棋子详情；点空白处或 `ESC` 关闭 |
| 左键单击 战斗中的棋子 | 打开该单位实时详情（数值随战斗刷新，含羊刀叠层实时攻速） |
| 右键单击 棋子 / 备战席 | 卖出换金币 |
| 拖到最底部空条（卖出区） | 同上，卖出并提示可得金币 |
| 左键拖动 装备 → 棋子 | 穿装备；基础件拖到已带散件的棋子上可现场合成 |
| 左键单击 左侧页签（羁绊 / 装备） | 切换左侧内容区：羁绊页看阵容羁绊详情，装备页看完整装备栏（默认羁绊页） |
| 拖两件基础装备到左侧装备页同格 | 合成成装；拖到装备栏空格则卸下棋子身上的装备 |
| 装备页滚轮 | 背包不设上限，超过一页（3×4）时滚动翻页浏览 |
| `F2` / `F3` | 打开 / 关闭成装自选台 / 棋子自选栏（部署阶段；与商店浮层互斥） |
| `Tab`（战斗中） | 开关伤害统计面板：蓝/红两栏按伤害降序列出每枚棋子的伤害/承伤/治疗/施法 |
| 点击 右侧血条 / 战况面板行 | 切换观察视角：选中谁就查看谁的棋盘与羁绊；左侧羁绊页只显示该玩家（默认自己）。未开战且看自己时不显示本回合对手信息 |
| 按钮：开战 | 进入战斗回放 |
| `ESC` | 战斗中：收起战斗单位详情（不退出）；部署期：自选台 → 自选栏 → 商店浮层 → 棋子详情 → **退回主页** |
| `M` | 静音 / 恢复声音 |

商店已从棋盘下方收进**金币球浮层**：点右下金币球弹出遮罩面板，内含整排商店卡 +
刷新概率行 + 刷新 / 锁定 / 关闭 ✕，点面板外或 `ESC` 即关。**卡面 = 棋子形象 + 底部
名字带**；卡片按费用套稀有度配色（1 灰 / 2 绿 / 3 蓝 / 4 紫 / 5 金），已购卡片直接变灰
显示"已购入"。商店搬走后备战席下方留出的空条即**卖出区**（拖棋子到此卖出）。
备战席上方随时显示**当前上场人口 `人口 X/Y`**：普通棋子占 1，远古巨龙等大型单位占 2。

### 战斗内实时详情

开战动画进行中，左键单击己方或敌方存活棋子即会在其旁弹出实时详情面板，并给该棋子
套一圈金色高亮：

- 当前生命 / 法力、**实时攻速**（按羊刀叠层实时结算，封顶全局 5 次/秒，与出手节奏同一公式）、法强；
- 护甲 / 魔抗 / 射程 / 暴击 / 移速；
- 携带装备与各装备特效的文字说明（同件/同类只列一次）、当前羊刀叠层百分比；
- 技能威力（按当前面板法强折算）。

再次点击同一棋子或点空白处关闭；战斗中按 `ESC` 也只会收起该详情，不会退出对局。
配合暂停逐帧观察，可以直观核验"特效吃基础值"等数值模型。

## 玩法节奏

每回合为「运营 → 布阵 → 开战」。3 张同名棋子自动升星（上限 3 星）；羁绊只统计上阵棋子。

- **人口上限 10**：升级固定 4 金币 / 4 经验，每回合自然 +2 经验；经验曲线对齐金铲铲
  现行节奏并延伸到 10 人口（升到 9 级累计约 212 经验、10 级约 312 经验）。
- **大型单位占多个人口**：普通棋子占 1 个弈子栏位，「远古巨龙」（顶级掠食者 471）
  占 **2 个弈子栏位**。手动上阵、自动补位、升星回场与 AI 上阵都按人口判断，
  1 级（上限 1 人口）放不下远古巨龙，升到 2 级才能上场。
- **羁绊计数按"合计贡献"口径**：普通棋子每个羁绊 +1；远古巨龙对自身羁绊分别计
  「顶级掠食者 1」「峡谷野怪 2」（`data/units.json` 的 `trait_extra: {"454": 2}`，
  +2 即其总贡献，单只不再叠自身）。该口径同时作用于羁绊面板、图鉴、AI 运营评估与战斗统计。
- 刷新商店 2 金币；锁定后下回合不自动刷新。
- 各等级抽卡费用概率见 `data/level.json` 的 `odds`（10 级各档已补齐，5 费最高 35%）。

官方羁绊绝大多数不产生战斗加成（见"数值与平衡"）；唯一例外「顶级掠食者」实装的是
"占人口 + 为【峡谷野怪】合计 +2 计数"的单位机制，同样不改动战斗属性。

## 美术资源

三类资源（棋子 / 羁绊 / 装备）都遵循"**有图显图，缺图自动回退**"，无需任何配置；
官方素材不进版本库，拉取仓库后按需运行下列脚本一键补齐。

### 棋子贴图

- 资源路径：`assets/units/<tid>.png`，`<tid>` 与 `data/units.json` 中的 `id` 严格对应
  （当前为官方 `s18_*` 素材 id）。
- **一键获取（金铲铲官方 CDN，推荐）**：`python tools/fetch_s18_avatars.py`
  按 `tools/tft_s18_heads.json` 的映射下载 S18 官方头像（96×96）到 `assets/units/`，
  并在根目录生成《棋子头像总览.png》核对图。
- **备选（Riot Data Dragon）**：`python tools/fetch_unit_portraits.py`
  按棋子中文名与 ddragon zh_CN 冠军表精确匹配下载；野怪/原创棋子不在冠军表中，
  自动跳过并打印，游戏内继续走程序化回退。
- **推荐格式**：方形 PNG、透明底、主体居中（头/肩大致落在画面竖向中线附近），
  主体约占画面宽 60% ~ 80%，给头部上方留约 10% 安全边距。
- 显示形态分两种：
  - **棋盘 / 备战席**：贴图裁进圆形头像，外圈保留队伍光环、稀有度描边、星级金星与血条；
  - **商店卡**：整卡立绘——原图等比放大铺满整张卡（cover 居中裁切，不变形），
    底部压渐暗带放名字，费用徽章 / 升星提示叠在卡面之上。
- 缺少贴图时：棋盘侧回退"羁绊色渐变底 + 首字"程序头像；商店卡回退
  "稀有度纵向渐变底 + 放大程序头像"。阵亡的棋子仍强制灰色程序头像。
- 注意负缓存：运行中放入的图片需**重启游戏**才生效。

### 羁绊图标

`assets/traits/<羁绊id>.png`（官方 96×96 六边形图标），
`python tools/fetch_trait_icons.py` 一键下载；缺图时程序化六边形回退。

### 装备贴图

按类别分目录存放，文件名 = 装备 id（与 `data/items.json` 严格对应）：

- 散件：`assets/items/base/<id>.png`，如 `base/bow.png`（反曲之弓）
- 成装：`assets/items/combine/<a>+<b>.png`，如 `combine/bow+wand.png`（羊刀）
- 特殊工具：`assets/items/special/gold_remover.png`（金制拆卸器）

格式优先 PNG（透明底最佳），也自动探测 `.webp` / `.jpg`；128×128 起，方形、
主体居中、占画面 60% ~ 80%。**一键获取**：`python tools/fetch_item_icons.py`
自动比对多个 Data Dragon 版本、下载全套官方图标并按目录落盘（统一 128×128）；
个别国服名在官方 CDN 查不到的装备会打印 `[未匹配]`，可自备同规格 PNG 补齐。

同一份贴图按需缩放用于：装备栏格子 / 自选台 / 拖拽跟手图标（40px 大图标），
以及棋子脚下的装备徽章（12px 小图标）。缺图时大图标回退"稀有度底色 + 装备名首字"，
小徽章回退金色（成装）/ 灰色菱形。同样有负缓存，放入后需重启生效。

列出全部装备 id（照着命名即可）：

```bash
python -c "from core.items import load_items as L, special_item_ids as S; [print(i) for i in list(L()['base']) + list(L()['combine']) + S()]"
```

## 数值与平衡

### 星级成长与面板构成

属性计算统一入口为 `core/stats.py` 的 `compute_stats()`：

- **升星翻倍成长**：生命 / 攻击按 `STAR_MULTIPLIER = {1: 1.0, 2: 1.8, 3: 3.24}` 成长
  （1 星为基准）。
- **攻速轻成长档位**：`AS_STAR_MULTIPLIER = {1: 1.0, 2: 1.1, 3: 1.25}`，
  避免高攻速单位升星后出手频率失控，也保住低攻速重装升星手感。
- **护甲 / 魔抗 / 法强不随星级成长**。
- 面板构成 = **星级白板基础值**（模板 × 星级档位）+ 装备加值；装备 `%` 加成
  从"白板基础值"出发。（官方羁绊绝大多数无战斗加成，故不产生羁绊属性收益；
  唯一实装的「顶级掠食者」也只是占人口 / 提供羁绊计数，不改变面板。）
- **全局攻速上限 `AS_CAP = 5.0` 次/秒**：装备、羊刀叠层等一切来源的实际攻速
  统一封顶（`core.combat.effective_attack_speed()`，渲染层展示同一函数保证显示与出手一致）。

### 装备特效吃"白板基础值"

羊刀 / 帽子这类"按自身属性百分比强化"的特效，加成基数取**星级白板基础值**
（`base_max_hp / base_ad / base_ap / base_attack_speed`，不含装备加成），
不与装备、大天使叠层等其它来源互相放大。每件装备挂载哪种特效由
`data/items.json` 的 `effect` 字段决定，引擎的全部特效实现与系数见 `core/combat.py` 顶部：

- **羊刀（`ramping_as`）**：每把每次命中叠 **+6% 基础攻速**（多把同击叠得更快），
  加性与面板攻速% 叠加；无叠层上限，由 `AS_CAP` 兜底。
- **灭世者的死亡之帽（`ap_amp`）**：施法时**仅基础法强 +35%**，不吃装备 /
  大天使叠层的法强；基础法强为 0 的物理棋子佩戴无效。
- 攻速光环类削减（`slow_aura`）按"先封顶、后乘性"作用于实际攻速，与羊刀互不干扰。

这样一星与三星、裸装与神装之间的差距被控制在单一乘区内，数值更可控、更好调。

### 调节入口

平衡参数集中在 `data/` 下按需修改；代码内常量见 `core/models.py` 与 `core/combat.py`：

- 棋子与技能：`data/units.json`（大型单位加 `"slots": 2`；对某羁绊"合计 +N 计数"
  写 `"trait_extra": {"<羁绊id>": N}`）
- 羁绊档位：`data/traits.json`（`implemented: true` 表示该羁绊已有实际效果/机制）
- 装备与合成：`data/items.json`
- 人口 / 升级曲线与抽卡概率：`data/level.json`
- 星级倍率 / 攻速档位 / 全局攻速上限 / 等级上限：`core/models.py` 与 `core/player.py`
- 特效系数（羊刀步进、帽子、大天使、巨人杀手、复活、冰心减速等）：`core/combat.py`

改完建议先 `python launcher.py sim --check` 校验数据，再跑 `--bench` 看胜率、
`--mirror` 确认内核无方向性偏差；需要把新数值做成可读清单时执行
`python tools/dump_tables.py` 重新生成总览。数值语义的改动请同步补充
`tests/test_stats_model.py`、`tests/test_rules.py` 之类回归测试。

### 官方数据同步工具

- `tools/sync_official_stats.py`：从金铲铲官网数据链拉取官方 1 星白板属性与技能名，
  写回 `data/units.json`（`--fields` 可裁剪同步范围）。
- `tools/fetch_official_traits.py`：拉取官方羁绊配置快照到 `tools/_jcc_raw/`。
- `tools/build_official_traits.py`：基于快照把棋子归属改为官方 S19 体系并重写
  `data/traits.json`（官方羁绊效果一律标注未实装）。

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

播放行为：布阵阶段循环部署曲，点"开战"切战斗曲，回合结束播一次胜/负小段后淡回部署曲；
买 / 卖 / 合成 / 刷新 / 锁定 / 升星等操作有对应音效；`M` 键全局静音，
无音频设备或资源缺失时自动降级静音，不影响运行。

## 项目结构

```
tft_2d/
├─ launcher.py             # 统一启动器：gui / play / sim 一条命令入口
├─ app.py                  # 图形界面入口：无参数进游戏主页（选模式），--players 直达
├─ app_auto.py             # AI 全自动观战：所有玩家交给 AI，自动推进回合；也被主页复用
├─ play.py                 # 命令行对局入口（纯 core）
├─ game_runner.py          # 命令行运营运行器：逐命令操作 + _game_state.pkl 存档
├─ mcp_server.py           # MCP Server：把整局游戏暴露成工具，供 AI Agent 游玩
├─ pyproject.toml          # 工程元数据：依赖 / 入口命令（pip install 后可用 tft2d 等）
├─ requirements.txt
├─ start_gui.bat / run.bat     # Windows 快捷启动（主页 / 菜单）
├─ core/                   # ── 核心规则层：纯 Python，零第三方依赖 ──
│  ├─ game.py              #   单一真源驱动器：run_ai_ops / start_battle / finish_battle / advance_round
│  ├─ combat.py            #   战斗内核：行动序列、寻路/普攻/技能/事件回放、特效结算与 AS_CAP
│  ├─ player.py            #   玩家：金币、血量、人口（大型单位占多栏位）、升星、备战席
│  ├─ shop.py / pool.py    #   商店刷新 / 共享卡池抽牌
│  ├─ loader.py / dataio.py#   数据加载（写入星级白板基础值）/ 统一 JSON 缓存与数据自检
│  ├─ traits.py / items.py #   羁绊统计（含 trait_extra 合计贡献口径）、装备合成与效果
│  ├─ grid.py / deploy.py  #   棋盘网格行带（8 行）、摆位落点校验与按人口自动补位
│  ├─ models.py / events.py#   战斗模型（星级倍率 / 攻速档位 / AS_CAP / slots 等常量）与事件定义
│  ├─ stats.py / rng.py    #   属性计算（compute_stats）/ 可复现随机
│  └─ ai.py                #   AI 运营（买/卖/升星/穿装，按人口上阵）
├─ render/                 # ── 图形界面层（pygame-ce）──
│  ├─ app.py               #   App 骨架：主循环、战斗回放状态机、draw() 编排（结束回主页不退出）
│  ├─ home.py              #   游戏主页 HomeView：标题 / 开始球 / 退出球 / 漂浮棋子背景
│  ├─ app_state.py         #   部署期交互：观察视角 / 事件分发 / 拖拽 / 买卖 / 自选台（F2）
│  ├─ app_draw.py          #   全部绘制编排：HUD/棋盘/悬停层/特效/结算/战况面板/阵容羁绊
│  ├─ theme.py             #   布局/配色/字体主题（蜂窝棋盘尺寸与 2.5D 透视参数在此推导）
│  ├─ board_view.py        #   六边形棋盘（透视投影/梯形底板）与棋子立式绘制；贴图/程序头像双轨与商店卡立绘层
│  ├─ battle_view.py       #   实时战斗回放 + 点选棋子查看实时详情 + 事件流伤害统计
│  ├─ recap.py             #   伤害统计面板绘制（蓝/红两栏，伤害/承伤/治疗/施法）
│  ├─ shop_view.py         #   商店卡 / 备战席绘制 + 商店浮层（面板/概率/刷新/锁定）
│  ├─ hud_view.py          #   左下经验球 / 右下金币球（含命中检测）
│  ├─ armory_view.py       #   成装自选台
│  ├─ side_view.py         #   左侧页签栏（羁绊 / 装备）绘制与命中
│  ├─ trait_art.py         #   羁绊六边形图标：assets/traits/ 加载/绘制，缺图程序化回退
│  ├─ item_view.py / item_art.py  #   装备栏 / 装备贴图（assets/items/{base,combine,special}/）
│  ├─ info.py              #   详情 tooltip：部署期 unit_records / 战斗期实时数值
│  ├─ assets.py            #   文字渲染与贴图缓存
│  ├─ audio.py             #   背景乐 / UI 音效（无设备自动降级静音）
│  └─ widgets.py           #   按钮 / 进度条 / 面板等小部件
├─ data/                   # 全部数值配置（改平衡只需动这里）
│  ├─ units.json           #   64 枚棋子：费用、白板属性、官方羁绊 id、技能（大型单位含 slots / trait_extra）
│  ├─ traits.json          #   34 个官方羁绊：名称/档位/描述（除顶级掠食者等实装项外效果未实现）
│  ├─ items.json           #   8 件散件 + 36 件两两合成成装
│  ├─ pool.json            #   卡池构成
│  └─ level.json           #   10 级人口经验曲线 + 各费用刷新概率
├─ assets/
│  ├─ audio/               #   程序化生成的 BGM / 音效 WAV（tools/gen_audio.py 重建）
│  ├─ items/               #   装备贴图：base/ 散件、combine/ 成装、special/ 特殊工具
│  ├─ traits/              #   羁绊图标：<羁绊id>.png
│  ├─ units/               #   棋子贴图：<tid>.png（tools/fetch_s18_avatars.py 下载官方头像）
│  └─ icon.ico             #   窗口图标（主页与对局窗口共用）
├─ tests/                  # pytest 回归：数据完整性 / 驱动器确定性 / 内核不变量 /
│                          #   数值模型 / 人口与羁绊规则 / 装备贴图 / GUI 冒烟
└─ tools/
   ├─ simulate.py          # 战斗模拟：单局 / --bench / --mirror / --fullgame / --check
   ├─ dump_tables.py       # 数值总览生成器：data/*.json → 《数值总览.md》
   ├─ live_blog.py         # AI 对战文字直播：逐回合打印运营与战斗日志
   ├─ fetch_s18_avatars.py # 金铲铲 S18 官方头像 → assets/units/<tid>.png
   ├─ fetch_unit_portraits.py # Riot Data Dragon 头像（按中文名匹配）
   ├─ fetch_trait_icons.py # 下载官方羁绊图标 → assets/traits/
   ├─ fetch_item_icons.py  # 下载全套 TFT 官方装备图标 → assets/items/{base,combine,special}/
   ├─ sync_official_stats.py     # 同步官方白板属性/技能名 → data/units.json
   ├─ fetch_official_traits.py   # 拉取官方羁绊快照 → tools/_jcc_raw/
   ├─ build_official_traits.py   # 重建官方 S19 羁绊体系 → data/traits.json
   ├─ tft_s18_heads.json   # 单位 id → S18 头像文件名映射
   └─ gen_audio.py         # 纯标准库合成全部音频资源
```

## 回归测试

```bash
python -m pytest tests/    # 或：python -m pytest（pyproject 已配置 tests 目录）
```

覆盖：`data/*.json` 完整性（`--check` 同源校验）、驱动器可复现确定性、战斗内核不变量、
星级成长与"特效吃白板基础值"的数值模型（`tests/test_stats_model.py`）、
人口规则（10 级曲线、大型单位占人口与羁绊合计计数，`tests/test_rules.py`）、
装备贴图加载与缺图回退（`tests/test_item_art.py`）、GUI 冒烟。
