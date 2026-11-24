// Kiosk Controller - DPRD Kota Surakarta
// Arsitektur Satu Pintu Berbasis Kamera & Jadwal Server

const video = document.getElementById("kioskVideo");
const canvas = document.getElementById("overlayCanvas");
const ctx = canvas.getContext("2d");

const cameraInactiveState = document.getElementById("cameraInactiveState");
const cameraActiveHud = document.getElementById("cameraActiveHud");
const cameraSubStatus = document.getElementById("cameraSubStatus");
const hudFeedModeLabel = document.getElementById("hudFeedModeLabel");

const btnActivateCamera = document.getElementById("btnActivateCamera");
const iconActivateWrap = document.getElementById("iconActivateWrap");
const labelActivateCamera = document.getElementById("labelActivateCamera");

const btnStartAttendance = document.getElementById("btnStartAttendance");
const labelStartAttendance = document.getElementById("labelStartAttendance");

const sessionIndicator = document.getElementById("sessionIndicator");
const sessionLabel = document.getElementById("sessionLabel");
const sessionScheduleMeta = document.getElementById("sessionScheduleMeta");

const statusCard = document.getElementById("statusCard");
const statusIconBox = document.getElementById("statusIconBox");
const statusTitle = document.getElementById("statusTitle");
const statusSubtitle = document.getElementById("statusSubtitle");
const guideSteps = document.getElementById("guideSteps");
const btnFallback = document.getElementById("btnFallback");

const readyScheduleVal = document.getElementById("readyScheduleVal");
const readyLocationVal = document.getElementById("readyLocationVal");
const readyCameraVal = document.getElementById("readyCameraVal");

let currentStream = null;
let isCameraActive = false;
let isVerifying = false;
let isShowingTempResult = false;
let failedAttempts = 0;
let lastModalTrigger = null;
let lastPopoverTrigger = null;
let lastNavMenuTrigger = null;
let lastPanduanTrigger = null;

// State GPS Geolocation & Geofence aktif dari server
let currentCoords = { latitude: null, longitude: null, accuracy: null };
let activeLocationConfig = { enforced: false, locations: [] };

// State Jadwal & Waktu Server
let serverTimeOffsetMs = 0;
let activeLogDateKey = "";
let currentSession = {
  session_code: "closed",
  is_open: false,
  label: "Memuat jadwal server...",
  short_label: "Tutup",
  message: "Menghubungkan ke server...",
  schedule: null,
};

// SVG Inline Ikon Fungsional
const ICONS = {
  camera: '<svg class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>',
  cameraOff: '<svg class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><line x1="2" y1="2" x2="22" y2="22"/><path d="M7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16"/><path d="M9.5 4h5L17 7h3a2 2 0 0 1 2 2v7.34"/><path d="M14.12 14.12a3 3 0 1 1-4.24-4.24"/></svg>',
  info: '<svg class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>',
  check: '<svg class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true"><polyline points="20 6 9 17 4 12"/></svg>',
  alert: '<svg class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>',
  lock: '<svg class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>',
  menu: '<svg class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>',
  close: '<svg class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
  expand: '<svg class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/></svg>',
  collapse: '<svg class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M4 14h6v6M20 10h-6V4M14 10l7-7M10 14l-7 7"/></svg>',
};

// ============================================================
// 0. TOAST & AUDIO CHIME
// ============================================================
function showToast(message, type = "info") {
  const container = document.getElementById("toastContainer");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = `toast-item toast-item-${type}`;
  toast.innerHTML = `<span class="toast-dot" aria-hidden="true"></span><span></span>`;
  toast.querySelector("span:last-child").textContent = message;

  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    setTimeout(() => toast.remove(), 250);
  }, 3500);
}

const audioCtx = new (window.AudioContext || window.webkitAudioContext)();

function playChime(type) {
  if (audioCtx.state === "suspended") {
    audioCtx.resume();
  }
  const osc = audioCtx.createOscillator();
  const gain = audioCtx.createGain();
  osc.connect(gain);
  gain.connect(audioCtx.destination);

  const now = audioCtx.currentTime;
  if (type === "success") {
    osc.frequency.setValueAtTime(523.25, now);
    osc.frequency.setValueAtTime(659.25, now + 0.1);
    osc.frequency.setValueAtTime(783.99, now + 0.2);
    gain.gain.setValueAtTime(0.28, now);
    gain.gain.exponentialRampToValueAtTime(0.01, now + 0.6);
    osc.start(now);
    osc.stop(now + 0.6);
  } else if (type === "cooldown") {
    osc.frequency.setValueAtTime(440, now);
    gain.gain.setValueAtTime(0.2, now);
    gain.gain.exponentialRampToValueAtTime(0.01, now + 0.3);
    osc.start(now);
    osc.stop(now + 0.3);
  } else if (type === "fail") {
    osc.frequency.setValueAtTime(220, now);
    gain.gain.setValueAtTime(0.22, now);
    gain.gain.exponentialRampToValueAtTime(0.01, now + 0.4);
    osc.start(now);
    osc.stop(now + 0.4);
  }
}

// ============================================================
// 1. SINKRONISASI WAKTU SERVER & JADWAL PRESENSI REAL-TIME
// ============================================================
function getServerDateKey(serverDateObj) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Jakarta",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(serverDateObj);
}

function formatServerShortDateFromKey(dateKey) {
  const parts = String(dateKey || "").split("-").map(Number);
  if (parts.length !== 3 || parts.some(Number.isNaN)) return "Hari ini";
  const utcMid = new Date(Date.UTC(parts[0], parts[1] - 1, parts[2], 12, 0, 0));
  return utcMid.toLocaleDateString("id-ID", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "Asia/Jakarta",
  });
}

function renderTodayLogDateBadges(dateKey) {
  const label = formatServerShortDateFromKey(dateKey);
  const tagIn = document.getElementById("logDateCheckIn");
  const tagOut = document.getElementById("logDateCheckOut");
  if (tagIn) tagIn.textContent = label;
  if (tagOut) tagOut.textContent = label;
}

function resetTodayLogsForNewDate(newDateKey) {
  activeLogDateKey = newDateKey;
  renderTodayLogDateBadges(newDateKey);

  const inList = document.getElementById("todayCheckInList");
  const outList = document.getElementById("todayCheckOutList");
  const inCount = document.getElementById("countTodayCheckIn");
  const outCount = document.getElementById("countTodayCheckOut");

  if (inCount) inCount.textContent = "0";
  if (outCount) outCount.textContent = "0";
  if (inList) {
    inList.innerHTML = '<li class="log-empty-row">Belum ada peserta yang berhasil presensi masuk hari ini.</li>';
  }
  if (outList) {
    outList.innerHTML = '<li class="log-empty-row">Belum ada peserta yang berhasil presensi pulang hari ini.</li>';
  }

  syncServerSchedule();
  loadTodayAttendanceLogs();
}

