"""Offline checks for reply targeting, quotas, persistence and API boundaries."""
import copy
import datetime as dt
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import bot


CURRENT = dt.datetime(2026, 11, 11, 12, tzinfo=bot.UTC)
CONFIG = {
    "enabled": True, "keywords": ["công việc online", "job online", "tìm việc"],
    "max_per_24h": 500, "max_per_run": 12, "interval_seconds": 5,
    "max_pages_per_keyword": 3, "max_post_age_hours": 72,
}


def post(post_id="11", text="Mình đang tìm việc online", **overrides):
    data = {"id": post_id, "text": text, "username": "applicant",
            "permalink": "https://www.threads.com/@applicant/post/example",
            "timestamp": CURRENT.isoformat(), "is_reply": False}
    data.update(overrides)
    return data


def planned(*ids):
    return [{"post_id": post_id, "comment": "Nội dung do người dùng chuẩn bị"} for post_id in ids]


class FakeAPI:
    def __init__(self, posts=(), quota=1000):
        self.posts = list(posts)
        self.quota = quota
        self.created = []
        self.published = []
        self.fail_publish_number = None
        self.on_create = None

    def me(self):
        return {"id": "100", "username": "account_owner"}

    def search(self, keyword, since, max_pages):
        return iter(copy.deepcopy(self.posts))

    def remaining_replies(self):
        return self.quota

    def create_reply(self, post_id, text):
        if self.on_create:
            self.on_create(post_id)
        self.created.append((post_id, text))
        return "8" + post_id

    def wait_ready(self, container_id):
        pass

    def publish(self, container_id):
        if len(self.published) + 1 == self.fail_publish_number:
            raise bot.BotError("Không xác nhận được kết quả gửi")
        self.published.append(container_id)
        return "9" + container_id


class FilesCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state_path = self.root / "state.json"
        self.state = bot.State(self.state_path, allow_missing=True)
        self.state.bind("100")
        self.state.save()
        self.config = copy.deepcopy(CONFIG)

    def receipt(self, post_id, hours_ago=0):
        return {"post_id": post_id, "reply_id": "9" + post_id,
                "sent_at": (CURRENT - dt.timedelta(hours=hours_ago)).isoformat()}

    def reserve(self, post_id, hours_ago=0):
        self.state.data["pending"][post_id] = {
            "status": "publishing", "reserved_at": (CURRENT - dt.timedelta(hours=hours_ago)).isoformat()}


class ConfigurationTests(FilesCase):
    def test_valid_config_and_deduplicated_keywords(self):
        self.config["keywords"] = ["job online", "job online", " tìm việc "]
        path = self.root / "config.json"
        bot.write_json(path, self.config)
        self.assertEqual(bot.load_config(path)["keywords"], ["job online", "tìm việc"])

    def test_invalid_limits_booleans_and_empty_queries_are_rejected(self):
        path = self.root / "config.json"
        for key, value in [("max_per_24h", 501), ("max_per_run", True),
                           ("enabled", "true"), ("interval_seconds", 0),
                           ("keywords", [""]), ("max_pages_per_keyword", 11)]:
            with self.subTest(key=key, value=value):
                invalid = dict(CONFIG, **{key: value})
                bot.write_json(path, invalid)
                with self.assertRaises(bot.BotError):
                    bot.load_config(path)

    def test_comments_keep_user_content_and_reject_blank_or_overlong_items(self):
        path = self.root / "comments.json"
        bot.write_json(path, ["  Tôi có công việc phù hợp.  ", "Dòng 1\nDòng 2"])
        self.assertEqual(bot.load_comments(path), ["Tôi có công việc phù hợp.", "Dòng 1\nDòng 2"])
        for invalid in [[" "], ["x" * 501], [123], {}]:
            bot.write_json(path, invalid)
            with self.assertRaises(bot.BotError):
                bot.load_comments(path)

    def test_accent_case_punctuation_and_word_boundaries(self):
        self.assertTrue(bot.matches("Mình TÌM VIỆC, online", ["tim viec"]))
        self.assertTrue(bot.matches("Cần CÔNG VIỆC ONLINE!", ["cong viec online"]))
        self.assertTrue(bot.matches("Job-online phù hợp", ["job online"]))
        self.assertFalse(bot.matches("job onlinex", ["job online"]))
        self.assertFalse(bot.matches("xjob online", ["job online"]))
        self.assertFalse(bot.matches("Việc làm offline", CONFIG["keywords"]))


