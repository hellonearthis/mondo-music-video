// Styles, Cast Actors, OAP package inspection/import, and Role Agreements.

import { $, $$, api, handle, json, notice, option, saveDownload, state, text, upload } from "./core.js";
import { scheduleSave } from "./project.js";

// --- Pure Helper & Formatting Functions ---

const escapeHtml = (s = "") =>
  String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");

export function actorOverview(actor) {
  const description = actor.description || "";
  const identity = description.match(
    /(?:^|\n)Identity:\s*([\s\S]*?)(?=\n(?:Hair|Makeup|Wardrobe|Footwear|Accessories|Expression Range|Detail Notes|Canonical Summary|Height):|$)/i
  );
  return identity ? identity[1].trim() : description;
}

export function shortDid(did) {
  return did && did.length > 34 ? did.slice(0, 22) + "…" + did.slice(-8) : did || "none";
}

// --- Pure HTML String Template Generators ---

const styleCardHtml = (style) => {
  const escId = escapeHtml(style.id);
  const escName = escapeHtml(style.name);
  const styleCardFold = style.style_card ? `
    <details class="style-card-fold" style="margin-top:8px;font-size:12px;">
      <summary style="cursor:pointer;color:var(--accent,#d08770);font-weight:600;">View 11-Axis Forensic Card</summary>
      <pre style="white-space:pre-wrap;background:var(--card-bg,#1a1a1a);padding:8px;border-radius:4px;max-height:200px;overflow-y:auto;margin-top:6px;font-family:monospace;">${escapeHtml(style.style_card)}</pre>
    </details>
  ` : "";
  return `
    <article class="card" title="Style card: ${escName}" data-id="${escId}" data-name="${escName}">
      <h2>${escName}</h2>
      <p>${escapeHtml(style.direction)}</p>
      ${styleCardFold}
      <div style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap;">
        <button type="button" class="secondary" data-action="export-style" title="Download ${escName} style JSON">Download JSON</button>
        <button type="button" class="secondary" data-action="duplicate-style" title="Duplicate ${escName} style">Duplicate</button>
        <button type="button" class="quiet operation-action" data-action="delete-style" title="Delete ${escName} from this machine">Delete style</button>
      </div>
    </article>
  `;
};

const actorCardHtml = (actor) => {
  const escId = escapeHtml(actor.id);
  const escName = escapeHtml(actor.name);
  const overview = escapeHtml(actorOverview(actor));
  const oapNote = actor.oap ? "OAP imported · original package preserved" : "OAP ready · signed on export";
  const auditionSection = actor.oap ? "" : `
    <label class="check audition-export" title="Only check this if the reference is a cleaned or watermarked take you are willing to share with casting directors">
      <input type="checkbox" class="audition-cleared-cb"> Reference is cleared for auditions
    </label>
    <button type="button" class="quiet audition-button" data-action="export-audition" title="Export a signed audition package for ${escName}; cast-only assets are listed by hash but left out">Export audition package</button>
  `;
  return `
    <article class="card" title="Cast member: ${escName}" data-id="${escId}" data-name="${escName}">
      <img src="/api/actors/${encodeURIComponent(actor.id)}/reference" alt="${escName} reference" loading="lazy" data-tooltip="Reference portrait for ${escName}" title="Reference portrait for ${escName}">
      <h2>${escName}</h2>
      <p>${overview}</p>
      <p>${oapNote}</p>
      <button type="button" class="secondary" data-action="export-oap" title="Export signed OAP package for ${escName}">Export OAP package</button>
      ${auditionSection}
      <button type="button" class="quiet operation-action" data-action="delete-actor" title="Delete ${escName} from this machine">Delete actor</button>
    </article>
  `;
};

