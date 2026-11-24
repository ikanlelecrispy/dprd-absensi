const API_BASE = `${window.location.protocol}//${window.location.host}/api`;

const DEFAULT_LAT = -7.5561;
const DEFAULT_LNG = 110.8312;

const TAB_META = {
  logs: {
    title: "Presensi Harian",
    desc: "Pantau catatan kehadiran masuk, pulang, dan pemeriksaan kecocokan wajah."
  },
  reports: {
    title: "Rekap Laporan",
    desc: "Susun rekap kehadiran per peserta (Nama, Tanggal, Waktu Masuk & Pulang) dalam format CSV atau PDF A4."
  },
  participants: {
    title: "Peserta Magang",
    desc: "Kelola data peserta aktif, pendaftaran wajah, dan persetujuan UU PDP."
  },
  manual: {
    title: "Input Manual",
    desc: "Catat kehadiran peserta secara manual saat perangkat kamera bermasalah atau izin khusus."
  },
  locations: {
    title: "Lingkup Lokasi",
    desc: "Atur titik koordinat kantor dan radius jangkauan presensi berbasis GPS."
  },
  schedule: {
    title: "Jadwal Presensi",
    desc: "Tentukan batas jam operasional sesi masuk dan pulang pada layar kiosk."
  },
  admins: {
    title: "Akun Admin",
    desc: "Buat akun pengelola baru dan atur status akses ke dashboard admin."
  }
};

let activeTab = "logs";
let currentAdminUser = null;
let locationsCache = [];
let locMap = null;
let locMarker = null;
let locCircle = null;
let serverOffsetMs = 0;
let clockTimerId = null;
let lastModalTrigger = null;

async function apiFetch(url, options = {}) {
  const res = await fetch(url, {
    credentials: "same-origin",
    ...options
  });
  if (res.status === 401) {
    window.location.replace("/admin/login.html");
    throw new Error("Sesi admin telah berakhir.");
  }
  return res;
}

