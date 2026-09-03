#!/usr/bin/env python3
"""
douyin-post.py — 抖音创作者中心「图文」发布 CLI（Playwright + 本机 Chrome）

用法:
  python3 scripts/douyin-post.py login                      # 打开有头浏览器，扫码登录（持久化到 profile）
  python3 scripts/douyin-post.py status                     # 检查登录状态
  python3 scripts/douyin-post.py post --title "..." --desc "..." \
      --images a.png b.png [--private] [--dry-run]

设计要点:
  - 抖音 web 登录绑定浏览器设备指纹，因此用【持久化 user_data_dir 个人资料】，
    而不是每次复制 storage_state（后者会被 douyin 踢回登录页）。
    profile 目录: ~/.douyin-cli/profile（仓库外，勿提交）。
  - 走 creator.douyin.com 创作者中心网页，channel="chrome" 用本机 Chrome，降低风控。
  - 选择器多路兜底；失败时保存截图 + 抽取页面文本，方便无头环境下排障。
  - --private 时若「仅自己可见」没有设置成功，直接中止，绝不把内容发成公开。
  - 发布点完后耐心等「快速检测」完成并命中「发布成功」再关闭，避免中途关闭导致漏发。
"""

import argparse
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

PROFILE_DIR = Path.home() / ".douyin-cli" / "profile"
UPLOAD_URL = "https://creator.douyin.com/creator-micro/content/upload?enter_from=publish"
LOGIN_MARKERS = ("扫码登录", "扫二维码", "二维码登录")
MAX_TITLE = 30
MAX_DESC = 1000


def log(msg: str) -> None:
    print(msg, flush=True)


def die(msg: str, page=None, tag: str = "debug") -> "None":
    if page is not None:
        try:
            shot = Path(f"/tmp/dy-{tag}.png")
            page.screenshot(path=str(shot), full_page=False)
            body = page.inner_text("body")[:1500]
            Path(f"/tmp/dy-{tag}.txt").write_text(body, encoding="utf-8")
            log(f"  [debug] 截图: {shot}  文本: /tmp/dy-{tag}.txt")
            log("  [debug] 页面文本前 1500 字:\n" + body)
        except Exception as e:  # noqa: BLE001
            log(f"  [debug] 保存调试信息失败: {e}")
    log(f"✗ {msg}")
    sys.exit(1)


def open_context(p, headless: bool):
    """持久化 user_data_dir 的个人资料会话（保留设备指纹，避免被踢回登录页）。"""
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    kw = dict(
        user_data_dir=str(PROFILE_DIR),
        channel="chrome",
        headless=headless,
        viewport={"width": 1440, "height": 960},
    )
    if headless:
        kw["args"] = ["--disable-blink-features=AutomationControlled"]
    return p.chromium.launch_persistent_context(**kw)


def looks_logged_in(page) -> bool:
    try:
        host = urlparse(page.url).hostname or ""
        body = page.inner_text("body")
    except Exception:  # noqa: BLE001
        return False
    if "creator.douyin.com" not in host:
        return False
    for marker in LOGIN_MARKERS:
        if marker in body:
            return False
    return True


def is_upload_ready(page) -> bool:
    """创作者已登录的强信号：上传页出现「发布图文/上传视频」或文件输入框。"""
    try:
        host = urlparse(page.url).hostname or ""
        if "creator.douyin.com" not in host:
            return False
        body = page.inner_text("body")
        if "发布图文" in body or "上传视频" in body:
            return True
        if page.locator("input[type=file]").count() > 0:
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


def wait_login_success(page, timeout_s: int = 300) -> None:
    log("等待真实登录（扫码/验证码），轮询中…")
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if is_upload_ready(page):
            log("✓ 登录成功，会话已持久化到 profile")
            return
        time.sleep(2)
    die("登录超时，未确认登录。", page, "login-timeout")


def wait_ready(page, timeout_s: int = 30) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if "加载中" not in page.inner_text("body"):
                return True
        except Exception:  # noqa: BLE001
            pass
        time.sleep(1)
    return False


