---
name: before-after-video
description: Records before/after MP4 videos of a UI change (visible mouse pointer, click rings, key-press box, captions) plus a side-by-side version, and can post them to a GitHub PR/issue or a ClickUp ticket. Use when asked to record or show the before/after of a UI change, or a demo video of a change for a ticket or PR.
argument-hint: "[PR/issue/ticket URL to post to]"
---

# Before/after video

Two MP4s — **before** (old code) and **after** (new code) — that replay the **same flow** with real input events, plus one **side-by-side** MP4. Headless video has no pointer, so `scripts/recorder.py` draws one: a pointer arrow that glides to each target, a red ring on every click, a yellow "Keys pressed" box (password fields show `•`), a caption bar, and a BEFORE/AFTER badge.

The scripts live in `${CLAUDE_SKILL_DIR}/scripts`. Outside Claude Code that variable is not filled in: use the `scripts/` folder next to this SKILL.md.

## Steps

0. **Check the tools.** `uv --version`, `ffmpeg -version`, and Google Chrome installed (without Chrome, pass `channel=None` to `Recorder` and run `uv run --with "playwright>=1.59" playwright install chromium`). Done when all three are there.

1. **Run the app locally** and seed the data the flow needs (test users, rows). Write the seed as a re-runnable reset script: both takes must start from identical data. Done when one command restores the start state.

2. **Write one flow script** for both takes, switching on the mode (`before`/`after`). Copy [`examples/payroll_flow.py`](examples/payroll_flow.py) as the template; `recorder.py` is imported, not copied:

   ```python
   from recorder import Recorder
   with Recorder(mode, out_dir, topic=topic) as r:   # r.page is the Playwright page
       r.goto(url); r.click(locator); r.type("-321504")
       r.caption(f"{mode.upper()}: what to look at"); r.pause(3)
   ```

   Run it with Playwright ≥ 1.59 (sharper capture through `page.screencast`; older versions fall back to the blurrier built-in recorder):

   ```bash
   PYTHONPATH="${CLAUDE_SKILL_DIR}/scripts" uv run --with "playwright>=1.59" python flow.py after OUT --topic <topic>
   ```

   - Drive every interaction through `r.click` / `r.type` / `r.press` / `r.scroll(dx=…, over=…)` — real events, so bugs that only real key presses trigger show up. Wait with `r.pause`, never `time.sleep` (sleep drops frames).
   - Narrate each step with `r.caption(...)`: say what is pressed, then what happened. Point at the evidence with `r.move_to(...)` and hold `r.pause(3–5)`.
   - When the key moment is a single key, type it alone, pause, caption the result, then type the rest.
   - Use `r.caption(..., top=True)` when the evidence sits at the bottom of the screen.
   - Type OTPs, tokens and keys with `r.type(..., secret=True)` so the key box shows dots.
   - Hash-routed SPAs never fire `load`: wait with `page.wait_for_function("location.hash.startsWith('#…')")`.

   Done when the after take runs end to end on the current code and prints `OUT/<topic>_AFTER.mp4`.

3. **Record the before take on the old code.**
   - Find the base: `git merge-base HEAD origin/main` (or the commit the user names).
   - Check the changed files are safe to swap: `git status --porcelain -- <changed frontend paths>` must print nothing. If it prints files, stop and ask the user to commit, or run `git stash push -- <paths>` with their OK.
   - `git checkout <base> -- <paths>` (a dev server hot-reloads them), reset data, run the flow with `before`. Then `git checkout HEAD -- <paths>` (and `git stash pop` if you stashed), reset data, run the flow with `after`.
   - If the change also touches backend code or migrations, swapping only frontend files gives a wrong before take: say so and swap those too, or ask.

   Done when both MP4s exist and `git status` shows only what was there before you started.

4. **Make the side-by-side:** `python3 ${CLAUDE_SKILL_DIR}/scripts/compose.py OUT --topic <topic>` → `OUT/<topic>_SIDE_BY_SIDE.mp4`. Add `--gif` only when the user asks for a GIF (READMEs, email). Done when the file prints with its size.

5. **Check the frames** of both takes before sharing. For each MP4, read its length with `ffprobe -v error -show_entries format=duration -of csv=p=0 X.mp4`, then
   `ffmpeg -i X.mp4 -vf "fps=16/<length>,scale=720:-1,tile=4x4" -frames:v 1 X_sheet.png` and Read the PNG. Done when every caption's claim is visible in a frame, the pointer is on the evidence, and no secret appears on screen.

6. **Deliver.** By default, save only: copy `<topic>_BEFORE.mp4`, `<topic>_AFTER.mp4` and `<topic>_SIDE_BY_SIDE.mp4` to `~/Downloads/` (add `_v2`… for re-takes) and give the user the paths. Post only when the user names a place:
   - GitHub PR or issue → [share/github.md](share/github.md)
   - ClickUp task → [share/clickup.md](share/clickup.md)
   - Anything else → give the paths and say posting there is not automated yet.

   Done when the user has the paths (and the post URL, if posted).

## Gotchas

- Over 10 MB, GitHub's free plan refuses the video. `recorder.py` and `compose.py` print each file's size; re-record with `Recorder(..., crf=26)` or compose with `--crf 26` to shrink it.
- `Recorder` takes the first match of a locator, so a text that appears twice will not abort the take — but check the pointer landed on the intended one. A locator that matches nothing fails after 10 s with `not visible: …`.
- A take that raises leaves no MP4 (on the fallback path the raw WebM stays in `OUT/_<mode>_raw/`). Fix the flow and re-run from the data reset.
- Playwright's bundled browser build often mismatches the installed package (`Executable doesn't exist … playwright install`). `channel="chrome"` (the default) sidesteps it.