function escapeHtml(text) {
  if (text === null || text === undefined) return "";
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function showAdminToast(message, type = "info") {
  const stack = document.getElementById("toastStack");
  if (!stack) return;

  const toast = document.createElement("div");
  toast.className = `toast-item ${type === "success" ? "is-success" : type === "error" ? "is-error" : ""}`;
  toast.textContent = message;
  stack.appendChild(toast);

  window.setTimeout(() => {
    toast.remove();
  }, 4000);
}

function toggleMobileSidebar(forceOpen) {
  const sidebar = document.getElementById("adminSidebar");
  const backdrop = document.getElementById("sidebarBackdrop");
  const mobileBtn = document.getElementById("btnMobileMenu");
  if (!sidebar || !backdrop) return;

  const shouldOpen = typeof forceOpen === "boolean" ? forceOpen : !sidebar.classList.contains("is-open");
  sidebar.classList.toggle("is-open", shouldOpen);
  backdrop.classList.toggle("is-open", shouldOpen);
  if (mobileBtn) {
    mobileBtn.setAttribute("aria-expanded", String(shouldOpen));
  }
}

function toggleSidebarCollapse() {
  const sidebar = document.getElementById("adminSidebar");
  const toggleBtn = document.getElementById("btnSidebarToggle");
  if (!sidebar || !toggleBtn) return;

  sidebar.classList.remove("is-collapsing", "is-expanding");
  void sidebar.offsetWidth;

  const collapsed = sidebar.classList.toggle("is-collapsed");
  const expanded = !collapsed;
  sidebar.classList.add(collapsed ? "is-collapsing" : "is-expanding");
  toggleBtn.setAttribute("aria-expanded", String(expanded));
  toggleBtn.setAttribute("aria-label", expanded ? "Ciutkan bilah samping" : "Bentangkan menu navigasi");

  window.clearTimeout(sidebar._springTimer);
  sidebar._springTimer = window.setTimeout(() => {
    sidebar.classList.remove("is-collapsing", "is-expanding");
  }, 460);

  try {
    localStorage.setItem("adminSidebarCollapsed", String(collapsed));
  } catch (e) {
    // Abaikan jika penyimpanan lokal dibatasi
  }

  if (activeTab === "locations" && locMap) {
    window.setTimeout(() => {
      locMap.invalidateSize();
    }, 450);
  }
}

function showTab(tabName) {
  if (!TAB_META[tabName]) return;
  activeTab = tabName;

  Object.keys(TAB_META).forEach((key) => {
    const pane = document.getElementById(`tab-${key}`);
    const navBtn = document.getElementById(`btn-tab-${key}`);
    const isCurrent = key === tabName;

    if (pane) {
      pane.hidden = !isCurrent;
      pane.classList.toggle("is-active", isCurrent);
    }
    if (navBtn) {
      navBtn.classList.toggle("active", isCurrent);
      if (isCurrent) {
        navBtn.setAttribute("aria-current", "page");
      } else {
        navBtn.removeAttribute("aria-current");
      }
    }
  });

  const titleEl = document.getElementById("activeSectionTitle");
  const descEl = document.getElementById("activeSectionDesc");
  if (titleEl) titleEl.textContent = TAB_META[tabName].title;
  if (descEl) descEl.textContent = TAB_META[tabName].desc;

  toggleMobileSidebar(false);
  refreshCurrentView();
}

function refreshCurrentView() {
  if (activeTab === "logs") {
    loadStats();
    loadAttendanceLogs();
  } else if (activeTab === "reports") {
    initReportsTab();
  } else if (activeTab === "participants") {
    loadParticipants();
  } else if (activeTab === "manual") {
    loadParticipantsForManualDropdown();
  } else if (activeTab === "locations") {
    initLocationsTab();
  } else if (activeTab === "schedule") {
    loadScheduleSettings();
  } else if (activeTab === "admins") {
    loadAdminUsers();
  }
}

async function loadStats() {
  try {
    const res = await apiFetch(`${API_BASE}/admin/stats`);
    if (!res.ok) return;
    const data = await res.json();

    const activeEl = document.getElementById("statActiveParticipants");
    const inEl = document.getElementById("statCheckIns");
    const outEl = document.getElementById("statCheckOuts");
    const flagEl = document.getElementById("statFlagged");

    if (activeEl) activeEl.textContent = String(data.active_participants ?? 0);
    if (inEl) inEl.textContent = String(data.today_check_ins ?? 0);
    if (outEl) outEl.textContent = String(data.today_check_outs ?? 0);
    if (flagEl) flagEl.textContent = String(data.today_flagged ?? 0);
  } catch (err) {
    console.error("Gagal memuat ringkasan presensi:", err);
  }
}

async function loadAttendanceLogs() {
  const tbody = document.getElementById("logsTableBody");
  if (!tbody) return;

  tbody.innerHTML = '<tr><td colspan="7" class="table-state">Memuat catatan presensi...</td></tr>';

  const dateVal = document.getElementById("filterDate")?.value || "";
  const flaggedOnly = Boolean(document.getElementById("filterFlagged")?.checked);

  let url = `${API_BASE}/admin/attendance?only_flagged=${flaggedOnly}`;
  if (dateVal) {
    url += `&target_date=${encodeURIComponent(dateVal)}`;
  }

  try {
    const res = await apiFetch(url);
    if (!res.ok) {
      throw new Error("Server gagal memuat catatan presensi.");
    }
    const rows = await res.json();

    if (!Array.isArray(rows) || rows.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" class="table-state">Belum ada catatan presensi pada tanggal yang dipilih.</td></tr>';
      return;
    }

    tbody.innerHTML = rows.map((r) => {
      const isLeave = r.record_kind === "leave" || r.attendance_type === "Izin";
      let sessionBadge;
      if (isLeave) {
        sessionBadge = '<span class="status-pill pill-warning">Izin</span>';
      } else {
        const baseSessionPill = r.attendance_type === "Masuk"
          ? '<span class="status-pill pill-success">Masuk</span>'
          : '<span class="status-pill pill-info">Pulang</span>';
        const lateBadge = r.is_late
          ? `<span class="status-pill pill-warning">Terlambat ${escapeHtml(r.late_minutes || 0)} mnt</span>`
          : "";
        sessionBadge = lateBadge
          ? `<div class="cell-badge-stack">${baseSessionPill}${lateBadge}</div>`
          : baseSessionPill;
      }

      let methodBadge = '<span class="status-pill pill-neutral">Manual</span>';
      if (isLeave) {
        methodBadge = '<span class="status-pill pill-info">Pengajuan Mobile</span>';
      } else if (r.status === "FACE" || r.status === "verified") {
        const pct = r.similarity_score ? `${Math.round(r.similarity_score * 100)}%` : "Valid";
        const cls = r.is_suspicious ? "pill-warning" : "pill-info";
        methodBadge = `<span class="status-pill ${cls}">Wajah ${escapeHtml(pct)}</span>`;
      } else if (r.status === "PIN_FALLBACK" || r.status === "fallback_pin") {
        methodBadge = '<span class="status-pill pill-warning">PIN Pribadi</span>';
      }

      const locDetail = isLeave
        ? '<span class="cell-sub">Izin per hari</span>'
        : r.location_name
          ? `<span class="cell-sub">${escapeHtml(r.location_name)}${r.distance_meters !== null && r.distance_meters !== undefined ? ` (${r.distance_meters} m)` : ""}</span>`
          : '<span class="cell-sub">Tanpa lokasi GPS</span>';

      const photoCell = r.evidence_photo_url
        ? `<button type="button" class="thumb-btn" onclick="zoomPhoto('${escapeHtml(r.evidence_photo_url)}')" aria-label="Perbesar bukti foto ${escapeHtml(r.full_name)}">
             <img src="${escapeHtml(r.evidence_photo_url)}" alt="Foto ${escapeHtml(r.full_name)}" class="log-thumb" />
           </button>`
        : '<span class="cell-sub">-</span>';

      let noteHtml = '<span class="cell-sub">-</span>';
      if (r.is_suspicious && r.suspicious_reason) {
        noteHtml = `<span class="status-pill pill-warning">${escapeHtml(r.suspicious_reason)}</span>`;
      } else if (r.manual_reason) {
        noteHtml = `<span>${escapeHtml(r.manual_reason)}</span>`;
      }

      const safeName = JSON.stringify(r.full_name || "Peserta");
      const safeType = JSON.stringify(r.attendance_type || "");
      const safeLeaveDate = JSON.stringify(r.leave_date || "");
      const actionBtn = isLeave
        ? `<button type="button" class="btn btn-sm btn-subtle-danger" onclick='deleteLeaveRecord("${escapeHtml(r.id)}", ${safeName}, ${safeLeaveDate})'>Hapus</button>`
        : `<button type="button" class="btn btn-sm btn-subtle-danger" onclick='deleteAttendance("${escapeHtml(r.id)}", ${safeName}, ${safeType})'>Hapus</button>`;

      return `
        <tr>
          <td class="cell-mono">${escapeHtml(r.checked_at)}</td>
          <td>
            <span class="cell-strong">${escapeHtml(r.full_name)}</span>
            <span class="cell-sub">${escapeHtml(r.intern_id)} | ${escapeHtml(r.division)}</span>
          </td>
          <td>${sessionBadge}</td>
          <td>${methodBadge}${locDetail}</td>
          <td>${photoCell}</td>
          <td>${noteHtml}</td>
          <td class="col-action">${actionBtn}</td>
        </tr>
      `;
    }).join("");
  } catch (err) {
    tbody.innerHTML = '<tr><td colspan="7" class="table-state is-error">Gagal memuat data presensi. Periksa koneksi ke server.</td></tr>';
    console.error(err);
  }
}

async function deleteAttendance(attendanceId, participantName, attType) {
  const confirmed = window.confirm(
    `Hapus catatan presensi ${attType} milik ${participantName}? Tindakan ini tidak dapat dibatalkan.`
  );
  if (!confirmed) return;

  try {
    const res = await apiFetch(`${API_BASE}/admin/attendance/${encodeURIComponent(attendanceId)}`, {
      method: "DELETE"
    });
    const data = await res.json();

    if (!res.ok) {
      showAdminToast(data.detail || "Gagal menghapus catatan presensi.", "error");
      return;
    }

    showAdminToast(data.message || "Catatan presensi dihapus.", "success");
    loadStats();
    loadAttendanceLogs();
  } catch (err) {
    showAdminToast("Koneksi ke server terputus saat menghapus data.", "error");
  }
}

async function deleteLeaveRecord(leaveId, participantName, leaveDate) {
  const confirmed = window.confirm(
    `Hapus catatan izin harian milik ${participantName} pada tanggal ${leaveDate}? Tindakan ini tidak dapat dibatalkan.`
  );
  if (!confirmed) return;

  try {
    const res = await apiFetch(`${API_BASE}/admin/leaves/${encodeURIComponent(leaveId)}`, {
      method: "DELETE"
    });
    const data = await res.json();

    if (!res.ok) {
      showAdminToast(data.detail || "Gagal menghapus catatan izin.", "error");
      return;
    }

    showAdminToast(data.message || "Catatan izin harian dihapus.", "success");
    loadStats();
    loadAttendanceLogs();
  } catch (err) {
    showAdminToast("Koneksi ke server terputus saat menghapus izin.", "error");
  }
}

async function cleanDuplicatesToday() {
  const confirmed = window.confirm(
    "Bersihkan presensi ganda hari ini? Sistem menyisakan 1 catatan Masuk pertama dan 1 catatan Pulang terakhir per peserta."
  );
  if (!confirmed) return;

  try {
    const res = await apiFetch(`${API_BASE}/admin/attendance/duplicates/clean-today`, {
      method: "DELETE"
    });
    const data = await res.json();

    if (!res.ok) {
      showAdminToast(data.detail || "Gagal membersihkan presensi ganda.", "error");
      return;
    }

    showAdminToast(data.message || "Data presensi ganda hari ini dibersihkan.", "success");
    loadStats();
    loadAttendanceLogs();
  } catch (err) {
    showAdminToast("Koneksi ke server bermasalah.", "error");
  }
}

let reportsTabInitialized = false;

function formatIsoDateLocal(dateObj) {
  const y = dateObj.getFullYear();
  const m = String(dateObj.getMonth() + 1).padStart(2, "0");
  const d = String(dateObj.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function setReportDownloadEnabled(enabled) {
  const csvBtn = document.getElementById("btnDownloadReportCsv");
  const pdfBtn = document.getElementById("btnDownloadReportPdf");
  if (csvBtn) csvBtn.disabled = !enabled;
  if (pdfBtn) pdfBtn.disabled = !enabled;
}

function setReportPreset(presetKey, shouldReload = true) {
  const now = new Date();
  let startObj;
  let endObj;

  if (presetKey === "this_month") {
    startObj = new Date(now.getFullYear(), now.getMonth(), 1);
    endObj = new Date(now.getFullYear(), now.getMonth(), 30);
    const monthEnd = new Date(now.getFullYear(), now.getMonth() + 1, 0);
    if (endObj > monthEnd) endObj = monthEnd;
  } else if (presetKey === "prev_month") {
    startObj = new Date(now.getFullYear(), now.getMonth() - 1, 1);
    endObj = new Date(now.getFullYear(), now.getMonth() - 1, 30);
    const prevEnd = new Date(now.getFullYear(), now.getMonth(), 0);
    if (endObj > prevEnd) endObj = prevEnd;
  } else {
    endObj = now;
    startObj = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 29);
  }

  const startEl = document.getElementById("reportStartDate");
  const endEl = document.getElementById("reportEndDate");
  if (startEl) startEl.value = formatIsoDateLocal(startObj);
  if (endEl) endEl.value = formatIsoDateLocal(endObj);

  document.querySelectorAll(".report-preset-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.preset === presetKey);
  });

  if (shouldReload) {
    loadParticipantReportPreview();
  }
}

function onReportDateChange() {
  document.querySelectorAll(".report-preset-btn").forEach((btn) => btn.classList.remove("active"));
  loadParticipantReportPreview();
}

async function initReportsTab() {
  const startEl = document.getElementById("reportStartDate");
  const endEl = document.getElementById("reportEndDate");
  if (startEl && endEl && (!startEl.value || !endEl.value)) {
    setReportPreset("30d", false);
  }

  await loadParticipantsForReportDropdown();

  const select = document.getElementById("reportParticipantSelect");
  if (select && select.value) {
    await loadParticipantReportPreview();
  } else if (!reportsTabInitialized) {
    setReportDownloadEnabled(false);
  }
  reportsTabInitialized = true;
}

async function loadParticipantsForReportDropdown() {
  const select = document.getElementById("reportParticipantSelect");
  if (!select) return;

  const previousVal = select.value;

  try {
    const res = await apiFetch(`${API_BASE}/participants`);
    if (!res.ok) throw new Error("Gagal memuat daftar peserta.");
    const list = await res.json();

    if (!Array.isArray(list) || list.length === 0) {
      select.innerHTML = '<option value="">Belum ada peserta terdaftar</option>';
      setReportDownloadEnabled(false);
      const tbody = document.getElementById("reportPreviewTableBody");
      if (tbody) {
        tbody.innerHTML = '<tr><td colspan="6" class="table-state">Belum ada peserta terdaftar. Daftarkan peserta terlebih dahulu melalui menu Peserta Magang.</td></tr>';
      }
      return;
    }

    select.innerHTML = '<option value="">Pilih peserta magang...</option>' + list.map((p) => {
      const statusSuffix = p.status === "active" ? "" : ` [${p.status}]`;
      return `<option value="${escapeHtml(p.id)}">${escapeHtml(p.full_name)} (${escapeHtml(p.intern_id)})${escapeHtml(statusSuffix)}</option>`;
    }).join("");

    if (previousVal && list.some((p) => p.id === previousVal)) {
      select.value = previousVal;
    } else if (!previousVal && list.length > 0) {
      const firstActive = list.find((p) => p.status === "active");
      select.value = (firstActive || list[0]).id;
    }
  } catch (err) {
    select.innerHTML = '<option value="">Gagal memuat daftar peserta</option>';
    setReportDownloadEnabled(false);
  }
}

async function loadParticipantReportPreview() {
  const participantId = document.getElementById("reportParticipantSelect")?.value || "";
  const startVal = document.getElementById("reportStartDate")?.value || "";
  const endVal = document.getElementById("reportEndDate")?.value || "";
  const tbody = document.getElementById("reportPreviewTableBody");
  const summaryPanel = document.getElementById("reportSummaryPanel");
  const periodTag = document.getElementById("reportPeriodTag");
  const previewSub = document.getElementById("reportPreviewSubtitle");

  if (!tbody) return;

  if (!participantId) {
    setReportDownloadEnabled(false);
    if (summaryPanel) summaryPanel.hidden = true;
    if (periodTag) periodTag.hidden = true;
    if (previewSub) previewSub.textContent = "Pilih peserta untuk melihat pratinjau rekap sebelum mengunduh file.";
    tbody.innerHTML = '<tr><td colspan="6" class="table-state">Pilih peserta magang di atas untuk menampilkan rekap kehadiran.</td></tr>';
    return;
  }

  if (startVal && endVal && startVal > endVal) {
    setReportDownloadEnabled(false);
    if (summaryPanel) summaryPanel.hidden = true;
    tbody.innerHTML = '<tr><td colspan="6" class="table-state is-error">Tanggal mulai tidak boleh lebih besar dari tanggal selesai. Perbaiki rentang tanggal di atas.</td></tr>';
    return;
  }

  tbody.innerHTML = '<tr><td colspan="6" class="table-state">Memuat pratinjau rekap peserta...</td></tr>';
  setReportDownloadEnabled(false);

  const params = new URLSearchParams({ participant_id: participantId });
  if (startVal) params.set("start_date", startVal);
  if (endVal) params.set("end_date", endVal);

  try {
    const res = await apiFetch(`${API_BASE}/admin/reports/preview?${params.toString()}`);
    const data = await res.json();

    if (!res.ok) {
      throw new Error(data.detail || "Gagal memuat pratinjau rekap.");
    }

    const p = data.participant || {};
    const period = data.period || {};
    const sum = data.summary || {};
    const rows = Array.isArray(data.rows) ? data.rows : [];

    if (summaryPanel) summaryPanel.hidden = false;
    const setTxt = (id, val) => {
      const el = document.getElementById(id);
      if (el) el.textContent = String(val ?? "-");
    };

    setTxt("reportParticipantTitle", `${p.full_name || "-"} (${p.intern_id || "-"})`);
    setTxt("reportParticipantSub", `${p.division || "-"} | ${p.institution || "Instansi tidak diisi"}`);
    setTxt("reportPageEstimate", `${period.total_days || 0} hari | ${period.pdf_pages || 1} lembar A4`);

    setTxt("repStatTotalDays", sum.total_days ?? 0);
    setTxt("repStatPresent", sum.present_days ?? 0);
    setTxt("repStatOnTime", sum.on_time_days ?? 0);
    setTxt("repStatLate", sum.late_days ?? 0);
    setTxt("repStatLeave", sum.leave_days ?? 0);
    setTxt("repStatCheckOut", sum.check_out_days ?? 0);

    if (periodTag) {
      periodTag.textContent = `${period.start_date || "-"} s.d. ${period.end_date || "-"}`;
      periodTag.hidden = false;
    }
    if (previewSub) {
      previewSub.textContent = `Menampilkan ${rows.length} hari (${period.pdf_pages || 1} halaman A4, maks. ${period.rows_per_page || 30} hari per lembar).`;
    }

    if (rows.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="table-state">Tidak ada rentang tanggal untuk ditampilkan.</td></tr>';
      setReportDownloadEnabled(false);
      return;
    }

    const rowsPerPage = period.rows_per_page || 30;
    const htmlParts = [];
    rows.forEach((r, idx) => {
      if (rows.length > rowsPerPage && idx % rowsPerPage === 0) {
        const pageNum = Math.floor(idx / rowsPerPage) + 1;
        htmlParts.push(`
          <tr class="report-page-divider">
            <td colspan="6">Lembar A4 Halaman ${pageNum} (Hari ${idx + 1} s.d. ${Math.min(idx + rowsPerPage, rows.length)})</td>
          </tr>
        `);
      }

      let statusPill = '<span class="status-pill pill-neutral">-</span>';
      if (r.status_label === "Hadir") {
        statusPill = `<span class="status-pill pill-success">${escapeHtml(r.note)}</span>`;
      } else if (r.status_label === "Terlambat") {
        statusPill = `<span class="status-pill pill-warning">${escapeHtml(r.note)}</span>`;
      } else if (r.status_label === "Izin") {
        statusPill = `<span class="status-pill pill-info">${escapeHtml(r.note)}</span>`;
      } else if (r.status_label === "Pulang Saja") {
        statusPill = `<span class="status-pill pill-info">${escapeHtml(r.note)}</span>`;
      }

      htmlParts.push(`
        <tr>
          <td class="cell-mono">${escapeHtml(r.no)}</td>
          <td><span class="cell-strong">${escapeHtml(r.full_name)}</span></td>
          <td class="cell-mono">${escapeHtml(r.date_display)}</td>
          <td class="cell-mono">${escapeHtml(r.check_in_time)}</td>
          <td class="cell-mono">${escapeHtml(r.check_out_time)}</td>
          <td>${statusPill}</td>
        </tr>
      `);
    });

    tbody.innerHTML = htmlParts.join("");
    setReportDownloadEnabled(true);
  } catch (err) {
    if (summaryPanel) summaryPanel.hidden = true;
    if (periodTag) periodTag.hidden = true;
    setReportDownloadEnabled(false);
    tbody.innerHTML = `<tr><td colspan="6" class="table-state is-error">${escapeHtml(err.message || "Gagal memuat rekap laporan. Coba muat ulang.")}</td></tr>`;
  }
}

async function downloadParticipantReport(format) {
  const participantId = document.getElementById("reportParticipantSelect")?.value || "";
  const startVal = document.getElementById("reportStartDate")?.value || "";
  const endVal = document.getElementById("reportEndDate")?.value || "";

  if (!participantId) {
    showAdminToast("Pilih peserta magang terlebih dahulu.", "error");
    return;
  }

  const csvBtn = document.getElementById("btnDownloadReportCsv");
  const pdfBtn = document.getElementById("btnDownloadReportPdf");
  const activeBtn = format === "pdf" ? pdfBtn : csvBtn;
  const originalLabel = activeBtn ? activeBtn.textContent : "";

  if (csvBtn) csvBtn.disabled = true;
  if (pdfBtn) pdfBtn.disabled = true;
  if (activeBtn) activeBtn.textContent = format === "pdf" ? "Menyiapkan PDF..." : "Menyiapkan CSV...";

  const params = new URLSearchParams({
    participant_id: participantId,
    export_format: format
  });
  if (startVal) params.set("start_date", startVal);
  if (endVal) params.set("end_date", endVal);

  try {
    const res = await apiFetch(`${API_BASE}/admin/reports/export?${params.toString()}`);
    if (!res.ok) {
      let errMsg = `Gagal mengunduh file ${format.toUpperCase()}.`;
      try {
        const errData = await res.json();
        if (errData.detail) errMsg = errData.detail;
      } catch (e) {
        // Abaikan jika respons bukan JSON
      }
      showAdminToast(errMsg, "error");
      return;
    }

    const blob = await res.blob();
    const disposition = res.headers.get("Content-Disposition") || "";
    const match = disposition.match(/filename="?([^"]+)"?/i);
    const filename = match ? match[1] : `rekap_presensi.${format}`;

    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);

    showAdminToast(`File ${filename} berhasil diunduh.`, "success");
  } catch (err) {
    showAdminToast("Koneksi ke server terputus saat mengunduh laporan.", "error");
  } finally {
    if (activeBtn && originalLabel) activeBtn.textContent = originalLabel;
    setReportDownloadEnabled(Boolean(document.getElementById("reportParticipantSelect")?.value));
  }
}

