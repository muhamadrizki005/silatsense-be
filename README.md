# SilatSense Backend

**Pembaruan 19 Oktober 2026:** route/schema HTTP prototype yang sudah punya
pengganti telah dihapus. Auth hanya memakai sign-up/sign-in/session/refresh-session/logout;
profil, katalog, sesi dan binaan memakai kontrak Member/Coach. Data existing tetap
dipertahankan. [Pemetaan dan pengujian](docs/route-cleanup.md).
Regresi pembersihan: SQLite **212 passed/18 skipped**, MySQL native terisolasi
**230 passed**, dan `alembic check` development lulus.

Untuk tim frontend: **[panduan serah terima dan prioritas integrasi](docs/frontend-handoff.md)**.

Verifikasi lokal terbaru: **[44 operasi API, MySQL terisolasi, HTTP dan worker native](docs/local-api-verification.md)**.

Untuk tes manual: **[panduan Postman dari startup sampai review/recovery](docs/postman-guide.md)**,
[collection](docs/postman/SilatSense.postman_collection.json), dan
[environment tanpa secret](docs/postman/SilatSense.local.postman_environment.json).

Deployment: [perbaikan ukuran bundle dan kebutuhan operasional Vercel](docs/vercel-deployment.md).

Backend mandiri hasil pemisahan dari `capstone-prototype` pada 14 Oktober 2026. FastAPI, Python 3.12, SQLAlchemy/Alembic, MySQL 8 (native 8.0/Compose 8.4), OpenCV, dan MediaPipe. Auth, recovery email, profil/katalog, sesi/worker, evaluasi/media, histori dan review Coach tersedia. Bridge auth/keamanan FE terhubung; data latihan FE masih demo.

**Native adalah mode utama untuk aplikasi dan tes. Docker bersifat opsional bila diminta/disepakati.** Fase 6–7 memakai MySQL native sementara terpisah untuk pengujian, tanpa menyalakan Docker.

## Status database native — 18 Oktober 2026

Koneksi `.env` pengguna ke MySQL `localhost:3306`, database `silatsense`, sudah
berhasil. Database dibuat setelah dipastikan belum ada, migrasi **0007** diterapkan,
dan **alembic check lulus**. Katalog empat gerakan terisi; akun, sesi latihan dan
profil referensi tidak dibuat. Profil prototype tidak diimpor karena dataset/
validasi intelligence belum tersedia.

API native sementara telah diverifikasi: liveness, readiness DB/storage, Swagger
serta OpenAPI semuanya HTTP 200; worker --once berhasil dengan antrean kosong.
Proses API pengujian sudah ditutup; database development tetap disimpan.
SMTP Zoho kini sudah dikonfigurasi secara lokal: TLS/login dan satu pengiriman
nyata berhasil; penerima melaporkan pesan masuk Spam. Pengujian recovery lewat API
dengan Zoho nyata belum dilakukan. Docker tidak dijalankan.

## Status Fase 7 — 18 Oktober 2026

- Link email dengan reautentikasi, verifikasi existing email, reset hanya verified
  email, token hash sekali pakai/expiry, rate limit database dan pencabutan sesi.
- SMTP adapter + memory/loopback test, bridge cookie FE terenkripsi, single-flight
  refresh 30 detik, login/logout dan halaman keamanan akun nyata.
- OpenAPI snapshot/collection HTTP, readiness/liveness, structured request logs,
  queue diagnostics, CI source dan container non-root; backup/restore native diuji.

Migrasi additive **0007**; development/.env/prototype tidak diubah. Setup,
hasil tes aktual, file berubah dan batas integrasi: **[docs/phase7-api.md](docs/phase7-api.md)**.
SQLite final **204 lulus, 18 skip**, MySQL native final **220 lulus**, FE **249 lulus** + build/typecheck/lint hijau.
SMTP nyata tetap disabled sampai dikonfigurasi; API_BASE_URL dan secret bridge FE
perlu disiapkan secara privat. CI remote/container build belum dijalankan.

Bagian status Fase 1–6 di bawah adalah catatan historis, bukan status recovery/FE terkini.

## Status Fase 6 — 18 Oktober 2026

- Satu Coach aktif per Member, CLI `python -m scripts.assign_coach` untuk assign/transfer/revoke dengan histori transaksi; endpoint Coach lama/baru kini dibatasi binaan.
- Roster/overview, histori/detail/pose/video privat Coach; transfer mencabut akses lama dan menutup stream, author historis dipertahankan.
- Draft privat dengan versi, publish/revisi immutable dan idempotent, tugas Member serta retry-intent; keputusan manusia terpisah dari skor analyzer.

