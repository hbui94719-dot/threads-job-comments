"""Offline verification of screenshot boundary/failure behavior."""
import sys
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch

import proof


URL = "https://www.threads.com/@test_account/post/AbCd123"
TEXT = "Nội dung đã soạn sẵn."
PNG = b"\x89PNG\r\n\x1a\nreal browser bytes mocked in unit test"


class ProofTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / "proof.png"
        self.runtime = MagicMock()
        self.browser = self.runtime.chromium.launch.return_value
        self.context = self.browser.new_context.return_value
        self.page = self.context.new_page.return_value
        self.page.url = URL
        self.page.goto.return_value.status = 200
        self.element = self.page.evaluate_handle.return_value.as_element.return_value
        self.element.evaluate.return_value = True
        self.element.screenshot.side_effect = lambda **kwargs: Path(kwargs["path"]).write_bytes(PNG)
        manager = MagicMock()
        manager.__enter__.return_value = self.runtime
        module = types.ModuleType("playwright.sync_api")
        module.sync_playwright = MagicMock(return_value=manager)
        self.modules = patch.dict(sys.modules, {"playwright": types.ModuleType("playwright"), "playwright.sync_api": module})
        self.modules.start()
        self.addCleanup(self.modules.stop)

    def capture(self, image=True):
        return proof.capture_proof(URL, TEXT, "test_account", image, self.output)

    def test_external_hosts_and_wrong_authors_rejected_before_browser_launch(self):
        for url in ["https://attacker.example/@test_account/post/AbCd123",
                    "https://www.threads.com.attacker.example/@test_account/post/AbCd123",
                    "https://www.threads.com/@another/post/AbCd123",
                    "http://www.threads.com/@test_account/post/AbCd123",
                    "https://secret@www.threads.com/@test_account/post/AbCd123",
                    "https://www.threads.com:444/@test_account/post/AbCd123"]:
            with self.subTest(url=url), self.assertRaises(proof.ProofError):
                proof.capture_proof(url, TEXT, "test_account", True, self.output)
        self.runtime.chromium.launch.assert_not_called()

    def test_login_redirect_is_not_screenshot_proof(self):
        self.page.url = "https://www.threads.com/login"
        with self.assertRaises(proof.ProofError):
            self.capture()
        self.element.screenshot.assert_not_called()
        self.assertFalse(self.output.exists())
        self.browser.close.assert_called_once()

    def test_missing_full_text_or_image_times_out_without_screenshot(self):
        # Playwright waits on the DOM predicate, which requires author, full
        # content, unique target permalink, and a non-avatar image if expected.
        self.page.wait_for_function.side_effect = TimeoutError("No matching reply")
        with self.assertRaises(proof.ProofError):
            self.capture()
        self.element.screenshot.assert_not_called()
        self.assertFalse(self.output.exists())
        predicate = self.page.wait_for_function.call_args.args[0]
        args = self.page.wait_for_function.call_args.kwargs["arg"]
        self.assertIn("naturalWidth", predicate)
        self.assertIn("postPaths.size !== 1", predicate)
        self.assertEqual(args["text"], TEXT)
        self.assertTrue(args["imageExpected"])

    def test_missing_element_is_failure(self):
        self.page.evaluate_handle.return_value.as_element.return_value = None
        with self.assertRaises(proof.ProofError):
            self.capture()
        self.assertFalse(self.output.exists())

    def test_verified_reply_saves_real_browser_screenshot(self):
        result = self.capture()
        self.assertEqual(self.output.read_bytes(), PNG)
        self.assertEqual(result["permalink"], URL)
        self.assertTrue(result["image_expected"])
        self.assertEqual(self.element.evaluate.call_count, 2)
        self.browser.close.assert_called_once()
        self.assertEqual(list(self.output.parent.glob(".threads-proof-*")), [])

    def test_text_only_reply_does_not_require_photo(self):
        self.capture(image=False)
        self.assertFalse(self.page.wait_for_function.call_args.kwargs["arg"]["imageExpected"])

    def test_content_changed_after_capture_discards_temp_image(self):
        self.element.evaluate.side_effect = [True, False]
        with self.assertRaises(proof.ProofError):
            self.capture()
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.output.parent.glob(".threads-proof-*")), [])

    def test_browser_error_does_not_produce_image_or_raw_error(self):
        self.page.goto.side_effect = RuntimeError("secret token should not leak")
        with self.assertRaises(proof.ProofError) as raised:
            self.capture()
        self.assertNotIn("secret", str(raised.exception))
        self.assertFalse(self.output.exists())

    def test_environment_can_select_installed_chromium(self):
        with patch.dict("os.environ", {"THREADS_CHROMIUM_PATH": "/usr/bin/chromium"}):
            self.capture()
        self.assertEqual(self.runtime.chromium.launch.call_args.kwargs["executable_path"], "/usr/bin/chromium")


if __name__ == "__main__":
    unittest.main()
