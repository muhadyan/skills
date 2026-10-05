"""Payroll before/after flow (local demo app) — a template to copy, not run as-is.

Usage: PYTHONPATH=<skill>/scripts uv run --with "playwright>=1.59" python payroll_flow.py before|after OUT --topic payroll

The change being shown: the tax field turned a typed '-' into 0, so a minus
amount (a tax refund) could not be entered, and the payroll table had no
Tax Allowance column. One script records both takes; the mode picks the branch.
"""
import argparse
import os
import sys

from recorder import Recorder  # found through PYTHONPATH=<skill>/scripts

ap = argparse.ArgumentParser()
ap.add_argument("mode", choices=["before", "after"])
ap.add_argument("out_dir")
ap.add_argument("--topic", default="payroll")
args = ap.parse_args()

MODE, OUT = args.mode, args.out_dir
BASE = "http://localhost:5173/"  # local dev app
PASSWORD = os.environ.get("DEMO_PASSWORD", "")  # never hardcode credentials
if not PASSWORD:
    sys.exit("set DEMO_PASSWORD to the demo user's password")
L = MODE.upper()

with Recorder(MODE, OUT, topic=args.topic) as r:
    p = r.page
    row = lambda name: p.locator("tbody tr", has_text=name)  # noqa: E731

    r.goto(BASE)
    r.click("input[type=email]"); r.type("demo@example.com", delay_ms=40)
    r.click("input[type=password]"); r.type(PASSWORD, delay_ms=40)  # shown as dots
    r.click("button[type=submit]")
    p.wait_for_function("location.hash.startsWith('#admin')")  # hash route: no 'load' event
    r.click(p.get_by_role("button", name="Payroll").first)
    row("Alice (test)").wait_for()
    r.keys_reset()
    r.caption(f"{L}: Payroll list, September"); r.pause(2.5)

    # 1. Minus income tax on Alice
    r.caption(f"{L}: edit Alice and enter a minus income tax (tax refund)")
    r.scroll(dx=1200, over=".overflow-x-auto"); r.pause(1)
    r.click(row("Alice (test)").get_by_role("button", name="Edit")); r.pause(1)
    tax = row("Alice (test)").get_by_role("spinbutton", name="Income tax")
    r.click(tax); r.select_all(); r.pause(1.2)
    r.caption(f"{L}: press the minus key '-' (yellow box = keys pressed)"); r.pause(1.5)
    r.type("-"); r.pause(1)  # the key moment: type it alone, then show the result
    r.caption("BEFORE: '-' was pressed, but the box shows 0 instead" if MODE == "before"
              else "AFTER: '-' was pressed, and the box keeps '-'")
    r.pause(3.5)
    r.type("250000", delay_ms=220); r.pause(1.5)
    if MODE == "before":
        r.caption("BEFORE: result is 0250000 (a positive number). A minus amount cannot be entered")
        r.pause(4)
        r.click(row("Alice (test)").get_by_role("button", name="Cancel"))
    else:
        r.click(row("Alice (test)").get_by_role("button", name="Save")); r.pause(1.5)
        r.caption("AFTER: saved. Income tax = -250,000, take-home pay goes up")
        r.move_to(row("Alice (test)").get_by_text("-250,000")); r.pause(4.5)
    r.keys_reset()

    # 2. Tax Allowance column on Bob
    r.scroll(dx=-1200, over=".overflow-x-auto"); r.pause(1)
    if MODE == "before":
        r.caption("BEFORE: no Tax Allowance column in the income part")
        r.move_to(p.locator("thead th", has_text="Total Income")); r.pause(4.5)
    else:
        r.caption("AFTER: new Tax Allowance column. Enter 1,000,000 for Bob")
        r.move_to(p.locator("thead th", has_text="Tax Allowance")); r.pause(2.5)
        r.scroll(dx=1200, over=".overflow-x-auto"); r.pause(0.8)
        r.click(row("Bob (test)").get_by_role("button", name="Edit")); r.pause(1)
        allowance = row("Bob (test)").get_by_role("spinbutton", name="Tax allowance")
        r.click(allowance); r.select_all(); r.type("1000000", delay_ms=180); r.pause(1.2)
        r.click(row("Bob (test)").get_by_role("button", name="Save")); r.pause(1.5)
        r.scroll(dx=-300, over=".overflow-x-auto")
        r.caption("AFTER: Total Income 11,000,000. The allowance covers the tax")
        r.move_to(row("Bob (test)").get_by_text("11,000,000")); r.pause(5)
    r.keys_reset()

    # 3. Staff detail page (evidence near the bottom: caption goes on top)
    r.scroll(dx=-1200, over=".overflow-x-auto")
    r.click(row("Bob (test)").get_by_role("button", name="Bob (test)"))
    p.get_by_text("Total Income").first.wait_for(); r.pause(1)
    if MODE == "before":
        r.caption("BEFORE: detail page has no Tax Allowance line in the income section")
        r.move_to(p.get_by_text("Bonus", exact=True)); r.pause(4)
        r.scroll(600); r.pause(1)
        r.caption("BEFORE: only 'Tax Cover' exists, and it is a company cost (not income)", top=True)
        r.move_to(p.get_by_text("Tax Cover", exact=True)); r.pause(4.5)
    else:
        r.caption("AFTER: 'Tax Allowance' is in the income section, above Total Income")
        r.move_to(p.get_by_text("Tax Allowance", exact=True)); r.pause(4)
        r.scroll(600); r.pause(1)
        r.caption("AFTER: Tax Cover is labelled 'company cost, not take-home' to avoid mix-ups", top=True)
        r.move_to(p.get_by_text("Tax Cover (company cost)")); r.pause(4.5)

print(r.mp4_path)
