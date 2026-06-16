# ESPN Fantasy Season Recap Email

This small project pulls ESPN Fantasy Football data for league `2999`, normalizes the 2025 season, and renders a one-time dramatic recap email for previewing and tweaking.

## Run

```powershell
python scripts\scrape_espn.py
python scripts\render_recap.py
```

If ESPN starts returning an auth-style error, set cookies before rerunning:

```powershell
$env:ESPN_S2="your espn_s2 cookie"
$env:SWID="{your-swid-cookie}"
python scripts\scrape_espn.py
```

## Outputs

- `data/last_season.json`: normalized data for the 2025 recap.
- `email/templates/recap_template.html`: inline-CSS email template.
- `email/output/season_recap_2025.html`: rendered email preview.
- `assets/*-placeholder.svg`: replaceable image placeholders for banner, bracket, and meme.