function updateServerClockDisplay() {
  const serverNow = new Date(Date.now() + serverTimeOffsetMs);
  const currentKey = getServerDateKey(serverNow);
  if (!activeLogDateKey) {
    activeLogDateKey = currentKey;
    renderTodayLogDateBadges(currentKey);
  } else if (currentKey !== activeLogDateKey) {
    resetTodayLogsForNewDate(currentKey);
  }

  const timeStr = serverNow.toLocaleTimeString("id-ID", {
    hour12: false,
    timeZone: "Asia/Jakarta",
  });
  const dateStr = serverNow.toLocaleDateString("id-ID", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
    timeZone: "Asia/Jakarta",
  });

  const clockEl = document.getElementById("clockTime");
  const dateEl = document.getElementById("clockDate");
  if (clockEl) clockEl.textContent = `${timeStr} WIB`;
  if (dateEl) dateEl.textContent = dateStr;
}

function setOnlineBadge(isOnline) {
  const pill = document.getElementById("kioskBadgePill");
  const label = document.getElementById("kioskBadge");
  const mPill = document.getElementById("kioskBadgePillMobile");
  const mLabel = document.getElementById("kioskBadgeMobile");

  if (pill && label) {
    pill.className = `status-pill ${isOnline ? "status-pill-online" : "status-pill-offline"}`;
    label.textContent = isOnline ? "ONLINE" : "OFFLINE";
  }

  if (mPill && mLabel) {
    mPill.className = `status-pill status-pill-compact ${isOnline ? "status-pill-online" : "status-pill-offline"}`;
    mLabel.textContent = isOnline ? "ONLINE" : "OFFLINE";
  }
}

async function syncServerSchedule() {
  try {
    const res = await fetch("/api/schedule/current");
    if (!res.ok) throw new Error("Gagal mengambil jadwal");
    const data = await res.json();

    serverTimeOffsetMs = data.server_time_ms - Date.now();
    currentSession = data;

    setOnlineBadge(true);
    renderSessionUI();
    updateServerClockDisplay();
  } catch (err) {
    console.warn("Gagal sinkronisasi jadwal server:", err);
    setOnlineBadge(false);
    if (readyScheduleVal) readyScheduleVal.textContent = "Server tidak terjangkau";
  }
}

function renderSessionUI() {
  const s = currentSession;
  const boxMasuk = document.getElementById("boxSesiMasuk");
  const boxPulang = document.getElementById("boxSesiPulang");
  const masukRange = document.getElementById("schedMasukRange");
  const pulangRange = document.getElementById("schedPulangRange");

  boxMasuk.classList.remove("is-open");
  boxPulang.classList.remove("is-open");

  if (s.session_code === "check_in") {
    sessionIndicator.className = "session-tag session-tag-checkin";
    boxMasuk.classList.add("is-open");
    if (readyScheduleVal) readyScheduleVal.textContent = "Dibuka (Masuk)";
  } else if (s.session_code === "late_check_in") {
    sessionIndicator.className = "session-tag session-tag-late";
    boxMasuk.classList.add("is-open");
    if (readyScheduleVal) readyScheduleVal.textContent = `Terlambat (${s.late_minutes || 0} mnt)`;
  } else if (s.session_code === "check_out") {
    sessionIndicator.className = "session-tag session-tag-checkout";
    boxPulang.classList.add("is-open");
    if (readyScheduleVal) readyScheduleVal.textContent = "Dibuka (Pulang)";
  } else {
    sessionIndicator.className = "session-tag session-tag-closed";
    if (readyScheduleVal) readyScheduleVal.textContent = "Ditutup";
  }

  sessionLabel.textContent = s.label || "Di Luar Jam Presensi";

  if (s.schedule) {
    if (masukRange) masukRange.textContent = `${s.schedule.check_in_start} - ${s.schedule.check_in_end}`;
    if (pulangRange) pulangRange.textContent = `${s.schedule.check_out_start} - ${s.schedule.check_out_end}`;
    if (s.session_code === "late_check_in") {
      sessionScheduleMeta.textContent =
        `${s.message} Jadwal Normal: Masuk ${s.schedule.check_in_start}-${s.schedule.check_in_end}, ` +
        `Pulang ${s.schedule.check_out_start}-${s.schedule.check_out_end} WIB.`;
    } else {
      sessionScheduleMeta.textContent =
        `Jadwal Server: Masuk ${s.schedule.check_in_start}-${s.schedule.check_in_end} WIB, ` +
        `Pulang ${s.schedule.check_out_start}-${s.schedule.check_out_end} WIB.`;
    }
  } else {
    sessionScheduleMeta.textContent = s.message || "";
  }

  updateStartAttendanceButtonState();
}

function updateStartAttendanceButtonState() {
  if (!isCameraActive) {
    btnStartAttendance.classList.add("is-hidden");
    return;
  }

  btnStartAttendance.classList.remove("is-hidden");

  if (isVerifying) {
    btnStartAttendance.disabled = true;
    labelStartAttendance.textContent = "Memverifikasi Wajah...";
    return;
  }

  if (!currentSession.is_open) {
    btnStartAttendance.disabled = true;
    labelStartAttendance.textContent = "Sesi Presensi Ditutup";
    if (!isShowingTempResult) {
      setStatusCardTheme(
        "error",
        "lock",
        "Di Luar Jam Presensi",
        currentSession.message,
        false
      );
      btnFallback.classList.add("is-hidden");
    }
  } else {
    btnStartAttendance.disabled = false;
    labelStartAttendance.textContent = `Mulai Presensi (${currentSession.short_label})`;
    if (!isShowingTempResult) {
      resetToPreviewReady();
    }
  }
}

setInterval(updateServerClockDisplay, 1000);
setInterval(syncServerSchedule, 10000);
syncServerSchedule();

// ============================================================
// 2. GEOLOCATION GPS & GEOFENCE POPOVER
// ============================================================
async function fetchActiveLocations() {
  try {
    const res = await fetch("/api/locations/active");
    if (res.ok) {
      activeLocationConfig = await res.json();
      await refreshLocationPopover();
    }
  } catch (err) {
    console.warn("Gagal memuat lokasi aktif:", err);
  }
}

