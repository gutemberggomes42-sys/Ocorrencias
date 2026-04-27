const LEGACY_STORAGE_KEY = "industria_boletins_ocorrencia_v1";
const API_BASE = location.protocol === "file:" ? "http://127.0.0.1:8080/api" : "/api";

const form = document.querySelector("#occurrenceForm");
const fields = {
  id: document.querySelector("#recordId"),
  dataOcorrencia: document.querySelector("#dataOcorrencia"),
  horaOcorrencia: document.querySelector("#horaOcorrencia"),
  turno: document.querySelector("#turno"),
  status: document.querySelector("#status"),
  unidade: document.querySelector("#unidade"),
  setor: document.querySelector("#setor"),
  local: document.querySelector("#local"),
  tipo: document.querySelector("#tipo"),
  gravidade: document.querySelector("#gravidade"),
  parada: document.querySelector("#parada"),
  registradoPor: document.querySelector("#registradoPor"),
  envolvidos: document.querySelector("#envolvidos"),
  responsavel: document.querySelector("#responsavel"),
  prazo: document.querySelector("#prazo"),
  descricao: document.querySelector("#descricao"),
  acaoImediata: document.querySelector("#acaoImediata"),
  causaProvavel: document.querySelector("#causaProvavel"),
  acaoCorretiva: document.querySelector("#acaoCorretiva"),
  observacoes: document.querySelector("#observacoes")
};

const recordsTable = document.querySelector("#recordsTable");
const emptyState = document.querySelector("#emptyState");
const resultCount = document.querySelector("#resultCount");
const recordCode = document.querySelector("#recordCode");
const formTitle = document.querySelector("#formTitle");
const searchInput = document.querySelector("#searchInput");
const filterStatus = document.querySelector("#filterStatus");
const filterGravidade = document.querySelector("#filterGravidade");
const filterTipo = document.querySelector("#filterTipo");
const toast = document.querySelector("#toast");
const importFile = document.querySelector("#importFile");
const photosInput = document.querySelector("#photosInput");
const detailsDialog = document.querySelector("#detailsDialog");
const detailsTitle = document.querySelector("#detailsTitle");
const detailsContent = document.querySelector("#detailsContent");
const editFromDetailsBtn = document.querySelector("#editFromDetailsBtn");

let records = [];
let apiOnline = false;
let activeDetailsId = null;

const iconTemplates = {
  view: '<svg viewBox="0 0 24 24"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/></svg>',
  edit: '<svg viewBox="0 0 24 24"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/></svg>',
  done: '<svg viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5"/></svg>',
  trash: '<svg viewBox="0 0 24 24"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 15H6L5 6"/><path d="M10 11v6M14 11v6"/></svg>'
};

async function apiRequest(path, options = {}) {
  const isFormData = options.body instanceof FormData;
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: isFormData ? (options.headers || {}) : {
      "Content-Type": "application/json",
      ...(options.headers || {})
    }
  });

  const text = await response.text();
  const payload = text ? JSON.parse(text) : null;

  if (!response.ok) {
    throw new Error(payload?.error || "Falha ao comunicar com o banco de dados.");
  }

  return payload;
}

async function loadRecords() {
  records = await apiRequest("/records");
  apiOnline = true;
}

async function migrateLegacyLocalStorage() {
  if (location.protocol !== "file:" || records.length > 0) return;

  const raw = localStorage.getItem(LEGACY_STORAGE_KEY);
  if (!raw) return;

  try {
    const legacy = JSON.parse(raw);
    if (!Array.isArray(legacy) || legacy.length === 0) return;
    records = await apiRequest("/records", {
      method: "PUT",
      body: JSON.stringify(legacy)
    });
    showToast("Dados antigos migrados para o banco SQLite.");
  } catch {
    showToast("Não foi possível migrar os dados antigos do navegador.");
  }
}

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

function nowTime() {
  return new Date().toTimeString().slice(0, 5);
}

