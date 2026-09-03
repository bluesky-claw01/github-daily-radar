#!/usr/bin/env python3
"""Build a static GitHub Daily Radar page from GitHub Search API. No extra deps."""
from __future__ import annotations

import html
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT_DIR = Path(os.environ.get("OUT_DIR", "site"))
API = "https://api.github.com"
CRON_HOUR_UTC = 2
CRON_MINUTE_UTC = 0
PER_SECTION = 10
UA = "aster-01-github-daily-radar"


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def next_cron(now: datetime) -> datetime:
    candidate = now.replace(hour=CRON_HOUR_UTC, minute=CRON_MINUTE_UTC, second=0, microsecond=0)
    if now >= candidate:
        candidate += timedelta(days=1)
    return candidate


def iso_date(d: datetime) -> str:
    return d.date().isoformat()


def token() -> str:
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""


def api_get(path: str, query: dict) -> dict:
    q = urllib.parse.urlencode(query, doseq=True)
    url = f"{API}{path}?{q}"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": UA,
            **({"Authorization": f"Bearer {token()}"} if token() else {}),
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:400]
        raise RuntimeError(f"GitHub API {e.code} on {path}: {body}") from e


def search_repos(q: str, sort: str, per_page: int = 15) -> list[dict]:
    data = api_get(
        "/search/repositories",
        {"q": q, "sort": sort, "order": "desc", "per_page": str(per_page)},
    )
    return data.get("items") or []


def slim(item: dict) -> dict:
    return {
        "name": item.get("full_name") or item.get("name") or "",
        "description": (item.get("description") or "").strip(),
        "language": item.get("language") or "—",
        "stars": int(item.get("stargazers_count") or 0),
        "forks": int(item.get("forks_count") or 0),
        "updated": (item.get("pushed_at") or item.get("updated_at") or "")[:10],
        "url": item.get("html_url") or "",
    }


def pick(items: list[dict], n: int, seen: set[str]) -> list[dict]:
    out: list[dict] = []
    for raw in items:
        row = slim(raw)
        key = row["name"].lower()
        if not key or key in seen or not row["url"].startswith("https://github.com/"):
            continue
        seen.add(key)
        out.append(row)
        if len(out) >= n:
            break
    return out


def collect() -> dict:
    now = now_utc()
    d14 = iso_date(now - timedelta(days=14))
    d30 = iso_date(now - timedelta(days=30))
    seen: set[str] = set()
    specs = [
        (
            "rising",
            "Rising Repositories",
            [f"created:>={d14} stars:>=10 archived:false is:public"],
            "stars",
        ),
        (
            "ai",
            "AI / Agent Radar",
            [
                (
                    "(mcp OR llm OR rag OR \"ai agent\" OR \"coding agent\" OR langchain) "
                    f"stars:>=20 pushed:>={d30} archived:false is:public"
                )
            ],
            "updated",
        ),
        (
            "tools",
            "Developer Tools Radar",
            [
                f"cli language:Python stars:>=30 pushed:>={d30} archived:false is:public",
                f"cli language:TypeScript stars:>=30 pushed:>={d30} archived:false is:public",
            ],
            "updated",
        ),
    ]
    result = {}
    errors = []
    for key, title, queries, sort in specs:
        rows: list[dict] = []
        used_q = " | ".join(queries)
        try:
            for query in queries:
                rows.extend(search_repos(query, sort=sort, per_page=15))
            result[key] = {
                "title": title,
                "query": used_q,
                "repos": pick(rows, PER_SECTION, seen),
            }
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{key}: {exc}")
            result[key] = {"title": title, "query": used_q, "repos": pick(rows, PER_SECTION, seen)}
    return {
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "next_update": next_cron(now).isoformat().replace("+00:00", "Z"),
        "sections": result,
        "errors": errors,
    }


def fmt_num(n: int) -> str:
    return f"{n:,}"


def repo_row(r: dict) -> str:
    desc = html.escape(r["description"] or "No description")
    name = html.escape(r["name"])
    lang = html.escape(r["language"])
    url = html.escape(r["url"], quote=True)
    return (
        "<tr>"
        f"<td class='name'><a href='{url}' rel='noopener noreferrer'>{name}</a></td>"
        f"<td class='desc'>{desc}</td>"
        f"<td>{lang}</td>"
        f"<td class='num'>{fmt_num(r['stars'])}</td>"
        f"<td class='num'>{fmt_num(r['forks'])}</td>"
        f"<td class='date'>{html.escape(r['updated'])}</td>"
        f"<td class='link'><a href='{url}' rel='noopener noreferrer'>GitHub</a></td>"
        "</tr>"
    )


def section_html(block: dict) -> str:
    rows = "".join(repo_row(r) for r in block["repos"]) or (
        "<tr><td colspan='7' class='empty'>No repositories returned for this query.</td></tr>"
    )
    return f"""
    <section>
      <h2>{html.escape(block['title'])}</h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Repository</th>
              <th>Description</th>
              <th>Language</th>
              <th>Stars</th>
              <th>Forks</th>
              <th>Last updated</th>
              <th>Link</th>
            </tr>
          </thead>
          <tbody>
            {rows}
          </tbody>
        </table>
      </div>
    </section>
    """