def goto_upload(page) -> None:
    page.goto(UPLOAD_URL, timeout=45000, wait_until="domcontentloaded")
    wait_ready(page)
    if not is_upload_ready(page):
        # 站点首页有「发布」导航，可能 SPA 需要点进去；兜底直接再跳一次
        page.goto(UPLOAD_URL, timeout=45000, wait_until="domcontentloaded")
        wait_ready(page)
    if not looks_logged_in(page):
        die("未登录或会话失效，请先: python3 scripts/douyin-post.py login", page, "need-login")


def find_image_input(page):
    inputs = page.locator("input[type=file]")
    n = inputs.count()
    if n == 0:
        return None
    for i in range(n):
        acc = (inputs.nth(i).get_attribute("accept") or "").lower()
        if "image" in acc:
            return inputs.nth(i)
    return inputs.first


def click_image_tab(page) -> bool:
    tab = None
    for txt in ("发布图文", "图文", "上传图文"):
        for role in ("tab", "button"):
            loc = page.get_by_role(role, name=txt, exact=False)
            if loc.count() > 0:
                tab = loc.first
                break
        if tab is None:
            loc = page.get_by_text(txt, exact=True)
            if loc.count() > 0:
                tab = loc.first
        if tab is not None:
            break
    if tab is not None:
        try:
            tab.click(timeout=6000)
            wait_ready(page)
            page.wait_for_timeout(2000)
            log("✓ 已切换「发布图文」")
            return True
        except Exception as e:  # noqa: BLE001
            log(f"· 点击图文 tab 失败: {e}")
    else:
        log("· 未找到图文 tab，按当前页面继续")
    return False


def find_title_input(page):
    for sel in (
        "input[placeholder*='标题']",
        "input[maxlength='30']",
        "textarea[placeholder*='标题']",
    ):
        loc = page.locator(sel)
        if loc.count() > 0:
            return loc.first
    return None


def find_desc_editor(page):
    editors = page.locator("[contenteditable='true']")
    for i in range(editors.count()):
        el = editors.nth(i)
        attrs = " ".join(
            (el.get_attribute(k) or "") for k in ("data-placeholder", "aria-label", "placeholder", "class")
        ).lower()
        if any(k in attrs for k in ("正文", "内容", "desc", "editor", "zone")):
            return el
    if editors.count() > 0:
        return editors.first
    for sel in ("textarea[placeholder*='正文']", "textarea[placeholder*='内容']"):
        loc = page.locator(sel)
        if loc.count() > 0:
            return loc.first
    return None


def set_visibility_private(page) -> bool:
    def _label():
        for text in ("仅自己可见", "仅自己"):
            lab = page.locator("label", has_text=text)
            for i in range(lab.count()):
                el = lab.nth(i)
                try:
                    if el.is_visible():
                        return el
                except Exception:  # noqa: BLE001
                    continue
        return None

    try:
        for _ in range(2):
            lab = _label()
            if lab is None:
                return False
            lab.click()
            page.wait_for_timeout(900)
            checked = (lab.get_attribute("data-checked") or lab.get_attribute("aria-checked") or "").strip().lower()
            if checked == "true":
                log("✓ 已设为仅自己可见")
                return True
        log("· 仅自己可见 选中态未确认")
        return False
    except Exception as e:  # noqa: BLE001
        log(f"· 设置仅自己可见时出错: {e}")
        return False


