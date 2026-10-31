// The production queue: line up whole productions and run them one at a time.

import { $, api, handle, json, notice, state, text } from "./core.js";

const STATE_LABELS = {
  pending: "Waiting", running: "Running", complete: "Finished", failed: "Failed",
  cancelled: "Cancelled", interrupted: "Interrupted", held: "Held, nothing spent"
};
const STOPPED = ["failed", "cancelled", "interrupted", "held"];
const QUEUEABLE = ["video", "ident"];

const button = (label, className, action) => {
  const node = text("button", label, className);
  node.type = "button";
  node.onclick = handle(action);
  return node;
};

const ticketNote = ticket => [
  ticket.kind === "ident" ? "Ident" : "Music video",
  ticket.estimate_usd > 0 ? `approved estimate $${Number(ticket.estimate_usd).toFixed(2)}` : "local, free",
  ticket.message
].filter(Boolean).join(" · ");

async function addFromQuote(quote, { consent, replaces }) {
  await json("/api/queue", { quote_id: quote.id, consent, replaces: replaces || null });
  await loadQueue();
}

async function retryTicket(ticket) {
  const quote = await json(`/api/queue/${ticket.id}/preview`, {});
  if (!(quote.estimate_usd > 0)) return addFromQuote(quote, { consent: false, replaces: ticket.id });
  // A priced plan is reviewed in full, in the same dialog as any other, before it can be accepted.
  const { showQuote } = await import("./production.js");
  state.lastRequest = quote.request;
  showQuote(quote.request, quote);
  state.queueReplaces = ticket.id;
  $("#start-production").hidden = true;
}

function ticketActions(ticket) {
  const actions = [];
  if (ticket.state === "pending") {
    actions.push(button("▲", "quiet", () => move(ticket.id, -1)), button("▼", "quiet", () => move(ticket.id, 1)));
  }
  if (ticket.resumable) {
    actions.push(button("Resume", "secondary", async () => renderQueue(await json(`/api/queue/${ticket.id}/resume`, {}))));
  }
  if (STOPPED.includes(ticket.state)) actions.push(button("Queue again", "secondary", () => retryTicket(ticket)));
  if (ticket.state !== "running") {
    actions.push(button("Remove", "quiet", async () => {
      await api(`/api/queue/${ticket.id}`, { method: "DELETE" });
      await loadQueue();
    }));
  }
  return actions;
}

async function move(id, delta) {
  renderQueue(await json(`/api/queue/${id}/move`, { delta }));
}

function renderTicket(ticket) {
  const item = document.createElement("li");
  item.className = "queue-ticket";
  item.dataset.state = ticket.state;
  const about = document.createElement("div");
  about.append(text("div", `${ticket.label} — ${STATE_LABELS[ticket.state] || ticket.state}`, "queue-ticket-title"),
    text("div", ticketNote(ticket), "queue-ticket-note"));
  const actions = document.createElement("div");
  actions.className = "queue-ticket-actions";
  actions.append(...ticketActions(ticket));
  item.append(about, actions);
  return item;
}

export function renderQueue(queue) {
  const list = $("#queue-list");
  if (!list) return;
  // Status events arrive often: leave the list alone unless it changed, so a button is never redrawn under the pointer.
  const signature = JSON.stringify(queue);
  if (list.dataset.signature === signature) return;
  list.dataset.signature = signature;
  list.replaceChildren(...queue.tickets.map(renderTicket));
  $("#queue-state").textContent = queue.running ? `Queue on · ${queue.waiting} waiting`
    : queue.waiting ? `Paused · ${queue.waiting} waiting` : "Nothing waiting";
  $("#queue-start").disabled = queue.running || !queue.waiting;
  $("#queue-pause").disabled = !queue.running;
}

export async function loadQueue() {
  renderQueue(await (await api("/api/queue")).json());
}

export function syncQueueButton(request, quote) {
  const add = $("#add-to-queue");
  if (add) add.hidden = !QUEUEABLE.includes(request.kind);
}

export function initQueue() {
  // A held or failed ticket changes nothing else on the page, so an open Queue tab keeps itself current.
  setInterval(() => { if (!$("#panel-queue").hidden) loadQueue().catch(() => {}); }, 4000);
  $("#preview-dialog").addEventListener("close", () => {
    state.queueReplaces = null;
    $("#start-production").hidden = false;
  });
  $("#queue-start").onclick = handle(async () => renderQueue(await json("/api/queue/start", {})));
  $("#queue-pause").onclick = handle(async () => renderQueue(await json("/api/queue/pause", {})));
  $("#queue-clear").onclick = handle(async () => renderQueue(await json("/api/queue/clear-finished", {})));
  $("#add-to-queue").onclick = handle(async () => {
    const quote = state.currentQuote;
    if (quote.estimate_usd > 0 && !$("#consent").checked) throw new Error("Accept the estimated charges before queueing this");
    await addFromQuote(quote, { consent: $("#consent").checked, replaces: state.queueReplaces });
    $("#preview-dialog").close();
    notice("Added to the queue. Open Queue to start it.");
  });
}