class StateTests(FilesCase):
    def test_rolling_quota_includes_pending_but_not_older_receipts(self):
        self.state.data["sent"] = [self.receipt("11", 2), self.receipt("12", 25)]
        self.reserve("13", 1)
        self.reserve("14", 25)
        self.assertEqual(self.state.remaining(5, CURRENT), 2)
        self.assertEqual(self.state.blocked_ids(), {"11", "12", "13", "14"})

    def test_quota_never_goes_negative(self):
        self.state.data["sent"] = [self.receipt("11"), self.receipt("12")]
        self.assertEqual(self.state.remaining(1, CURRENT), 0)

    def test_corrupt_or_missing_live_state_fails_closed(self):
        for invalid in ["not json", "{}", '{"version":1,"account_id":"100","sent":{},"pending":{}}']:
            with self.subTest(invalid=invalid):
                self.state_path.write_text(invalid)
                with self.assertRaises(bot.BotError):
                    bot.State(self.state_path)
        with self.assertRaises(bot.BotError):
            bot.State(self.root / "missing.json")

    def test_corrupt_timestamp_or_overlapping_history_is_rejected(self):
        self.state.data["sent"] = [self.receipt("11")]
        self.reserve("11")
        with self.assertRaises(bot.BotError):
            self.state.save()
        self.state.data["pending"] = {"12": {"reserved_at": "not a date"}}
        with self.assertRaises(bot.BotError):
            self.state.save()

    def test_different_account_cannot_reuse_state(self):
        with self.assertRaises(bot.BotError):
            self.state.bind("200")

    def test_init_never_overwrites_existing_history(self):
        before = self.state_path.read_bytes()
        with patch("sys.stderr", new=io.StringIO()):
            self.assertEqual(bot.main(["--init-state", "--state", str(self.state_path)]), 1)
        self.assertEqual(self.state_path.read_bytes(), before)


class TargetingTests(FilesCase):
    def test_only_fresh_matching_public_root_posts_survive(self):
        self.state.data["sent"] = [self.receipt("18")]
        self.reserve("19")
        posts = [
            post("11"), post("11"),
            post("12", "Muốn tìm việc", username="account_owner"),
            post("13", "Tìm việc", is_reply=True),
            post("14", "Tìm việc", timestamp=(CURRENT - dt.timedelta(hours=73)).isoformat()),
            post("15", "Đi du lịch thôi"),
            post("16", "Tìm việc", timestamp=(CURRENT + dt.timedelta(seconds=1)).isoformat()),
            post("17", "Tìm việc", timestamp="invalid"),
            post("18"), post("19"), post("20", "Tìm việc", is_reply=None),
            post("21", "Tìm việc", id="not-an-api-id"),
            post("22", "Có job online", timestamp=(CURRENT - dt.timedelta(minutes=1)).isoformat()),
        ]
        plan = bot.plan_replies(FakeAPI(posts), self.state, self.config, ["a", "b"], CURRENT)
        self.assertEqual([p["post_id"] for p in plan], ["11", "22"])
        self.assertEqual([p["comment"] for p in plan], ["b", "a"])

    def test_plan_obeys_run_and_rolling_caps(self):
        self.config.update(max_per_run=3, max_per_24h=3)
        self.state.data["sent"] = [self.receipt("90")]
        self.reserve("91")
        plan = bot.plan_replies(FakeAPI([post("11"), post("12"), post("13")]),
                                self.state, self.config, ["hello"], CURRENT)
        self.assertEqual(len(plan), 1)

    def test_preview_main_does_not_save_state_or_send(self):
        config_path, comments_path = self.root / "config.json", self.root / "comments.json"
        report_path = self.root / "report.json"
        bot.write_json(config_path, CONFIG)
        bot.write_json(comments_path, [])
        before = self.state_path.read_bytes()
        api = FakeAPI([post()])
        with patch.object(bot, "ThreadsAPI", return_value=api), patch.object(bot, "now", return_value=CURRENT), patch("sys.stdout", new=io.StringIO()):
            result = bot.main(["--mode", "preview", "--state", str(self.state_path),
                               "--config", str(config_path), "--comments", str(comments_path),
                               "--report", str(report_path)])
        self.assertEqual(result, 0)
        self.assertEqual(self.state_path.read_bytes(), before)
        self.assertEqual(api.created, [])
        self.assertIsNone(bot.read_json(report_path)["plan"][0]["comment"])


