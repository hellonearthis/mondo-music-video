// Interactive In-App Help & Architecture Guides (OAP, llama.cpp tuning, Vocabulary).

import { $, $$, api, copyToClipboard, handle, notice } from "./core.js";
import { renderMarkdown } from "./markdown.js";

let vocabDocLoaded = false;

export function setupOapGuide() {
  const dialog = $("#oap-helper-dialog");
  if (!dialog) return;

  $$(".oap-help-btn").forEach(btn => {
    btn.onclick = () => {
      dialog.showModal();
    };
  });

  $$(".close-oap-dialog").forEach(btn => {
    btn.onclick = () => {
      dialog.close();
    };
  });

  $$(".nav-to-actors-btn").forEach(btn => {
    btn.onclick = () => {
      const actorNav = document.querySelector('.nav[data-panel="actors"]');
      if (actorNav) actorNav.click();
      if (dialog.open) dialog.close();
    };
  });

  $$("#oap-helper-dialog .oap-tab-btn").forEach(tabBtn => {
    tabBtn.onclick = () => {
      const tabId = tabBtn.dataset.tab;
      $$("#oap-helper-dialog .oap-tab-btn").forEach(b => b.classList.toggle("active", b === tabBtn));
      $$("#oap-helper-dialog .oap-tab-content").forEach(content => {
        const matches = content.id === `tab-${tabId}`;
        content.classList.toggle("active", matches);
        content.hidden = !matches;
      });
    };
  });

  const toggleRaw = $("#toggle-raw-oap");
  if (toggleRaw) {
    toggleRaw.onclick = () => {
      const pre = $("#oap-report");
      pre.hidden = !pre.hidden;
      toggleRaw.textContent = pre.hidden ? "Show raw manifest JSON" : "Hide raw manifest JSON";
    };
  }
}

export function tuneLlamaCommand(currentJson, preset = "context_16k") {
  if (preset === "current") return currentJson;
  const args = typeof currentJson === "string" ? JSON.parse(currentJson) : currentJson;
  if (!Array.isArray(args) || !args.length || args.some(arg => typeof arg !== "string")) {
    throw new Error("Configure a JSON array launch command first.");
  }
  const options = {
    "-c": "16384",
    "--ctx-size": "16384",
    "-b": "2048",
    "--batch-size": "2048",
    "-ub": "1024",
    "--ubatch-size": "1024"
  };
  if (args.some(arg => arg === "--mmproj" || arg.startsWith("--mmproj="))) {
    options["--image-min-tokens"] = "1024";
  }
  const result = [args[0]];
  for (let i = 1; i < args.length; i++) {
    const flag = args[i].split("=", 1)[0];
    if (Object.hasOwn(options, flag)) {
      if (!args[i].includes("=")) i++;
    } else {
      result.push(args[i]);
    }
  }
  result.push("-c", "16384", "-b", "2048", "-ub", "1024");
  if (options["--image-min-tokens"]) result.push("--image-min-tokens", "1024");
  return JSON.stringify(result);
}

export function setupLlamaGuide() {
  const dialog = $("#llama-helper-dialog");
  if (!dialog) return;

  const picker = $("#writer-tuning-preset");
  function commandPreview() {
    const current = $("input[name=writer_launch]")?.value || "";
    return tuneLlamaCommand(current, picker.value);
  }
  function showPreview() {
    try {
      $("#llama-current-json").textContent = commandPreview() || "No launch command configured.";
    } catch {
      $("#llama-current-json").textContent = "Configure a valid JSON array launch command before choosing alternate tuning.";
    }
  }
  function openGuide() {
    picker.value = "current";
    showPreview();
    dialog.showModal();
  }
  $$(".llama-help-btn").forEach(button => button.onclick = openGuide);
  picker.onchange = showPreview;
  $$(".close-llama-dialog").forEach(button => button.onclick = () => dialog.close());
  $("#copy-llama-json").onclick = handle(async () => {
    const command = commandPreview();
    if (!command) throw new Error("Configure a writer launch command first.");
    if (!await copyToClipboard(command)) throw new Error("Could not copy the launch command.");
    notice("Writer launch preview copied.");
  });
  $("#apply-writer-tuning").onclick = handle(async () => {
    const command = commandPreview();
    if (!command) throw new Error("Configure a writer launch command first.");
    $("input[name=writer_launch]").value = command;
    notice("Writer tuning applied to the field. Save settings to persist it.");
    dialog.close();
  });
}