function zoomPhoto(photoUrl) {
  const modal = document.getElementById("photoModal");
  const img = document.getElementById("zoomedImg");
  const closeBtn = document.getElementById("btnClosePhotoModal");
  if (!modal || !img) return;

  lastModalTrigger = document.activeElement;
  img.src = photoUrl;
  modal.hidden = false;
  if (closeBtn) closeBtn.focus();
}

function closePhotoModal(event) {
  const modal = document.getElementById("photoModal");
  const img = document.getElementById("zoomedImg");
  if (!modal) return;
  if (event && event.target !== modal) return;

  modal.hidden = true;
  if (img) img.src = "";
  if (lastModalTrigger && typeof lastModalTrigger.focus === "function") {
    lastModalTrigger.focus();
    lastModalTrigger = null;
  }
}

async function loadParticipants() {
  const tbody = document.getElementById("participantsTableBody");
  if (!tbody) return;

  tbody.innerHTML = '<tr><td colspan="6" class="table-state">Memuat daftar peserta...</td></tr>';

  try {
    const res = await apiFetch(`${API_BASE}/participants`);
    if (!res.ok) throw new Error("Gagal mengambil daftar peserta.");
    const list = await res.json();

    if (!Array.isArray(list) || list.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="table-state">Belum ada peserta terdaftar.</td></tr>';
      return;
    }

    tbody.innerHTML = list.map((p) => {
      const embCount = p.active_embeddings_count || 0;
      const faceBadge = embCount > 0
        ? `<span class="status-pill pill-success">${embCount} sampel wajah</span>`
        : '<span class="status-pill pill-warning">Belum rekam wajah</span>';

      let statusBadge = '<span class="status-pill pill-neutral">Nonaktif</span>';
      if (p.status === "active") {
        statusBadge = '<span class="status-pill pill-info">Aktif</span>';
      } else if (p.status === "completed") {
        statusBadge = '<span class="status-pill pill-success">Selesai</span>';
      }

      const safeName = JSON.stringify(p.full_name || "Peserta");
      const actionHtml = p.status === "active"
        ? `<button type="button" class="btn btn-sm btn-subtle-danger" onclick='deactivateParticipant("${escapeHtml(p.id)}", ${safeName})'>Nonaktifkan</button>`
        : '<span class="cell-sub">Biometrik dihapus</span>';

      return `
        <tr>
          <td class="cell-mono">${escapeHtml(p.intern_id)}</td>
          <td>
            <span class="cell-strong">${escapeHtml(p.full_name)}</span>
            <span class="cell-sub">${escapeHtml(p.institution || "Instansi tidak diisi")}</span>
          </td>
          <td class="cell-mono">${escapeHtml(p.internship_start)} s.d. ${escapeHtml(p.internship_end)}</td>
          <td>${faceBadge}</td>
          <td>${statusBadge}</td>
          <td class="col-action">${actionHtml}</td>
        </tr>
      `;
    }).join("");
  } catch (err) {
    tbody.innerHTML = '<tr><td colspan="6" class="table-state is-error">Gagal memuat daftar peserta.</td></tr>';
    console.error(err);
  }
}

