// Interactive In-App Help & Architecture Guides (OAP, llama.cpp tuning, Vocabulary).

import { $, $$, api, copyToClipboard, handle, notice } from "./core.js";
import { renderMarkdown } from "./markdown.js";

let vocabDocLoaded = false;
let oppDocLoaded = false;
let visionDocLoaded = false;

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
    const field = $("input[name=writer_launch]");
    field.value = command;
    field.dispatchEvent(new Event("change", { bubbles: true }));
    notice("Writer tuning applied to the launch field and saved automatically.");
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

export async function loadOppGuideMarkdown() {
  if (oppDocLoaded) return;
  const rawPre = $("#opp-guide-raw");
  const formattedDiv = $("#opp-guide-formatted");
  if (!rawPre && !formattedDiv) return;
  try {
    const resp = await api("/api/props/guide");
    if (resp.ok) {
      const data = await resp.json();
      const markdown = data.markdown || "Guide content empty.";
      if (rawPre) rawPre.textContent = markdown;
      if (formattedDiv) formattedDiv.innerHTML = renderMarkdown(markdown);
      oppDocLoaded = true;
    } else {
      if (rawPre) rawPre.textContent = "Could not load the Open Prop Protocol guide.";
      if (formattedDiv) formattedDiv.innerHTML = "<p>Could not load the Open Prop Protocol guide.</p>";
    }
  } catch {
    if (rawPre) rawPre.textContent = "Error fetching Open Prop Protocol guide from server.";
    if (formattedDiv) formattedDiv.innerHTML = "<p>Error fetching Open Prop Protocol guide from server.</p>";
  }
}

export function setupOppGuide() {
  const dialog = $("#opp-helper-dialog");
  if (!dialog) return;

  loadOppGuideMarkdown().catch(() => {});

  $$(".opp-help-btn").forEach(btn => {
    btn.onclick = () => {
      loadOppGuideMarkdown();
      dialog.showModal();
    };
  });

  $$(".close-opp-dialog").forEach(btn => {
    btn.onclick = () => {
      dialog.close();
    };
  });

  $$(".nav-to-props-btn").forEach(btn => {
    btn.onclick = () => {
      if (dialog.open) dialog.close();
      const actorNav = document.querySelector('.nav[data-panel="actors"]');
      if (actorNav) actorNav.click();
      const fold = $("#opp-library-fold");
      if (fold) {
        fold.open = true;
        fold.scrollIntoView({ behavior: "smooth" });
      }
    };
  });

  const toggleRawBtn = $("#toggle-opp-raw-btn");
  if (toggleRawBtn) {
    toggleRawBtn.onclick = () => {
      const rawPre = $("#opp-guide-raw");
      const formattedDiv = $("#opp-guide-formatted");
      if (!rawPre || !formattedDiv) return;
      const isRawVisible = !rawPre.hidden;
      rawPre.hidden = isRawVisible;
      formattedDiv.hidden = !isRawVisible;
      toggleRawBtn.textContent = isRawVisible ? "View raw markdown" : "View formatted guide";
    };
  }

  const copyBtn = $("#copy-opp-doc-btn");
  if (copyBtn) {
    copyBtn.onclick = handle(async () => {
      await loadOppGuideMarkdown();
      const rawPre = $("#opp-guide-raw");
      const content = rawPre ? rawPre.textContent : "";
      if (!content || content.startsWith("Error") || content.startsWith("Could not")) {
        throw new Error("No guide document available to copy.");
      }
      if (!await copyToClipboard(content)) throw new Error("Could not copy document to clipboard.");
      notice("Open Prop Protocol Guide copied to clipboard.");
      const origText = copyBtn.textContent;
      copyBtn.textContent = "✓ Copied!";
      setTimeout(() => { copyBtn.textContent = origText; }, 2500);
    });
  }

  const guideBody = $("#opp-guide-body");
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


export async function loadVisionGuideMarkdown() {
  if (visionDocLoaded) return;
  const rawPre = $("#vision-guide-raw");
  const formattedDiv = $("#vision-guide-formatted");
  if (!rawPre && !formattedDiv) return;
  try {
    const resp = await api("/api/vision/guide");
    if (resp.ok) {
      const data = await resp.json();
      const markdown = data.markdown || "Guide content empty.";
      if (rawPre) rawPre.textContent = markdown;
      if (formattedDiv) formattedDiv.innerHTML = renderMarkdown(markdown);
      visionDocLoaded = true;
    } else {
      if (rawPre) rawPre.textContent = "Could not load the Vision setup guide.";
      if (formattedDiv) formattedDiv.innerHTML = "<p>Could not load the Vision setup guide.</p>";
    }
  } catch {
    if (rawPre) rawPre.textContent = "Error fetching Vision setup guide from server.";
    if (formattedDiv) formattedDiv.innerHTML = "<p>Error fetching Vision setup guide from server.</p>";
  }
}

export function setupVisionGuide() {
  const dialog = $("#vision-helper-dialog");
  if (!dialog) return;

  loadVisionGuideMarkdown().catch(() => {});

  $$(".vision-help-btn").forEach(btn => {
    btn.onclick = () => {
      loadVisionGuideMarkdown();
      dialog.showModal();
    };
    // The service cards are not <button>s; let Enter and Space open the guide too.
    if (btn.tagName !== "BUTTON") btn.onkeydown = event => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      btn.click();
    };
  });

  $$(".close-vision-dialog").forEach(btn => {
    btn.onclick = () => {
      dialog.close();
    };
  });

  $$(".nav-to-settings-vision-btn").forEach(btn => {
    btn.onclick = () => {
      if (dialog.open) dialog.close();
      const settingsNav = document.querySelector('.nav[data-panel="settings"]');
      if (settingsNav) settingsNav.click();
    };
  });

  const toggleRawBtn = $("#toggle-vision-raw-btn");
  if (toggleRawBtn) {
    toggleRawBtn.onclick = () => {
      const rawPre = $("#vision-guide-raw");
      const formattedDiv = $("#vision-guide-formatted");
      if (!rawPre || !formattedDiv) return;
      const isRawVisible = !rawPre.hidden;
      rawPre.hidden = isRawVisible;
      formattedDiv.hidden = !isRawVisible;
      toggleRawBtn.textContent = isRawVisible ? "View raw markdown" : "View formatted guide";
    };
  }

  const copyBtn = $("#copy-vision-doc-btn");
  if (copyBtn) {
    copyBtn.onclick = handle(async () => {
      await loadVisionGuideMarkdown();
      const rawPre = $("#vision-guide-raw");
      const content = rawPre ? rawPre.textContent : "";
      if (!content || content.startsWith("Error") || content.startsWith("Could not")) {
        throw new Error("No guide document available to copy.");
      }
      if (!await copyToClipboard(content)) throw new Error("Could not copy document to clipboard.");
      notice("Vision Architecture Guide copied to clipboard.");
      const origText = copyBtn.textContent;
      copyBtn.textContent = "✓ Copied!";
      setTimeout(() => { copyBtn.textContent = origText; }, 2500);
    });
  }

  const guideBody = $("#vision-guide-body");
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
