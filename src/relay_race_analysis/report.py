"""Generate a portable static report with local Plotly assets and data exports."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from hashlib import sha256
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
            "title": "Race lap",
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
    own = race.teams[0]
    gap = base_figure("Tracklife lead (seconds)", 380)
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
                "Lap %{x}<br>Tracklife finished %{y}s earlier"
                "<br>Tracklife total: %{customdata[1]}"
                "<br>Will-Being total: %{customdata[2]}<extra></extra>"
            ),
        )
    )
    for lap_number, label in (
        (8, "5s ahead at lap 8"),
        (report["peak"]["number"], f"Largest lead: {report['peak']['lead']}s"),
        (report["count"], f"Finish: {report['margin']}s"),
    ):
        if lap_number <= len(rows):
            row = rows[lap_number - 1]
            gap.add_annotation(
                x=lap_number,
                y=row["lead"],
                text=label,
                showarrow=True,
                arrowhead=0,
                ax=-35 if lap_number == report["count"] else 0,
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
    return {"gap-chart": json.loads(gap.to_json())}


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
    asset_urls = {}
    for filename in ("report.css", "report.js", "replay.js"):
        content = (ASSETS / filename).read_bytes()
        path = Path(filename)
        versioned_name = f"{path.stem}.{sha256(content).hexdigest()[:12]}{path.suffix}"
        (output / versioned_name).write_bytes(content)
        asset_urls[filename] = versioned_name
    environment = Environment(
        loader=FileSystemLoader(ASSETS), autoescape=select_autoescape(["html"])
    )
    environment.filters["time"] = format_time
    template = environment.get_template("index.html")
    chart_specs = figures(race, report)
    export_titles = {"gap-chart": "Tracklife’s lead over Run for Will-Being"}
    export_figures = []
    export_caption = " · ".join(
        [race.title, race.date, "Official finish-line timings", f"{race.lap_distance_km} km / lap"]
    )
    for chart_id, spec in chart_specs.items():
        image = go.Figure(spec)
        image.update_layout(
            title={
                "text": export_titles[chart_id],
                "font": {"size": 24},
                "x": 0.04,
                "y": 0.96,
                "yanchor": "top",
            },
            legend={"orientation": "h", "x": 0, "y": 1.11, "yanchor": "top"},
            paper_bgcolor="#fffef9",
            plot_bgcolor="#fffef9",
            margin={"l": 85, "r": 40, "t": 140, "b": 100},
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
        asset_urls=asset_urls,
        margin_time=format_time(abs(report["margin"])),
    )
    (output / "index.html").write_text(page, encoding="utf-8")
    (output / ".nojekyll").touch()
