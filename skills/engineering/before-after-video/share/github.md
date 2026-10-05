# Post to a GitHub PR or issue

Uses `gh … comment --attach`, which uploads the videos to GitHub and puts an inline player in the comment.

1. **Check `gh`.** `gh --version` must be 2.99 or newer (`brew upgrade gh` otherwise), and `gh auth status` must show an account with push access to the repo. If the repo belongs to another logged-in account, run the commands with `GH_TOKEN=$(gh auth token -u <account>)`. Done when both checks pass.

2. **Check the size.** Each video must be under 10 MB on a free plan (100 MB on paid plans). Over the limit, re-run `compose.py --crf 26` or re-record with `Recorder(..., crf=26)`.

3. **Write the body** so each video is alone in its own paragraph — otherwise GitHub shows a link instead of a player:

   ```markdown
   **Before**: <one line on what goes wrong>

   ![](./<topic>_BEFORE.mp4)

   **After**: <one line on what changed>

   ![](./<topic>_AFTER.mp4)
   ```

   Lead with `<topic>_SIDE_BY_SIDE.mp4` instead when one video is enough.

4. **Post** from the folder that holds the videos, so the `./` paths match:

   ```bash
   gh pr comment <number-or-url> --body-file body.md --attach <topic>_BEFORE.mp4 --attach <topic>_AFTER.mp4
   ```

   For an issue use `gh issue comment`. To put the videos in the PR description instead, use `gh pr edit --body-file … --attach …`.

5. **Check it.** `gh` replaces each `![](./X.mp4)` with a bare `https://github.com/user-attachments/assets/…` URL, which GitHub renders as a player. Read the posted body with `gh issue view <n> --json comments -q '.comments[-1].body'` (same for `gh pr view`), and `curl -sI <url>` on each URL must return 302, not 404. Done when the comment URL is shown to the user.
