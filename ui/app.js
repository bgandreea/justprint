const $ = (id) => document.getElementById(id);

const els = {
  addFiles: $("add-files"),
  addFolder: $("add-folder"),
  printer: $("printer"),
  printerDot: $("printer-dot"),
  printerStatus: $("printer-status-label"),
  testPage: $("test-page"),
  printBtn: $("print-btn"),
  sheets: $("sheets-value"),
  pagesFiles: $("pages-files"),
  previewImage: $("preview-image"),
  previewEmpty: $("preview-empty"),
  pageLabel: $("page-label"),
  prevPage: $("prev-page"),
  nextPage: $("next-page"),
  previewName: $("preview-name"),
  bar: $("bar"),
  barFill: $("bar-fill"),
  jobFile: $("job-file"),
  jobCurrent: $("job-current"),
  jobMessage: $("job-message"),
  jobSheets: $("job-sheets"),
  openSettings: $("open-settings"),
  toPrint: $("to-print"),
  removePrinted: $("remove-printed"),
  clear: $("clear"),
  selectAll: $("select-all"),
  rows: $("rows"),
  settings: $("settings"),
  closeSettings: $("close-settings"),
  summary: $("summary"),
  closeSummary: $("close-summary"),
  dismissSummary: $("dismiss-summary"),
  summaryTitle: $("summary-title"),
  summaryMessage: $("summary-message"),
  summaryStats: $("summary-stats"),
  summaryItems: $("summary-items"),
  warningModal: $("warning-modal"),
  warningMessage: $("warning-message"),
  warningOk: $("warning-ok"),
  warningClose: $("warning-close"),
  live: $("live"),
  paper: $("set-paper"),
  paperTray: $("set-paper-tray"),
  orientation: $("set-orientation"),
  color: $("set-color"),
  duplex: $("set-duplex"),
  duplexButton: $("duplex-button"),
  duplexMenu: $("duplex-menu"),
  duplexIcon: document.querySelector("#duplex-picker .duplex-icon"),
  duplexTitle: $("duplex-title"),
  duplexHint: $("duplex-hint"),
  copies: $("set-copies"),
  collate: $("set-collate"),
  batchRepeat: $("set-batch-repeat"),
  pageRange: $("set-page-range"),
  documentFront: $("set-document-front"),
  customWidth: $("set-custom-width"),
  customHeight: $("set-custom-height"),
  adoptDefaults: $("set-adopt-defaults"),
  loadPrinterDefaults: $("load-printer-defaults"),
  ppm: $("set-ppm"),
  pause: $("set-pause"),
  waitQueue: $("set-wait-queue"),
  singleJob: $("set-single-job"),
  printedAction: $("set-printed-action"),
  printedFolder: $("set-printed-folder"),
  pickPrintedFolder: $("pick-printed-folder"),
  removePrintedAfter: $("set-remove-printed"),
  showSummary: $("set-show-summary"),
  subfolders: $("set-subfolders"),
  pdf: $("set-pdf"),
  images: $("set-images"),
  text: $("set-text"),
  settingsSave: $("settings-save"),
  settingsLoad: $("settings-load"),
  settingsReset: $("settings-reset"),
  settingsCloseFooter: $("settings-close-footer"),
  scale: $("set-scale"),
  scalePercent: $("set-scale-percent"),
  marginLeft: $("set-margin-left"),
  marginRight: $("set-margin-right"),
  marginTop: $("set-margin-top"),
  marginBottom: $("set-margin-bottom"),
  alignH: $("set-align-h"),
  alignV: $("set-align-v"),
  offsetX: $("set-offset-x"),
  offsetY: $("set-offset-y"),
  parity: $("set-parity"),
  rotate: $("set-rotate"),
  reverse: $("set-reverse"),
  skipBlank: $("set-skip-blank"),
  imageDpi: $("set-image-dpi"),
  nUp: $("set-nup"),
  nUpBorder: $("set-nup-border"),
  nUpOrder: $("set-nup-order"),
  booklet: $("set-booklet"),
  bookletBinding: $("set-booklet-binding"),
  cropMarks: $("set-crop-marks"),
  coverPage: $("set-cover-page"),
  separatorPages: $("set-separator-pages"),
  placeholder: $("set-placeholder"),
  folderCover: $("set-folder-cover"),
  endCover: $("set-end-cover"),
  stampHl: $("set-stamp-hl"),
  stampHc: $("set-stamp-hc"),
  stampHr: $("set-stamp-hr"),
  stampFl: $("set-stamp-fl"),
  stampFc: $("set-stamp-fc"),
  stampFr: $("set-stamp-fr"),
  stampSize: $("set-stamp-size"),
  wmText: $("set-wm-text"),
  wmSize: $("set-wm-size"),
  wmAngle: $("set-wm-angle"),
  wmIntensity: $("set-wm-intensity"),
  wmOutline: $("set-wm-outline"),
  wmBehind: $("set-wm-behind"),
  wmRange: $("set-wm-range"),
  wmImage: $("set-wm-image"),
  wmImageSize: $("set-wm-image-size"),
  printReport: $("set-print-report"),
  reportFile: $("set-report-file"),
  reportFormat: $("set-report-format"),
};

const EYE = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2.8 12S6.2 6.8 12 6.8 21.2 12 21.2 12 17.8 17.2 12 17.2 2.8 12 2.8 12z" fill="none" stroke="currentColor" stroke-width="1.7"/><circle cx="12" cy="12" r="2.4" fill="none" stroke="currentColor" stroke-width="1.7"/></svg>';

const view = {
  last: null,
  docKey: null,
  previewId: null,
  previewPage: 1,
  previewSrc: "",
  holdPreview: false,
  holdFile: null,
  sawRunning: false,
  scrolledTo: null,
  printerKey: "",
  errorText: "",
  errorUntil: 0,
  lastSpoken: "",
  dropText: "",
  summaryKey: "",
  warningKey: "",
};

let chain = Promise.resolve();
let mutations = 0;
let refreshing = false;
let refreshAgain = false;
const rangeTimers = new Map();