Migrasi additive **0006** menambah tabel binaan/review/tugas; tidak mengubah data existing atau menugaskan Member otomatis. Database development, `.env`, FE dan rumus skor tidak diubah. Panduan endpoint, CLI dan bukti native: **[docs/phase6-api.md](docs/phase6-api.md)**. Suite SQLite: **185 lulus, 15 skip** khusus MySQL; MySQL native **200 lulus**. Smoke HTTP native assign→upload/worker→publish/revisi→transfer/revoke berhasil. Berikutnya Fase 7 bridge FE dan linking/verifikasi email/password reset.

## Status Fase 5 — 18 Oktober 2026

- GET `/api/v1/member/history`: pagination cursor default 20/maksimum 100, urutan waktu+ID menurun, filter kategori/status/review/rentang UTC, scope pemilik.
- GET `/api/v1/member/history/{sessionId}`: detail sesi/evaluasi nullable dan catatan legacy beserta author asli.
- GET `/api/v1/member/dashboard`: kelompok skor comparable dengan sampleCount, durasi verified, lastSession, latestCoachNote, kategori dominan dan aktivitas Senin–Minggu Asia/Jakarta.

Migrasi additive **0005** hanya menambah indeks histori/dashboard. Database development, `.env`, FE, auth dan rumus skor tidak diubah. Panduan dan bukti: **[docs/phase5-api.md](docs/phase5-api.md)**. SQLite: **158 lulus, 11 skip** khusus MySQL; suite Linux/MySQL disposable: **169 lulus**. Smoke HTTP upload→worker→histori/dashboard berhasil, termasuk expiry dan delete. Binaan/review/tindak lanjut kini tersedia pada Fase 6; bridge FE/email recovery tetap Fase 7.

## Status Fase 4 — 17 Oktober 2026

- GET `/api/v1/member/sessions/{sessionId}/evaluation` dan `/pose`: hasil bertipe camelCase, measurement mentah beserta unit dan overlay landmark tersimpan untuk analisis baru; histori lama tetap nullable dengan alasan.
- GET `/api/v1/member/sessions/{sessionId}/video`: playback privat 200/206, single/suffix Range, owner-only, expiry tepat 24 jam dan penghentian stream saat akses dicabut.
- POST `/api/v1/member/sessions/{sessionId}/acknowledge`: timestamp pertama idempotent; DELETE sesi: soft-delete, fencing worker dan cleanup, hasil/catatan audit dipertahankan.

Panduan endpoint, perilaku legacy, integrasi FE dan bukti tes: **[docs/phase4-api.md](docs/phase4-api.md)**. Fase 4 memakai JSON/kolom existing; head saat fase tersebut **0004**, tanpa migrasi baru. Database development, `.env`, FE dan prototype tidak diubah. Histori/dashboard kini tersedia pada Fase 5 di atas.

Suite final SQLite: **128 lulus, 11 skip** khusus MySQL; suite Linux/MySQL disposable: **138 lulus**, diikuti **2 regresi akhir lulus** untuk expiry saat DB lambat dan audit setelah delete. Smoke HTTP Linux upload→worker→evaluasi→Range→expiry→delete berhasil. Pengujian memakai data/schema sementara; bukan benchmark atau validasi skor pada manusia.

## Status Fase 3 — 17 Oktober 2026

Upload persisten dan worker tersedia pada kode dengan migrasi additive **`0004`**:

- `POST /api/v1/member/sessions` — upload 202, validasi video, kuota dan idempotensi.
- `GET /api/v1/member/sessions/{sessionId}` — status queued/processing/completed/failed dan metadata privat, owner-only.
- Worker CLI terpisah dengan antrean MySQL, lease/heartbeat, fencing, retry terbatas dan snapshot referensi/model; cleanup media 24 jam dan orphan.
- Compose opsional memiliki satu migration step, API/worker/cleanup, serta volume media terpisah. Native tetap mode utama.

Panduan request, migrasi, tiga proses native dan batas fase: **[docs/phase3-api.md](docs/phase3-api.md)**. MySQL disposable **104 tes lulus**; SQLite **95 lulus, 9 skip** khusus MySQL. Smoke test Linux API→upload→worker berhasil, termasuk inference MediaPipe pada video sintetis kosong dengan skor null dan replay idempotent. Ini bukan benchmark atau validasi gerakan silat manusia.

Status historis Fase 3: evaluasi/pose/playback/acknowledge/DELETE saat itu belum tersedia. Semuanya kini tersedia pada Fase 4 di atas; evaluationUrl aktif dan playbackPath diisi untuk media available. Database development belum dimigrasi dan `.env`/FE tidak diubah.

