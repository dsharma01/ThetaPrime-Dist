#!/usr/bin/env python3
"""Regenerate docs/*.html on the ThetaPrime marketing site from the app's docs/*.md.

Run after every release:

    python scripts/build_docs.py <extracted-docs-src-dir> <app-repo-dir> <version>

<extracted-docs-src-dir> is a plain folder of the app's docs/ tree (e.g. from
`git archive origin/main docs`). <app-repo-dir> is a real git checkout of that
same app repo (with origin/main fetched) -- used only to look up each source
file's last-commit date for the per-page "last updated" footer. <version> is
the app version each page describes (e.g. "0.30.1").

Reads the site's own index.html for its header/footer/CSS chrome so generated
pages stay visually identical to the homepage (same theme, same mobile nav)
without a templating engine or new dependency -- just the already-installed
`markdown` package.

Internal docs (docs/dev/*) and dead ones (docs/archive/*) are deliberately
never in PAGES below -- do not add them without checking they're meant to be
public.
"""
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import markdown as md

SITE_ROOT = Path(__file__).resolve().parent.parent
INDEX_HTML = SITE_ROOT / "index.html"
DOCS_OUT = SITE_ROOT / "docs"

# (source .md relative to --src, output .html relative to docs/, title, group)
PAGES = [
    ("installation.md", "installation.html", "Installation Guide", "Getting Started"),
    ("setup.md", "setup.html", "Setup Guide", "Getting Started"),
    ("obtaining-credentials.md", "obtaining-credentials.html", "Obtaining API Credentials", "Getting Started"),
    ("brokers/kite.md", "brokers/kite.html", "Kite (Zerodha) Setup", "Brokers"),
    ("brokers/breeze.md", "brokers/breeze.html", "Breeze (ICICI Direct) Setup", "Brokers"),
    ("brokers/dhan.md", "brokers/dhan.html", "Dhan Setup", "Brokers"),
    ("strategy-composer.md", "strategy-composer.html", "Strategy Composer Guide", "Building Strategies"),
    ("composer-strategy-examples.md", "composer-strategy-examples.html", "Composer Strategy Examples", "Building Strategies"),
    ("strategy-usage.md", "strategy-usage.html", "Strategy Configuration & Usage", "Operations"),
    ("data-management.md", "data-management.html", "Data Management", "Operations"),
    ("mcp-setup.md", "mcp-setup.html", "MCP Setup (AI Assistant Tools)", "Operations"),
    ("security.md", "security.html", "Security", "Security & Licensing"),
    ("licensing.md", "licensing.html", "License & Activation", "Security & Licensing"),
]
IMAGES = ["images/strategy-composer-layout.svg", "images/strategy-composer-save.svg"]