function cssEscape(value) {
  if (window.CSS && typeof CSS.escape === "function") return CSS.escape(value);
  return String(value).replace(/[^a-zA-Z0-9_-]/g, "\\$&");
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[ch]));
}

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  const mb = bytes / (1024 * 1024);
  return `${mb >= 10 ? Math.round(mb) : mb.toFixed(1)} MB`;
}

function formatModified(epoch) {
  const date = new Date(epoch * 1000);
  const pad = (n) => String(n).padStart(2, "0");
  const year = String(date.getFullYear()).slice(2);
  return `${pad(date.getMonth() + 1)}/${pad(date.getDate())}/${year}, ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function showError(text) {
  view.errorText = text;
  view.errorUntil = Date.now() + 7000;
  paintMessage();
}

function api(url, body) {
  const run = chain.then(async () => {
    mutations += 1;
    try {
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body || {}),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || "That did not work");
      if (data.warning) showUnsupportedWarning(data.warning);
      if (!data.cancelled) await refresh();
      return data;
    } catch (error) {
      showError(error.message || "That did not work");
      throw error;
    } finally {
      mutations -= 1;
    }
  });
  chain = run.catch(() => {});
  return run;
}

async function refresh() {
  if (refreshing) {
    refreshAgain = true;
    return;
  }
  refreshing = true;
  try {
    do {
      refreshAgain = false;
      const response = await fetch("/api/state", { cache: "no-store" });
      if (!response.ok) throw new Error("Could not load the queue");
      apply(await response.json());
    } while (refreshAgain);
  } catch (error) {
    if (!view.last) showError(error.message || "SpoolMate is not responding.");
  } finally {
    refreshing = false;
  }
}

function apply(data) {
  view.last = data;
  followJob(data.job);
  const docs = data.documents || [];
  if (!view.previewId || !docs.some((doc) => doc.id === view.previewId)) {
    view.previewId = docs[0] ? docs[0].id : null;
    view.previewPage = 1;
  }
  const preview = docs.find((doc) => doc.id === view.previewId);
  if (preview && preview.pages) {
    view.previewPage = Math.min(Math.max(1, view.previewPage), preview.pages);
  }
  paintChrome(data);
  paintDocuments(data);
  paintPreview(data);
  paintSettings(data.settings);
  paintSummary(data.summary);
  paintMessage();
  if (data.warning) showUnsupportedWarning(data.warning);
  else if (!data.warning) view.warningKey = "";
}

function showUnsupportedWarning(text) {
  if (!text || text === view.warningKey) return;
  view.warningKey = text;
  els.warningMessage.textContent = text;
  els.warningModal.hidden = false;
}

function dismissUnsupportedWarning() {
  els.warningModal.hidden = true;
  api("/api/warning/dismiss").catch(() => {});
}

function followJob(job) {
  if (job.running && !view.sawRunning) {
    view.holdPreview = false;
    view.sawRunning = true;
  }
  if (!job.running) view.sawRunning = false;
  if (!job.running || !job.currentId) return;
  if (view.holdPreview && job.currentId !== view.holdFile) view.holdPreview = false;
  if (!view.holdPreview) {
    view.previewId = job.currentId;
    view.previewPage = job.currentPage || 1;
  }
}

function paintChrome(data) {
  const { job, settings, totals, printerStatus, printers } = data;
  els.sheets.textContent = String(totals.sheets);
  els.pagesFiles.textContent = `Pages: ${totals.pages} · Files: ${totals.files}`;
  els.toPrint.textContent = `To print: ${totals.selected} of ${totals.files}`;

  const printerKey = `${printers.join("|")}|${settings.printer}`;
  if (printerKey !== view.printerKey && document.activeElement !== els.printer) {
    els.printer.innerHTML = printers.length
      ? printers.map((name) => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`).join("")
      : '<option value="">No printers found</option>';
    if (settings.printer) els.printer.value = settings.printer;
    view.printerKey = printerKey;
  }
  els.printer.disabled = job.running || !printers.length;
  els.printerDot.className = `dot ${printerStatus.level || "warn"}`;
  els.printerStatus.textContent = printerStatus.label || "Unavailable";
  els.testPage.disabled = job.running || !settings.printer;

  els.printBtn.classList.toggle("stop", job.running);
  const nothingSelected = totals.selected === 0;
  els.printBtn.disabled = job.running ? false : Boolean(data.blocked) || nothingSelected;
  const idleReason = data.blocked || (nothingSelected ? (totals.files ? "Select at least one file." : "Add a file to print.") : "");
  els.printBtn.title = !job.running && idleReason ? idleReason : "";

  const busy = job.running;
  els.addFiles.disabled = busy;
  els.addFolder.disabled = busy;
  els.clear.disabled = busy || totals.files === 0;
  els.removePrinted.hidden = !data.documents.some((doc) => doc.status === "printed");
  els.removePrinted.disabled = busy;

  const showProgress = job.phase && job.phase !== "idle";
  els.bar.hidden = !showProgress;
  const pct = job.sheetsTotal ? Math.min(100, (job.sheetsPrinted / job.sheetsTotal) * 100) : 0;
  els.barFill.style.width = `${pct}%`;
  els.jobFile.textContent = showProgress && job.fileTotal ? `file ${job.fileIndex} of ${job.fileTotal}` : "";
  const printingFile = job.running && job.currentName ? `Printing ${job.currentName}…` : "";
  els.jobCurrent.hidden = !printingFile;
  els.jobCurrent.textContent = printingFile;
  els.jobSheets.textContent = showProgress ? `Sheets printed: ${job.sheetsPrinted}` : "";
}

function paintMessage() {
  const data = view.last;
  let text = "Add files or a folder, or drop them on this window.";
  if (Date.now() < view.errorUntil && view.errorText) {
    text = view.errorText;
  } else if (view.dropText) {
    text = view.dropText;
  } else if (data) {
    const job = data.job;
    if (job.running) text = job.message || "Sending the job to the print queue…";
    else if (data.notice) text = data.notice;
    else if (job.phase && job.phase !== "idle" && job.message) text = job.message;
    else if (data.blocked && data.documents.length) text = data.blocked;
    else if (data.documents.length) text = "Ready to print.";
  }
  els.jobMessage.textContent = text;
  if (text !== view.lastSpoken) {
    view.lastSpoken = text;
    els.live.textContent = text;
  }
}

