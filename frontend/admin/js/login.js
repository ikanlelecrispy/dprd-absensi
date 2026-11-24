const AUTH_API = `${window.location.protocol}//${window.location.host}/api/auth`;

const EYE_SHOW_SVG =
  '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z"></path><circle cx="12" cy="12" r="3"></circle></svg>';

const EYE_HIDE_SVG =
  '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17.94 17.94A10.94 10.94 0 0 1 12 19c-6.5 0-10-7-10-7a18.45 18.45 0 0 1 5.06-5.94"></path><path d="M9.9 4.24A10.94 10.94 0 0 1 12 5c6.5 0 10 7 10 7a18.5 18.5 0 0 1-2.16 3.19"></path><path d="M14.12 14.12a3 3 0 1 1-4.24-4.24"></path><line x1="2" y1="2" x2="22" y2="22"></line></svg>';

function togglePasswordVisibility(inputId, btnEl) {
  const input = document.getElementById(inputId);
  if (!input || !btnEl) return;

  const show = input.type === "password";
  input.type = show ? "text" : "password";
  btnEl.innerHTML = show ? EYE_HIDE_SVG : EYE_SHOW_SVG;
  btnEl.setAttribute("aria-label", show ? "Sembunyikan kata sandi" : "Tampilkan kata sandi");
  btnEl.setAttribute("aria-pressed", String(show));
}

function showLoginError(message) {
  const box = document.getElementById("loginErrorBox");
  if (!box) return;

  if (!message) {
    box.hidden = true;
    box.textContent = "";
    return;
  }

  box.textContent = message;
  box.hidden = false;
}

async function handleAdminLogin(event) {
  event.preventDefault();
  showLoginError("");

  const identifier = (document.getElementById("loginIdentifier")?.value || "").trim();
  const password = document.getElementById("loginPassword")?.value || "";
  const submitBtn = document.getElementById("btnLoginSubmit");
  const submitLabel = document.getElementById("btnLoginLabel");

  if (!identifier || !password) {
    showLoginError("Mohon isi email atau username beserta kata sandi.");
    return;
  }

  if (submitBtn) submitBtn.disabled = true;
  if (submitLabel) submitLabel.textContent = "Memverifikasi...";

  try {
    const res = await fetch(`${AUTH_API}/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ identifier, password })
    });
    const data = await res.json();

    if (!res.ok) {
      showLoginError(data.detail || "Gagal masuk. Periksa kembali kredensial Anda.");
      return;
    }

    window.location.replace("/admin/index.html");
  } catch (err) {
    showLoginError("Koneksi ke server bermasalah. Pastikan backend berjalan.");
  } finally {
    if (submitBtn) submitBtn.disabled = false;
    if (submitLabel) submitLabel.textContent = "Masuk Dashboard";
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  try {
    const res = await fetch(`${AUTH_API}/me`, { credentials: "same-origin" });
    if (res.ok) {
      window.location.replace("/admin/index.html");
    }
  } catch (e) {
    // Abaikan jika gagal mengecek sesi awal
  }
});
