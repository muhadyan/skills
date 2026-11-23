# Skills

My agent skills for Claude Code, Codex and other coding agents. Small, composable and easy to adapt: copy them, hack on them, make them your own.

Layout inspired by [mattpocock/skills](https://github.com/mattpocock/skills).

## Installation

Pick one. Installing both gives you every skill twice.

<details>
<summary><strong>Claude Code plugin</strong> (managed, updates when I ship)</summary>

```bash
claude plugin marketplace add muhadyan/skills
claude plugin install muhadyan-skills@muhadyan
```

Or, from inside a session:

```
/plugin marketplace add muhadyan/skills
/plugin install muhadyan-skills@muhadyan
```

</details>

<details>
<summary><strong>Any agent, via skills.sh</strong> (editable copies you own)</summary>

```bash
npx skills@latest add muhadyan/skills
```

Pick the skills you want and which agents to install them on. Pull later changes with `npx skills update`.

</details>

## Reference

### Design

- **[ux-revamp](./skills/design/ux-revamp/SKILL.md)**: Revamp an app's UI/UX so a non-tech-savvy person can use it without help, while every current feature keeps working (backend, data and infra changes included when needed). Plan mode with deep research, [screensdesign.com](https://screensdesign.com) and a one-question-at-a-time grill; a senior designer sub-agent with [Emil Kowalski's skills](https://github.com/emilkowalski/skills); then build, verify in a real browser, two adversarial reviews, PRs with before/after videos, and merge. Type `/ux-revamp` to run it.

### Engineering

- **[before-after-video](./skills/engineering/before-after-video/SKILL.md)**: Record before/after MP4 videos of a UI change (visible mouse pointer, click rings, key-press box, captions, browser alerts) plus a side-by-side version, with Playwright + ffmpeg. Works on any web app: cuts slow loads, survives popups, blurs personal data, checks every caption against the screen, and runs the old code in a git worktree so your checkout stays untouched. Saves files by default; posts to a GitHub PR/issue (`gh --attach`) or a ClickUp comment or thread reply when you ask. Needs `uv`, `ffmpeg` and Google Chrome.
- **[feature-demo-video](./skills/engineering/feature-demo-video/SKILL.md)**: Record one walkthrough MP4 of a feature built from scratch, where no "before" exists: a scene for each acceptance criterion of the ticket, each caption checked against the screen first. Takes of different sizes or users (a phone shop and a PC admin) join into one video. Criteria no screen can show go in the post text with their proof. Uses before-after-video's recorder, so install both.

### Knowledge

- **[session-journal](./skills/knowledge/session-journal/SKILL.md)**: Log every Claude Code and Codex session to an Obsidian vault (work done + lessons) through SessionStart/SessionEnd hooks, feed past lessons back at session start, and export brand-safe notes (path gate + NDA denylist) as a knowledge base for a content bot. Stdlib Python, needs the `claude` CLI and `git`.
- **[vault-memory](./skills/knowledge/vault-memory/SKILL.md)**: Keep agent memory as notes in an Obsidian vault instead of each tool's built-in memory, so Claude Code, Codex and any AGENTS.md-reading agent share one memory. SessionStart hook injects the index, SessionEnd hook commits `memory/` (secrets stripped), and a one-off import moves old Claude Code and Codex memories in with secrets scrubbed. Stdlib Python, needs `git`.

## License

[MIT](./LICENSE)
