"""Maakt de PNG-iconen voor de PWA uit het SVG-icoon.

Eenmalig nodig (de PNG's staan in git). Vereist Playwright met Chromium:
    uv run --with playwright python scripts/maak_iconen.py
(Zet CHROMIUM=/pad/naar/chrome als Playwright zijn eigen browser niet vindt.)
"""

import os
from pathlib import Path

from playwright.sync_api import sync_playwright

STATIC = Path(__file__).resolve().parents[1] / "src" / "fond" / "static"
SVG = (STATIC / "icons" / "icon.svg").read_text()


def html(maat: int, maskable: bool) -> str:
    # Maskable: Android snijdt het icoon bij tot een cirkel of druppel, dus het merk
    # moet binnen de middelste 80% blijven en de achtergrond moet tot de rand lopen.
    svg = SVG.replace("<svg ", f'<svg width="{maat}" height="{maat}" ', 1)
    if maskable:
        svg = svg.replace('rx="112"', 'rx="0"', 1).replace(
            '<g id="merk">',
            '<g id="merk" transform="translate(256 256) scale(0.78) translate(-256 -256)">',
            1,
        )
    stijl = "html, body { margin: 0; background: transparent; }"
    return f"<html><head><style>{stijl}</style></head><body>{svg}</body></html>"


with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=os.environ.get("CHROMIUM") or None)
    for naam, maat, maskable in [
        ("icon-192.png", 192, False),
        ("icon-512.png", 512, False),
        ("icon-maskable-512.png", 512, True),
        ("apple-touch-icon.png", 180, True),
    ]:
        pagina = browser.new_page(viewport={"width": maat, "height": maat})
        pagina.set_content(html(maat, maskable))
        pagina.wait_for_timeout(300)
        pagina.locator("svg").screenshot(path=STATIC / "icons" / naam, omit_background=True)
        print("gemaakt:", naam)
    browser.close()
