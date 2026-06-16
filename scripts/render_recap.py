#!/usr/bin/env python3
"""Render the ESPN recap JSON into the final HTML email."""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render the season recap email.")
    parser.add_argument("--data", default="data/last_season.json")
    parser.add_argument("--template", default="email/templates/recap_template.html")
    parser.add_argument("--out", default="email/output/season_recap_2025.html")
    return parser.parse_args()


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def score_line(matchup: dict) -> str:
    return (
        f"{esc(matchup['home']['team'])} {matchup['home']['score']:.2f} "
        f"vs. {esc(matchup['away']['team'])} {matchup['away']['score']:.2f}"
    )


def render_rows(rows: list[str]) -> str:
    return "\n".join(rows)


def standing_rows(standings: list[dict]) -> str:
    rows = []
    for team in standings:
        rows.append(
            "<tr>"
            f"<td style=\"padding:10px 8px;border-bottom:1px solid #27313f;color:#f8f2df;font-weight:bold;\">{team['final_rank']}</td>"
            f"<td style=\"padding:10px 8px;border-bottom:1px solid #27313f;color:#f8f2df;\">{esc(team['name'])}</td>"
            f"<td style=\"padding:10px 8px;border-bottom:1px solid #27313f;color:#d8c08a;\">{esc(team['record']['label'])}</td>"
            f"<td style=\"padding:10px 8px;border-bottom:1px solid #27313f;color:#d8c08a;\">{team['record']['points_for']:.2f}</td>"
            "</tr>"
        )
    return render_rows(rows)


def regular_rows(standings: list[dict]) -> str:
    rows = []
    for team in standings:
        rows.append(
            "<tr>"
            f"<td style=\"padding:9px 8px;border-bottom:1px solid #27313f;color:#f8f2df;font-weight:bold;\">{team['playoff_seed']}</td>"
            f"<td style=\"padding:9px 8px;border-bottom:1px solid #27313f;color:#f8f2df;\">{esc(team['name'])}</td>"
            f"<td style=\"padding:9px 8px;border-bottom:1px solid #27313f;color:#d8c08a;\">{esc(team['record']['label'])}</td>"
            f"<td style=\"padding:9px 8px;border-bottom:1px solid #27313f;color:#d8c08a;\">{team['record']['points_for']:.2f}</td>"
            "</tr>"
        )
    return render_rows(rows)


def moment_blocks(moments: list[dict]) -> str:
    blocks = []
    for moment in moments:
        blocks.append(
            "<tr><td style=\"padding:0 0 14px 0;\">"
            "<table role=\"presentation\" width=\"100%\" cellspacing=\"0\" cellpadding=\"0\" style=\"border:1px solid #364252;background-color:#121821;\">"
            "<tr><td style=\"padding:16px;\">"
            f"<div style=\"font-family:Georgia,serif;font-size:20px;line-height:26px;color:#f4d27a;font-weight:bold;\">{esc(moment['title'])}</div>"
            f"<div style=\"font-family:Arial,sans-serif;font-size:12px;line-height:18px;color:#9fb0c5;text-transform:uppercase;letter-spacing:1px;padding-top:3px;\">{esc(moment['team'])}</div>"
            f"<div style=\"font-family:Arial,sans-serif;font-size:15px;line-height:23px;color:#e7edf6;padding-top:9px;\">{esc(moment['detail'])}</div>"
            "</td></tr></table></td></tr>"
        )
    return render_rows(blocks)


def bracket_blocks(bracket: list[dict]) -> str:
    rows = []
    for round_info in bracket:
        matchups = []
        for matchup in round_info["matchups"]:
            if matchup["away"]["team"] == "BYE":
                detail = f"{esc(matchup['home']['team'])} earned the bye."
            else:
                detail = score_line(matchup)
            matchups.append(
                f"<div style=\"font-family:Arial,sans-serif;font-size:14px;line-height:22px;color:#e7edf6;padding:6px 0;border-bottom:1px solid #293443;\">{detail}</div>"
            )
        rows.append(
            "<tr><td style=\"padding:0 0 16px 0;\">"
            f"<div style=\"font-family:Georgia,serif;font-size:22px;line-height:28px;color:#f4d27a;font-weight:bold;\">Week {round_info['week']}: {esc(round_info['label'])}</div>"
            f"{''.join(matchups)}"
            "</td></tr>"
        )
    return render_rows(rows)


