#!/usr/bin/env python3
"""Fetch and normalize ESPN fantasy football league data for a recap email."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_LEAGUE_ID = 2999
DEFAULT_SEASON = 2025
VIEWS = (
    "mTeam",
    "mMatchup",
    "mSettings",
    "mRoster",
    "mDraftDetail",
    "mScoreboard",
    "mStandings",
)
POSITION_NAMES = {
    1: "QB",
    2: "RB",
    3: "WR",
    4: "TE",
    5: "K",
    16: "D/ST",
}
PLAYER_OVERRIDES = {
    4595348: {"name": "Malik Nabers", "position": "WR"},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pull ESPN fantasy league data and write data/last_season.json."
    )
    parser.add_argument("--league-id", type=int, default=DEFAULT_LEAGUE_ID)
    parser.add_argument("--season", type=int, default=DEFAULT_SEASON)
    parser.add_argument("--out", default="data/last_season.json")
    parser.add_argument("--raw-out", default="work/espn_2025_raw.json")
    parser.add_argument(
        "--from-cache",
        action="store_true",
        help="Normalize an existing raw JSON file instead of fetching ESPN.",
    )
    return parser.parse_args()


def build_url(league_id: int, season: int) -> str:
    query = urllib.parse.urlencode([("view", view) for view in VIEWS])
    return (
        f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/"
        f"seasons/{season}/segments/0/leagues/{league_id}?{query}"
    )


def fetch_json(url: str) -> dict:
    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 fantasy-recap-script/1.0",
    }
    cookie_parts = []
    espn_s2 = os.environ.get("ESPN_S2")
    swid = os.environ.get("SWID")
    if espn_s2:
        cookie_parts.append(f"espn_s2={espn_s2}")
    if swid:
        cookie_parts.append(f"SWID={swid}")
    if cookie_parts:
        headers["Cookie"] = "; ".join(cookie_parts)

    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403, 404} and not cookie_parts:
            raise SystemExit(
                "ESPN returned an auth-style error. Log into ESPN in a browser, "
                "copy the espn_s2 and SWID cookies, then rerun with ESPN_S2 and "
                "SWID environment variables set."
            ) from exc
        raise


def money(value: float | int | None) -> float:
    return round(float(value or 0), 2)


def record_label(record: dict) -> str:
    return f"{record.get('wins', 0)}-{record.get('losses', 0)}-{record.get('ties', 0)}"


def team_name(team: dict) -> str:
    return team.get("name") or team.get("location") or f"Team {team.get('id')}"


def member_name(member: dict) -> str:
    first = member.get("firstName") or ""
    last = member.get("lastName") or ""
    full = f"{first} {last}".strip()
    return full or member.get("displayName") or member.get("id") or "Unknown owner"


def entry_score(entry: dict | None) -> float:
    if not entry:
        return 0.0
    return money(entry.get("totalPoints") or 0)


def outcome_for(game: dict, side: str) -> str:
    winner = game.get("winner")
    if winner == "UNDECIDED":
        return "UNDECIDED"
    return "WIN" if winner == side else "LOSS"


def matchup_record(game: dict, teams_by_id: dict[int, dict]) -> dict:
    home = game.get("home") or {}
    away = game.get("away") or {}
    home_id = home.get("teamId")
    away_id = away.get("teamId")
    home_team = teams_by_id.get(home_id, {})
    away_team = teams_by_id.get(away_id, {})
    return {
        "id": game.get("id"),
        "week": game.get("matchupPeriodId"),
        "winner": game.get("winner"),
        "home": {
            "team_id": home_id,
            "team": team_name(home_team) if home_id else "BYE",
            "score": entry_score(home),
            "result": outcome_for(game, "HOME") if home_id else "BYE",
        },
        "away": {
            "team_id": away_id,
            "team": team_name(away_team) if away_id else "BYE",
            "score": entry_score(away),
            "result": outcome_for(game, "AWAY") if away_id else "BYE",
        },
        "margin": money(abs(entry_score(home) - entry_score(away))),
    }


def collect_player_map(raw: dict) -> dict[int, dict]:
    players: dict[int, dict] = {}
    for team in raw.get("teams", []):
        for entry in team.get("roster", {}).get("entries", []):
            player = entry.get("playerPoolEntry", {}).get("player", {})
            if player.get("id"):
                players[player["id"]] = {
                    "id": player["id"],
                    "name": player.get("fullName"),
                    "position": POSITION_NAMES.get(player.get("defaultPositionId"), "FLEX"),
                    "pro_team_id": player.get("proTeamId"),
                }
    return players


def normalize(raw: dict, league_id: int, season: int, url: str) -> dict:
    members_by_id = {member.get("id"): member for member in raw.get("members", [])}
    teams_by_id = {team["id"]: team for team in raw.get("teams", [])}
    player_map = collect_player_map(raw)

    teams = []
    for team in raw.get("teams", []):
        overall = team.get("record", {}).get("overall", {})
        owners = [member_name(members_by_id.get(owner_id, {})) for owner_id in team.get("owners", [])]
        teams.append(
            {
                "id": team.get("id"),
                "name": team_name(team),
                "abbrev": team.get("abbrev"),
                "owners": owners,
                "primary_owner": member_name(members_by_id.get(team.get("primaryOwner"), {})),
                "playoff_seed": team.get("playoffSeed"),
                "final_rank": team.get("rankCalculatedFinal") or team.get("rankFinal"),
                "record": {
                    "wins": overall.get("wins", 0),
                    "losses": overall.get("losses", 0),
                    "ties": overall.get("ties", 0),
                    "label": record_label(overall),
                    "points_for": money(overall.get("pointsFor") or team.get("points")),
                    "points_against": money(overall.get("pointsAgainst")),
                },
            }
        )

    teams_by_seed = sorted(teams, key=lambda t: (t["playoff_seed"] or 999, t["name"]))
    teams_by_final = sorted(teams, key=lambda t: (t["final_rank"] or 999, t["name"]))
    teams_by_points = sorted(teams, key=lambda t: t["record"]["points_for"], reverse=True)

    schedule_settings = raw.get("settings", {}).get("scheduleSettings", {})
    regular_season_weeks = int(schedule_settings.get("matchupPeriodCount") or 14)
    playoff_team_count = int(schedule_settings.get("playoffTeamCount") or 0)
    playoff_weeks = sorted(
        {
            game.get("matchupPeriodId")
            for game in raw.get("schedule", [])
            if game.get("matchupPeriodId") and game.get("matchupPeriodId") > regular_season_weeks
        }
    )

    weekly_scores = []
    for week in sorted({g.get("matchupPeriodId") for g in raw.get("schedule", []) if g.get("matchupPeriodId")}):
        games = [matchup_record(g, teams_by_id) for g in raw.get("schedule", []) if g.get("matchupPeriodId") == week]
        weekly_scores.append(
            {
                "week": week,
                "phase": "regular_season" if week <= regular_season_weeks else "playoffs",
                "matchups": sorted(games, key=lambda item: item["id"] or 0),
            }
        )

    playoff_games = [
        matchup_record(g, teams_by_id)
        for g in raw.get("schedule", [])
        if g.get("matchupPeriodId") in playoff_weeks
    ]
    playoff_bracket = []
    for week in playoff_weeks:
        games = [g for g in playoff_games if g["week"] == week]
        playoff_bracket.append(
            {
                "week": week,
                "label": {15: "Wild Card", 16: "Semifinals", 17: "Championship"}.get(week, f"Week {week}"),
                "matchups": sorted(games, key=lambda item: item["id"] or 0),
            }
        )

    champion = teams_by_final[0]
    runner_up = teams_by_final[1] if len(teams_by_final) > 1 else None
    championship_game = None
    if playoff_games and runner_up:
        championship_week = max(playoff_weeks)
        title_team_ids = {champion["id"], runner_up["id"]}
        real_games = [
            game
            for game in playoff_games
            if game["week"] == championship_week and game["home"]["team_id"] and game["away"]["team_id"]
        ]
        championship_game = next(
            (
                game
                for game in real_games
                if {game["home"]["team_id"], game["away"]["team_id"]} == title_team_ids
            ),
            None,
        )
    if championship_game:
        winning_side = "home" if championship_game["winner"] == "HOME" else "away"
        losing_side = "away" if winning_side == "home" else "home"
        champion = next(t for t in teams if t["id"] == championship_game[winning_side]["team_id"])
        runner_up = next(t for t in teams if t["id"] == championship_game[losing_side]["team_id"])

    regular_season_beast = teams_by_seed[0]
    points_king = teams_by_points[0]
    playoff_teams = {team["id"] for team in teams_by_seed[:playoff_team_count]}
    non_playoff_points = [team for team in teams_by_points if team["id"] not in playoff_teams]
    unlucky_team = non_playoff_points[0] if non_playoff_points else teams_by_seed[-1]
    fraud_candidates = [team for team in teams_by_seed[:playoff_team_count] if (team["final_rank"] or 0) > (team["playoff_seed"] or 0)]
    fraud_team = max(
        fraud_candidates or teams_by_seed,
        key=lambda team: (team["final_rank"] or 0) - (team["playoff_seed"] or 0),
    )

    biggest_blowout = max(
        (g for week in weekly_scores for g in week["matchups"] if g["home"]["team_id"] and g["away"]["team_id"]),
        key=lambda g: g["margin"],
    )
    closest_game = min(
        (g for week in weekly_scores for g in week["matchups"] if g["home"]["team_id"] and g["away"]["team_id"]),
        key=lambda g: g["margin"],
    )
    highest_score_game = max(
        (g for week in weekly_scores for g in week["matchups"] if g["home"]["team_id"] and g["away"]["team_id"]),
        key=lambda g: max(g["home"]["score"], g["away"]["score"]),
    )
    highest_side = "home" if highest_score_game["home"]["score"] >= highest_score_game["away"]["score"] else "away"

    draft_picks = []
    for pick in raw.get("draftDetail", {}).get("picks", []):
        player = player_map.get(pick.get("playerId"), PLAYER_OVERRIDES.get(pick.get("playerId"), {}))
        drafting_team = teams_by_id.get(pick.get("teamId"), {})
        draft_picks.append(
            {
                "overall": pick.get("overallPickNumber"),
                "round": pick.get("roundId"),
                "round_pick": pick.get("roundPickNumber"),
                "team_id": pick.get("teamId"),
                "team": team_name(drafting_team),
                "player_id": pick.get("playerId"),
                "player": player.get("name") or f"Player ID {pick.get('playerId')}",
                "position": player.get("position") or POSITION_NAMES.get(pick.get("lineupSlotId"), "FLEX"),
                "keeper": bool(pick.get("keeper")),
            }
        )
    first_round = sorted([p for p in draft_picks if p["round"] == 1], key=lambda p: p["overall"] or 999)

    signature_moments = [
        {
            "title": "The Crown Was Earned Under December Lights",
            "team": champion["name"],
            "detail": f"{champion['name']} finished the job against {runner_up['name']} in Week {championship_game['week']}." if championship_game and runner_up else f"{champion['name']} finished first overall.",
        },
        {
            "title": "Regular Season Thunder",
            "team": regular_season_beast["name"],
            "detail": f"{regular_season_beast['name']} took the No. {regular_season_beast['playoff_seed']} seed at {regular_season_beast['record']['label']} with {regular_season_beast['record']['points_for']} points.",
        },
        {
            "title": "Scoreboard Fireworks",
            "team": highest_score_game[highest_side]["team"],
            "detail": f"{highest_score_game[highest_side]['team']} dropped {highest_score_game[highest_side]['score']} in Week {highest_score_game['week']}.",
        },
        {
            "title": "The Thin White Line",
            "team": closest_game["home"]["team"],
            "detail": f"Week {closest_game['week']} came down to {closest_game['margin']} points: {closest_game['home']['team']} {closest_game['home']['score']}, {closest_game['away']['team']} {closest_game['away']['score']}.",
        },
        {
            "title": "The Resume That Got Left Outside",
            "team": unlucky_team["name"],
            "detail": f"{unlucky_team['name']} scored {unlucky_team['record']['points_for']} but landed as the No. {unlucky_team['playoff_seed']} seed.",
        },
    ]

    return {
        "metadata": {
            "league_id": league_id,
            "season": season,
            "source_url": url,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "note": "Normalized from ESPN Fantasy Football API. Set ESPN_S2 and SWID env vars if the league becomes private.",
        },
        "league": {
            "name": raw.get("settings", {}).get("name"),
            "size": raw.get("settings", {}).get("size"),
            "regular_season_weeks": regular_season_weeks,
            "playoff_team_count": playoff_team_count,
        },
        "champion": champion,
        "runner_up": runner_up,
        "regular_season_beast": regular_season_beast,
        "points_king": points_king,
        "fraud_team": {
            **fraud_team,
            "reason": f"Entered as seed {fraud_team['playoff_seed']} and finished {fraud_team['final_rank']}. The film room will be unkind.",
        },
        "unluckiest_team": unlucky_team,
        "signature_moments": signature_moments,
        "final_standings": teams_by_final,
        "regular_season_standings": teams_by_seed,
        "weekly_scores": weekly_scores,
        "playoff_bracket": playoff_bracket,
        "draft_info": {
            "complete_date": raw.get("draftDetail", {}).get("completeDate"),
            "first_round": first_round,
            "all_picks": sorted(draft_picks, key=lambda p: p["overall"] or 999),
        },
        "superlatives": {
            "biggest_blowout": biggest_blowout,
            "closest_game": closest_game,
            "highest_single_team_score": {
                "week": highest_score_game["week"],
                "team": highest_score_game[highest_side]["team"],
                "score": highest_score_game[highest_side]["score"],
                "opponent": highest_score_game["away" if highest_side == "home" else "home"]["team"],
            },
        },
    }


def main() -> int:
    args = parse_args()
    url = build_url(args.league_id, args.season)
    raw_path = Path(args.raw_out)
    out_path = Path(args.out)

    if args.from_cache:
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
    else:
        raw = fetch_json(url)
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(json.dumps(raw, indent=2, sort_keys=True), encoding="utf-8")

    normalized = normalize(raw, args.league_id, args.season, url)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(normalized, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Wrote {out_path}")
    print(f"Champion: {normalized['champion']['name']}")
    print(f"Runner-up: {normalized['runner_up']['name']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
