"""Check the real timing record, reconciliation and corrupted-source failures."""

from dataclasses import replace
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from relay_race_analysis.analysis import compare
from relay_race_analysis.data import load_race, parse_laps

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


def test_changed_assets_get_new_urls_so_browsers_cannot_reuse_old_defaults(
    race, laps, tmp_path, monkeypatch
):
    import shutil

    import relay_race_analysis.report as report_module

    assets = tmp_path / "assets"
    shutil.copytree(report_module.ASSETS, assets)
    monkeypatch.setattr(report_module, "ASSETS", assets)
    # PNG rendering is unrelated to the browser's script and stylesheet cache.
    monkeypatch.setattr(report_module.pio, "write_images", lambda **kwargs: None)
    analysis = compare(race, laps)

    def build_urls(directory):
        report_module.build_report(race, laps, analysis, directory)
        page = BeautifulSoup((directory / "index.html").read_text(), "html.parser")
        urls = (
            next(
                tag["src"] for tag in page.select("script[src]") if tag["src"].startswith("report")
            ),
            page.select_one("link[rel=stylesheet]")["href"],
        )
        for url in urls:
            assert (directory / url).is_file()
        return urls

    first_urls = build_urls(tmp_path / "first")
    script = assets / "report.js"
    script.write_text(script.read_text().replace("let activeLap = 1;", "let activeLap = 8;"))
    stylesheet = assets / "report.css"
    stylesheet.write_text(stylesheet.read_text() + "\n/* Changed release */\n")
    second_urls = build_urls(tmp_path / "second")
    assert first_urls[0] != second_urls[0], "Changed lap defaults must request a fresh script"
    assert first_urls[1] != second_urls[1], "Changed styling must request a fresh stylesheet"


def test_replay_positions_handovers_cutoff_and_finish(race, laps):
    import json
    import shutil
    import subprocess

    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is needed to exercise the browser's replay timing functions")
    script = ROOT / "src/relay_race_analysis/assets/replay.js"
    checks = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {positionAt, snapshotAt} = require(process.argv[1]);
const report = JSON.parse(fs.readFileSync(0, 'utf8'));
const rows = report.laps;
for (const side of ['own', 'rival']) {
  const laps = rows.map(row => row[side]);
  assert.equal(positionAt(laps, -10).progress, 0);
  for (let i = 0; i < laps.length; i++) {
    const lap = laps[i];
    const start = lap.elapsed_seconds - lap.duration_seconds;
    const midway = positionAt(laps, start + lap.duration_seconds / 2);
    assert.equal(midway.runner, lap.runner);
    assert.equal(midway.lap, i + 1);
    assert.equal(midway.progress, i + 0.5);
    const finish = positionAt(laps, lap.elapsed_seconds);
    assert.equal(finish.completed, i + 1);
    assert.equal(finish.progress, i + 1);
    if (i + 1 < laps.length) assert.equal(finish.runner, laps[i + 1].runner);
  }
  assert.equal(positionAt(laps, 999999).progress, laps.length);
}
assert.equal(snapshotAt(rows, 0).split, null);
assert.equal(snapshotAt(rows, rows[0].own.elapsed_seconds).split, null);
const close = snapshotAt(rows, rows[7].rival.elapsed_seconds);
assert.equal(close.split.number, 8);
assert.equal(close.split.lead, 5);
const cutoff = snapshotAt(rows, 14400);
for (const side of ['own', 'rival']) {
  assert.equal(cutoff[side].completed, 28);
  assert.equal(cutoff[side].lap, 29);
  assert.equal(cutoff[side].finished, false);
}
const firstFinish = snapshotAt(rows, report.teams[0].finish_seconds);
assert.equal(firstFinish.own.finished, true);
assert.equal(firstFinish.rival.finished, false);
assert.equal(firstFinish.split.number, 28);
const final = snapshotAt(rows, report.teams[1].finish_seconds);
assert.equal(final.own.finished, true);
assert.equal(final.rival.finished, true);
assert.equal(final.split.lead, 73);
console.log('Replay timing checks passed at every lap midpoint and finish.');
"""
    result = subprocess.run(
        [node, "-e", checks, str(script)],
        input=json.dumps(compare(race, laps)),
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stdout + result.stderr
