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

### Engineering

- **[before-after-video](./skills/engineering/before-after-video/SKILL.md)**: Record before/after MP4 videos of a UI change (visible mouse pointer, click rings, key-press box, captions) plus a side-by-side version, with Playwright + ffmpeg. Saves files by default; posts to a GitHub PR/issue (`gh --attach`) or a ClickUp comment when you ask. Needs `uv`, `ffmpeg` and Google Chrome.

### Knowledge

- **[session-journal](./skills/knowledge/session-journal/SKILL.md)**: Log every Claude Code and Codex session to an Obsidian vault (work done + lessons) through SessionStart/SessionEnd hooks, feed past lessons back at session start, and export brand-safe notes (path gate + NDA denylist) as a knowledge base for a content bot. Stdlib Python, needs the `claude` CLI and `git`.

## License

[MIT](./LICENSE)