def cmd_login(_args) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        ctx = open_context(p, headless=False)
        page = ctx.new_page()
        try:
            page.goto(UPLOAD_URL, timeout=45000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            if is_upload_ready(page):
                log("✓ 当前 profile 已是登录态")
            else:
                wait_login_success(page)
        finally:
            ctx.close()


def open_music_picker(page) -> bool:
    sel = page.get_by_text("选择音乐", exact=False)
    for i in range(sel.count() - 1, -1, -1):
        try:
            if sel.nth(i).is_visible():
                sel.nth(i).click()
                page.wait_for_timeout(2200)
                return True
        except Exception:  # noqa: BLE001
            continue
    alt = page.get_by_text("点击添加合适作品风格音乐", exact=False)
    for i in range(alt.count()):
        try:
            if alt.nth(i).is_visible():
                alt.nth(i).click()
                page.wait_for_timeout(2200)
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


def click_first_music(page) -> bool:
    import re

    try:
        body = page.inner_text("body")
        m = re.search(r"([^\n]{2,44})\n[^\n]{1,26}\n(\d{2}:\d{2})", body)
        if m:
            title = m.group(1).strip()
            loc = page.get_by_text(title, exact=True)
            if loc.count() > 0:
                loc.first.click()
                page.wait_for_timeout(2500)
                log(f"· 已点击配乐: {title}")
                return True
    except Exception as e:  # noqa: BLE001
        log(f"· 点击配乐失败: {e}")
    return False


def select_music(page, keyword=None) -> bool:
    """打开抖音曲库并选一首。keyword 非空则搜索关键词；否则取「热门榜」第一首。"""
    if not open_music_picker(page):
        return False
    if keyword:
        box = page.locator("input[placeholder='搜索音乐']")
        if box.count() == 0:
            return False
        box.first.click()
        box.first.fill(keyword)
        box.first.press("Enter")
        page.wait_for_timeout(2800)
    else:
        hot = page.get_by_text("热门榜", exact=True)
        if hot.count() > 0:
            try:
                hot.first.click()
                page.wait_for_timeout(2200)
            except Exception:  # noqa: BLE001
                pass
    return click_first_music(page)


def close_sidesheet(page) -> None:
    """关闭可能残留的底/侧弹层（semi-sidesheet），否则会挡住发布按钮。"""
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(800)
    except Exception:  # noqa: BLE001
        pass
    mask = page.locator(".semi-sidesheet-mask")
    if mask.count() > 0:
        try:
            # 点遮罩左上角边缘关闭（远离弹层内容）
            mask.first.click(position={"x": 20, "y": 20})
            page.wait_for_timeout(800)
        except Exception:  # noqa: BLE001
            pass
        mask = page.locator(".semi-sidesheet-mask")
        if mask.count() > 0:
            try:
                page.keyboard.press("Escape")
                page.wait_for_timeout(600)
            except Exception:  # noqa: BLE001
                pass


def cmd_status(_args) -> None:
    from playwright.sync_api import sync_playwright

    ok = False
    with sync_playwright() as p:
        ctx = open_context(p, headless=True)
        page = ctx.new_page()
        try:
            page.goto(UPLOAD_URL, timeout=45000, wait_until="domcontentloaded")
            page.wait_for_timeout(4000)
            ok = is_upload_ready(page)
        except Exception as e:  # noqa: BLE001
            log(f"AUTH_UNKNOWN ({e})")
            sys.exit(2)
        finally:
            ctx.close()
    if ok:
        log("AUTH_OK")
    else:
        log("AUTH_NEEDED (session expired)")
        sys.exit(1)


def cmd_post(args) -> None:
    if len(args.title) > MAX_TITLE:
        die(f"标题 {len(args.title)} 字，超过抖音 {MAX_TITLE} 字上限")
    if len(args.desc) > MAX_DESC:
        die(f"描述 {len(args.desc)} 字，超过 {MAX_DESC} 字上限")
    images = [str(Path(i).resolve()) for i in args.images]
    for img in images:
        if not Path(img).exists():
            die(f"图片不存在: {img}")

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        ctx = open_context(p, headless=not args.headed)
        page = ctx.new_page()
        try:
            goto_upload(page)
            click_image_tab(page)

            # 上传图片
            target = None
            deadline = time.time() + 60
            while time.time() < deadline:
                target = find_image_input(page)
                if target is not None:
                    break
                page.wait_for_timeout(1500)
            if target is None:
                die("60s 内页面未出现图片上传输入框", page, "no-file-input")
            target.set_input_files(images)
            log(f"✓ 已选择 {len(images)} 张图片，等待上传/编辑器…")
            deadline = time.time() + 90
            while time.time() < deadline:
                page.wait_for_timeout(2000)
                title_box = find_title_input(page)
                if title_box is not None:
                    try:
                        if title_box.is_visible() and title_box.is_enabled():
                            log("✓ 编辑器就绪")
                            break
                    except Exception:  # noqa: BLE001
                        pass
            else:
                die("90s 内编辑器未就绪", page, "editor-timeout")

            # 标题
            title_box = find_title_input(page)
            if title_box is None:
                die("找不到标题输入框", page, "no-title")
            title_box.click()
            title_box.fill(args.title)
            log("✓ 标题已填")

            # 描述（insert_text 整段粘贴，避免 #话题 联想搅乱文字）
            desc = find_desc_editor(page)
            if desc is None:
                die("找不到正文编辑器", page, "no-desc")
            desc.click()
            page.keyboard.insert_text(args.desc)
            page.wait_for_timeout(600)
            if len(desc.inner_text() or "") < 10:
                die("描述填入异常", page, "desc-fill")
            log("✓ 描述已填")

            if args.private:
                if not set_visibility_private(page):
                    die("--private 模式下「仅自己可见」设置失败，为安全起见中止", page, "private-fail")
                log("✓ 已设为仅自己可见")

            if args.music or args.hot:
                if not select_music(page, keyword=args.music):
                    die("配乐选择失败（曲库面板未打开或没选到曲目）", page, "music-fail")
                log("✓ 配乐已选")
                close_sidesheet(page)

            page.wait_for_timeout(1000)
            if args.dry_run:
                shot = Path("/tmp/dy-dryrun.png")
                page.screenshot(path=str(shot))
                body = page.inner_text("body")[:800]
                log(f"✓ DRY-RUN 完成，未发布。截图: {shot}")
                log("---- 页面文本 ----\n" + body)
                return

            # 发布（耐心等检测完成后提交）
            close_sidesheet(page)
            btn = None
            deadline = time.time() + 60
            while time.time() < deadline:
                cand = page.get_by_role("button", name="发布", exact=True)
                if cand.count() == 0:
                    cand = page.locator("button:has-text('发布')")
                for i in range(cand.count()):
                    el = cand.nth(i)
                    try:
                        if el.is_visible() and el.is_enabled():
                            btn = el
                            break
                    except Exception:  # noqa: BLE001
                        continue
                if btn is not None:
                    break
                page.wait_for_timeout(1500)
            if btn is None:
                die("找不到可用的发布按钮", page, "no-publish-btn")
            btn.click()
            log("✓ 已点击发布，等待检测与提交…")

            result = "PENDING"
            deadline = time.time() + 300
            while time.time() < deadline:
                page.wait_for_timeout(1500)
                body = page.inner_text("body")
                if "短信验证码" in body or "接收短信验证码" in body:
                    log("🔐 检测到短信验证界面：请在打开的浏览器窗口输入手机收到的验证码并点「验证」，脚本会继续。")
                if "发布成功" in body or "作品已发布" in body:
                    result = "SUCCESS"
                    break
                if any(k in body for k in ("检测未通过", "发布失败", "内容审核不通过", "未通过", "违规")):
                    result = "REJECTED"
                    break
            shot = Path("/tmp/dy-posted.png")
            page.screenshot(path=str(shot))
            body = page.inner_text("body")[:1200]
            log(f"发布结果: {result}. 截图: {shot}")
            log("---- 页面文本 ----\n" + body)
        finally:
            ctx.close()


def main() -> None:
    ap = argparse.ArgumentParser(description="抖音图文发布 CLI")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("login", help="扫码登录并持久化会话（profile）")
    sub.add_parser("status", help="检查登录状态")

    pp = sub.add_parser("post", help="发布图文")
    pp.add_argument("--title", required=True, help=f"标题 ≤{MAX_TITLE} 字")
    pp.add_argument("--desc", required=True, help="描述/正文（含 #话题）")
    pp.add_argument("--images", nargs="+", required=True, help="图片路径（1–35 张）")
    pp.add_argument("--private", action="store_true", help="仅自己可见（设置失败即中止）")
    pp.add_argument("--music", default=None, help="按关键词从抖音曲库选配乐")
    pp.add_argument("--hot", action="store_true", help="取热门榜第一首作配乐")
    pp.add_argument("--dry-run", action="store_true", help="填完不点发布，输出预览")
    pp.add_argument("--headed", action="store_true", help="有头模式运行（排障用）")

    args = ap.parse_args()
    {"login": cmd_login, "status": cmd_status, "post": cmd_post}[args.cmd](args)


if __name__ == "__main__":
    main()