function uid() {
  if (crypto.randomUUID) return crypto.randomUUID();
  return `id-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function slug(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

function makeCode(dateValue) {
  const year = (dateValue || todayIso()).slice(0, 4);
  const sameYearCodes = records
    .map((record) => record.codigo)
    .filter((code) => code && code.startsWith(`BO-${year}-`))
    .map((code) => Number(code.split("-").pop()))
    .filter(Number.isFinite);
  const next = sameYearCodes.length ? Math.max(...sameYearCodes) + 1 : 1;
  return `BO-${year}-${String(next).padStart(4, "0")}`;
}

function formatDate(value) {
  if (!value) return "-";
  const [year, month, day] = value.split("-");
  if (!year || !month || !day) return value;
  return `${day}/${month}/${year}`;
}

function formatDateTime(record) {
  const date = formatDate(record.dataOcorrencia);
  return record.horaOcorrencia ? `${date} ${record.horaOcorrencia}` : date;
}

function normalize(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

function isClosed(record) {
  return ["Concluído", "Concluido", "Cancelado"].includes(record.status);
}

function isLate(record) {
  return Boolean(record.prazo && !isClosed(record) && record.prazo < todayIso());
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("is-visible");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    toast.classList.remove("is-visible");
  }, 3000);
}

function resetForm() {
  form.reset();
  fields.id.value = "";
  fields.dataOcorrencia.value = todayIso();
  fields.horaOcorrencia.value = nowTime();
  fields.status.value = "Aberto";
  fields.parada.value = "0";
  photosInput.value = "";
  recordCode.textContent = "BO novo";
  formTitle.textContent = "Novo boletim";
}

function getFormRecord() {
  const existing = records.find((record) => record.id === fields.id.value);
  const data = Object.fromEntries(
    Object.entries(fields).map(([key, element]) => [key, element.value.trim()])
  );

  const now = new Date().toISOString();
  return {
    id: data.id || uid(),
    codigo: existing?.codigo || makeCode(data.dataOcorrencia),
    dataOcorrencia: data.dataOcorrencia,
    horaOcorrencia: data.horaOcorrencia,
    turno: data.turno,
    status: data.status,
    unidade: data.unidade,
    setor: data.setor,
    local: data.local,
    tipo: data.tipo,
    gravidade: data.gravidade,
    parada: Number(data.parada || 0),
    registradoPor: data.registradoPor,
    envolvidos: data.envolvidos,
    responsavel: data.responsavel,
    prazo: data.prazo,
    descricao: data.descricao,
    acaoImediata: data.acaoImediata,
    causaProvavel: data.causaProvavel,
    acaoCorretiva: data.acaoCorretiva,
    observacoes: data.observacoes,
    createdAt: existing?.createdAt || now,
    updatedAt: now
  };
}

function applyRecordToForm(record) {
  fields.id.value = record.id;
  fields.dataOcorrencia.value = record.dataOcorrencia || todayIso();
  fields.horaOcorrencia.value = record.horaOcorrencia || nowTime();
  fields.turno.value = record.turno || "";
  fields.status.value = record.status || "Aberto";
  fields.unidade.value = record.unidade || "";
  fields.setor.value = record.setor || "";
  fields.local.value = record.local || "";
  fields.tipo.value = record.tipo || "";
  fields.gravidade.value = record.gravidade || "";
  fields.parada.value = record.parada ?? 0;
  fields.registradoPor.value = record.registradoPor || "";
  fields.envolvidos.value = record.envolvidos || "";
  fields.responsavel.value = record.responsavel || "";
  fields.prazo.value = record.prazo || "";
  fields.descricao.value = record.descricao || "";
  fields.acaoImediata.value = record.acaoImediata || "";
  fields.causaProvavel.value = record.causaProvavel || "";
  fields.acaoCorretiva.value = record.acaoCorretiva || "";
  fields.observacoes.value = record.observacoes || "";
  photosInput.value = "";
  recordCode.textContent = record.codigo;
  formTitle.textContent = `Editando ${record.codigo}`;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function getFilteredRecords() {
  const query = normalize(searchInput.value);
  return records
    .filter((record) => {
      const haystack = normalize([
        record.codigo,
        record.dataOcorrencia,
        record.setor,
        record.local,
        record.tipo,
        record.gravidade,
        record.status,
        record.responsavel,
        record.registradoPor,
        record.descricao,
        record.acaoCorretiva
      ].join(" "));

      return (
        (!query || haystack.includes(query)) &&
        (!filterStatus.value || record.status === filterStatus.value) &&
        (!filterGravidade.value || record.gravidade === filterGravidade.value) &&
        (!filterTipo.value || record.tipo === filterTipo.value)
      );
    })
    .sort((a, b) => {
      const aTime = `${a.dataOcorrencia || ""}T${a.horaOcorrencia || "00:00"}`;
      const bTime = `${b.dataOcorrencia || ""}T${b.horaOcorrencia || "00:00"}`;
      return bTime.localeCompare(aTime);
    });
}

function renderMetrics() {
  document.querySelector("#metricTotal").textContent = records.length;
  document.querySelector("#metricOpen").textContent = records.filter((record) => record.status === "Aberto").length;
  document.querySelector("#metricProgress").textContent = records.filter((record) => record.status === "Em tratamento").length;
  document.querySelector("#metricCritical").textContent = records.filter((record) => ["Alta", "Crítica", "Critica"].includes(record.gravidade)).length;
  document.querySelector("#metricLate").textContent = records.filter(isLate).length;
}

function renderTable() {
  const filtered = getFilteredRecords();
  resultCount.textContent = `${filtered.length} ${filtered.length === 1 ? "item" : "itens"}`;
  emptyState.classList.toggle("is-visible", filtered.length === 0);

  recordsTable.innerHTML = filtered.map((record) => {
    const late = isLate(record);
    return `
      <tr data-id="${escapeHtml(record.id)}">
        <td><strong>${escapeHtml(record.codigo)}</strong></td>
        <td>${escapeHtml(formatDateTime(record))}</td>
        <td>${escapeHtml(record.setor || "-")}<br><span class="muted">${escapeHtml(record.local || "")}</span></td>
        <td>${escapeHtml(record.tipo || "-")}</td>
        <td><span class="badge gravity-${slug(record.gravidade)}">${escapeHtml(record.gravidade || "-")}</span></td>
        <td><span class="badge status-${slug(record.status)}">${escapeHtml(record.status || "-")}</span></td>
        <td>${late ? '<span class="badge late">Atrasado</span>' : escapeHtml(formatDate(record.prazo))}</td>
        <td>${Number(record.photoCount || 0)}</td>
        <td>
          <div class="row-actions">
            <button class="icon-btn" type="button" data-action="view" aria-label="Ver ${escapeHtml(record.codigo)}" title="Ver">${iconTemplates.view}</button>
            <button class="icon-btn" type="button" data-action="edit" aria-label="Editar ${escapeHtml(record.codigo)}" title="Editar">${iconTemplates.edit}</button>
            <button class="icon-btn" type="button" data-action="done" aria-label="Concluir ${escapeHtml(record.codigo)}" title="Concluir">${iconTemplates.done}</button>
            <button class="icon-btn" type="button" data-action="delete" aria-label="Excluir ${escapeHtml(record.codigo)}" title="Excluir">${iconTemplates.trash}</button>
          </div>
        </td>
      </tr>
    `;
  }).join("");
}

function render() {
  renderMetrics();
  renderTable();
}

async function refreshRecords() {
  await loadRecords();
  render();
}

async function upsertRecord(record) {
  const saved = await apiRequest("/records", {
    method: "POST",
    body: JSON.stringify(record)
  });
  const index = records.findIndex((item) => item.id === saved.id);
  if (index >= 0) {
    records[index] = saved;
  } else {
    records.unshift(saved);
  }
  render();
  return saved;
}

async function uploadPhotos(recordId, fileList) {
  const files = Array.from(fileList || []);
  if (!files.length) return [];

  const formData = new FormData();
  files.forEach((file) => formData.append("photos", file));
  return apiRequest(`/records/${encodeURIComponent(recordId)}/photos`, {
    method: "POST",
    body: formData
  });
}

function findRecord(id) {
  return records.find((record) => record.id === id);
}

function detailItem(label, value, full = false) {
  return `
    <div class="detail-item ${full ? "full" : ""}">
      <span>${escapeHtml(label)}</span>
      <p>${escapeHtml(value || "-")}</p>
    </div>
  `;
}

function photoUrl(photo) {
  if (!photo?.url) return "";
  if (!photo.url.startsWith("/")) return photo.url;
  if (API_BASE.startsWith("http")) return API_BASE.replace(/\/api$/, "") + photo.url;
  return photo.url;
}

function renderPhotoGallery(record) {
  const photos = record.photos || [];
  if (!photos.length) {
    return detailItem("Fotos", "Nenhuma foto anexada", true);
  }

  return `
    <div class="detail-item full">
      <span>Fotos</span>
      <div class="photo-gallery">
        ${photos.map((photo) => `
          <figure class="photo-card">
            <img src="${escapeHtml(photoUrl(photo))}" alt="${escapeHtml(photo.filename || "Foto da ocorrência")}">
            <button class="icon-btn" type="button" data-photo-delete="${escapeHtml(photo.id)}" aria-label="Excluir foto" title="Excluir foto">${iconTemplates.trash}</button>
            <figcaption class="photo-caption">${escapeHtml(photo.filename || "Foto")}</figcaption>
          </figure>
        `).join("")}
      </div>
    </div>
  `;
}

function showDetails(record) {
  activeDetailsId = record.id;
  detailsTitle.textContent = record.codigo;
  detailsContent.innerHTML = `
    <div class="details-grid">
      ${detailItem("Data e hora", formatDateTime(record))}
      ${detailItem("Status", record.status)}
      ${detailItem("Turno", record.turno)}
      ${detailItem("Gravidade", record.gravidade)}
      ${detailItem("Unidade", record.unidade)}
      ${detailItem("Setor", record.setor)}
      ${detailItem("Local", record.local)}
      ${detailItem("Tipo", record.tipo)}
      ${detailItem("Registrado por", record.registradoPor)}
      ${detailItem("Envolvidos", record.envolvidos)}
      ${detailItem("Responsável", record.responsavel)}
      ${detailItem("Prazo", formatDate(record.prazo))}
      ${detailItem("Parada", `${record.parada || 0} min`)}
      ${detailItem("Criado em", record.createdAt ? new Date(record.createdAt).toLocaleString("pt-BR") : "-")}
      ${detailItem("Descrição", record.descricao, true)}
      ${detailItem("Ação imediata", record.acaoImediata, true)}
      ${detailItem("Causa provável", record.causaProvavel, true)}
      ${detailItem("Ação corretiva / preventiva", record.acaoCorretiva, true)}
      ${detailItem("Observações", record.observacoes, true)}
      ${renderPhotoGallery(record)}
    </div>
  `;
  if (!detailsDialog.open) {
    detailsDialog.showModal();
  }
}

function downloadFile(filename, content, type) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function exportJson() {
  const stamp = todayIso();
  downloadFile(`boletins-ocorrencia-${stamp}.json`, JSON.stringify(records, null, 2), "application/json;charset=utf-8");
  showToast("Arquivo JSON exportado.");
}

function csvCell(value) {
  return `"${String(value ?? "").replace(/"/g, '""')}"`;
}

