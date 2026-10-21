// A small inline colour wheel: hue around the circle, saturation toward the centre, a brightness slider and a hex box.
// It enhances a text input (the value stays "#rrggbb" in that input, so forms, saved projects and requests are unchanged).

const SIZE = 132;                       // CSS pixels; the canvas is drawn at the device's pixel ratio for sharp edges

// Pure colour maths (exported for tests): h in degrees, s and v in 0..1, rgb in 0..255.
export function hsvToRgb(h, s, v) {
  h = ((h % 360) + 360) % 360;
  const f = n => { const k = (n + h / 60) % 6; return v - v * s * Math.max(0, Math.min(k, 4 - k, 1)); };
  return [f(5), f(3), f(1)].map(x => Math.round(x * 255));
}

export function rgbToHsv([r, g, b]) {
  const [R, G, B] = [r, g, b].map(x => x / 255);
  const max = Math.max(R, G, B), d = max - Math.min(R, G, B);
  const h = d === 0 ? 0 : max === R ? ((G - B) / d + 6) % 6 : max === G ? (B - R) / d + 2 : (R - G) / d + 4;
  return { h: h * 60, s: max === 0 ? 0 : d / max, v: max };
}

export const toHex = rgb => "#" + rgb.map(x => x.toString(16).padStart(2, "0")).join("");

// "#abc", "abc", "#aabbcc" or "AABBCC" -> [r, g, b], otherwise null.
export function parseHex(text) {
  const m = /^#?([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(String(text).trim());
  if (!m) return null;
  const full = m[1].length === 3 ? [...m[1]].map(c => c + c).join("") : m[1];
  return [0, 2, 4].map(i => parseInt(full.slice(i, i + 2), 16));
}

const wheelImageCache = new Map();

function drawWheel(canvas) {
  const px = canvas.width, ctx = canvas.getContext("2d");
  const cached = wheelImageCache.get(px);
  if (cached) { ctx.putImageData(cached, 0, 0); return; }
  const radius = px / 2, image = new ImageData(px, px);
  for (let y = 0; y < px; y++) for (let x = 0; x < px; x++) {
    const dx = x + 0.5 - radius, dy = y + 0.5 - radius, distance = Math.hypot(dx, dy);
    if (distance > radius) continue;
    const [r, g, b] = hsvToRgb((Math.atan2(dy, dx) * 180 / Math.PI + 360) % 360, distance / radius, 1);
    const i = (y * px + x) * 4;
    image.data.set([r, g, b, distance > radius - 1 ? Math.round(255 * (radius - distance)) : 255], i);   // soft edge
  }
  wheelImageCache.set(px, image);
  ctx.putImageData(image, 0, 0);
}

