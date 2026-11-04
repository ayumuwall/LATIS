# LATIS website

A small, bilingual concept site, separate from the technical documentation. English lives at `/`; Japanese at `/ja/`, relative to the deployment base path.

## Stack and source

Python 3.11+ and its standard library generate plain HTML and CSS. There are no installed build dependencies, browser scripts, external fonts, trackers, or runtime services. The shared template handles navigation and metadata; the two editorial HTML files contain the localized content. Native HTML `details` provides the expandable example without JavaScript.

- `site.json`: the public `SITE_URL` and repository URL
- `template.html`: shared document, header, footer, and metadata
- `content/en.html`, `content/ja.html`: localized page sections
- `static/style.css`: responsive layout and concept diagram
- `static/favicon.svg`: site icon
- `static/social.svg`, `static/social.png`: editable social artwork and its 1200 × 630 raster export (PNG is used for crawler compatibility)
- `build.py`: generates `dist/`, including sitemap, robots.txt, and custom-domain CNAME when appropriate
- `check.py`: checks local links, fragment IDs, source-document links, locale metadata, JSON-LD, sitemap, and deployment paths
- `serve.py`: local preview with the actual deployment base path
- `../.github/workflows/pages.yml`: build/check on pull requests; build/check/deploy on main

Content is based on `README.md`, `README.ja.md`, `docs/LATIS_Spec.ja.md`, `docs/LATIS_API.ja.md`, and `docs/LATIS_Operation.ja.md`. Current unresolved design boundaries are also described in `docs/LATIS_Concerns.ja.md`. These documents remain the authority; update both translations when the design or release status changes.

## Local development

From the repository root:

```sh
python3 website/build.py
python3 -m compileall -q website
python3 website/check.py
python3 website/serve.py
```

Visit <http://127.0.0.1:8000/LATIS/> and <http://127.0.0.1:8000/LATIS/ja/> with the default configuration. Stop the server with Ctrl+C. Rebuild after edits; generated output is ignored by Git. There is no separate lint/typecheck toolchain; the Python syntax check and generated-output checks run in CI.

## GitHub Pages

1. In the repository's **Settings → Pages → Build and deployment → Source**, select **GitHub Actions**.
2. Push the website/workflow changes to `main`, or run **Website / GitHub Pages** manually from Actions.
3. The build job checks the output and uploads only `website/dist`. The deployment job publishes it through the `github-pages` environment.

Default public address: <https://ayumuwall.github.io/LATIS/>. Pull requests validate without deploying. Subsequent pushes changing `website/` or the Pages workflow on `main` deploy automatically. Review the `github-pages` environment's protection rules if a deployment waits for approval.

The workflow follows [GitHub's custom Pages workflow guidance](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages): explicit artifact upload, separate dependent deploy job, and `pages: write` / `id-token: write` limited to deployment. Enabling Pages and completing a successful hosted Actions run are repository-side steps, not accomplished by the local build.

## SITE_URL and a custom domain

Change **only `SITE_URL` in `website/site.json`** to the complete HTTPS public base URL, including any repository path. Trailing slash is normalized. Examples:

- Project Pages: `https://ayumuwall.github.io/LATIS/`
- Custom domain: `https://your-domain.example/`

Builds derive asset URLs, language links, canonical URLs, hreflang, Open Graph / Twitter image URLs, JSON-LD, sitemap, and robots sitemap location from this setting. A non-`github.io` host also generates `dist/CNAME`. Custom domains must use the root path.

For a custom domain, also configure DNS and **Settings → Pages → Custom domain**, verify ownership as appropriate, and enable HTTPS. A generated CNAME file alone does not configure DNS or GitHub's account settings. Avoid adding a separate manually maintained CNAME.

`SITE_URL` can also be overridden as an environment variable for build/validation experiments. Use the same value for both commands:

```sh
SITE_URL=https://your-domain.example/ python3 website/build.py
SITE_URL=https://your-domain.example/ python3 website/check.py
# Restore the normal local build afterward:
python3 website/build.py
```

A project Pages URL serves `robots.txt` under `/LATIS/`; crawlers consult robots at the host root, which this project cannot control. The sitemap is still available at `/LATIS/sitemap.xml` for direct submission to search engines. On a custom root domain, the generated robots file is served at its standard location.

## Verification and further work

Initial implementation was checked in Chrome at 320, 390, 768, and 1440px in both languages, with JavaScript disabled and reduced motion enabled. Checks covered overflow, asset responses, keyboard skip navigation, and the native example disclosure; desktop and mobile screenshots were visually reviewed. Both project-path and custom-domain-root builds passed the link and metadata checker.

Before publishing, recheck the current copy against the source documents and inspect both languages. After publishing, verify the actual HTTPS URLs, redirects and social-card fetch, run Lighthouse against the hosted site, and submit the sitemap in Search Console if desired. No Lighthouse score or live deployment is claimed by the local checks. Keep installation instructions off the site until an installable implementation exists.

The social PNG is committed so normal builds need no image tooling. If the social artwork changes, export `static/social.svg` to `static/social.png` at 1200 × 630 with an SVG renderer, then rebuild.
