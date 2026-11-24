const API_BASE = `${window.location.protocol}//${window.location.host}/api`;
const STORAGE_KEY = "dprd_leave_selected_student_id";

let participantsList = [];
let currentStudentId = "";
let currentPortalData = null;
let defaultServerDate = "";
let activeDashboardPanel = "leave";
let historyMode = "leaves";

function showAlert(id, message) {
  const el = document.getElementById(id);
  if (!el) return;
  if (!message) {
    el.hidden = true;
    el.textContent = "";
    return;
  }
  el.textContent = message;
  el.hidden = false;
}

function updateReasonCounter() {
  const textarea = document.getElementById("leaveReasonInput");
  const counter = document.getElementById("reasonCharCount");
  if (!textarea || !counter) return;
  counter.textContent = `${textarea.value.length}/500`;
}

function renderStudentOptions(filterText = "") {
  const select = document.getElementById("loginParticipantSelect");
  const hint = document.getElementById("loginCountHint");
  const btn = document.getElementById("btnEnterPortal");
  if (!select) return;

  const q = filterText.trim().toLowerCase();
  const filtered = q
    ? participantsList.filter((p) => (
      p.full_name.toLowerCase().includes(q)
      || p.intern_id.toLowerCase().includes(q)
      || p.division.toLowerCase().includes(q)
    ))
    : participantsList;

  if (participantsList.length === 0) {
    select.innerHTML = '<option value="">Belum ada mahasiswa berstatus aktif</option>';
    select.disabled = true;
    if (btn) btn.disabled = true;
    if (hint) hint.textContent = "Daftar kosong. Hubungi admin untuk mengaktifkan peserta.";
    return;
  }

  if (filtered.length === 0) {
    select.innerHTML = '<option value="">Nama tidak ditemukan pada pencarian</option>';
    select.disabled = false;
    if (btn) btn.disabled = true;
    if (hint) hint.textContent = "Ubah kata kunci pencarian nama atau ID magang.";
    return;
  }

  select.innerHTML = '<option value="">Pilih nama Anda...</option>' + filtered.map((p) => {
    const opt = document.createElement("option");
    opt.value = p.id;
    opt.textContent = `${p.full_name} (${p.intern_id})`;
    return opt.outerHTML;
  }).join("");

  if (filtered.length === 1) {
    select.value = filtered[0].id;
  }
  select.disabled = false;
  if (btn) btn.disabled = false;
  if (hint) {
    hint.textContent = `${filtered.length} peserta aktif tersedia.`;
  }
}

function filterStudentDropdown() {
  const searchVal = document.getElementById("loginSearchInput")?.value || "";
  renderStudentOptions(searchVal);
}

async function loadActiveParticipants() {
  const searchInput = document.getElementById("loginSearchInput");
  const select = document.getElementById("loginParticipantSelect");
  const btn = document.getElementById("btnEnterPortal");
  if (searchInput) searchInput.disabled = true;
  if (select) select.disabled = true;
  if (btn) btn.disabled = true;
  showAlert("loginErrorAlert", "");

  try {
    const res = await fetch(`${API_BASE}/leaves/participants`, { cache: "no-store" });
    if (!res.ok) throw new Error("Gagal memuat daftar mahasiswa aktif.");
    const data = await res.json();

    participantsList = Array.isArray(data.participants) ? data.participants : [];
    defaultServerDate = data.server_date || "";
    renderStudentOptions();
    if (searchInput) searchInput.disabled = participantsList.length === 0;

    const savedId = window.sessionStorage.getItem(STORAGE_KEY) || "";
    if (savedId && participantsList.some((p) => p.id === savedId)) {
      await openStudentDashboard(savedId);
    }
  } catch (err) {
    if (searchInput) searchInput.disabled = false;
    if (select) select.innerHTML = '<option value="">Gagal memuat daftar mahasiswa</option>';
    showAlert("loginErrorAlert", err.message || "Tidak dapat terhubung ke server.");
  }
}

async function enterStudentPortal(event) {
  event.preventDefault();
  showAlert("loginErrorAlert", "");

  const selectedId = document.getElementById("loginParticipantSelect")?.value || "";
  if (!selectedId) {
    showAlert("loginErrorAlert", "Silakan pilih nama Anda terlebih dahulu.");
    document.getElementById("loginParticipantSelect")?.focus();
    return;
  }

  await openStudentDashboard(selectedId);
}