function exportCsv() {
  const headers = [
    "Codigo",
    "Data",
    "Hora",
    "Turno",
    "Status",
    "Unidade",
    "Setor",
    "Local",
    "Tipo",
    "Gravidade",
    "Parada min",
    "Registrado por",
    "Envolvidos",
    "Responsavel",
    "Prazo",
    "Descricao",
    "Acao imediata",
    "Causa provavel",
    "Acao corretiva",
    "Observacoes"
  ];
  const rows = records.map((record) => [
    record.codigo,
    record.dataOcorrencia,
    record.horaOcorrencia,
    record.turno,
    record.status,
    record.unidade,
    record.setor,
    record.local,
    record.tipo,
    record.gravidade,
    record.parada,
    record.registradoPor,
    record.envolvidos,
    record.responsavel,
    record.prazo,
    record.descricao,
    record.acaoImediata,
    record.causaProvavel,
    record.acaoCorretiva,
    record.observacoes
  ]);
  const csv = [headers, ...rows].map((row) => row.map(csvCell).join(";")).join("\n");
  downloadFile(`boletins-ocorrencia-${todayIso()}.csv`, csv, "text/csv;charset=utf-8");
  showToast("Arquivo CSV exportado.");
}

async function importJsonFile(file) {
  const reader = new FileReader();
  reader.onload = async () => {
    try {
      const imported = JSON.parse(reader.result);
      if (!Array.isArray(imported)) {
        throw new Error("Formato inválido");
      }
      const ok = window.confirm("Importar este JSON vai substituir os registros atuais do banco. Deseja continuar?");
      if (!ok) return;

      const cleaned = imported
        .filter((record) => record && typeof record === "object")
        .map((record) => ({
          ...record,
          id: record.id || uid(),
          codigo: record.codigo || "",
          createdAt: record.createdAt || new Date().toISOString(),
          updatedAt: new Date().toISOString()
        }));

      records = await apiRequest("/records", {
        method: "PUT",
        body: JSON.stringify(cleaned)
      });
      render();
      resetForm();
      showToast("Dados importados para o banco.");
    } catch (error) {
      showToast(error.message || "Não foi possível importar o arquivo.");
    } finally {
      importFile.value = "";
    }
  };
  reader.readAsText(file);
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!form.checkValidity()) {
    form.reportValidity();
    return;
  }

  if (!apiOnline) {
    showToast("Banco de dados offline. Inicie o servidor pelo start.bat.");
    return;
  }

  try {
    const selectedPhotos = Array.from(photosInput.files || []);
    const saved = await upsertRecord(getFormRecord());
    if (selectedPhotos.length) {
      await uploadPhotos(saved.id, selectedPhotos);
      await refreshRecords();
    }
    showToast(`${saved.codigo} salvo no banco${selectedPhotos.length ? " com fotos" : ""}.`);
    resetForm();
  } catch (error) {
    showToast(error.message || "Não foi possível salvar.");
  }
});

