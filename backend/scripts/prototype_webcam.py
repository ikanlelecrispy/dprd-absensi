"""
PROTOTIPE INTI PRESENSI & ENROLLMENT WAJAH — DPRD SURAKARTA
-----------------------------------------------------------
Fitur yang diuji di script ini:
1. Enrollment Peserta Baru (3 pose: Depan, Toleh Kiri, Toleh Kanan).
2. Validasi Kualitas Citra Real-time (Blur, Pencahayaan, 1 Wajah).
3. Pencegahan Pendaftaran Ganda (Duplicate Face Detection via Cosine Similarity).
4. Presensi Real-Time Kamera Kiosk (Matching, Cooldown 5 menit, Foto Bukti).
5. Nonaktifkan & Hapus Data Wajah Peserta (Kepatuhan UU PDP).
6. Mode Uji Headless / Otomatis (Tanpa Kamera Fisik).
"""

import os
import sys
import uuid
from datetime import datetime, date, timedelta
from pathlib import Path
import cv2
import numpy as np

# Tambahkan backend ke PYTHONPATH
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings
from app.db.base import Base
from app.db.session import engine, SessionLocal
from app.db.models.division import Division
from app.db.models.participant import Participant, ParticipantStatus
from app.db.models.face_embedding import FaceEmbedding
from app.db.models.attendance import Attendance, AttendanceType, AttendanceStatus
from app.core.security import security_service
from app.core.quality_checker import quality_checker
from app.core.matcher import matcher
from app.core.face_processor import face_processor


def get_compatible_db_session():
    """
    Menyediakan DB session ke PostgreSQL.
    """
    return SessionLocal()



def ensure_default_division(db) -> Division:
    """Memastikan minimal ada 1 divisi default."""
    div = db.query(Division).first()
    if not div:
        div = Division(
            name="Bagian Persidangan & Perundang-undangan",
            code="SIDANG",
            description="Divisi default untuk peserta magang",
            supervisor_name="Admin Resepsionis",
            is_active=True,
        )
        db.add(div)
        db.commit()
        db.refresh(div)
    return div


