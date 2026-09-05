---
name: football-content-ops
description: >-
  End-to-end content-operation methodology for a Chinese football-content account
  (@bawbaw 足球观察员), unified across Xiaohongshu · Douyin · FlowUs. From topic to
  verified content, card design, per-team color theming, a fixed IP mascot, and
  publish/record. Use when 发一篇, 做图卡, 按队换色, 做封面, 发小红书, 发抖音, 记 FlowUs, or 复盘.
---

# 足球观察员 · 内容运营全流程 Skill

一套把「足球快讯/赛前预告」从选题到发布的**统一方法论**（小红书 + 抖音 + FlowUs 一套通吃）+ 可复用资产。目标是：**内容硬朗、主页统一、数据不翻车、发布零踩坑**。

## 一句话
选题 → 结构 → 视觉（按队换色 + 固定 IP 小夜鹰 + 大字号海报卡）→ 发布（小红书 / 抖音 / FlowUs）→ 复盘。

---

## 0. 账号定位（先读 `references/positioning.md`）
- 号：足球观察员 · 夜场快讯 × 数据/战术 × (心理×足球)。
- 受众：18–35 英超/欧洲球迷，熬夜看球、转会控。男向、硬朗。
- 形态：70% 足球快讯，30% 心理×足球（挂回球迷场景）。
- 视觉：硬朗、干净、有立场；别可爱/别花哨/别粉色。

## 1. 标题（≤20 字）
- 公式：**悬念 + ≥2 张力**（人名 / 数字 / 大比分 / 关键词），如：
  - `皇马客战贝蒂斯！四连胜在望`（13）
  - `曼城vs考文垂！哈兰德冲三连胜`（14）
- 人名/球队用**标准译名**（如 伊纳西奥、居莱尔——搜 `xhs topics` 确认话题存在再定译名）。

## 2. 正文（要点，见 `references/publishing.md`）
- **精简**：几行说清（钩子 → 关键数据 → 一句看点 → #话题）。
- **不要用 Markdown**：`**加粗**` 在小红书会原样显示 → 全部去掉 `**`。
- **不要写评论/选项**：`你觉得...？评论区聊`、`A/B/C 投票` 一律去掉（纯信息）。
- **中立平衡**：**双方都要报道、不偏一队**；强弱悬殊/争冠战也要给主队/弱队同等分量，别把一方写成"背景板/陪衬"（例：`蓉城冲冠 vs 河南主场`、`巴萨领跑 vs 主场反击`）。视角可站"冠军/焦点"那方，但措辞与卡内容两方都到。
- 话题 ≤10 个（小红书上限），发布前用 `xhs topics` 核对存在。
- 事实核验：发前 `web_search` 对照（比分、球员、时间、场馆），引用来源。

## 3. 图卡（football-4，见 `references/visual-system.md`）
| 页 | 角色 | 内容 |
|----|------|------|
| 01 封面 | 钩子 | 球场/球员实拍海报 + 大字 + 信息（**不用 VS 圆章**） |
| 02 THE DEAL | 数字/信息 | 对阵 / 时间 / 双方近况 / 看点 |
| 03 MY TAKE | 立场 | 观点 + 关键对位 |
| 04 KEY MATCHUP | 看点 | 明星对位 / 悬念 |

> 两条线：① 比赛前瞻（硬朗信息卡，本小节）；② **战术分析/数据复盘**（tiny type 编辑风 + 足球图型 + 赢家主色，见 `references/tactical-analysis.md`，模板 `templates/tactical-card.html`）。战术线必须**先 web_search 核验数据**（比分/进球者/射门/xG），拿不到坐标/分钟时标注"示意"。
- 规格 **1080×1440**，`python3 scripts/xhs-cover.py render --html … --out …` 渲染。
- **大字号**：标题 ~112px、小标题 ~50px、正文 ~44px、标签 ~36px（比默认大）。
- **图卡里不要写比分/数据**（容易错、难改）——把数字都放进正文/避免，或只写定性词。这样数据错只改文案、不动图。
- 标题要**在语义处换行**（别把词拆开，如"安东尼"不要变"安东/尼"）——用 `<br>` 断行。

