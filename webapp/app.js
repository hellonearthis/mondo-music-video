// Mondo Music Video — Application Entry Point & Orchestrator.

import { $, $$, api, initThemeToggle, notice, option, state, text } from "./js/core.js";
import { setupLlamaGuide, setupOapGuide, setupVocabGuide } from "./js/guides.js";
import { initLibraryForms, loadActors, loadAgreements, loadStyles } from "./js/library.js";
import { initUpscaleForm, loadOutputs } from "./js/outputs.js";
import {
  initOperationControls,
  initProductionForms,
  loadUpdateStatus,
  refreshServices,
  setupEventStream
} from "./js/production.js";
import { initNavigation, resolutionSelect, restoreProject, scheduleSave } from "./js/project.js";
import { initSettingsAndPicker, loadSettings } from "./js/settings.js";
import { initTooltips } from "./js/tooltips.js";
import { setupVocabularyCustomizer, loadVocabularyCatalog } from "./js/vocabulary.js";

function populateCatalogControls() {
  const { catalog } = state;
  $$(".backend-select").forEach(select => {
    select.append(...Object.entries(catalog.backends).map(([key, card]) =>
      option(key, card.name, `${card.name}: ${card.description || key}`)
    ));
    select.onchange = () => {
      resolutionSelect(select.closest("form"));
      scheduleSave();
    };
  });

  for (const [name, levels] of Object.entries(catalog.ratings)) {
    const tip = `OAP rating ceiling for ${name.replaceAll("_", " ")}`;
    const label = text("label", name.replaceAll("_", " "), "", tip);
    const select = document.createElement("select");
    select.name = "rating_" + name;
    select.dataset.tooltip = tip;
    select.title = tip;
    select.append(...levels.map(level => option(level, level, `Content rating level: ${level}`)));
    select.onchange = scheduleSave;
    label.append(select);
    $(".ratings").append(label);

    const agreementLabel = text("label", name.replaceAll("_", " "), "", `Project content rating for ${name.replaceAll("_", " ")}`);
    const agreementSelect = document.createElement("select");
    agreementSelect.name = "content_" + name;
    agreementSelect.append(...levels.map(level => option(level, level)));
    agreementLabel.append(agreementSelect);
    $(".agreement-ratings").append(agreementLabel);
  }
}

async function initialize() {
  initThemeToggle();
  initTooltips();
  setupOapGuide();
  setupLlamaGuide();
  setupVocabGuide();
  loadUpdateStatus();

  state.catalog = await (await api("/api/catalog")).json();
  const version = await (await api("/api/version")).json();
  $("#version").textContent = version.version;
  $("#oap-version").textContent = state.catalog.oap_version;

  populateCatalogControls();

  const [settings] = await Promise.all([
    loadSettings(),
    loadActors(),
    loadStyles(),
    loadOutputs(),
    loadAgreements()
  ]);

  $$(".backend-select").forEach(select => {
    select.value = settings.backend;
    resolutionSelect(select.closest("form"));
  });

  initNavigation();
  initProductionForms();
  initOperationControls();
  initLibraryForms();
  initSettingsAndPicker();
  initUpscaleForm();

  // Custom presets must be in the profile select before a saved choice is restored.
  await loadVocabularyCatalog().catch(() => {});
  await restoreProject();
  setupEventStream();
  await refreshServices();
  setupVocabularyCustomizer();
  setInterval(() => { refreshServices(); }, 8000);
}

initialize().catch(error => notice(error.message));