export function mountColourWheel(input) {
  const initial = parseHex(input.value) || [255, 255, 255];
  let color = rgbToHsv(initial), last = toHex(initial);
  const ratio = Math.min(window.devicePixelRatio || 1, 3);
  const box = document.createElement("div");
  box.className = "colour-wheel";
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = Math.round(SIZE * ratio);
  canvas.style.width = canvas.style.height = SIZE + "px";
  canvas.tabIndex = 0;
  canvas.setAttribute("role", "slider");                       // one slider whose value is read out as hue, saturation and the hex colour
  canvas.setAttribute("aria-label", `${input.getAttribute("aria-label") || "Colour"} wheel: arrow keys change the hue and the saturation`);
  canvas.setAttribute("aria-valuemin", "0");
  canvas.setAttribute("aria-valuemax", "360");
  const marker = document.createElement("span");
  marker.className = "colour-marker";
  const slider = document.createElement("input");
  slider.type = "range";
  slider.min = "0"; slider.max = "100"; slider.step = "1";
  slider.setAttribute("aria-label", `${input.getAttribute("aria-label") || "Colour"} brightness`);
  const swatch = document.createElement("span");
  swatch.className = "colour-swatch";
  swatch.setAttribute("aria-hidden", "true");
  const stage = document.createElement("div");
  stage.className = "colour-stage";
  stage.append(canvas, marker);
  const row = document.createElement("div");
  row.className = "colour-row";
  row.append(swatch);
  input.before(box);
  row.append(input);
  box.append(stage, slider, row);

  drawWheel(canvas);                    // always at full brightness, once: the slider carries the brightness
  const paint = () => {
    const rgb = hsvToRgb(color.h, color.s, color.v), hex = toHex(rgb);
    const angle = color.h * Math.PI / 180;
    marker.style.left = SIZE / 2 + Math.cos(angle) * color.s * SIZE / 2 + "px";
    marker.style.top = SIZE / 2 + Math.sin(angle) * color.s * SIZE / 2 + "px";
    canvas.setAttribute("aria-valuenow", String(Math.round(color.h)));
    canvas.setAttribute("aria-valuetext", `hue ${Math.round(color.h)} degrees, saturation ${Math.round(color.s * 100)} percent, colour ${hex}`);
    slider.value = String(Math.round(color.v * 100));
    slider.style.background = `linear-gradient(to right, #000, ${toHex(hsvToRgb(color.h, color.s, 1))})`;
    swatch.style.background = hex;
    return hex;
  };
  const publish = () => {
    const hex = paint();
    last = hex;
    if (input.value !== hex) { input.value = hex; input.dispatchEvent(new Event("input", { bubbles: true })); input.dispatchEvent(new Event("change", { bubbles: true })); }
  };
  const fromPointer = event => {
    const rect = canvas.getBoundingClientRect(), r = rect.width / 2;
    const dx = event.clientX - rect.left - r, dy = event.clientY - rect.top - r;
    // Picking on a black colour would change nothing visible, so a pick on the wheel lifts it to full brightness.
    color = { h: (Math.atan2(dy, dx) * 180 / Math.PI + 360) % 360, s: Math.min(Math.hypot(dx, dy) / r, 1), v: color.v < 0.05 ? 1 : color.v };
    publish();
  };
  let active = null;                    // one pointer at a time: a second finger or a right click cannot fight over the colour
  canvas.addEventListener("pointerdown", event => {
    if (active !== null || (event.pointerType === "mouse" && event.button !== 0)) return;
    active = event.pointerId;
    canvas.setPointerCapture(event.pointerId);
    canvas.focus();                      // preventDefault below would otherwise stop the click from focusing, so arrow keys went elsewhere
    fromPointer(event);
    event.preventDefault();
  });
  canvas.addEventListener("pointermove", event => { if (event.pointerId === active) fromPointer(event); });
  for (const end of ["pointerup", "pointercancel", "lostpointercapture"]) canvas.addEventListener(end, event => { if (event.pointerId === active) active = null; });
  canvas.addEventListener("keydown", event => {
    const step = { ArrowLeft: [-4, 0], ArrowRight: [4, 0], ArrowUp: [0, 0.04], ArrowDown: [0, -0.04] }[event.key];
    if (!step) return;
    color = { h: (color.h + step[0] + 360) % 360, s: Math.max(0, Math.min(1, color.s + step[1])), v: color.v < 0.05 ? 1 : color.v };
    publish();
    event.preventDefault();
  });
  slider.addEventListener("input", () => { color = { ...color, v: Number(slider.value) / 100 }; publish(); });
  // Typing a colour: accept #abc / abc / #aabbcc; anything else goes back to the last good colour.
  input.addEventListener("change", () => {
    const rgb = parseHex(input.value);
    if (!rgb) { input.value = last; return; }
    const hex = toHex(rgb);
    if (hex !== last) color = rgbToHsv(rgb);
    last = hex;
    input.value = hex;
    paint();
  });
  paint();
  return { refresh: () => { const rgb = parseHex(input.value); if (rgb) { color = rgbToHsv(rgb); last = toHex(rgb); } input.value = last; paint(); } };
}

// Every [data-colour-wheel] input becomes a wheel; the returned list refreshes them after a value is restored from outside.
export function initColourWheels(root = document) {
  const wheels = [...root.querySelectorAll("input[data-colour-wheel]")].map(mountColourWheel);
  return () => wheels.forEach(wheel => wheel.refresh());
}
