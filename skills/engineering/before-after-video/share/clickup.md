# Post to a ClickUp task comment

The ClickUp MCP cannot attach a file to a comment: `mcp__clickup__clickup_request_attachment_upload` attaches to the task. So post through the web UI with Claude in Chrome. ClickUp's composer often ignores the extension's synthetic clicks and typing, so drive it with page JavaScript (`mcp__claude-in-chrome__javascript_tool`). The selectors below are as of 2026-11. If one matches nothing, inspect the composer with `mcp__claude-in-chrome__read_page` and adapt.

`BAR` below is the composer you post into:

- **New comment:** `document.querySelector('.comment-bar-root')`.
- **Reply in a thread:** see "Reply in a thread" below.

1. **Pick the browser.** If `mcp__claude-in-chrome__list_connected_browsers` lists more than one browser, ask the user which one to use, then call `select_browser`. Open the task URL in a new tab (`mcp__claude-in-chrome__navigate`) and wait about 5 s. `navigate` can return before the page is ready. Wait until `tabs_context_mcp` shows the task URL.

2. **Type the text first.** Focus `BAR.querySelector('[contenteditable=true]')`, then run `document.execCommand('insertText', false, text)`. Keep the text ASCII-friendly. ClickUp does not link PRs to the task on its own, so put the PR URL in the text.

   ⚠️ Text goes in BEFORE the video. If you run `insertText` on a draft that already holds a video, the whole draft is wiped, and the upload stays behind only as a task attachment.

3. **Attach the videos to the comment.**
   - Open the attach menu: `BAR.querySelector('.cu-cloud-buttons-dropdown__toggle').click()`.
   - Wait about 1.5 s, then tag the file input inside the overlay: `[...document.querySelectorAll('input[type=file]')].filter(i => i.closest('.cdk-overlay-container')).forEach(i => i.setAttribute('aria-label', 'COMMENT_OVERLAY_FILE_INPUT'))`.
   - `find` that exact label, then `mcp__claude-in-chrome__file_upload` the MP4 paths to its ref. Keep each call under 10 MB.
   - Upload the `~/Downloads` copies from the Deliver step. The upload tool only accepts files from folders shared with the session, so it may refuse paths under OUT.

   ⚠️ An untagged `find` can return the TASK's attachment input. The video then lands in the task's attachments, not in the comment.

4. **Check the draft.** Wait about 6 s. The editor must hold one `video` per file AND still contain your text, and `BAR.innerHTML` must contain each file name.

5. **Send:** `BAR.querySelector('.comment-bar__send').click()`.

6. **Check the post.** First make the window tall with `mcp__claude-in-chrome__resize_window` (about 1600×1000). In a short window, the Activity panel draws only history rows, not comments.
   - In the page, `[...document.querySelectorAll('video')].map(v => v.currentSrc || v.src)` must list one URL per file, each ending in its file name. An empty list right after sending is often just early: run the check once more, with a screenshot, before you doubt the post.
   - Through the API, `mcp__clickup__clickup_get_task_comments` must return the comment with your text. For a reply, use `mcp__clickup__clickup_get_threaded_comments(<parent comment id>)`. `comment_text` holds only the text, not the video URLs.

   Done when both checks pass. If an earlier comment points at older files, update it with `mcp__clickup__clickup_update_comment`. Comments with text only are safe to rewrite this way.

## Reply in a thread

1. Find the parent comment's id with `mcp__clickup__clickup_get_task_comments`.
2. Open its thread in the page. Find the comment on the page by its text (`mcp__claude-in-chrome__find` with a few words of it), and work inside that comment.
   - If the comment has replies, click its replies link: `[class*=_repliesText_]`, the "N replies" text.
   - If it has none, hover the comment and click the reply arrow in its toolbar.
   - A second composer appears.
3. Set `BAR` to the reply composer: `[...document.querySelectorAll('.comment-bar-root')].find(b => (b.querySelector('[contenteditable=true]')?.getAttribute('data-placeholder') || '').startsWith('Reply'))`. Then run steps 2–6 inside that `BAR`.
4. Check that the thread has one more reply, and that no new top-level comment appeared.

## Fallback

Use this when the composer cannot be driven, or no Chrome browser is connected.

- Upload each MP4 as a task attachment with `mcp__clickup__clickup_request_attachment_upload`.
- Post a comment that names the files: `mcp__clickup__clickup_create_comment`.
- Tell the user the videos are in the task's attachments, not inside the comment.

Deleting old comments or attachments is permanent. Leave it to the user, and tell them which ones.
