"""Walkthrough of a new feature on the demo app. Copy it as the template for a real flow.

Usage (the demo app stands in for your dev or staging server):
  python3 -m http.server 8765 -d <skills>/before-after-video/examples/demo-app
  PYTHONPATH=<skills>/before-after-video/scripts uv run --with "playwright>=1.59" python demo_flow.py OUT

The ticket, as the AC map of step 1 lists it:
  DEMO-12 "Edit an order's discount"
  AC1 on screen: the Orders list shows each order's discount.
  AC2 on screen: a discount over 100% shows an inline message, and the typed value stays.
  AC3 on screen: a valid discount saves, and the list shows it.
  AC4 off screen: the API refuses a discount over 100%. Proof: its unit test, named in the post text.
"""
import argparse

from recorder import Recorder  # found through PYTHONPATH=<skills>/before-after-video/scripts

ap = argparse.ArgumentParser()
ap.add_argument("out_dir")
ap.add_argument("--topic", default="DEMO-12")
ap.add_argument("--base", default="http://127.0.0.1:8765")
ap.add_argument("--delay", type=int, default=6000, help="the demo app's slow first load, in ms")
args = ap.parse_args()

URL = f"{args.base}/index.html?v=after&delay={args.delay}"

# One Recorder is one browser at one size: one take. A feature seen by two users or at two
# sizes gets one take each, named after its scene ("shop", "admin"), and join.py plays them in order.
with Recorder("demo", args.out_dir, topic=args.topic,
              blur=[".email"],  # personal data never reaches the video
              context_options={"locale": "en-US", "timezone_id": "UTC"}) as r:
    p = r.page
    row = p.locator("tbody tr", has_text="A-1001")

    # Load (and log in) off camera, then start recording on a ready screen.
    r.goto(URL, capture=False)
    row.wait_for(timeout=30_000)
    r.start_capture()
    r.show(p.get_by_role("heading", name="Orders"), "DEMO-12: edit an order's discount", hold=2.5)
    r.show(row.locator(".discount"), "AC1: the Orders list shows each order's discount", hold=3)

    r.click(row.get_by_role("button", name="Edit"))
    discount = p.get_by_label("Discount")
    r.click(discount)
    r.select_all()
    r.caption("Type a discount over 100% and press Save")
    r.type("150")
    r.click(p.get_by_role("button", name="Save"))
    r.show(p.get_by_text("Discount must be 0–100%"), "AC2: an inline message explains the limit", hold=3)
    r.show(discount, "AC2: the typed value stays, so it is easy to fix", value="150", hold=2.5)

    r.click(discount)
    r.select_all()
    r.type("15")
    r.click(p.get_by_role("button", name="Save"))
    r.show(row.get_by_text("15%"), "AC3: saved. Order A-1001 now shows a 15% discount", hold=3.5)

print(r.mp4_path)