async function refreshLocationPopover() {
  const badgeText = document.getElementById("locationBadgeText");
  const badgeTextMobile = document.getElementById("locationBadgeTextMobile");
  const popStatus = document.getElementById("popGeoStatus");
  const popName = document.getElementById("popGeoName");
  const popCoords = document.getElementById("popGeoCoords");
  const popRadius = document.getElementById("popGeoRadius");
  const popAccuracy = document.getElementById("popGeoAccuracy");

  if (currentCoords.latitude !== null && currentCoords.longitude !== null) {
    popCoords.textContent = `${currentCoords.latitude.toFixed(5)}, ${currentCoords.longitude.toFixed(5)}`;
    popAccuracy.textContent = `±${Math.round(currentCoords.accuracy || 0)} meter`;
  } else {
    popCoords.textContent = "Menunggu izin GPS";
    popAccuracy.textContent = "-";
  }

  if (!activeLocationConfig.enforced) {
    popStatus.textContent = "Bebas Lokasi (Nonaktif)";
    popName.textContent = "Semua Lokasi Diizinkan";
    popRadius.textContent = "-";
    const acc = Math.round(currentCoords.accuracy || 0);
    if (badgeText) {
      badgeText.textContent = currentCoords.latitude !== null ? `GPS Aktif (±${acc} m)` : "Lokasi Bebas";
    }
    if (badgeTextMobile) {
      badgeTextMobile.textContent = currentCoords.latitude !== null ? `±${acc}m` : "Bebas";
    }
    if (readyLocationVal) readyLocationVal.textContent = "Bebas lokasi";
    return;
  }

  const firstLoc = activeLocationConfig.locations[0];
  popName.textContent = firstLoc ? firstLoc.name : "-";

  if (currentCoords.latitude === null || currentCoords.longitude === null) {
    popStatus.textContent = "GPS Wajib Aktif";
    popRadius.textContent = firstLoc ? `Maks ${firstLoc.radius_meters} m` : "-";
    if (badgeText) badgeText.textContent = "Izin GPS Nonaktif";
    if (badgeTextMobile) badgeTextMobile.textContent = "Perlu GPS";
    if (readyLocationVal) readyLocationVal.textContent = "Perlu izin GPS";
    return;
  }

  try {
    const res = await fetch("/api/locations/check", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        latitude: currentCoords.latitude,
        longitude: currentCoords.longitude,
      }),
    });
    const check = await res.json();
    popName.textContent = check.location_name || (firstLoc ? firstLoc.name : "-");
    if (check.allowed) {
      popStatus.textContent = "Dalam Area Presensi";
      popRadius.textContent = `${Math.round(check.distance_meters)} m / maks ${check.radius_meters} m`;
      if (badgeText) badgeText.textContent = `GPS Aktif (${Math.round(check.distance_meters)} m)`;
      if (badgeTextMobile) badgeTextMobile.textContent = `${Math.round(check.distance_meters)}m`;
      if (readyLocationVal) readyLocationVal.textContent = `Dalam area (${Math.round(check.distance_meters)} m)`;
    } else {
      popStatus.textContent = "Di Luar Radius";
      popRadius.textContent = `${Math.round(check.distance_meters)} m / maks ${check.radius_meters} m`;
      if (badgeText) badgeText.textContent = `Luar Area (${Math.round(check.distance_meters)} m)`;
      if (badgeTextMobile) badgeTextMobile.textContent = "Luar Area";
      if (readyLocationVal) readyLocationVal.textContent = `Di luar radius (${Math.round(check.distance_meters)} m)`;
    }
  } catch (err) {
    console.warn("Gagal cek geofence:", err);
  }
}

function initGeolocation() {
  const badgeText = document.getElementById("locationBadgeText");
  fetchActiveLocations();

  if (!navigator.geolocation) {
    if (badgeText) badgeText.textContent = "GPS Tidak Didukung";
    if (readyLocationVal) readyLocationVal.textContent = "Browser tanpa GPS";
    return;
  }

  navigator.geolocation.watchPosition(
    (pos) => {
      currentCoords.latitude = pos.coords.latitude;
      currentCoords.longitude = pos.coords.longitude;
      currentCoords.accuracy = pos.coords.accuracy;
      refreshLocationPopover();
    },
    (err) => {
      currentCoords.latitude = null;
      currentCoords.longitude = null;
      currentCoords.accuracy = null;
      if (badgeText && activeLocationConfig.enforced) {
        badgeText.textContent = "Izin GPS Nonaktif";
      }
      refreshLocationPopover();
      console.warn("Geolocation error:", err.message);
    },
    { enableHighAccuracy: true, maximumAge: 10000, timeout: 10000 }
  );
}
initGeolocation();
setInterval(fetchActiveLocations, 30000);

function closeNavMenu(restoreFocus = true) {
  const menu = document.getElementById("navMegaMenu");
  const btn = document.getElementById("btnNavFitur");
  if (menu) menu.classList.add("is-hidden");
  if (btn) btn.setAttribute("aria-expanded", "false");
  if (restoreFocus && lastNavMenuTrigger) {
    lastNavMenuTrigger.focus();
    lastNavMenuTrigger = null;
  }
}

function toggleNavMenu(e, triggerEl) {
  if (e) e.stopPropagation();
  const menu = document.getElementById("navMegaMenu");
  const btn = triggerEl || document.getElementById("btnNavFitur");
  if (!menu) return;

  const willOpen = menu.classList.contains("is-hidden");
  if (willOpen) {
    lastNavMenuTrigger = btn || document.activeElement;
    closePanduanMenu(false);
    closeGpsPopover(false);
    toggleMobileNav(false);
    menu.classList.remove("is-hidden");
    if (btn) btn.setAttribute("aria-expanded", "true");
  } else {
    closeNavMenu(false);
  }
}

function closePanduanMenu(restoreFocus = true) {
  const menu = document.getElementById("navPanduanMenu");
  const btn = document.getElementById("btnNavPanduan");
  if (menu) menu.classList.add("is-hidden");
  if (btn) btn.setAttribute("aria-expanded", "false");
  if (restoreFocus && lastPanduanTrigger) {
    lastPanduanTrigger.focus();
    lastPanduanTrigger = null;
  }
}

function togglePanduanMenu(e, triggerEl) {
  if (e) e.stopPropagation();
  const menu = document.getElementById("navPanduanMenu");
  const btn = triggerEl || document.getElementById("btnNavPanduan");
  if (!menu) return;

  const willOpen = menu.classList.contains("is-hidden");
  if (willOpen) {
    lastPanduanTrigger = btn || document.activeElement;
    closeNavMenu(false);
    closeGpsPopover(false);
    toggleMobileNav(false);
    menu.classList.remove("is-hidden");
    if (btn) btn.setAttribute("aria-expanded", "true");
  } else {
    closePanduanMenu(false);
  }
}

function toggleMobileNav(forceState) {
  const drawer = document.getElementById("mobileNavDrawer");
  const btn = document.getElementById("btnMobileMenu");
  const svg = document.getElementById("mobileMenuSvg");
  if (!drawer) return;

  const willOpen = typeof forceState === "boolean"
    ? forceState
    : drawer.classList.contains("is-hidden");

  drawer.classList.toggle("is-hidden", !willOpen);
  if (btn) btn.setAttribute("aria-expanded", String(willOpen));
  if (svg) svg.outerHTML = willOpen ? ICONS.close.replace('class="ui-icon"', 'id="mobileMenuSvg" class="ui-icon"') : ICONS.menu.replace('class="ui-icon"', 'id="mobileMenuSvg" class="ui-icon"');
  if (willOpen) {
    closeGpsPopover(false);
    closeNavMenu(false);
    closePanduanMenu(false);
  }
}