async function openStudentDashboard(participantId) {
  const btn = document.getElementById("btnEnterPortal");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Memuat Profil...";
  }

  try {
    const res = await fetch(`${API_BASE}/leaves/student/${encodeURIComponent(participantId)}`, {
      cache: "no-store"
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Gagal memuat data peserta.");
    }

    currentStudentId = participantId;
    currentPortalData = data;
    window.sessionStorage.setItem(STORAGE_KEY, participantId);

    renderDashboard(data);
    applyDashboardPanelState(activeDashboardPanel);

    const viewLogin = document.getElementById("viewLogin");
    const viewDash = document.getElementById("viewDashboard");
    if (viewLogin) viewLogin.hidden = true;
    if (viewDash) viewDash.hidden = false;
    window.scrollTo({ top: 0, behavior: "auto" });
    document.querySelector(".dash-scroll-area")?.scrollTo({ top: 0, behavior: "auto" });
  } catch (err) {
    window.sessionStorage.removeItem(STORAGE_KEY);
    showAlert("loginErrorAlert", err.message || "Gagal membuka halaman izin mahasiswa.");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Masuk";
    }
  }
}

function renderDashboard(data) {
  const p = data.participant || {};
  const today = data.today || {};
  const m = data.month_summary || {};

  const setText = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.textContent = val || "-";
  };

  setText("dashAvatarInitials", p.initials || "--");
  setText("dashStudentName", p.full_name || "-");
  setText("dashInternId", `${p.intern_id || "-"} | Aktif`);
  setText("dashDivisionBadge", p.division || "-");
  setText("dashPeriod", p.internship_period || "-");
  setText("dashPresentCount", `${m.present_days ?? 0} Hari`);
  setText("dashLeaveCount", `${m.leave_days ?? 0} Hari`);
  setText("dashTodayStatus", today.status_label || "-");
  setText("dashTodayDateChip", data.server_date_display || "-");

  const dateInput = document.getElementById("leaveDateInput");
  if (dateInput && data.server_date && !dateInput.value) {
    dateInput.value = data.server_date;
  }

  const todayBanner = document.getElementById("dashTodayBanner");
  if (todayBanner) {
    if (today.status_code === "present") {
      const jam = today.check_in_time ? ` pukul ${today.check_in_time}` : "";
      todayBanner.textContent = `Anda sudah tercatat hadir hari ini${jam}. Pengajuan izin tanggal lain tetap tersedia di bawah.`;
      todayBanner.hidden = false;
    } else if (today.status_code === "leave") {
      todayBanner.textContent = `Anda sudah tercatat izin hari ini: "${today.leave_reason || "-"}".`;
      todayBanner.hidden = false;
    } else {
      todayBanner.hidden = true;
      todayBanner.textContent = "";
    }
  }

  renderHistoryFeed();
}

function renderHistoryFeed() {
  const listEl = document.getElementById("historyFeedList");
  const titleEl = document.getElementById("historySectionTitle");
  if (!listEl || !currentPortalData) return;

  if (historyMode === "attendance") {
    if (titleEl) titleEl.textContent = "Riwayat Presensi Terbaru";

    const items = Array.isArray(currentPortalData.recent_attendances)
      ? currentPortalData.recent_attendances
      : [];
    if (items.length === 0) {
      listEl.innerHTML = '<div class="surface-card empty-state-card">Belum ada catatan presensi masuk atau pulang.</div>';
      return;
    }

    listEl.innerHTML = items.map((item) => {
      const badgeCls = item.is_late ? "feed-icon-badge is-warn" : "feed-icon-badge";
      const badgeTxt = item.attendance_type === "Masuk" ? "IN" : "OUT";
      const desc = item.is_late
        ? `Presensi ${item.attendance_type} (Terlambat ${item.late_minutes} menit)`
        : `Presensi ${item.attendance_type} tercatat`;

      const card = document.createElement("article");
      card.className = "feed-card";
      card.innerHTML = `
        <div class="${badgeCls}" aria-hidden="true">${badgeTxt}</div>
        <div class="feed-body">
          <div class="feed-top">
            <span class="feed-title"></span>
            <span class="feed-date mono-text"></span>
          </div>
          <p class="feed-desc"></p>
        </div>
      `;
      card.querySelector(".feed-title").textContent = item.date_display;
      card.querySelector(".feed-date").textContent = item.time_str;
      card.querySelector(".feed-desc").textContent = desc;
      return card.outerHTML;
    }).join("");
    return;
  }

  if (titleEl) titleEl.textContent = "Riwayat Izin Terbaru";

  const leaves = Array.isArray(currentPortalData.recent_leaves)
    ? currentPortalData.recent_leaves
    : [];
  if (leaves.length === 0) {
    listEl.innerHTML = '<div class="surface-card empty-state-card">Belum ada riwayat pengajuan izin untuk peserta ini.</div>';
    return;
  }

  listEl.innerHTML = leaves.map((lv) => {
    const card = document.createElement("article");
    card.className = "feed-card";
    card.innerHTML = `
      <div class="feed-icon-badge is-warn" aria-hidden="true">IZIN</div>
      <div class="feed-body">
        <div class="feed-top">
          <span class="feed-title"></span>
          <span class="feed-date mono-text"></span>
        </div>
        <p class="feed-desc"></p>
      </div>
    `;
    card.querySelector(".feed-title").textContent = lv.leave_date_display;
    card.querySelector(".feed-date").textContent = lv.submitted_at;
    card.querySelector(".feed-desc").textContent = lv.reason;
    return card.outerHTML;
  }).join("");
}

