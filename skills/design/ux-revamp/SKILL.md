---
name: ux-revamp
description: Deep-research an app's UI/UX and revamp it so a non-tech-savvy person can use it without help, keeping every current feature working. Plan mode with research, screensdesign.com and a one-question-at-a-time grill; a senior designer sub-agent with Emil Kowalski's skills; build, verify, two adversarial reviews, PRs, merge.
disable-model-invocation: true
argument-hint: "[area, flow or URL; empty = whole app]"
---

# UX revamp

**Goal:** a **newcomer** (a person who has never seen this app and is not tech-savvy) finishes every **main task** alone, on the first try, without confusion. Every item in the **capability inventory** (each feature that works today) still works after the change.

Backend, data model and infrastructure changes are in scope when the UX needs them. Make them as part of the revamp.

Scope is `$ARGUMENTS` when given (an area, a flow or a URL), else the whole app.

Running this skill is the user's consent to branch, commit, push, open PRs and merge them, as the steps below say.

## Needs

- [Emil Kowalski's skills](https://github.com/emilkowalski/skills): `npx skills@latest add emilkowalski/skills`.
- The `frontend-design` skill (Claude Code plugin `frontend-design`).
- The `grilling` skill from [mattpocock/skills](https://github.com/mattpocock/skills).
- [Claude in Chrome](https://claude.com/chrome) (`/chrome`) to drive the app and screensdesign.com.
- Optional, each with a fallback:
  - `deep-research` skill. Else: parallel research sub-agents with web search.
  - A Claude **Design** artifact (Artifact tool, `quickstart` intent `design`). Else: local HTML mockups.
  - [`before-after-video`](../../engineering/before-after-video/SKILL.md) skill. Else: desktop + 390px screenshots in the PR.
  - ScreensDesign MCP (Pro). Else: the free web library, see [`references/screensdesign.md`](references/screensdesign.md).
  - A `verify` skill. Else: `superpowers:verification-before-completion`, or the checks in step 9 alone.

## A. Plan mode

Change no project files here; the plan file holds everything you decide. You may run the app locally against a local or seeded test database. Production data stays untouched.

1. **Enter plan mode.**

2. **Build the capability inventory.** Read the code (routes, pages, API endpoints, jobs, roles, settings) and drive the running app in Chrome. When a page needs a login, ask the user to log in as that role in that Chrome; never ask for passwords. Then:
   - one row per route, screen and API action: what it does, which role uses it, how to reach it;
   - mark the **main tasks**: the 3 to 7 jobs most users open the app for.

   Ask the user to confirm the main tasks in one `AskUserQuestion`. Done when every route has a row and the main tasks are confirmed. This table is the regression checklist for step 9.

3. **Newcomer audit.** Walk each main task as a newcomer in Chrome at desktop width and at 390px. Log every friction point: screen, what confuses, severity (blocker / slows / cosmetic), and the layer a fix touches (UI, backend, data, infra). Done when every main task has been walked end to end at both widths.

4. **Deep research.** Use the `deep-research` skill, or parallel research sub-agents. Aim it at the audit's problems:
   - usability for people with low digital skills (plain language, one main action per screen, recognition over recall, forgiving errors, undo);
   - accessibility at WCAG 2.2 AA (contrast, target size, labels, keyboard, focus);
   - how leading apps in this app's domain shape the same flows;
   - real screens from screensdesign.com: follow [`references/screensdesign.md`](references/screensdesign.md).

   Done when every blocker and slows row has a fix idea backed by at least one source: a study, a guideline, or a real-app screen.

5. **Grill the user.** Use the `grilling` skill's design tree. Ask exactly one question per `AskUserQuestion` call: one short line, 2 to 4 options, your recommended option first and marked "(Recommended)". Look up facts yourself; ask only for decisions. Done when the frontier is empty.

6. **Write the plan.** Put in the plan file:
   - research summary with sources, the audit table, the grill decisions;
   - the capability inventory as a checklist;
   - the PR slices: backend and data first, UI after; each slice ships alone without breaking the app;
   - the verify steps.

   Exit plan mode for approval.

## B. Design, then build

Starts when the user approves the plan.

7. **Designer sub-agent.** Spawn one sub-agent with the prompt in [`references/designer-brief.md`](references/designer-brief.md), filled with the plan's research, audit, decisions and inventory. It writes HTML mockups to a folder outside the app repo (the session scratchpad). Create one Claude Design artifact and publish those mockups to it, or keep them as local HTML files. Put the link or paths in the plan, and add one inventory row per moved URL (old URL redirects to new). Done when the design brief and mockups for every changed screen exist, before any code changes.

8. **Build.** First record the "before" takes of the main tasks from the base branch (`before-after-video`). Then make one branch per slice, each stacked on the one before. Use test-driven development for logic, API and data changes. Load `frontend-design` and Emil Kowalski's skills while you build UI, and follow the design brief. Keep the inventory working:
   - database migrations are additive and reversible; backfill data before code reads it;
   - API fields that clients use stay until no client reads them;
   - each moved URL redirects to its new place.

   Done when every planned change is built and the tests pass.

9. **Verify.** Try `Skill("verify")` first. When it is not available, use `superpowers:verification-before-completion`. Then:
   - run tests, lint, type check and build;
   - drive every inventory row in a real browser at desktop and 390px;
   - walk every main task again as a newcomer;
   - check keyboard use, focus, contrast and labels.

   Done when every inventory row has evidence (a test, a screenshot, or a log line) and all checks pass. When a later step says "re-verify", run all checks again, and drive the inventory rows that the new fixes touch.

10. **Review 1.** Launch a sub-agent to adversarially review the change for correctness and simplicity. Apply its valid feedback, then re-verify. Done when no open finding is left.

11. **Open the PR(s).** One PR per slice; each slice's base is the slice before it. Record the "after" takes and build the side-by-side video. Each body has: the research summary, the design link, the before/after video of the main tasks, the inventory checklist, and the test plan. Done when every PR is open.

12. **Review 2.** Launch a fresh sub-agent to adversarially review the full diff of the whole change (`git diff <default-branch>...<top slice>`). Focus: security, data integrity, and bugs that the review-1 fixes introduced. Apply its valid feedback, re-verify, push. Done when no open finding is left.

13. **Merge.** Merge the PRs in order (backend and data before the UI that needs them). Before each merge after the first, set that PR's base to the default branch, rebase it onto that branch, and re-run the checks. When CI does not run, run its steps locally first and say so in the PR. When a merge deploys, check that migrations ran and the main tasks work on the deployed app. Done when every PR is merged and the main branch builds.