function closeGpsPopover(restoreFocus = true) {
  const popover = document.getElementById("gpsPopover");
  const btn = document.getElementById("btnGpsPopover");
  const btnMob = document.getElementById("btnGpsPopoverMobile");
  if (popover) popover.classList.add("is-hidden");
  if (btn) btn.setAttribute("aria-expanded", "false");
  if (btnMob) btnMob.setAttribute("aria-expanded", "false");
  if (restoreFocus && lastPopoverTrigger) {
    lastPopoverTrigger.focus();
    lastPopoverTrigger = null;
  }
}

function toggleGpsPopover(e, triggerEl) {
  if (e) e.stopPropagation();
  const popover = document.getElementById("gpsPopover");
  if (!popover) return;
  const willOpen = popover.classList.contains("is-hidden");
  if (willOpen) {
    lastPopoverTrigger = triggerEl || document.activeElement;
    closeNavMenu(false);
    closePanduanMenu(false);
    toggleMobileNav(false);
    popover.classList.remove("is-hidden");
    if (triggerEl) triggerEl.setAttribute("aria-expanded", "true");
    refreshLocationPopover();
  } else {
    closeGpsPopover(false);
  }
}

document.addEventListener("click", (e) => {
  const navMenu = document.getElementById("navMegaMenu");
  const navBtn = document.getElementById("btnNavFitur");
  if (navMenu && !navMenu.classList.contains("is-hidden") && !navMenu.contains(e.target) && !(navBtn && navBtn.contains(e.target))) {
    closeNavMenu(false);
  }

  const panduanMenu = document.getElementById("navPanduanMenu");
  const panduanBtn = document.getElementById("btnNavPanduan");
  if (panduanMenu && !panduanMenu.classList.contains("is-hidden") && !panduanMenu.contains(e.target) && !(panduanBtn && panduanBtn.contains(e.target))) {
    closePanduanMenu(false);
  }

  const popover = document.getElementById("gpsPopover");
  const btn = document.getElementById("btnGpsPopover");
  const btnMob = document.getElementById("btnGpsPopoverMobile");
  const clickedInsideBtn = (btn && btn.contains(e.target)) || (btnMob && btnMob.contains(e.target));
  if (popover && !popover.classList.contains("is-hidden") && !popover.contains(e.target) && !clickedInsideBtn) {
    closeGpsPopover(false);
  }

  const drawer = document.getElementById("mobileNavDrawer");
  const menuBtn = document.getElementById("btnMobileMenu");
  if (drawer && !drawer.classList.contains("is-hidden") && !drawer.contains(e.target) && !(menuBtn && menuBtn.contains(e.target))) {
    toggleMobileNav(false);
  }
});

// ============================================================
// 3. HELPER MIRROR FOTO (SEBAGAI CERMIN AGAR SESUAI PREVIEW)
// ============================================================
function captureMirroredFrame(targetWidth, targetHeight, quality = 0.88, sourceVideo = null) {
  const src = sourceVideo && sourceVideo.videoWidth ? sourceVideo : video;
  const w = targetWidth || src.videoWidth || 640;
  const h = targetHeight || src.videoHeight || 480;
  const offscreen = document.createElement("canvas");
  offscreen.width = w;
  offscreen.height = h;
  const offCtx = offscreen.getContext("2d");

  offCtx.translate(w, 0);
  offCtx.scale(-1, 1);
  offCtx.drawImage(src, 0, 0, w, h);

  return offscreen.toDataURL("image/jpeg", quality);
}

function syncEnrollPreviewStream() {
  const modal = document.getElementById("enrollModal");
  const enrollVideo = document.getElementById("enrollPreviewVideo");
  const guide = document.getElementById("enrollCamGuide");
  const placeholder = document.getElementById("enrollCamPlaceholder");
  const statusText = document.getElementById("enrollCamStatusText");
  if (!enrollVideo) return;

  const modalOpen = modal && !modal.classList.contains("is-hidden");
  if (modalOpen && isCameraActive && currentStream) {
    enrollVideo.srcObject = currentStream;
    enrollVideo.muted = true;
    enrollVideo.play().catch((err) => console.warn("enrollPreviewVideo.play warning:", err));
    enrollVideo.classList.remove("is-hidden");
    if (guide) guide.classList.remove("is-hidden");
    if (placeholder) placeholder.classList.add("is-hidden");
  } else {
    enrollVideo.srcObject = null;
    enrollVideo.classList.add("is-hidden");
    if (guide) guide.classList.add("is-hidden");
    if (placeholder) placeholder.classList.remove("is-hidden");
    if (statusText) {
      statusText.textContent = "Kamera belum aktif. Tekan tombol di bawah untuk membuka pratinjau.";
    }
  }
}

// ============================================================
// 4. TAHAP 1: AKTIFKAN / MATIKAN KAMERA (PREVIEW)
// ============================================================
function toggleCameraPreview() {
  if (isCameraActive) {
    deactivateCamera();
  } else {
    activateCamera();
  }
}

async function openStreamWithFallback(preferredId) {
  const attempts = [];
  if (preferredId) {
    attempts.push({ video: { deviceId: { exact: preferredId }, width: { ideal: 640 }, height: { ideal: 480 } }, audio: false });
  }
  attempts.push({ video: { facingMode: "user", width: { ideal: 640 }, height: { ideal: 480 } }, audio: false });
  attempts.push({ video: { width: { ideal: 640 }, height: { ideal: 480 } }, audio: false });
  attempts.push({ video: true, audio: false });

  let lastError = null;
  for (let i = 0; i < attempts.length; i++) {
    try {
      const stream = await navigator.mediaDevices.getUserMedia(attempts[i]);
      if (i > 0 && preferredId) {
        localStorage.removeItem("preferredCameraId");
      }
      return stream;
    } catch (err) {
      lastError = err;
      if (err.name === "NotAllowedError" || err.name === "PermissionDeniedError") {
        throw err;
      }
    }
  }
  throw lastError || new Error("Kamera tidak dapat diakses");
}

function setActivateButtonUI(active) {
  if (active) {
    btnActivateCamera.classList.add("is-stop");
    iconActivateWrap.innerHTML = ICONS.cameraOff;
    labelActivateCamera.textContent = "Matikan Kamera";
  } else {
    btnActivateCamera.classList.remove("is-stop");
    iconActivateWrap.innerHTML = ICONS.camera;
    labelActivateCamera.textContent = "Aktifkan Kamera";
  }
}