function paintDocuments(data) {
  const docs = data.documents;
  const key = docs.map((doc) => doc.id).join("|");
  if (key !== view.docKey) {
    view.docKey = key;
    els.rows.innerHTML = docs.length ? docs.map((doc, index) => rowHtml(doc, index, data)).join("") : emptyRow();
  }
  docs.forEach((doc, index) => syncRow(doc, index, data));
  const selected = docs.filter((doc) => doc.selected).length;
  if (document.activeElement !== els.selectAll) {
    els.selectAll.checked = docs.length > 0 && selected === docs.length;
    els.selectAll.indeterminate = selected > 0 && selected < docs.length;
  }
  els.selectAll.disabled = data.job.running || docs.length === 0;
  const job = data.job;
  if (job.running && job.currentId && job.currentId !== view.scrolledTo) {
    const row = els.rows.querySelector(`tr[data-id="${cssEscape(job.currentId)}"]`);
    if (row) row.scrollIntoView({ block: "nearest" });
    view.scrolledTo = job.currentId;
  }
}

function emptyRow() {
  return '<tr class="empty"><td colspan="11">Add files or a folder, or drop them here.<br>PDFs, images, and text files can be printed together.</td></tr>';
}

function rowHtml(doc, index, data) {
  const status = statusInfo(doc, data);
  const locked = data.job.running;
  return `<tr data-id="${doc.id}" class="${rowClass(doc)}">
    <td class="num">${index + 1}</td>
    <td class="check"><input type="checkbox" class="include" ${doc.selected ? "checked" : ""} ${locked ? "disabled" : ""} aria-label="Include ${escapeHtml(doc.name)}"></td>
    <td class="file"><div class="file-cell">${fileIcon(doc.kind)}<button type="button" class="eye" aria-label="Preview ${escapeHtml(doc.name)}">${EYE}</button><span class="file-name" title="${escapeHtml(doc.path)}">${escapeHtml(doc.name)}</span></div></td>
    <td>${escapeHtml(doc.typeLabel)}</td>
    <td class="pages">${pagesText(doc)}</td>
    <td>${formatSize(doc.size)}</td>
    <td class="modified" title="${escapeHtml(formatModified(doc.modified))}">${formatModified(doc.modified)}</td>
    <td><select class="copies" aria-label="Copies for ${escapeHtml(doc.name)}" ${locked ? "disabled" : ""}>${copyOptions(doc.copies)}</select></td>
    <td><input class="range${doc.rangeError ? " bad" : ""}" type="text" value="${escapeHtml(doc.range)}" ${locked ? "disabled" : ""} aria-label="Page range for ${escapeHtml(doc.name)}" title="${escapeHtml(doc.rangeError || "all, or a range like 1-3,5")}" spellcheck="false" autocomplete="off"></td>
    <td class="status ${status.cls}" title="${escapeHtml(status.title)}">${escapeHtml(status.text)}</td>
    <td><button type="button" class="remove" aria-label="Remove ${escapeHtml(doc.name)}" ${locked ? "disabled" : ""}>×</button></td>
  </tr>`;
}

function syncRow(doc, index, data) {
  const row = els.rows.querySelector(`tr[data-id="${cssEscape(doc.id)}"]`);
  if (!row) return;
  row.className = rowClass(doc);
  const locked = data.job.running;
  const include = row.querySelector(".include");
  if (document.activeElement !== include) include.checked = doc.selected;
  include.disabled = locked;
  row.querySelector(".num").textContent = String(index + 1);
  row.querySelector(".pages").textContent = pagesText(doc);
  const status = statusInfo(doc, data);
  const statusCell = row.querySelector(".status");
  statusCell.className = `status ${status.cls}`.trim();
  statusCell.textContent = status.text;
  statusCell.title = status.title;
  const copies = row.querySelector(".copies");
  const wanted = doc.copies == null ? "" : String(doc.copies);
  if (document.activeElement !== copies && copies.value !== wanted) copies.value = wanted;
  copies.disabled = locked;
  copies.title = `Default is ${data.settings.defaultCopies}`;
  const range = row.querySelector(".range");
  range.classList.toggle("bad", Boolean(doc.rangeError));
  range.title = doc.rangeError || "all, or a range like 1-3,5";
  range.disabled = locked;
  if (document.activeElement !== range && range.value !== doc.range) range.value = doc.range;
  row.querySelector(".remove").disabled = locked;
}

function rowClass(doc) {
  const classes = [];
  if (doc.selected && ["preparing", "queued", "printing"].includes(doc.status)) classes.push("printing");
  if (doc.id === view.previewId) classes.push("previewing");
  return classes.join(" ");
}

function pagesText(doc) {
  if (doc.inspecting || doc.pages == null && !doc.error) return "…";
  if (doc.pages == null) return "—";
  return String(doc.pages);
}

function statusInfo(doc, data) {
  if (!doc.selected) {
    const earlier = doc.status === "printed" ? "Printed earlier" : doc.error || "Not included in the next job";
    return { text: "Skipped", cls: "skipped", title: earlier };
  }
  const job = data ? data.job : null;
  if (doc.status === "preparing") {
    return { text: "Preparing", cls: "preparing", title: "Reading pages and sending to the printer" };
  }
  if (doc.status === "queued") {
    return { text: "Queued", cls: "queued", title: "In the printer queue; waiting for it to finish" };
  }
  if (job && job.running && doc.status === "ready") {
    return { text: "Waiting", cls: "waiting", title: "Prints after the files above it" };
  }
  if (doc.status === "printed") return { text: "Printed", cls: "printed", title: "" };
  if (doc.status === "printing") {
    return { text: "Printing", cls: "printing", title: "Printing this file" };
  }
  if (doc.status === "stopped") return { text: "Stopped", cls: "stopped", title: doc.error || "" };
  if (doc.status === "error") return { text: "Error", cls: "error", title: doc.error || "Could not print this file" };
  return { text: "", cls: "", title: "" };
}

function copyOptions(copies) {
  const options = ['<option value="">default</option>'];
  const extra = copies != null && (copies < 1 || copies > 10) ? [copies] : [];
  for (const value of [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, ...extra]) {
    options.push(`<option value="${value}">${value}</option>`);
  }
  return options.join("");
}

