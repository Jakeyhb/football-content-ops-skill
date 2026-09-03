#!/usr/bin/env python3
"""Xiaohongshu cover pipeline: MiniMax image-01 / image-01-live + M3 plan/QA.

Subcommands:
  plan     M3 decides html / minimax / hybrid and writes a visual prompt
  gen      Call MiniMax image API (high-res 3:4, prompt optimizer, optional ref)
  qa       M3 vision scores generated images and picks a winner
  overlay  Put Chinese hook text on a background via HTML + Chrome screenshot
  render   Screenshot an existing HTML card to 1080x1440 PNG
  run      plan → gen → qa → overlay (default publish path)
"""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates" / "cover"
CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
API_BASE = "https://api.minimaxi.com"
IMAGE_URL = f"{API_BASE}/v1/image_generation"
CHAT_URL = f"{API_BASE}/v1/chat/completions"
PROMPT_LIMIT = 1500
CANVAS = (1080, 1440)

NO_TEXT_SUFFIX = (
    " Absolutely no text, letters, numbers, captions, watermarks, logos, "
    "club crests, badges, or typography anywhere in the image."
)

PLAN_SYSTEM = """You plan Xiaohongshu (小红书) cover images for account @bawbaw.
Return ONLY compact JSON. No markdown.

Account: football transfer news + psychology. CTR lives or dies on the cover.
Rules:
1. pipeline must be one of: html | hybrid | minimax
   - html: text-heavy cards (deal facts, rankings, method cards, polls). Agent writes HTML, Chrome screenshots. Do NOT use MiniMax to draw Chinese or data.
   - hybrid: MiniMax draws a TEXTLESS background/atmosphere; HTML overlays 6-10 Chinese hook characters. Default for covers.
   - minimax: only when the image has ZERO required Chinese (rare).
2. Never ask MiniMax to draw real footballers, club crests, or extra fingers. If a real photo exists, pipeline=hybrid and need_photo=true.
3. MiniMax visual_prompt MUST be English, <= 900 chars, photography/illustration language, no Chinese glyphs.
4. overlay.title_lines: 1-3 short Chinese lines, total 6-10 characters if possible. subtitle one line.
5. Football visual: night stadium, cinematic. Match the story's venue (Allianz, Etihad, etc). Account HTML overlay already uses City-blue — do NOT paint every pitch #6CABDD. No people unless 已有实拍文件 lists a real file.
6. Psychology visual: quiet, understood, watercolor/soft light, not cute cartoon, not dense collage.
7. model: image-01 for photoreal/atmosphere; image-01-live + style_type 水彩 for psychology illustration. style_type one of 漫画,元气,中世纪,水彩 or null.
8. If 已有实拍文件 is 无, need_photo=false. Never invent a photo.

JSON shape:
{
  "pipeline": "hybrid",
  "reason": "",
  "model": "image-01",
  "style_type": null,
  "need_photo": false,
  "kicker": "HWG CONFIRMED",
  "title_lines": ["大字1","大字2"],
  "subtitle": "",
  "visual_prompt": "English, no text in image...",
  "avoid": ["text","logos","faces","extra fingers"]
}
"""

QA_SYSTEM = """You are a Xiaohongshu cover QA rater. Return ONLY JSON.
Score 0-10. Fail (pass=false) if ANY of:
- Chinese on the image is missing, misspelled, extra, or garbled
- Real-person face looks AI (extra fingers, melted badge, waxy skin) unless it is clearly a photo
- Large empty margins / thin type / magazine whitespace (kills CTR)
- Canvas not filled like a 3:4 phone cover
- Extra watermarks/logos the brief did not ask for
CTR rules: hook title 35-50% of frame, high contrast, one strong subject, dense not airy.
JSON:
{"score": 0, "pass": false, "text_ok": true, "issues": [], "ctr_notes": "", "pick": false}
"""


def die(msg: str, code: int = 1) -> None:
    print(f"❌ {msg}", file=sys.stderr)
    sys.exit(code)