async function deactivateParticipant(participantId, fullName) {
  const confirmed = window.confirm(
    `Nonaktifkan ${fullName}? Seluruh data vektor wajah akan dihapus permanen sesuai ketentuan UU PDP.`
  );
  if (!confirmed) return;

  try {
    const res = await apiFetch(`${API_BASE}/participants/${encodeURIComponent(participantId)}`, {
      method: "DELETE"
    });
    const data = await res.json();

    if (!res.ok) {
      showAdminToast(data.detail || "Gagal menonaktifkan peserta.", "error");
      return;
    }

    showAdminToast(data.message || "Peserta dinonaktifkan dan data wajah dihapus.", "success");
    loadParticipants();
    loadStats();
  } catch (err) {
    showAdminToast("Koneksi ke server bermasalah.", "error");
  }
}

async function loadParticipantsForManualDropdown() {
  const select = document.getElementById("manualParticipantSelect");
  if (!select) return;

  try {
    const res = await apiFetch(`${API_BASE}/participants?status_filter=active`);
    if (!res.ok) throw new Error("Gagal memuat peserta aktif.");
    const list = await res.json();

    if (!Array.isArray(list) || list.length === 0) {
      select.innerHTML = '<option value="">Belum ada peserta berstatus aktif</option>';
      return;
    }

    select.innerHTML = '<option value="">Pilih peserta magang...</option>' + list.map((p) => (
      `<option value="${escapeHtml(p.id)}">${escapeHtml(p.full_name)} (${escapeHtml(p.intern_id)})</option>`
    )).join("");
  } catch (err) {
    select.innerHTML = '<option value="">Gagal memuat peserta aktif</option>';
  }
}

