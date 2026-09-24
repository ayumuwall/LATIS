"""Validate generated HTML, local links, translated routes and SEO metadata."""
import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit
from xml.etree import ElementTree

from build import DIST, settings


class Page(HTMLParser):
    def __init__(self, path):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.ids = []
        self.json_ld = []
        self.in_json = False
        self.in_title = False
        self.title = ""
        self.feed(path.read_text())

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.tags.append((tag, attrs))
        if "id" in attrs:
            self.ids.append(attrs["id"])
        if tag == "script":
            assert attrs.get("type") == "application/ld+json", "Unexpected runtime JavaScript"
            self.in_json = True
        if tag == "title":
            self.in_title = True

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_json = False
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_json:
            self.json_ld.append(data)
        if self.in_title:
            self.title += data

    def select(self, tag, **attrs):
        return [a for t, a in self.tags if t == tag and all(a.get(k) == v for k, v in attrs.items())]


def check():
    config = settings()
    url = config["SITE_URL"]
    base = urlsplit(url)
    pages = {path: Page(path) for path in DIST.rglob("*.html")}
    assert len(pages) == 2
    assert len({page.title for page in pages.values()}) == 2, "Titles must be unique"
    for path, page in pages.items():
        lang = "ja" if path.parent.name == "ja" else "en"
        canonical = url + ("ja/" if lang == "ja" else "")
        assert page.select("html", lang=lang)
        assert len(page.select("h1")) == 1
        assert page.title.startswith("LATIS")
        previous_heading = 0
        for tag, _ in page.tags:
            if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
                level = int(tag[1])
                assert level <= previous_heading + 1, "Skipped heading level"
                previous_heading = level
        assert len(page.select("main")) == 1
        assert len(page.ids) == len(set(page.ids)), "Duplicate IDs"
        assert page.select("link", rel="canonical", href=canonical)
        assert page.select("meta", property="og:url", content=canonical)
        for locale, route in (("en", ""), ("ja", "ja/"), ("x-default", "")):
            assert page.select("link", rel="alternate", hreflang=locale, href=url + route)
        for key in ("description", "twitter:card", "twitter:image", "twitter:title", "twitter:description"):
            assert page.select("meta", name=key)[0]["content"]
        for key in ("og:title", "og:description", "og:image", "og:image:alt"):
            assert page.select("meta", property=key)[0]["content"]
        schema = json.loads("".join(page.json_ld))
        assert schema["@type"] == "SoftwareSourceCode"
        assert schema["codeRepository"] == config["repository"]
        assert schema["url"] == canonical
        for tag, attrs in page.tags:
            if tag == "img":
                assert "alt" in attrs
            for key in ("href", "src"):
                if key not in attrs:
                    continue
                target = urlsplit(urljoin(canonical, attrs[key]))
                if target.netloc != base.netloc:
                    # Source links must point to files that exist in this repository.
                    prefix = config["repository"] + "/blob/main/"
                    if attrs[key].startswith(prefix):
                        assert (DIST.parent.parent / attrs[key][len(prefix):]).is_file(), attrs[key]
                    continue
                assert target.path.startswith(base.path), f"Link escapes deployment base: {attrs[key]}"
                local = DIST / unquote(target.path[len(base.path):])
                if local.is_dir():
                    local /= "index.html"
                assert local.is_file(), f"Broken link: {attrs[key]} in {path}"
                if target.fragment:
                    assert local in pages and unquote(target.fragment) in pages[local].ids
        social = page.select("meta", property="og:image")[0]["content"]
        assert social == url + "social.png" and (DIST / "social.png").is_file()
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    sitemap = ElementTree.parse(DIST / "sitemap.xml")
    assert [node.text for node in sitemap.findall("s:url/s:loc", ns)] == [url, url + "ja/"]
    assert f"Sitemap: {url}sitemap.xml" in (DIST / "robots.txt").read_text()
    assert (DIST / ".nojekyll").is_file()
    assert (DIST / "CNAME").exists() == (not base.hostname.endswith(".github.io"))
    print("PASS: both languages, local links/anchors, repository source links, SEO, JSON-LD, sitemap and base path")


if __name__ == "__main__":
    check()