DOC_CSS = """
.doc-page{padding-block:clamp(2.5rem,5vw,4rem);max-width:52rem;margin-inline:auto;}
.doc-crumb{font-family:'IBM Plex Mono',monospace;font-size:0.78rem;color:var(--text-muted);margin-bottom:1.5rem;}
.doc-crumb a{color:var(--text-muted);}
.doc-crumb a:hover{color:var(--accent-ink);}
.doc-body h1{font-size:clamp(1.8rem,4vw,2.6rem);margin-bottom:1rem;}
.doc-body h2{font-size:clamp(1.3rem,2.6vw,1.7rem);margin-top:2.4rem;margin-bottom:0.9rem;padding-top:1.4rem;border-top:1px solid var(--border);}
.doc-body h3{font-size:1.15rem;margin-top:1.8rem;margin-bottom:0.6rem;text-transform:none;}
.doc-body h4{font-family:'IBM Plex Mono',monospace;font-size:0.85rem;margin-top:1.4rem;margin-bottom:0.5rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.04em;}
.doc-body p,.doc-body li{color:var(--text-muted);font-size:0.96rem;line-height:1.65;}
.doc-body>p,.doc-body>ul,.doc-body>ol,.doc-body>table,.doc-body>blockquote,.doc-body>div{margin-bottom:1rem;}
.doc-body strong{color:var(--text);}
.doc-body a{color:var(--accent-ink);}
.doc-body ul,.doc-body ol{padding-left:1.4rem;}
.doc-body li{margin-bottom:0.35rem;}
.doc-body code{font-family:'IBM Plex Mono',monospace;font-size:0.86em;background:var(--bg-inset);border:1px solid var(--border);border-radius:4px;padding:0.1em 0.4em;}
.doc-body pre{background:var(--bg-inset);border:1px solid var(--border);border-radius:8px;padding:1rem;overflow-x:auto;margin-bottom:1.2rem;}
.doc-body pre code{border:none;background:none;padding:0;}
.doc-body blockquote{border-left:3px solid var(--accent-ink);padding-left:1rem;color:var(--text-muted);margin-left:0;}
.doc-body img{max-width:100%;border:1px solid var(--border);border-radius:8px;}
.doc-body hr{border:none;border-top:1px solid var(--border);margin-block:1.6rem;}
.doc-body table{width:100%;border-collapse:collapse;font-size:0.88rem;margin-bottom:1.2rem;overflow-x:auto;display:block;}
.doc-body th,.doc-body td{border:1px solid var(--border);padding:0.5rem 0.7rem;text-align:left;}
.doc-body th{background:var(--bg-inset);font-family:'IBM Plex Mono',monospace;font-size:0.78rem;text-transform:uppercase;letter-spacing:0.03em;}
.doc-hub-group{margin-bottom:2.2rem;}
.doc-hub-group h2{font-size:1.05rem;font-family:'IBM Plex Mono',monospace;text-transform:uppercase;letter-spacing:0.04em;color:var(--text-muted);border:none;margin:0 0 0.8rem;padding:0;}
.doc-hub-list{display:flex;flex-direction:column;gap:0.5rem;}
.doc-hub-list a{display:block;padding:0.85rem 1rem;border:1px solid var(--border);border-radius:9px;background:var(--bg-elevated);color:var(--text);text-decoration:none;font-size:0.94rem;}
.doc-hub-list a:hover{border-color:var(--accent-ink);}
.doc-toc{border:1px solid var(--border);border-radius:9px;background:var(--bg-elevated);padding:1rem 1.3rem;margin-bottom:2rem;}
.doc-toc-label{display:block;font-family:'IBM Plex Mono',monospace;font-size:0.72rem;text-transform:uppercase;letter-spacing:0.06em;color:var(--text-muted);margin-bottom:0.6rem;}
.doc-toc ul{list-style:none;padding-left:0;margin:0;font-size:0.88rem;}
.doc-toc ul ul{padding-left:1.1rem;margin-top:0.3rem;}
.doc-toc li{margin-bottom:0.4rem;}
.doc-toc a{color:var(--text-muted);text-decoration:none;}
.doc-toc a:hover{color:var(--accent-ink);}
.doc-toc ul ul a{font-size:0.85em;}
.doc-meta{margin-top:2.5rem;padding-top:1rem;border-top:1px solid var(--border);font-family:'IBM Plex Mono',monospace;font-size:0.72rem;color:var(--text-muted);}

/* ── Persistent docs sidebar + search (every doc detail page) ──────────── */
.docs-layout{display:flex;align-items:flex-start;gap:2.5rem;}
.docs-layout .doc-page{flex:1;min-width:0;padding-block:clamp(2.5rem,5vw,4rem);}
.docs-sidebar{position:sticky;top:1.5rem;width:210px;flex-shrink:0;margin-top:clamp(2.5rem,5vw,4rem);}
.docs-sidebar-mobile{display:none;margin-top:1.5rem;}
.docs-nav-block{display:flex;flex-direction:column;gap:0.2rem;}
.doc-search-input{width:100%;box-sizing:border-box;background:var(--bg-elevated);border:1px solid var(--border);border-radius:8px;color:var(--text);font-size:0.85rem;padding:0.5rem 0.7rem;margin-bottom:0.9rem;}
.doc-search-input:focus-visible{outline:2px solid var(--accent-ink);outline-offset:1px;}
.doc-search-empty{font-size:0.8rem;color:var(--text-muted);margin:0 0 0.9rem;}
.docs-nav-group{margin-bottom:1.1rem;}
.docs-nav-label{display:block;font-family:'IBM Plex Mono',monospace;font-size:0.68rem;text-transform:uppercase;letter-spacing:0.06em;color:var(--text-muted);margin-bottom:0.4rem;}
.docs-nav-block .doc-link{display:block;padding:0.35rem 0.5rem;margin-inline:-0.5rem;border-radius:6px;color:var(--text-muted);text-decoration:none;font-size:0.86rem;}
.docs-nav-block .doc-link:hover{background:var(--bg-elevated);color:var(--text);}
.docs-nav-block .doc-link.active{background:var(--bg-elevated);color:var(--accent-ink);font-weight:600;}
.docs-sidebar-mobile summary{cursor:pointer;font-family:'IBM Plex Mono',monospace;font-size:0.78rem;text-transform:uppercase;letter-spacing:0.05em;color:var(--text-muted);padding:0.75rem 1rem;border:1px solid var(--border);border-radius:9px;background:var(--bg-elevated);}
.docs-sidebar-mobile[open] summary{border-radius:9px 9px 0 0;margin-bottom:0;}
.docs-sidebar-mobile .docs-nav-block{border:1px solid var(--border);border-top:none;border-radius:0 0 9px 9px;padding:1rem;background:var(--bg-inset);}
@media (max-width:900px){
  .docs-layout{flex-direction:column;}
  .docs-sidebar{display:none;}
  .docs-sidebar-mobile{display:block;}
  .docs-layout .doc-page{padding-block:1.5rem clamp(2.5rem,5vw,4rem);width:100%;}
}

/* ── Prev/Next doc footer ─────────────────────────────────────────────── */
.doc-prev-next{display:flex;justify-content:space-between;gap:1rem;margin-top:3rem;padding-top:1.25rem;border-top:1px solid var(--border);}
.doc-prev-next-link{display:flex;flex-direction:column;gap:0.15rem;max-width:48%;padding:0.6rem 0.8rem;border:1px solid var(--border);border-radius:9px;background:var(--bg-elevated);color:var(--text);text-decoration:none;font-size:0.86rem;font-weight:600;}
.doc-prev-next-link.next{text-align:right;margin-left:auto;}
.doc-prev-next-link:hover{border-color:var(--accent-ink);color:var(--accent-ink);}
"""

