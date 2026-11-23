# Flow situations

Find the row that matches what the screen does. Each row says what to put in the flow script. `r` is the `Recorder`, and `p` is `r.page`.

## Time

| The screen… | Do this |
|---|---|
| needs a slow first load or a login before the part worth showing | `r.goto(url, capture=False)`, log in, then wait for the data (`locator.wait_for(timeout=60_000)`) and call `r.start_capture()`. The video opens on a ready screen. |
| has a slow load or a long wait in the middle of the take (about 5 s or more) | `with r.cut(): p.reload(); locator.wait_for(timeout=60_000)`. The block's time is left out of the video. Caption it, for example "(loading time cut from the video)". |
| keeps polling, so `wait_for_load_state("networkidle")` times out | Wait for the element that proves the state you want to film: `locator.wait_for()`. Never wait for `networkidle`. |
| is a single-page app that routes by `#hash`, so no `load` event fires | Wait for the route: `p.wait_for_function("location.hash.startsWith('#orders')")`, then for an element on it. |
| reloads or moves on right after Save | Wait for the saved value before the next step: `r.show(row.get_by_text("15%"), …)`. |
| shows output that changes from run to run (AI answers, timestamps) | Use a caption that holds for every run ("an answer appears"). Do not quote the text. Check it in the still. |

## Browser behavior

| The flow… | Do this |
|---|---|
| opens a new tab (`target=_blank`, `window.open(url)`) | `Recorder(..., popups=True)`. In Google Chrome's headless mode, every frame after a new tab comes out zoomed and cropped. `popups=True` uses Playwright's headless shell, which keeps frames whole (install it in step 0). The video shows only the first page, never the new tab. After you close the tab, call `p.bring_to_front()`. |
| opens a PDF in a new tab | To show the PDF, skip the new tab. Point at the link, then open it in the same page with the default Chrome, which shows its PDF viewer: `r.move_to(link)`, then `r.goto(link.evaluate("a => a.href"))` (the full URL, also for a relative link). If the click itself must be on video, use `popups=True` and do not wait for the PDF tab to load: the headless shell has no PDF viewer, so that tab never loads. Pause, then close it. |
| shows `alert`, `confirm` or `prompt` | The recorder draws the message in a "Browser alert" box, which stays until the next click or key, and dismisses the dialog. Use `dialogs="accept"` when the flow must click OK on a `confirm()`. Wait for it, then quote it: `with r.expect_dialog() as alert: r.click(save)`, then `r.show(r.dialog_box, f"BEFORE: the alert says '{alert.message}'")`. |
| needs a language, time zone or HTTP login | `Recorder(..., context_options={"locale": "de-DE", "timezone_id": "Europe/Berlin", "http_credentials": {...}})`. Any `browser.new_context` option works here. Browser start options go in `launch_options`. |
| works inside a frame (a payment form, an embedded editor) | Locate through the frame: `p.frame_locator("iframe#pay").locator("#card")`. `r.click` and `r.type` work there, and the pointer follows. The key box shows typing only in frames from the same origin as the page. |
| types into a date or time input | Typed digits follow the browser locale. Set `locale` in `context_options`, or `r.move_to(input)` and then `input.fill("2026-12-01")`. |
| is redirected by an app-wide gate (a banner, a "finish setup" screen, a forced tour) | Before the first `goto`, keep the gate's request away: `p.route("**/api/<gate-endpoint>**", lambda route: route.fulfill(status=404, body="{}"))`. Choose a reply the app treats as "nothing to show". Check that it changes no data. |
| must be shown at a phone size and a PC size | Record one take per size: `Recorder("phone", …, width=390, height=844)`, then `Recorder("pc", …)`. Join them with before-after-video's `scripts/join.py`, which fits both on one canvas: `python3 join.py OUT --topic <topic> --parts phone pc`. Resizing the page during a take (`set_viewport_size`) shrinks every later frame into the first size. |
| shows different lists for different user roles | Pick the test user's role first, then write the locators. Open the tab or filter that shows the rows (an "All" tab, for example) before you point at them. |

## People and data

| The screen shows… | Do this |
|---|---|
| real names, emails, phone numbers | Anonymise the local copy, for example `UPDATE users SET name = 'User ' \|\| id, email = 'user' \|\| id \|\| '@example.invalid'`. Or blur them: `Recorder(..., blur=[".email", "td.customer"])`, or `r.blur(selector)` during the take. Blur takes CSS selectors only, and it stays on after reloads. |
| a login form | Log in with the camera off (`capture=False`, see Time). If the login must show, type the password into a password field (the key box shows dots) and type OTPs or tokens with `r.type(..., secret=True)`. |
| what one user does and what another user sees | One `Recorder` is one browser, so storage is shared. Record one take per user, for example `Recorder("before-buyer", …)` and `Recorder("before-seller", …)`. Join each mode's parts in order with before-after-video's `scripts/join.py`: `python3 join.py OUT --topic <topic> --parts before-buyer before-seller --name before`. Then run `compose.py`. |

## Showing the key moment

- **A single key matters** (a minus sign, a decimal point). Type it alone, pause, and caption the result. Then type the rest.
- **The evidence is at the bottom of the screen.** Use `r.show(..., top=True)` so the caption bar does not cover it.
- **The evidence is in an input field.** Use `r.show(field, …, value="150")`. The take fails if the field holds anything else.
- **The screen changes.** A caption stays on until the next one, also across reloads. Set a new caption before each screen change, or the old caption describes the new screen.
