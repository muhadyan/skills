---
name: feature-demo-video
description: Walkthrough video of a new feature, scene by scene along its ticket's acceptance criteria. Use when asked for a demo or walkthrough video of a ticket, feature or PR, or a video of what was built, when there is no old version to compare.
argument-hint: "[ticket/PR URL]"
---

# Feature demo video

One MP4 shows what a ticket built: a scene for each acceptance criterion (AC), and every claim checked on screen before the caption says it. Use it for a feature, screen or app built from scratch. When the change alters behavior that already existed, use [before-after-video](../before-after-video/SKILL.md) instead: it records the old code next to the new.

This skill reuses before-after-video's tools: `recorder.py` (pointer, click rings, key box, captions, evidence checks), `join.py`, and its posting guides. They live in `${CLAUDE_SKILL_DIR}/../before-after-video`. Outside Claude Code that variable is not filled in: use the `before-after-video` folder next to this skill's folder.

`OUT` below is an output folder outside the repo. `<topic>` is the ticket key (`DEMO-12`): every file name starts with it.

## Steps

0. **Check the tools.** `ls "${CLAUDE_SKILL_DIR}/../before-after-video/scripts/recorder.py"` must print the path. If it does not, install before-after-video next to this skill (the plugin and `npx skills add muhadyan/skills` ship both). Then do step 0 of [before-after-video](../before-after-video/SKILL.md). Done when `recorder.py` is found and uv, ffmpeg and Chrome are there.

1. **Write the AC map** to `OUT/ac-map.md`. Read the ticket. Copy its acceptance criteria (often "Acceptance criteria" or "Expected behavior", or the same heading in the ticket's language) and number them AC1, AC2… in the ticket's order. If the ticket lists none, write them from what it asks for, and say so in the post. One row per AC:

   | AC | On screen? | Take | Evidence: what the viewer sees | Proof, when off screen |
   |---|---|---|---|---|
   | AC1 Orders show their discount | yes | demo | the "5%" cell of order A-1001 | |
   | AC4 The API refuses over 100% | no | | | `test_discount_limit` passes |

   An AC that no screen can show (a build, a lint run, a header, a log line) gets its proof instead: a command and its result, or a CI run link. Proof goes in the post text, never in a caption. Done when every AC has a row, each on-screen row names one thing the viewer can see, and each off-screen row names its proof.

2. **Make the takes safe and repeatable.** Record where the feature runs: your dev servers, or a staging server that has the ticket deployed. Production only when the user asks for it.
   - Dev servers: do step 1 of [before-after-video](../before-after-video/SKILL.md) (a reset script, outbound messages off, fake data).
   - Shared staging: log in as a test account and change only its data. What a take creates stays on the server, so give it a name that says it is a demo, and list it in your report. Ask before a take that sends a real email or message, or takes a payment.

   Done when the flow can run twice in a row with the same screens, and nothing can reach a real customer.

3. **Write the flow script.** Copy [`examples/demo_flow.py`](examples/demo_flow.py). It runs against before-after-video's demo app; its docstring says how to serve it. Import `recorder.py`; do not copy it. Read before-after-video's step 2 for `r.show`, `r.caption` and real input events. They work the same here.
   - Open on the first ready screen with the ticket: `r.show(heading, "DEMO-12: edit an order's discount")`.
   - Give every on-screen AC at least one `r.show(evidence, "AC2: …")`, its caption starting with the AC label. Use `r.caption` only for narration that claims nothing ("open the admin").
   - Order the scenes as a user meets them. The labels keep the ticket's numbers.
   - Reach each state through the app or its data: seed a sale that opens tomorrow, or let an admin create the product. The screen must be the app's own.
   - One `Recorder` is one browser at one size: one **take**. Name each take after its scene, because its badge shows the name. Record a phone-first app at phone size, and a feature that two users see as one take per user:

     ```python
     with Recorder("shop", out, topic=topic, width=390, height=844) as r: ...   # the customer, on a phone
     with Recorder("admin", out, topic=topic) as r: ...                          # staff, at 1440×810
     ```

   - Write captions in the ticket's language. For a ticket in two languages, use the first.
   - For slow loads, login, popups, alerts, personal data and two sizes, see [FLOWS.md](../before-after-video/FLOWS.md).

   ```bash
   PYTHONPATH="${CLAUDE_SKILL_DIR}/../before-after-video/scripts" uv run --with "playwright>=1.59" python flow.py OUT --topic <topic>
   ```

   Done when every take runs end to end and prints its `OUT/<topic>_<TAKE>.mp4`.

4. **Join the takes:** `python3 "${CLAUDE_SKILL_DIR}/../before-after-video/scripts/join.py" OUT --topic <topic> --parts shop admin`. It plays them in that order on one canvas and writes `OUT/<topic>_DEMO.mp4` and its contact sheet `OUT/<topic>_DEMO_sheet.png`. A single take named `demo` needs no join: `--parts demo` writes only the sheet. Name a take `demo` only when it is the only one: the joined video takes that name. Done when the MP4 path prints with its size.

5. **Check every still against the AC map.** Each take writes `OUT/<topic>_<TAKE>_stills/NN.jpg` and `captions.txt` (still name, tab, caption). Read every still next to its caption, then read the sheet. Done when every on-screen AC in the map has a still whose caption starts with its label and whose screen shows its evidence, the pointer is on the evidence, every frame is whole, and no secret or personal data is on screen. If a still fails, fix the flow and record that take again from the data reset.

6. **Deliver.** By default, only save the file. Copy `<topic>_DEMO.mp4` to `~/Downloads/`, with `_v2`… for re-takes, and give the user the path. Post only when the user names a place:
   - GitHub PR or issue: [share/github.md](../before-after-video/share/github.md)
   - ClickUp task, comment or thread reply: [share/clickup.md](../before-after-video/share/clickup.md)
   - Anything else: give the path and say posting there is not automated yet.

   Post the one video with this text, built from the AC map:

   ```markdown
   **Demo of DEMO-12: edit an order's discount**

   ![](./DEMO-12_DEMO.mp4)

   Shown in the video: AC1 (orders show their discount), AC2 (inline message over 100%), AC3 (a valid discount saves).
   Checked outside the video: AC4, `test_discount_limit` passes.
   ```

   A video over 10 MB does not upload to a free GitHub plan. Join again with `--crf 26`, or record a single `demo` take again with `Recorder(..., crf=26)`.

   Done when the user has the path, and the post URL if you posted.

## Gotchas

- A take never changes size. `page.set_viewport_size` during a take shrinks every later frame into the first size. Record one take per size and join them.
- Captions in Japanese, Chinese or Korean need a CJK font on the machine that records. Linux often has none (install `fonts-noto-cjk`), so check the first still.
- Everything in before-after-video's Gotchas applies here too (`python -I`, first matches, stopping servers by PID).