DOC_JS = """
<script>
document.querySelectorAll('.docs-nav-block').forEach(function(block){
  var input = block.querySelector('.doc-search-input');
  var empty = block.querySelector('.doc-search-empty');
  var groups = Array.from(block.querySelectorAll('.docs-nav-group'));
  var indexUrl = block.getAttribute('data-search-index');
  var indexData = null, indexPromise = null;
  function ensureIndex(){
    if (!indexPromise) indexPromise = fetch(indexUrl).then(function(r){ return r.json(); }).then(function(d){ indexData = d; });
    return indexPromise;
  }
  function apply(term){
    var anyVisible = false;
    groups.forEach(function(g){
      var groupHasMatch = false;
      g.querySelectorAll('.doc-link').forEach(function(a){
        var url = a.getAttribute('data-url');
        var entry = indexData && indexData.find(function(e){ return e.url === url; });
        var match = !term || a.textContent.toLowerCase().includes(term) || (entry && entry.text.includes(term));
        a.hidden = !match;
        if (match) { groupHasMatch = true; anyVisible = true; }
      });
      g.hidden = !groupHasMatch;
    });
    empty.hidden = anyVisible || !term;
  }
  input.addEventListener('input', function(e){
    var term = e.target.value.trim().toLowerCase();
    apply(term);
    if (term) ensureIndex().then(function(){ if (input.value.trim().toLowerCase() === term) apply(term); });
  });
});
</script>
"""

TOC_MIN_HEADINGS = 4  # below this, a page's short enough that a TOC just adds noise

MD_EXTENSIONS = ["tables", "fenced_code", "sane_lists", "toc"]


