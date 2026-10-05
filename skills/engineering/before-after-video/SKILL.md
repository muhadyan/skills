---
name: before-after-video
description: Record before/after MP4 videos of a UI change (visible mouse pointer, click rings, key-press box, captions) and post them inside a ticket comment. Use when asked to record, capture or show the before/after of a change, a demo video, or a screen recording for a ticket or PR.
---

# Before/after video

Two MP4s — **before** (old code) and **after** (new code) — that replay the **same flow** with real input events, so a viewer sees exactly what a user gets. Headless video has no pointer, so `scripts/recorder.py` draws one: a pointer arrow that glides to each target, a red ring on every click, a yellow "Keys pressed" box (password fields show `•`), and a caption bar.

Tools: Python with the `playwright` package (any venv; `channel="chrome"` drives the installed Google Chrome, so no browser download), `ffmpeg`, and Claude in Chrome for the upload.

## Steps

1. **Run the app locally** and seed the data the flow needs (test users, rows). Write the seed as a re-runnable reset script: both takes must start from identical data. Done when one command restores the start state.

2. **Write one flow script** for both takes, switching on `MODE` (`before`/`after`). Start from [`examples/payroll_flow.py`](examples/payroll_flow.py). Import the helper by adding this skill's `scripts/` folder to `sys.path` (the path below is a manual install; a plugin or `npx skills` install puts the skill elsewhere, so use the folder this SKILL.md sits in):

   ```python
   sys.path.insert(0, str(Path.home() / ".claude/skills/before-after-video/scripts"))
   from recorder import Recorder
   with Recorder(MODE, OUT_DIR) as r:   # r.page is the Playwright page
       r.goto(url); r.click(locator); r.type("-321504")
       r.caption(f"{MODE.upper()}: what to look at"); r.pause(3)
   ```

   - Drive every interaction through `r.click` / `r.type` / `r.press` / `r.scroll(dx=…, over=…)` — real events, so bugs that only real key presses trigger show up.
   - Narrate each step with `r.caption(...)`: say what is pressed, then what happened. Point at the evidence with `r.move_to(...)` and hold `r.pause(3–5)`.
   - When the key moment is a single key, type it alone, pause, caption the result, then type the rest.
   - Use `r.caption(..., top=True)` when the evidence sits at the bottom of the screen.
   - Hash-routed SPAs never fire `load`: wait with `page.wait_for_function("location.hash.startsWith('#…')")`.

3. **Record the before take on the old code.** Put the old UI files back without touching history: `git checkout <base-commit> -- <changed frontend paths>` (a dev server hot-reloads them), reset data, run `python flow.py before OUT`. Then restore with `git checkout HEAD -- <same paths>`, reset data, run `python flow.py after OUT`. Done when `git status` shows only what was there before you started.

4. **Check the frames** before sharing:
   `ffmpeg -i OUT/before.mp4 -vf "fps=1/3.5,scale=720:-1,tile=4x4" -frames:v 1 sheet.png`, then Read the PNG. Done when every caption's claim is visible in a frame, the pointer is on the evidence, and no secret appears on screen.

5. **Post both MP4s inside one ticket comment.** See [ClickUp upload](#clickup-upload). Name files `<topic>_BEFORE.mp4` / `<topic>_AFTER.mp4` (add `_v2`… for re-takes). Copy them to `~/Downloads/` for the user.

## ClickUp upload

The ClickUp MCP has no comment-attachment call (`clickup_request_attachment_upload` attaches to the task, not a comment), so post through the web UI with Claude in Chrome. ClickUp's composer often ignores the extension's synthetic clicks and typing; drive it with page JavaScript, which is reliable:

1. Open the task URL; wait ~5 s.
2. Open the comment's attach menu and confirm the newest file input sits in the overlay:
   `document.querySelector('.comment-bar-root .cu-cloud-buttons-dropdown__toggle').click()` — the last `input[type=file]` must have a `cdk-overlay-container` ancestor (the others belong to the task's attachment area).
3. `find` that input ("file upload input inside the comment attachment dropdown"), then `file_upload` both MP4 paths to its ref (under 10 MB per call). Wait ~5 s.
4. Insert the caption text into the last block of `.comment-bar__editor [contenteditable=true]` with a Range + `document.execCommand('insertText', false, text)`. Keep it ASCII-friendly; check `editor.children` shows two video blocks and the text.
5. `document.querySelector('.comment-bar__send').click()`.
6. Done when `clickup_get_task_comments` returns a comment whose text contains both `….mp4?view=open` URLs. If an earlier comment points at older files, update it with `clickup_update_comment` (text-only comments are safe to rewrite this way).

Deleting old comments or attachments is permanent: leave it to the user and tell them which ones.

## Gotchas

- Playwright's bundled browser build often mismatches the installed package (`Executable doesn't exist … playwright install`). `channel="chrome"` (the default in `Recorder`) sidesteps it.
- `Recorder` takes the first match of a locator, so a text that appears twice will not abort the take — but check the pointer landed on the intended one.
- A take that raises leaves no MP4 (the raw WebM stays in `OUT/_<name>_raw/`). Fix the flow and re-run from the data reset.
