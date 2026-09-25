import json
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from test_pipeline import audit

pytestmark = pytest.mark.e2e


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_visual(harness, happy, edges, empty, browser, width, height, theme):
    pages = [
        ("s1", "index", happy[1]["site_url"], "/"),
        ("s1", "page2", happy[1]["site_url"], "/page/2/"),
        ("s1", "post", happy[1]["site_url"], "/posts/post-00/"),
        ("s1", "tag", happy[1]["site_url"], "/tags/tag-0/"),
        ("s1", "404", happy[1]["site_url"], "/404.html"),
        ("s3", "long", edges[1]["site_url"], "/posts/long-form/"),
        ("s3", "unicode", edges[1]["site_url"], "/posts/cafe-notes/"),
        ("s8", "empty", empty[1]["site_url"], "/"),
        ("serve", "listing", f"http://localhost:{harness.port}", "/"),
    ]
    output = harness.root / "screenshots"
    output.mkdir(parents=True, exist_ok=True)
    metrics = []
    for scenario, name, origin, path in pages:
        context = browser.new_context(
            viewport={"width": width, "height": height}, color_scheme=theme, service_workers="block"
        )
        page = context.new_page()
        errors, failed, requests = [], [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on(
            "console",
            lambda message: errors.append(message.text) if message.type == "error" else None,
        )
        page.on("requestfailed", lambda request: failed.append(request.url))
        page.on("request", lambda request: requests.append((request.url, request.resource_type)))
        try:
            response = page.goto(origin + path, wait_until="networkidle")
            assert response.status == 200
            assert page.locator("h1").count() == 1
            assert page.title()
            if name == "listing":
                for href in page.locator("a[href]").evaluate_all(
                    "nodes => nodes.map(node => node.href)"
                ):
                    assert harness.get(href)[0] == 200
            if name == "long":
                assert page.locator("pre").get_attribute("tabindex") == "0"
            for selector, attribute in [
                ("meta[name=description]", "content"),
                ("link[rel=canonical]", "href"),
                ('meta[property="og:title"]', "content"),
            ]:
                assert page.locator(selector).get_attribute(attribute)
            assert page.evaluate("document.documentElement.scrollWidth") <= width
            if name != "listing":
                boxes = [
                    page.locator(selector).bounding_box()
                    for selector in (".site-header", ".site-main", ".site-footer")
                ]
                assert all(
                    abs(box["x"] - boxes[0]["x"]) < 1 and abs(box["width"] - boxes[0]["width"]) < 1
                    for box in boxes
                )
                assert boxes[0]["width"] <= 720
                column = page.locator(
                    ".post-article, .post-list, .empty-state, .page-heading"
                ).first.bounding_box()
                assert abs(column["x"] - boxes[0]["x"]) < 1

            size = page.evaluate(
                "performance.getEntriesByType('navigation').concat(performance.getEntriesByType('resource')).reduce((sum, item) => sum + item.transferSize, 0)"
            )
            assert 0 < size < 100_000, (name, size)
            toggle = page.locator(".theme-toggle")
            for _ in range(30):
                page.keyboard.press("Tab")
                if toggle.evaluate("node => node === document.activeElement"):
                    break
            assert toggle.evaluate("node => node === document.activeElement")
            assert toggle.evaluate(
                "node => parseFloat(getComputedStyle(node).outlineWidth) > 0 && getComputedStyle(node).outlineStyle !== 'none'"
            )
            page.mouse.click(width - 2, 2)
            page.screenshot(
                path=str(output / f"{scenario}-{name}-{width}-{theme}.png"),
                full_page=True,
                animations="disabled",
            )
            chosen = "light" if theme == "dark" else "dark"
            toggle.click()
            page.reload(wait_until="networkidle")
            assert page.evaluate("document.documentElement.dataset.theme") == chosen
            assert page.evaluate("localStorage.getItem('theme')") == chosen
            page.add_script_tag(path=str(Path(__file__).with_name("axe-core-4.13.0.min.js")))
            results = page.evaluate("async () => await axe.run(document)")
            violations = [
                row for row in results["violations"] if row["impact"] in ("critical", "serious")
            ]
            assert not violations, violations
            assert not errors and not failed, (errors, failed)
            assert all(
                urlsplit(url).hostname == "localhost"
                or urlsplit(url).hostname.endswith(".localhost")
                for url, _ in requests
            )
            assert all(kind != "font" for _, kind in requests)
            metrics.append(
                {
                    "screenshot": f"{scenario}-{name}-{width}-{theme}.png",
                    "transfer_bytes": size,
                    "serious_or_critical": 0,
                    "console_errors": errors,
                    "failed_requests": failed,
                }
            )
        finally:
            context.close()
    (harness.root / f"visual-{width}-{theme}.json").write_text(json.dumps(metrics, indent=2))
    for data in (happy[1], edges[1], empty[1]):
        audit(browser, harness, data)
