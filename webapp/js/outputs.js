// Finished Videos, Musical Score Canvas visualization, and Topaz upscale dialog.

import { $, $$, api, handle, json, option, state, text } from "./core.js";

// One theme observer for all score views; loadOutputs disposes views before replacing cards.
const scoreViews = new Set();
new MutationObserver(() => scoreViews.forEach(view => view.draw())).observe(
  document.documentElement,
  { attributes: true, attributeFilter: ["data-theme"] }
);

const GRAMMAR_CLASSES = {
  "Standard": "standard",
  "Thematic multi-scene": "thematic",
  "Chaotic multi-scene": "chaotic",
  "Single-subject fragmentation": "fragmentation"
};

export function scoreView(output, video) {
  const box = text("details", "", "score-view");
  box.append(text("summary", "Watch the song conduct", "", "Show the beats, energy and planned cuts behind this video"));
  const canvas = document.createElement("canvas");
  canvas.tabIndex = 0;
  canvas.setAttribute("role", "slider");
  canvas.setAttribute("aria-label", "Musical score position. Arrow keys jump between planned cuts; Home and End go to the start and end.");
  canvas.setAttribute("aria-valuemin", "0");
  const caption = text("p", "", "score-caption");
  caption.setAttribute("aria-live", "polite");
  const legend = text("div", "", "score-legend");
  box.append(canvas, caption, legend);
  let score = null, frame = 0, lastCaption = "";
  const x = time => time / Math.max(score.duration || score.song_end, 0.001) * canvas.clientWidth;

  function colors() {
    const style = getComputedStyle(box);
    const value = name => style.getPropertyValue(name).trim();
    return {
      ink: value("--ink"),
      muted: value("--muted"),
      line: value("--line"),
      accent: value("--score-accent"),
      grammar: Object.fromEntries(Object.values(GRAMMAR_CLASSES).map(key => [key, value("--score-" + key)]))
    };
  }

  function describe(time) {
    if (time < score.offset) return "Opening ident · the song starts at " + score.offset.toFixed(1) + " s";
    if (time >= score.song_end) return "Closing ident";
    const passage = score.passages.find(item => time >= item.start && time < item.end) || score.passages.at(-1);
    const index = passage.shots.findIndex((shot, i) => time >= shot.start && (time < shot.end || i === passage.shots.length - 1));
    const shot = passage.shots[Math.max(index, 0)];
    const cut = {
      passage: passage.on_downbeat ? "passage starts on a downbeat" : "passage start",
      downbeat: "cut on a downbeat",
      beat: "cut on a beat",
      split: "long hold split"
    }[shot.cut];
    return `${passage.section} energy (${Number(passage.energy).toFixed(2)}) → ${passage.grammar}: ${passage.grammar_description} ` +
      `Shot ${Math.max(index, 0) + 1} of ${passage.shots.length}, ${shot.shot_scale}, ${cut}. ` +
      `${passage.shots.length} ${passage.shots.length === 1 ? "shot" : "shots"} across ${passage.beats} beats at ${Math.round(score.tempo_bpm)} BPM.`;
  }

  function draw() {
    if (!score) return;
    const ratio = window.devicePixelRatio || 1, width = canvas.clientWidth, height = canvas.clientHeight;
    if (canvas.width !== Math.round(width * ratio)) {
      canvas.width = Math.round(width * ratio);
      canvas.height = Math.round(height * ratio);
    }
    const ctx = canvas.getContext("2d"), c = colors();
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, width, height);
    const band = 22, curveTop = band + 8, curveBottom = height - 20;
    for (const passage of score.passages) {
      ctx.fillStyle = c.grammar[GRAMMAR_CLASSES[passage.grammar]] || c.line;
      ctx.fillRect(x(passage.start), 0, Math.max(1, x(passage.end) - x(passage.start) - 1), band);
      ctx.strokeStyle = c.ink;
      ctx.globalAlpha = 0.55;
      for (const shot of passage.shots.slice(1)) {
        ctx.beginPath();
        ctx.moveTo(x(shot.start), 0);
        ctx.lineTo(x(shot.start), curveBottom);
        ctx.stroke();
      }
      ctx.globalAlpha = 1;
    }
    ctx.beginPath();
    ctx.moveTo(x(score.offset), curveBottom);
    for (const beat of score.beats) ctx.lineTo(x(beat.time), curveBottom - beat.energy * (curveBottom - curveTop));
    ctx.lineTo(x(score.song_end), curveBottom);
    ctx.closePath();
    ctx.fillStyle = c.accent;
    ctx.globalAlpha = 0.28;
    ctx.fill();
    ctx.globalAlpha = 1;
    ctx.strokeStyle = c.accent;
    ctx.lineWidth = 1.5;
    ctx.stroke();
    ctx.lineWidth = 1;
    for (const beat of score.beats) {
      ctx.fillStyle = beat.downbeat ? c.ink : c.muted;
      ctx.fillRect(x(beat.time) - (beat.downbeat ? 1 : 0.5), height - (beat.downbeat ? 16 : 9), beat.downbeat ? 2 : 1, beat.downbeat ? 16 : 9);
    }
    const now = video.currentTime || 0;
    ctx.fillStyle = c.ink;
    ctx.fillRect(x(now) - 1, 0, 2, height);
    const line = describe(now);
    if (line !== lastCaption) {
      caption.textContent = line;
      lastCaption = line;
    }
    canvas.setAttribute("aria-valuemax", String(end()));
    canvas.setAttribute("aria-valuenow", now.toFixed(1));
    canvas.setAttribute("aria-valuetext", `${now.toFixed(1)} seconds. ${line}`);
  }

  const end = () => score.duration || score.song_end;
  function jump(time) {
    video.currentTime = Math.min(Math.max(0, time), end());
    draw();
  }
  function loop() {
    draw();
    if (!video.paused && !video.ended) frame = requestAnimationFrame(loop);
  }
  function seek(event) {
    if (!score) return;
    const rect = canvas.getBoundingClientRect();
    jump((event.clientX - rect.left) / rect.width * end());
  }

  canvas.addEventListener("keydown", event => {
    if (!score) return;
    const cuts = [0, ...score.passages.flatMap(passage => passage.shots.map(shot => shot.start)), end()];
    const now = video.currentTime || 0;
    const target = {
      ArrowRight: cuts.find(t => t > now + 0.05),
      ArrowUp: cuts.find(t => t > now + 0.05),
      ArrowLeft: cuts.filter(t => t < now - 0.05).at(-1),
      ArrowDown: cuts.filter(t => t < now - 0.05).at(-1),
      Home: 0,
      End: end()
    }[event.key];
    if (target === undefined && !(event.key in { Home: 1, End: 1 })) return;
    event.preventDefault();
    jump(target ?? now);
  });

  canvas.addEventListener("pointerdown", event => { canvas.setPointerCapture(event.pointerId); seek(event); });
  canvas.addEventListener("pointermove", event => { if (canvas.hasPointerCapture(event.pointerId)) seek(event); });
  video.addEventListener("play", () => { cancelAnimationFrame(frame); loop(); });
  ["seeked", "pause", "timeupdate", "loadedmetadata"].forEach(name => video.addEventListener(name, draw));

  const resize = new ResizeObserver(draw);
  resize.observe(canvas);
  const view = { draw, dispose: () => { resize.disconnect(); cancelAnimationFrame(frame); } };
  scoreViews.add(view);

  box.addEventListener("toggle", async () => {
    if (!box.open || score) return draw();
    try {
      score = await (await api(`/api/outputs/${encodeURIComponent(output.file.split("/")[0])}/score`)).json();
      legend.replaceChildren(
        ...[...new Set(score.passages.map(passage => passage.grammar))].map(name =>
          text("span", name, "score-key score-" + (GRAMMAR_CLASSES[name] || "other"))
        ),
        text("span", "energy", "score-key score-energy"),
        text("span", "beats · downbeats (tall)", "score-key score-beats"),
        text("span", "planned cuts", "score-key score-cuts")
      );
      draw();
    } catch (error) {
      box.replaceChildren(text("summary", "Watch the song conduct"), text("p", error.message, "muted"));
    }
  });
  return box;
}

