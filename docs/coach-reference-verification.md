# Bukti integrasi Coach — 23 November 2026

Branch pekerjaan: `codex/coach-reference-api`; main tidak diubah. Belum commit,
push, merge, redeploy, atau aktivasi mode analyzer pada API Vercel. Default
aplikasi tetap mode static. [Kontrak dan setup](coach-reference-api.md).

## Baseline source main

Source main diekstrak dengan `git archive --format=zip main` ke folder privat
`.cache/coach-api-main-baseline`. Tes dijalankan menggunakan interpreter venv
existing dari root salinan tersebut:

```powershell
python -m pytest -q --basetemp="C:\Projek Software\silatsense-be\.cache\pytest-coach-main-isolated"
```

Hasil: **360 passed, 20 skipped, 26 warnings dalam 51,42 detik**. Salinan main
tidak menyertakan artifact pose privat: dua tes MediaPipe opsional ikut skip,
selain 18 tes khusus MySQL. Log: `.cache/coach-main-isolated-tests.log`.
Tidak menyalin `.env`, database atau kredensial ke snapshot source.

## Suite akhir branch

```powershell
python -m pytest -q --basetemp=.cache/pytest-coach-api-release --tb=short
```

Hasil: **377 passed, 18 skipped, 26 warnings dalam 59,55 detik**.
Log: `.cache/coach-api-release-tests.log`. Artifact pose lokal tersedia sehingga
dua tes inference opsional yang di-skip pada snapshot main berjalan di suite akhir.
Penambahan mencakup 15 kasus temporal API/worker dan launcher env.

Database API memakai SQLite terisolasi; migration tests memakai file SQLite
sementara terpisah. TEST_DATABASE_URL dan MIGRATION_TEST_DATABASE_URL dikosongkan
untuk proses tes. B2 diuji dengan adapter S3 berversi sintetis; SMTP existing
menggunakan fixture/loopback. Tidak menjalankan Docker, mengirim email nyata,
atau menulis data aplikasi ke database development/Filess selama suite.
18 tes khusus MySQL tidak dijalankan; suite ini bukan bukti regresi penuh MySQL.
Warning berasal dari deprecation Starlette/httpx dan konfigurasi path Alembic existing.

TestClient tersangkut pada pembatas sandbox Windows. Pengujian diulang secara
native di luar sandbox dengan target database yang tetap terisolasi; percobaan
yang tersangkut dihentikan dan tidak dihitung sebagai tes lulus.

Kasus penting yang diperiksa:

- Target gerakan wajib dan cocok dengan kategori; idempotensi membedakan target.
- Snapshot analyzer/target/hash saat reservasi B2, sebelum complete; perubahan
  konfigurasi berikutnya tidak mengubah makna reservasi tersebut.
- Hash artifact hilang/berubah, payload yang tidak valid, dan hasil yang tidak
  sesuai snapshot job ditolak; tidak mengganti model secara diam-diam.
- Serialisasi perbandingan per waktu, unit rasio torso, koordinat image-normalized,
  filter visibility, gap pose, serta batas payload timeline 900 observasi.
- Ownership Member dan akses Coach aktif; pencabutan binaan mencabut akses timeline.
- Detail histori menyertakan hasil baru; hasil null tidak menjadi sampel skor dashboard.
- Mode statis, playback, auth dan seluruh tes existing tetap lulus.
- Env worker dimuat sebelum app settings; --check tidak mengambil pekerjaan,
  kredensial/path sensitif tidak masuk pesan kegagalan, cleanup/queue_status memakai
  env yang dipilih.

## Smoke inference nyata melalui API dan worker

Helper privat `.cache/dataset-label-review-20261123/smoke_temporal_api.py`
memakai SQLite baru dengan migrasi 0001–0008 dan seed empat kategori. API diakses
melalui FastAPI TestClient native; worker menjalankan subprocess inference
MediaPipe nyata. Ini bukan tes HTTP jaringan eksternal/deployment Vercel.

Hasil versi akhir:

