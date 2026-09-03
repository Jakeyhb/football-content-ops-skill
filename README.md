# xhs-football-content-ops

把「足球观察员」账号的全流程运营方法打包成一个 **Agent Skill**：选题 → 结构 → 视觉（按队换色 + 固定 IP 小夜鹰 + 大字号海报卡）→ 发布（小红书 / 抖音 / FlowUs）→ 复盘。

配套一套**可复用资产**（图卡样式、各队主题、IP 小夜鹰、渲染/发布脚本、模板），让每篇产出统一、硬朗、数据不翻车。

## 怎么用
1. 看完 `SKILL.md` 里的全流程。
2. 需要做某一环时读对应 `references/*.md`。
3. 用 `scripts/*` 渲染图卡、写 FlowUs、发布。

## 目录
```
SKILL.md                 全流程主文档
README.md                这份
references/
  positioning.md         账号定位
  visual-system.md       视觉系统（按队换色/固定IP/封面/排版）
  ip-character.md        IP 小夜鹰固定 IP 系统
  publishing.md          发布规范（小红书/抖音/FlowUs）
  compliance.md          合规（xhs/dy 镜像）
assets/
  football-data.css      信息卡基础样式
  themes/*.css           各队主题（多特/曼城/阿森纳/国米/贝蒂斯/沙尔克…）
  ip/night-owl.svg       固定 IP 小夜鹰（SVG）
  ip/night-owl-transparent.png  透明版（角标/封面）
scripts/
  xhs-cover.py           渲染 HTML 图卡 → 1080×1440 PNG（含出图/质检）
  xhs-flowus-create.sh   小红书 FlowUs 建行
  dy-flowus-create.sh    抖音 FlowUs 建行
  douyin-post.py         抖音自动发布（备用，主发布走手动）
  publish.sh             一键：渲染 + 质检 + 发布
templates/
  cover-poster.html      封面（球场/实拍海报）母版
  info-card.html         信息卡（大字号）母版
```

## 依赖
- `xhs`（xiaohongshu-cli）· `flowus`（FlowUs CLI）
- 本机 Chrome / Playwright（`channel="chrome"`）
- MiniMax 可选（M3 规划 / image-01 出无字底图 + 叠字）

## License
MIT
