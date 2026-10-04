"""Head-to-head timing with an explicit same-distance comparison and sign convention."""

from __future__ import annotations

from dataclasses import asdict
from statistics import mean, pstdev

from .data import Lap, Race


def format_time(value: float, hours: bool = False) -> str:
    total = round(value)
    if hours or total >= 3600:
        return f"{total // 3600}:{total % 3600 // 60:02d}:{total % 60:02d}"
    return f"{total // 60}:{total % 60:02d}"


def compare(race: Race, laps: list[Lap]) -> dict:
    team_laps = {team.id: [lap for lap in laps if lap.team_id == team.id] for team in race.teams}
    own, rival = (team_laps[team.id] for team in race.teams)
    if not own or not rival:
        raise ValueError("Both teams must have completed laps.")
    if len(own) != len(rival):
        raise ValueError(
            "This report compares equal lap counts; the teams finished different laps."
        )
    comparisons = []
    for left, right in zip(own, rival, strict=True):
        comparisons.append(
            {
                "number": left.number,
                "gain": right.duration_seconds - left.duration_seconds,
                "lead": right.elapsed_seconds - left.elapsed_seconds,
                "own": asdict(left),
                "rival": asdict(right),
            }
        )
    final = comparisons[-1]["lead"]
    if sum(lap["gain"] for lap in comparisons) != final:
        raise ValueError("Per-lap gains do not reconcile to the finish margin.")
    runners = []
    for team in race.teams:
        names = list(dict.fromkeys(lap.runner for lap in team_laps[team.id]))
        for name in names:
            outings = [lap for lap in team_laps[team.id] if lap.runner == name]
            regular = [lap for lap in outings if lap.number != 1]
            # A separate opening-lap option allows a like-for-like repeat-effort comparison.
            for subset_name, subset in (("all", outings), ("regular", regular)):
                values = [lap.duration_seconds for lap in subset]
                stats = {
                    "count": len(values),
                    "average": mean(values) if values else None,
                    "best": min(values) if values else None,
                    "sd": pstdev(values) if values else None,
                    "change": values[-1] - values[0] if len(values) > 1 else None,
                }
                if subset_name == "all":
                    item = {
                        "team_id": team.id,
                        "name": name,
                        "outings": [asdict(x) for x in outings],
                    }
                    item["all"] = stats
                else:
                    item["regular"] = stats
            runners.append(item)
    # These phases describe this 29-lap race; shorter/other races are split into thirds.
    boundaries = (
        (7, 23, len(own))
        if len(own) == 29
        else (max(1, len(own) // 3), max(2, len(own) * 2 // 3), len(own))
    )
    phases = []
    start = 1
    for end in sorted(set(boundaries)):
        rows = comparisons[start - 1 : end]
        if rows:
            phases.append({"start": start, "end": end, "gain": sum(x["gain"] for x in rows)})
        start = end + 1
    return {
        "laps": comparisons,
        "runners": runners,
        "teams": [
            asdict(team)
            | {
                "finish_seconds": team_laps[team.id][-1].elapsed_seconds,
                "finish": format_time(team_laps[team.id][-1].elapsed_seconds, hours=True),
                "average": mean(lap.duration_seconds for lap in team_laps[team.id]),
                "laps": len(team_laps[team.id]),
                "at_cutoff": sum(
                    lap.elapsed_seconds <= race.cutoff_seconds for lap in team_laps[team.id]
                ),
                "last_lap_start": team_laps[team.id][-2].elapsed_seconds if len(own) > 1 else 0,
            }
            for team in race.teams
        ],
        "count": len(own),
        "distance": len(own) * race.lap_distance_km,
        "margin": final,
        "peak": max(comparisons, key=lambda lap: lap["lead"]),
        "closest": min(comparisons, key=lambda lap: abs(lap["lead"])),
        "biggest_gain": max(comparisons, key=lambda lap: lap["gain"]),
        "biggest_loss": min(comparisons, key=lambda lap: lap["gain"]),
        "gains": sum(lap["gain"] > 0 for lap in comparisons),
        "losses": sum(lap["gain"] < 0 for lap in comparisons),
        "ties": sum(lap["gain"] == 0 for lap in comparisons),
        "ahead_every_split": all(lap["lead"] > 0 for lap in comparisons),
        "phases": phases,
        "rounding_rows": sum(
            lap.reported_seconds is not None and lap.reported_seconds != lap.duration_seconds
            for lap in laps
        ),
    }