export async function loadVocabGuideMarkdown() {
  if (vocabDocLoaded) return;
  const rawPre = $("#vocab-guide-raw");
  const formattedDiv = $("#vocab-guide-formatted");
  if (!rawPre && !formattedDiv) return;
  try {
    const resp = await api("/api/vocabulary/guide");
    if (resp.ok) {
      const data = await resp.json();
      const markdown = data.markdown || "Guide content empty.";
      if (rawPre) rawPre.textContent = markdown;
      if (formattedDiv) formattedDiv.innerHTML = renderMarkdown(markdown);
      vocabDocLoaded = true;
    } else {
      if (rawPre) rawPre.textContent = "Could not load the vocabulary guide.";
      if (formattedDiv) formattedDiv.innerHTML = "<p>Could not load the vocabulary guide.</p>";
    }
  } catch {
    if (rawPre) rawPre.textContent = "Error fetching vocabulary guide from server.";
    if (formattedDiv) formattedDiv.innerHTML = "<p>Error fetching vocabulary guide from server.</p>";
  }
}

export function setupVocabGuide() {
  const dialog = $("#vocab-helper-dialog");
  if (!dialog) return;

  // Pre-load guide in background so it renders immediately when opened
  loadVocabGuideMarkdown().catch(() => {});

  $$(".vocab-help-btn").forEach(btn => {
    btn.onclick = () => {
      loadVocabGuideMarkdown();
      dialog.showModal();
    };
  });

  $$(".close-vocab-dialog").forEach(btn => {
    btn.onclick = () => {
      dialog.close();
    };
  });

  $$(".nav-to-vocab-btn").forEach(btn => {
    btn.onclick = () => {
      if (dialog.open) dialog.close();
      $(".nav[data-panel=vocab]")?.click();
    };
  });

  const toggleRawBtn = $("#toggle-vocab-raw-btn");
  if (toggleRawBtn) {
    toggleRawBtn.onclick = () => {
      const rawPre = $("#vocab-guide-raw");
      const formattedDiv = $("#vocab-guide-formatted");
      if (!rawPre || !formattedDiv) return;
      const isRawVisible = !rawPre.hidden;
      rawPre.hidden = isRawVisible;
      formattedDiv.hidden = !isRawVisible;
      toggleRawBtn.textContent = isRawVisible ? "View raw markdown" : "View formatted guide";
    };
  }

  const copyBtn = $("#copy-vocab-doc-btn");
  if (copyBtn) {
    copyBtn.onclick = handle(async () => {
      await loadVocabGuideMarkdown();
      const rawPre = $("#vocab-guide-raw");
      const content = rawPre ? rawPre.textContent : "";
      if (!content || content.startsWith("Error") || content.startsWith("Could not")) {
        throw new Error("No guide document available to copy.");
      }
      if (!await copyToClipboard(content)) throw new Error("Could not copy document to clipboard.");
      notice("Vocabulary Architecture Guide copied to clipboard.");
      const origText = copyBtn.textContent;
      copyBtn.textContent = "✓ Copied!";
      setTimeout(() => { copyBtn.textContent = origText; }, 2500);
    });
  }

  const guideBody = $("#vocab-guide-body");
  if (guideBody) {
    guideBody.onclick = handle(async (event) => {
      const copyCodeBtn = event.target.closest(".md-copy-btn");
      if (!copyCodeBtn) return;
      const codeBlock = copyCodeBtn.closest(".md-code-block");
      const codeText = codeBlock?.querySelector("code")?.textContent || "";
      if (!codeText) return;
      if (!await copyToClipboard(codeText)) throw new Error("Could not copy code snippet.");
      notice("Code snippet copied to clipboard.");
      const origText = copyCodeBtn.textContent;
      copyCodeBtn.textContent = "✓ Copied";
      setTimeout(() => { copyCodeBtn.textContent = origText; }, 2000);
    });
  }
}