def weekly_blocks(weeks: list[dict]) -> str:
    rows = []
    for week in weeks:
        headline = "Regular Season" if week["phase"] == "regular_season" else "Playoffs"
        matchups = []
        for matchup in week["matchups"]:
            if matchup["away"]["team"] == "BYE":
                matchups.append(f"{esc(matchup['home']['team'])} on bye")
            else:
                matchups.append(score_line(matchup))
        rows.append(
            "<tr><td style=\"padding:10px 0;border-bottom:1px solid #27313f;\">"
            f"<div style=\"font-family:Arial,sans-serif;font-size:12px;color:#9fb0c5;text-transform:uppercase;letter-spacing:1px;\">Week {week['week']} - {headline}</div>"
            f"<div style=\"font-family:Arial,sans-serif;font-size:14px;line-height:21px;color:#e7edf6;padding-top:4px;\">{'<br>'.join(matchups)}</div>"
            "</td></tr>"
        )
    return render_rows(rows)


def draft_rows(picks: list[dict]) -> str:
    rows = []
    for pick in picks:
        rows.append(
            "<tr>"
            f"<td style=\"padding:9px 8px;border-bottom:1px solid #27313f;color:#f8f2df;font-weight:bold;\">{pick['overall']}</td>"
            f"<td style=\"padding:9px 8px;border-bottom:1px solid #27313f;color:#f8f2df;\">{esc(pick['player'])}</td>"
            f"<td style=\"padding:9px 8px;border-bottom:1px solid #27313f;color:#d8c08a;\">{esc(pick['position'])}</td>"
            f"<td style=\"padding:9px 8px;border-bottom:1px solid #27313f;color:#d8c08a;\">{esc(pick['team'])}</td>"
            "</tr>"
        )
    return render_rows(rows)


def safe_filename(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def main() -> int:
    args = parse_args()
    data = json.loads(Path(args.data).read_text(encoding="utf-8"))
    template = Path(args.template).read_text(encoding="utf-8")
    champion = data["champion"]
    runner_up = data["runner_up"]
    beast = data["regular_season_beast"]
    fraud = data["fraud_team"]
    superlatives = data["superlatives"]

    replacements = {
        "league_name": data["league"]["name"],
        "season": data["metadata"]["season"],
        "champion_name": champion["name"],
        "champion_record": champion["record"]["label"],
        "champion_points": f"{champion['record']['points_for']:.2f}",
        "runner_up_name": runner_up["name"],
        "regular_season_beast": beast["name"],
        "regular_season_beast_detail": f"No. {beast['playoff_seed']} seed, {beast['record']['label']}, {beast['record']['points_for']:.2f} points.",
        "fraud_team": fraud["name"],
        "fraud_detail": fraud["reason"],
        "points_king": data["points_king"]["name"],
        "points_king_points": f"{data['points_king']['record']['points_for']:.2f}",
        "unluckiest_team": data["unluckiest_team"]["name"],
        "unluckiest_detail": f"{data['unluckiest_team']['record']['points_for']:.2f} points and the No. {data['unluckiest_team']['playoff_seed']} seed.",
        "biggest_blowout": score_line(superlatives["biggest_blowout"]),
        "closest_game": score_line(superlatives["closest_game"]),
        "highest_score": f"{superlatives['highest_single_team_score']['team']} scored {superlatives['highest_single_team_score']['score']:.2f} in Week {superlatives['highest_single_team_score']['week']}.",
        "final_standings_rows": standing_rows(data["final_standings"]),
        "regular_standings_rows": regular_rows(data["regular_season_standings"]),
        "signature_moments": moment_blocks(data["signature_moments"]),
        "playoff_bracket": bracket_blocks(data["playoff_bracket"]),
        "weekly_scores": weekly_blocks(data["weekly_scores"]),
        "draft_rows": draft_rows(data["draft_info"]["first_round"]),
        "banner_src": "../../assets/banner-placeholder.svg",
        "bracket_src": "../../assets/bracket-placeholder.svg",
        "meme_src": "../../assets/meme-placeholder.svg",
        "preheader": f"{data['league']['name']} 2025 recap: {champion['name']} takes the crown, 2026 waits in the tunnel.",
    }

    rendered = template
    for key, value in replacements.items():
        rendered = rendered.replace("{{" + key + "}}", str(value))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8")
    print(f"Wrote {out_path}")
    print(f"Preview slug: {safe_filename(data['league']['name'])}-{data['metadata']['season']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