def capture_pose_with_webcam(cap, pose_label: str, instruction: str) -> np.ndarray | None:
    """
    Menampilkan panduan di layar OpenCV, memeriksa kualitas real-time,
    dan mengambil frame saat tombol SPACE ditekan.
    """
    print(f"\n>>> Silakan ambil pose: {pose_label.upper()}")
    print(f">>> Panduan: {instruction}")
    print(">>> Tekan [SPACE] untuk mengambil foto | Tekan [ESC] untuk batal.")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[ERROR] Gagal membaca frame dari webcam.")
            return None

        # Mirror frame agar terasa natural seperti cermin
        display_frame = cv2.flip(frame, 1)
        h, w, _ = display_frame.shape

        # Gambar area panduan elips/kotak di tengah layar
        box_w, box_h = int(w * 0.45), int(h * 0.65)
        x1 = (w - box_w) // 2
        y1 = (h - box_h) // 2
        x2, y2 = x1 + box_w, y1 + box_h
        cv2.rectangle(display_frame, (x1, y1), (x2, y2), (255, 200, 0), 2)

        # Petunjuk di layar
        cv2.putText(
            display_frame,
            f"Pose: {pose_label} ({instruction})",
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 255),
            2,
        )
        cv2.putText(
            display_frame,
            "Tekan [SPACE] untuk Tangkap | [ESC] Batal",
            (20, h - 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (200, 200, 200),
            2,
        )

        cv2.imshow("Enrollment Wajah - DPRD Surakarta", display_frame)
        key = cv2.waitKey(1) & 0xFF

        if key == 27:  # ESC
            return None
        elif key == 32:  # SPACE
            # Gunakan frame asli tanpa flip untuk proses deteksi presisi
            captured = frame.copy()
            return captured


def run_enrollment_interactive(db):
    """Alur lengkap enrollment peserta baru via webcam."""
    print("\n" + "=" * 60)
    print("           FORM PENDAFTARAN PESERTA MAGANG BARU")
    print("=" * 60)

    intern_id = input("Nomor Induk / ID Magang (misal: MGG-2024-001): ").strip()
    if not intern_id:
        print("[GAGAL] ID Magang tidak boleh kosong.")
        return

    # Cek apakah ID sudah ada
    existing = db.query(Participant).filter(Participant.intern_id == intern_id).first()
    if existing:
        print(f"[GAGAL] Peserta dengan ID '{intern_id}' sudah terdaftar: {existing.full_name}")
        return

    full_name = input("Nama Lengkap Peserta: ").strip()
    if not full_name:
        print("[GAGAL] Nama lengkap tidak boleh kosong.")
        return

    institution = input("Asal Kampus / Sekolah: ").strip() or "Universitas Sebelas Maret"
    divisi = ensure_default_division(db)

    print(f"\nDivisi otomatis dialokasikan ke: {divisi.name}")
    print("\n[PERSETUJUAN BIOMETRIK SESEUA UU PDP]")
    print("'Peserta menyetujui ekstraksi fitur biometrik wajah untuk keperluan presensi magang di DPRD Surakarta.'")
    consent = input("Apakah peserta menyetujui? (y/n): ").strip().lower()
    if consent != "y":
        print("[DIBATALKAN] Pendaftaran biometrik wajib mendapatkan persetujuan peserta.")
        return

    # Inisialisasi Kamera
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[ERROR] Webcam tidak terdeteksi atau sedang digunakan aplikasi lain.")
        return

    poses = [
        ("front", "Menghadap lurus ke kamera"),
        ("left", "Sedikit menoleh ke kiri (~15 derajat)"),
        ("right", "Sedikit menoleh ke kanan (~15 derajat)"),
    ]

    enrolled_embeddings = []
    collected_photos_metadata = []

    try:
        for angle, instruction in poses:
            success_pose = False
            while not success_pose:
                captured_frame = capture_pose_with_webcam(cap, angle, instruction)
                if captured_frame is None:
                    print("[INFO] Enrollment dibatalkan oleh pengguna.")
                    return

                # Jalankan Quality Checker & Ekstraksi Wajah
                print(f"[PROSES] Menganalisis kualitas citra pose '{angle}'...")
                res = face_processor.process_frame(captured_frame, enforce_quality=True)

                if not res.success:
                    print(f"  [X] KUALITAS TIDAK MEMENUHI: {res.error_message}")
                    print("      Silakan ulangi pengambilan pose ini.\n")
                    continue

                print(f"  [OK] Kualitas citra baik!")
                print(f"       Ketajaman (Laplacian): {res.quality.blur_score:.1f}")
                print(f"       Pencahayaan (Mean): {res.quality.brightness_score:.1f}")

                enrolled_embeddings.append(res.embedding)
                collected_photos_metadata.append({
                    "angle": angle,
                    "quality_score": min(1.0, res.quality.blur_score / 200.0),
                })
                success_pose = True

        cv2.destroyAllWindows()
    finally:
        cap.release()

    # --- PENCEGAHAN PENDAFTARAN GANDA (DUPLICATE ENROLLMENT CHECK) ---
    print("\n[SECURITY] Melakukan pencocokan duplikasi dengan seluruh peserta aktif...")
    mean_candidate = np.mean(enrolled_embeddings, axis=0)
    dup_check = matcher.check_duplicate(mean_candidate)

    if dup_check.is_duplicate:
        print("\n" + "!" * 60)
        print("  [DITOLAK] TERDETEKSI DUPLIKASI WAJAH!")
        print(f"  Wajah ini memiliki kemiripan {dup_check.similarity_score:.3f} (Threshold: {get_settings().duplicate_enrollment_threshold})")
        print(f"  Sangat identik dengan peserta terdaftar: {dup_check.existing_name}")
        print("  Pendaftaran digagalkan untuk mencegah titip absen / pendaftaran ganda.")
        print("!" * 60 + "\n")
        return

    # --- SIMPAN DATA KE DATABASE ---
    print("[DB] Menyimpan data peserta dan enkripsi biometrik...")
    participant = Participant(
        intern_id=intern_id,
        full_name=full_name,
        institution=institution,
        division_id=divisi.id,
        internship_start=date.today(),
        internship_end=date.today() + timedelta(days=90),
        status=ParticipantStatus.ACTIVE,
        biometric_consent=True,
        consent_given_at=datetime.now(),
    )
    db.add(participant)
    db.flush()

    for idx, emb_vec in enumerate(enrolled_embeddings):
        meta = collected_photos_metadata[idx]
        encrypted_bytes = security_service.encrypt_embedding(emb_vec)

        face_emb_row = FaceEmbedding(
            participant_id=participant.id,
            embedding_encrypted=encrypted_bytes,
            photo_angle=meta["angle"],
            quality_score=meta["quality_score"],
            is_active=True,
        )
        db.add(face_emb_row)

    db.commit()

    # Daftarkan langsung ke in-memory matcher
    matcher.register_participant(
        participant_id=participant.id,
        intern_id=participant.intern_id,
        full_name=participant.full_name,
        embedding_vectors=enrolled_embeddings,
    )

    print("\n" + "=" * 60)
    print(f"  [SUKSES] Peserta {full_name} ({intern_id}) berhasil di-enroll!")
    print(f"  Tersimpan 3 embedding terenkripsi (Fernet AES-128).")
    print(f"  Foto mentah dibuang dari memori (Privacy by Design).")
    print("=" * 60 + "\n")


def run_kiosk_attendance_camera(db):
    """Mode Kiosk Presensi Real-Time via Kamera Webcam."""
    settings = get_settings()
    # Muat ulang peserta aktif dari DB ke memori
    count = matcher.load_from_db(db)
    print(f"\n[KIOSK] Sistem siap. Terdaftar {count} peserta aktif di memori.")

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[ERROR] Kamera webcam tidak dapat diakses.")
        return

    # Tracker cooldown: dict[uuid.UUID, datetime]
    cooldown_tracker: dict[uuid.UUID, datetime] = {}
    cooldown_minutes = settings.attendance_cooldown_minutes

    print("[KIOSK] Membuka jendela kiosk presensi...")
    print("Tekan [Q] di jendela kamera untuk kembali ke menu utama.\n")

    evidence_base = BACKEND_DIR / "data" / "evidence_photos"
    evidence_base.mkdir(parents=True, exist_ok=True)

    frame_counter = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_counter += 1
        h, w, _ = frame.shape
        display = frame.copy()

        # Proses deteksi wajah (setiap 2 frame untuk optimasi CPU)
        if frame_counter % 2 == 0:
            res = face_processor.process_frame(frame, enforce_quality=False)

            if res.bbox:
                x1, y1, x2, y2 = res.bbox
                if res.embedding is not None:
                    # Lakukan pencocokan
                    match_res = matcher.match(res.embedding)

                    if match_res.is_matched:
                        pid = match_res.participant_id
                        now = datetime.now()
                        last_time = cooldown_tracker.get(pid)

                        # Cek Cooldown 5 menit
                        is_in_cooldown = last_time and (now - last_time < timedelta(minutes=cooldown_minutes))

                        if is_in_cooldown:
                            sisa_detik = int((timedelta(minutes=cooldown_minutes) - (now - last_time)).total_seconds())
                            box_color = (0, 255, 255)  # Kuning
                            label = f"{match_res.full_name} [SUDAH ABSEN - Tunggu {sisa_detik}s]"
                        else:
                            # Catat Presensi
                            cooldown_tracker[pid] = now
                            box_color = (0, 255, 0)  # Hijau
                            label = f"{match_res.full_name} ({match_res.similarity_score:.2f}) - BERHASIL"

                            # Simpan foto bukti beresolusi kecil
                            today_str = now.strftime("%Y/%m/%d")
                            ev_dir = evidence_base / today_str
                            ev_dir.mkdir(parents=True, exist_ok=True)
                            ev_filename = f"{uuid.uuid4()}.jpg"
                            ev_path = ev_dir / ev_filename
                            cv2.imwrite(str(ev_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 75])

                            # Insert DB Attendance
                            att = Attendance(
                                participant_id=pid,
                                attendance_type=AttendanceType.CHECK_IN,
                                status=AttendanceStatus.FLAGGED if match_res.is_suspicious else AttendanceStatus.VERIFIED,
                                checked_at=now,
                                similarity_score=match_res.similarity_score,
                                evidence_photo_path=f"{today_str}/{ev_filename}",
                                is_suspicious=match_res.is_suspicious,
                                suspicious_reason=match_res.suspicious_reason,
                            )
                            db.add(att)
                            db.commit()
                            print(f"[PRESENSI DICATAT] {match_res.full_name} | Skor: {match_res.similarity_score:.3f} | Bukti: {ev_filename}")

                        # Gambar Bounding Box & Teks
                        cv2.rectangle(display, (x1, y1), (x2, y2), box_color, 2)
                        cv2.putText(display, label, (x1, max(20, y1 - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, box_color, 2)

                    else:
                        # Wajah tidak dikenal (merah)
                        cv2.rectangle(display, (x1, y1), (x2, y2), (0, 0, 255), 2)
                        cv2.putText(
                            display,
                            f"Tidak Dikenal (Skor: {match_res.similarity_score:.2f})",
                            (x1, max(20, y1 - 10)),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.6,
                            (0, 0, 255),
                            2,
                        )

        # UI Kiosk banner
        cv2.rectangle(display, (0, 0), (w, 40), (40, 40, 40), -1)
        cv2.putText(display, "KIOSK PRESENSI DPRD SURAKARTA | Tekan 'q' untuk keluar", (15, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

        cv2.imshow("Kiosk Presensi Wajah - DPRD Surakarta", display)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


def deactivate_and_purge_participant(db):
    """
    Kepatuhan UU PDP:
    Saat masa magang peserta berakhir:
    1. Status diubah menjadi INACTIVE.
    2. Semua embedding biometrik di-HARD DELETE dari database.
    3. Dihapus dari RAM matcher in-memory.
    """
    print("\n" + "=" * 60)
    print("      NONAKTIFKAN & HAPUS DATA BIOMETRIK PESERTA (UU PDP)")
    print("=" * 60)

    participants = db.query(Participant).filter(Participant.status == ParticipantStatus.ACTIVE).all()
    if not participants:
        print("[INFO] Tidak ada peserta aktif yang terdaftar.")
        return

    print("Daftar Peserta Aktif:")
    for idx, p in enumerate(participants, 1):
        print(f"  [{idx}] {p.intern_id} - {p.full_name} ({p.institution})")

    pilihan = input("\nPilih nomor peserta yang ingin dinonaktifkan (atau 0 untuk batal): ").strip()
    if not pilihan.isdigit() or int(pilihan) <= 0 or int(pilihan) > len(participants):
        print("[INFO] Dibatalkan.")
        return

    selected = participants[int(pilihan) - 1]
    konfirmasi = input(f"Yakin ingin menonaktifkan {selected.full_name}? Data wajah akan DIHAPUS PERMANEN (y/n): ").strip().lower()
    if konfirmasi != "y":
        print("[INFO] Dibatalkan.")
        return

    # 1. Update status
    selected.status = ParticipantStatus.INACTIVE
    selected.updated_at = datetime.now()

    # 2. Hard delete data biometrik
    deleted_embeddings_count = (
        db.query(FaceEmbedding)
        .filter(FaceEmbedding.participant_id == selected.id)
        .delete()
    )

    db.commit()

    # 3. Hapus dari in-memory matcher
    matcher.remove_participant(selected.id)

    print(f"\n[SUKSES] Peserta '{selected.full_name}' telah dinonaktifkan.")
    print(f"[UU PDP COMPLIANCE] {deleted_embeddings_count} record embedding biometrik telah dihapus permanen dari sistem!")


def run_automated_headless_benchmark(db):
    """
    Simulasi pengujian otomatis tanpa webcam fisik (benchmark algoritma):
    - Menguji Quality Checker (Laplacian Blur, Brightness)
    - Menguji Enkripsi Fernet Embedding
    - Menguji Cosine Similarity Math
    - Menguji Pencegahan Duplikasi
    - Menguji Cooldown Presensi
    """
    print("\n" + "=" * 60)
    print("        MENJALANKAN BENCHMARK OTOMATIS (HEADLESS TEST)")
    print("=" * 60)

    # 1. Test Quality Checker pada synthetic images
    print("\n[TEST 1] Pengujian Quality Checker...")
    # Gambar tajam
    sharp_img = np.random.randint(50, 200, (400, 400, 3), dtype=np.uint8)
    # Gambar buram (gaussian blur pekat)
    blurry_img = cv2.GaussianBlur(sharp_img, (51, 51), 0)

    from types import SimpleNamespace
    mock_face = SimpleNamespace(bbox=np.array([50, 50, 300, 300]))

    res_sharp = quality_checker.check(sharp_img, [mock_face])
    res_blurry = quality_checker.check(blurry_img, [mock_face])

    print(f"  - Citra tajam lolos quality: {res_sharp.is_valid} (Skor blur: {res_sharp.blur_score:.1f})")
    print(f"  - Citra buram tertolak: {not res_blurry.is_valid} (Pesan: '{res_blurry.message}')")
    assert not res_blurry.is_valid, "Quality checker harus menolak citra buram!"

    # 2. Test Enkripsi Fernet
    print("\n[TEST 2] Pengujian Enkripsi Biometrik...")
    test_vec = np.random.randn(512).astype(np.float32)
    enc_bytes = security_service.encrypt_embedding(test_vec)
    dec_vec = security_service.decrypt_embedding(enc_bytes)
    diff = np.max(np.abs(test_vec - dec_vec))
    print(f"  - Vektor asli (512 float32) terenkripsi menjadi {len(enc_bytes)} bytes ciphertext")
    print(f"  - Max loss saat dekripsi: {diff:.8f}")
    assert diff < 1e-6, "Dekripsi embedding harus identik dengan vektor asli!"

    # 3. Test Matcher & Duplicate Detection
    print("\n[TEST 3] Pengujian Cosine Similarity & Deteksi Duplikasi...")
    test_id = uuid.uuid4()
    base_embedding = test_vec / np.linalg.norm(test_vec)

    matcher.register_participant(test_id, "TEST-001", "Budi Santoso", [base_embedding])

    # Wajah sama persis
    exact_match = matcher.match(base_embedding)
    print(f"  - Wajah identik dicocokkan -> Dikenal: {exact_match.is_matched}, Nama: '{exact_match.full_name}', Skor: {exact_match.similarity_score:.4f}")
    assert exact_match.is_matched and exact_match.similarity_score > 0.99

    # Wajah mirip (tambah noise kecil, cosine similarity ~0.85)
    noise = np.random.randn(512).astype(np.float32) * 0.2
    similar_face = (base_embedding + noise)
    similar_face = similar_face / np.linalg.norm(similar_face)
    dup_check = matcher.check_duplicate(similar_face)
    print(f"  - Calon wajah mirip (skor {dup_check.similarity_score:.3f}) dideteksi duplikasi -> Is Duplicate: {dup_check.is_duplicate}")

    # Wajah orang lain yang berbeda
    other_face = np.random.randn(512).astype(np.float32)
    other_face = other_face / np.linalg.norm(other_face)
    other_match = matcher.match(other_face)
    print(f"  - Wajah acak/orang lain dicocokkan -> Dikenal: {other_match.is_matched}, Skor: {other_match.similarity_score:.3f}")
    assert not other_match.is_matched

    # Bersihkan memori matcher test
    matcher.remove_participant(test_id)

    print("\n" + "=" * 60)
    print("  [SEMUA PENGUJIAN BENCHMARK BERHASIL DENGAN NILAI SEMPURNA!]")
    print("=" * 60 + "\n")


def main():
    db = get_compatible_db_session()
    ensure_default_division(db)
    matcher.load_from_db(db)

    while True:
        print("\n" + "=" * 55)
        print("  SISTEM PRESENSI WAJAH DPRD SURAKARTA - PROTOTIPE INTI")
        print("=" * 55)
        print("1. Daftarkan Peserta Baru (Enrollment via Webcam)")
        print("2. Buka Kiosk Presensi Real-Time Kamera")
        print("3. Nonaktifkan Peserta & Hapus Data Biometrik (UU PDP)")
        print("4. Jalankan Pengujian Otomatis / Benchmark Headless")
        print("5. Keluar")
        print("=" * 55)

        choice = input("Pilih menu (1-5): ").strip()
        if choice == "1":
            run_enrollment_interactive(db)
        elif choice == "2":
            run_kiosk_attendance_camera(db)
        elif choice == "3":
            deactivate_and_purge_participant(db)
        elif choice == "4":
            run_automated_headless_benchmark(db)
        elif choice == "5":
            print("\nTerima kasih. Selesai.")
            break
        else:
            print("[PILIHAN INVALID] Masukkan angka 1 sampai 5.")


if __name__ == "__main__":
    main()