function fileIcon(kind) {
  const color = kind === "pdf" ? "#d64545" : kind === "image" ? "#2f6fed" : "#6b7785";
  return `<svg class="file-icon" viewBox="0 0 16 16" aria-hidden="true"><path d="M4 1.5h5.2L13 5.2V14a.8.8 0 0 1-.8.8H4a.8.8 0 0 1-.8-.8V2.3A.8.8 0 0 1 4 1.5z" fill="${color}"/><path d="M9.2 1.7V5.2H13" fill="none" stroke="white" stroke-width="1"/></svg>`;
}

function paintPreview(data) {
  const doc = (data.documents || []).find((item) => item.id === view.previewId);
  els.previewName.textContent = doc ? doc.name : data.job.running ? data.job.currentName : "";
  els.previewName.title = doc ? doc.path : "";
  const pages = doc && doc.pages ? doc.pages : 0;
  els.pageLabel.textContent = doc ? `page ${pages ? view.previewPage : 0} of ${pages || "…"}` : "page 0 of 0";
  els.prevPage.disabled = !doc || view.previewPage <= 1;
  els.nextPage.disabled = !doc || !pages || view.previewPage >= pages;
  if (!doc || doc.inspecting || doc.error && !doc.pages) {
    els.previewImage.hidden = true;
    els.previewImage.removeAttribute("src");
    view.previewSrc = "";
    els.previewEmpty.hidden = false;
    els.previewEmpty.textContent = !doc ? "Select a file to preview it." : doc.error || "Reading this file…";
    return;
  }
  const s = data.settings;
  const token = [
    s.paper, s.orientation, s.color, s.rotate, s.scale,
    s.watermark && s.watermark.text, s.stamps && s.stamps.headerCenter, doc.modified,
  ].join("-");
  const src = `/api/preview/${encodeURIComponent(doc.id)}?page=${view.previewPage}&v=${encodeURIComponent(token)}`;
  if (view.previewSrc !== src) {
    view.previewSrc = src;
    els.previewImage.hidden = false;
    els.previewEmpty.hidden = true;
    els.previewImage.alt = `Preview of ${doc.name}, page ${view.previewPage}`;
    els.previewImage.src = src;
  }
}

function paintSettings(settings) {
  setValue(els.paper, settings.paper || "default");
  setValue(els.paperTray, settings.paperTray || "default");
  setValue(els.orientation, settings.orientation);
  setValue(els.color, settings.color);
  setValue(els.duplex, settings.duplex);
  paintDuplex();
  setValue(els.copies, String(settings.defaultCopies));
  setChecked(els.collate, settings.collate);
  setValue(els.batchRepeat, String(settings.batchRepeat ?? 1));
  setValue(els.pageRange, settings.pageRange || "");
  setChecked(els.documentFront, settings.documentOnFront);
  setValue(els.customWidth, String(settings.customPaperWidth ?? 0));
  setValue(els.customHeight, String(settings.customPaperHeight ?? 0));
  setChecked(els.adoptDefaults, settings.adoptPrinterDefaults);
  setValue(els.ppm, String(settings.sheetsPerMinute));
  setValue(els.pause, String(settings.pauseBeforeDocument));
  setChecked(els.waitQueue, settings.waitForEmptyQueue);
  setChecked(els.singleJob, settings.singleJob);
  setValue(els.printedAction, settings.printedAction || "none");
  if (document.activeElement !== els.printedFolder) {
    els.printedFolder.value = settings.printedFolder || "";
  }
  setChecked(els.removePrintedAfter, settings.removePrintedAfter);
  setChecked(els.showSummary, settings.showSummary);
  setChecked(els.subfolders, settings.subfolders);
  setChecked(els.pdf, settings.types.pdf);
  setChecked(els.images, settings.types.images);
  setChecked(els.text, settings.types.text);
  setValue(els.scale, settings.scale || "fit");
  setValue(els.scalePercent, String(settings.scalePercent ?? 100));
  setValue(els.marginLeft, String(settings.marginLeft ?? 0));
  setValue(els.marginRight, String(settings.marginRight ?? 0));
  setValue(els.marginTop, String(settings.marginTop ?? 0));
  setValue(els.marginBottom, String(settings.marginBottom ?? 0));
  setValue(els.alignH, settings.horizontalAlign || "center");
  setValue(els.alignV, settings.verticalAlign || "middle");
  setValue(els.offsetX, String(settings.offsetX ?? 0));
  setValue(els.offsetY, String(settings.offsetY ?? 0));
  setValue(els.parity, settings.parity || "all");
  setValue(els.rotate, String(settings.rotate ?? 0));
  setChecked(els.reverse, settings.reverseOrder);
  setChecked(els.skipBlank, settings.skipBlank);
  setValue(els.imageDpi, String(settings.imageDpi ?? 300));
  setValue(els.nUp, String(settings.nUp ?? 1));
  setChecked(els.nUpBorder, settings.nUpBorder);
  setValue(els.nUpOrder, settings.nUpOrder || "rowsright");
  setChecked(els.booklet, settings.booklet);
  setValue(els.bookletBinding, settings.bookletBinding || "left");
  setChecked(els.cropMarks, settings.cropMarks);
  setChecked(els.coverPage, settings.coverPage);
  setChecked(els.separatorPages, settings.separatorPages);
  setChecked(els.placeholder, settings.placeholder);
  setChecked(els.folderCover, settings.folderCoverPage);
  setChecked(els.endCover, settings.endCoverPage);
  const stamps = settings.stamps || {};
  setValue(els.stampHl, stamps.headerLeft || "");
  setValue(els.stampHc, stamps.headerCenter || "");
  setValue(els.stampHr, stamps.headerRight || "");
  setValue(els.stampFl, stamps.footerLeft || "");
  setValue(els.stampFc, stamps.footerCenter || "");
  setValue(els.stampFr, stamps.footerRight || "");
  setValue(els.stampSize, String(stamps.fontSize ?? 8));
  const wm = settings.watermark || {};
  setValue(els.wmText, wm.text || "");
  setValue(els.wmSize, String(wm.fontSize ?? 0));
  setValue(els.wmAngle, String(wm.angle ?? 45));
  setValue(els.wmIntensity, String(wm.intensity ?? 15));
  setChecked(els.wmOutline, wm.outline);
  setChecked(els.wmBehind, wm.behind);
  setValue(els.wmRange, wm.pageRange || "");
  setValue(els.wmImage, wm.image || "");
  setValue(els.wmImageSize, String(wm.imageSize ?? 40));
  setChecked(els.printReport, settings.printReport);
  setChecked(els.reportFile, settings.reportFile);
  setValue(els.reportFormat, settings.reportFormat || "text");
  const duplex = settings.duplex !== "simplex";
  const combined = Boolean(settings.singleJob);
  els.documentFront.disabled = !(duplex && combined);
  const needsFolder = settings.printedAction === "move" || settings.printedAction === "copy";
  els.printedFolder.disabled = !needsFolder;
  els.pickPrintedFolder.disabled = !needsFolder || (view.last && view.last.job.running);
  els.loadPrinterDefaults.disabled = Boolean(view.last && view.last.job.running) || !settings.printer;
}

