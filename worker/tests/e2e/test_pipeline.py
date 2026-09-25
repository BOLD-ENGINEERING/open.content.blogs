from __future__ import annotations

import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from html import unescape
from pathlib import Path
from urllib.parse import urlsplit
from xml.etree import ElementTree

import pytest
from conftest import ROOT, command, post

pytestmark = pytest.mark.e2e


def links(html, prefix):
    return set(re.findall(r'href="(' + re.escape(prefix) + r'[^"?#]*)"', html))


def published(harness, data):
    status, rss, _ = harness.get(data["site_url"], "/rss.xml")
    assert status == 200
    return {
        urlsplit(item.text).path for item in ElementTree.fromstring(rss).findall(".//item/link")
    }


def audit(browser, harness, data):
    context = browser.new_context(service_workers="block")
    page = context.new_page()
    errors, requests, failed = [], [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on(
        "console", lambda message: errors.append(message.text) if message.type == "error" else None
    )
    page.on("request", lambda request: requests.append((request.url, request.resource_type)))
    page.on("requestfailed", lambda request: failed.append(request.url))
    origin = data["site_url"]
    todo, seen = {"/"}, set()
    try:
        while todo:
            path = todo.pop()
            if path in seen:
                continue
            response = page.goto(origin + path, wait_until="networkidle")
            assert response.status == 200, path
            seen.add(path)
            for href in page.locator("a[href]").evaluate_all("nodes => nodes.map(n => n.href)"):
                address = urlsplit(href)
                assert address.netloc == urlsplit(origin).netloc, href
                if address.path not in seen:
                    todo.add(address.path)
        expected = published(harness, data)
        assert expected <= seen
        dist = Path(data["build"]["dist_dir"])
        tags = {
            "/" + str(path.relative_to(dist)).removesuffix("index.html")
            for path in dist.glob("tags/*/index.html")
        }
        assert tags <= seen
        assert requests and all(
            urlsplit(url).hostname == "localhost" or urlsplit(url).hostname.endswith(".localhost")
            for url, _ in requests
        )
        assert not any(kind == "font" for _, kind in requests)
        assert not errors and not failed, (errors, failed)
    finally:
        context.close()
    return seen


def test_s1_happy(harness, happy, browser):
    _, data = happy
    origin = data["site_url"]
    dist = Path(data["build"]["dist_dir"])
    assert len(list(dist.glob("posts/*/index.html"))) == 12
    assert harness.get(origin)[1].count('class="post-card"') == 10
    assert harness.get(origin, "/page/2/")[1].count('class="post-card"') == 2
    for tag in range(4):
        html = harness.get(origin, f"/tags/tag-{tag}/")[1]
        assert links(html, "/posts/") == {
            f"/posts/post-{n:02d}/" for n in range(12) if n % 4 == tag
        }
    assert len(published(harness, data)) == 12
    seen = audit(browser, harness, data)
    sitemap = ElementTree.fromstring(harness.get(origin, "/sitemap-0.xml")[1])
    sitemap_urls = {element.text for element in sitemap.iter() if element.tag.endswith("}loc")}
    assert {origin + path for path in seen} <= sitemap_urls
    for path in seen:
        html = harness.get(origin, path)[1]
        assert f'rel="canonical" href="{origin}' in html
        assert f'property="og:url" content="{origin}' in html


def test_s2_promotion(harness, browser):
    repo = harness.repo("promotion")
    for n in range(12):
        repo.write(f"post-{n:02d}.md", post(n))
    repo.commit()
    main = harness.build(repo, "promotion")
    repo.git("checkout", "-b", "staging")
    repo.write("post-12.md", post(12))
    repo.commit("2024-02-03T12:00:00+00:00")
    staging = harness.build(repo, "promotion", "staging")
    assert len(published(harness, main)) == 12
    assert len(published(harness, staging)) == 13
    assert harness.get(main["site_url"], "/posts/post-12/")[0] == 404
    audit(browser, harness, main)
    audit(browser, harness, staging)
    repo.git("checkout", "main")
    repo.git("merge", "--ff-only", "staging")
    repo.git("push", "origin", "main")
    promoted = harness.build(repo, "promotion")
    assert len(published(harness, promoted)) == 13
    assert published(harness, promoted) == published(harness, staging)
    audit(browser, harness, promoted)


def test_s3_edges(harness, edges, browser):
    _, data = edges
    report = data["build"]["report"]
    assert report["loaded"] == 8 and report["skipped"] == []
    actual = {(row["file"], row["field"]) for row in report["fallbacks"]}
    assert actual == {
        (name + ".md", field)
        for name, fields in {
            "empty-file": ["title", "date"],
            "malformed-date": ["date"],
            "missing-title": ["title"],
            "no-frontmatter": ["title", "date"],
        }.items()
        for field in fields
    }
    assert harness.get(data["site_url"], "/posts/draft-post/")[0] == 404
    assert harness.get(data["site_url"], "/posts/cafe-notes/")[0] == 200
    html = harness.get(data["site_url"], "/posts/long-form/")[1]
    assert html.count("readable fixture words.") >= 290
    rendered = unescape(
        re.sub(r"<[^>]+>", "", html.split('<div class="post-body">', 1)[1].split("</div>", 1)[0])
    )
    source = (ROOT / "test-fixtures/sample-content/long-form.md").read_text().split("---\n")[-1]
    expected = re.sub(r"^#{1,6}\s+|^```.*$", "", source, flags=re.MULTILINE)
    assert rendered.split() == expected.split()
    assert "<h2" in html and "<pre" in html and "print(message)" in rendered
    audit(browser, harness, data)


def test_s4_hostile(harness, browser):
    repo = harness.repo("hostile")
    repo.write("safe.md", post(1))
    (repo.work / "passwd.md").symlink_to("/etc/passwd")
    (repo.work / "outside").symlink_to(repo.work.parent)
    for name in (".hidden/secret.md", ".secret.md", "danger.mdx", "image.png", "notes.txt"):
        repo.write(name, "forbidden")
    repo.commit()
    data = harness.build(repo, "hostile")
    manifest = data["build"]["manifest"]
    assert manifest["files"] == ["safe.md"]
    assert {row["path"]: row["reason"] for row in manifest["skipped"]} == {
        "passwd.md": "symlink not permitted",
        "outside": "symlink not permitted",
        ".hidden/secret.md": "hidden path",
        ".secret.md": "hidden path",
        "danger.mdx": "mdx not permitted",
        "image.png": "not a markdown file",
        "notes.txt": "not a markdown file",
    }
    content = Path(data["build"]["dist_dir"]).parent / "content"
    assert sorted(p.name for p in content.rglob("*") if p.is_file()) == ["safe.md"]
    assert not (content.parent / "src").exists()
    audit(browser, harness, data)


def test_s4b_oversize(harness, browser):
    repo = harness.repo("oversize")
    repo.write("safe.md", post(1))
    repo.commit()
    original = harness.build(repo, "oversize")
    before = (harness.serve_root / "oversize/main/.deploy.json").read_bytes()
    repo.write("huge.md", "x" * (3 * 1024 * 1024))
    repo.commit()
    failed = harness.build(repo, "oversize", success=False)
    assert failed["build"]["status"] == "failed"
    assert "2 MB" in failed["build"]["error"] and "huge.md" in failed["build"]["error"]
    assert failed["deploy"] is None
    assert (harness.serve_root / "oversize/main/.deploy.json").read_bytes() == before
    assert published(harness, original) == {"/posts/safe/"}
    audit(browser, harness, original)


def test_s5_subdir(harness, browser):
    repo = harness.repo("subdir")
    repo.write("stray.md", post(1))
    repo.write("posts/nested/inside.md", post(2))
    repo.commit()
    data = harness.build(repo, "subdir", extra=("--subdir", "posts"))
    assert data["build"]["manifest"]["files"] == ["nested/inside.md"]
    assert published(harness, data) == {"/posts/inside/"}
    audit(browser, harness, data)


def test_s6_removal(harness, browser):
    repo = harness.repo("removal")
    repo.write("removed.md", post(1))
    repo.write("old.md", post(2))
    repo.commit()
    harness.build(repo, "removal")
    (repo.work / "removed.md").unlink()
    repo.git("mv", "old.md", "new.md")
    repo.commit("2024-03-01T12:00:00+00:00")
    data = harness.build(repo, "removal")
    for path in ("removed", "old"):
        status, html, _ = harness.get(data["site_url"], f"/posts/{path}/")
        assert status == 404 and 'href="/"' in html and "404" in html
    assert published(harness, data) == {"/posts/new/"}
    sitemap = harness.get(data["site_url"], "/sitemap-0.xml")[1]
    assert (
        "/posts/new/" in sitemap
        and "/posts/old/" not in sitemap
        and "/posts/removed/" not in sitemap
    )
    audit(browser, harness, data)


def test_s7_dates(harness, browser):
    repo = harness.repo("dates")
    repo.write("café-first.md", "An undated first post.")
    repo.commit("2021-05-06T12:00:00+00:00")
    repo.write("second.md", "An undated second post.")
    repo.commit("2022-07-08T12:00:00+00:00")

    def dates(data):
        return [
            re.search(
                r'<time datetime="([^"]+)"', harness.get(data["site_url"], f"/posts/{slug}/")[1]
            )[1]
            for slug in ("cafe-first", "second")
        ]

    first = harness.build(repo, "dates")
    expected = ["2021-05-06T12:00:00.000Z", "2022-07-08T12:00:00.000Z"]
    assert dates(first) == expected
    repo.write("unrelated.txt", "unrelated")
    repo.commit("2023-08-09T12:00:00+00:00")
    second = harness.build(repo, "dates")
    assert dates(second) == expected
    audit(browser, harness, second)


def test_s8_refs(harness, empty, browser):
    repo, empty_data = empty
    sha = repo.git("rev-parse", "HEAD")
    data = harness.build(repo, "sha", sha)
    assert data["build"]["sha"] == sha
    before = set(harness.build_root.iterdir())
    failed = harness.build(repo, "bad-ref", "does-not-exist", success=False)
    assert "does-not-exist" in failed["build"]["error"]
    assert set(harness.build_root.iterdir()) == before
    result = harness.cli(
        "build",
        "--repo",
        (harness.root / "nonexistent.git").as_uri(),
        "--slug",
        "missing",
        "--json",
    )
    assert result.returncode == 1 and json.loads(result.stdout)["build"]["status"] == "failed"
    assert "Traceback" not in result.stderr and set(harness.build_root.iterdir()) == before
    assert "No posts published yet." in harness.get(empty_data["site_url"])[1]
    audit(browser, harness, data)
    audit(browser, harness, empty_data)


def test_s9_rollback(harness, browser):
    repo = harness.repo("rollback")
    repo.write("a.md", post(1))
    sha = repo.commit()
    data = harness.build(repo, "rollback")
    repo.write("b.md", post(2))
    repo.commit("2024-03-01T12:00:00+00:00")
    harness.build(repo, "rollback")
    assert len(published(harness, data)) == 2
    result = harness.cli("rollback", "--slug", "rollback", "--sha", sha)
    assert result.returncode == 0, result.stderr
    assert published(harness, data) == {"/posts/a/"}
    assert json.loads((harness.serve_root / "rollback/main/.deploy.json").read_text())["sha"] == sha
    assert harness.cli("rollback", "--slug", "rollback", "--sha", "0" * 40).returncode == 1
    audit(browser, harness, data)


def test_s10_concurrency(harness, browser):
    repos = [harness.repo(f"concurrent-{n}") for n in range(2)]
    for n, repo in enumerate(repos):
        repo.write(f"only-{n}.md", post(n))
        repo.commit()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(harness.build, repo, f"concurrent-{n}") for n, repo in enumerate(repos)
        ]
        results = [future.result() for future in futures]
    for n, data in enumerate(results):
        assert published(harness, data) == {f"/posts/only-{n}/"}
        audit(browser, harness, data)
    assert results[0]["build"]["dist_dir"] != results[1]["build"]["dist_dir"]
    assert command(["git", "status", "--porcelain", "web/"], ROOT) == ""


def test_s11_timeout(harness, happy):
    repo, _ = happy
    data = harness.build(repo, "timeout", success=False, env={"BUILD_TIMEOUT": "1"})
    assert data["build"]["status"] == "timeout" and data["deploy"] is None
    marker = f"BUILD_OUT_DIR={data['build']['dist_dir']}".encode()
    survivors = []
    for process in Path("/proc").iterdir():
        if process.name.isdigit():
            try:
                environment = (process / "environ").read_bytes().split(b"\0")
                cmd = (process / "cmdline").read_bytes()
            except OSError:
                continue
            if marker in environment and (b"node" in cmd or b"pnpm" in cmd):
                survivors.append(process.name)
    assert not survivors, survivors


def test_s12_determinism(harness, happy, browser):
    repo, _ = happy
    sha = repo.git("rev-parse", "HEAD")
    first = harness.build(repo, "deterministic", sha)
    second = harness.build(repo, "deterministic", sha)

    def hashes(data):
        root = Path(data["build"]["dist_dir"])
        return {
            str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*")
            if path.is_file()
        }

    assert first["build"]["dist_dir"] != second["build"]["dist_dir"]
    assert hashes(first) == hashes(second)
    assert "_build-report.json" in hashes(first)
    audit(browser, harness, second)