def load_chrome():
    """Pull <style>, favicon links, header, and footer+script chrome out of index.html."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    style = re.search(r"<style>(.*?)</style>", html, re.S).group(1)
    favicons = "\n".join(re.findall(r'<link rel="icon"[^>]*>', html))
    header = re.search(r"(<header class=\"nav\">.*?</header>)", html, re.S).group(1)
    footer = re.search(r"(<footer>.*?</html>)", html, re.S).group(1)
    return style, favicons, header, footer


def last_updated(app_repo_dir, src_rel):
    """Git commit date (origin/main) of docs/<src_rel> in the app repo -- the real
    content date, not "today", so the footer stays accurate even on a run where
    a given page's source didn't actually change."""
    result = subprocess.run(
        ["git", "-C", str(app_repo_dir), "log", "-1", "--follow", "--format=%ad",
         "--date=short", "origin/main", "--", f"docs/{src_rel}"],
        capture_output=True, text=True, check=True,
    )
    out = result.stdout.strip()
    if not out:
        raise RuntimeError(f"no git history found for docs/{src_rel} on origin/main")
    return out


def rewrite_chrome_links(block, root):
    """Point in-page anchors (#how etc.), the standalone pricing page, and the
    brand logo back at the homepage/site root."""
    block = re.sub(r'href="#(top|how|composer|safety|monitoring|faq)"',
                    lambda m: f'href="{root}index.html#{m.group(1)}"', block)
    block = block.replace('href="pricing.html"', f'href="{root}pricing.html"')
    # Highlight "Docs" as current section on doc pages.
    block = block.replace('href="docs/index.html">Docs</a>',
                           f'href="{root}docs/index.html" style="color:var(--text)">Docs</a>')
    return block


def render_toc_ul(tokens):
    items = []
    for t in tokens:
        nested = render_toc_ul(t["children"]) if t.get("children") else ""
        items.append(f'<li><a href="#{t["id"]}">{t["name"]}</a>{nested}</li>')
    return "<ul>" + "".join(items) + "</ul>"


def count_headings(tokens):
    return sum((1 if t["level"] > 1 else 0) + count_headings(t.get("children", [])) for t in tokens)


def convert(md_text, image_root):
    """Markdown -> HTML fragment, with .md links rewritten to .html, image paths fixed,
    and an auto-generated table of contents inserted after the title on longer pages."""
    md_text = md_text.replace("/docs/images/", f"{image_root}images/")
    # obtaining-credentials.md / setup.md link into brokers/*.md as "brokers/foo.md"; brokers/*.md
    # link to siblings as "foo.md" and back up via "obtaining-credentials.md" etc. Both patterns
    # just need the .md -> .html swap; relative directory structure already matches the output tree.
    md_text = re.sub(r"\]\(([\w./#-]+)\.md(#[\w-]*)?\)", r"](\1.html\2)", md_text)

    converter = md.Markdown(extensions=MD_EXTENSIONS)
    html = converter.convert(md_text)

    # toc_tokens' root is normally [{level:1 (the page's own H1), children: [h2, h2, ...]}] --
    # drop that h1 wrapper itself, a TOC linking a page to its own title is pointless.
    toc_tokens = converter.toc_tokens
    headings = toc_tokens[0]["children"] if len(toc_tokens) == 1 and toc_tokens[0]["level"] == 1 else toc_tokens
    if count_headings(headings) >= TOC_MIN_HEADINGS:
        toc_html = f'<nav class="doc-toc"><span class="doc-toc-label">On this page</span>{render_toc_ul(headings)}</nav>'
        html = re.sub(r"</h1>", lambda m: m.group(0) + toc_html, html, count=1)
    return html


def _nav_root(depth):
    """Path prefix from a page at this depth back to docs/ root -- same formula
    as image_root, reused here because sidebar/prev-next hrefs are also
    docs/-root-relative."""
    return "../" * (depth - 1)


def group_pages():
    """PAGES grouped in their declared order: {group: [(out_rel, title), ...]}."""
    groups = {}
    for _src_rel, out_rel, title, group in PAGES:
        groups.setdefault(group, []).append((out_rel, title))
    return groups


def render_nav_block(groups, current_out_rel, depth, search_index_url):
    root = _nav_root(depth)
    parts = [f'<div class="docs-nav-block" data-search-index="{search_index_url}">',
             '<input type="search" class="doc-search-input" placeholder="Search docs…" aria-label="Search docs">',
             '<p class="doc-search-empty" hidden>No docs match.</p>']
    for group, pages in groups.items():
        parts.append(f'<div class="docs-nav-group"><span class="docs-nav-label">{group}</span>')
        for out_rel, title in pages:
            cls = "doc-link active" if out_rel == current_out_rel else "doc-link"
            parts.append(f'<a href="{root}{out_rel}" class="{cls}" data-url="{out_rel}">{title}</a>')
        parts.append('</div>')
    parts.append('</div>')
    return "".join(parts)


def render_sidebar(groups, current_out_rel, depth):
    root = _nav_root(depth)
    search_index_url = f"{root}search-index.json"
    nav_block = render_nav_block(groups, current_out_rel, depth, search_index_url)
    desktop = f'<nav class="docs-sidebar" aria-label="Docs navigation">{nav_block}</nav>'
    mobile_block = render_nav_block(groups, current_out_rel, depth, search_index_url)
    mobile = f'<details class="docs-sidebar-mobile"><summary>Browse docs</summary>{mobile_block}</details>'
    return desktop + mobile


def render_prev_next(page_idx, depth):
    root = _nav_root(depth)
    prev_page = PAGES[page_idx - 1] if page_idx > 0 else None
    next_page = PAGES[page_idx + 1] if page_idx < len(PAGES) - 1 else None
    if not prev_page and not next_page:
        return ""
    prev_html = (f'<a class="doc-prev-next-link prev" href="{root}{prev_page[1]}">← <span>{prev_page[2]}</span></a>'
                 if prev_page else '<span></span>')
    next_html = (f'<a class="doc-prev-next-link next" href="{root}{next_page[1]}"><span>{next_page[2]}</span> →</a>'
                 if next_page else '')
    return f'<div class="doc-prev-next">{prev_html}{next_html}</div>'


def render_page(title, body_html, root, out_rel, version, updated, sidebar_html="", prev_next_html=""):
    style, favicons, header, footer = CHROME
    header = rewrite_chrome_links(header, root)
    footer = rewrite_chrome_links(footer, root)
    if sidebar_html:
        footer = footer.replace("</html>", DOC_JS + "\n</html>")
    crumb = title if out_rel == "index.html" else f'<a href="{root}docs/index.html">Docs</a> / {title}'
    meta = f'<p class="doc-meta">Applies to ThetaPrime v{version} · Page last updated {updated}</p>'
    doc_page = f"""<div class="doc-page">
<div class="doc-crumb">{crumb}</div>
<div class="doc-body">
{body_html}
</div>
{prev_next_html}
{meta}
</div>"""
    main_inner = f'<div class="docs-layout">{sidebar_html}{doc_page}</div>' if sidebar_html else doc_page
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — ThetaPrime Docs</title>
<meta name="description" content="{title} — ThetaPrime documentation.">
<link rel="canonical" href="https://thetaprime.in/docs/{'' if out_rel == 'index.html' else out_rel}">
{favicons}
<style>{style}
{DOC_CSS}
</style>
</head>
<body>
<div class="bg-grid"></div>
<div class="bg-field"></div>
{header}
<main class="wrap">
{main_inner}
</main>
{footer}
"""


def build():
    if len(sys.argv) != 4:
        print("usage: build_docs.py <extracted-docs-src-dir> <app-repo-dir> <version>")
        sys.exit(1)
    src = Path(sys.argv[1])
    app_repo_dir = Path(sys.argv[2])
    version = sys.argv[3]
    global CHROME
    CHROME = load_chrome()

    (DOCS_OUT / "brokers").mkdir(parents=True, exist_ok=True)
    (DOCS_OUT / "images").mkdir(parents=True, exist_ok=True)

    for img in IMAGES:
        (DOCS_OUT / img).write_bytes((src / img).read_bytes())

    groups = group_pages()  # also feeds the sidebar on every detail page below

    generated = []
    cross_anchors = []  # (src_rel, out_rel_of_page, href, anchor) for post-build verification
    same_page_anchors = []  # (src_rel, out_rel, anchor)
    search_entries = []
    for page_idx, (src_rel, out_rel, title, group) in enumerate(PAGES):
        depth = out_rel.count("/") + 1  # docs/foo.html = depth 1, docs/brokers/foo.html = depth 2
        chrome_root = "../" * depth  # site root, for header/footer link rewriting
        image_root = "../" * (depth - 1)  # docs/images/, sibling of docs/foo.html
        md_text = (src / src_rel).read_text(encoding="utf-8")
        body_html = convert(md_text, image_root)
        for m in re.finditer(r'href="([^"]*)"', body_html):
            href = m.group(1)
            if href.startswith("#"):
                same_page_anchors.append((src_rel, out_rel, href[1:]))
            elif ".html#" in href:
                target, anchor = href.split("#", 1)
                cross_anchors.append((src_rel, out_rel, target, anchor))
        sidebar_html = render_sidebar(groups, out_rel, depth)
        prev_next_html = render_prev_next(page_idx, depth)
        page = render_page(title, body_html, chrome_root, out_rel, version,
                            last_updated(app_repo_dir, src_rel), sidebar_html, prev_next_html)
        out_path = DOCS_OUT / out_rel
        out_path.write_text(page, encoding="utf-8")
        generated.append((out_rel, title, group))
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body_html)).strip().lower()
        search_entries.append({"title": title, "url": out_rel, "group": group, "text": text})
        print(f"wrote docs/{out_rel}")

    (DOCS_OUT / "search-index.json").write_text(json.dumps(search_entries), encoding="utf-8")
    print("wrote docs/search-index.json")

    # Hub page
    hub_body = ["<h1>ThetaPrime Docs</h1>",
                '<p style="color:var(--text-muted);margin-bottom:2rem;max-width:42rem;">Guides for installing ThetaPrime, connecting a broker, building strategies in the Composer, and running it day to day.</p>']
    for group in ["Getting Started", "Brokers", "Building Strategies", "Operations", "Security & Licensing"]:
        if group not in groups:
            continue
        hub_body.append(f'<div class="doc-hub-group"><h2>{group}</h2><div class="doc-hub-list">')
        for out_rel, title in groups[group]:
            hub_body.append(f'<a href="{out_rel}">{title}</a>')
        hub_body.append("</div></div>")
    hub_html = render_page("Docs", "\n".join(hub_body), "../", "index.html", version, date.today().isoformat())
    (DOCS_OUT / "index.html").write_text(hub_html, encoding="utf-8")
    print("wrote docs/index.html")

    # Verify every anchor link (cross-doc and same-page) resolves to a real id.
    print("\nVerifying anchors...")
    ok, bad = 0, 0
    out_by_rel = {out_rel: out_rel for out_rel, _, _ in generated}
    out_by_rel["index.html"] = "index.html"

    def page_html(out_rel):
        return (DOCS_OUT / out_rel).read_text(encoding="utf-8")

    for src_rel, page_out_rel, href, anchor in cross_anchors:
        page_dir = Path(page_out_rel).parent
        target_rel = str((page_dir / href).as_posix()) if str(page_dir) != "." else href
        target = DOCS_OUT / target_rel
        if not target.exists():
            print(f"  MISSING FILE: {src_rel} ({page_out_rel}) -> {href}#{anchor}")
            bad += 1
            continue
        if f'id="{anchor}"' in target.read_text(encoding="utf-8"):
            ok += 1
        else:
            print(f"  BROKEN CROSS-DOC ANCHOR: {src_rel} ({page_out_rel}) -> {href}#{anchor}")
            bad += 1

    for src_rel, page_out_rel, anchor in same_page_anchors:
        if f'id="{anchor}"' in page_html(page_out_rel):
            ok += 1
        else:
            print(f"  BROKEN SAME-PAGE ANCHOR: {src_rel} ({page_out_rel}) -> #{anchor}")
            bad += 1

    print(f"{ok} anchors OK, {bad} broken")
    if bad:
        sys.exit(1)


if __name__ == "__main__":
    build()