function showSettingsTab(name) {
  document.querySelectorAll(".settings-tab").forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.tab === name);
  });
  document.querySelectorAll(".settings-panel").forEach((panel) => {
    panel.hidden = panel.dataset.panel !== name;
  });
}

function paintSummary(summary) {
  if (!summary) {
    view.summaryKey = "";
    els.summary.hidden = true;
    return;
  }
  const key = `${summary.message}|${summary.sheets}|${summary.printed}|${summary.failed}|${summary.stopped}`;
  if (key === view.summaryKey && !els.summary.hidden) return;
  view.summaryKey = key;
  els.summaryTitle.textContent = summary.title || "Print summary";
  els.summaryMessage.textContent = summary.message || "";
  const bits = [];
  bits.push(`Sheets: ${summary.sheets || 0}`);
  bits.push(`Printed: ${summary.printed || 0}`);
  if (summary.failed) bits.push(`Failed: ${summary.failed}`);
  if (summary.stopped) bits.push(`Stopped: ${summary.stopped}`);
  els.summaryStats.textContent = bits.join(" · ");
  const items = Array.isArray(summary.items) ? summary.items : [];
  els.summaryItems.innerHTML = items.length
    ? items.map((item) => {
      const status = escapeHtml(item.status || "");
      const err = item.error ? ` — ${escapeHtml(item.error)}` : "";
      return `<li><span class="summary-name">${escapeHtml(item.name)}</span><span class="summary-status ${status}">${status}${err}</span></li>`;
    }).join("")
    : "";
  els.summary.hidden = false;
}

function dismissSummary() {
  els.summary.hidden = true;
  view.summaryKey = "";
  api("/api/summary/dismiss").catch(() => {});
}

function paintDuplex() {
  const value = els.duplex.value || "simplex";
  const option = els.duplexMenu.querySelector(`[data-value="${value}"]`) || els.duplexMenu.querySelector('[data-value="simplex"]');
  els.duplexTitle.textContent = option.dataset.title;
  els.duplexHint.textContent = option.dataset.hint;
  els.duplexIcon.innerHTML = option.querySelector("svg").outerHTML;
  els.duplexButton.setAttribute("aria-label", `${option.dataset.title}. ${option.dataset.hint}`);
  els.duplexMenu.querySelectorAll(".duplex-option").forEach((item) => {
    item.setAttribute("aria-selected", item === option ? "true" : "false");
  });
}

function placeDuplexMenu() {
  const rect = els.duplexButton.getBoundingClientRect();
  const height = els.duplexMenu.offsetHeight || 176;
  const spaceBelow = window.innerHeight - rect.bottom;
  const top = spaceBelow < height + 8 && rect.top > height + 8 ? rect.top - height - 4 : rect.bottom + 4;
  els.duplexMenu.style.left = `${rect.left}px`;
  els.duplexMenu.style.top = `${Math.max(8, top)}px`;
  els.duplexMenu.style.width = `${rect.width}px`;
}

function setDuplexOpen(open) {
  els.duplexMenu.hidden = !open;
  els.duplexButton.setAttribute("aria-expanded", open ? "true" : "false");
  if (!open) return;
  if (els.duplexMenu.parentElement !== document.body) document.body.appendChild(els.duplexMenu);
  placeDuplexMenu();
}

function setValue(element, value) {
  if (document.activeElement !== element && element.value !== value) element.value = value;
}

function setChecked(element, checked) {
  if (document.activeElement !== element) element.checked = Boolean(checked);
}

function pinPreview(id) {
  const job = view.last ? view.last.job : null;
  view.holdPreview = true;
  view.holdFile = job ? job.currentId : null;
  view.previewId = id;
  view.previewPage = 1;
  if (view.last) {
    view.docKey = "";
    apply(view.last);
  }
}

function stepPage(delta) {
  const doc = view.last && view.last.documents.find((item) => item.id === view.previewId);
  if (!doc || !doc.pages) return;
  const job = view.last.job;
  view.holdPreview = true;
  view.holdFile = job.currentId;
  view.previewPage = Math.min(doc.pages, Math.max(1, view.previewPage + delta));
  paintPreview(view.last);
  paintDocuments(view.last);
}

els.previewImage.addEventListener("error", () => {
  els.previewImage.hidden = true;
  els.previewEmpty.hidden = false;
  els.previewEmpty.textContent = "No preview for this page.";
  view.previewSrc = "";
});

