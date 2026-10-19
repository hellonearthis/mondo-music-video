// Styles, Cast Actors, OAP package inspection/import, and Role Agreements.

import { $, $$, api, handle, json, notice, option, saveDownload, state, text, upload } from "./core.js";
import { scheduleSave } from "./project.js";

export async function loadStyles() {
  const styles = await (await api("/api/styles")).json();
  $$(".style-select").forEach(select => {
    const old = select.value;
    select.replaceChildren(...styles.map(style => option(style.id, style.name, `${style.name} (${style.id})`)));
    if (!styles.length) {
      const empty = option("", "No styles yet — add one in Styles");
      empty.disabled = true;
      select.replaceChildren(empty);
    }
    if (styles.some(x => x.id === old)) select.value = old;
  });
  $("#style-list").replaceChildren(...styles.map(style => {
    const card = text("article", "", "card", `Style card: ${style.name}`);
    card.append(text("h2", style.name), text("p", style.direction));
    const remove = text("button", "Delete style", "quiet operation-action", `Delete ${style.name} from this machine`);
    remove.type = "button";
    remove.onclick = handle(async () => {
      if (!window.confirm(`Delete style “${style.name}” from this machine? Completed videos are kept.`)) return;
      await api(`/api/styles/${encodeURIComponent(style.id)}`, { method: "DELETE" });
      await loadStyles();
      scheduleSave();
      notice("Style deleted from your local collection.");
    });
    card.append(remove);
    return card;
  }));
}

export function actorOverview(actor) {
  const description = actor.description || "";
  const identity = description.match(/(?:^|\n)Identity:\s*([\s\S]*?)(?=\n(?:Hair|Makeup|Wardrobe|Footwear|Accessories|Expression Range|Detail Notes|Canonical Summary|Height):|$)/i);
  return identity ? identity[1].trim() : description;
}

export async function loadActors() {
  const actors = await (await api("/api/actors")).json();
  $$(".actor-select").forEach(select => {
    const old = [...select.selectedOptions].map(x => x.value);
    if (!actors.length) {
      const emptyOpt = option("", "No cast members yet — add in 02. Actors & OAP", "No cast members currently in your studio library");
      emptyOpt.disabled = true;
      select.replaceChildren(emptyOpt);
    } else {
      select.replaceChildren(...actors.map(actor => {
        const node = option(actor.id, actor.name, `Cast actor: ${actor.name} (${actor.id})`);
        node.selected = old.includes(actor.id);
        return node;
      }));
    }
  });
  $("#actor-list").replaceChildren(...actors.map(actor => {
    const card = text("article", "", "card", `Cast member: ${actor.name}`);
    const image = document.createElement("img");
    image.src = `/api/actors/${encodeURIComponent(actor.id)}/reference`;
    image.alt = actor.name + " reference";
    image.loading = "lazy";
    image.dataset.tooltip = `Reference portrait for ${actor.name}`;
    image.title = image.dataset.tooltip;

    const button = text("button", "Export OAP package", "secondary", `Export signed OAP package for ${actor.name}`);
    button.onclick = handle(async () => {
      await saveDownload(await api(`/api/actors/${encodeURIComponent(actor.id)}/export`, { method: "POST" }), actor.id + ".oap");
    });
    card.append(
      image,
      text("h2", actor.name),
      text("p", actorOverview(actor)),
      text("p", actor.oap ? "OAP imported · original package preserved" : "OAP ready · signed on export"),
      button
    );
    if (!actor.oap) {
      const cleared = document.createElement("input");
      cleared.type = "checkbox";
      const clearedLabel = text("label", "", "check audition-export", "Only check this if the reference is a cleaned or watermarked take you are willing to share with casting directors");
      clearedLabel.append(cleared, " Reference is cleared for auditions");
      const audition = text("button", "Export audition package", "quiet audition-button", `Export a signed audition package for ${actor.name}; cast-only assets are listed by hash but left out`);
      audition.type = "button";
      audition.onclick = handle(async () => {
        const query = new URLSearchParams({ tier: "audition", reference_clearance: cleared.checked ? "audition" : "cast" });
        await saveDownload(await api(`/api/actors/${encodeURIComponent(actor.id)}/export?${query}`, { method: "POST" }), actor.id + "-audition.oap");
        notice(cleared.checked ? "Audition package exported with the audition-cleared reference." : "Audition package exported. The cast-only reference is listed by hash but not included.");
      });
      card.append(clearedLabel, audition);
    }
    const remove = text("button", "Delete actor", "quiet operation-action", `Delete ${actor.name} from this machine`);
    remove.type = "button";
    remove.onclick = handle(async () => {
      if (!window.confirm(`Delete actor “${actor.name}”, their reference image and imported package from this machine? Export first if you want a backup. Completed videos and earlier exports are kept.`)) return;
      await api(`/api/actors/${encodeURIComponent(actor.id)}`, { method: "DELETE" });
      await loadActors();
      scheduleSave();
      notice("Actor deleted from your local cast.");
    });
    card.append(remove);
    return card;
  }));
  if (!actors.length) $("#actor-list").append(text("div", "Your cast starts here. Create an actor or import a full OAP package below.", "empty", "No actors currently in your studio library"));
  const agreementActor = $("#agreement-form").elements.actor_id;
  const chosen = agreementActor.value;
  agreementActor.replaceChildren(...actors.map(actor => option(actor.id, actor.name)));
  if (actors.some(actor => actor.id === chosen)) agreementActor.value = chosen;
}

export function shortDid(did) {
  return did && did.length > 34 ? did.slice(0, 22) + "…" + did.slice(-8) : did || "none";
}

