"""Maakt de PNG-iconen voor de PWA uit het SVG-icoon, met het eigen lettertype.

Eenmalig nodig (de PNG's staan in git). Vereist Playwright met Chromium:
    uv run --with playwright python scripts/maak_iconen.py
(Zet CHROMIUM=/pad/naar/chrome als Playwright zijn eigen browser niet vindt.)
"""

import base64
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

STATIC = Path(__file__).resolve().parents[1] / "src" / "fond" / "static"
FONT = base64.b64encode((STATIC / "fonts" / "fraunces-opsz-italic.woff2").read_bytes()).decode()


def html(maat: int, maskable: bool) -> str:
    # Maskable: Android snijdt het icoon bij tot een cirkel of druppel, dus de letter
    # moet binnen de middelste 80% blijven en de achtergrond moet tot de rand lopen.
    rond = 0 if maskable else 112
    schaal = 0.78 if maskable else 1
    return f"""<html><head><style>
    @font-face {{ font-family: F; src: url(data:font/woff2;base64,{FONT}); font-style: italic; }}
    html, body {{ margin: 0; background: transparent; }}
    </style></head><body>
    <svg xmlns="http://www.w3.org/2000/svg" width="{maat}" height="{maat}" viewBox="0 0 512 512">
      <rect width="512" height="512" rx="{rond}" fill="#9b3a16"/>
      <g transform="translate(256 256) scale({schaal}) translate(-256 -256)">
        <text x="236" y="362" text-anchor="middle" font-family="F" font-style="italic"
              font-weight="700" font-size="330" fill="#fffaf0">F</text>
        <circle cx="352" cy="346" r="26" fill="#f2dac8"/>
      </g>
    </svg></body></html>"""


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