els.addFiles.addEventListener("click", () => api("/api/pick/files").catch(() => {}));
els.addFolder.addEventListener("click", () => api("/api/pick/folder").catch(() => {}));
els.warningOk.addEventListener("click", dismissUnsupportedWarning);
els.warningClose.addEventListener("click", dismissUnsupportedWarning);
els.warningModal.addEventListener("click", (event) => {
  if (event.target === els.warningModal) dismissUnsupportedWarning();
});
els.printer.addEventListener("change", () => api("/api/settings", { printer: els.printer.value }).catch(() => {}));
els.testPage.addEventListener("click", () => api("/api/print/test").catch(() => {}));
els.printBtn.addEventListener("click", () => {
  const active = document.activeElement;
  if (active && active.classList && active.classList.contains("range")) {
    const row = active.closest("tr");
    if (row) scheduleRange(row.dataset.id, active.value, 0);
  }
  const url = view.last && view.last.job.running ? "/api/print/stop" : "/api/print/start";
  api(url).catch(() => {});
});
els.selectAll.addEventListener("change", () => {
  api("/api/documents/select-all", { selected: els.selectAll.checked }).catch(() => {});
});
els.clear.addEventListener("click", () => {
  if (!view.last || !view.last.documents.length) return;
  if (!window.confirm("Remove all files from the list? They stay on disk.")) return;
  api("/api/documents/clear").catch(() => {});
});
els.removePrinted.addEventListener("click", () => api("/api/documents/remove-printed").catch(() => {}));
els.openSettings.addEventListener("click", () => {
  showSettingsTab("print");
  els.settings.hidden = false;
});
els.closeSettings.addEventListener("click", () => { setDuplexOpen(false); els.settings.hidden = true; });
els.settingsCloseFooter.addEventListener("click", () => { setDuplexOpen(false); els.settings.hidden = true; });
els.settings.addEventListener("click", (event) => {
  if (event.target === els.settings) { setDuplexOpen(false); els.settings.hidden = true; }
});
document.querySelector(".settings-panels").addEventListener("scroll", () => {
  if (els.duplexMenu.hidden) return;
  const rect = els.duplexButton.getBoundingClientRect();
  const panel = document.querySelector(".settings-panels").getBoundingClientRect();
  if (rect.bottom < panel.top || rect.top > panel.bottom) setDuplexOpen(false);
  else placeDuplexMenu();
});
document.querySelectorAll(".settings-tab").forEach((tab) => {
  tab.addEventListener("click", () => showSettingsTab(tab.dataset.tab));
});
const infoPop = document.createElement("div");
infoPop.className = "info-pop";
infoPop.hidden = true;
document.body.appendChild(infoPop);
function placeInfo(button) {
  infoPop.textContent = button.getAttribute("aria-label") || "";
  infoPop.hidden = false;
  const rect = button.getBoundingClientRect();
  const width = Math.min(280, window.innerWidth - 16);
  const left = Math.min(Math.max(8, rect.left - 8), window.innerWidth - width - 8);
  infoPop.style.width = `${width}px`;
  infoPop.style.left = `${left}px`;
  infoPop.style.top = `${rect.bottom + 6}px`;
  const height = infoPop.offsetHeight;
  if (rect.bottom + 6 + height > window.innerHeight - 8 && rect.top > height + 8) {
    infoPop.style.top = `${rect.top - height - 6}px`;
  }
}
function hideInfo(target) {
  if (target && target.closest && target.closest(".info")) infoPop.hidden = true;
}
document.body.addEventListener("mouseover", (event) => {
  const button = event.target.closest(".info");
  if (button) placeInfo(button);
});
document.body.addEventListener("mouseout", (event) => {
  const button = event.target.closest(".info");
  if (button && !button.contains(event.relatedTarget)) infoPop.hidden = true;
});
document.body.addEventListener("focusin", (event) => {
  const button = event.target.closest(".info");
  if (button) placeInfo(button);
});
document.body.addEventListener("focusout", (event) => hideInfo(event.target));
els.closeSummary.addEventListener("click", dismissSummary);
els.dismissSummary.addEventListener("click", dismissSummary);
els.summary.addEventListener("click", (event) => {
  if (event.target === els.summary) dismissSummary();
});
els.prevPage.addEventListener("click", () => stepPage(-1));
els.nextPage.addEventListener("click", () => stepPage(1));

els.duplexButton.addEventListener("click", (event) => {
  event.stopPropagation();
  setDuplexOpen(els.duplexMenu.hidden);
});
els.duplexMenu.addEventListener("click", (event) => {
  const option = event.target.closest(".duplex-option");
  if (!option) return;
  event.stopPropagation();
  els.duplex.value = option.dataset.value;
  paintDuplex();
  setDuplexOpen(false);
  els.duplex.dispatchEvent(new Event("change"));
});
document.addEventListener("click", (event) => {
  if (els.duplexMenu.hidden) return;
  if (event.target.closest("#duplex-picker") || event.target.closest("#duplex-menu")) return;
  setDuplexOpen(false);
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !els.duplexMenu.hidden) setDuplexOpen(false);
});
for (const [element, key] of [
  [els.paper, "paper"],
  [els.paperTray, "paperTray"],
  [els.orientation, "orientation"],
  [els.color, "color"],
  [els.duplex, "duplex"],
  [els.printedAction, "printedAction"],
]) {
  element.addEventListener("change", () => api("/api/settings", { [key]: element.value }).catch(() => {}));
}
els.copies.addEventListener("change", () => {
  api("/api/settings", { defaultCopies: Number(els.copies.value) }).catch(() => {});
});
els.batchRepeat.addEventListener("change", () => {
  api("/api/settings", { batchRepeat: Number(els.batchRepeat.value) }).catch(() => {});
});
els.pageRange.addEventListener("change", () => {
  api("/api/settings", { pageRange: els.pageRange.value }).catch(() => {});
});
els.customWidth.addEventListener("change", () => {
  api("/api/settings", { customPaperWidth: Number(els.customWidth.value) }).catch(() => {});
});
els.customHeight.addEventListener("change", () => {
  api("/api/settings", { customPaperHeight: Number(els.customHeight.value) }).catch(() => {});
});
els.ppm.addEventListener("change", () => {
  api("/api/settings", { sheetsPerMinute: Number(els.ppm.value) }).catch(() => {});
});
els.pause.addEventListener("change", () => {
  api("/api/settings", { pauseBeforeDocument: Number(els.pause.value) }).catch(() => {});
});
for (const [element, key] of [
  [els.collate, "collate"],
  [els.documentFront, "documentOnFront"],
  [els.adoptDefaults, "adoptPrinterDefaults"],
  [els.waitQueue, "waitForEmptyQueue"],
  [els.singleJob, "singleJob"],
  [els.removePrintedAfter, "removePrintedAfter"],
  [els.showSummary, "showSummary"],
  [els.subfolders, "subfolders"],
]) {
  element.addEventListener("change", () => api("/api/settings", { [key]: element.checked }).catch(() => {}));
}
els.loadPrinterDefaults.addEventListener("click", () => {
  api("/api/settings/printer-defaults").catch(() => {});
});
els.pickPrintedFolder.addEventListener("click", () => {
  api("/api/settings/printed-folder").catch(() => {});
});
els.settingsSave.addEventListener("click", () => {
  api("/api/settings/export").catch(() => {});
});
els.settingsLoad.addEventListener("click", () => {
  api("/api/settings/import").catch(() => {});
});
els.settingsReset.addEventListener("click", () => {
  if (!window.confirm("Reset settings to defaults? Printer and window size stay.")) return;
  api("/api/settings/reset").catch(() => {});
});
function saveTypes() {
  api("/api/settings", {
    types: { pdf: els.pdf.checked, images: els.images.checked, text: els.text.checked },
  }).catch(() => {});
}
els.pdf.addEventListener("change", saveTypes);
els.images.addEventListener("change", saveTypes);
els.text.addEventListener("change", saveTypes);