| Pemeriksaan | Hasil |
| --- | --- |
| Upload multipart lokal, worker, evaluation/pose/history untuk 12 gerakan | 12/12 completed, reference_compared, comparison.status=compared |
| Video playback dengan Range | 12/12 HTTP 206 |
| Resolusi perbandingan | 32 titik waktu per video |
| Pose timeline observasi aktual | 35–63 frame pada video yang diuji |
| Skor seluruh hasil temporal | Null, bukan nol atau skor buatan |
| Video sintetis kosong tambahan | Completed, insufficient_pose, not_assessable, timeline kosong |
| Dashboard setelah 12 video dan video kosong | completedSessionCount=13, scoredSessionCount=0 |
| Pengguna lain membaca evaluation/pose/video | HTTP 404 |
| Video setelah expiry | HTTP 410; hasil evaluation tetap HTTP 200 |
| Alembic check | No new upgrade operations detected pada DB smoke terisolasi |
| Model verifier | Checksum pose/referensi dan versi dependency cocok |

Bukti JSON privat:
`.cache/coach-api-native-smoke-20261123-v3/verification.json`,
hasil evaluation/pose setiap gerakan dalam folder tersebut, dan
`.cache/coach-api-native-smoke-v3.log`.
Tidak mengunggah video dataset ke B2 atau mengubah file video asli.

Percobaan smoke pertama memakai DB baru tanpa seed kategori dan mendapat 404;
fixture diperbaiki dengan seed kategori existing. Percobaan berikutnya dan smoke
akhir di atas lulus. Regresi awal pada respons config tambahan dan pengaturan
proses inference juga diperbaiki sebelum suite akhir.

## Kesiapan worker laptop yang dipilih pengguna

Artifact privat disalin ke `.data/models/coach-reference-<sha256>.json` dan
konfigurasi terpisah dibuat pada `.env.worker`; `.env` development tidak diubah.
`git check-ignore` mengonfirmasi file konfigurasi dan folder model diabaikan Git.
Secret tidak ditampilkan atau dimasukkan ke source/dokumentasi.

```powershell
python -m scripts.worker --env-file .env.worker --check
```

Hasil nyata: `{"status":"ready","analysisMode":"coach-reference","workerActive":false}`.
Log privat: `.cache/laptop-worker-check.log`.
Pemeriksaan mencakup model/dependency, SELECT 1 dan revisi 0008 pada Filess,
serta probe marker kecil B2 yang dibaca dan dihapus beserta versinya. Tidak ada
pekerjaan antrean yang diklaim, tidak ada perubahan schema/data aplikasi, tidak
menjalankan cleanup massal atau memulai proses worker persisten.

## Pemeriksaan source

- Ruff critical: `python -m ruff check --select E9,F63,F7,F82 app scripts tests alembic` lulus.
- Format check 24 modul yang diperiksa CI, termasuk modul Coach/launcher baru, lulus.
- `python -m scripts.export_openapi --check` cocok; `docs/openapi.json` diperbarui.
- `git diff --check` lulus. Tidak ada migrasi atau dependency tambahan.
- Workflow CI ditambah format check modul baru; CI remote/container build belum dijalankan.

Kelompok file perubahan:

| Bagian | File utama |
| --- | --- |
| Kontrak ringan dan konfigurasi analyzer | intelligence/coach_contracts.py, core/config.py, services/analysis_config.py |
| Integrasi inference dan penyimpanan hasil | services/coach_analysis.py, analysis_process.py, worker.py, repositories/jobs.py |
| Request/response dan katalog | schemas/temporal.py, results.py, uploads.py, domain.py; api/sessions.py, health.py; services/results.py, sessions.py, uploads.py, training.py |
| Metadata ekstraksi | intelligence/movement_video.py, movement_features.py |
| Launcher/verifier laptop | scripts/process_env.py, verify_coach_model.py, worker.py, cleanup_media.py, queue_status.py |
| Tes | test_coach_analysis_api.py, test_worker_env.py, pembaruan ekspektasi aditif test_profiles_training.py |
| Handoff | README, .env.example, OpenAPI, api-contract, frontend-handoff, dua dokumen Coach ini, workflow CI |

## Batas klaim dan pekerjaan tersisa

Kode integrasi backend selesai dan lulus tes native di atas. Ini tidak
membuktikan akurasi koreksi kesalahan pemula, ketersediaan layanan 24 jam,
kapasitas multiuser, atau deployment Vercel sudah memakai analyzer baru.
Tidak ada perubahan FE pada pekerjaan ini. Aktivasi online memerlukan merge/
redeploy, pilihan movementId di FE dan konfigurasi API yang sesuai worker laptop.
Worker persisten/cleanup belum dimulai. Rekaman pemula dengan catatan Coach dan
rekaman baru untuk evaluasi akhir masih diperlukan untuk validasi kualitas.
