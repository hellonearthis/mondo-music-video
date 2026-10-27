// WCAG 1.4.13 Compliant Studio Tooltip System.

import { $ } from "./core.js";

let activeTooltipTrigger = null;
let tooltipTimeout = null;

export const computeTooltipPosition = (
  rect,
  tipRect,
  viewportWidth,
  viewportHeight,
  gap = 8,
  padding = 10,
  preferredPlacement = "top"
) => {
  let left;
  let top;
  let placement = preferredPlacement;

  if (preferredPlacement === "right") {
    left = rect.right + gap;
    top = rect.top + (rect.height / 2) - (tipRect.height / 2);
    // If overflowing right viewport boundary, flip to left if space permits, else clamp
    if (left + tipRect.width > viewportWidth - padding) {
      const leftPos = rect.left - tipRect.width - gap;
      if (leftPos >= padding) {
        left = leftPos;
        placement = "left";
      } else {
        left = Math.max(padding, viewportWidth - tipRect.width - padding);
      }
    }
    top = Math.max(padding, Math.min(top, viewportHeight - tipRect.height - padding));
  } else if (preferredPlacement === "left") {
    left = rect.left - tipRect.width - gap;
    top = rect.top + (rect.height / 2) - (tipRect.height / 2);
    if (left < padding) {
      const rightPos = rect.right + gap;
      if (rightPos + tipRect.width <= viewportWidth - padding) {
        left = rightPos;
        placement = "right";
      } else {
        left = padding;
      }
    }
    top = Math.max(padding, Math.min(top, viewportHeight - tipRect.height - padding));
  } else if (preferredPlacement === "top") {
    left = rect.left + (rect.width / 2) - (tipRect.width / 2);
    left = Math.max(padding, Math.min(left, viewportWidth - tipRect.width - padding));
    top = rect.top - tipRect.height - gap;
    if (top < padding) {
      const bottomPos = rect.bottom + gap;
      if (bottomPos + tipRect.height <= viewportHeight - padding) {
        top = bottomPos;
        placement = "bottom";
      } else {
        top = Math.max(padding, top);
      }
    }
  } else {
    left = rect.left + (rect.width / 2) - (tipRect.width / 2);
    left = Math.max(padding, Math.min(left, viewportWidth - tipRect.width - padding));
    top = rect.bottom + gap;
    if (top + tipRect.height > viewportHeight - padding) {
      top = Math.max(padding, rect.top - tipRect.height - gap);
      placement = "top";
    }
  }

  return { left: Math.round(left), top: Math.round(top), placement };
};

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
  if (target.dataset.tooltipImage) {
    const img = document.createElement("img");
    img.className = "tooltip-thumb";
    img.src = target.dataset.tooltipImage;
    img.alt = "";
    img.loading = "eager";
    tip.appendChild(img);
  }
  if (target.dataset.tooltipFooter) {
    const footer = document.createElement("div");
    footer.className = "tooltip-footer";
    footer.textContent = target.dataset.tooltipFooter;
    tip.appendChild(footer);
  }
  tip.hidden = false;

  const rect = target.getBoundingClientRect();
  const tipRect = tip.getBoundingClientRect();
  const preferredPlacement =
    target.dataset.tooltipPosition ||
    target.dataset.placement ||
    (target.closest("aside") ? "right" : null) ||
    target.closest("[data-tooltip-position]")?.dataset.tooltipPosition ||
    "top";
  const pos = computeTooltipPosition(
    rect,
    tipRect,
    window.innerWidth,
    window.innerHeight,
    8,
    10,
    preferredPlacement
  );

  tip.dataset.placement = pos.placement;
  tip.style.left = `${pos.left}px`;
  tip.style.top = `${pos.top}px`;
}

export function hideTooltip(immediate = false) {
  clearTimeout(tooltipTimeout);
  const doHide = () => {
    const tip = $("#studio-tooltip");
    if (tip) tip.hidden = true;
    if (activeTooltipTrigger) {
      activeTooltipTrigger.removeAttribute("aria-describedby");
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