function applyDashboardPanelState(panel) {
  activeDashboardPanel = panel || "leave";
  const leaveSection = document.getElementById("dashLeaveSection");
  const historySection = document.getElementById("dashHistorySection");
  const activeTile = document.querySelector(`.quick-tile[data-panel="${activeDashboardPanel}"]`);

  document.querySelectorAll(".quick-tile[data-panel]").forEach((el) => {
    const isCurrent = el === activeTile;
    el.classList.toggle("is-active", isCurrent);
    el.setAttribute("aria-pressed", String(isCurrent));
  });

  if (activeDashboardPanel === "leave") {
    if (leaveSection) leaveSection.hidden = false;
    if (historySection) historySection.hidden = true;
    return;
  }

  if (leaveSection) leaveSection.hidden = true;
  if (historySection) historySection.hidden = false;
  historyMode = activeDashboardPanel === "attendance_history" ? "attendance" : "leaves";
  renderHistoryFeed();
}

function switchDashboardFocus(panel) {
  applyDashboardPanelState(panel);

  const scrollArea = document.querySelector(".dash-scroll-area");
  if (scrollArea) {
    scrollArea.scrollTo({ top: 0, behavior: "smooth" });
  }
}

function logoutToSelectScreen() {
  currentStudentId = "";
  currentPortalData = null;
  activeDashboardPanel = "leave";
  historyMode = "leaves";
  window.sessionStorage.removeItem(STORAGE_KEY);

  const form = document.getElementById("leaveForm");
  if (form) form.reset();
  updateReasonCounter();
  showAlert("leaveErrorAlert", "");
  showAlert("leaveSuccessAlert", "");

  const viewDash = document.getElementById("viewDashboard");
  const viewLogin = document.getElementById("viewLogin");
  if (viewDash) viewDash.hidden = true;
  if (viewLogin) viewLogin.hidden = false;

  const searchInput = document.getElementById("loginSearchInput");
  if (searchInput) searchInput.value = "";
  renderStudentOptions("");
  window.scrollTo({ top: 0, behavior: "auto" });
  document.getElementById("loginParticipantSelect")?.focus();
}

async function submitLeaveForm(event) {
  event.preventDefault();
  showAlert("leaveErrorAlert", "");
  showAlert("leaveSuccessAlert", "");

  if (!currentStudentId) {
    logoutToSelectScreen();
    return;
  }

  const leaveDate = document.getElementById("leaveDateInput")?.value || "";
  const reason = (document.getElementById("leaveReasonInput")?.value || "").trim();
  const submitBtn = document.getElementById("btnSubmitLeave");

  if (reason.length < 5) {
    showAlert("leaveErrorAlert", "Alasan izin wajib diisi minimal 5 karakter.");
    document.getElementById("leaveReasonInput")?.focus();
    return;
  }

  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.textContent = "Menyimpan Izin...";
  }

  try {
    const res = await fetch(`${API_BASE}/leaves`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        participant_id: currentStudentId,
        leave_date: leaveDate || null,
        reason
      })
    });
    const data = await res.json();

    if (!res.ok) {
      showAlert("leaveErrorAlert", data.detail || "Gagal mencatat izin harian.");
      return;
    }

    showAlert(
      "leaveSuccessAlert",
      `Izin tanggal ${data.leave_date_display || data.leave_date} berhasil masuk ke absensi (${data.reason}).`
    );

    const textarea = document.getElementById("leaveReasonInput");
    if (textarea) textarea.value = "";
    updateReasonCounter();

    activeDashboardPanel = "leave";
    await openStudentDashboard(currentStudentId);
  } catch (err) {
    showAlert("leaveErrorAlert", "Koneksi ke server bermasalah. Periksa jaringan lalu coba lagi.");
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.textContent = "Kirim Izin Harian";
    }
  }
}

document.addEventListener("DOMContentLoaded", () => {
  updateReasonCounter();
  loadActiveParticipants();
});