async function activateCamera() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    showToast("Browser ini tidak mendukung akses kamera.", "error");
    return;
  }

  try {
    btnActivateCamera.disabled = true;
    labelActivateCamera.textContent = "Membuka Kamera...";

    if (currentStream) {
      currentStream.getTracks().forEach((track) => track.stop());
      currentStream = null;
    }

    const savedCamId = localStorage.getItem("preferredCameraId");
    currentStream = await openStreamWithFallback(savedCamId);

    cameraInactiveState.classList.add("is-hidden");
    video.classList.remove("is-hidden");
    canvas.classList.remove("is-hidden");
    cameraActiveHud.classList.remove("is-hidden");

    video.srcObject = currentStream;
    video.muted = true;
    try {
      await video.play();
    } catch (playErr) {
      console.warn("video.play warning:", playErr);
    }

    if (!video.videoWidth) {
      await new Promise((resolve) => {
        const done = () => {
          video.removeEventListener("loadedmetadata", done);
          resolve();
        };
        video.addEventListener("loadedmetadata", done);
        setTimeout(done, 1500);
      });
    }

    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;

    isCameraActive = true;
    btnActivateCamera.disabled = false;
    setActivateButtonUI(true);

    await updateCameraList(false);
    navigator.mediaDevices.ondevicechange = () => updateCameraList(false);

    const activeTrack = currentStream.getVideoTracks()[0];
    const camLabel = activeTrack ? activeTrack.label : "Kamera Aktif";
    cameraSubStatus.textContent = `Aktif • ${camLabel}`;
    cameraSubStatus.classList.add("is-active");
    hudFeedModeLabel.textContent = camLabel.split(" (")[0];
    if (readyCameraVal) readyCameraVal.textContent = "Aktif";

    await syncServerSchedule();
    updateStartAttendanceButtonState();
    syncEnrollPreviewStream();
    showToast("Kamera berhasil diaktifkan.", "success");
  } catch (err) {
    console.error("Gagal membuka kamera:", err);
    if (currentStream) {
      currentStream.getTracks().forEach((track) => track.stop());
      currentStream = null;
    }
    video.srcObject = null;
    video.classList.add("is-hidden");
    canvas.classList.add("is-hidden");
    cameraActiveHud.classList.add("is-hidden");
    cameraInactiveState.classList.remove("is-hidden");

    isCameraActive = false;
    btnActivateCamera.disabled = false;
    setActivateButtonUI(false);
    if (readyCameraVal) readyCameraVal.textContent = "Gagal dibuka";

    let errMsg = "Izinkan akses kamera pada browser atau periksa perangkat kamera Anda.";
    if (err.name === "NotReadableError" || err.name === "TrackStartError") {
      errMsg = "Kamera sedang digunakan tab atau aplikasi lain. Tutup aplikasi kamera lain lalu coba lagi.";
    } else if (err.name === "NotFoundError") {
      errMsg = "Perangkat kamera tidak ditemukan di perangkat ini.";
    } else if (err.name === "NotAllowedError") {
      errMsg = "Izin kamera ditolak oleh browser. Aktifkan izin kamera pada ikon pengaturan di address bar.";
    }

    setStatusCardTheme("error", "alert", "Kamera Tidak Dapat Diakses", errMsg, true);
    syncEnrollPreviewStream();
    showToast(errMsg, "error");
  }
}

function deactivateCamera() {
  if (currentStream) {
    currentStream.getTracks().forEach((track) => track.stop());
    currentStream = null;
  }
  video.srcObject = null;
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  isCameraActive = false;
  isVerifying = false;
  isShowingTempResult = false;
  failedAttempts = 0;

  video.classList.add("is-hidden");
  canvas.classList.add("is-hidden");
  cameraActiveHud.classList.add("is-hidden");
  cameraInactiveState.classList.remove("is-hidden");

  setActivateButtonUI(false);
  btnStartAttendance.classList.add("is-hidden");

  cameraSubStatus.textContent = "Kamera dalam posisi nonaktif";
  cameraSubStatus.classList.remove("is-active");
  if (readyCameraVal) readyCameraVal.textContent = "Belum aktif";

  btnFallback.classList.add("is-hidden");

  setStatusCardTheme(
    "standby",
    "info",
    "Aktifkan Kamera untuk Memulai",
    "Jenis presensi (Masuk atau Pulang) ditentukan otomatis oleh jam server.",
    true
  );

  syncEnrollPreviewStream();
  showToast("Kamera dimatikan.", "info");
}

async function updateCameraList(autoSwitchToDroidCam = false) {
  const devices = await navigator.mediaDevices.enumerateDevices();
  const videoDevices = devices.filter((d) => d.kind === "videoinput");
  const selects = [
    document.getElementById("cameraSelect"),
    document.getElementById("enrollCameraSelect")
  ].filter(Boolean);
  if (selects.length === 0) return;

  const activeTrack = currentStream ? currentStream.getVideoTracks()[0] : null;
  const activeDeviceId = activeTrack && activeTrack.getSettings ? activeTrack.getSettings().deviceId : null;
  const savedCamId = localStorage.getItem("preferredCameraId");

  let preferredTargetId = null;

  selects.forEach((sel) => {
    sel.innerHTML = "";
    videoDevices.forEach((device, idx) => {
      const opt = document.createElement("option");
      opt.value = device.deviceId;
      opt.textContent = device.label || `Kamera ${idx + 1}`;

      if (activeDeviceId && device.deviceId === activeDeviceId) {
        opt.selected = true;
      } else if (!activeDeviceId && savedCamId === device.deviceId) {
        opt.selected = true;
      }

      const isDroidCam = (device.label || "").toLowerCase().includes("droidcam");
      if (!savedCamId && isDroidCam && !preferredTargetId) {
        preferredTargetId = device.deviceId;
      }
      sel.appendChild(opt);
    });
  });

  if (autoSwitchToDroidCam && preferredTargetId && activeDeviceId && activeDeviceId !== preferredTargetId) {
    await switchCamera(preferredTargetId);
  }
}

async function onCameraSelected(deviceId) {
  if (!deviceId) return;
  localStorage.setItem("preferredCameraId", deviceId);
  if (isCameraActive) {
    await switchCamera(deviceId);
  }
}

async function switchCamera(deviceId) {
  try {
    if (currentStream) {
      currentStream.getTracks().forEach((track) => track.stop());
      currentStream = null;
    }
    currentStream = await navigator.mediaDevices.getUserMedia({
      video: {
        deviceId: { exact: deviceId },
        width: { ideal: 640 },
        height: { ideal: 480 },
      },
      audio: false,
    });
    video.srcObject = currentStream;
    try {
      await video.play();
    } catch (e) {
      console.warn(e);
    }
    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;

    const activeTrack = currentStream.getVideoTracks()[0];
    const camLabel = activeTrack ? activeTrack.label : "Kamera Aktif";
    cameraSubStatus.textContent = `Aktif • ${camLabel}`;
    hudFeedModeLabel.textContent = camLabel.split(" (")[0];
    await updateCameraList(false);
    syncEnrollPreviewStream();
  } catch (err) {
    console.error("Gagal beralih kamera:", err);
    showToast("Gagal menghubungkan ke kamera tersebut.", "error");
  }
}

