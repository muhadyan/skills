---
name: before-after-video
description: Before/after demo videos of a UI change. Use when asked to record, show or post the before/after of a UI change, or a demo video of a change for a PR, issue or ticket.
argument-hint: "[PR/issue/ticket URL to post to]"
---

# Before/after video

Two MP4s, **before** (old code) and **after** (new code), replay the **same flow** with real input events. A third MP4 shows them **side by side**. Headless video has no pointer, so `scripts/recorder.py` draws one. It also draws a red ring on every click, a yellow "Keys pressed" box (password fields show `•`), a caption bar, a BEFORE/AFTER badge, and a "Browser alert" box for native dialogs.

The scripts live in `${CLAUDE_SKILL_DIR}/scripts`. Outside Claude Code that variable is not filled in: use the `scripts/` folder next to this SKILL.md.

## Steps

0. **Check the tools.** Run `uv --version` and `ffmpeg -version`, and check that Google Chrome is installed. Without Chrome, or when the flow opens a new tab, install Playwright's own browser: `uv run --with "playwright>=1.59" playwright install chromium-headless-shell`. Then pass `channel=None` to `Recorder` (without Chrome) or `popups=True` (new tab). Done when all of them are there.

1. **Make the takes safe and repeatable.** Run the app locally.
   - Write a reset script that restores the start data, including rows a take deletes or adds, and prints a row count. Both takes start from it.
   - Turn off outbound email, chat and push in the local backend. Each take runs the flow for real. Env vars set on the command line override the `.env` file.
   - Use fake or anonymised data. If real names or emails would show, anonymise the local copy, or blur them (see [FLOWS.md](FLOWS.md)).
   - Make sure nothing else writes to the database during a take, such as test runs or review agents.

   Done when one command resets the data and prints the count you expect, and no message can leave the machine.

2. **Write one flow script** for both takes. It switches on the mode (`before`/`after`). Copy [`examples/demo_flow.py`](examples/demo_flow.py) as the template. It runs against the demo app in `examples/demo-app/`. Import `recorder.py`; do not copy it.

   ```python
   from recorder import Recorder
   with Recorder(mode, out_dir, topic=topic) as r:   # r.page is the Playwright page
       r.goto(url); r.click(locator); r.type("150")
       r.show(evidence_locator, f"{mode.upper()}: what the viewer should see")
   ```

   - Use `r.show(evidence, caption, value=…)` for every claim. It waits until the evidence is on screen, points at it, captions it and holds. Missing evidence fails the take, so a caption cannot claim what the screen does not show. Use `r.caption(...)` only for narration that claims nothing ("press Save").
   - Write each BEFORE caption only after you have seen the old screen, not from the ticket text. Run the before take once, read its stills (step 5), then fix the captions.
   - Drive every interaction through `r.click`, `r.type`, `r.press`, `r.select_all` and `r.scroll(dx=…, over=…)`. These send real events, so bugs that only real key presses trigger still show. Wait with `r.pause` or a locator's `wait_for`, never with `time.sleep`, which drops frames.
   - For slow loads, popups, alerts, locale, polling pages, login, personal data and two users, see [FLOWS.md](FLOWS.md).

   Run the flow with Playwright 1.59 or newer. Older versions fall back to a blurrier recorder that cannot cut.

   ```bash
   PYTHONPATH="${CLAUDE_SKILL_DIR}/scripts" uv run --with "playwright>=1.59" python flow.py after OUT --topic <topic>
   ```

   Done when the after take runs end to end on the current code and prints `OUT/<topic>_AFTER.mp4`.

3. **Run the old code next to the new code** for the before take, on its own ports, from a git worktree. Follow [OLD-CODE.md](OLD-CODE.md). The flow picks the URL for each mode. Reset the data, record `before`, reset again, record `after`. Done when both MP4s exist and `git status` in the user's checkout shows only what was there before you started.

4. **Make the side-by-side:** `python3 ${CLAUDE_SKILL_DIR}/scripts/compose.py OUT --topic <topic>`. It writes `OUT/<topic>_SIDE_BY_SIDE.mp4` and a contact sheet for each take (`OUT/<topic>_BEFORE_sheet.png`). Add `--gif` only when the user asks for a GIF (READMEs, email). Done when the MP4 path prints with its size.

5. **Check every caption still** before you share. Each take writes `OUT/<topic>_<MODE>_stills/NN.jpg` (the last frame of each caption) and `captions.txt` (still name, tab, caption). Read every still next to its caption, then read both sheets. Done when every claim is visible in its still, the pointer is on the evidence, every frame is whole (the badge is in its corner), and no secret or personal data is on screen. If a still fails, fix the flow and record again from the data reset.

6. **Deliver.** By default, only save the files. Copy `<topic>_BEFORE.mp4`, `<topic>_AFTER.mp4` and `<topic>_SIDE_BY_SIDE.mp4` to `~/Downloads/`, with `_v2`… for re-takes, and give the user the paths. Post only when the user names a place:
   - GitHub PR or issue → [share/github.md](share/github.md)
   - ClickUp task, comment or thread reply → [share/clickup.md](share/clickup.md)
   - Anything else → give the paths and say posting there is not automated yet.

   Done when the user has the paths, and the post URL if you posted.

## Gotchas

- GitHub's free plan refuses videos over 10 MB. `recorder.py` and `compose.py` print each file's size. To shrink a video, record again with `Recorder(..., crf=26)` or compose with `--crf 26`.
- `Recorder` uses the first match of a locator, so a text that appears twice does not stop the take. Check in the still that the pointer landed on the right one. A locator that matches nothing fails after 10 s with `not visible: …`.
- A take that raises leaves no MP4. On the fallback path the raw WebM stays in `OUT/_<mode>_raw/`. Fix the flow and run it again from the data reset.
- `Recorder` answers native dialogs itself. By default it dismisses them, as Playwright does. A "leave this page?" dialog is always accepted, so navigation cannot hang. Use `dialogs="accept"` to click OK on a `confirm()`. Read the messages from `r.dialogs`. If the flow adds its own `page.on("dialog")` handler, that handler answers, and the recorder only records the message.
- Playwright's bundled browser often does not match the installed package (`Executable doesn't exist … playwright install`). `channel="chrome"`, the default, avoids this.
- Run flows with plain `python`, not `python -I`. `-I` ignores `PYTHONPATH`, so `from recorder import Recorder` fails.
- Stop the servers you started by PID or port (`kill <pid>`, `lsof -ti tcp:<port>`). Do not use `pkill -f <name>`: other sessions may run the same tools.
