/* All data is embedded in the generated HTML; this report also works from file://. */
"use strict";
const report = JSON.parse(document.getElementById("report-data").textContent);
const figures = JSON.parse(document.getElementById("report-figures").textContent);
const raceConfig = JSON.parse(document.getElementById("race-config").textContent);
const raceCharts = ["gap-chart"];
const chartConfig = {responsive: true, displaylogo: false, scrollZoom: false,
  modeBarButtonsToRemove: ["select2d", "lasso2d", "toImage"],
  toImageButtonOptions: {format: "png", width: 1400, height: 700, scale: 2}};
let activeLap = 1;

function time(seconds) {
  const value = Math.round(seconds);
  return `${Math.floor(value / 60)}:${String(value % 60).padStart(2, "0")}`;
}
function signed(value) { return `${value >= 0 ? "+" : ""}${value}`; }
function escapeHTML(value) {
  return String(value).replace(/[&<>"']/g, character =>
    ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[character]));
}
function selectLap(number) {
  activeLap = Math.max(1, Math.min(report.count, Number(number)));
  const row = report.laps[activeLap - 1];
  document.getElementById("lap-slider").value = activeLap;
  document.getElementById("lap-label").textContent =
    `LAP ${String(activeLap).padStart(2, "0")} / ${report.count}`;
  document.getElementById("previous-lap").disabled = activeLap === 1;
  document.getElementById("next-lap").disabled = activeLap === report.count;
  const outcome = row.gain > 0 ? "Tracklife gained" : row.gain < 0 ? "Tracklife lost" : "Same lap time";
  document.getElementById("lap-detail").innerHTML = `
    <div><p class="detail-label">Tracklife London</p>
      <p class="detail-name">${escapeHTML(row.own.runner)}</p>
      <span class="detail-value positive">${time(row.own.duration_seconds)}
      <small>${time(row.own.duration_seconds / raceConfig.lap_distance_km)}/km</small></span></div>
    <div><p class="detail-label">Run for Will-Being</p>
      <p class="detail-name">${escapeHTML(row.rival.runner)}</p>
      <span class="detail-value" style="color:#4763b4">${time(row.rival.duration_seconds)}
      <small>${time(row.rival.duration_seconds / raceConfig.lap_distance_km)}/km</small></span></div>
    <div><p class="detail-label">${outcome}</p>
      <span class="detail-value ${row.gain >= 0 ? "positive" : "negative"}">${signed(row.gain)}s</span>
      <p class="detail-gap">${row.lead >= 0 ? "Tracklife ahead by" : "Will-Being ahead by"} <strong>${Math.abs(row.lead)}s</strong> after this lap</p></div>`;
  for (const id of raceCharts) {
    const existing = figures[id].layout.shapes || [];
    const selection = {type: "line", xref: "x", yref: "paper", x0: activeLap, x1: activeLap,
      y0: 0, y1: 1, line: {color: "#899586", width: 1.2, dash: "dot"}, layer: "below"};
    Plotly.relayout(id, {shapes: [...existing, selection]});
  }
  document.querySelectorAll(".lap-table tbody tr").forEach(element =>
    element.classList.toggle("selected", Number(element.dataset.lap) === activeLap));
}
function renderRunnerTable() {
  document.getElementById("runner-table").innerHTML = report.runners.map(runner => {
    const stats = runner.all;
    const own = runner.team_id === report.teams[0].id;
    return `<tr><th scope="row">${escapeHTML(runner.name)}</th>
      <td><span class="team-pill ${own ? "" : "rival"}">${own ? "Tracklife" : "Will-Being"}</span></td>
      <td class="numeric">${stats.count}</td>
      <td class="numeric">${stats.average === null ? "—" : time(stats.average)}</td>
      <td class="numeric">${stats.average === null ? "—" : time(stats.average / raceConfig.lap_distance_km)}</td>
      <td class="numeric">${stats.best === null ? "—" : time(stats.best)}</td>
      <td class="numeric">${stats.sd === null ? "—" : stats.sd.toFixed(1) + "s"}</td>
      <td class="numeric">${stats.change === null ? "—" :
        stats.change === 0 ? "No change" : `${Math.abs(stats.change)}s ${stats.change > 0 ? "slower" : "faster"}`}</td></tr>`;
  }).join("");
}
async function initialise() {
  await Promise.all(Object.entries(figures).map(([id, figure]) => {
    document.getElementById(id).style.height = `${figure.layout.height}px`;
    return Plotly.newPlot(id, structuredClone(figure.data), structuredClone(figure.layout), chartConfig);
  }));
  for (const id of raceCharts) {
    document.getElementById(id).on("plotly_click", event => {
      const number = event.points[0]?.customdata?.[0];
      if (number) selectLap(number);
    });
  }
  document.getElementById("lap-slider").addEventListener("input", event => selectLap(event.target.value));
  document.getElementById("previous-lap").addEventListener("click", () => selectLap(activeLap - 1));
  document.getElementById("next-lap").addEventListener("click", () => selectLap(activeLap + 1));
  document.querySelectorAll("[data-select-lap]").forEach(button =>
    button.addEventListener("click", () => {
      selectLap(button.dataset.selectLap);
      document.querySelector(".lap-inspector").scrollIntoView({block: "center", behavior: "smooth"});
    }));
  renderRunnerTable();
  selectLap(activeLap);
  document.documentElement.dataset.reportReady = "true";
}
initialise().catch(error => {
  console.error("Report initialisation failed", error);
  const notice = document.createElement("p");
  notice.className = "noscript-note";
  notice.textContent = "The charts could not load. The lap table and data downloads are still available.";
  document.querySelector("main").prepend(notice);
});