// ============================================================
// 5. TAHAP 2: MULAI PRESENSI (VERIFIKASI OTOMATIS KE SERVER)
// ============================================================
function drawFaceBbox(bbox, status) {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!bbox) return;

  const bx = bbox.x * canvas.width;
  const by = bbox.y * canvas.height;
  const bw = bbox.width * canvas.width;
  const bh = bbox.height * canvas.height;

  ctx.lineWidth = 4;
  if (status === "success") {
    ctx.strokeStyle = "#047857";
  } else if (status === "already_checked") {
    ctx.strokeStyle = "#B45309";
  } else if (status === "out_of_range" || status === "outside_schedule" || status === "unrecognized") {
    ctx.strokeStyle = "#B91C1C";
  } else {
    ctx.strokeStyle = "#1D4ED8";
  }
  ctx.strokeRect(bx, by, bw, bh);
}

async function startAttendanceCapture() {
  if (!isCameraActive || isVerifying) return;

  await syncServerSchedule();
  if (!currentSession.is_open) {
    playChime("fail");
    updateStartAttendanceButtonState();
    showToast("Presensi ditolak: di luar jam presensi.", "error");
    return;
  }

  isVerifying = true;
  isShowingTempResult = true;
  updateStartAttendanceButtonState();
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  setStatusCardTheme(
    "standby",
    "info",
    "Memverifikasi Wajah...",
    "Tahan posisi wajah Anda di dalam bingkai kamera.",
    false
  );

  const MAX_TRIES = 4;
  let finalData = null;

  try {
    for (let attempt = 1; attempt <= MAX_TRIES; attempt++) {
      const frameB64 = captureMirroredFrame(video.videoWidth || 640, video.videoHeight || 480, 0.85);
      const res = await fetch("/api/attendance/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          photo_b64: frameB64,
          latitude: currentCoords.latitude,
          longitude: currentCoords.longitude,
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Gagal memverifikasi presensi");
      }

      finalData = data;
      drawFaceBbox(data.bbox, data.status);

      if (
        data.status === "success" ||
        data.status === "already_checked" ||
        data.status === "outside_schedule" ||
        data.status === "out_of_range"
      ) {
        break;
      }

      if (attempt < MAX_TRIES) {
        await new Promise((r) => setTimeout(r, 350));
      }
    }

    if (finalData) {
      handleVerifyResult(finalData);
    }
  } catch (err) {
    playChime("fail");
    setStatusCardTheme("error", "alert", "Gagal Memproses Presensi", err.message, false);
    showToast(err.message, "error");
    scheduleResetAfterResult(4500);
  } finally {
    isVerifying = false;
    updateStartAttendanceButtonState();
  }
}

function setStatusCardTheme(theme, iconKey, title, subtitle, showReadiness = false) {
  statusCard.className = `panel status-panel status-${theme}`;
  statusIconBox.innerHTML = ICONS[iconKey] || ICONS.info;
  statusTitle.textContent = title;
  statusSubtitle.textContent = subtitle;

  if (showReadiness) {
    guideSteps.classList.remove("is-hidden");
  } else {
    guideSteps.classList.add("is-hidden");
  }
}

function handleVerifyResult(data) {
  if (data.status === "success") {
    playChime("success");
    failedAttempts = 0;
    btnFallback.classList.add("is-hidden");

    const locText = data.location_name ? ` (Lokasi: ${data.location_name})` : "";
    if (data.is_late) {
      setStatusCardTheme(
        "warning",
        "alert",
        `Presensi Masuk (Terlambat): ${data.full_name}`,
        `Terlambat ${data.late_minutes || 0} menit | Tercatat pukul ${data.time}${locText}.`,
        false
      );
      showToast(`Presensi Masuk (Terlambat ${data.late_minutes || 0} mnt): ${data.full_name}`, "warning");
    } else {
      setStatusCardTheme(
        "success",
        "check",
        `Presensi ${data.attendance_type} Berhasil: ${data.full_name}`,
        `Tercatat pukul ${data.time}${locText}.`,
        false
      );
      showToast(`Presensi ${data.attendance_type} berhasil: ${data.full_name}`, "success");
    }
    loadTodayAttendanceLogs();
    scheduleResetAfterResult(5000);
    return;
  }

  if (data.status === "already_checked") {
    playChime("cooldown");
    setStatusCardTheme(
      "warning",
      "info",
      `Sudah Presensi ${data.attendance_type} Hari Ini (${data.full_name})`,
      data.message,
      false
    );
    showToast(data.message, "warning");
    scheduleResetAfterResult(5000);
    return;
  }

  if (data.status === "outside_schedule") {
    playChime("fail");
    setStatusCardTheme("error", "lock", "Sesi Presensi Ditutup", data.message, false);
    showToast("Sesi presensi sedang ditutup.", "error");
    syncServerSchedule();
    scheduleResetAfterResult(4500);
    return;
  }

  if (data.status === "out_of_range") {
    playChime("fail");
    setStatusCardTheme(
      "error",
      "alert",
      `Di Luar Lingkup Lokasi (${data.full_name})`,
      data.message,
      false
    );
    showToast(data.message, "error");
    scheduleResetAfterResult(5000);
    return;
  }

  if (data.status === "unrecognized") {
    handleFaceFailureAttempt(
      "Wajah Tidak Dikenali",
      "Pastikan pencahayaan cukup dan wajah terlihat jelas, lalu tekan 'Mulai Presensi' sekali lagi."
    );
    return;
  }

  handleFaceFailureAttempt(
    "Wajah Belum Terdeteksi Jelas",
    data.message || "Posisikan wajah di dalam bingkai kamera, lalu tekan 'Mulai Presensi' sekali lagi."
  );
}

function handleFaceFailureAttempt(reasonTitle, retryHint) {
  playChime("fail");
  failedAttempts++;

  if (failedAttempts >= 2 && currentSession.is_open) {
    failedAttempts = 0;
    setStatusCardTheme(
      "warning",
      "info",
      reasonTitle,
      "Gagal 2 kali. Pop-up Presensi PIN dibuka otomatis untuk mencatat kehadiran.",
      false
    );
    showToast("Verifikasi wajah gagal 2 kali. Silakan masukkan PIN absensi.", "warning");
    openPinModal(btnStartAttendance);
    scheduleResetAfterResult(4500);
    return;
  }

  setStatusCardTheme("error", "alert", `${reasonTitle} (Percobaan 1/2)`, retryHint, false);
  showToast(`${reasonTitle}. Coba sekali lagi atau tunggu pengalihan ke PIN.`, "error");
  scheduleResetAfterResult(4000);
}

let resetTimer = null;
function scheduleResetAfterResult(ms) {
  if (resetTimer) clearTimeout(resetTimer);
  resetTimer = setTimeout(() => {
    isShowingTempResult = false;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (isCameraActive) {
      updateStartAttendanceButtonState();
    }
  }, ms);
}

function resetToPreviewReady() {
  setStatusCardTheme(
    "standby",
    "check",
    `Kamera Siap: Sesi ${currentSession.short_label}`,
    'Posisikan wajah di dalam bingkai lalu tekan tombol "Mulai Presensi".',
    true
  );
}

