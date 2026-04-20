"""
ResearchScope demo GIF generator
Focuses on: Paper of the Day, Research Gaps, Upcoming Conference Deadlines

Requires: pip install playwright pillow
          playwright install chromium
"""

import asyncio
from pathlib import Path
from PIL import Image
import io

from playwright.async_api import async_playwright

BASE_URL = "https://kishormorol.github.io/ResearchScope"
OUT_PATH = Path(__file__).parent.parent / "docs" / "demo.gif"
VIEWPORT = {"width": 1280, "height": 800}


async def take(page, frames: list, delay_ms: int = 80, repeat: int = 1):
    buf = await page.screenshot(type="png")
    img = Image.open(io.BytesIO(buf)).convert("RGBA")
    for _ in range(repeat):
        frames.append((img.copy(), delay_ms))


async def smooth_scroll(page, frames, start, end, step=55, delay_ms=50, sleep=0.03):
    rng = range(start, end + step, step) if end > start else range(start, end - step, -step)
    for y in rng:
        y = max(0, min(y, end if end > start else start))
        await page.evaluate(f"window.scrollTo(0, {y})")
        await take(page, frames, delay_ms=delay_ms)
        await asyncio.sleep(sleep)


async def main():
    frames: list[tuple[Image.Image, int]] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport=VIEWPORT)

        # ── 1. Home page — brief intro ────────────────────────────────────
        print("Loading home page...")
        await page.goto(f"{BASE_URL}/index.html", wait_until="networkidle")
        await asyncio.sleep(1.5)
        await take(page, frames, delay_ms=150, repeat=8)  # hold hero

        # ── 2. Paper of the Day ───────────────────────────────────────────
        print("Scrolling to Paper of the Day...")

        # Scroll to potd-container
        await page.evaluate("document.getElementById('potd-container').scrollIntoView({behavior:'instant'})")
        await asyncio.sleep(0.5)

        # Nudge up a bit so heading is visible
        current_y = await page.evaluate("window.scrollY")
        await page.evaluate(f"window.scrollTo(0, {max(0, current_y - 80)})")
        await asyncio.sleep(0.5)
        await take(page, frames, delay_ms=150, repeat=12)  # hold ~1.8s

        # Scroll down to show full card
        await smooth_scroll(page, frames, max(0, current_y - 80), current_y + 400, step=40, delay_ms=60)
        await take(page, frames, delay_ms=150, repeat=10)

        # ── 3. Research Gaps page ─────────────────────────────────────────
        print("Navigating to Research Gaps...")
        await page.goto(f"{BASE_URL}/gaps.html", wait_until="networkidle")
        await asyncio.sleep(1.5)
        await take(page, frames, delay_ms=150, repeat=8)

        # Wait for gaps to load
        try:
            await page.wait_for_function("document.getElementById('gaps-list').children.length > 1", timeout=10000)
        except Exception:
            await asyncio.sleep(2)

        await take(page, frames, delay_ms=150, repeat=6)

        # Scroll through first few gap cards
        await smooth_scroll(page, frames, 0, 900, step=50, delay_ms=50)
        await take(page, frames, delay_ms=150, repeat=10)

        # Show a bit more
        await smooth_scroll(page, frames, 900, 1500, step=60, delay_ms=50)
        await take(page, frames, delay_ms=150, repeat=8)

        # Scroll back up
        await smooth_scroll(page, frames, 1500, 0, step=120, delay_ms=40)

        # ── 4. Upcoming Conference Deadlines ──────────────────────────────
        print("Navigating to Deadlines...")
        await page.goto(f"{BASE_URL}/deadlines.html", wait_until="networkidle")
        await asyncio.sleep(1.5)
        await take(page, frames, delay_ms=150, repeat=8)  # hold page load

        # Show the next-deadline banner if visible
        banner_visible = await page.evaluate(
            "!document.getElementById('next-banner').classList.contains('hidden')"
        )
        if banner_visible:
            await take(page, frames, delay_ms=150, repeat=8)

        # Scroll through deadline cards
        await smooth_scroll(page, frames, 0, 800, step=50, delay_ms=50)
        await take(page, frames, delay_ms=150, repeat=10)
        await smooth_scroll(page, frames, 800, 1400, step=60, delay_ms=50)
        await take(page, frames, delay_ms=150, repeat=8)

        await browser.close()

    # ── Build GIF ─────────────────────────────────────────────────────────
    print(f"Building GIF from {len(frames)} frames...")
    images = [fr.convert("P", palette=Image.ADAPTIVE, colors=256) for fr, _ in frames]
    durations = [d for _, d in frames]

    images[0].save(
        OUT_PATH,
        save_all=True,
        append_images=images[1:],
        optimize=False,
        duration=durations,
        loop=0,
    )
    size_mb = OUT_PATH.stat().st_size / 1_048_576
    print(f"Saved: {OUT_PATH}  ({size_mb:.1f} MB)")


if __name__ == "__main__":
    asyncio.run(main())
