#!/bin/bash
# publish.sh — 渲染一套图卡 + 溢出质检，并输出小红书画布命令
# 用法: ./scripts/publish.sh "doc/主题" [--post]
#   --post  额外执行 xhs post（需 主题/title.md、body.md、可选 主题/.topics.txt）
set -euo pipefail
DIR="${1:?用法: $0 <doc/主题目录> [--post]}"
POST=0; [ "${2:-}" = "--post" ] && POST=1
ROOT="$(cd "$(dirname "$0")/.." && pwd)"   # 本仓库根（= 运营工作区）
LAYOUT="$DIR/图集-layout"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# 1) 渲染 0X.html -> 图集-X.png
imgs=()
for html in "$LAYOUT"/0*.html; do
  [ -f "$html" ] || continue
  base=$(basename "$html" .html)
  n=$(echo "$base" | sed 's/^0//')
  python3 "$ROOT/scripts/xhs-cover.py" render --html "$html" --out "$DIR/图集-$n.png"
  imgs+=("$DIR/图集-$n.png")
done
echo "✓ 渲染 ${#imgs[@]} 张图卡"

# 2) 溢出质检（Chrome headless）
if command -v "$CHROME" >/dev/null 2>&1; then
  for i in "${imgs[@]}"; do :; done
  for html in "$LAYOUT"/0*.html; do
    [ -f "$html" ] || continue
    tmp="$html.q.html"
    python3 - "$html" "$tmp" <<'PY'
import sys,re,pathlib
html,out=sys.argv[1],sys.argv[2]
h=pathlib.Path(html).read_text(encoding="utf-8")
q="""<script>window.addEventListener('load',()=>{const W=1080,H=1440,skip=['artboard','frame','scrim','photo','bandL','bandR'];const bad=[];document.querySelectorAll('body *').forEach(el=>{const c=(el.className&&el.className.baseVal===undefined)?String(el.className):'';if(skip.some(s=>c.includes(s)))return;const r=el.getBoundingClientRect();if(r.width===0&&r.height===0)return;if(r.bottom>H-8||r.right>W-8||r.top<-8||r.left<-8)bad.push(el.tagName+'['+c+']');});const p=document.createElement('pre');p.textContent='OVERFLOW|'+(bad.length?bad.join('; '):'');document.body.appendChild(p);});</script>"""
pathlib.Path(out).write_text(h.replace("</body>",q+"</body>"),encoding="utf-8")
PY
    out=$("$CHROME" --headless=new --disable-gpu --virtual-time-budget=2400 --dump-dom "file://$(pwd)/$tmp" 2>/dev/null | grep -o 'OVERFLOW|[^<]*' | tail -1)
    rm -f "$tmp"
    [ -n "${out#*|}" ] && echo "⚠️ $html 溢出: ${out#*|}"
  done
  echo "✓ 溢出质检完成"
fi

# 3) 输出 / 执行 xhs post
args=(--title "$(cat "$DIR/title.md")" --body "$(cat "$DIR/body.md")")
for i in "${imgs[@]}"; do args+=(--images "$i"); done
if [ -f "$DIR/.topics.txt" ]; then while read -r t; do [ -n "$t" ] && args+=(--topic "$t"); done < "$DIR/.topics.txt"; fi

echo "── 要执行的命令 ──"; echo "xhs post ${args[*]}"
if [ "$POST" = "1" ]; then echo "── 执行 ──"; xhs post "${args[@]}"; fi
