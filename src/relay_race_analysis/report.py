"""Generate a portable static report with local Plotly assets and data exports."""

from __future__ import annotations

import csv
import json
import shutil
from dataclasses import asdict
from pathlib import Path

import plotly.graph_objects as go
import plotly.io as pio
from jinja2 import Environment, FileSystemLoader, select_autoescape
from plotly.offline import get_plotlyjs

from .analysis import format_time
from .data import Lap, Race

ASSETS = Path(__file__).parent / "assets"


def base_figure(y_title: str, height: int = 340) -> go.Figure:
    figure = go.Figure()
    figure.update_layout(
        template="plotly_white",
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "Arial, sans-serif", "color": "#233630"},
        margin={"l": 55, "r": 20, "t": 28, "b": 50},
        hovermode="x unified",
        hoverlabel={"bgcolor": "#fffdf8", "font_size": 13},
        xaxis={
            "title": "Completed lap",
            "dtick": 2,
            "range": [0.5, 29.5],
            "showgrid": False,
            "zeroline": False,
        },
        yaxis={"title": y_title, "gridcolor": "#e4e8e0", "zerolinecolor": "#aab7ae"},
        legend={"orientation": "h", "y": 1.13, "x": 0},
        modebar={"bgcolor": "rgba(0,0,0,0)", "color": "#62746b"},
    )
    return figure


def figures(race: Race, report: dict) -> dict:
    rows = report["laps"]
    numbers = [row["number"] for row in rows]
    own, rival = race.teams
    gap = base_figure("Tracklife lead · seconds", 380)
    gap.update_layout(showlegend=False)
    gap.add_trace(
        go.Scatter(
            x=numbers,
            y=[row["lead"] for row in rows],
            name="Lead",
            mode="lines+markers",
            line={"color": own.color, "width": 3},
            marker={"size": 6},
            fill="tozeroy",
            fillcolor="rgba(33,97,78,0.10)",
            customdata=[
                [
                    row["number"],
                    format_time(row["own"]["elapsed_seconds"], True),
                    format_time(row["rival"]["elapsed_seconds"], True),
                ]
                for row in rows
            ],
            hovertemplate=(
                "Lap %{x}<br>Tracklife lead: %{y}s<br>Tracklife: %{customdata[1]}"
                "<br>Will-Being: %{customdata[2]}<extra></extra>"
            ),
        )
    )
    for lap_number, label in (
        (8, "Just 5s at lap 8"),
        (report["peak"]["number"], f"Peak: {report['peak']['lead']}s"),
    ):
        if lap_number <= len(rows):
            row = rows[lap_number - 1]
            gap.add_annotation(
                x=lap_number,
                y=row["lead"],
                text=label,
                showarrow=True,
                arrowhead=0,
                ax=0,
                ay=-38,
                font={"size": 12},
            )
    gap.update_yaxes(
        range=[
            min(-5, min(row["lead"] for row in rows) - 10),
            max(row["lead"] for row in rows) + 32,
        ],
        ticksuffix="s",
    )
    gain = base_figure("Seconds gained / lost")
    gain.add_trace(
        go.Bar(
            x=numbers,
            y=[row["gain"] for row in rows],
            name="Change in lead",
            marker_color=[own.color if row["gain"] >= 0 else "#b55b3e" for row in rows],
            customdata=[
                [
                    row["number"],
                    row["own"]["runner"],
                    row["rival"]["runner"],
                    format_time(row["own"]["duration_seconds"]),
                    format_time(row["rival"]["duration_seconds"]),
                ]
                for row in rows
            ],
            hovertemplate=(
                "Lap %{x}<br>Change in Tracklife lead: %{y:+d}s"
                "<br>%{customdata[1]}: %{customdata[3]}"
                "<br>%{customdata[2]}: %{customdata[4]}<extra></extra>"
            ),
        )
    )
    gain.update_layout(showlegend=False, bargap=0.25)
    gain.update_yaxes(ticksuffix="s")
    pace = base_figure("Lap time · min:sec", 380)
    for team, key in ((own, "own"), (rival, "rival")):
        pace.add_trace(
            go.Scatter(
                x=numbers,
                y=[row[key]["duration_seconds"] for row in rows],
                name=team.name,
                mode="lines+markers",
                line={"color": team.color, "width": 2.5},
                marker={"size": 7, "symbol": "circle" if key == "own" else "diamond"},
                customdata=[
                    [
                        row["number"],
                        row[key]["runner"],
                        format_time(row[key]["duration_seconds"]),
                        format_time(row[key]["duration_seconds"] / race.lap_distance_km),
                    ]
                    for row in rows
                ],
                hovertemplate=(
                    "%{customdata[1]}<br>Lap: %{customdata[2]}"
                    "<br>Pace: %{customdata[3]}/km<extra>%{fullData.name}</extra>"
                ),
            )
        )
    ticks = list(range(450, 571, 15))
    pace.update_yaxes(tickvals=ticks, ticktext=[format_time(value) for value in ticks])
    pace.update_layout(
        shapes=[
            {
                "type": "rect",
                "xref": "x",
                "yref": "paper",
                "x0": 0.5,
                "x1": 1.5,
                "y0": 0,
                "y1": 1,
                "fillcolor": "#e8e0ce",
                "opacity": 0.45,
                "line": {"width": 0},
                "layer": "below",
            }
        ]
    )
    result = {"gap-chart": gap, "gain-chart": gain, "pace-chart": pace}
    palettes = (
        ("#21614e", "#448b83", "#89673c", "#344b5e"),
        ("#4763b4", "#8671a8", "#3c8b9b", "#9b6a81"),
    )
    for team, palette in zip(race.teams, palettes, strict=True):
        figure = base_figure("Lap time · min:sec", 320)
        maximum_outings = max(
            len(runner["outings"]) for runner in report["runners"] if runner["team_id"] == team.id
        )
        figure.update_xaxes(title="Runner outing", dtick=1, range=[0.7, maximum_outings + 0.3])
        figure.update_yaxes(tickvals=ticks, ticktext=[format_time(value) for value in ticks])
        for runner, color in zip(
            [runner for runner in report["runners"] if runner["team_id"] == team.id],
            palette,
            strict=False,
        ):
            outings = runner["outings"]
            figure.add_trace(
                go.Scatter(
                    x=list(range(1, len(outings) + 1)),
                    y=[lap["duration_seconds"] for lap in outings],
                    mode="lines+markers",
                    name=runner["name"].split()[0],
                    line={"color": color, "width": 2},
                    marker={"size": 7},
                    customdata=[
                        [lap["number"], runner["name"], format_time(lap["duration_seconds"])]
                        for lap in outings
                    ],
                    hovertemplate=(
                        "%{customdata[1]}<br>Race lap %{customdata[0]}"
                        "<br>Lap: %{customdata[2]}<extra></extra>"
                    ),
                )
            )
        result[f"runners-{team.id}"] = figure
    return {key: json.loads(figure.to_json()) for key, figure in result.items()}


