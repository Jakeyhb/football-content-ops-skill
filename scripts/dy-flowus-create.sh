#!/bin/bash
# dy-flowus-create.sh — 创建 FlowUs「抖音发布管理」数据库页面（带完整属性）
# 用法: ./dy-flowus-create.sh "标题" ["形态"] ["分类"] ["标签1,标签2"] ["配乐"] ["话题"] ["状态"]
#
# 示例:
#   ./dy-flowus-create.sh "U23亚运名单出炉！王钰栋领衔" "图文" "足球" "国足,亚运会" "热门榜" "#亚运会 #王钰栋"
#   ./dy-flowus-create.sh "曼城战术复盘" "视频" "足球" "曼城,战术,数据" "关键词选取" "#英超 #曼城" "审核中"

set -euo pipefail

DATABASE_ID="df0459bc-350a-437f-aaa2-9f9c69ea6446"

TITLE="${1:?用法: $0 \"标题\" [\"形态\"] [\"分类\"] [\"标签1,标签2\"] [\"配乐\"] [\"话题\"] [\"状态\"]}"
FORM="${2:-图文}"
CATEGORY="${3:-足球}"
TAGS_RAW="${4:-}"
MUSIC="${5:-无配乐}"
TOPICS="${6:-}"
STATUS="${7:-待发布}"

# 校验
case "$FORM" in 图文|视频|其他) ;; *) echo "错误: 形态必须是 图文/视频/其他，got: $FORM"; exit 1 ;; esac
case "$CATEGORY" in 足球|心理×足球|其他) ;; *) echo "错误: 分类必须是 足球/心理×足球/其他，got: $CATEGORY"; exit 1 ;; esac
case "$MUSIC" in 无配乐|热门榜|关键词选取|定制音乐) ;; *) echo "错误: 配乐必须是 无配乐/热门榜/关键词选取/定制音乐，got: $MUSIC"; exit 1 ;; esac
case "$STATUS" in 待发布|审核中|已发布|已删除) ;; *) echo "错误: 状态必须是 待发布/审核中/已发布/已删除，got: $STATUS"; exit 1 ;; esac

# 标签数组
TAGS_JSON=""
if [ -n "$TAGS_RAW" ]; then
  IFS=',' read -ra TAG_ARRAY <<< "$TAGS_RAW"
  for tag in "${TAG_ARRAY[@]}"; do
    tag=$(echo "$tag" | xargs)
    [ -z "$tag" ] && continue
    [ -n "$TAGS_JSON" ] && TAGS_JSON="$TAGS_JSON,"
    TAGS_JSON="${TAGS_JSON}{\"name\":\"${tag}\"}"
  done
fi

# 构建 JSON（url/number/date 由数据库自动填充，不显式设置）
JSON=$(cat <<EOJSON
{
  "icon": { "emoji": "📹", "type": "emoji" },
  "parent": { "database_id": "${DATABASE_ID}", "type": "database_id" },
  "properties": {
    "标题": {
      "title": [{ "text": { "content": "${TITLE}" }, "type": "text" }],
      "type": "title"
    },
    "形态": { "select": { "name": "${FORM}" }, "type": "select" },
    "分类": { "select": { "name": "${CATEGORY}" }, "type": "select" },
    "标签": { "multi_select": [${TAGS_JSON}], "type": "multi_select" },
    "配乐": { "select": { "name": "${MUSIC}" }, "type": "select" },
    "话题": { "rich_text": [{ "text": { "content": "${TOPICS}" }, "type": "text" }], "type": "rich_text" },
    "状态": { "select": { "name": "${STATUS}" }, "type": "select" },
    "笔记ID": { "rich_text": [{ "text": { "content": "" }, "type": "text" }], "type": "rich_text" }
  }
}
EOJSON
)

RESULT=$(echo "$JSON" | flowus --json page create --body /dev/stdin 2>&1)
EXIT_CODE=$?

PAGE_ID=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['id'])" 2>/dev/null)
PAGE_URL=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['url'])" 2>/dev/null)

if [ -n "$PAGE_ID" ]; then
  echo "✅ 页面创建成功"
  echo "   ID:  $PAGE_ID"
  echo "   URL: $PAGE_URL"
  echo "   标题: $TITLE"
  echo "   形态: $FORM | 分类: $CATEGORY | 配乐: $MUSIC | 状态: $STATUS"
else
  echo "❌ 创建失败: $RESULT"
  exit 1
fi
