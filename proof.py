"""Capture a real, publicly visible Threads reply; never fabricate a proof image.

The browser is unauthenticated. Login walls and layouts we cannot verify cause an
explicit failure. Screenshot failure must not trigger another publication.
"""
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path
import re
import tempfile
import time
from urllib.parse import unquote, urlsplit


class ProofError(Exception):
    pass


HOSTS = {"threads.com", "www.threads.com", "threads.net", "www.threads.net"}


def validate_permalink(permalink, username):
    if not isinstance(permalink, str) or not isinstance(username, str):
        raise ProofError("Thiếu permalink hoặc tên tài khoản để xác minh ảnh chụp.")
    username = username.removeprefix("@")
    if not re.fullmatch(r"[A-Za-z0-9._]+", username):
        raise ProofError("Tên tài khoản Threads không hợp lệ.")
    try:
        parsed = urlsplit(permalink)
        if (parsed.scheme != "https" or parsed.hostname not in HOSTS
                or parsed.port not in (None, 443) or parsed.username or parsed.password):
            raise ValueError()
        path = unquote(parsed.path).rstrip("/")
        match = re.fullmatch(r"/@([A-Za-z0-9._]+)/post/([A-Za-z0-9_-]+)", path)
        if not match or match[1].casefold() != username.casefold():
            raise ValueError()
    except ValueError:
        raise ProofError("Chỉ chụp permalink HTTPS chính thức của đúng tài khoản Threads.") from None
    # Discard query strings, fragments and tracking parameters.
    return f"https://{parsed.hostname}{path}", path, username


_VERIFY_FUNCTION = r"""
function verified(el, args) {
    if (!el || !el.isConnected) return false;
    const norm = s => String(s || '').replace(/[\u200b\u200c\u200d\ufeff]/g, '').replace(/\s+/g, ' ').trim();
    const visible = node => {
        const rect = node.getBoundingClientRect();
        const style = getComputedStyle(node);
        return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
    };
    if (!visible(el) || !norm(el.innerText).includes(norm(args.text))) return false;
    const allowed = new Set(['threads.com', 'www.threads.com', 'threads.net', 'www.threads.net']);
    const pathOf = link => {
        try {
            const u = new URL(link.href, location.href);
            if (u.protocol !== 'https:' || !allowed.has(u.hostname)) return null;
            return decodeURIComponent(u.pathname).replace(/\/$/, '');
        } catch (_) { return null; }
    };
    const links = Array.from(el.querySelectorAll('a[href]'));
    const postPaths = new Set(links.map(pathOf).filter(p => p && /^\/@[^/]+\/post\/[^/]+$/.test(p)));
    // Reject a combined parent/reply area: it can attribute someone else's image
    // or text to this reply. Prefer failing to photographing the wrong post.
    if (postPaths.size !== 1 || !postPaths.has(args.postPath)) return false;
    const authorPath = '/@' + args.username.toLowerCase();
    const author = links.some(a => {
        const path = pathOf(a);
        const name = norm(a.innerText).replace(/^@/, '').toLowerCase();
        return path && path.toLowerCase() === authorPath && name === args.username.toLowerCase() && visible(a);
    });
    if (!author) return false;
    if (args.imageExpected) {
        const images = Array.from(el.querySelectorAll('img'));
        const photo = images.some(img => {
            const r = img.getBoundingClientRect();
            if (!visible(img) || !img.complete || img.naturalWidth < 120 || img.naturalHeight < 100
                    || r.width < 120 || r.height < 90) return false;
            if (/avatar|profile\s*(picture|photo)|ảnh\s*đại\s*diện|logo/i.test(img.alt || '')) return false;
            const parentLink = img.closest('a[href]');
            if (parentLink && /^\/@[^/]+$/.test(pathOf(parentLink) || '')) return false;
            try { return new URL(img.currentSrc || img.src, location.href).protocol === 'https:'; }
            catch (_) { return false; }
        });
        if (!photo) return false;
    }
    return true;
}
"""