export async function loadAgreements() {
  const agreements = await (await api("/api/agreements")).json();
  $("#agreement-list").replaceChildren(...agreements.map(agreement => {
    const card = text("article", "", "card", `Role agreement ${agreement.id}`);
    if (agreement.damaged) {
      card.append(text("span", "Damaged record", "oap-badge-pill badge-invalid"), text("h3", agreement.id), text("p", agreement.issues.join("; ")));
      return card;
    }
    const status = agreement.complete ? ["Signed by both parties", "badge-valid"]
      : agreement.issues.length && agreement.signed.length ? ["Signature problem", "badge-invalid"]
      : agreement.signed.length ? [`Signed by ${agreement.signed.join(" and ")}; awaiting countersignature`, "badge-unsigned"]
      : ["Unsigned draft", "badge-unsigned"];
    const compensation = agreement.compensation || {};
    card.append(
      text("span", status[0], "oap-badge-pill " + status[1]),
      text("h3", agreement.title || agreement.id),
      text("p", `${agreement.character || "Role"} · actor ${agreement.actor_id || "unknown"} · ${compensation.amount} ${compensation.currency}`),
      text("p", `Agent ${shortDid(agreement.agent_did)}${agreement.local_agent ? " (this studio)" : ""}`, "", agreement.agent_did),
      text("p", `Director ${shortDid(agreement.director_did)} (this studio)`, "", agreement.director_did)
    );
    if (agreement.issues.length && agreement.signed.length) card.append(text("p", agreement.issues.join("; ")));
    const actions = text("div", "", "agreement-actions");
    const path = `/api/agreements/${encodeURIComponent(agreement.id)}`;
    const roles = ["director", ...(agreement.local_agent ? ["agent"] : [])].filter(role => !agreement.signed.includes(role));
    for (const role of roles) {
      const sign = text("button", `Sign as ${role}`, "secondary operation-action", `Sign this agreement with this studio's ${role} key`);
      sign.type = "button";
      sign.onclick = handle(async () => {
        if (!window.confirm(`Sign “${agreement.title}” as ${role}? This commits the ${role} to ${compensation.amount} ${compensation.currency} and the casting call terms. Signatures cannot be withdrawn from copies already shared.`)) return;
        await json(`${path}/sign`, { role });
        await loadAgreements();
        notice(`Signed as ${role}.`);
      });
      actions.append(sign);
    }
    const verify = text("button", "Verify", "secondary", "Check both signatures and the exact manifest and casting call bindings");
    verify.type = "button";
    verify.onclick = handle(async () => {
      const result = await (await api(`${path}/verify`)).json();
      notice(result.ok ? `Verified: both signatures are valid. ${result.note}` : `Not complete: ${result.issues.join("; ")}`);
    });
    const download = text("button", "Download bundle", "secondary", "Zip of agreement.json, manifest.json and casting_call.json for the other party");
    download.type = "button";
    download.onclick = handle(async () => saveDownload(await api(`${path}/bundle`, { method: "POST" }), agreement.id + "-agreement.zip"));
    actions.append(verify, download);
    card.append(actions);
    return card;
  }));
  if (!agreements.length) $("#agreement-list").append(text("div", "No role agreements yet. Draft one below.", "empty"));
}

export function renderOapReportCard(report, allowUnsigned) {
  const card = $("#oap-report-card");
  if (!card) return;
  const manifest = report.manifest || {}, verification = report.verification || {};
  const identity = manifest.identity || {}, rider = manifest.rider || {};
  const signed = Boolean(verification.signature_valid);
  const valid = Boolean(verification.ok);
  const header = text("div", "", "oap-report-header");
  header.append(text("div", "Package: " + (identity.display_name || identity.actor_id || "Actor"), "oap-report-title"));
  const badge = signed && valid
    ? (verification.agent_known ? "Signature valid · known signer" : "Signature valid · signer not locally trusted")
    : (valid && allowUnsigned ? "Unsigned package · explicitly allowed" : "Verification warning");
  header.append(text("span", badge, "oap-badge-pill " + (signed && valid ? "badge-valid" : "badge-unsigned")));
  const grid = text("div", "", "oap-report-grid");
  const ratings = rider.content && typeof rider.content === "object"
    ? Object.entries(rider.content).map(([key, value]) => `${key}: ${value}`).join(", ")
    : "Not specified in package";
  for (const [label, value] of [
    ["Actor ID", identity.actor_id || "Not specified"],
    ["Display name", identity.display_name || "Not specified"],
    ["Signing public key", signed ? (manifest.agent?.public_key || "Not supplied") : "Unsigned"],
    ["Visual identity", manifest.visual?.core_identity || "Not specified"],
    ["Ratings ceiling", ratings],
    ["Commercial rider", rider.commercial ? JSON.stringify(rider.commercial, null, 2) : "Not specified in package"]
  ]) {
    grid.append(text("div", label + ":", "oap-report-label"), text("div", String(value), "oap-report-value"));
  }
  card.replaceChildren(header, grid);
  card.hidden = false;
  if ($("#oap-raw-toggle-wrap")) $("#oap-raw-toggle-wrap").hidden = false;
}

export function initLibraryForms() {
  $("#actor-form").onsubmit = handle(async event => {
    await api("/api/actors", { method: "POST", body: new FormData(event.target) });
    event.target.reset();
    await loadActors();
    scheduleSave();
  });

  $("#style-form").onsubmit = handle(async event => {
    await json("/api/styles", Object.fromEntries(new FormData(event.target)));
    event.target.reset();
    await loadStyles();
    scheduleSave();
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

  $("#oap-import-form").onsubmit = handle(async event => {
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

  $("#agreement-form").onsubmit = handle(async event => {
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

