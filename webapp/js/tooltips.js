// WCAG 1.4.13 Compliant Studio Tooltip System.

import { $ } from "./core.js";

let activeTooltipTrigger = null;
let tooltipTimeout = null;

const clamp = (value, min, max) => Math.max(min, Math.min(value, max));

export const computeTooltipPosition = (
  rect,
  tipRect,
  viewportWidth,
  viewportHeight,
  gap = 8,
  padding = 10,
  preferredPlacement = "top"
) => {
  const centeredTop = clamp(
    rect.top + (rect.height / 2) - (tipRect.height / 2),
    padding,
    viewportHeight - tipRect.height - padding
  );
  const centeredLeft = clamp(
    rect.left + (rect.width / 2) - (tipRect.width / 2),
    padding,
    viewportWidth - tipRect.width - padding
  );

  if (preferredPlacement === "right") {
    const candidateLeft = rect.right + gap;
    const fitsRight = candidateLeft + tipRect.width <= viewportWidth - padding;
    const flippedLeft = rect.left - tipRect.width - gap;
    const canFlipLeft = !fitsRight && flippedLeft >= padding;
    const left = fitsRight
      ? candidateLeft
      : canFlipLeft
        ? flippedLeft
        : Math.max(padding, viewportWidth - tipRect.width - padding);
    const placement = canFlipLeft ? "left" : "right";
    return { left: Math.round(left), top: Math.round(centeredTop), placement };
  }

  if (preferredPlacement === "left") {
    const candidateLeft = rect.left - tipRect.width - gap;
    const fitsLeft = candidateLeft >= padding;
    const flippedRight = rect.right + gap;
    const canFlipRight = !fitsLeft && flippedRight + tipRect.width <= viewportWidth - padding;
    const left = fitsLeft ? candidateLeft : canFlipRight ? flippedRight : padding;
    const placement = canFlipRight ? "right" : "left";
    return { left: Math.round(left), top: Math.round(centeredTop), placement };
  }

  if (preferredPlacement === "top") {
    const candidateTop = rect.top - tipRect.height - gap;
    const fitsTop = candidateTop >= padding;
    const flippedBottom = rect.bottom + gap;
    const canFlipBottom = !fitsTop && flippedBottom + tipRect.height <= viewportHeight - padding;
    const top = fitsTop ? candidateTop : canFlipBottom ? flippedBottom : Math.max(padding, candidateTop);
    const placement = canFlipBottom ? "bottom" : "top";
    return { left: Math.round(centeredLeft), top: Math.round(top), placement };
  }

  const candidateBottom = rect.bottom + gap;
  const overflowsBottom = candidateBottom + tipRect.height > viewportHeight - padding;
  const top = overflowsBottom
    ? Math.max(padding, rect.top - tipRect.height - gap)
    : candidateBottom;
  const placement = overflowsBottom ? "top" : preferredPlacement;
  return { left: Math.round(centeredLeft), top: Math.round(top), placement };
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