const agreementCardHtml = (agreement) => {
  const escId = escapeHtml(agreement.id);
  const escTitle = escapeHtml(agreement.title || agreement.id);
  if (agreement.damaged) {
    return `
      <article class="card" title="Role agreement ${escId}" data-id="${escId}">
        <span class="oap-badge-pill badge-invalid">Damaged record</span>
        <h3>${escId}</h3>
        <p>${escapeHtml(agreement.issues.join("; "))}</p>
      </article>
    `;
  }
  const status = agreement.complete ? ["Signed by both parties", "badge-valid"]
    : agreement.issues.length && agreement.signed.length ? ["Signature problem", "badge-invalid"]
    : agreement.signed.length ? [`Signed by ${agreement.signed.join(" and ")}; awaiting countersignature`, "badge-unsigned"]
    : ["Unsigned draft", "badge-unsigned"];
  const compensation = agreement.compensation || {};
  const issuesHtml = (agreement.issues.length && agreement.signed.length)
    ? `<p>${escapeHtml(agreement.issues.join("; "))}</p>`
    : "";
  const roles = ["director", ...(agreement.local_agent ? ["agent"] : [])].filter(role => !agreement.signed.includes(role));
  const signButtonsHtml = roles.map(role => `
    <button type="button" class="secondary operation-action" data-action="sign-agreement" data-role="${escapeHtml(role)}" data-title="${escTitle}" data-amount="${escapeHtml(String(compensation.amount || ''))}" data-currency="${escapeHtml(String(compensation.currency || ''))}" title="Sign this agreement with this studio's ${role} key">Sign as ${escapeHtml(role)}</button>
  `).join("");
  return `
    <article class="card" title="Role agreement ${escId}" data-id="${escId}">
      <span class="oap-badge-pill ${status[1]}">${escapeHtml(status[0])}</span>
      <h3>${escTitle}</h3>
      <p>${escapeHtml(agreement.character || "Role")} · actor ${escapeHtml(agreement.actor_id || "unknown")} · ${escapeHtml(String(compensation.amount || ""))} ${escapeHtml(String(compensation.currency || ""))}</p>
      <p title="${escapeHtml(agreement.agent_did || '')}">Agent ${escapeHtml(shortDid(agreement.agent_did))}${agreement.local_agent ? " (this studio)" : ""}</p>
      <p title="${escapeHtml(agreement.director_did || '')}">Director ${escapeHtml(shortDid(agreement.director_did))} (this studio)</p>
      ${issuesHtml}
      <div class="agreement-actions">
        ${signButtonsHtml}
        <button type="button" class="secondary" data-action="verify-agreement" title="Check both signatures and the exact manifest and casting call bindings">Verify</button>
        <button type="button" class="secondary" data-action="download-bundle" title="Zip of agreement.json, manifest.json and casting_call.json for the other party">Download bundle</button>
      </div>
    </article>
  `;
};

// --- DOM Population & Renderers ---

export async function loadStyles() {
  const styles = await (await api("/api/styles")).json();
  state.styles = styles;
  $$(".style-select").forEach((select) => {
    const old = select.value;
    select.replaceChildren(...styles.map((style) => option(style.id, style.name, `${style.name} (${style.id})`)));
    if (!styles.length) {
      const empty = option("", "No styles yet — add one in Styles");
      empty.disabled = true;
      select.replaceChildren(empty);
    }
    if (styles.some((x) => x.id === old)) select.value = old;
  });

  const listEl = $("#style-list");
  if (!listEl) return;
  listEl.innerHTML = styles.map(styleCardHtml).join("");
}

export async function loadActors() {
  const actors = await (await api("/api/actors")).json();
  $$(".actor-select").forEach((select) => {
    const old = [...select.selectedOptions].map((x) => x.value);
    if (!actors.length) {
      const emptyOpt = option("", "No cast members yet — add in 02. Actors & OAP", "No cast members currently in your studio library");
      emptyOpt.disabled = true;
      select.replaceChildren(emptyOpt);
    } else {
      select.replaceChildren(
        ...actors.map((actor) => {
          const node = option(actor.id, actor.name, `Cast actor: ${actor.name} (${actor.id})`);
          node.selected = old.includes(actor.id);
          return node;
        })
      );
    }
  });

  const listEl = $("#actor-list");
  if (!listEl) return;
  if (!actors.length) {
    listEl.innerHTML = '<div class="empty" title="No actors currently in your studio library">Your cast starts here. Create an actor or import a full OAP package below.</div>';
  } else {
    listEl.innerHTML = actors.map(actorCardHtml).join("");
  }

  const agreementActor = $("#agreement-form")?.elements?.actor_id;
  if (agreementActor) {
    const chosen = agreementActor.value;
    agreementActor.replaceChildren(...actors.map((actor) => option(actor.id, actor.name)));
    if (actors.some((actor) => actor.id === chosen)) agreementActor.value = chosen;
  }
}