document.querySelector("#newRecordBtn").addEventListener("click", resetForm);
document.querySelector("#clearFormBtn").addEventListener("click", resetForm);
document.querySelector("#exportJsonBtn").addEventListener("click", exportJson);
document.querySelector("#exportCsvBtn").addEventListener("click", exportCsv);
document.querySelector("#importBtn").addEventListener("click", () => importFile.click());
document.querySelector("#printBtn").addEventListener("click", () => window.print());
document.querySelector("#closeDetailsBtn").addEventListener("click", () => detailsDialog.close());
document.querySelector("#printDetailsBtn").addEventListener("click", () => {
  document.body.classList.add("printing-details");
  window.print();
});

window.addEventListener("afterprint", () => {
  document.body.classList.remove("printing-details");
});

editFromDetailsBtn.addEventListener("click", () => {
  const record = findRecord(activeDetailsId);
  if (record) {
    detailsDialog.close();
    applyRecordToForm(record);
  }
});

detailsContent.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-photo-delete]");
  if (!button) return;

  const ok = window.confirm("Excluir esta foto do banco de dados?");
  if (!ok) return;

  try {
    await apiRequest(`/photos/${encodeURIComponent(button.dataset.photoDelete)}`, { method: "DELETE" });
    await refreshRecords();
    const record = findRecord(activeDetailsId);
    if (record) showDetails(record);
    showToast("Foto excluída.");
  } catch (error) {
    showToast(error.message || "Não foi possível excluir a foto.");
  }
});

