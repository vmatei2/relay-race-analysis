"""Fetch, preserve and validate the timing provider's completed split rows."""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx
from bs4 import BeautifulSoup


@dataclass(frozen=True)
class Team:
    id: str
    name: str
    short_name: str
    bib: int
    color: str
    url: str


@dataclass(frozen=True)
class Race:
    title: str
    date: str
    lap_distance_km: float
    cutoff_seconds: int
    opening_lap_same_distance: bool
    results_url: str
    teams: tuple[Team, ...]


@dataclass(frozen=True)
class Lap:
    team_id: str
    number: int
    runner: str
    runner_slot: str
    elapsed_seconds: int
    duration_seconds: int
    reported_seconds: int | None
    clock_time: str | None


def load_race(config: Path) -> Race:
    with config.open("rb") as source:
        values = tomllib.load(source)
    values["teams"] = tuple(Team(**team) for team in values["teams"])
    race = Race(**values)
    if len(race.teams) != 2 or len({team.id for team in race.teams}) != 2:
        raise ValueError("Choose exactly two teams with unique IDs for head-to-head analysis.")
    if race.lap_distance_km <= 0 or race.cutoff_seconds <= 0:
        raise ValueError("Lap distance and race cutoff must be positive.")
    return race


def seconds(value: str) -> int:
    hours, minutes, secs = map(int, value.split(":"))
    if hours < 0 or not 0 <= minutes < 60 or not 0 <= secs < 60:
        raise ValueError(f"Invalid timing value: {value}")
    return hours * 3600 + minutes * 60 + secs


def parse_laps(html: str, team: Team) -> list[Lap]:
    """Use cumulative differences, retaining the provider's separately rounded leg times."""
    soup = BeautifulSoup(html, "html.parser")
    title = soup.select_one(".rtv3-hero")
    if title is None or team.name.casefold() not in title.get_text(" ", strip=True).casefold():
        raise ValueError(f"The downloaded page does not identify {team.name}.")
    result: list[Lap] = []
    previous = 0
    for row in soup.select(".rtv3-splits-table tbody tr"):
        cells = row.find_all("td", recursive=False)
        if len(cells) < 3:
            raise ValueError(f"Malformed split row for {team.name}.")
        label = cells[0].select_one(".rtv3-split-nm")
        match = re.fullmatch(r"Lap\s+(\d+)", label.get_text(strip=True)) if label else None
        if not match:
            raise ValueError(f"Unrecognised split label for {team.name}.")
        time_div = cells[1].find("div", recursive=False)
        elapsed_text = time_div.get_text(strip=True) if time_div else ""
        if not elapsed_text:
            # The provider appends an empty row for the next, uncompleted lap.
            if any(cell.get_text(strip=True) for cell in cells[1:]):
                raise ValueError("An incomplete lap unexpectedly contains timing data.")
            continue
        number = int(match[1])
        if number != len(result) + 1:
            raise ValueError(f"Missing or duplicated lap number {number} for {team.name}.")
        elapsed = seconds(elapsed_text)
        if elapsed <= previous:
            raise ValueError(f"Non-increasing cumulative time at lap {number}.")
        runner_div = cells[0].select_one(".rtv3-sub2")
        runner_match = re.fullmatch(
            r"([A-Z])\s*-\s*(.+)", runner_div.get_text(strip=True) if runner_div else ""
        )
        if not runner_match:
            raise ValueError(f"Missing runner attribution for lap {number}.")
        reported_match = re.search(r"\d{2}:\d{2}:\d{2}", cells[2].get_text())
        reported = seconds(reported_match[0]) if reported_match else None
        duration = elapsed - previous
        if reported is not None and abs(duration - reported) > 1:
            raise ValueError(f"Cumulative and leg timing disagree by >1s at lap {number}.")
        if number > 1 and reported is None:
            raise ValueError(f"Missing leg time at lap {number}.")
        clock_match = re.search(r"\d{2}:\d{2}:\d{2}", cells[1].get_text()[len(elapsed_text) :])
        result.append(
            Lap(
                team.id,
                number,
                runner_match[2].title(),
                runner_match[1],
                elapsed,
                duration,
                reported,
                clock_match[0] if clock_match else None,
            )
        )
        previous = elapsed
    if not result:
        raise ValueError(f"No completed laps found for {team.name}.")
    count_item = next(
        (
            item
            for item in soup.select(".rtv3-info-item")
            if item.select_one(".rtv3-info-label")
            and item.select_one(".rtv3-info-label").get_text(strip=True) == "No Laps"
        ),
        None,
    )
    if count_item is None:
        raise ValueError(f"Missing official lap count for {team.name}.")
    count = int(count_item.select_one(".rtv3-info-value").get_text(strip=True))
    if count != len(result):
        raise ValueError(f"Expected {count} laps for {team.name}, found {len(result)}.")
    return result


def get_laps(race: Race, data_dir: Path, refresh: bool = False) -> list[Lap]:
    raw_dir = data_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    manifest_file = raw_dir / "manifest.json"
    manifest = json.loads(manifest_file.read_text()) if manifest_file.exists() else {}
    laps = []
    for team in race.teams:
        raw_file = raw_dir / f"{team.id}.html"
        if refresh or not raw_file.exists() or manifest.get(team.id, {}).get("url") != team.url:
            with httpx.Client(timeout=30, follow_redirects=True) as client:
                response = client.get(team.url, headers={"User-Agent": "RelayRaceAnalysis/0.1"})
                response.raise_for_status()
            # Validate before replacing a working cached result.
            parsed = parse_laps(response.text, team)
            raw_file.write_text(response.text, encoding="utf-8")
            manifest[team.id] = {"url": team.url, "fetched_at": datetime.now(UTC).isoformat()}
            manifest_file.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        else:
            parsed = parse_laps(raw_file.read_text(encoding="utf-8"), team)
        laps.extend(parsed)
    (data_dir / "laps.json").write_text(
        json.dumps([asdict(lap) for lap in laps], indent=2) + "\n", encoding="utf-8"
    )
    return laps