class DeliveryTests(FilesCase):
    def test_image_reply_uses_image_parameter(self):
        api = bot.ThreadsAPI("test-token")
        with patch.object(api, "request", return_value={"id": "123"}) as request:
            result = api.create_reply("11", "Nội dung", image_url="https://example.com/photo.jpg")
        self.assertEqual(result, "123")
        self.assertEqual(request.call_args.args[2], {
            "media_type": "IMAGE", "text": "Nội dung", "reply_to_id": "11",
            "image_url": "https://example.com/photo.jpg"})

    def test_screenshot_failure_keeps_sent_receipt_and_stops_batch(self):
        api = FakeAPI()
        self.config["screenshots"] = True
        with patch.object(bot, "save_proof", side_effect=bot.BotError("Chưa chụp được ảnh")):
            with self.assertRaises(bot.BotError):
                self.run_send(api, planned("11", "12"))
        disk = bot.read_json(self.state_path)
        self.assertEqual(len(api.published), 1)
        self.assertEqual(disk["sent"][0]["post_id"], "11")
        self.assertEqual(disk["sent"][0]["proof_status"], "failed")
        self.assertEqual(disk["pending"], {})
        self.assertIn("11", self.state.blocked_ids())

    def run_send(self, api, plan, checkpoint=None):
        report = {"sent": []}
        with patch.object(bot, "checkpoint", side_effect=checkpoint), patch.object(bot, "now", return_value=CURRENT), patch.object(bot.time, "sleep"), patch("sys.stdout", new=io.StringIO()):
            bot.send_plan(api, self.state, plan, self.config, report)
        return report

    def test_reservations_saved_and_checkpointed_before_first_api_write(self):
        api = FakeAPI()
        events = []

        def checkpoint():
            disk = bot.read_json(self.state_path)
            events.append(("checkpoint", set(disk["pending"])))

        def on_create(post_id):
            self.assertTrue(events)
            self.assertEqual(events[0], ("checkpoint", {"11", "12"}))
            self.assertIn(post_id, bot.read_json(self.state_path)["pending"])

        api.on_create = on_create
        report = self.run_send(api, planned("11", "12"), checkpoint)
        self.assertEqual(len(report["sent"]), 2)
        self.assertEqual(events[-1], ("checkpoint", set()))
        restored = bot.State(self.state_path)
        self.assertEqual(restored.blocked_ids(), {"11", "12"})

    def test_failed_remote_reservation_sends_nothing(self):
        api = FakeAPI()
        with self.assertRaises(bot.BotError):
            self.run_send(api, planned("11"), bot.BotError("push failed"))
        self.assertEqual(api.created, [])
        self.assertEqual(api.published, [])

    def test_uncertain_publish_is_blocked_on_next_plan(self):
        api = FakeAPI()
        api.fail_publish_number = 1
        with self.assertRaises(bot.BotError):
            self.run_send(api, planned("11", "12"))
        restored = bot.State(self.state_path)
        self.assertEqual(restored.data["pending"]["11"]["status"], "publishing")
        self.assertNotIn("12", restored.data["pending"])
        next_plan = bot.plan_replies(FakeAPI([post("11"), post("12")]), restored,
                                     self.config, ["hello"], CURRENT)
        self.assertEqual([p["post_id"] for p in next_plan], ["12"])

    def test_partial_batch_keeps_success_and_uncertainty_releases_unattempted(self):
        api = FakeAPI()
        api.fail_publish_number = 2
        with self.assertRaises(bot.BotError):
            self.run_send(api, planned("11", "12", "13"))
        restored = bot.State(self.state_path)
        self.assertEqual([e["post_id"] for e in restored.data["sent"]], ["11"])
        self.assertEqual(set(restored.data["pending"]), {"12"})
        self.assertEqual(restored.remaining(500, CURRENT), 498)
        self.assertEqual(len(api.created), 2)

    def test_live_api_quota_truncates_batch(self):
        api = FakeAPI(quota=1)
        report = self.run_send(api, planned("11", "12"))
        self.assertEqual([e["post_id"] for e in report["sent"]], ["11"])
        self.assertEqual(self.state.data["pending"], {})

    def test_zero_quota_does_not_reserve_or_send(self):
        api = FakeAPI(quota=0)
        before = self.state_path.read_bytes()
        report = self.run_send(api, planned("11"))
        self.assertEqual(report["sent"], [])
        self.assertEqual(api.created, [])
        self.assertEqual(self.state_path.read_bytes(), before)


class APIBoundaryTests(unittest.TestCase):
    def test_external_pagination_host_is_never_requested(self):
        api = bot.ThreadsAPI("fake-test-token")
        first = {"data": [], "paging": {"next": "https://attacker.example/keyword_search?after=x"}}
        with patch.object(api, "request", return_value=first) as request:
            with self.assertRaises(bot.BotError):
                list(api.search("job online", CURRENT, 3))
        self.assertEqual(request.call_count, 1)

    def test_server_pagination_strips_embedded_token(self):
        api = bot.ThreadsAPI("fake-test-token")
        responses = [
            {"data": [], "paging": {"next": "https://graph.threads.net/v1.0/keyword_search?after=cursor&q=job&access_token=secret&appsecret_proof=proof"}},
            {"data": []},
        ]
        with patch.object(api, "request", side_effect=responses) as request:
            self.assertEqual(list(api.search("job online", CURRENT, 3)), [])
        second_params = request.call_args_list[1].args[2]
        self.assertEqual(second_params, {"after": "cursor", "q": "job"})

    def test_redirect_is_rejected(self):
        with self.assertRaises(bot.BotError):
            bot.NoRedirect().redirect_request(None, None, 302, "", {}, "https://attacker.example")

    def test_unknown_reply_quota_fails_closed(self):
        api = bot.ThreadsAPI("fake-test-token")
        for invalid in [{"data": []}, {"data": [{"reply_quota_usage": 1}]},
                        {"data": [{"reply_quota_usage": True, "reply_config": {"quota_total": 1000}}]}]:
            with self.subTest(invalid=invalid), patch.object(api, "request", return_value=invalid):
                with self.assertRaises(bot.BotError):
                    api.remaining_replies()


if __name__ == "__main__":
    unittest.main()