## Status Fase 2 — 17 Oktober 2026

Fase 2 sudah diimplementasikan pada kode, dengan migrasi additive **`0003`**:

- GET/PATCH profil Member/Coach, nullable NPM/email, whitelist biodata.
- PATCH password per role: verifikasi password lama, pencabutan seluruh sesi lewat authVersion, wajib login ulang; DTO/cookie/rememberMe auth tetap kompatibel.
- Katalog empat kategori, persiapan/panduan bersumber, konfigurasi upload, capability berdasarkan referensi valid; panduan yang belum dikurasi kosong.

Panduan endpoint, contoh HTTP, migrasi dan bukti pengujian: **[docs/phase2-api.md](docs/phase2-api.md)**. Tes SQLite: **69 passed, 4 skipped** (race khusus MySQL). Suite API/security MySQL disposable: **73 passed**. Tes migrasi MySQL terpisah: **2 passed**, termasuk preservasi data 0002 dan alembic check.

Database development belum dimigrasi; `.env` dan FE tidak diubah. Verifikasi koneksi native di bawah sebelum menerapkan migrasi. Worker/upload persisten tersedia sejak **Fase 3**, binaan/review sejak Fase 6, linking/verifikasi email/reset serta integrasi FE tetap Fase 7. Endpoint Coach prototype kini dibatasi binaan pada Fase 6.

## Status Fase 1 — 17 Oktober 2026

Fase 1 menyelesaikan audit dan dokumentasi, **bukan implementasi endpoint domain baru**:

- [Kontrak API](docs/api-contract.md): endpoint aktual/rencana, DTO, nullability, pagination, media 24 jam, binaan dan review.
- [Arsitektur dan baseline](docs/architecture.md): bukti tes, batas analisis, rancangan worker/storage/migrasi dan konfigurasi native/Docker.
- [Integrasi FE dan matriks field](docs/fe-integration.md): pemetaan seluruh DTO FE, cookie bridge, refresh paralel dan perubahan UI.
- [Auth existing](docs/auth-api.md): kontrak login/registrasi/session/refresh/logout yang dipertahankan.

Baseline historis Fase 1: **31 passed, 1 warning in 2.30s**. Kode bisnis, auth, migrasi, `.env`, database, frontend dan prototype tidak diubah pada Fase 1. Fase 2 kini selesai pada kode sebagaimana status di atas.

Mode development utama adalah native FastAPI/worker, memakai MySQL lokal `localhost:3306`, user `root`, database `silatsense`. Konfigurasi `.env` pengguna telah diverifikasi dan database berada pada head `0007`. Password tidak dicantumkan di dokumentasi. Jangan memakai atau mengubah database `event_sportainment` maupun prototype.

## Pengembangan native

Jalankan seluruh perintah dari root proyek. Python 3.12 diperlukan:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-lock.txt
```

Untuk native, siapkan `DATABASE_URL` lokal menuju target MySQL yang benar sesuai bagian status di atas, tanpa mencetak password. Compose existing tidak mempublikasikan port 13307. `.env.example` masih contoh konfigurasi Compose; jangan menimpa `.env` native pengguna dengannya. Perintah berikut dijalankan **setelah konfigurasi dan target database diverifikasi**:

```powershell
.venv/Scripts/alembic.exe upgrade head
.venv/Scripts/alembic.exe check
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --no-access-log
```

Katalog database native sudah diisi. `scripts.seed` default juga mengimpor profil referensi prototype, sehingga tidak dijalankan dalam provisioning native ini.

`API_PORT` tidak otomatis mengatur uvicorn native; gunakan flag `--port` eksplisit. Worker/cleanup tersedia pada Fase 3; jalankan pada terminal berbeda setelah konfigurasi/migrasi yang benar, memakai database dan MEDIA_ROOT yang sama:

```powershell
.venv/Scripts/python.exe -m scripts.worker
.venv/Scripts/python.exe -m scripts.cleanup_media
```

Keduanya mendukung `--once`. Jalankan API, worker dan cleanup agar antrean berjalan dan file expired dibersihkan; konfigurasi baru ada di `.env.example` tanpa menulis `.env` lokal.

## Menjalankan dengan Docker (opsional)

Buka Docker Desktop, lalu dari folder ini:

```powershell
docker compose up -d --build --wait
docker compose ps
```

Compose bersifat opsional. Port default 8000; `API_PORT` lokal saat audit adalah **8001**. Dengan konfigurasi lokal tersebut: [API docs](http://localhost:8001/docs), [health](http://localhost:8001/health), base API `http://localhost:8001/api/v1`. Contoh port 8000 di dokumen auth adalah default, bukan port yang selalu aktif.

