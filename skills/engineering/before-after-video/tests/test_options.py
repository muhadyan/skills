"""How Recorder builds the browser launch and context options."""
import unittest

import helpers  # noqa: F401  (puts scripts/ on the path)

from options import context_kwargs, launch_kwargs

SIZE = {"width": 1440, "height": 810}


class LaunchKwargsTest(unittest.TestCase):
    def test_chrome_channel_by_default(self):
        self.assertEqual(launch_kwargs("chrome"), {"channel": "chrome"})

    def test_no_channel_means_bundled_chromium(self):
        self.assertEqual(launch_kwargs(None), {})

    def test_popups_use_the_headless_shell(self):
        # Google Chrome's new headless mode crops every frame after a new tab opens
        self.assertEqual(launch_kwargs("chrome", popups=True), {})

    def test_caller_options_win(self):
        kw = launch_kwargs("chrome", popups=True, launch_options={"channel": "chrome", "slow_mo": 50})
        self.assertEqual(kw, {"channel": "chrome", "slow_mo": 50})

    def test_caller_dict_is_not_changed(self):
        opts = {"args": ["--lang=de-DE"]}
        kw = launch_kwargs("chrome", launch_options=opts)
        kw["args"].append("--x")
        self.assertEqual(opts, {"args": ["--lang=de-DE"]})


class ContextKwargsTest(unittest.TestCase):
    def test_viewport_only_on_screencast_path(self):
        self.assertEqual(context_kwargs(SIZE), {"viewport": SIZE})

    def test_fallback_path_records_video(self):
        kw = context_kwargs(SIZE, raw_dir="/tmp/raw")
        self.assertEqual(kw["record_video_dir"], "/tmp/raw")
        self.assertEqual(kw["record_video_size"], SIZE)

    def test_context_options_pass_through(self):
        kw = context_kwargs(SIZE, context_options={"locale": "de-DE", "timezone_id": "Europe/Berlin"})
        self.assertEqual(kw["locale"], "de-DE")
        self.assertEqual(kw["timezone_id"], "Europe/Berlin")
        self.assertEqual(kw["viewport"], SIZE)

    def test_size_keys_belong_to_the_recorder(self):
        for key in ("viewport", "record_video_dir", "record_video_size"):
            with self.assertRaisesRegex(ValueError, key):
                context_kwargs(SIZE, context_options={key: {}})

    def test_viewport_is_a_copy(self):
        kw = context_kwargs(SIZE)
        kw["viewport"]["width"] = 1
        self.assertEqual(SIZE["width"], 1440)


if __name__ == "__main__":
    unittest.main()
