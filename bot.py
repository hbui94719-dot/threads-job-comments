#!/usr/bin/env python3
"""Reply to matching public Threads search results using the official API."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://graph.threads.net/v1.0"
UTC = dt.timezone.utc


class BotError(Exception):
    pass


def now():
    return dt.datetime.now(UTC)


def timestamp(value):
    try:
        result = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            raise ValueError()
        return result.astimezone(UTC)
    except (ValueError, TypeError, AttributeError) as exc:
        raise BotError("Mốc thời gian trong dữ liệu không hợp lệ.") from exc


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise BotError(f"Không đọc được JSON: {path}") from exc


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_config(path):
    config = read_json(path)
    if not isinstance(config, dict) or type(config.get("enabled")) is not bool:
        raise BotError("config.json cần enabled: true hoặc false.")
    keywords = config.get("keywords")
    if not isinstance(keywords, list) or not 1 <= len(keywords) <= 10:
        raise BotError("Cần từ 1 đến 10 từ khóa.")
    if any(not isinstance(q, str) or not q.strip() for q in keywords):
        raise BotError("Từ khóa phải là chuỗi không rỗng.")
    config["keywords"] = list(dict.fromkeys(q.strip() for q in keywords))
    bounds = {
        "max_per_24h": (1, 500), "max_per_run": (1, 50),
        "interval_seconds": (1, 300), "max_pages_per_keyword": (1, 10),
        "max_post_age_hours": (1, 168),
    }
    for key, (low, high) in bounds.items():
        value = config.get(key)
        if type(value) is not int or not low <= value <= high:
            raise BotError(f"{key} phải là số nguyên từ {low} đến {high}.")
    for key in ("require_image", "screenshots"):
        if key in config and type(config[key]) is not bool:
            raise BotError(f"{key} phải là true hoặc false.")
    image_url = config.get("image_url")
    if image_url is not None:
        try:
            parsed = urllib.parse.urlsplit(image_url) if isinstance(image_url, str) else None
            if parsed is not None and parsed.port not in (None, 443):
                raise ValueError()
        except ValueError:
            raise BotError("image_url không phải URL HTTPS hợp lệ.") from None
        if (parsed is None or parsed.scheme != "https" or not parsed.hostname
                or parsed.username or parsed.password or parsed.fragment):
            raise BotError("image_url cần là URL HTTPS công khai, hoặc null khi chưa có ảnh.")
    return config


def load_comments(path):
    values = read_json(path)
    if not isinstance(values, list):
        raise BotError("comments.json phải là một mảng chuỗi JSON.")
    if any(not isinstance(t, str) or not t.strip() or len(t.strip()) > 500 for t in values):
        raise BotError("Mỗi bình luận phải có từ 1 đến 500 ký tự.")
    return [t.strip() for t in values]


def normalize(text):
    text = unicodedata.normalize("NFKD", text.casefold().replace("đ", "d"))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^\w]+", " ", text).split())


def matches(text, keywords):
    haystack = " " + normalize(text) + " "
    return any(" " + normalize(q) + " " in haystack for q in keywords)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise BotError("API chuyển hướng bất thường; dừng để bảo vệ token.")


class ThreadsAPI:
    def __init__(self, token):
        if not token or any(c.isspace() for c in token):
            raise BotError("Thiếu hoặc sai định dạng THREADS_ACCESS_TOKEN trong GitHub Secrets.")
        self.token = token
        self.opener = urllib.request.build_opener(NoRedirect)

    def request(self, method, path, params=None):
        url = BASE + "/" + path.lstrip("/")
        params = dict(params or {})
        encoded = urllib.parse.urlencode(params).encode()
        headers = {"Authorization": "Bearer " + self.token}
        if method == "GET":
            url += ("?" + encoded.decode()) if encoded else ""
            body = None
        else:
            body = encoded
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=45) as response:
                data = json.load(response)
        except urllib.error.HTTPError as exc:
            # Deliberately do not log the URL or raw response: they can contain secrets.
            try:
                error = json.loads(exc.read()).get("error", {})
                code = error.get("code", "unknown")
                if not isinstance(code, int):
                    code = "unknown"
            except (ValueError, AttributeError):
                code = "unknown"
            raise BotError(f"Threads HTTP {exc.code}, mã API {code}. Dừng đợt chạy; kiểm tra quyền, quota và tài khoản.") from None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            raise BotError("Không xác nhận được phản hồi API. Không tự gửi lại yêu cầu.") from None
        if not isinstance(data, dict) or "error" in data:
            raise BotError("API trả dữ liệu lỗi hoặc không đúng định dạng.")
        return data

    def me(self):
        data = self.request("GET", "me", {"fields": "id,username"})
        if not valid_id(data.get("id")) or not isinstance(data.get("username"), str):
            raise BotError("Không xác định được tài khoản Threads.")
        return data

    def search(self, keyword, since, max_pages):
        params = {"q": keyword, "search_type": "RECENT", "search_mode": "KEYWORD",
                  "limit": 50, "since": int(since.timestamp()),
                  "fields": "id,text,username,permalink,timestamp,is_reply"}
        seen_pages = set()
        for _ in range(max_pages):
            data = self.request("GET", "keyword_search", params)
            posts = data.get("data")
            if not isinstance(posts, list):
                raise BotError("Kết quả tìm kiếm không hợp lệ.")
            yield from posts
            paging = data.get("paging")
            if paging is None:
                break
            if not isinstance(paging, dict):
                raise BotError("Dữ liệu phân trang API không hợp lệ.")
            next_url = paging.get("next")
            if not next_url:
                break
            try:
                if not isinstance(next_url, str):
                    raise ValueError()
                parsed = urllib.parse.urlsplit(next_url)
                port = parsed.port
            except ValueError:
                raise BotError("Đường dẫn phân trang API không hợp lệ.") from None
            if (parsed.scheme != "https" or parsed.hostname != "graph.threads.net"
                    or port not in (None, 443) or parsed.username or parsed.password
                    or parsed.path.rstrip("/") not in ("/v1.0/keyword_search", "/keyword_search")):
                raise BotError("Đường dẫn phân trang API không hợp lệ.")
            # Only use server-provided pagination; remove any token embedded in its URL.
            params = dict(urllib.parse.parse_qsl(parsed.query))
            params.pop("access_token", None)
            params.pop("appsecret_proof", None)
            signature = tuple(sorted(params.items()))
            if signature in seen_pages:
                break
            seen_pages.add(signature)

    def remaining_replies(self):
        data = self.request("GET", "me/threads_publishing_limit", {
            "fields": "reply_quota_usage,reply_config"})
        try:
            item = data["data"][0]
            used, total = item["reply_quota_usage"], item["reply_config"]["quota_total"]
            if type(used) is not int or type(total) is not int or min(used, total) < 0:
                raise ValueError()
        except (KeyError, IndexError, TypeError, ValueError):
            raise BotError("Không đọc được quota bình luận; không gửi.") from None
        return max(0, total - used)

    def create_reply(self, post_id, text, image_url=None):
        params = {"media_type": "IMAGE" if image_url else "TEXT", "text": text, "reply_to_id": post_id}
        if image_url:
            params["image_url"] = image_url
        data = self.request("POST", "me/threads", params)
        if not valid_id(data.get("id")):
            raise BotError("API chưa xác nhận ID bình luận nháp.")
        return data["id"]

    def wait_ready(self, container_id):
        for attempt in range(15):
            data = self.request("GET", container_id, {"fields": "status,error_message"})
            status = data.get("status")
            if status == "FINISHED":
                return
            if status != "IN_PROGRESS":
                raise BotError("Bình luận nháp chưa sẵn sàng hoặc đã lỗi; dừng đợt chạy.")
            if attempt < 14:
                time.sleep(2)
        raise BotError("Hết thời gian chờ bình luận nháp; không tự gửi lại.")

    def publish(self, container_id):
        data = self.request("POST", "me/threads_publish", {"creation_id": container_id})
        if not valid_id(data.get("id")):
            raise BotError("Chưa xác nhận được kết quả gửi bình luận.")
        return data["id"]

    def post_details(self, reply_id):
        data = self.request("GET", reply_id, {"fields": "id,text,username,permalink,media_type,is_reply"})
        if data.get("id") != reply_id or not isinstance(data.get("permalink"), str):
            raise BotError("Không xác nhận được đường dẫn bình luận đã gửi.")
        return data


def valid_id(value):
    return isinstance(value, str) and value.isascii() and value.isdigit()


class State:
    def __init__(self, path, allow_missing=False):
        self.path = Path(path)
        self.data = read_json(path) if self.path.exists() else None
        if self.data is None:
            if not allow_missing:
                raise BotError("Thiếu state. Khởi tạo bằng tùy chọn initialize_state ở lần chạy đầu tiên.")
            self.data = {"version": 1, "account_id": None, "sent": [], "pending": {}}
        self.validate()

    def validate(self):
        d = self.data
        if (not isinstance(d, dict) or type(d.get("version")) is not int or d.get("version") != 1
                or not isinstance(d.get("sent"), list) or not isinstance(d.get("pending"), dict)
                or "account_id" not in d
                or (d.get("account_id") is not None and not valid_id(d.get("account_id")))):
            raise BotError("State sai cấu trúc. Không xóa state để chạy lại.")
        ids = set()
        for entry in d["sent"]:
            if not isinstance(entry, dict) or not valid_id(entry.get("post_id")) or not valid_id(entry.get("reply_id")):
                raise BotError("Lịch sử gửi bị lỗi.")
            if entry["post_id"] in ids:
                raise BotError("Lịch sử chứa ID bài trùng.")
            ids.add(entry["post_id"])
            timestamp(entry.get("sent_at"))
        for post_id, entry in d["pending"].items():
            if not valid_id(post_id) or post_id in ids or not isinstance(entry, dict):
                raise BotError("Danh sách giữ chỗ bị lỗi.")
            timestamp(entry.get("reserved_at"))
        if d.get("account_id") is None and (d["sent"] or d["pending"]):
            raise BotError("State có lịch sử nhưng thiếu tài khoản.")

    def bind(self, account_id):
        if self.data["account_id"] not in (None, account_id):
            raise BotError("Token thuộc tài khoản khác với state. Cần repo/state riêng cho từng tài khoản.")
        self.data["account_id"] = account_id

    def save(self):
        self.validate()
        write_json(self.path, self.data)

    def blocked_ids(self):
        return {e["post_id"] for e in self.data["sent"]} | set(self.data["pending"])

    def remaining(self, cap, current):
        cutoff = current - dt.timedelta(hours=24)
        # Pending results remain uncertain even if a runner died long after reserving them.
        # Count every pending item until it is manually reconciled, never guess its send time.
        used = sum(timestamp(e["sent_at"]) > cutoff for e in self.data["sent"])
        used += len(self.data["pending"])
        return max(0, cap - used)


def checkpoint():
    script = os.environ.get("THREADS_STATE_CHECKPOINT")
    if script:
        try:
            subprocess.run(["bash", script], check=True, timeout=90)
        except (OSError, subprocess.SubprocessError):
            raise BotError("Không lưu được state lên GitHub. Dừng gửi để tránh trùng.") from None


def plan_replies(api, state, config, comments, current):
    since = current - dt.timedelta(hours=config["max_post_age_hours"])
    blocked, found = state.blocked_ids(), {}
    me = api.me()
    state.bind(me["id"])
    for query in config["keywords"]:
        for post in api.search(query, since, config["max_pages_per_keyword"]):
            if not isinstance(post, dict) or not valid_id(post.get("id")):
                continue
            post_id = post["id"]
            text = post.get("text", "")
            if (post_id in blocked or post_id in found or post.get("is_reply") is not False
                    or post.get("username") == me["username"] or not isinstance(text, str)
                    or not matches(text, config["keywords"])):
                continue
            try:
                created = timestamp(post.get("timestamp"))
            except BotError:
                continue
            if created < since or created > current:
                continue
            found[post_id] = {"post_id": post_id, "username": post.get("username"),
                              "permalink": post.get("permalink"), "post_text": text,
                              "timestamp": created.isoformat(), "source_keyword": query}
    limit = min(config["max_per_run"], state.remaining(config["max_per_24h"], current))
    posts = sorted(found.values(), key=lambda p: p["timestamp"], reverse=True)[:limit]
    offset = len(state.data["sent"])
    for i, post in enumerate(posts):
        post["comment"] = comments[(offset + i) % len(comments)] if comments else None
        post["image_url"] = config.get("image_url")
    return posts


def save_proof(api, reply_id, post, report):
    from proof import ProofError, capture_proof
    try:
        details = api.post_details(reply_id)
        if (details.get("text") != post["comment"] or not details.get("username")
                or details.get("is_reply") is not True
                or (post.get("image_url") and details.get("media_type") != "IMAGE")):
            raise BotError("Dữ liệu bình luận đã gửi chưa khớp để chụp ảnh.")
        output = f"screenshots/{reply_id}.png"
        capture_proof(details["permalink"], post["comment"], details["username"],
                      bool(post.get("image_url")), output)
        report.setdefault("proofs", []).append({"reply_id": reply_id, "permalink": details["permalink"], "screenshot": output})
    except (ProofError, BotError) as exc:
        report.setdefault("proof_failed", []).append({"reply_id": reply_id, "reason": str(exc)})
        raise BotError("Bình luận đã gửi nhưng chưa chụp được ảnh xác nhận. Dừng các bài tiếp theo; không đăng lại.") from None


def send_plan(api, state, plan, config, report):
    limit = min(len(plan), api.remaining_replies(), state.remaining(config["max_per_24h"], now()))
    plan = plan[:limit]
    if not plan:
        return
    reserved_at = now().isoformat()
    for post in plan:
        state.data["pending"][post["post_id"]] = {"status": "reserved", "reserved_at": reserved_at}
    state.save()
    checkpoint()  # Remote reservations MUST succeed before the first write to Threads.
    attempted = set()
    try:
        for i, post in enumerate(plan):
            if i:
                time.sleep(config["interval_seconds"])
            post_id = post["post_id"]
            attempted.add(post_id)
            entry = state.data["pending"][post_id]
            entry["status"] = "creating"
            state.save()
            if config.get("image_url"):
                container_id = api.create_reply(post_id, post["comment"], image_url=config["image_url"])
            else:
                container_id = api.create_reply(post_id, post["comment"])
            entry.update(status="container_created", container_id=container_id)
            state.save()
            api.wait_ready(container_id)
            entry["status"] = "publishing"
            state.save()
            reply_id = api.publish(container_id)
            receipt = {"post_id": post_id, "reply_id": reply_id, "sent_at": now().isoformat()}
            if config.get("screenshots"):
                receipt["proof_status"] = "pending"
            state.data["sent"].append(receipt)
            del state.data["pending"][post_id]
            state.save()
            report["sent"].append(receipt)
            print(f"Đã gửi {len(report['sent'])}/{limit} bình luận.", flush=True)
            if config.get("screenshots"):
                try:
                    save_proof(api, reply_id, post, report)
                except BotError:
                    receipt["proof_status"] = "failed"
                    state.save()
                    raise
                receipt["proof_status"] = "captured"
                state.save()
    finally:
        # Only release targets that never reached any API write attempt.
        for post in plan:
            if post["post_id"] not in attempted:
                state.data["pending"].pop(post["post_id"], None)
        state.save()
        checkpoint()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("preview", "live"), default="preview")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--comments", default="comments.json")
    parser.add_argument("--state", default="state/state.json")
    parser.add_argument("--report", default="report.json")
    parser.add_argument("--init-state", action="store_true")
    args = parser.parse_args(argv)
    report = {"mode": args.mode, "created_at": now().isoformat(), "plan": [], "sent": []}
    try:
        if args.init_state:
            if Path(args.state).exists():
                raise BotError("State đã tồn tại; không ghi đè.")
            State(args.state, allow_missing=True).save()
            return 0
        config = load_config(args.config)
        if args.mode == "live" and not config["enabled"]:
            report["status"] = "disabled"
            print("Tool đang tắt. Đặt enabled=true sau khi kiểm tra preview.")
            return 0
        comments = load_comments(args.comments)
        if args.mode == "live" and not comments:
            raise BotError("Chưa có nội dung. Thêm bình luận của bạn vào comments.json trước khi gửi.")
        if args.mode == "live" and config.get("require_image") and not config.get("image_url"):
            raise BotError("Chưa có ảnh đính kèm. Cần image_url HTTPS công khai trước khi gửi.")
        state = State(args.state, allow_missing=args.mode == "preview")
        if args.mode == "live" and config.get("screenshots"):
            if any(entry.get("proof_status") in ("pending", "failed") for entry in state.data["sent"]):
                raise BotError("Có bình luận đã gửi nhưng thiếu ảnh xác nhận. Cần kiểm tra và xử lý trước khi gửi tiếp.")
            try:
                import playwright.sync_api  # noqa: F401; check before any public write
            except ImportError:
                raise BotError("Thiếu Playwright để chụp ảnh. Chưa gửi bình luận nào trong lượt này.") from None
        api = ThreadsAPI(os.environ.get("THREADS_ACCESS_TOKEN", ""))
        report["plan"] = plan_replies(api, state, config, comments, now())
        report["blocked_pending"] = len(state.data["pending"])
        print(f"Tìm được {len(report['plan'])} bài phù hợp cho đợt này.")
        if args.mode == "live" and report["plan"]:
            send_plan(api, state, report["plan"], config, report)
        report["status"] = "ok"
        return 0
    except BotError as exc:
        report.update(status="error", error=str(exc))
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        if not args.init_state:
            write_json(args.report, report)


if __name__ == "__main__":
    sys.exit(main())
