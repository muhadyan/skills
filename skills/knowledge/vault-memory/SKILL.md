---
name: vault-memory
description: Agent memory kept as notes in an Obsidian vault instead of each tool's built-in memory, shared by Claude Code, Codex and any agent that reads AGENTS.md. Use when asked to set up vault memory, import old Claude Code or Codex memories, or debug a missing memory index or an uncommitted memory note.
---

# Vault memory

Hooks run this automatically. The agent reaches this skill only for setup, the one-off import, or a fix.
Scripts live in `${CLAUDE_SKILL_DIR}/scripts` (outside Claude Code: the `scripts/` folder next to this file).
`M` below means `python3 ${CLAUDE_SKILL_DIR}/scripts/memory.py`.

## How it works

- Notes live in `<vault>/memory/<project>/<name>.md`; facts about the user that hold in every project live in
  `<vault>/memory/_global/`. `<project>` is the git top-level folder name, else the last folder of the cwd
  (the same rule as session-journal, so both share one `project` value).
- Each note has flat frontmatter, so Obsidian Bases can show it:
  ```
  ---
  type: memory
  kind: user | feedback | project | reference
  description: one line, used to decide relevance
  project: <project> | _global
  updated: YYYY-MM-DD
  ---
  ```
  There is no hand-made index file. The index is built from this frontmatter.
- **SessionStart hook** (`M hook start`): prints the vault path, this project's folder, and the index
  (`_global` first, then the project, newest first, capped at 200 lines / 25KB) as `additionalContext`.
- **SessionEnd hook** (`M hook end`): starts a detached `M commit` and returns at once.
- **commit**: under session-journal's flock for the same repo
  (`<LOCK_DIR>/repo-<sha1(resolved vault path)[:12]>.lock`), commits every change under `memory/` and nothing
  else, then `pull --rebase --autostash` and push. On a failed rebase it aborts and keeps the commit local
  until the next sync.
- Hooks do nothing for subagents (`agent_id` in the payload) or child processes (`VAULT_MEMORY` or
  `SESSION_JOURNAL` set). A hook never fails the session; errors go to `<STATE_DIR>/memory.log`.

What the agent saves, and how, lives in the user's `AGENTS.md` Memory section. This skill does not repeat it.

## Setup

1. Create `~/.config/vault-memory/config.env`:
   ```
   VAULT=~/path/to/vault                         # a git clone; required
   # STATE_DIR=~/.local/state/vault-memory
   # LOCK_DIR=~/.local/state/session-journal     # must match session-journal's state dir
   ```
   Done when `M context` prints the vault path.
2. Turn the built-in memory off. Claude Code: `"autoMemoryEnabled": false` in `~/.claude/settings.json`.
   Codex: `memories = false` under `[features]` in `~/.codex/config.toml`.
3. Add the hooks next to any existing ones, in `~/.claude/settings.json` and `~/.codex/hooks.json`:
   ```json
   "SessionStart": [{"hooks": [{"type": "command", "command": "python3 ~/.claude/skills/vault-memory/scripts/memory.py hook start", "timeout": 10}]}],
   "SessionEnd":   [{"hooks": [{"type": "command", "command": "python3 ~/.claude/skills/vault-memory/scripts/memory.py hook end", "timeout": 5}]}]
   ```
   Codex asks you to trust new hooks once (`/hooks`). Done when a new session shows "Vault memory is on".
4. Add a Memory section to the user-level `AGENTS.md`: where notes live, the format above, one fact per
   file, update instead of duplicate, no secrets, and "run `M context` when no index was injected" for agents
   without hooks.

## Import old memories (once)

1. Dry run: `M migrate --vault <scratch dir>`. It reads `~/.claude/projects/*/memory` and
   `~/.codex/memories/MEMORY.md`, finds each Claude project's real cwd from its transcripts (the folder slug
   is lossy), sends `kind: user` to `_global`, turns a `MEMORY.md` with real content into `project-notes`,
   and splits Codex task groups into one note each.
2. Read the report: every redaction (secret values are replaced, words around them kept), every collision,
   every unresolved folder. Search the output for secrets that no pattern can spot (a bare password in
   prose) and list them, one per line, in a file outside the repo. Rerun with `--also-redact FILE` until a
   scan (`gitleaks dir <scratch>/memory`) and the literal list find nothing.
3. `M migrate --apply` (add `--vault` for a worktree), review the diff, commit. The originals stay where they
   are as a backup.

## Fix

- No index at session start: run `M context` in that folder, then read `<STATE_DIR>/memory.log`.
- Note not pushed: run `M commit` and read its error. A push that keeps failing usually means the vault has
  a rebase conflict to settle by hand.

## Tests

`cd tests && python3 -m unittest` (stdlib only, Python 3.9+).
