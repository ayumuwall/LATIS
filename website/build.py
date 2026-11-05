"""Build the bilingual site with Python 3.11+; no third-party dependencies."""
import json
import os
import shutil
from html import escape
from pathlib import Path
from string import Template
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"


def settings():
    config = json.loads((ROOT / "site.json").read_text())
    url = os.environ.get("SITE_URL") or config["SITE_URL"]
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.query
            or parsed.fragment or parsed.username or parsed.password):
        raise ValueError("SITE_URL must be an absolute HTTPS URL without query or fragment")
    config["SITE_URL"] = url.rstrip("/") + "/"
    return config


LOCALES = {
    "en": {
        "title": "LATIS — An Agreement Engine for software development",
        "description": "LATIS records software agreements, rationale, and dependencies. The v0.3.0 Python CLI implements P0 and P1; final acceptance remains in progress.",
        "locale": "en_US", "other_locale": "ja_JP",
        "skip": "Skip to content", "home_label": "Home", "nav_label": "Main navigation",
        "concept_label": "The concept", "direction_label": "Direction", "source_label": "Source on GitHub",
    },
    "ja": {
        "title": "LATIS — ソフトウェア開発のための合意エンジン",
        "description": "LATISは合意・理由・依存関係を記録する合意エンジンです。v0.3.0のPython CLIでP0とP1を実装し、人間の指示・授権に基づく変更を扱います。完全実装の最終判定は継続中です。",
        "locale": "ja_JP", "other_locale": "en_US",
        "skip": "本文へ移動", "home_label": "ホーム", "nav_label": "メインナビゲーション",
        "concept_label": "基本アイデア", "direction_label": "設計の方向性", "source_label": "GitHubのソース",
    },
}


def build():
    config = settings()
    site_url = config["SITE_URL"]
    base = urlsplit(site_url).path
    repository = config["repository"]
    if DIST.exists():
        shutil.rmtree(DIST)
    shutil.copytree(ROOT / "static", DIST)
    template = Template((ROOT / "template.html").read_text())
    for lang, labels in LOCALES.items():
        route = "ja/" if lang == "ja" else ""
        canonical = site_url + route
        schema = {
            "@context": "https://schema.org", "@type": "SoftwareSourceCode",
            "@id": site_url + "#source", "name": "LATIS",
            "alternateName": "Layered Agreement, Traceability & Intent System",
            "description": labels["description"], "url": canonical,
            "codeRepository": repository, "license": "https://spdx.org/licenses/MIT.html",
            "developmentStatus": "v0.3.0 reference CLI; final acceptance in progress",
            "inLanguage": lang,
        }
        values = {**labels, "lang": lang, "canonical": canonical, "base": base,
                  "home": base + route, "en_url": site_url, "ja_url": site_url + "ja/",
                  "image_url": site_url + "social.png", "repository": repository}
        values = {key: escape(value, quote=True) for key, value in values.items()}
        values.update({
            "en_current": 'aria-current="page"' if lang == "en" else "",
            "ja_current": 'aria-current="page"' if lang == "ja" else "",
            "content": Template((ROOT / "content" / f"{lang}.html").read_text()).substitute(repository=escape(repository)),
            "structured_data": json.dumps(schema, ensure_ascii=False).replace("<", "\\u003c"),
        })
        destination = DIST / route
        destination.mkdir(exist_ok=True)
        (destination / "index.html").write_text(template.substitute(values), encoding="utf-8")
    (DIST / ".nojekyll").touch()
    (DIST / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {site_url}sitemap.xml\n")
    sitemap_entries = "".join(
        f'<url><loc>{escape(site_url + route)}</loc>'
        f'<xhtml:link rel="alternate" hreflang="en" href="{escape(site_url)}"/>'
        f'<xhtml:link rel="alternate" hreflang="ja" href="{escape(site_url)}ja/"/>'
        f'<xhtml:link rel="alternate" hreflang="x-default" href="{escape(site_url)}"/></url>'
        for route in ("", "ja/")
    )
    (DIST / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
        f'xmlns:xhtml="http://www.w3.org/1999/xhtml">{sitemap_entries}</urlset>\n'
    )
    # Custom-domain configuration is derived from the same URL, never a second setting.
    hostname = urlsplit(site_url).hostname
    if not hostname.endswith(".github.io"):
        if base != "/":
            raise ValueError("A GitHub Pages custom domain must use the root path")
        (DIST / "CNAME").write_text(hostname + "\n")
    print(f"Built EN + JA → {DIST} (public URL: {site_url})")


if __name__ == "__main__":
    build()