def load_api_key() -> str:
    key = os.environ.get("MINIMAX_CN_API_KEY") or os.environ.get("MINIMAX_API_KEY") or ""
    if key:
        return key.strip()
    creds = Path.home() / ".dsh" / ".credentials.yaml"
    if creds.is_file():
        for line in creds.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*(MINIMAX_CN_API_KEY|MINIMAX_API_KEY)\s*:\s*(.+)\s*$", line)
            if m:
                return m.group(2).strip().strip("'\"")
    die("未找到 MINIMAX_CN_API_KEY（~/.dsh/.credentials.yaml 或环境变量）")
    return ""


def http_json(url: str, payload: dict, timeout: int = 180) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {load_api_key()}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        die(f"HTTP {e.code} {url}: {err[:800]}")
    return {}


def extract_json(text: str) -> dict:
    if not text:
        die("模型返回空内容")
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        die(f"无法解析 JSON: {text[:400]}")
    return {}


def message_text(resp: dict) -> str:
    msg = (resp.get("choices") or [{}])[0].get("message") or {}
    content = msg.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text") or "")
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return str(content or "")


def m3_chat(messages: list, *, thinking: str = "disabled", max_tokens: int = 1200) -> str:
    payload = {
        "model": "MiniMax-M3",
        "messages": messages,
        "max_completion_tokens": max_tokens,
        "thinking": {"type": thinking},
        "temperature": 0.4,
    }
    resp = http_json(CHAT_URL, payload, timeout=180)
    if resp.get("base_resp", {}).get("status_code") not in (None, 0):
        die(f"M3 失败: {json.dumps(resp, ensure_ascii=False)[:600]}")
    return message_text(resp)


def read_text(path: Path | None) -> str:
    if not path:
        return ""
    p = Path(path)
    return p.read_text(encoding="utf-8").strip() if p.is_file() else ""


def file_data_url(path: Path) -> str:
    raw = path.read_bytes()
    if len(raw) > 9_500_000:
        die(f"参考图过大（>10MB）: {path}")
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    if path.suffix.lower() == ".png":
        mime = "image/png"
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


def clip_prompt(prompt: str) -> str:
    prompt = prompt.strip()
    if len(prompt) <= PROMPT_LIMIT:
        return prompt
    print(f"⚠️ prompt 超 {PROMPT_LIMIT} 字，已截断")
    return prompt[: PROMPT_LIMIT - 1]