## 4. 视觉系统（`references/visual-system.md`）
### 4.1 硬朗足球数据风
- 中性网格底 + 近黑深蓝字 + 加粗黑体（PingFang/Noto Heavy），干净、男向、不花哨。
- 基础样式：`assets/football-data.css`。

### 4.2 按队换色（CSS 变量覆盖）
- 每队一套主题（**改 `--blue/--green/--ink` 三个变量**，布局不变）：
  `assets/themes/*.css`（多特 black/yellow、曼城 sky-blue/gold、阿森纳 red/gold、国米 blue/black、贝蒂斯 gold/navy、沙尔克 blue/white…）。
- 做法：`cp football-data.css themes/<team>.css` 后改 3 个变量。

### 4.3 固定 IP 小夜鹰（`assets/ip/night-owl.svg` + `-transparent.png`）
- 一只抱足球的夜鹰观察员：**人物恒定，场景/道具可变**（抱球/哨子/球场/战术板/奖杯/数据/庆祝变体）。
- 作为**每页右下角固定角标**（透明底，不挡内容），封面也放一个。
- 原则：**先锁定 IP 身份，再进不同场景** → 主页不散。详见 `references/ip-character.md`。

### 4.4 封面规范
- 用**球场/球员实拍**铺满 + 大字（参考图 2 海报风），**不要红蓝分屏 + VS 圆章**（丑）。
- 左侧压暗保证文字可读；顶部放 `COMPETITION · 联赛 · 第N轮 · 日期`；底部品牌 BAWBAW + 向左滑。
- 有球员图就双人/单人实拍；没给图就用球场实景。

## 5. 发布（`references/publishing.md`）
### 小红书
```bash
xhs post --title "$(cat title.md)" --body "$(cat body.md)" \
  --images 图集-1.png 图集-2.png 图集-3.png 图集-4.png \
  --topic 话题1 --topic 话题2 ...
```
- `--images` 每个文件一个参数；`--topic` 最多 10，先核对存在。
- 发布后**不要自动自评**（用户偏好"不用评论"）。

### 抖音
- 默认**手动发**（创作者中心/app）+ FlowUs 记录（自动发布脚本 `scripts/douyin-post.py` 备用）。
- 图卡同套（大字号信息卡）；标题 ≤30；简介精简（见 `references/publishing.md`）。
- `scripts/dy-flowus-create.sh` 写入 FlowUs「抖音发布管理」库（状态=待发布）。

### FlowUs 库
- 小红书：`scripts/xhs-flowus-create.sh`
- 抖音：`scripts/dy-flowus-create.sh`
- 字段含 标题/形态/分类/标签/配乐/话题/状态/链接/数据时长等。

## 6. 合规（`references/compliance.md`）
- 无极限词（第一/唯一/最强/顶级/最…）、无「点赞收藏关注」、无竞品（抖音提小红书/小红书提抖音皆忌）、无迷信。
- 无 `**`；正文无评论引导。
- xhs 与 dy 规则**镜像**：xhs 禁提抖音，dy 禁提小红书。

## 7. 复盘
- 只调封面 / 互动 / 选题配比 / 时效；结论写回定位卡和选题库。

## 资产清单
| 路径 | 用途 |
|------|------|
| `assets/football-data.css` | 信息卡基础样式（硬朗数据风） |
| `assets/themes/*.css` | 各队主题（按队换色） |
| `assets/ip/night-owl.svg` / `-transparent.png` | 固定 IP 小夜鹰（角标/封面） |
| `scripts/xhs-cover.py` | 渲染 HTML 图卡 → 1080×1440 PNG + 出图 |
| `scripts/xhs-flowus-create.sh` / `dy-flowus-create.sh` | 写入 FlowUs 库 |
| `scripts/douyin-post.py` | 抖音自动发布（备用） |
| `scripts/publish.sh` | 一键：渲染 + 质检 + 发布 |
| `templates/cover-poster.html` / `info-card.html` | 封面 / 信息卡母版 |

> 授权：需 `xhs`（xiaohongshu-cli）、`flowus`、本机 Chrome / Playwright（channel=chrome）、MiniMax 可选（M3/出图）。