async function submitManualAttendanceForm(event) {
  event.preventDefault();
  const form = event.target;
  const submitBtn = form.querySelector('button[type="submit"]');

  const payload = {
    participant_id: document.getElementById("manualParticipantSelect")?.value || "",
    attendance_type: document.getElementById("manualType")?.value || "check_in",
    admin_name: (document.getElementById("manualAdminName")?.value || "").trim(),
    manual_reason: (document.getElementById("manualReason")?.value || "").trim()
  };

  if (submitBtn) submitBtn.disabled = true;

  try {
    const res = await apiFetch(`${API_BASE}/admin/attendance/manual`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();

    if (!res.ok) {
      showAdminToast(data.detail || "Gagal menyimpan catatan manual.", "error");
      return;
    }

    showAdminToast(data.message || "Presensi manual berhasil dicatat.", "success");
    form.reset();
    loadStats();
  } catch (err) {
    showAdminToast("Koneksi ke server terputus.", "error");
  } finally {
    if (submitBtn) submitBtn.disabled = false;
  }
}

function initMapIfNeeded() {
  const mapEl = document.getElementById("locationMap");
  if (!mapEl || typeof L === "undefined") return;

  if (!locMap) {
    locMap = L.map("locationMap").setView([DEFAULT_LAT, DEFAULT_LNG], 16);

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap",
      maxZoom: 19
    }).addTo(locMap);

    locMarker = L.marker([DEFAULT_LAT, DEFAULT_LNG], { draggable: true }).addTo(locMap);
    locCircle = L.circle([DEFAULT_LAT, DEFAULT_LNG], {
      radius: 100,
      color: "#1D4ED8",
      weight: 2,
      fillColor: "#1D4ED8",
      fillOpacity: 0.14
    }).addTo(locMap);

    locMap.on("click", (ev) => {
      updateCoordsAndMap(ev.latlng.lat, ev.latlng.lng, true);
    });

    locMarker.on("dragend", () => {
      const pos = locMarker.getLatLng();
      updateCoordsAndMap(pos.lat, pos.lng, true);
    });
  }

  window.setTimeout(() => {
    if (locMap) locMap.invalidateSize();
  }, 160);
}

function updateCoordsAndMap(lat, lng, updateInputs = true, shouldPan = false) {
  const parsedLat = Number(lat);
  const parsedLng = Number(lng);
  if (Number.isNaN(parsedLat) || Number.isNaN(parsedLng)) return;

  if (updateInputs) {
    const latInput = document.getElementById("locLat");
    const lngInput = document.getElementById("locLng");
    if (latInput) latInput.value = parsedLat.toFixed(6);
    if (lngInput) lngInput.value = parsedLng.toFixed(6);
  }

  const previewEl = document.getElementById("mapCoordPreview");
  if (previewEl) {
    previewEl.textContent = `${parsedLat.toFixed(6)}, ${parsedLng.toFixed(6)}`;
  }

  if (locMarker) locMarker.setLatLng([parsedLat, parsedLng]);
  if (locCircle) locCircle.setLatLng([parsedLat, parsedLng]);
  if (locMap && shouldPan) locMap.panTo([parsedLat, parsedLng]);
}

function onCoordInputChange() {
  const latVal = parseFloat(document.getElementById("locLat")?.value || "");
  const lngVal = parseFloat(document.getElementById("locLng")?.value || "");
  if (!Number.isNaN(latVal) && !Number.isNaN(lngVal)) {
    updateCoordsAndMap(latVal, lngVal, false, true);
  }
}

function onRadiusSliderInput(radiusMeters) {
  const meters = parseInt(radiusMeters, 10) || 100;
  const label = document.getElementById("radiusValueLabel");
  if (label) {
    label.textContent = meters >= 1000 ? `${(meters / 1000).toFixed(2)} km (${meters} m)` : `${meters} meter`;
  }

  if (locCircle) {
    locCircle.setRadius(meters);
  }

  document.querySelectorAll(".preset-btn").forEach((btn) => {
    const match = btn.getAttribute("onclick") || "";
    btn.classList.toggle("active", match.includes(`(${meters})`));
  });
}

function setRadiusPreset(meters) {
  const slider = document.getElementById("locRadiusSlider");
  if (slider) {
    slider.value = String(meters);
  }
  onRadiusSliderInput(meters);
  fitMapToRadius();
}

function fitMapToRadius() {
  if (locMap && locCircle) {
    try {
      locMap.fitBounds(locCircle.getBounds(), { padding: [36, 36] });
    } catch (e) {
      // Abaikan jika peta belum memiliki ukuran
    }
  }
}

async function initLocationsTab() {
  initMapIfNeeded();
  await loadLocationsList();
}

async function loadLocationsList() {
  const container = document.getElementById("locationsList");
  const banner = document.getElementById("geofenceStatusBanner");
  const bannerTitle = document.getElementById("geofenceBannerTitle");
  const bannerDesc = document.getElementById("geofenceBannerDesc");
  if (!container) return;

  try {
    const res = await apiFetch(`${API_BASE}/locations`);
    if (!res.ok) throw new Error("Gagal mengambil daftar lokasi.");
    locationsCache = await res.json();

    const activeCount = locationsCache.filter((l) => l.is_active).length;
    if (banner && bannerTitle && bannerDesc) {
      banner.classList.toggle("is-active", activeCount > 0);
      if (activeCount > 0) {
        bannerTitle.textContent = `Pembatasan Lokasi Aktif (${activeCount} Titik)`;
        bannerDesc.textContent = "Peserta wajib berada di dalam radius titik yang aktif saat melakukan presensi.";
      } else {
        bannerTitle.textContent = "Pembatasan Lokasi Belum Diaktifkan";
        bannerDesc.textContent = "Semua presensi wajah diterima tanpa memeriksa radius GPS sampai minimal satu titik diaktifkan.";
      }
    }

    if (locationsCache.length === 0) {
      container.innerHTML = '<div class="inline-state">Belum ada titik lokasi tersimpan. Klik area peta untuk menentukan titik pertama.</div>';
      startNewLocation();
      return;
    }

    const currentLocId = document.getElementById("locId")?.value || "";
    container.innerHTML = locationsCache.map((loc) => {
      const selectedClass = currentLocId === loc.id ? "is-selected" : "";
      const activePill = loc.is_active
        ? '<span class="status-pill pill-success">Aktif</span>'
        : '<span class="status-pill pill-neutral">Nonaktif</span>';
      const safeLocName = JSON.stringify(loc.name || "Lokasi");

      return `
        <div class="loc-item ${selectedClass}">
          <button type="button" class="loc-item-main" onclick="selectLocationById('${escapeHtml(loc.id)}')">
            <span class="loc-item-title">${escapeHtml(loc.name)}</span>
            <span class="loc-item-meta">${loc.radius_meters} m | ${loc.latitude.toFixed(4)}, ${loc.longitude.toFixed(4)}</span>
          </button>
          <div class="loc-item-actions">
            ${activePill}
            <button type="button" class="btn btn-sm btn-subtle-danger" onclick='deleteLocation("${escapeHtml(loc.id)}", ${safeLocName})'>Hapus</button>
          </div>
        </div>
      `;
    }).join("");

    if (!currentLocId) {
      selectLocationById(locationsCache[0].id);
    }
  } catch (err) {
    container.innerHTML = '<div class="inline-state is-error">Gagal memuat daftar lokasi.</div>';
    console.error(err);
  }
}

