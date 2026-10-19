// WCAG 1.4.13 Compliant Studio Tooltip System.

import { $ } from "./core.js";

let activeTooltipTrigger = null;
let tooltipTimeout = null;

export function showTooltip(target) {
  if (!target) return;
  const tipText = target.dataset.tooltip || target.getAttribute("title");
  if (!tipText) return;

  if (target.hasAttribute("title")) {
    target.dataset.tooltip = target.getAttribute("title");
    target.removeAttribute("title");
  }

  activeTooltipTrigger = target;
  target.setAttribute("aria-describedby", "studio-tooltip");
  const tip = $("#studio-tooltip");
  if (!tip) return;
  tip.textContent = tipText;
  tip.hidden = false;

  const rect = target.getBoundingClientRect();
  const tipRect = tip.getBoundingClientRect();
  const gap = 8;
  const padding = 10;

  let left = rect.left + (rect.width / 2) - (tipRect.width / 2);
  left = Math.max(padding, Math.min(left, window.innerWidth - tipRect.width - padding));

  let top = rect.bottom + gap;
  if (top + tipRect.height > window.innerHeight - padding) {
    top = Math.max(padding, rect.top - tipRect.height - gap);
  }

  tip.style.left = `${Math.round(left)}px`;
  tip.style.top = `${Math.round(top)}px`;
}

export function hideTooltip(immediate = false) {
  clearTimeout(tooltipTimeout);
  const doHide = () => {
    const tip = $("#studio-tooltip");
    if (tip) tip.hidden = true;
    if (activeTooltipTrigger) {
      activeTooltipTrigger.removeAttribute("aria-describedby");
      if (activeTooltipTrigger.dataset.tooltip) {
        activeTooltipTrigger.setAttribute("title", activeTooltipTrigger.dataset.tooltip);
      }
      activeTooltipTrigger = null;
    }
  };
  if (immediate) doHide();
  else tooltipTimeout = setTimeout(doHide, 120);
}

export function initTooltips() {
  const tip = $("#studio-tooltip");
  if (tip) {
    tip.onpointerenter = () => clearTimeout(tooltipTimeout);
    tip.onpointerleave = () => hideTooltip(false);
  }

  document.addEventListener("pointerover", event => {
    const target = event.target.closest("[data-tooltip], [title]");
    if (target && !target.closest("#studio-tooltip")) {
      clearTimeout(tooltipTimeout);
      showTooltip(target);
    }
  }, true);

  document.addEventListener("pointerout", event => {
    const target = event.target.closest("[data-tooltip], [title]");
    if (target) hideTooltip(false);
  }, true);

  document.addEventListener("focusin", event => {
    const target = event.target.closest("[data-tooltip], [title]");
    if (target) {
      clearTimeout(tooltipTimeout);
      showTooltip(target);
    }
  }, true);

  document.addEventListener("focusout", event => {
    const target = event.target.closest("[data-tooltip], [title]");
    if (target) hideTooltip(true);
  }, true);

  document.addEventListener("keydown", event => {
    if (event.key === "Escape") hideTooltip(true);
  });
}