def build_report(race: Race, laps: list[Lap], report: dict, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    exports = output / "downloads"
    exports.mkdir(exist_ok=True)
    with (exports / "laps.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(asdict(laps[0])))
        writer.writeheader()
        writer.writerows(asdict(lap) for lap in laps)
    with (exports / "head-to-head.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "lap",
                "tracklife_runner",
                "willbeing_runner",
                "tracklife_lap_seconds",
                "willbeing_lap_seconds",
                "tracklife_gain_seconds",
                "tracklife_lead_seconds",
            ]
        )
        for row in report["laps"]:
            writer.writerow(
                [
                    row["number"],
                    row["own"]["runner"],
                    row["rival"]["runner"],
                    row["own"]["duration_seconds"],
                    row["rival"]["duration_seconds"],
                    row["gain"],
                    row["lead"],
                ]
            )
    (exports / "analysis.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (output / "plotly.min.js").write_text(get_plotlyjs(), encoding="utf-8")
    for filename in ("report.css", "report.js"):
        shutil.copyfile(ASSETS / filename, output / filename)
    environment = Environment(
        loader=FileSystemLoader(ASSETS), autoescape=select_autoescape(["html"])
    )
    environment.filters["time"] = format_time
    template = environment.get_template("index.html")
    chart_specs = figures(race, report)
    export_titles = {
        "gap-chart": "Cumulative lead · Tracklife London vs Run for Will-Being",
        "gain-chart": "Seconds gained or lost · Tracklife London vs Run for Will-Being",
        "pace-chart": "Lap times · Tracklife London vs Run for Will-Being",
        "runners-tracklife": "Tracklife London · Individual runner outings",
        "runners-willbeing": "Run for Will-Being · Individual runner outings",
    }
    export_figures = []
    export_caption = " · ".join(
        [race.title, race.date, "Published cumulative timing", f"{race.lap_distance_km} km / lap"]
    )
    for chart_id, spec in chart_specs.items():
        image = go.Figure(spec)
        image.update_layout(
            title={"text": export_titles[chart_id], "font": {"size": 24}, "x": 0.04},
            paper_bgcolor="#fffef9",
            plot_bgcolor="#fffef9",
            margin={"l": 85, "r": 40, "t": 105, "b": 100},
        )
        image.add_annotation(
            text=export_caption,
            xref="paper",
            yref="paper",
            x=0,
            y=-0.15,
            showarrow=False,
            font={"size": 12, "color": "#69766e"},
        )
        export_figures.append(image)
    pio.write_images(
        fig=export_figures,
        file=[exports / f"{chart_id}.png" for chart_id in chart_specs],
        format="png",
        width=1400,
        height=700,
        scale=2,
    )
    page = template.render(
        race=race,
        report=report,
        figures=chart_specs,
        margin_time=format_time(abs(report["margin"])),
    )
    (output / "index.html").write_text(page, encoding="utf-8")
    (output / ".nojekyll").touch()
