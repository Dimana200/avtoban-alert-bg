"""Open the site's map page (as the site and as the app) and fail on any script error."""
import asyncio, os, sys
from playwright.async_api import async_playwright

SITE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "site")


async def local(route):
    path = route.request.url.split("/avtoban-alert-bg/", 1)[1].split("?")[0] or "index.html"
    f = os.path.join(SITE, path)
    if os.path.isfile(f):
        await route.fulfill(path=f)
    else:
        await route.fulfill(status=404, body="")


async def main():
    bad = False
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for q in ("?app=1", ""):
            pg = await b.new_page(viewport={"width": 390, "height": 780})
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            await pg.route("https://dimana200.github.io/avtoban-alert-bg/**", local)
            await pg.goto("https://dimana200.github.io/avtoban-alert-bg/index.html" + q)
            await pg.wait_for_timeout(5000)
            has_map = await pg.evaluate("typeof map === 'object' && !!map.getZoom")
            print("page", q or "(site)", "errors:", errs, "map:", has_map)
            bad = bad or bool(errs) or not has_map
        await b.close()
    sys.exit(1 if bad else 0)


asyncio.run(main())