// ============================================================
// 6. LAYAR PENUH
// ============================================================
function updateFullscreenUI(isFs) {
  const labelEl = document.getElementById("labelFullscreen");
  const labelMobile = document.getElementById("labelFullscreenMobile");
  const svg = document.getElementById("iconFullscreenSvg");
  if (labelEl) labelEl.textContent = isFs ? "Keluar Layar Penuh" : "Layar Penuh";
  if (labelMobile) labelMobile.textContent = isFs ? "Keluar Layar Penuh" : "Mode Layar Penuh";
  if (svg) {
    svg.outerHTML = (isFs ? ICONS.collapse : ICONS.expand).replace('class="ui-icon"', 'id="iconFullscreenSvg" class="ui-icon-sm"');
  }
}

function toggleFullScreen() {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen()
      .then(() => updateFullscreenUI(true))
      .catch((err) => showToast(err.message, "warning"));
  } else {
    document.exitFullscreen();
  }
}

document.addEventListener("fullscreenchange", () => {
  updateFullscreenUI(Boolean(document.fullscreenElement));
});

// ============================================================
// 7. PENDAFTARAN PESERTA (3 FOTO MIRRORED + DIVISI + PIN)
// ============================================================
let cachedDivisions = [];

async function prefetchDivisions() {
  try {
    const res = await fetch("/api/divisions");
    if (res.ok) {
      cachedDivisions = await res.json();
    }
  } catch (err) {
    console.warn("Gagal preload divisi:", err);
  }
}
prefetchDivisions();

async function openEnrollmentModal(triggerEl) {
  lastModalTrigger = triggerEl || document.activeElement;
  const modal = document.getElementById("enrollModal");
  modal.classList.remove("is-hidden");
  populateDivisionsDropdown();
  syncEnrollPreviewStream();

  const firstInput = document.getElementById("enrollInternId");
  if (firstInput) firstInput.focus();

  if (!isCameraActive) {
    await activateCamera();
  }
}

function closeEnrollmentModal() {
  const modal = document.getElementById("enrollModal");
  modal.classList.add("is-hidden");
  syncEnrollPreviewStream();
  if (lastModalTrigger) {
    lastModalTrigger.focus();
    lastModalTrigger = null;
  }
}

function populateDivisionsDropdown() {
  const sel = document.getElementById("enrollDivision");
  if (cachedDivisions.length > 0) {
    sel.innerHTML = cachedDivisions
      .map((d) => `<option value="${d.id}">${d.name} (${d.code})</option>`)
      .join("");
  } else {
    sel.innerHTML = '<option value="">Memuat daftar divisi...</option>';
    prefetchDivisions().then(() => {
      if (cachedDivisions.length > 0) {
        sel.innerHTML = cachedDivisions
          .map((d) => `<option value="${d.id}">${d.name} (${d.code})</option>`)
          .join("");
      } else {
        sel.innerHTML = '<option value="">Divisi tidak tersedia</option>';
      }
    });
  }
}

let capturedPoses = { front: null, left: null, right: null };

function captureEnrollPose(poseName) {
  const enrollVideo = document.getElementById("enrollPreviewVideo");
  const srcVideo = enrollVideo && enrollVideo.videoWidth ? enrollVideo : video;

  if (!isCameraActive || !srcVideo || !srcVideo.videoWidth || !srcVideo.videoHeight) {
    showToast("Kamera belum aktif. Harap aktifkan kamera terlebih dahulu.", "warning");
    return;
  }

  const b64 = captureMirroredFrame(srcVideo.videoWidth, srcVideo.videoHeight, 0.88, srcVideo);
  capturedPoses[poseName] = b64;

  const card = document.getElementById(`poseCard_${poseName}`);
  const img = document.getElementById(`thumb_${poseName}`);
  const placeholder = card.querySelector(".pose-placeholder");
  const hint = card.querySelector(".pose-hint");

  card.classList.add("captured");
  if (placeholder) placeholder.classList.add("is-hidden");
  if (img) {
    img.src = b64;
    img.classList.remove("is-hidden");
  }
  if (hint) hint.textContent = "Tersimpan";

  showToast(`Foto pose '${poseName}' berhasil diambil (mode cermin).`, "success");
}

async function submitEnrollmentForm(e) {
  e.preventDefault();
  const internId = document.getElementById("enrollInternId").value.trim();
  const fullName = document.getElementById("enrollFullName").value.trim();
  const institution = document.getElementById("enrollInstitution").value.trim();
  const divisionId = document.getElementById("enrollDivision").value;

  if (!capturedPoses.front || !capturedPoses.left || !capturedPoses.right) {
    showToast("Harap ambil ke-3 foto pose (Depan, Kiri, Kanan) terlebih dahulu.", "warning");
    return;
  }

  const submitBtn = document.getElementById("btnSubmitEnroll");
  submitBtn.disabled = true;
  submitBtn.querySelector("span").textContent = "Menganalisis & Mendaftarkan...";

  const pinVal = document.getElementById("enrollPin") ? document.getElementById("enrollPin").value.trim() : "123456";

  try {
    const res = await fetch("/api/enrollment/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        intern_id: internId,
        full_name: fullName,
        institution: institution,
        division_id: divisionId,
        pin: pinVal || "123456",
        biometric_consent: true,
        photos: [
          { angle: "front", photo_b64: capturedPoses.front },
          { angle: "left", photo_b64: capturedPoses.left },
          { angle: "right", photo_b64: capturedPoses.right },
        ],
      }),
    });

    let result = {};
    const resText = await res.text();
    try {
      result = JSON.parse(resText);
    } catch (err) {
      throw new Error(`Server (${res.status}): ${resText.slice(0, 150)}`);
    }

    if (!res.ok) {
      throw new Error(result.detail || "Gagal mendaftarkan peserta");
    }

    showToast(result.message || `Peserta ${fullName} berhasil didaftarkan.`, "success");
    closeEnrollmentModal();

    document.getElementById("enrollForm").reset();
    capturedPoses = { front: null, left: null, right: null };
    document.querySelectorAll(".pose-card").forEach((c) => c.classList.remove("captured"));
    document.querySelectorAll(".pose-thumb").forEach((img) => {
      img.src = "";
      img.classList.add("is-hidden");
    });
    document.querySelectorAll(".pose-placeholder").forEach((p) => p.classList.remove("is-hidden"));
    document.querySelectorAll(".pose-hint").forEach((h) => (h.textContent = "Klik untuk ambil"));
  } catch (err) {
    showToast(err.message || "Gagal mendaftarkan peserta.", "error");
  } finally {
    submitBtn.disabled = false;
    submitBtn.querySelector("span").textContent = "Simpan & Daftarkan Wajah";
  }
}

// ============================================================
// 8. PRESENSI CADANGAN MANDIRI (SELF-SERVICE PIN) & ESCAPE KEY
// ============================================================
function openPinModal(triggerEl) {
  if (!currentSession.is_open) {
    showToast(currentSession.message || "Sesi presensi sedang ditutup.", "warning");
    return;
  }
  lastModalTrigger = triggerEl || document.activeElement;
  const modal = document.getElementById("pinModal");
  modal.classList.remove("is-hidden");
  document.getElementById("pinInternId").focus();
}

