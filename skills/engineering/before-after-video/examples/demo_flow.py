"""Before/after flow for the demo app. Copy it as the template for a real flow.

Usage (the demo app stands in for your dev servers):
  python3 -m http.server 8765 -d <skill>/examples/demo-app
  PYTHONPATH=<skill>/scripts uv run --with "playwright>=1.59" python demo_flow.py before OUT --topic discount

The change: a discount over 100% raised a browser alert and lost the typed
value; now an inline message explains the limit and the value stays.
One script records both takes; the mode picks the server and the branch.
"""
import argparse

from recorder import Recorder  # found through PYTHONPATH=<skill>/scripts

ap = argparse.ArgumentParser()
ap.add_argument("mode", choices=["before", "after"])
ap.add_argument("out_dir")
ap.add_argument("--topic", default="discount")
ap.add_argument("--base", default="http://127.0.0.1:8765")
ap.add_argument("--delay", type=int, default=6000, help="the demo app's slow first load, in ms")
args = ap.parse_args()

# A real flow points each mode at its own server: the old code runs on its own port.
SERVER = {"before": f"{args.base}/index.html?v=before", "after": f"{args.base}/index.html?v=after"}
URL = f"{SERVER[args.mode]}&delay={args.delay}"
L = args.mode.upper()

with Recorder(args.mode, args.out_dir, topic=args.topic,
              blur=[".email"],  # personal data never reaches the video
              context_options={"locale": "de-DE", "timezone_id": "Europe/Berlin"}) as r:
    p = r.page
    row = p.locator("tbody tr", has_text="A-1001")

    # Load (and log in) off camera, then start recording on a ready screen.
    r.goto(URL, capture=False)
    row.wait_for(timeout=30_000)
    r.start_capture()
    r.show(row, f"{L}: the Orders list. Edit order A-1001", hold=2.5)

    r.click(row.get_by_role("button", name="Edit"))
    discount = p.get_by_label("Discount")
    r.click(discount)
    r.select_all()
    r.caption(f"{L}: type a discount over 100% and press Save")
    r.type("150")
    r.pause(1)
    save = p.get_by_role("button", name="Save")

    # r.show checks that the evidence is on screen before the caption claims it.
    if args.mode == "before":
        with r.expect_dialog() as alert:  # waits for the alert, so the caption quotes the right one
            r.click(save)
        r.show(r.dialog_box, f"BEFORE: a browser alert says '{alert.message}'", hold=3)
        r.show(discount, "BEFORE: and the typed 150 is gone", value="", hold=3.5)
    else:
        r.click(save)
        r.show(p.get_by_text("Discount must be 0–100%"), "AFTER: an inline message explains the limit", hold=3)
        r.show(discount, "AFTER: the typed value stays, so it is easy to fix", value="150", hold=2.5)
        r.click(discount)
        r.select_all()
        r.type("15")
        r.click(p.get_by_role("button", name="Save"))
        r.show(row.get_by_text("15%"), "AFTER: saved. Order A-1001 now has a 15% discount", hold=3.5)

print(r.mp4_path)