importFile.addEventListener("change", () => {
  const [file] = importFile.files;
  if (file) importJsonFile(file);
});

[searchInput, filterStatus, filterGravidade, filterTipo].forEach((control) => {
  control.addEventListener("input", renderTable);
});

recordsTable.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;

  const row = button.closest("tr");
  const record = findRecord(row.dataset.id);
  if (!record) return;

  if (button.dataset.action === "view") {
    showDetails(record);
  }

  if (button.dataset.action === "edit") {
    applyRecordToForm(record);
  }

  if (button.dataset.action === "done") {
    if (["Concluído", "Concluido"].includes(record.status)) {
      showToast(`${record.codigo} já está concluído.`);
      return;
    }
    try {
      await upsertRecord({ ...record, status: "Concluído", updatedAt: new Date().toISOString() });
      showToast(`${record.codigo} concluído.`);
    } catch (error) {
      showToast(error.message || "Não foi possível concluir.");
    }
  }

  if (button.dataset.action === "delete") {
    const ok = window.confirm(`Excluir ${record.codigo} do banco? Esta ação não pode ser desfeita.`);
    if (!ok) return;
    try {
      await apiRequest(`/records/${encodeURIComponent(record.id)}`, { method: "DELETE" });
      records = records.filter((item) => item.id !== record.id);
      render();
      showToast(`${record.codigo} excluído do banco.`);
    } catch (error) {
      showToast(error.message || "Não foi possível excluir.");
    }
  }
});

async function init() {
  resetForm();
  try {
    await loadRecords();
    await migrateLegacyLocalStorage();
    render();
    showToast("Banco conectado.");
  } catch {
    apiOnline = false;
    records = [];
    render();
    showToast("Banco offline. Execute start.bat para salvar em SQLite.");
  }
}

init();