function closePinModal() {
  const modal = document.getElementById("pinModal");
  modal.classList.add("is-hidden");
  document.getElementById("pinCode").value = "";
  if (lastModalTrigger) {
    lastModalTrigger.focus();
    lastModalTrigger = null;
  }
}

async function submitPinAttendance() {
  const internId = document.getElementById("pinInternId").value.trim();
  const pin = document.getElementById("pinCode").value.trim();

  if (!internId || !pin) {
    showToast("Harap masukkan ID Magang dan PIN.", "warning");
    return;
  }

  let photoB64 = null;
  if (isCameraActive && video.videoWidth && video.videoHeight) {
    photoB64 = captureMirroredFrame(400, 300, 0.75);
  }

  try {
    const res = await fetch("/api/attendance/fallback-pin", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        intern_id: internId,
        pin: pin,
        photo_b64: photoB64,
        latitude: currentCoords.latitude,
        longitude: currentCoords.longitude,
      }),
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Presensi PIN gagal");
    }

    closePinModal();
    playChime("success");
    isShowingTempResult = true;
    failedAttempts = 0;
    btnFallback.classList.add("is-hidden");

    if (data.is_late) {
      setStatusCardTheme(
        "warning",
        "alert",
        `Presensi Masuk (Terlambat): ${data.full_name}`,
        `Terlambat ${data.late_minutes || 0} menit via PIN Mandiri pukul ${data.time}.`,
        false
      );
      showToast(`Presensi PIN Masuk (Terlambat ${data.late_minutes || 0} mnt): ${data.full_name}`, "warning");
    } else {
      setStatusCardTheme(
        "success",
        "check",
        `Presensi ${data.attendance_type} Berhasil: ${data.full_name}`,
        `Via PIN Mandiri pada pukul ${data.time}.`,
        false
      );
      showToast(`Presensi PIN berhasil: ${data.full_name}`, "success");
    }
    loadTodayAttendanceLogs();
    scheduleResetAfterResult(5000);
  } catch (err) {
    showToast("GAGAL: " + err.message, "error");
  }
}

document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;

  const enrollModal = document.getElementById("enrollModal");
  if (enrollModal && !enrollModal.classList.contains("is-hidden")) {
    closeEnrollmentModal();
    return;
  }

  const pinModal = document.getElementById("pinModal");
  if (pinModal && !pinModal.classList.contains("is-hidden")) {
    closePinModal();
    return;
  }

  const navMenu = document.getElementById("navMegaMenu");
  if (navMenu && !navMenu.classList.contains("is-hidden")) {
    closeNavMenu(true);
    return;
  }

  const panduanMenu = document.getElementById("navPanduanMenu");
  if (panduanMenu && !panduanMenu.classList.contains("is-hidden")) {
    closePanduanMenu(true);
    return;
  }

  const gpsPopover = document.getElementById("gpsPopover");
  if (gpsPopover && !gpsPopover.classList.contains("is-hidden")) {
    closeGpsPopover(true);
    return;
  }

  const drawer = document.getElementById("mobileNavDrawer");
  if (drawer && !drawer.classList.contains("is-hidden")) {
    toggleMobileNav(false);
    const menuBtn = document.getElementById("btnMobileMenu");
    if (menuBtn) menuBtn.focus();
  }
});

function escapeLogHtml(text) {
  if (text === null || text === undefined) return "";
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

async function loadTodayAttendanceLogs() {
  const inList = document.getElementById("todayCheckInList");
  const outList = document.getElementById("todayCheckOutList");
  const inCount = document.getElementById("countTodayCheckIn");
  const outCount = document.getElementById("countTodayCheckOut");
  if (!inList || !outList) return;

  try {
    const res = await fetch("/api/attendance/today", { cache: "no-store" });
    if (!res.ok) throw new Error("Gagal mengambil log hari ini");
    const headerDate = res.headers.get("X-Server-Date");
    if (headerDate && /^\d{4}-\d{2}-\d{2}$/.test(headerDate)) {
      if (headerDate !== activeLogDateKey) {
        activeLogDateKey = headerDate;
      }
      renderTodayLogDateBadges(activeLogDateKey);
    }

    const rawRows = await res.json();
    const rows = Array.isArray(rawRows)
      ? rawRows.filter((r) => !r.checked_date || !activeLogDateKey || r.checked_date === activeLogDateKey)
      : [];

    const checkIns = rows.filter((r) => r.attendance_type === "check_in");
    const checkOuts = rows.filter((r) => r.attendance_type === "check_out");

    if (inCount) inCount.textContent = String(checkIns.length);
    if (outCount) outCount.textContent = String(checkOuts.length);

    if (checkIns.length === 0) {
      inList.innerHTML = '<li class="log-empty-row">Belum ada peserta yang berhasil presensi masuk hari ini.</li>';
    } else {
      inList.innerHTML = checkIns.map((r) => {
        const badge = r.is_late
          ? `<span class="log-status-pill log-pill-late">Terlambat ${escapeLogHtml(r.late_minutes || 0)} mnt</span>`
          : '<span class="log-status-pill log-pill-ok">Masuk</span>';
        const statusDesc = r.is_late
          ? "Berhasil presensi masuk (Terlambat)"
          : "Berhasil presensi masuk";

        return `
          <li class="today-log-row">
            <div class="log-row-main">
              <span class="log-person-name">${escapeLogHtml(r.full_name || "Peserta")}</span>
              <span class="log-row-meta">${statusDesc}</span>
            </div>
            <div class="log-row-right">
              ${badge}
              <span class="log-time-text">${escapeLogHtml(r.time_str)}</span>
            </div>
          </li>
        `;
      }).join("");
    }

    if (checkOuts.length === 0) {
      outList.innerHTML = '<li class="log-empty-row">Belum ada peserta yang berhasil presensi pulang hari ini.</li>';
    } else {
      outList.innerHTML = checkOuts.map((r) => `
        <li class="today-log-row">
          <div class="log-row-main">
            <span class="log-person-name">${escapeLogHtml(r.full_name || "Peserta")}</span>
            <span class="log-row-meta">Berhasil presensi pulang</span>
          </div>
          <div class="log-row-right">
            <span class="log-status-pill log-pill-out">Pulang</span>
            <span class="log-time-text">${escapeLogHtml(r.time_str)}</span>
          </div>
        </li>
      `).join("");
    }
  } catch (err) {
    inList.innerHTML = '<li class="log-empty-row">Gagal memuat log masuk dari server.</li>';
    outList.innerHTML = '<li class="log-empty-row">Gagal memuat log pulang dari server.</li>';
  }
}

document.addEventListener("DOMContentLoaded", () => {
  updateServerClockDisplay();
  loadTodayAttendanceLogs();
  window.setInterval(loadTodayAttendanceLogs, 20000);
});
