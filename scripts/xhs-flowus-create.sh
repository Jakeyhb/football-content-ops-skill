#!/bin/bash
# xhs-flowus-create.sh — 创建 Flowus 数据库页面（带完整属性）
# 用法: ./xhs-flowus-create.sh "标题" "分类" "标签1,标签2,标签3" ["状态"]
#
# 示例:
#   ./xhs-flowus-create.sh "曼城揭幕战！" "足球" "曼城,英超,社区盾"
#   ./xhs-flowus-create.sh "阿森纳战术" "足球" "阿森纳,英超" "草稿"

set -euo pipefail

DATABASE_ID="060f200e-f17e-48cb-a677-fc26efb07807"

TITLE="${1:?用法: $0 \"标题\" \"分类\" \"标签1,标签2\" [\"状态\"]}"
CATEGORY="${2:?用法: $0 \"标题\" \"分类\" \"标签1,标签2\" [\"状态\"]}"
TAGS_RAW="${3:?用法: $0 \"标题\" \"分类\" \"标签1,标签2\" [\"状态\"]}"
STATUS="${4:-草稿}"

# 验证分类
case "$CATEGORY" in
  足球|科技|生活|摄影|AI|其他) ;;
  *) echo "错误: 分类必须是 足球/科技/生活/摄影/AI/其他， got: $CATEGORY"; exit 1 ;;
esac

# 验证状态
case "$STATUS" in
  草稿|已发布|已删除|待审核) ;;
  *) echo "错误: 状态必须是 草稿/已发布/已删除/待审核， got: $STATUS"; exit 1 ;;
esac

# 构建标签 JSON 数组
TAGS_JSON=""
IFS=',' read -ra TAG_ARRAY <<< "$TAGS_RAW"
for tag in "${TAG_ARRAY[@]}"; do
  tag=$(echo "$tag" | xargs)  # trim whitespace
  [ -z "$tag" ] && continue
  [ -n "$TAGS_JSON" ] && TAGS_JSON="$TAGS_JSON,"
  TAGS_JSON="${TAGS_JSON}{\"name\":\"${tag}\"}"
done

# 构建完整 JSON
JSON=$(cat <<EOJSON
{
  "icon": { "emoji": "📝", "type": "emoji" },
  "parent": {
    "database_id": "${DATABASE_ID}",
    "type": "database_id"
  },
  "properties": {
    "标题": {
      "title": [{ "text": { "content": "${TITLE}" }, "type": "text" }],
      "type": "title"
    },
    "分类": {
      "select": { "name": "${CATEGORY}" },
      "type": "select"
    },
    "标签": {
      "multi_select": [${TAGS_JSON}],
      "type": "multi_select"
    },
    "状态": {
      "select": { "name": "${STATUS}" },
      "type": "select"
    },
    "笔记ID": {
      "rich_text": [{ "text": { "content": "" }, "type": "text" }],
      "type": "rich_text"
    }
  }
}
EOJSON
)

# 创建页面
RESULT=$(echo "$JSON" | flowus --json page create --body /dev/stdin 2>&1)
EXIT_CODE=$?

# 提取信息
PAGE_ID=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['id'])" 2>/dev/null)
PAGE_URL=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['url'])" 2>/dev/null)

if [ -n "$PAGE_ID" ]; then
  echo "✅ 页面创建成功"
  echo "   ID:  $PAGE_ID"
  echo "   URL: $PAGE_URL"
  echo "   标题: $TITLE"
  echo "   分类: $CATEGORY"
  echo "   标签: $TAGS_RAW"
  echo "   状态: $STATUS"
else
  echo "❌ 创建失败: $RESULT"
  exit 1
fi