export async function loadOutputs() {
  const outputs = await (await api("/api/outputs")).json();
  scoreViews.forEach(view => view.dispose());
  scoreViews.clear();
  $("#output-list").replaceChildren(...outputs.map(output => {
    const card = text("article", "", "card", `Rendered output: ${output.title}`);
    const video = document.createElement("video");
    video.src = "/api/media/" + output.file;
    video.controls = true;
    video.preload = "metadata";
    video.dataset.tooltip = `Video player for ${output.title}`;
    video.title = video.dataset.tooltip;

    const download = text("a", "Download", "download", `Download ${output.title} as MP4`);
    download.href = "/api/media/" + output.file + "?download=true";

    const upscale = text("button", "Topaz upscale ↗", "quiet", `Upscale ${output.title} using Topaz Video AI`);
    upscale.onclick = () => {
      state.upscaleSource = output.file;
      $("#upscale-dialog").showModal();
    };

    card.append(video);
    if (output.kind === "video") card.append(scoreView(output, video));
    card.append(text("h2", output.title), text("p", `${output.kind} · ${Number(output.duration).toFixed(1)} seconds`));
    if (output.quality_warnings?.length) {
      const warning = text("div", "", "quality-warning", "Automatic motion and framing check results");
      warning.setAttribute("role", "note");
      warning.append(text("strong", "Quality check: "), output.quality_warnings.join(" · "));
      card.append(warning);
    }
    card.append(download, upscale);
    return card;
  }));
  if (!outputs.length) {
    $("#output-list").append(text("div", "Your finished videos and idents will appear here.", "empty", "No completed productions yet"));
  }
  $$(".ident-select").forEach(select => {
    const old = select.value;
    select.replaceChildren(
      option("", "None", "No ident clip attached"),
      ...outputs.filter(output => output.kind === "ident").map(output =>
        option(output.file, output.title, `Ident clip: ${output.title}`)
      )
    );
    if ([...select.options].some(item => item.value === old)) select.value = old;
  });
}

export function initUpscaleForm() {
  $("#upscale-form").onsubmit = handle(async event => {
    const body = Object.fromEntries(new FormData(event.target));
    body.scale = Number(body.scale);
    await json("/api/upscale", { ...body, source: state.upscaleSource });
    $("#upscale-dialog").close();
  });
}

