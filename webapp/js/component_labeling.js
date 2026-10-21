// Component Labeling Mode for Studio AI Pair Programming & UI Refactoring.
// Enables dev overlay on Ctrl+Shift+L or the header button, rendering
// component outlines, names, stable IDs, and click-to-copy breadcrumbs.

import { $, $$, copyToClipboard, notice } from "./core.js";

let isLabelingActive = false;
let overlayEl = null;
let badgeEl = null;
let currentTarget = null;

function createOverlay() {
  if (overlayEl) return;
  overlayEl = document.createElement("div");
  overlayEl.className = "component-labeling-overlay";
  overlayEl.hidden = true;

  badgeEl = document.createElement("div");
  badgeEl.className = "component-labeling-badge";
  badgeEl.hidden = true;

  badgeEl.onclick = async (e) => {
    e.stopPropagation();
    if (!currentTarget) return;
    const name = currentTarget.dataset.component;
    const id = currentTarget.dataset.componentId;
    const copiedText = `${name} (${id})`;
    try {
      await copyToClipboard(copiedText);
      const original = [...badgeEl.childNodes];
      const copied = Object.assign(document.createElement("span"), { className: "comp-name", textContent: "Copied!" });
      badgeEl.replaceChildren(copied);
      setTimeout(() => { if (badgeEl) badgeEl.replaceChildren(...original); }, 1200);
      notice(`Copied component "${name}" (${id}) to clipboard.`);
    } catch {
      notice(`Component ID: ${id}`);
    }
  };

  document.body.append(overlayEl, badgeEl);
}

function getHierarchyPath(el) {
  const path = [];
  let cur = el;
  while (cur) {
    if (cur.dataset && cur.dataset.component) {
      path.unshift(cur.dataset.component);
    }
    cur = cur.parentElement;
  }
  return path.join(" > ");
}

function updateOverlay(el) {
  if (!el || !overlayEl || !badgeEl) return;
  currentTarget = el;
  const rect = el.getBoundingClientRect();
  const name = el.dataset.component || "Unnamed Component";
  const id = el.dataset.componentId || "unassigned-id";
  const source = el.dataset.componentSource || "";
  const path = getHierarchyPath(el);

  overlayEl.style.left = `${Math.max(0, rect.left)}px`;
  overlayEl.style.top = `${Math.max(0, rect.top)}px`;
  overlayEl.style.width = `${rect.width}px`;
  overlayEl.style.height = `${rect.height}px`;
  overlayEl.hidden = false;

  const part = (cls, text) => Object.assign(document.createElement("span"), { className: cls, textContent: text });
  badgeEl.replaceChildren(part("comp-name", name), part("comp-id", id),
    ...(source ? [part("comp-source", `[${source}]`)] : []), part("comp-copy-hint", "📋 Click badge to copy"));
  badgeEl.title = `Nesting: ${path}\nClick to copy component name & ID`;

  let badgeTop = rect.top - 28;
  if (badgeTop < 10) badgeTop = rect.top + 8;
  let badgeLeft = rect.left + 4;
  if (badgeLeft + 350 > window.innerWidth) badgeLeft = window.innerWidth - 360;

  badgeEl.style.top = `${Math.max(4, badgeTop)}px`;
  badgeEl.style.left = `${Math.max(4, badgeLeft)}px`;
  badgeEl.hidden = false;
}

function hideOverlay() {
  if (overlayEl) overlayEl.hidden = true;
  if (badgeEl) badgeEl.hidden = true;
  currentTarget = null;
}

export function toggleComponentLabeling(forceState = null) {
  isLabelingActive = forceState !== null ? forceState : !isLabelingActive;
  document.body.classList.toggle("component-labeling-active", isLabelingActive);

  const toggleBtn = $("#toggle-component-labels");
  if (toggleBtn) {
    toggleBtn.classList.toggle("active", isLabelingActive);
    toggleBtn.setAttribute("aria-pressed", isLabelingActive ? "true" : "false");
    toggleBtn.textContent = isLabelingActive ? "🏷️ Labels ON" : "🏷️ Labels";
  }

  if (isLabelingActive) {
    createOverlay();
    notice("Component Labeling Mode ON: Hover over UI components to inspect names & IDs. Click badge to copy.");
  } else {
    hideOverlay();
    notice("Component Labeling Mode OFF");
  }
}

export function initComponentLabeling() {
  const toggleBtn = $("#toggle-component-labels");
  if (toggleBtn) {
    toggleBtn.onclick = () => toggleComponentLabeling();
  }

  window.addEventListener("keydown", (e) => {
    // Ctrl+Shift+L or Alt+L toggles labeling mode
    if ((e.ctrlKey && e.shiftKey && (e.key === "L" || e.key === "l")) ||
        (e.altKey && (e.key === "L" || e.key === "l"))) {
      e.preventDefault();
      toggleComponentLabeling();
    } else if (e.key === "Escape" && isLabelingActive) {
      toggleComponentLabeling(false);
    }
  });

  document.addEventListener("mouseover", (e) => {
    if (!isLabelingActive) return;
    const target = e.target.closest("[data-component]");
    if (target) {
      updateOverlay(target);
    }
  });

  window.addEventListener("scroll", () => {
    if (isLabelingActive && currentTarget) {
      updateOverlay(currentTarget);
    }
  }, { passive: true });
}