_SELECT_REPLY = """args => {
""" + _VERIFY_FUNCTION + r"""
    const candidates = new Set(document.querySelectorAll('article, [role="article"], [data-pressable-container]'));
    // Threads' markup changes. Walk only a small number of ancestors of the
    // target permalink, and still require the strict single-post checks above.
    for (const a of document.querySelectorAll('a[href]')) {
        let path;
        try { path = decodeURIComponent(new URL(a.href, location.href).pathname).replace(/\/$/, ''); }
        catch (_) { continue; }
        if (path !== args.postPath) continue;
        let node = a.parentElement;
        for (let depth = 0; node && depth < 8 && node !== document.body; depth++, node = node.parentElement) {
            candidates.add(node);
        }
    }
    return Array.from(candidates).filter(el => verified(el, args)).sort((a, b) => {
        const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
        return ra.width * ra.height - rb.width * rb.height;
    })[0] || null;
}"""

_REVERIFY_REPLY = """(el, args) => {
""" + _VERIFY_FUNCTION + "return verified(el, args); }"


def capture_proof(permalink, text, username, image_expected, output_path):
    """Return metadata only after capturing a verified real reply element.

    This verifies that a rendered attachment exists, not byte-for-byte identity
    with the uploaded picture. API media confirmation belongs to the caller.
    """
    url, path, username = validate_permalink(permalink, username)
    if not isinstance(text, str) or not text.strip() or type(image_expected) is not bool:
        raise ProofError("Nội dung hoặc tùy chọn ảnh chụp không hợp lệ.")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise ProofError("Chưa cài Playwright và Chromium để chụp bằng chứng.") from None
    destination = Path(output_path)
    temporary = None
    deadline = time.monotonic() + 45

    def remaining(maximum):
        budget = int((deadline - time.monotonic()) * 1000)
        if budget <= 0:
            raise ProofError("Hết 45 giây chờ xác minh ảnh chụp trang Threads.")
        return min(maximum, budget)

    args = {"text": text, "username": username, "postPath": path, "imageExpected": image_expected}
    try:
        with sync_playwright() as runtime:
            launch = {"headless": True, "timeout": remaining(15000)}
            executable = os.environ.get("THREADS_CHROMIUM_PATH")
            if executable:
                launch["executable_path"] = executable
            browser = runtime.chromium.launch(**launch)
            try:
                context = browser.new_context(viewport={"width": 1280, "height": 1200},
                                              locale="vi-VN", service_workers="block")
                page = context.new_page()
                page.set_default_timeout(10000)
                page.set_default_navigation_timeout(45000)
                response = page.goto(url, wait_until="domcontentloaded", timeout=remaining(45000))
                if response is None or response.status >= 400:
                    raise ProofError("Không tải được permalink công khai để chụp.")
                # A login redirect must not be mistaken for the published reply.
                _, redirected_path, _ = validate_permalink(page.url, username)
                if redirected_path != path:
                    raise ProofError("Threads chuyển sang trang khác; chưa xác minh được bình luận.")
                try:
                    page.wait_for_function(_SELECT_REPLY, arg=args, timeout=remaining(20000))
                except Exception:
                    raise ProofError("Không xác minh được đúng bình luận, tác giả và ảnh trên trang công khai; có thể gặp yêu cầu đăng nhập hoặc giao diện đã đổi.") from None
                handle = page.evaluate_handle(_SELECT_REPLY, args)
                element = handle.as_element()
                if element is None:
                    raise ProofError("Không tìm thấy vùng bình luận đủ điều kiện chụp.")
                element.scroll_into_view_if_needed(timeout=remaining(10000))
                if not element.evaluate(_REVERIFY_REPLY, args):
                    raise ProofError("Bình luận thay đổi trước lúc chụp; chưa tạo bằng chứng.")
                destination.parent.mkdir(parents=True, exist_ok=True)
                fd, temporary_name = tempfile.mkstemp(prefix=".threads-proof-", suffix=".png", dir=destination.parent)
                os.close(fd)
                temporary = Path(temporary_name)
                element.screenshot(path=str(temporary), type="png", animations="disabled", timeout=remaining(10000))
                if not element.evaluate(_REVERIFY_REPLY, args):
                    raise ProofError("Không xác minh được nội dung sau lúc chụp; bỏ ảnh chưa chắc chắn.")
                if not temporary.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
                    raise ProofError("Trình duyệt không tạo được ảnh PNG hợp lệ.")
                temporary.replace(destination)
                temporary = None
            finally:
                browser.close()
    except ProofError:
        raise
    except Exception:
        raise ProofError("Không chụp được trang Threads thật. Bình luận đã gửi không được tự đăng lại.") from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {"path": str(destination), "permalink": url,
            "verified_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "image_expected": image_expected}
