"""Check the real timing record, reconciliation and corrupted-source failures."""

from dataclasses import replace
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from relay_race_analysis.analysis import compare
from relay_race_analysis.data import load_race, parse_laps
from relay_race_analysis.report import figures

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def race():
    return load_race(ROOT / "race.toml")


@pytest.fixture
def laps(race):
    return [
        lap
        for team in race.teams
        for lap in parse_laps((ROOT / "data/raw" / f"{team.id}.html").read_text(), team)
    ]


def test_real_splits_include_runners_and_ignore_empty_lap_30(race, laps):
    assert len(laps) == 58
    assert [lap.number for lap in laps[:29]] == list(range(1, 30))
    assert laps[0].runner == "Omar Mansour"
    assert laps[1].runner == "Vlad Matei"
    assert laps[28].elapsed_seconds == 14691
    assert laps[-1].elapsed_seconds == 14764


def test_gain_reconciles_and_pivotal_lap_uses_cumulative_precision(race, laps):
    report = compare(race, laps)
    assert report["margin"] == 73 == sum(row["gain"] for row in report["laps"])
    assert report["laps"][6]["lead"] == 45
    assert report["laps"][7]["gain"] == -40
    assert report["laps"][7]["lead"] == 5
    assert report["peak"]["number"] == 23
    assert report["peak"]["lead"] == 97
    assert report["ahead_every_split"]
    assert (report["gains"], report["losses"], report["ties"]) == (21, 8, 0)


def test_preserves_reported_times_instead_of_silently_overwriting(laps):
    second = laps[1]
    assert second.duration_seconds == 490
    assert second.reported_seconds == 489
    assert sum(lap.duration_seconds for lap in laps[:29]) == laps[28].elapsed_seconds


def test_cutoff_and_unequal_runner_rotations(race, laps):
    report = compare(race, laps)
    assert [team["at_cutoff"] for team in report["teams"]] == [28, 28]
    assert all(team["last_lap_start"] < 14400 < team["finish_seconds"] for team in report["teams"])
    assert [runner["all"]["count"] for runner in report["runners"]] == [8, 7, 7, 7, 9, 8, 6, 6]
    omar = report["runners"][0]
    assert omar["regular"]["count"] == 7
    assert omar["regular"]["best"] == 487
    chart = figures(race, report)["runners-willbeing"]
    assert chart["layout"]["xaxis"]["range"][1] > 9


def test_missing_lap_is_rejected(race):
    html = (ROOT / "data/raw/tracklife.html").read_text()
    soup = BeautifulSoup(html, "html.parser")
    soup.select(".rtv3-splits-table tbody tr")[8].decompose()
    with pytest.raises(ValueError, match="Missing or duplicated lap"):
        parse_laps(str(soup), race.teams[0])


def test_clock_or_leg_inconsistency_is_rejected(race):
    html = (ROOT / "data/raw/tracklife.html").read_text()
    # A 9-second discrepancy is outside the provider's observed 1-second rounding.
    broken = html.replace("00:08:09 <span", "00:08:00 <span", 1)
    with pytest.raises(ValueError, match="disagree by >1s"):
        parse_laps(broken, race.teams[0])


def test_wrong_page_is_rejected(race):
    html = (ROOT / "data/raw/willbeing.html").read_text()
    with pytest.raises(ValueError, match="does not identify"):
        parse_laps(html, race.teams[0])


def test_different_distances_are_not_presented_as_a_finish_time_win(race, laps):
    with pytest.raises(ValueError, match="different laps"):
        compare(race, laps[:-1])


def test_sign_convention_reverses_when_team_order_reverses(race, laps):
    reversed_race = replace(race, teams=tuple(reversed(race.teams)))
    report = compare(reversed_race, laps)
    assert report["margin"] == -73
    assert report["laps"][7]["gain"] == 40
    assert not report["ahead_every_split"]