`.env` lokal sudah dibuat dengan secret acak. Untuk checkout baru, salin `.env.example` menjadi `.env`, lalu isi password database dan JWT secret. Model pose lokal sudah disalin dari prototype; file `.task` diabaikan Git. Untuk mengunduhnya pada mesin lain:

```powershell
docker compose build
docker compose run --rm --no-deps backend python -m scripts.download_pose_model
```

MySQL Compose hanya tersedia dalam jaringan Docker, memakai volume `silatsense-be_mysql_data` yang terpisah dari MySQL native/prototype. Database native dan Compose tidak otomatis berbagi data meskipun namanya sama. Startup existing menjalankan migrasi dan seed kategori/profil secara idempotent. Registrasi Member tersedia melalui API; untuk membuat akun Coach:

```powershell
docker compose exec backend python -m scripts.seed --coach-email pelatih@example.com --coach-name "Pelatih SilatSense"
```

Password diminta interaktif. Pembuatan akun Coach belum menugaskan binaan; CLI penugasan/transfer/revoke kini tersedia, lihat [phase6-api.md](docs/phase6-api.md). Hentikan layanan dengan `docker compose stop`; data tetap tersimpan. Gunakan port kosong bila 8000 dipakai aplikasi lain. Sesuaikan `FRONTEND_ORIGIN` dengan origin frontend saat integrasi.

## Verifikasi

```powershell
$env:DATABASE_URL = 'sqlite://'
$env:TEST_DATABASE_URL = ''
$env:MIGRATION_TEST_DATABASE_URL = ''
$env:TEMP = 'C:\Projek Software\silatsense-be\.cache'
$env:TMP = $env:TEMP
.venv/Scripts/python.exe -m pytest -q
```

Jalankan tes di atas pada terminal tes khusus. Pada checkout baru buat folder `.cache` terlebih dahulu. Tes API default memakai SQLite memory dan tes migrasi memakai file sementara; variabel URL tes sengaja kosong agar fixture tidak menjalankan create/drop pada MySQL. Jika folder pytest OS mengalami masalah izin, gunakan `--basetemp=.cache/phase4-test-run` dengan direktori khusus tes yang belum dipakai (pytest membersihkan direktori tersebut). Bukti MySQL disposable dan tes Fase 4 ada di [phase4-api.md](docs/phase4-api.md). Peringatan deprecation httpx/TestClient dan Alembic masih ada. Ini belum membuktikan validitas video silat manusia, binaan Coach, integrasi FE, atau kapasitas 10–15 pengguna.

Database development native kini sudah pada head **`0007`** dan `alembic check` lulus. Password akun MySQL tidak direset/diubah. Jalankan tes pada database disposable, bukan schema development. Docker tetap opsional.

`scripts.validate_local --video <video-uji>` memakai alur sesi/worker/review sekarang
dan hanya mengizinkan database `*_test`. API serta worker harus memakai database
disposable yang sama. Script tidak membutuhkan dataset privat dan tidak menulis
password/token ke disk. Jangan mengarahkannya ke database development.

## Struktur

Kontrak autentikasi untuk frontend (NPM/email, login, sesi, refresh, logout):
lihat [docs/auth-api.md](docs/auth-api.md). Alias prototype sudah dihapus.

- `app/api`, `schemas`, `core`: endpoint, kontrak, konfigurasi, autentikasi.
- `app/db`, `models`, `repositories`: persistensi database.
- `app/services`, `intelligence`: upload, decoding video, pose, fitur, evaluasi, feedback.
- `alembic`: migrasi database.
- `artifacts`: model pose lokal dan tujuh profil referensi JSON.
- `scripts`, `tests`: setup, builder referensi, pengujian.
- `docs`: metode evaluasi dan sumber data.

## Batas kemampuan aktual

Skor merupakan kemiripan pose eksperimen terhadap referensi, bukan akurasi atau standar kelulusan IPSI. Kuda-kuda dan tangkisan memiliki referensi; pukulan/tendangan menghasilkan `reference_not_ready` tanpa skor. Upload hanya melalui endpoint sesi: video privat 24 jam dan analisis melalui worker. Playback privat dan data keyframe tersedia sejak Fase 4. Belum ada penghitungan repetisi atau analisis urutan gerak. Detail ada di [docs/evaluation-method.md](docs/evaluation-method.md).

Histori/dashboard Member tersedia sejak Fase 5; scope binaan Coach, review berversi dan tugas tersedia sejak Fase 6, dengan akses hanya untuk binaan aktif. Recovery email/bridge auth tetap Fase 7. FE masih dummy/stub dan belum dihubungkan.