function selectLocationById(locationId) {
  const loc = locationsCache.find((item) => item.id === locationId);
  if (!loc) return;

  const setVal = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.value = val;
  };

  setVal("locId", loc.id);
  setVal("locName", loc.name || "");
  setVal("locAddress", loc.address || "");
  setVal("locLat", loc.latitude);
  setVal("locLng", loc.longitude);
  setVal("locRadiusSlider", loc.radius_meters || 100);

  const activeBox = document.getElementById("locIsActive");
  if (activeBox) activeBox.checked = Boolean(loc.is_active);

  const titleEl = document.getElementById("locFormTitle");
  const modeBadge = document.getElementById("locModeBadge");
  if (titleEl) titleEl.textContent = "Sunting Titik Lokasi";
  if (modeBadge) {
    modeBadge.textContent = "Mode Sunting";
    modeBadge.className = "status-pill pill-warning";
  }

  updateCoordsAndMap(loc.latitude, loc.longitude, true, true);
  onRadiusSliderInput(loc.radius_meters || 100);
  fitMapToRadius();

  document.querySelectorAll(".loc-item").forEach((el) => {
    const matchBtn = el.querySelector(`button[onclick*="${locationId}"]`);
    el.classList.toggle("is-selected", Boolean(matchBtn));
  });
}

function startNewLocation() {
  const setVal = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.value = val;
  };

  setVal("locId", "");
  setVal("locName", "");
  setVal("locAddress", "");
  setVal("locLat", DEFAULT_LAT.toFixed(6));
  setVal("locLng", DEFAULT_LNG.toFixed(6));
  setVal("locRadiusSlider", "100");

  const activeBox = document.getElementById("locIsActive");
  if (activeBox) activeBox.checked = true;

  const titleEl = document.getElementById("locFormTitle");
  const modeBadge = document.getElementById("locModeBadge");
  if (titleEl) titleEl.textContent = "Titik Lokasi Baru";
  if (modeBadge) {
    modeBadge.textContent = "Mode Baru";
    modeBadge.className = "status-pill pill-info";
  }

  document.querySelectorAll(".loc-item").forEach((el) => el.classList.remove("is-selected"));
  updateCoordsAndMap(DEFAULT_LAT, DEFAULT_LNG, true, true);
  onRadiusSliderInput(100);
  fitMapToRadius();
}

function useMyCurrentLocation() {
  if (!navigator.geolocation) {
    showAdminToast("Browser tidak mendukung pembacaan GPS.", "error");
    return;
  }

  navigator.geolocation.getCurrentPosition(
    (pos) => {
      updateCoordsAndMap(pos.coords.latitude, pos.coords.longitude, true, true);
      fitMapToRadius();
      showAdminToast("Koordinat perangkat berhasil diterapkan.", "success");
    },
    (err) => {
      showAdminToast(`Gagal membaca koordinat GPS: ${err.message}`, "error");
    },
    { enableHighAccuracy: true, timeout: 10000 }
  );
}

async function searchAddress() {
  const input = document.getElementById("locSearchInput");
  const resultsEl = document.getElementById("locSearchResults");
  const query = (input?.value || "").trim();
  if (!query || !resultsEl) return;

  resultsEl.classList.remove("hidden");
  resultsEl.innerHTML = '<div class="inline-state">Mencari alamat pada peta...</div>';

  try {
    const url = `https://nominatim.openstreetmap.org/search?format=json&limit=5&countrycodes=id&q=${encodeURIComponent(query)}`;
    const res = await fetch(url);
    const items = await res.json();

    if (!Array.isArray(items) || items.length === 0) {
      resultsEl.innerHTML = '<div class="inline-state">Alamat tidak ditemukan. Coba kata kunci nama jalan atau gedung lain.</div>';
      return;
    }

    resultsEl.innerHTML = items.map((item) => {
      const safeDisplay = JSON.stringify(item.display_name || "");
      return `
        <button type="button" class="search-result-btn" onclick='pickSearchResult(${Number(item.lat)}, ${Number(item.lon)}, ${safeDisplay})'>
          ${escapeHtml(item.display_name)}
        </button>
      `;
    }).join("");
  } catch (err) {
    resultsEl.innerHTML = '<div class="inline-state is-error">Gagal menghubungi layanan pencarian alamat.</div>';
  }
}

function pickSearchResult(lat, lon, displayName) {
  const resultsEl = document.getElementById("locSearchResults");
  if (resultsEl) resultsEl.classList.add("hidden");

  const addrInput = document.getElementById("locAddress");
  const nameInput = document.getElementById("locName");
  if (addrInput) addrInput.value = displayName;
  if (nameInput && !nameInput.value.trim()) {
    nameInput.value = (displayName || "").split(",")[0].trim();
  }

  updateCoordsAndMap(lat, lon, true, true);
  fitMapToRadius();
}

