# Post to a ClickUp task comment

The ClickUp MCP cannot attach a file to a comment (`mcp__clickup__clickup_request_attachment_upload` attaches to the task), so post through the web UI with Claude in Chrome. ClickUp's composer often ignores the extension's synthetic clicks and typing; drive it with page JavaScript (`mcp__claude-in-chrome__javascript_tool`). The selectors below are as of 2026-10; if one matches nothing, inspect the composer with `mcp__claude-in-chrome__read_page` and adapt.

1. Open the task URL in a new tab (`mcp__claude-in-chrome__navigate`); wait ~5 s.
2. Open the comment's attach menu and confirm the newest file input sits in the overlay:
   `document.querySelector('.comment-bar-root .cu-cloud-buttons-dropdown__toggle').click()` — the last `input[type=file]` must have a `cdk-overlay-container` ancestor (the others belong to the task's attachment area).
3. `mcp__claude-in-chrome__find` that input ("file upload input inside the comment attachment dropdown"), then `mcp__claude-in-chrome__file_upload` the MP4 paths to its ref (under 10 MB per call). Upload the `~/Downloads` copies from the Deliver step: the upload tool only accepts files from folders shared with the session, so paths under OUT may be refused. Wait ~5 s.
4. Insert the caption text into the last block of `.comment-bar__editor [contenteditable=true]` with a Range + `document.execCommand('insertText', false, text)`. Keep it ASCII-friendly; check `editor.children` shows one video block per file and the text.
5. `document.querySelector('.comment-bar__send').click()`.
6. Check it in the page: `[...document.querySelectorAll('video')].map(v => v.currentSrc || v.src)` must list one URL per file, ending in each file name, and `mcp__clickup__clickup_get_task_comments` must return the comment with your text (its `comment_text` holds the text only, not the video URLs). Done when both checks pass. If an earlier comment points at older files, update it with `mcp__clickup__clickup_update_comment` (text-only comments are safe to rewrite this way).

**Fallback** when the composer cannot be driven: upload each MP4 as a task attachment with `mcp__clickup__clickup_request_attachment_upload`, then post a comment with `mcp__clickup__clickup_create_comment` that names the files. Tell the user the videos sit in the task's attachments, not inside the comment.

Deleting old comments or attachments is permanent: leave it to the user and tell them which ones.