def convert_to_png(src: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    raw = src.read_bytes()
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        shutil.copyfile(src, dest)
        return dest
    if shutil.which("sips"):
        subprocess.run(
            ["sips", "-s", "format", "png", str(src), "--out", str(dest)],
            check=True,
            capture_output=True,
        )
        return dest
    dest = dest.with_suffix(".jpg")
    shutil.copyfile(src, dest)
    return dest


def resample(path: Path, w: int, h: int) -> None:
    if not shutil.which("sips"):
        return
    subprocess.run(
        ["sips", "-z", str(h), str(w), str(path)],
        check=False,
        capture_output=True,
    )


def find_chrome() -> Path:
    if CHROME.is_file():
        return CHROME
    which = shutil.which("google-chrome") or shutil.which("chromium")
    if which:
        return Path(which)
    die("未找到 Google Chrome，无法截 HTML 图卡")
    return CHROME


def screenshot_html(html_path: Path, out_png: Path) -> Path:
    chrome = find_chrome()
    html_path = html_path.resolve()
    out_png = out_png.resolve()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    uri = html_path.as_uri()
    cmd = [
        str(chrome),
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--force-device-scale-factor=2",
        f"--window-size={CANVAS[0]},{CANVAS[1]}",
        "--allow-file-access-from-files",
        "--virtual-time-budget=5000",
        f"--screenshot={out_png}",
        uri,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    if not out_png.is_file():
        die(f"Chrome 截图失败: {out_png}")
    resample(out_png, *CANVAS)
    return out_png


# --- plan ------------------------------------------------------------------

def cmd_plan(args: argparse.Namespace) -> dict:
    title = args.title or read_text(Path(args.topic_dir) / "title.md" if args.topic_dir else None)
    body = args.body or read_text(Path(args.topic_dir) / "body.md" if args.topic_dir else None)
    if not title and args.prompt_file:
        title = Path(args.prompt_file).stem
        body = read_text(Path(args.prompt_file))
    if not title and not body:
        die("plan 需要 --title/--body 或 --topic-dir")
    photos = []
    if args.topic_dir:
        for p in Path(args.topic_dir).glob("*"):
            if p.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
                continue
            skip = ("封面", "图集", "cover-bg", "Snipaste", "overlay", "screenshot", "截图")
            if any(s.lower() in p.name.lower() for s in skip):
                continue
            photos.append(p.name)
    user = (
        f"分类: {args.category or '未指定'}\n"
        f"标题: {title}\n"
        f"正文:\n{body[:2500]}\n"
        f"已有实拍文件: {photos or '无（不要假装有照片）'}\n"
        f"用户备注: {args.note or '无'}"
    )
    raw = m3_chat(
        [{"role": "system", "content": PLAN_SYSTEM}, {"role": "user", "content": user}],
        thinking="disabled",
        max_tokens=900,
    )
    plan = extract_json(raw)
    plan.setdefault("pipeline", "hybrid")
    plan.setdefault("model", "image-01")
    out_dir = Path(args.out or args.topic_dir or ".")
    out_dir.mkdir(parents=True, exist_ok=True)
    plan_path = out_dir / "cover-plan.json"
    prompt_path = out_dir / "cover-visual-prompt.md"
    visual = clip_prompt((plan.get("visual_prompt") or "") + NO_TEXT_SUFFIX)
    plan["visual_prompt"] = visual
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    prompt_path.write_text(visual + "\n", encoding="utf-8")
    print(f"✅ pipeline={plan['pipeline']} model={plan.get('model')} → {plan_path}")
    print(f"   visual prompt → {prompt_path}")
    if plan.get("title_lines"):
        print("   overlay:", " / ".join(plan["title_lines"]))
    return plan


# --- gen -------------------------------------------------------------------

def cmd_gen(args: argparse.Namespace) -> list[Path]:
    prompt = args.prompt or read_text(Path(args.prompt_file) if args.prompt_file else None)
    if not prompt:
        die("gen 需要 --prompt 或 --prompt-file")
    if args.no_text:
        if "no text" not in prompt.lower() and "不要文字" not in prompt:
            prompt = prompt.rstrip() + NO_TEXT_SUFFIX
    prompt = clip_prompt(prompt)
    model = args.model
    payload: dict = {
        "model": model,
        "prompt": prompt,
        "response_format": "url",
        "n": int(args.n),
        "prompt_optimizer": not args.no_optimize,
        "aigc_watermark": False,
    }
    if model == "image-01":
        payload["width"] = int(args.width)
        payload["height"] = int(args.height)
    else:
        payload["aspect_ratio"] = args.aspect
        if args.style:
            payload["style"] = {"style_type": args.style, "style_weight": float(args.style_weight)}
    if args.ref:
        ref = Path(args.ref)
        if not ref.is_file():
            die(f"找不到参考图: {ref}")
        payload["subject_reference"] = [{"type": "character", "image_file": file_data_url(ref)}]
    if args.seed is not None:
        payload["seed"] = int(args.seed)

    print(f"🎨 MiniMax {model}  n={payload['n']}  optimizer={payload['prompt_optimizer']}")
    resp = http_json(IMAGE_URL, payload, timeout=180)
    status = resp.get("base_resp", {}).get("status_code", -1)
    if status != 0:
        die(f"出图失败: {json.dumps(resp, ensure_ascii=False)[:800]}")
    urls = (resp.get("data") or {}).get("image_urls") or []
    if not urls:
        die(f"没有返回图片 URL: {json.dumps(resp, ensure_ascii=False)[:600]}")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    for i, url in enumerate(urls, 1):
        tmp = out_dir / f"{args.prefix}-{i}.tmp"
        urllib.request.urlretrieve(url, tmp)
        dest = convert_to_png(tmp, out_dir / f"{args.prefix}-{i}.png")
        tmp.unlink(missing_ok=True)
        if dest.suffix == ".png":
            resample(dest, *CANVAS)
        print(f"  ✅ {dest}")
        saved.append(dest)
    return saved


# --- qa --------------------------------------------------------------------

def cmd_qa(args: argparse.Namespace) -> dict:
    images = [Path(p) for p in args.images]
    if args.dir:
        images.extend(sorted(Path(args.dir).glob(f"{args.prefix}-*.png")))
        images.extend(sorted(Path(args.dir).glob(f"{args.prefix}-*.jpg")))
    images = [p for p in images if p.is_file()]
    if not images:
        die("qa 没有找到图片")
    expected = args.expected or ""
    results = []
    best: dict | None = None
    for path in images:
        content = [
            {
                "type": "text",
                "text": (
                    f"这是小红书 3:4 封面候选。期望画面上出现的中文（若走 hybrid 叠字，则应清晰可读）:\n"
                    f"{expected or '（无强制中文，检查是否误生文字/假脸）'}\n"
                    f"文件名: {path.name}\n请打分。"
                ),
            },
            {"type": "image_url", "image_url": {"url": file_data_url(path), "detail": "high"}},
        ]
        raw = m3_chat(
            [{"role": "system", "content": QA_SYSTEM}, {"role": "user", "content": content}],
            thinking="adaptive",
            max_tokens=700,
        )
        item = extract_json(raw)
        item["path"] = str(path)
        results.append(item)
        score = float(item.get("score") or 0)
        print(f"  {path.name}: {score}/10  pass={item.get('pass')}  {', '.join(item.get('issues') or []) or 'ok'}")
        if best is None or score > float(best.get("score") or 0):
            best = item
    if best:
        best["pick"] = True
        for item in results:
            item["pick"] = item is best
    report = {"results": results, "winner": best}
    out = Path(args.report) if args.report else (images[0].parent / "cover-qa.json")
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ QA 报告 {out}")
    if best:
        print(f"   首选: {best['path']}  ({best.get('score')}/10)")
    return report


# --- overlay / render ------------------------------------------------------

def load_theme_css() -> str:
    css = TEMPLATES / "theme.css"
    if not css.is_file():
        die(f"缺少 {css}")
    return css.read_text(encoding="utf-8")


def build_overlay_html(
    *,
    bg: Path | None,
    kicker: str,
    title_html: str,
    subtitle: str,
    theme: str,
) -> str:
    css = load_theme_css()
    bg_tag = ""
    if bg and bg.is_file():
        rel = bg.name
        bg_tag = f'<img class="photo" src="{rel}" alt="" />'
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<title>cover</title>
<style>
{css}
body[data-theme="psycho"] {{
  --city: #8fd0e0;
  --city-deep: #1a3c48;
  --gold: #e9c97c;
}}
.photo {{
  position: absolute; inset: 0; width: 100%; height: 100%;
  object-fit: cover; object-position: 50% 20%; z-index: 0;
  filter: saturate(0.92) contrast(1.08);
}}
.scrim {{
  position: absolute; inset: 0; z-index: 1;
  background:
    linear-gradient(105deg, rgba(7,13,18,0.94) 0%, rgba(7,13,18,0.78) 42%, rgba(7,13,18,0.28) 68%, rgba(7,13,18,0.18) 100%),
    linear-gradient(180deg, transparent 58%, rgba(5,9,12,0.92) 100%);
}}
.hook {{
  font-size: 118px; font-weight: 800; letter-spacing: 0.04em;
  line-height: 1.05; max-width: 980px;
}}
.hook em {{ font-style: normal; color: var(--city); }}
.kicker-line {{
  display: flex; align-items: center; gap: 16px;
  font-family: var(--num); font-size: 26px; letter-spacing: 0.2em; color: var(--gold);
  margin-bottom: 28px;
}}
.kicker-line i {{ width: 10px; height: 10px; background: var(--gold); transform: rotate(45deg); display: block; }}
</style>
</head>
<body data-theme="{theme}">
<div class="artboard">
  <div class="stripe"></div>
  {bg_tag}
  <div class="scrim"></div>
  <div class="pad">
    <div class="topbar">
      <div class="kicker-line"><i></i> {kicker or "BAWBAW"}</div>
      <div class="pager">COVER</div>
    </div>
    <div class="grow">
      <div>
        <h1 class="display hook">{title_html}</h1>
        <p class="sub">{subtitle}</p>
      </div>
    </div>
    <div class="footer">
      <div class="brand">BAWBAW</div>
      <div class="hint">向左滑</div>
    </div>
  </div>
</div>
</body>
</html>
"""


def cmd_overlay(args: argparse.Namespace) -> Path:
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    bg = Path(args.bg) if args.bg else None
    if bg and bg.is_file():
        dest_bg = out_dir / bg.name
        if dest_bg.resolve() != bg.resolve():
            shutil.copyfile(bg, dest_bg)
        bg = dest_bg
    lines = args.title if isinstance(args.title, list) else [args.title]
    lines = [x for x in lines if x]
    if not lines:
        die("overlay 需要 --title")
    # emphasize the last line
    html_lines = []
    for i, line in enumerate(lines):
        if i == len(lines) - 1:
            html_lines.append(f"<em>{line}</em>")
        else:
            html_lines.append(line)
    title_html = "<br>".join(html_lines)
    html = build_overlay_html(
        bg=bg,
        kicker=args.kicker or "BAWBAW",
        title_html=title_html,
        subtitle=args.subtitle or "",
        theme=args.theme,
    )
    html_path = out_dir / "overlay.html"
    html_path.write_text(html, encoding="utf-8")
    png = screenshot_html(html_path, out_dir / f"{args.prefix}.png")
    print(f"✅ 叠字封面 {png}")
    return png


def cmd_render(args: argparse.Namespace) -> Path:
    html = Path(args.html)
    if not html.is_file():
        die(f"找不到 HTML: {html}")
    out = Path(args.out) if args.out else html.with_suffix(".png")
    png = screenshot_html(html, out)
    print(f"✅ {png}")
    return png


# --- run -------------------------------------------------------------------

def cmd_run(args: argparse.Namespace) -> None:
    topic = Path(args.topic_dir)
    topic.mkdir(parents=True, exist_ok=True)
    args.out = str(topic)
    plan = cmd_plan(args)
    pipeline = plan.get("pipeline") or "hybrid"

    if pipeline == "html":
        print("📐 本篇应走 HTML 图卡（文字/数据密度高），不要用 MiniMax 画中文。")
        print("   复制 templates/cover/ 为底，改文案后:")
        print(f"   python3 scripts/xhs-cover.py render --html {topic}/图集-layout/01.html --out {topic}/图集-1.png")
        (topic / "cover-plan.json").write_text(
            json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return

    if pipeline == "minimax" and not args.force_minimax_text:
        print("↪️  改为 hybrid：MiniMax 只出无字底图，中文由 HTML 叠上（中文渲染更稳）")
        pipeline = "hybrid"

    photo = Path(args.ref) if args.ref else None
    if not photo and args.topic_dir:
        for p in topic.iterdir():
            if p.suffix.lower() in {".jpg", ".jpeg", ".png"} and p.name.startswith("素材"):
                photo = p
                break

    gen_ns = argparse.Namespace(
        prompt=plan.get("visual_prompt"),
        prompt_file=None,
        model=plan.get("model") or "image-01",
        n=args.n,
        width=1080,
        height=1440,
        aspect="3:4",
        style=plan.get("style_type"),
        style_weight=0.8,
        no_optimize=False,
        no_text=True,
        ref=str(photo) if photo else None,
        seed=None,
        out=str(topic),
        prefix="cover-bg",
    )
    if gen_ns.model == "image-01-live" and not gen_ns.style:
        gen_ns.style = "水彩"
    bgs = cmd_gen(gen_ns)

    qa_ns = argparse.Namespace(
        images=[],
        dir=str(topic),
        prefix="cover-bg",
        expected="（底图不应有中文/队徽/假脸）",
        report=str(topic / "cover-qa.json"),
    )
    report = cmd_qa(qa_ns)
    winner = (report.get("winner") or {}).get("path")
    if not winner and bgs:
        winner = str(bgs[0])
    if not winner:
        die("没有可用底图")

    overlay_ns = argparse.Namespace(
        bg=winner,
        title=plan.get("title_lines") or [topic.name],
        subtitle=plan.get("subtitle") or "",
        kicker=plan.get("kicker") or ("HWG CONFIRMED" if (args.category or "") == "football" else "BAWBAW"),
        theme="football" if (args.category or "football") == "football" else "psycho",
        out=str(topic),
        prefix="封面",
    )
    final = cmd_overlay(overlay_ns)
    print(f"\n🎉 发布用封面: {final}")
    print("   若 QA 分数低，换 --ref 实拍或改 title_lines 后重跑 overlay。")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="MiniMax 小红书封面流水线")
    sub = p.add_subparsers(dest="cmd", required=True)

    plan = sub.add_parser("plan", help="M3 规划 pipeline + 无字视觉提示词")
    plan.add_argument("--topic-dir")
    plan.add_argument("--title")
    plan.add_argument("--body")
    plan.add_argument("--prompt-file")
    plan.add_argument("--category", choices=["football", "psychology", "other"])
    plan.add_argument("--note")
    plan.add_argument("--out")
    plan.set_defaults(func=cmd_plan)

    gen = sub.add_parser("gen", help="MiniMax image-01 / image-01-live 出图")
    gen.add_argument("--prompt")
    gen.add_argument("--prompt-file")
    gen.add_argument("--out", required=True)
    gen.add_argument("--prefix", default="cover")
    gen.add_argument("--model", default="image-01", choices=["image-01", "image-01-live"])
    gen.add_argument("--n", type=int, default=4)
    gen.add_argument("--width", type=int, default=1080)
    gen.add_argument("--height", type=int, default=1440)
    gen.add_argument("--aspect", default="3:4")
    gen.add_argument("--style", choices=["漫画", "元气", "中世纪", "水彩"])
    gen.add_argument("--style-weight", type=float, default=0.8)
    gen.add_argument("--ref", help="人物参考图（subject_reference）")
    gen.add_argument("--seed", type=int)
    gen.add_argument("--no-optimize", action="store_true")
    gen.add_argument("--no-text", action="store_true", default=True)
    gen.add_argument("--allow-text", action="store_false", dest="no_text")
    gen.set_defaults(func=cmd_gen)

    qa = sub.add_parser("qa", help="M3 多模态打分选图")
    qa.add_argument("images", nargs="*")
    qa.add_argument("--dir")
    qa.add_argument("--prefix", default="cover")
    qa.add_argument("--expected", default="")
    qa.add_argument("--report")
    qa.set_defaults(func=cmd_qa)

    ov = sub.add_parser("overlay", help="HTML 叠中文钩子并截图")
    ov.add_argument("--bg")
    ov.add_argument("--title", action="append", required=True)
    ov.add_argument("--subtitle", default="")
    ov.add_argument("--kicker", default="BAWBAW")
    ov.add_argument("--theme", default="football", choices=["football", "psycho"])
    ov.add_argument("--out", required=True)
    ov.add_argument("--prefix", default="封面")
    ov.set_defaults(func=cmd_overlay)

    rd = sub.add_parser("render", help="把 HTML 图卡截成 1080x1440 PNG")
    rd.add_argument("--html", required=True)
    rd.add_argument("--out")
    rd.set_defaults(func=cmd_render)

    run = sub.add_parser("run", help="plan → gen → qa → overlay")
    run.add_argument("--topic-dir", required=True)
    run.add_argument("--category", choices=["football", "psychology", "other"])
    run.add_argument("--title")
    run.add_argument("--body")
    run.add_argument("--prompt-file")
    run.add_argument("--note")
    run.add_argument("--ref")
    run.add_argument("--n", type=int, default=4)
    run.add_argument("--out")
    run.add_argument("--force-minimax-text", action="store_true")
    run.set_defaults(func=cmd_run)
    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
