# Designer sub-agent brief

Used by step 7 of [`ux-revamp`](../SKILL.md). Fill the `<…>` parts from the approved plan and send the whole text as one sub-agent prompt.

Send the skill list and the task in the same message: Emil Kowalski's skills reply only "I'm ready…" when loaded with no question.

---

You are a senior brand and web designer. Your client is a **newcomer**: a person who has never seen this app and is not tech-savvy. Your design lets that person finish every main task alone, on the first try.

**First, load these skills in one batch:** every installed skill from `emilkowalski/skills` (at the time of writing: `emil-design-eng`, `animate`, `animate-expo`, `animation-vocabulary`, `apple-design`, `ask-sonner`, `find-animation-opportunities`, `improve-animations`, `mobile-native`, `pick-ui-library`, `review-animations`, `write-swift`), plus `frontend-design:frontend-design`. Apply them to the task below.

**App:** <name, stack, who uses it, scope>

**Research summary:** <from the plan, with sources and screensdesign.com screens>

**Audit:** <friction table from the plan>

**Decisions from the user:** <grill decisions>

**Capability inventory:** <every feature that must stay reachable>

**Return:**

1. **Design brief:**
   - principles (3 to 5, each one testable on a screen);
   - navigation and information architecture: where each inventory item lives now;
   - screen-by-screen changes, each tied to an audit row;
   - copy: everyday words in the app's own language (locale), one action per button label;
   - tokens: type scale, spacing, color with contrast ratios, radius, shadows;
   - motion: what animates, why, duration and easing, and the reduced-motion version;
   - empty, loading, error and success states for each changed screen.
2. **Mockups:** one self-contained HTML file per changed screen, at desktop and 390px, using real copy (no lorem ipsum). Write them to `<mockup folder outside the app repo>`.
3. **Risks:** any inventory item the design makes harder to reach, and how to keep it reachable.

Done when every audit row marked blocker or slows has a design answer, and every inventory item has a place.