for (const [element, key] of [
  [els.scale, "scale"],
  [els.alignH, "horizontalAlign"],
  [els.alignV, "verticalAlign"],
  [els.parity, "parity"],
  [els.nUpOrder, "nUpOrder"],
  [els.bookletBinding, "bookletBinding"],
  [els.reportFormat, "reportFormat"],
]) {
  element.addEventListener("change", () => api("/api/settings", { [key]: element.value }).catch(() => {}));
}
for (const [element, key] of [
  [els.scalePercent, "scalePercent"],
  [els.marginLeft, "marginLeft"],
  [els.marginRight, "marginRight"],
  [els.marginTop, "marginTop"],
  [els.marginBottom, "marginBottom"],
  [els.offsetX, "offsetX"],
  [els.offsetY, "offsetY"],
  [els.rotate, "rotate"],
  [els.imageDpi, "imageDpi"],
  [els.nUp, "nUp"],
]) {
  element.addEventListener("change", () => api("/api/settings", { [key]: Number(element.value) }).catch(() => {}));
}
for (const [element, key] of [
  [els.reverse, "reverseOrder"],
  [els.skipBlank, "skipBlank"],
  [els.nUpBorder, "nUpBorder"],
  [els.booklet, "booklet"],
  [els.cropMarks, "cropMarks"],
  [els.coverPage, "coverPage"],
  [els.separatorPages, "separatorPages"],
  [els.placeholder, "placeholder"],
  [els.folderCover, "folderCoverPage"],
  [els.endCover, "endCoverPage"],
  [els.printReport, "printReport"],
  [els.reportFile, "reportFile"],
]) {
  element.addEventListener("change", () => api("/api/settings", { [key]: element.checked }).catch(() => {}));
}
function saveStamps() {
  api("/api/settings", {
    stamps: {
      headerLeft: els.stampHl.value,
      headerCenter: els.stampHc.value,
      headerRight: els.stampHr.value,
      footerLeft: els.stampFl.value,
      footerCenter: els.stampFc.value,
      footerRight: els.stampFr.value,
      fontSize: Number(els.stampSize.value),
    },
  }).catch(() => {});
}
[els.stampHl, els.stampHc, els.stampHr, els.stampFl, els.stampFc, els.stampFr, els.stampSize].forEach((el) => {
  el.addEventListener("change", saveStamps);
});
function saveWatermark() {
  api("/api/settings", {
    watermark: {
      text: els.wmText.value,
      fontSize: Number(els.wmSize.value),
      angle: Number(els.wmAngle.value),
      intensity: Number(els.wmIntensity.value),
      outline: els.wmOutline.checked,
      behind: els.wmBehind.checked,
      pageRange: els.wmRange.value,
      image: els.wmImage.value,
      imageSize: Number(els.wmImageSize.value),
    },
  }).catch(() => {});
}
[els.wmText, els.wmSize, els.wmAngle, els.wmIntensity, els.wmOutline, els.wmBehind, els.wmRange, els.wmImage, els.wmImageSize].forEach((el) => {
  el.addEventListener("change", saveWatermark);
});

function scheduleRange(id, value, delay) {
  clearTimeout(rangeTimers.get(id));
  rangeTimers.set(id, setTimeout(() => {
    api("/api/documents/update", { id, range: value }).catch(() => {});
  }, delay));
}

els.rows.addEventListener("input", (event) => {
  if (!event.target.classList.contains("range")) return;
  const row = event.target.closest("tr");
  if (!row) return;
  scheduleRange(row.dataset.id, event.target.value, 300);
});

els.rows.addEventListener("change", (event) => {
  const row = event.target.closest("tr");
  if (!row) return;
  const id = row.dataset.id;
  if (event.target.classList.contains("include")) {
    api("/api/documents/update", { id, selected: event.target.checked }).catch(() => {});
  } else if (event.target.classList.contains("copies")) {
    const value = event.target.value;
    api("/api/documents/update", { id, copies: value === "" ? null : Number(value) }).catch(() => {});
  } else if (event.target.classList.contains("range")) {
    scheduleRange(id, event.target.value, 0);
  }
});

els.rows.addEventListener("click", (event) => {
  const row = event.target.closest("tr");
  if (!row || !row.dataset.id) return;
  if (event.target.closest(".remove")) {
    api("/api/documents/remove", { ids: [row.dataset.id] }).catch(() => {});
    return;
  }
  if (event.target.closest(".include, select, input")) return;
  pinPreview(row.dataset.id);
});

let dropDepth = 0;

function isFileDrag(event) {
  const types = event.dataTransfer && event.dataTransfer.types;
  if (!types) return false;
  return Array.from(types).includes("Files");
}

function setDropping(active) {
  document.body.classList.toggle("dropping", active);
  const overlay = document.getElementById("drop-overlay");
  if (overlay) overlay.setAttribute("aria-hidden", active ? "false" : "true");
}

function resetDrop() {
  dropDepth = 0;
  setDropping(false);
}

window.addEventListener("dragenter", (event) => {
  // Cancelling the drag is what stops the window from opening the files.
  event.preventDefault();
  if (!isFileDrag(event)) return;
  dropDepth += 1;
  setDropping(true);
}, true);