export async function loadAgreements() {
  const agreements = await (await api("/api/agreements")).json();
  const listEl = $("#agreement-list");
  if (!listEl) return;
  if (!agreements.length) {
    listEl.innerHTML = '<div class="empty">No role agreements yet. Draft one below.</div>';
  } else {
    listEl.innerHTML = agreements.map(agreementCardHtml).join("");
  }
}

export function renderOapReportCard(report, allowUnsigned) {
  const card = $("#oap-report-card");
  if (!card) return;
  const manifest = report.manifest || {};
  const verification = report.verification || {};
  const identity = manifest.identity || {};
  const rider = manifest.rider || {};
  const signed = Boolean(verification.signature_valid);
  const valid = Boolean(verification.ok);

  const displayName = identity.display_name || identity.actor_id || "Actor";
  const badgeText = signed && valid
    ? (verification.agent_known ? "Signature valid · known signer" : "Signature valid · signer not locally trusted")
    : (valid && allowUnsigned ? "Unsigned package · explicitly allowed" : "Verification warning");
  const badgeClass = signed && valid ? "badge-valid" : "badge-unsigned";

  const ratings = rider.content && typeof rider.content === "object"
    ? Object.entries(rider.content).map(([k, v]) => `${k}: ${v}`).join(", ")
    : "Not specified in package";

  const rows = [
    ["Actor ID", identity.actor_id || "Not specified"],
    ["Display name", identity.display_name || "Not specified"],
    ["Signing public key", signed ? (manifest.agent?.public_key || "Not supplied") : "Unsigned"],
    ["Visual identity", manifest.visual?.core_identity || "Not specified"],
    ["Ratings ceiling", ratings],
    ["Commercial rider", rider.commercial ? JSON.stringify(rider.commercial, null, 2) : "Not specified in package"]
  ];

  const gridHtml = rows
    .map(([lbl, val]) => `<div class="oap-report-label">${escapeHtml(lbl)}:</div><div class="oap-report-value">${escapeHtml(String(val))}</div>`)
    .join("");

  card.innerHTML = `
    <div class="oap-report-header">
      <div class="oap-report-title">Package: ${escapeHtml(displayName)}</div>
      <span class="oap-badge-pill ${badgeClass}">${escapeHtml(badgeText)}</span>
    </div>
    <div class="oap-report-grid">${gridHtml}</div>
  `;
  card.hidden = false;
  if ($("#oap-raw-toggle-wrap")) $("#oap-raw-toggle-wrap").hidden = false;
}

// --- Delegated Action Listeners & Form Submissions ---

