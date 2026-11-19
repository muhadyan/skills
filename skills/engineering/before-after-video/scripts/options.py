"""Browser launch and context options for Recorder (no Playwright import, so testable)."""
from __future__ import annotations

import copy
from typing import Any, Mapping, Optional

# The recorder sizes the screencast from these, so a caller must not change them behind its back.
RECORDER_CONTEXT_KEYS = frozenset({"viewport", "record_video_dir", "record_video_size"})


def launch_kwargs(channel: Optional[str], *, popups: bool = False,
                  launch_options: Optional[Mapping[str, Any]] = None) -> dict:
    """Keyword arguments for ``chromium.launch``; the caller's ``launch_options`` win.

    ``popups=True`` drops the channel, so Playwright starts its own headless
    shell: in Google Chrome's new headless mode, every screencast frame comes
    out zoomed and cropped once the page has opened a new tab.
    """
    kw: dict = {"channel": channel} if channel and not popups else {}
    kw.update(copy.deepcopy(dict(launch_options or {})))
    return kw


def context_kwargs(size: Mapping[str, int], *, raw_dir: Optional[str] = None,
                   context_options: Optional[Mapping[str, Any]] = None) -> dict:
    """Keyword arguments for ``browser.new_context``. ``raw_dir`` turns on the video fallback."""
    clash = sorted(RECORDER_CONTEXT_KEYS & set(context_options or {}))
    if clash:
        raise ValueError(f"set {', '.join(clash)} through Recorder(width=, height=, native=), not context_options")
    kw: dict = {"viewport": dict(size)}
    if raw_dir is not None:
        kw.update(record_video_dir=str(raw_dir), record_video_size=dict(size))
    kw.update(copy.deepcopy(dict(context_options or {})))
    return kw