window.addEventListener("dragover", (event) => {
  event.preventDefault();
  if (!isFileDrag(event)) return;
  if (event.dataTransfer) event.dataTransfer.dropEffect = "copy";
  setDropping(true);
}, true);

window.addEventListener("dragleave", (event) => {
  if (!isFileDrag(event)) return;
  dropDepth = Math.max(0, dropDepth - 1);
  if (dropDepth === 0) resetDrop();
}, true);

window.addEventListener("drop", (event) => {
  event.preventDefault();
  const transfer = event.dataTransfer;
  const captured = captureDrop(transfer);
  resetDrop();
  if (!isFileDrag(event) && !captured.entries.length && !captured.loose.length) return;
  const failed = (error) => {
    view.dropText = "";
    showError(error.message || "Could not add the dropped files.");
  };
  if (!window.__spoolmateDrop) {
    addCapturedDrop(captured).catch(failed);
    return;
  }
  const tick = view.last ? Number(view.last.dropTick || 0) : 0;
  window.setTimeout(async () => {
    try {
      await refresh();
      if (view.last && Number(view.last.dropTick || 0) !== tick) return;
      await addCapturedDrop(captured);
    } catch (error) {
      failed(error);
    }
  }, 1000);
}, true);

window.addEventListener("blur", resetDrop);

function captureDrop(transfer) {
  const entries = [];
  const loose = [];
  const items = transfer && transfer.items ? Array.from(transfer.items) : [];
  for (const item of items) {
    const entry = item.webkitGetAsEntry && item.webkitGetAsEntry();
    if (entry) entries.push(entry);
    else {
      const file = item.getAsFile && item.getAsFile();
      if (file) loose.push({ relative: file.name, file });
    }
  }
  if (!entries.length && !loose.length && transfer && transfer.files) {
    for (const file of transfer.files) loose.push({ relative: file.webkitRelativePath || file.name, file });
  }
  return { entries, loose };
}

async function addCapturedDrop(captured) {
  if (view.last && view.last.job.running) {
    showError("Wait until this job finishes, or press Stop");
    return;
  }
  const found = captured.loose.slice();
  await Promise.all(captured.entries.map((entry) => walkEntry(entry, "", found)));
  if (!found.length) {
    showError("Nothing in that drop could be read. Use Add files.");
    return;
  }
  if (found.length > 500) {
    showError("That drop has too many files. Use Add folder for a large folder.");
    return;
  }
  const batch = crypto.randomUUID();
  const paths = [];
  for (let index = 0; index < found.length; index += 1) {
    const item = found[index];
    view.dropText = found.length > 1 ? `Adding dropped files… ${index + 1} of ${found.length}` : "Adding dropped files…";
    paintMessage();
    const response = await fetch("/api/drop", {
      method: "POST",
      headers: {
        "X-Drop-Batch": batch,
        "X-Drop-Name": encodeURIComponent(item.relative),
      },
      body: item.file,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || "Could not add the dropped files.");
    paths.push(data.path);
  }
  view.dropText = "";
  await api("/api/add", { paths });
}

function walkEntry(entry, prefix, found) {
  const relative = prefix ? `${prefix}/${entry.name}` : entry.name;
  if (entry.isFile) {
    return new Promise((resolve) => {
      entry.file((file) => {
        found.push({ relative, file });
        resolve();
      }, () => resolve());
    });
  }
  if (!entry.isDirectory) return Promise.resolve();
  return readEntries(entry.createReader()).then((entries) => (
    Promise.all(entries.map((child) => walkEntry(child, relative, found)))
  ));
}

function readEntries(reader) {
  return new Promise((resolve) => {
    const all = [];
    const read = () => {
      reader.readEntries((batch) => {
        if (!batch.length) resolve(all);
        else {
          all.push(...batch);
          read();
        }
      }, () => resolve(all));
    };
    read();
  });
}

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !els.warningModal.hidden) {
    dismissUnsupportedWarning();
    return;
  }
  if (event.key === "Escape" && !els.summary.hidden) {
    dismissSummary();
    return;
  }
  if (event.key === "Escape" && !els.settings.hidden) {
    els.settings.hidden = true;
    return;
  }
  if (els.settings.hidden === false || els.summary.hidden === false || els.warningModal.hidden === false) return;
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "o") {
    event.preventDefault();
    if (view.last && view.last.job.running) return;
    api(event.shiftKey ? "/api/pick/folder" : "/api/pick/files").catch(() => {});
  }
});

paintDuplex();
refresh();
setInterval(refresh, 400);
bindWindowChrome();

function bindWindowChrome() {
  const banner = document.querySelector(".app-banner");
  const call = (name) => {
    const api = window.pywebview && window.pywebview.api;
    if (!api || typeof api[name] !== "function") return null;
    return api[name]();
  };
  document.getElementById("win-min").addEventListener("click", () => call("minimize_window"));
  document.getElementById("win-close").addEventListener("click", () => call("close_window"));
  document.getElementById("win-max").addEventListener("click", async () => {
    const maximized = await call("toggle_maximize");
    if (maximized !== null) banner.classList.toggle("is-maximized", Boolean(maximized));
  });
  const drag = document.querySelector(".banner-drag");
  drag.addEventListener("dblclick", async () => {
    const maximized = await call("toggle_maximize");
    if (maximized !== null) banner.classList.toggle("is-maximized", Boolean(maximized));
  });
  let last = null;
  const onMove = (ev) => {
    if (!last) return;
    const api = window.pywebview && window.pywebview.api;
    if (!api || typeof api.nudge_window !== "function") return;
    const dx = ev.screenX - last.x;
    const dy = ev.screenY - last.y;
    last = { x: ev.screenX, y: ev.screenY };
    if (dx || dy) api.nudge_window(dx, dy);
  };
  const onUp = () => {
    last = null;
    window.removeEventListener("mousemove", onMove);
    window.removeEventListener("mouseup", onUp);
  };
  drag.addEventListener("mousedown", (ev) => {
    if (ev.button !== 0) return;
    last = { x: ev.screenX, y: ev.screenY };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  });
}
