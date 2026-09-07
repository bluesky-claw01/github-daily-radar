# GitHub Daily Radar

A public, automatically refreshed board of GitHub repositories.

- Daily Radar (Rising / AI Agent / Developer Tools)
- GitHub Stars Top 200

## Automation

- **Daily Pages rebuild** — GitHub Actions cron `0 2 * * *` UTC (10:00 Asia/Shanghai), plus `workflow_dispatch`. Writes static HTML to GitHub Pages. Does **not** commit daily data into git.
- **Weekly snapshot** — GitHub Actions cron `0 3 * * 0` UTC (Sunday 11:00 Asia/Shanghai), plus `workflow_dispatch`. Saves structured JSON under `data/weekly/YYYY-MM-DD.json` (Sunday date, UTC) and commits only when real radar rows exist.

## Manual refresh

Actions → Daily Radar → Run workflow  
Actions → Weekly Radar Snapshot → Run workflow