export function initLibraryForms() {
  // Delegated handler for Style cards
  $("#style-list")?.addEventListener("click", handle(async (e) => {
    const btn = e.target.closest("button[data-action]");
    if (!btn) return;
    const card = btn.closest("article[data-id]");
    const { id, name } = card.dataset;
    const action = btn.dataset.action;

    if (action === "delete-style") {
      if (!window.confirm(`Delete style “${name}” from this machine? Completed videos are kept.`)) return;
      await api(`/api/styles/${encodeURIComponent(id)}`, { method: "DELETE" });
      await loadStyles();
      scheduleSave();
      notice("Style deleted from your local collection.");
    } else if (action === "export-style") {
      await saveDownload(await api(`/api/styles/${encodeURIComponent(id)}/export`), `${id}.json`);
      notice(`Exported style “${name}” as ${id}.json`);
    } else if (action === "duplicate-style") {
      const existing = (state.styles || []).find((s) => s.id === id);
      const form = $("#style-form");
      if (form && existing) {
        form.elements.id.value = `${existing.id}_copy`.slice(0, 64);
        form.elements.name.value = `${existing.name} (Copy)`.slice(0, 160);
        form.elements.direction.value = existing.direction || "";
        form.scrollIntoView({ behavior: "smooth" });
        form.elements.name.focus();
        notice(`Duplicating “${name}”. Edit fields and save.`);
      }
    }
  }));

  // Delegated handler for Actor cards
  $("#actor-list")?.addEventListener("click", handle(async (e) => {
    const btn = e.target.closest("button[data-action]");
    if (!btn) return;
    const card = btn.closest("article[data-id]");
    const { id, name } = card.dataset;
    const action = btn.dataset.action;

    if (action === "export-oap") {
      await saveDownload(await api(`/api/actors/${encodeURIComponent(id)}/export`, { method: "POST" }), id + ".oap");
    } else if (action === "export-audition") {
      const clearedCb = card.querySelector(".audition-cleared-cb");
      const isCleared = Boolean(clearedCb?.checked);
      const query = new URLSearchParams({ tier: "audition", reference_clearance: isCleared ? "audition" : "cast" });
      await saveDownload(await api(`/api/actors/${encodeURIComponent(id)}/export?${query}`, { method: "POST" }), id + "-audition.oap");
      notice(isCleared ? "Audition package exported with the audition-cleared reference." : "Audition package exported. The cast-only reference is listed by hash but not included.");
    } else if (action === "delete-actor") {
      if (!window.confirm(`Delete actor “${name}”, their reference image and imported package from this machine? Export first if you want a backup. Completed videos and earlier exports are kept.`)) return;
      await api(`/api/actors/${encodeURIComponent(id)}`, { method: "DELETE" });
      await loadActors();
      scheduleSave();
      notice("Actor deleted from your local cast.");
    }
  }));

  // Delegated handler for Agreement cards
  $("#agreement-list")?.addEventListener("click", handle(async (e) => {
    const btn = e.target.closest("button[data-action]");
    if (!btn) return;
    const card = btn.closest("article[data-id]");
    const { id } = card.dataset;
    const action = btn.dataset.action;
    const path = `/api/agreements/${encodeURIComponent(id)}`;

    if (action === "sign-agreement") {
      const { role, title, amount, currency } = btn.dataset;
      if (!window.confirm(`Sign “${title}” as ${role}? This commits the ${role} to ${amount} ${currency} and the casting call terms. Signatures cannot be withdrawn from copies already shared.`)) return;
      await json(`${path}/sign`, { role });
      await loadAgreements();
      notice(`Signed as ${role}.`);
    } else if (action === "verify-agreement") {
      const result = await (await api(`${path}/verify`)).json();
      notice(result.ok ? `Verified: both signatures are valid. ${result.note}` : `Not complete: ${result.issues.join("; ")}`);
    } else if (action === "download-bundle") {
      await saveDownload(await api(`${path}/bundle`, { method: "POST" }), id + "-agreement.zip");
    }
  }));

  $("#actor-form").onsubmit = handle(async (event) => {
    await api("/api/actors", { method: "POST", body: new FormData(event.target) });
    event.target.reset();
    await loadActors();
    scheduleSave();
  });

  $("#style-form").onsubmit = handle(async (event) => {
    await json("/api/styles", Object.fromEntries(new FormData(event.target)));
    event.target.reset();
    await loadStyles();
    scheduleSave();
  });

  $("#import-style-btn")?.addEventListener("click", handle(async () => {
    const file = $("#style-import-file")?.files?.[0];
    if (!file) throw new Error("Choose a style .json file first");
    const overwrite = Boolean($("#style-import-overwrite")?.checked);

    let parsed;
    try {
      const textContent = await file.text();
      parsed = JSON.parse(textContent);
    } catch (err) {
      throw new Error(`Invalid JSON file: ${err.message}`);
    }

    if (!parsed || typeof parsed !== "object") {
      throw new Error("Invalid style format: Root must be a JSON object");
    }

    const payload = {
      id: String(parsed.id || "").trim(),
      name: String(parsed.name || "").trim(),
      direction: String(parsed.direction || "").trim(),
      overwrite,
    };
    if (parsed.style_card) {
      payload.style_card = String(parsed.style_card);
    }

    if (!payload.id) throw new Error("Style JSON must include an 'id'");
    if (!payload.name) throw new Error("Style JSON must include a 'name'");
    if (!payload.direction) throw new Error("Style JSON must include 'direction'");

    const result = await json("/api/styles/import", payload);
    $("#style-import-file").value = "";
    $("#style-import-overwrite").checked = false;
    await loadStyles();
    scheduleSave();
    notice(`Style “${result.name}” (${result.id}) successfully imported.`);
  }));

  $("#oap-file").addEventListener("change", () => {
    state.currentOap = undefined;
    $("#oap-import-form").hidden = true;
    $("#oap-report-card").hidden = true;
    $("#oap-raw-toggle-wrap").hidden = true;
    $("#oap-report").hidden = true;
  });

  $("#inspect-oap").onclick = handle(async () => {
    const file = $("#oap-file").files[0];
    if (!file) throw new Error("Choose an OAP package first");
    $("#oap-import-form").hidden = true;
    $("#oap-import-form").elements.accept_unknown.checked = false;
    $("#oap-report-card").hidden = true;
    $("#oap-raw-toggle-wrap").hidden = true;
    $("#oap-report").hidden = true;
    $("#toggle-raw-oap").textContent = "Show raw manifest JSON";
    state.currentOap = await upload(file, "oap");
    const allowUnsigned = $("#allow-unsigned").checked;
    const report = await (await api(`/api/oap/inspect/${state.currentOap}?allow_unsigned=${allowUnsigned}`)).json();
    $("#oap-report").textContent = JSON.stringify(report, null, 2);
    renderOapReportCard(report, allowUnsigned);
    $("#oap-import-form").hidden = false;
  });

  $("#oap-import-form").onsubmit = handle(async (event) => {
    const body = new FormData(event.target);
    body.set("filename", state.currentOap);
    body.set("allow_unsigned", String($("#allow-unsigned").checked));
    body.set("accept_unknown", String(event.target.elements.accept_unknown.checked));
    await api("/api/oap/import", { method: "POST", body });
    event.target.hidden = true;
    $("#oap-report").hidden = true;
    if ($("#oap-report-card")) $("#oap-report-card").hidden = true;
    if ($("#oap-raw-toggle-wrap")) $("#oap-raw-toggle-wrap").hidden = true;
    notice("Actor successfully imported into your studio cast library.");
    await loadActors();
  });

  $("#agreement-form").onsubmit = handle(async (event) => {
    const values = Object.fromEntries(new FormData(event.target));
    const body = { content: {} };
    for (const [key, value] of Object.entries(values)) {
      if (key.startsWith("content_")) body.content[key.slice(8)] = value;
      else body[key] = value;
    }
    await json("/api/agreements", body);
    event.target.elements.agreement_id.value = "";
    await loadAgreements();
    notice("Agreement drafted. Sign as Director, then send the bundle to the Agent to countersign.");
  });

  $("#import-agreement").onclick = handle(async () => {
    const file = $("#agreement-file").files[0];
    if (!file) throw new Error("Choose a signed agreement.json first");
    const body = new FormData();
    body.set("filename", await upload(file, "agreement"));
    const result = await (await api("/api/agreements/import", { method: "POST", body })).json();
    $("#agreement-file").value = "";
    await loadAgreements();
    notice(result.complete
      ? "Countersigned agreement imported; both signatures verify."
      : "Signatures imported; the agreement is not yet signed by both parties.");
  });
}
