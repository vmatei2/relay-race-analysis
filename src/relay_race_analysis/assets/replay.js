/* Lap finishes are measured; movement between them assumes constant lap speed. */
(function () {
  "use strict";
  function positionAt(laps, seconds) {
    const elapsed = Math.max(0, seconds);
    const next = laps.findIndex(lap => lap.elapsed_seconds > elapsed);
    if (next === -1) {
      return {completed: laps.length, lap: laps.length, progress: laps.length,
        fraction: 0, runner: laps.at(-1).runner, finished: true};
    }
    const lap = laps[next];
    const start = lap.elapsed_seconds - lap.duration_seconds;
    const fraction = Math.max(0, Math.min(1, (elapsed - start) / lap.duration_seconds));
    return {completed: next, lap: lap.number, progress: next + fraction,
      fraction, runner: lap.runner, finished: false};
  }
  function snapshotAt(rows, seconds) {
    const own = positionAt(rows.map(row => row.own), seconds);
    const rival = positionAt(rows.map(row => row.rival), seconds);
    const common = Math.min(own.completed, rival.completed);
    return {own, rival, split: common ? rows[common - 1] : null};
  }
  // The same timing functions run in the browser and the Node regression tests.
  if (typeof module !== "undefined" && module.exports) {
    module.exports = {positionAt, snapshotAt};
  }
  if (typeof document === "undefined") return;
  const container = document.getElementById("replay");
  if (!container) return;
  const report = JSON.parse(document.getElementById("report-data").textContent);
  const config = JSON.parse(document.getElementById("race-config").textContent);
  const end = Math.max(...report.teams.map(team => team.finish_seconds));
  const ownFinish = report.teams[0].finish_seconds;
  const rivalFinish = report.teams[1].finish_seconds;
  const el = name => document.getElementById(`replay-${name}`);
  const path = document.getElementById("replay-course-path");
  const pathLength = path.getTotalLength();
  const clock = seconds => {
    const total = Math.floor(seconds);
    return `${Math.floor(total / 3600)}:${String(Math.floor(total / 60) % 60).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
  };
  let raceTime = 0;
  let playing = false;
  let frameId = null;
  let previousFrame = null;
  let lastStory = -1;
  el("slider").max = end;
  const moments = [
    {at: 0, label: "THE START", text: "Omar and Kazuya take the opening lap."},
    ...[1, 7, 8, 13, 23, 28].filter(lap => lap <= report.count).map(number => {
      const row = report.laps[number - 1];
      const lines = {
        1: `Omar runs 7:42; Kazuya runs 7:47. Tracklife starts with a ${row.lead}s lead.`,
        7: `Greg finishes lap 7. Tracklife’s lead reaches ${row.lead}s.`,
        8: `James runs 9:02 and Alexander runs 8:22. The gap falls to ${row.lead}s.`,
        13: `Omar’s 8:07 gains 19 seconds, the largest gain on a single lap.`,
        23: `Tracklife’s lead reaches ${row.lead}s, the largest gap at a recorded split.`,
        28: `Both teams start the final lap. Tracklife’s lead is ${row.lead}s.`
      };
      return {at: Math.max(row.own.elapsed_seconds, row.rival.elapsed_seconds),
        label: `LAP ${String(number).padStart(2, "0")}`, text: lines[number]};
    }),
    {at: ownFinish, label: "TRACKLIFE FINISH", text: `Omar finishes lap 29 at ${clock(ownFinish)}. Will-Being is still on the course.`},
    {at: rivalFinish, label: "BOTH TEAMS FINISHED", text: `Will-Being finishes at ${clock(rivalFinish)}. Both teams cover ${report.distance} km; Tracklife wins by ${report.margin} seconds.`}
  ].sort((a, b) => a.at - b.at);
  function moveDot(id, state, offset) {
    const distance = state.fraction * pathLength;
    const point = path.getPointAtLength(distance);
    const before = path.getPointAtLength((distance - 1 + pathLength) % pathLength);
    const after = path.getPointAtLength((distance + 1) % pathLength);
    const dx = after.x - before.x, dy = after.y - before.y;
    const length = Math.hypot(dx, dy) || 1;
    el(`dot-${id}`).setAttribute("transform", `translate(${point.x - dy / length * offset} ${point.y + dx / length * offset})`);
  }
  function render() {
    const state = snapshotAt(report.laps, raceTime);
    el("clock").textContent = clock(raceTime);
    el("slider").value = raceTime;
    el("slider").setAttribute("aria-valuetext", `${clock(raceTime)} race time`);
    [["own", state.own, -14], ["rival", state.rival, 14]].forEach(([id, team, offset]) => {
      moveDot(id, team, offset);
      el(`runner-${id}`).textContent = team.finished ? "Finished" : team.runner;
      el(`lap-${id}`).textContent = team.finished ? `${team.completed} laps · ${clock(report.teams[id === "own" ? 0 : 1].finish_seconds)}` : `Lap ${team.lap} of ${report.count} · ${team.completed} complete`;
      el(`distance-${id}`).textContent = `${(team.progress * config.lap_distance_km).toFixed(1)} km`;
      el(`progress-${id}`).style.width = `${team.progress / report.count * 100}%`;
    });
    if (state.split) {
      const lead = state.split.lead;
      el("leader").textContent = lead > 0 ? "Tracklife ahead" : lead < 0 ? "Will-Being ahead" : "Level at the split";
      el("gap-value").textContent = `${Math.abs(lead)}s`;
      el("gap-split").textContent = state.own.finished && state.rival.finished ? "Final winning margin" : `At completed lap ${state.split.number}`;
    } else {
      el("leader").textContent = raceTime === 0 ? "Together at the start" : "Waiting for lap 1";
      el("gap-value").textContent = raceTime === 0 ? "0s" : "—";
      el("gap-split").textContent = "No completed split yet";
    }
    const index = moments.findLastIndex(moment => moment.at <= raceTime);
    if (index !== lastStory) {
      lastStory = index;
      el("story-time").textContent = moments[index].label;
      el("story-text").textContent = moments[index].text;
    }
    el("status").textContent = raceTime >= end ? "Race finished" : playing ? "Playing" : raceTime === 0 ? "Ready to start" : "Paused";
    el("play").innerHTML = playing ? 'Pause <span aria-hidden="true">Ⅱ</span>' : raceTime >= end ? 'Replay race <span aria-hidden="true">↺</span>' : 'Play race <span aria-hidden="true">▶</span>';
    el("play").setAttribute("aria-pressed", String(playing));
  }
  function pause() {
    playing = false;
    cancelAnimationFrame(frameId);
    frameId = null;
    previousFrame = null;
  }
  function seek(seconds) {
    pause();
    raceTime = Math.max(0, Math.min(end, Number(seconds)));
    render();
  }
  function tick(timestamp) {
    if (!playing) return;
    if (previousFrame !== null) raceTime = Math.min(end, raceTime + (timestamp - previousFrame) / 1000 * end / Number(el("speed").value));
    previousFrame = timestamp;
    if (raceTime >= end) pause();
    render();
    if (playing) frameId = requestAnimationFrame(tick);
  }
  el("play").addEventListener("click", () => {
    if (playing) {pause(); render(); return;}
    if (raceTime >= end) raceTime = 0;
    playing = true;
    previousFrame = null;
    render();
    frameId = requestAnimationFrame(tick);
  });
  el("reset").addEventListener("click", () => seek(0));
  el("slider").addEventListener("input", event => seek(event.target.value));
  el("speed").addEventListener("change", () => {previousFrame = null;});
  container.querySelectorAll("[data-replay-lap]").forEach(button => button.addEventListener("click", () => {
    const row = report.laps[Number(button.dataset.replayLap) - 1];
    seek(Math.max(row.own.elapsed_seconds, row.rival.elapsed_seconds));
  }));
  el("finish").addEventListener("click", () => seek(end));
  document.addEventListener("visibilitychange", () => {
    // Hidden tabs pause rather than jumping forward when you return.
    if (document.hidden && playing) {pause(); render();}
  });
  render();
})();