async function saveLocationForm(event) {
  event.preventDefault();
  const form = event.target;
  const submitBtn = form.querySelector('button[type="submit"]');

  const locId = (document.getElementById("locId")?.value || "").trim();
  const payload = {
    name: (document.getElementById("locName")?.value || "").trim(),
    address: (document.getElementById("locAddress")?.value || "").trim() || null,
    latitude: parseFloat(document.getElementById("locLat")?.value || ""),
    longitude: parseFloat(document.getElementById("locLng")?.value || ""),
    radius_meters: parseInt(document.getElementById("locRadiusSlider")?.value || "100", 10),
    is_active: Boolean(document.getElementById("locIsActive")?.checked)
  };

  if (Number.isNaN(payload.latitude) || Number.isNaN(payload.longitude)) {
    showAdminToast("Koordinat latitude dan longitude wajib berupa angka valid.", "error");
    return;
  }

  if (submitBtn) submitBtn.disabled = true;

  try {
    const endpoint = locId ? `${API_BASE}/locations/${encodeURIComponent(locId)}` : `${API_BASE}/locations`;
    const method = locId ? "PUT" : "POST";
    const res = await apiFetch(endpoint, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();

    if (!res.ok) {
      showAdminToast(data.detail || "Gagal menyimpan titik lokasi.", "error");
      return;
    }

    const idEl = document.getElementById("locId");
    if (idEl && data.id) idEl.value = data.id;

    showAdminToast(locId ? "Titik lokasi berhasil diperbarui." : "Titik lokasi baru berhasil ditambahkan.", "success");
    await loadLocationsList();
    if (data.id) selectLocationById(data.id);
  } catch (err) {
    showAdminToast("Koneksi ke server terputus saat menyimpan lokasi.", "error");
  } finally {
    if (submitBtn) submitBtn.disabled = false;
  }
}

async function deleteLocation(locationId, locationName) {
  const confirmed = window.confirm(`Hapus titik lokasi "${locationName}" dari database?`);
  if (!confirmed) return;

  try {
    const res = await apiFetch(`${API_BASE}/locations/${encodeURIComponent(locationId)}`, {
      method: "DELETE"
    });
    if (!res.ok) {
      showAdminToast("Gagal menghapus titik lokasi.", "error");
      return;
    }

    const currentId = document.getElementById("locId")?.value || "";
    if (currentId === locationId) {
      const idEl = document.getElementById("locId");
      if (idEl) idEl.value = "";
    }

    showAdminToast(`Titik lokasi "${locationName}" dihapus.`, "success");
    await loadLocationsList();
  } catch (err) {
    showAdminToast("Koneksi ke server bermasalah.", "error");
  }
}

function updateLiveServerClock() {
  const clockEl = document.getElementById("schedServerClock");
  if (!clockEl) return;

  const now = new Date(Date.now() + serverOffsetMs);
  const hh = String(now.getHours()).padStart(2, "0");
  const mm = String(now.getMinutes()).padStart(2, "0");
  const ss = String(now.getSeconds()).padStart(2, "0");
  clockEl.textContent = `${hh}:${mm}:${ss} WIB`;
}

function applyScheduleStatusUI(data) {
  const banner = document.getElementById("scheduleStatusBanner");
  const titleEl = document.getElementById("schedLiveTitle");
  const descEl = document.getElementById("schedLiveDesc");
  if (!banner || !titleEl || !descEl) return;

  banner.classList.remove("is-open", "is-closed");
  banner.classList.add(data.is_open ? "is-open" : "is-closed");

  titleEl.textContent = data.label || "Status Jadwal";
  descEl.textContent = data.message || "Mengikuti waktu server pusat.";

  if (data.server_time_ms) {
    serverOffsetMs = data.server_time_ms - Date.now();
  }
  updateLiveServerClock();

  if (!clockTimerId) {
    clockTimerId = window.setInterval(updateLiveServerClock, 1000);
  }
}

const SCHEDULE_FIELDS = [
  "schedCheckInStart",
  "schedCheckInEnd",
  "schedCheckOutStart",
  "schedCheckOutEnd"
];

function initScheduleDropdowns() {
  const hours = Array.from({ length: 24 }, (_, i) => String(i).padStart(2, "0"));
  const mins = Array.from({ length: 60 }, (_, i) => String(i).padStart(2, "0"));

  SCHEDULE_FIELDS.forEach((prefix) => {
    const hSel = document.getElementById(`${prefix}Hour`);
    const mSel = document.getElementById(`${prefix}Min`);
    if (hSel && hSel.options.length === 0) {
      hSel.innerHTML = hours.map((h) => `<option value="${h}">${h}</option>`).join("");
    }
    if (mSel && mSel.options.length === 0) {
      mSel.innerHTML = mins.map((m) => `<option value="${m}">${m}</option>`).join("");
    }
  });
}

function setTimeDropdownValue(prefix, hhmm) {
  const parts = String(hhmm || "00:00").split(":");
  const hh = (parts[0] || "00").padStart(2, "0");
  const mm = (parts[1] || "00").padStart(2, "0");
  const hSel = document.getElementById(`${prefix}Hour`);
  const mSel = document.getElementById(`${prefix}Min`);
  if (hSel) hSel.value = hh;
  if (mSel) mSel.value = mm;
}

function getTimeDropdownValue(prefix, fallback = "06:00") {
  const hSel = document.getElementById(`${prefix}Hour`);
  const mSel = document.getElementById(`${prefix}Min`);
  if (!hSel || !mSel || !hSel.value || !mSel.value) return fallback;
  return `${hSel.value}:${mSel.value}`;
}

async function loadScheduleSettings() {
  initScheduleDropdowns();
  try {
    const res = await apiFetch(`${API_BASE}/schedule/current`);
    if (!res.ok) throw new Error("Gagal mengambil pengaturan jadwal.");
    const data = await res.json();

    if (data.schedule) {
      setTimeDropdownValue("schedCheckInStart", data.schedule.check_in_start);
      setTimeDropdownValue("schedCheckInEnd", data.schedule.check_in_end);
      setTimeDropdownValue("schedCheckOutStart", data.schedule.check_out_start);
      setTimeDropdownValue("schedCheckOutEnd", data.schedule.check_out_end);
    }

    applyScheduleStatusUI(data);
  } catch (err) {
    console.error("Gagal memuat jadwal:", err);
  }
}

async function saveScheduleForm(event) {
  event.preventDefault();
  const form = event.target;
  const submitBtn = form.querySelector('button[type="submit"]');

  const payload = {
    check_in_start: getTimeDropdownValue("schedCheckInStart", "06:00"),
    check_in_end: getTimeDropdownValue("schedCheckInEnd", "09:00"),
    check_out_start: getTimeDropdownValue("schedCheckOutStart", "14:00"),
    check_out_end: getTimeDropdownValue("schedCheckOutEnd", "16:00")
  };

  if (submitBtn) submitBtn.disabled = true;

  try {
    const res = await apiFetch(`${API_BASE}/schedule`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();

    if (!res.ok) {
      showAdminToast(data.detail || "Gagal memperbarui jadwal.", "error");
      return;
    }

    showAdminToast("Jadwal presensi berhasil diperbarui.", "success");
    await loadScheduleSettings();
  } catch (err) {
    showAdminToast("Koneksi ke server terputus.", "error");
  } finally {
    if (submitBtn) submitBtn.disabled = false;
  }
}

function resetScheduleDefault() {
  initScheduleDropdowns();
  const defaults = {
    schedCheckInStart: "06:00",
    schedCheckInEnd: "09:00",
    schedCheckOutStart: "14:00",
    schedCheckOutEnd: "16:00"
  };

  Object.entries(defaults).forEach(([prefix, val]) => {
    setTimeDropdownValue(prefix, val);
  });

  showAdminToast("Jam bawaan 06:00-09:00 dan 14:00-16:00 diisikan. Tekan Simpan Jadwal untuk menerapkan.", "info");
}

function toggleAdminPasswordField(inputId, btnEl) {
  const input = document.getElementById(inputId);
  if (!input || !btnEl) return;

  const show = input.type === "password";
  input.type = show ? "text" : "password";
  btnEl.textContent = show ? "Sembunyikan" : "Tampilkan";
  btnEl.setAttribute("aria-pressed", String(show));
}

async function checkAdminSession() {
  try {
    const res = await fetch(`${API_BASE}/auth/me`, {
      credentials: "same-origin"
    });
    if (!res.ok) {
      window.location.replace("/admin/login.html");
      return false;
    }
    const data = await res.json();
    currentAdminUser = data.user || null;

    const nameEl = document.getElementById("currentAdminName");
    const roleEl = document.getElementById("currentAdminRole");
    if (nameEl && currentAdminUser) nameEl.textContent = currentAdminUser.full_name;
    if (roleEl && currentAdminUser) roleEl.textContent = currentAdminUser.role === "superadmin" ? "Superadmin" : "Admin";

    document.body.classList.remove("auth-checking");
    return true;
  } catch (err) {
    window.location.replace("/admin/login.html");
    return false;
  }
}

async function logoutAdmin() {
  try {
    await fetch(`${API_BASE}/auth/logout`, {
      method: "POST",
      credentials: "same-origin"
    });
  } catch (e) {
    // Tetap arahkan keluar ke halaman login
  }
  window.location.replace("/admin/login.html");
}

async function loadAdminUsers() {
  const tbody = document.getElementById("adminUsersTableBody");
  if (!tbody) return;

  tbody.innerHTML = '<tr><td colspan="6" class="table-state">Memuat daftar akun admin...</td></tr>';

  try {
    const res = await apiFetch(`${API_BASE}/admin/users`);
    if (!res.ok) throw new Error("Gagal mengambil daftar akun admin.");
    const list = await res.json();

    if (!Array.isArray(list) || list.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="table-state">Belum ada akun admin terdaftar.</td></tr>';
      return;
    }

    tbody.innerHTML = list.map((u) => {
      const isSelf = Boolean(currentAdminUser && currentAdminUser.id === u.id);
      const rolePill = u.role === "superadmin"
        ? '<span class="status-pill pill-info">Superadmin</span>'
        : '<span class="status-pill pill-neutral">Admin</span>';
      const statusPill = u.is_active
        ? '<span class="status-pill pill-success">Aktif</span>'
        : '<span class="status-pill pill-warning">Nonaktif</span>';

      const selfTag = isSelf ? ' <span class="status-pill pill-info">Anda</span>' : "";
      const safeName = JSON.stringify(u.full_name || "Admin");
      const toggleLabel = u.is_active ? "Nonaktifkan" : "Aktifkan";
      const actionHtml = isSelf
        ? '<span class="cell-sub">Sesi aktif</span>'
        : `<div class="row-actions-inline">
             <button type="button" class="btn btn-sm btn-secondary" onclick='toggleAdminUserStatus("${escapeHtml(u.id)}", ${Boolean(u.is_active)}, ${safeName})'>${toggleLabel}</button>
             <button type="button" class="btn btn-sm btn-subtle-danger" onclick='deleteAdminUser("${escapeHtml(u.id)}", ${safeName})'>Hapus</button>
           </div>`;

      return `
        <tr>
          <td>
            <span class="cell-strong">${escapeHtml(u.full_name)}${selfTag}</span>
            <span class="cell-sub">${escapeHtml(u.email)}</span>
          </td>
          <td class="cell-mono">${escapeHtml(u.username)}</td>
          <td>${rolePill}</td>
          <td class="cell-mono">${escapeHtml(u.last_login || "Belum pernah")}</td>
          <td>${statusPill}</td>
          <td class="col-action">${actionHtml}</td>
        </tr>
      `;
    }).join("");
  } catch (err) {
    tbody.innerHTML = '<tr><td colspan="6" class="table-state is-error">Gagal memuat daftar akun admin.</td></tr>';
    console.error(err);
  }
}

async function createAdminUserForm(event) {
  event.preventDefault();
  const form = event.target;
  const submitBtn = form.querySelector('button[type="submit"]');

  const payload = {
    full_name: (document.getElementById("newAdminFullName")?.value || "").trim(),
    email: (document.getElementById("newAdminEmail")?.value || "").trim(),
    password: document.getElementById("newAdminPassword")?.value || "",
    role: document.getElementById("newAdminRole")?.value || "admin"
  };

  if (submitBtn) submitBtn.disabled = true;

  try {
    const res = await apiFetch(`${API_BASE}/admin/users`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();

    if (!res.ok) {
      showAdminToast(data.detail || "Gagal membuat akun admin baru.", "error");
      return;
    }

    showAdminToast(data.message || "Akun admin baru berhasil dibuat.", "success");
    form.reset();
    await loadAdminUsers();
  } catch (err) {
    showAdminToast("Koneksi ke server bermasalah.", "error");
  } finally {
    if (submitBtn) submitBtn.disabled = false;
  }
}

async function toggleAdminUserStatus(userId, currentlyActive, fullName) {
  const actionWord = currentlyActive ? "nonaktifkan" : "aktifkan kembali";
  const confirmed = window.confirm(`${currentlyActive ? "Nonaktifkan" : "Aktifkan"} akses akun ${fullName}?`);
  if (!confirmed) return;

  try {
    const res = await apiFetch(`${API_BASE}/admin/users/${encodeURIComponent(userId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_active: !currentlyActive })
    });
    const data = await res.json();

    if (!res.ok) {
      showAdminToast(data.detail || `Gagal ${actionWord} akun.`, "error");
      return;
    }

    showAdminToast(data.message || "Status akun admin diperbarui.", "success");
    await loadAdminUsers();
  } catch (err) {
    showAdminToast("Koneksi ke server bermasalah.", "error");
  }
}

async function deleteAdminUser(userId, fullName) {
  const confirmed = window.confirm(`Hapus permanen akun admin "${fullName}"?`);
  if (!confirmed) return;

  try {
    const res = await apiFetch(`${API_BASE}/admin/users/${encodeURIComponent(userId)}`, {
      method: "DELETE"
    });
    const data = await res.json();

    if (!res.ok) {
      showAdminToast(data.detail || "Gagal menghapus akun admin.", "error");
      return;
    }

    showAdminToast(data.message || "Akun admin dihapus.", "success");
    await loadAdminUsers();
  } catch (err) {
    showAdminToast("Koneksi ke server bermasalah.", "error");
  }
}

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;

  const modal = document.getElementById("photoModal");
  if (modal && !modal.hidden) {
    closePhotoModal();
    return;
  }

  const sidebar = document.getElementById("adminSidebar");
  if (sidebar && sidebar.classList.contains("is-open")) {
    toggleMobileSidebar(false);
  }
});

function getLocalIsoDate(dateObj = new Date()) {
  return new Date(dateObj.getTime() - dateObj.getTimezoneOffset() * 60000).toISOString().split("T")[0];
}

let activeAdminDateIso = getLocalIsoDate();

document.addEventListener("DOMContentLoaded", async () => {
  try {
    const savedCollapse = localStorage.getItem("adminSidebarCollapsed");
    if (savedCollapse === "false" && window.innerWidth >= 768) {
      const sidebar = document.getElementById("adminSidebar");
      const toggleBtn = document.getElementById("btnSidebarToggle");
      if (sidebar) sidebar.classList.remove("is-collapsed");
      if (toggleBtn) {
        toggleBtn.setAttribute("aria-expanded", "true");
        toggleBtn.setAttribute("aria-label", "Ciutkan bilah samping");
      }
    } else if (window.innerWidth < 768) {
      const sidebar = document.getElementById("adminSidebar");
      if (sidebar) sidebar.classList.remove("is-collapsed");
    }
  } catch (e) {
    // Abaikan jika penyimpanan lokal tidak tersedia
  }

  const ok = await checkAdminSession();
  if (!ok) return;

  initScheduleDropdowns();

  activeAdminDateIso = getLocalIsoDate();
  const filterDate = document.getElementById("filterDate");
  if (filterDate && !filterDate.value) {
    filterDate.value = activeAdminDateIso;
  }

  loadStats();
  loadAttendanceLogs();

  window.setInterval(() => {
    const todayIso = getLocalIsoDate();
    if (todayIso !== activeAdminDateIso) {
      const currentFilter = document.getElementById("filterDate");
      if (currentFilter && (!currentFilter.value || currentFilter.value === activeAdminDateIso)) {
        currentFilter.value = todayIso;
        loadAttendanceLogs();
      }
      activeAdminDateIso = todayIso;
      loadStats();
    }
  }, 30000);
});