def render(payload: dict) -> str:
    sections = "".join(section_html(payload["sections"][k]) for k in ("rising", "ai", "tools"))
    err = ""
    if payload["errors"]:
        err = "<p class='warn'>Some queries failed this run. The remaining sections still use live GitHub search data.</p>"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>GitHub Daily Radar · Aster-01</title>
  <meta name="description" content="A daily, automatically refreshed radar of public GitHub repositories.">
  <style>
    :root {{
      --bg:#0b1020; --ink:#e7eefc; --muted:#9aa8c7; --line:rgba(140,170,220,.22);
      --accent:#8ec5ff; --ok:#8dffe1; --panel:rgba(14,20,38,.88);
    }}
    * {{ box-sizing:border-box; }}
    html,body {{ margin:0; min-height:100%; }}
    body {{
      font-family:"Segoe UI","Helvetica Neue",ui-sans-serif,sans-serif;
      color:var(--ink); background:var(--bg); line-height:1.5;
    }}
    .sky {{
      position:fixed; inset:0; z-index:0; pointer-events:none;
      background:
        radial-gradient(1px 1px at 14% 22%, rgba(255,255,255,.65) 50%, transparent 51%),
        radial-gradient(1px 1px at 72% 18%, rgba(255,255,255,.4) 50%, transparent 51%),
        radial-gradient(1px 1px at 88% 70%, rgba(255,255,255,.5) 50%, transparent 51%),
        radial-gradient(900px 500px at 100% -10%, #1a2a55 0%, transparent 55%),
        var(--bg);
    }}
    main {{ position:relative; z-index:1; max-width:1080px; margin:0 auto; padding:3.2rem 1.2rem 3rem; }}
    .kicker {{ font-family:ui-monospace,Menlo,Consolas,monospace; font-size:.78rem; color:var(--accent); letter-spacing:.08em; }}
    h1 {{ font-size:clamp(1.8rem,4vw,2.6rem); font-weight:650; letter-spacing:-.03em; margin:.35rem 0 .6rem; }}
    .lede, .meta {{ color:var(--muted); max-width:46rem; }}
    .meta {{ font-family:ui-monospace,Menlo,Consolas,monospace; font-size:.86rem; }}
    h2 {{
      margin:2.2rem 0 .8rem; padding-top:1rem; border-top:1px solid var(--line);
      font-size:.8rem; letter-spacing:.16em; text-transform:uppercase; color:var(--ok);
    }}
    .table-wrap {{ overflow:auto; border:1px solid var(--line); background:var(--panel); border-radius:10px; }}
    table {{ width:100%; border-collapse:collapse; min-width:720px; font-size:.92rem; }}
    th, td {{ padding:.7rem .75rem; text-align:left; vertical-align:top; border-bottom:1px solid var(--line); }}
    th {{ color:var(--muted); font-weight:600; font-size:.75rem; letter-spacing:.04em; text-transform:uppercase; }}
    a {{ color:var(--accent); text-decoration:none; }}
    a:hover {{ text-decoration:underline; }}
    .name {{ font-family:ui-monospace,Menlo,Consolas,monospace; white-space:nowrap; }}
    .desc {{ color:var(--muted); }}
    .num, .date, .link {{ white-space:nowrap; }}
    .empty, .warn {{ color:var(--muted); }}
    footer {{ margin-top:2.4rem; color:var(--muted); font-size:.86rem; }}
    @media (max-width:640px) {{ main {{ padding-top:2.2rem; }} }}
  </style>
</head>
<body>
  <div class="sky" aria-hidden="true"></div>
  <main>
    <p class="kicker">// github daily radar</p>
    <h1>GitHub Daily Radar</h1>
    <p class="lede">A small public board of recently created and recently active repositories, rebuilt once a day from GitHub’s own search API. No editorial ranking, no extra model in the loop.</p>
    <p class="meta">Last generated (UTC): {html.escape(payload['generated_at'])}<br>
    Next scheduled update (UTC): {html.escape(payload['next_update'])} · 10:00 Asia/Shanghai</p>
    {err}
    {sections}
    <footer>Aster-01 · GitHub Daily Radar · data from GitHub Search API</footer>
  </main>
</body>
</html>
"""


def main() -> None:
    payload = collect()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "index.html").write_text(render(payload), encoding="utf-8")
    (OUT_DIR / "radar.json").write_text(
        json.dumps(
            {
                "generated_at": payload["generated_at"],
                "next_update": payload["next_update"],
                "counts": {k: len(v["repos"]) for k, v in payload["sections"].items()},
                "errors": payload["errors"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "generated_at": payload["generated_at"],
                "next_update": payload["next_update"],
                "counts": {k: len(v["repos"]) for k, v in payload["sections"].items()},
                "errors": payload["errors"],
            }
        )
    )


if __name__ == "__main__":
    main()
