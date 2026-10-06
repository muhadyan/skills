---
name: session-journal
description: Logs every Claude Code and Codex session to an Obsidian vault (work done + lessons) through SessionStart/SessionEnd hooks, and exports brand-safe notes as a knowledge base for a content bot. Use when asked to set up the session journal, write the journal note now, look up past lessons or sessions in the vault, backfill old sessions, or debug why a note or export is missing.
---

# Session journal

Hooks run this automatically; the agent reaches this skill only for setup, a manual run, a vault lookup, or a fix.
Scripts live in `${CLAUDE_SKILL_DIR}/scripts` (outside Claude Code: the `scripts/` folder next to this file).
`J` below means `python3 ${CLAUDE_SKILL_DIR}/scripts/journal.py`.

## How it works

1. **SessionStart hook** (`J hook start --agent claude|codex`): adds a short context block (vault path + up to 10
   lessons from past sessions of the same project) and starts a detached `J sweep`.
2. **SessionEnd hook** (`J hook end --agent …`): starts a detached `J summarize <transcript>` and returns at once.
3. **summarize**: reads the transcript (prompts and replies only), skips sessions with fewer than `MIN_PROMPTS`
   real prompts or headless runs (`claude -p`, `codex exec`), asks a tool-less, settings-less `claude -p` for a
   JSON note, commits `sessions/YYYY/MM/<date>-<agent>-<id8>.md`, then pulls and pushes. Offline or on a rebase
   conflict the commit stays local and the next sync pushes it. Resumed sessions overwrite their note unless it
   has `locked: true`.
4. **sweep**: the backstop for sessions whose end hook never ran (crash, killed terminal). Summarizes transcripts
   idle for `IDLE_HOURS` that changed since they were last handled, oldest first, `--max` per run. State is
   `processed.json`; a transcript that fails 3 times at the same version is left alone.
5. **export**: the knowledge base. Only title, date, tags and the post angle leave the vault. Gates:
   - Gate 1, path: a note is `brand_safe` only when every folder the session worked in is under
     `BRAND_SAFE_ROOTS`; the model can only lower it, and export re-checks the note's `cwd`.
   - Gate 2, denylist: title, tags and post angle are matched against `DENYLIST` plus the export repo's
     `nda*` regex rules in `rules.json`. A missing or empty denylist, a bad regex or a missing `sessions/`
     stops the export. Deleting 5+ exported notes at once needs `J export --force`.
   - Gate 3, downstream: the bot's own rules and reviewer.
   Export only touches files it generated (marked `generated: session-journal`).

Every child process runs with `SESSION_JOURNAL=1`, so its own hooks do nothing (no recursion).
Logs: `~/.local/state/session-journal/journal.log`. State: `processed.json` in the same folder.

## Setup

1. Create `~/.config/session-journal/config.env`:
   ```
   VAULT=~/path/to/vault                      # a git clone; required
   BRAND_SAFE_ROOTS=~/Developer/personal:~/Developer/skills
   MODEL=claude-sonnet-5-5
   EXPORT_REPO=~/.local/share/session-journal/brand   # optional dedicated clone of the bot's content repo
   EXPORT_DIR=knowledge
   # DENYLIST defaults to $VAULT/_meta/nda-denylist.txt (one regex per line)
   ```
   Done when `J context` prints the vault path.
2. Add the hooks. Claude Code `~/.claude/settings.json` and Codex `~/.codex/hooks.json`, next to any existing ones:
   ```json
   "SessionStart": [{"hooks": [{"type": "command", "command": "python3 ~/.claude/skills/session-journal/scripts/journal.py hook start --agent claude", "timeout": 10}]}],
   "SessionEnd":   [{"hooks": [{"type": "command", "command": "python3 ~/.claude/skills/session-journal/scripts/journal.py hook end --agent claude", "timeout": 5}]}]
   ```
   Use `--agent codex` in the Codex file. Codex asks you to trust new hooks once (`/hooks`).
   Done when a new session shows "Session journal is on" in its context.
3. Backfill: `J sweep --days 30 --max 0` in the background. Then `J export`.

## Manual use

- Write this session's note now: `J summarize --agent claude <transcript_path>` (Claude transcripts are in
  `~/.claude/projects/<cwd-slug>/<session_id>.jsonl`).
- Look up past lessons: `J context <dir>`, or grep the vault's `sessions/` by `project:` and `## Lessons`.
- Missing note: read the log, then check the skip rules in step 3. Missing export: run `J export`; it prints
  exported and blocked note names.

## Tests

`cd tests && python3 -m unittest` (stdlib only, Python 3.9+).
