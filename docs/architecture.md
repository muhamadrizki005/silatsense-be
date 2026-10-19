# Arsitektur, baseline dan status implementasi SilatSense

Tanggal status: 18 Oktober 2026. **Fase 1 dokumentasi; Fase 2–7 sudah diimplementasikan.**
Head source `0007`: profil/katalog/password, upload persisten, storage, job,
worker dan cleanup. Evaluasi/pose/measurements, playback Range privat,
acknowledge/delete tersedia; Fase 4 menyimpan data tambahan dalam result_json,
tanpa migrasi baru. Histori cursor/filter dan dashboard Member tersedia; 0005
hanya menambah indeks. Binaan/CLI/review/tugas tersedia pada 0006; recovery email, rate limit persisten dan bridge auth FE tersedia pada Fase 7.
Data latihan FE masih dummy; deployment belum dilakukan. Native adalah default, termasuk pengujian tanpa Docker
pada Fase 6. Bukti di [phase2-api.md](phase2-api.md), [phase3-api.md](phase3-api.md),
[phase4-api.md](phase4-api.md), [phase5-api.md](phase5-api.md), [phase6-api.md](phase6-api.md), [phase7-api.md](phase7-api.md);
bagian baseline berikut adalah snapshot historis Fase 1.
[api-contract.md](api-contract.md) menetapkan wire contract;
[fe-integration.md](fe-integration.md) memetakan FE dan transport sesi.
Rujukan awal: `capstone-prototype/docs/silatsense-backend-plan.md`, dibaca tanpa
diubah. Keputusan fase pada tiga dokumen ini mengikuti persetujuan terbaru:
penautan/verifikasi email dan password reset di **Fase 7**.

## 1. Audit baseline Fase 1 (historis) dan bukti

| Subsystem | Bukti lokal | Kesimpulan aktual |
| --- | --- | --- |
| HTTP | `app/main.py`, `app/api/routes.py` | FastAPI, CORS origin tunggal, `/api/v1`; router belum dipisahkan per domain |
| Auth | `app/core/security.py`, `app/services/auth.py`, `app/schemas/auth.py` | Password hash, JWT 900 detik, NPM/email, cookie refresh hash di DB, rotasi claim atomik |
| Session auth | `refresh_tokens` | Tanpa rememberMe maksimum 24 jam, persistent 7 hari; rotasi mempertahankan deadline awal |
| Database | `app/models/entities.py`, `alembic/versions/0001_initial.py`, `0002_auth_identifiers.py` | User/NPM/email nullable, refresh, movement/reference, evaluation/issues/notes; belum ada training session/job/media/assignment/review |
| Upload | `app/services/uploads.py` | Streaming ke TemporaryDirectory, whitelist suffix/MIME, ukuran, inference sinkron, cleanup termasuk kegagalan |
| Decoder | `app/services/video.py` | OpenCV decode sequential, validasi metadata, batas durasi, sampling dan resize; belum proses decode terisolasi/timeout |
| Scoring | `app/services/analysis.py`, `app/intelligence/*` | MediaPipe IMAGE, fitur bidang gambar, best-frame static-reference-pose, NoClassifier |
| Persistensi | `app/repositories/evaluations.py` | Hasil/issue/version dan catatan tersimpan; landmark/semua measurement tidak dipersist |
| Coach | routes Coach dan akses detail evaluasi | Role check tersedia, tetapi **Coach dapat membaca Member/evaluasi di luar binaan**; relasi penugasan belum ada |
| FE | types/data/actions/components/specs di `silatsense-fe` | Auth throw stub, data dummy, update profil echo, upload timer, evaluasi per slug, playback placeholder, shared cache dummy |
| Kamera | `camera-experience.tsx` dan komponen kamera FE | Preview/device browser; belum alur upload rekaman nyata end-to-end |
| Runtime | `docker-compose.yml`, `app/core/config.py` | Compose API+MySQL, startup migration/seed; belum worker/storage/cleanup service |

### Baseline Fase 1 yang benar-benar dijalankan

Dari root backend, PowerShell; environment override hanya berlaku pada proses
tes, **tidak menulis `.env`**:

```powershell
$env:DATABASE_URL = 'sqlite://'
$env:TEST_DATABASE_URL = ''
$env:TEMP = 'C:\Projek Software\silatsense-be\.cache'
$env:TMP = $env:TEMP
.venv\Scripts\python.exe -m pytest -q
```

Hasil 17 Oktober 2026: **31 passed, 1 warning in 2.30s**, exit code 0.
Warning: `StarletteDeprecationWarning` penggunaan httpx pada TestClient;
migrasi dependency bukan bagian Fase 1. Di lingkungan agent Windows, tes
dijalankan dengan izin socket lokal di luar sandbox karena event loop
TestClient memerlukan socketpair. Tidak menjalankan server publik.

`tests/conftest.py` memaksa default `DATABASE_URL=sqlite://`; tanpa
`TEST_DATABASE_URL`, fixture memakai SQLite memory dengan StaticPool,
create/drop tabel hanya engine tersebut. Override TEST_DATABASE_URL dikosongkan
secara eksplisit karena bila terisi fixture memang menjalankan drop_all pada
database tes. Jangan mengarahkan variabel ini ke development; suffix `_test`
adalah syarat minimum, bukan izin memakai data penting.

Yang diuji: registrasi/login NPM dan email, validasi/role injection, cookie
rememberMe, refresh rotation/replay/expiry, logout, access token invalid,
profile prototype, isolasi histori Member, catatan/akses role Coach existing,
upload validation/cleanup (analysis dimock), geometri/normalisasi/fitur/skor
sintetis, decoder MP4 sintetis nyata dan file palsu.

Yang **belum dibuktikan**: inference MediaPipe pada video silat nyata, validitas
ilmiah skor, MySQL constraints/migrasi saat audit ini, concurrent refresh pada
MySQL, worker restart/claim, media Range/retensi, binaan/revisi, FE/browser E2E,
throughput 10–15 pengguna. Model lokal ditemukan, bukan bukti inference lulus.

Head source pada baseline Fase 1 adalah `0002` (sekarang `0007`). `alembic check` development **tidak dijalankan pada
Fase 1 ini**: konfigurasi native belum menunjuk target yang disetujui. Tidak
melakukan provisioning, reset, migrasi, seed atau koneksi ke database aplikasi
lain. Pemeriksaan Docker/MySQL pada sesi sebelumnya tidak dianggap sebagai
validasi native `root@localhost:3306/silatsense` hari ini.

### Batas analisis

Referensi artifact: enam varian kuda-kuda (masing-masing 200 pose) dan satu
tangkisan (202 pose), sesuai metode/provenance existing. Pukulan/tendangan
belum memiliki dataset referensi tambahan. Repository menolak debug partial,
feature version tidak cocok, metadata mismatch, dan file di luar reference root.
Capability runtime harus memeriksa profil aktif valid, bukan jumlah file saja.

MediaPipe landmark diproses independen; visibility filter, origin midpoint hip,
skala lebar bahu, dan sudut 2D. Minimal 8 fitur dan coverage 70% fitur referensi
usable; IQR nol dikeluarkan. Score `100/(1+distance)` untuk pasangan pose/profil
terbaik. Hasil ini tidak menunjukkan kualitas seluruh video. Pose tanpa cukup
fitur dapat dihitung sebagai tidak valid; `validPoseFrames` bukan jumlah repetisi.
Tidak ada pronasi, timing impak, beban kaki, koreksi cm, jarak kamera meter,
kelulusan sabuk, atau akurasi model yang tervalidasi. Detail:
[evaluation-method.md](evaluation-method.md), [data-sources.md](data-sources.md).

## 2. Arsitektur target dan storage (rencana Fase 2–4)

Tetap monolit modular: router → schema → service/use case → repository → MySQL
dan storage. Intelligence tidak bergantung HTTP/database. Pisahkan router
bertahap; tidak rewrite menjadi async SQLAlchemy, microservices atau training
model baru. Satu transaksi use case ditanggung service; refactor commit parsial
repository existing hanya saat diperlukan oleh use case fase berikutnya.

Alur baru:

```text
FE upload -> API stream/validate -> private file finalization
          -> DB transaction(session + media + job + idempotency) -> 202
worker -> claim committed job -> MediaPipe existing -> fenced result commit
FE poll -> session/evaluation -> authorized streaming proxy -> private video
cleanup -> expiry check + coordinated unlink; evaluation/review remain
```

API/worker native berbagi `MEDIA_ROOT` lokal privat, default rencana
`./.data/media`; direktori itu harus di-ignore sebelum implementasi menyimpan
file. Gunakan nama acak dan relative storage key, bukan nama upload/path user.
Storage interface: write-temp/finalize/read-range/delete; semua path resolve
harus tetap di root. Reference/model tetap artifact immutable terpisah.
Jangan menyajikan `MEDIA_ROOT` sebagai static directory atau folder public FE.

Retensi dimulai ketika seluruh byte upload diterima; simpan uploadedAt saat itu.
File streaming parsial belum dianggap media selesai; jika validasi/commit gagal,
hapus file atau biarkan reconciler menghapus orphan. Rename/finalize pada
filesystem dan transaksi DB bukan satu transaksi: staged key + cleanup orphan
menutup celah crash. Job dipoll dari DB sehingga tidak ada dual-write queue Redis.

Batas awal upload dari konfigurasi existing: 100 MiB, 60 detik, MP4/MOV/WebM.
Fase 3 menambah quota awal 500 MiB media tersimpan per Member dan maksimal dua
sesi queued/processing per Member, direservasi atomik agar request paralel tidak
melewati batas. Byte expired yang belum dibersihkan tetap dihitung untuk kuota
disk; jalankan cleanup sebelum menolak kuota jika memungkinkan. Semua batas
dikirim lewat konfigurasi upload bila relevan dan dapat dikonfigurasi tanpa
menjanjikan 10–15 proses inference.

Decoder validation dijalankan di child process dengan timeout 30 detik dan
limit resolusi input 3840×2160; inference per job timeout awal 120 detik, dengan
resize existing maksimal 1280. Batas ini operasional awal yang harus diukur,
bukan hasil benchmark; input beyond limit ditolak 422, timeout server transient
503 sebelum penerimaan/failed job setelah penerimaan. Jangan mengandalkan
metadata MIME atau timeout HTTP untuk menghentikan decoder yang macet.

## 3. Worker, retensi, dan kegagalan

Worker persisten adalah CLI terpisah menggunakan SQLAlchemy session sendiri;
bukan BackgroundTasks, thread daemon, atau subprocess yang hilang saat request
selesai. Default satu inference, polling 1 detik, lease 60 detik, heartbeat
15 detik; maksimum 3 attempts, retry transient setelah 5 lalu 30 detik.
Heartbeat memakai koneksi/loop terpisah dari inference blocking. Job timeout
120 detik menghentikan child process; lease bukan izin inference tanpa batas.

Claim pada MySQL 8: transaksi `SELECT ... FOR UPDATE SKIP LOCKED`, pilih job
queued/availableAt atau lease expired yang eligible, tulis claim token baru,
workerId/attempt/leaseUntil, commit. Unique satu job per session cukup untuk
MVP; retry memperbarui job yang sama. Claim token fencing dicek pada heartbeat,
hasil, failure dan cleanup; worker lama tidak boleh commit setelah re-claim.
Result/evaluation dan completed status disimpan dalam satu transaksi dengan
unique evaluation per training session. Tidak menghasilkan dua hasil untuk
dua workers; snapshot referensi versi/checksum diambil saat job dibuat.

Retry hanya transient (koneksi DB, temporary IO/worker crash), bukan video
invalid, model/config/reference corrupt permanen. Tidak ada referensi adalah
hasil completed/reference_not_ready/score null. Media expired sebelum claim
menjadi failed `media_expired`; queued job tidak menunggu tanpa batas.

Cleanup CLI/loop berjalan tiap 60 detik dengan batch terbatas; claim deletion
dan metadata transaksional, unlink idempotent, file hilang dianggap selesai.
File yang sedang diproses ditandai pending deletion, hentikan/fence inference
atau tunggu lease aktif berakhir sebelum unlink; expiry **tetap** menutup akses
playback saat tepat 24 jam. Worker yang tidak sempat selesai sebelum deadline
dihentikan dan job failed/media_expired, bukan memperpanjang retensi. Hasil
yang sudah commit dipertahankan. Orphan staged files tanpa referensi DB hanya
dihapus setelah grace 1 jam agar tidak berbenturan upload aktif.

Delete sesi: periksa owner, soft-delete segera, cancel/fence job, tandai media
untuk cleanup; jangan menunggu unlink untuk mencabut akses. Read/claim/result
commit memeriksa deletedAt. Retention expiry tidak soft-delete sesi. Stream
media memeriksa waktu/akses per chunk dalam transaksi baru. Watchdog terpisah
tiap 0,5 detik memutus juga stream yang stall, dengan timer deadline expiry;
DB harus responsif untuk batas pemeriksaan akses tersebut. Delete/password
revocation dan pemeriksaan binaan/current assignment event sudah berlaku.
Tidak ada janji menarik byte yang telah diunduh.

Worker graceful shutdown berhenti claim, menyelesaikan atau membatalkan child
secara terbatas; lease memberi recovery bila proses mati. Health/readiness
berikutnya membedakan API hidup, DB dapat diakses, dan heartbeat worker; `/health`
existing hanya liveness sederhana. Log requestId/jobId/durasi/errorCode, tanpa
token, password, isi email, video, ataupun path privat.

## 4. Entitas, relasi Coach, dan migrasi

| Fase | Perubahan additive setelah 0002 |
| --- | --- |
| 2 | Profil Member/Coach, metadata katalog, passwordChangedAt dan authVersion pada users/refresh_tokens |
| 3 | training_sessions, media_assets, analysis_jobs, idempotency records; FK session dari evaluation_sessions |
| 4 | Measurement/keyframe persistence di result_json existing; memakai kolom soft-delete/acknowledgement/media dari 0004, tanpa migrasi baru |
| 5 | 0005 indeks owner/deleted/created dan owner/deleted/status/completed; query histori/filter dan agregat, tanpa tabel hasil kedua |
| 6 | 0006 coach_member_assignments + assignment_events, feedback_drafts, review_revisions/heads, follow_up_tasks, retry_intents |
| 7 | 0007 recovery_tokens (hash/purpose/email/authVersion/expiry/usedAt), auth_rate_buckets (HMAC identity+window, count, expiry) |

Profile dan security tidak mengubah login identifier lewat PATCH profil.
Transisi authVersion Fase 2: existing users dibackfill version 0. JWT existing
tanpa version diperlakukan version 0 hanya untuk akun yang masih version 0;
token baru menyertakan version saat itu. Password change/reset increment version
dan revoke semua refresh dalam transaksi; access token lama langsung ditolak
oleh pemeriksaan per request. Refresh harus memeriksa versi sebelum menerbitkan
token agar request race tidak menghidupkan ulang sesi. Login/refresh/password
change mengunci user lalu refresh row dalam urutan yang sama; authVersion
refresh legacy dibackfill 0 dan token baru menyimpan versi user yang dikunci.
Kebijakan login,
rememberMe dan refresh deadline tetap sama. Logout existing tetap mencabut
sesi refresh saat ini; global logout hanya akibat password change/reset.

Evaluation existing tetap sumber hasil, bukan dipindah ke JSON baru tanpa FK.
Backfill satu training session per evaluation legacy, status completed dan
timestamps dari hasil existing, uploadedAt/duration null, media unavailable;
ID evaluation dan author note tidak diubah. Metadata versi yang tidak tersimpan
tidak diturunkan dari versi aktif hari ini. Backfill dan unique constraints
diuji pada akun NPM/email, histori/issues/notes dan database kosong. Tidak
mengubah `0001`/`0002`, tidak reset/drop development. Seed metadata modul
idempotent, sumber panduan dicatat; panduan belum tervalidasi boleh kosong/null.

**Penugasan Coach:** tabel current assignment memiliki member_id UNIQUE/PK,
coach_id FK, assignedAt; tidak ada baris berarti belum dibina. History terpisah
append-only mencatat fromCoachId/toCoachId, administrator lokal, reason,
occurredAt UTC. Account role divalidasi service; Member bukan Coach dirinya.
CLI rencana `python -m scripts.assign_coach --member-id ... --coach-id ...`
dan `--unassign`, dengan `--actor` dan `--reason` wajib. Script kini tersedia.
Identitas actor CLI adalah audit operator OS, bukan endpoint admin publik.

Assign/transfer/revoke mengunci baris user Member lalu current assignment
(termasuk bila belum ada assignment), memperbarui assignment + event atomik.
Publish/revisi review juga mengunci baris Member yang sama; cek ulang current
coach di transaksi. Member menjadi gate bersama; CLI lalu mengunci assignment,
publish mengunci actor Coach untuk authVersion lalu session/draft/review.
Tidak mengambil lock job dalam publish. Unique constraint mencegah dua
Coach aktif, FK menjaga relasi; seluruh query overview/roster/detail/media/
legacy Coach memakai current assignment, bukan author review sebagai izin.

Transfer tidak mengubah authorship: Coach baru membaca histori lengkap yang
masih terlihat; Coach lama kehilangan semua akses termasuk revisi tulisannya
sendiri. Published review immutable, revisi menambah revision dan author baru;
snapshot nama/title saat publikasi dipertahankan untuk identitas historis.
Draft lama diarsip privat, tidak ditampilkan kepada Member/Coach baru, dan
tidak muncul lagi bila Coach lama ditugaskan kembali. Member tanpa Coach tetap
mempunyai seluruh alur analisis otomatis; reviewAvailable false. Penugasan
ulang tidak memindahkan owner sesi atau membuat review seolah telah disetujui.

## 5. Environment native, Docker opsional, dan fase

Audit konfigurasi baseline Fase 1 tanpa menampilkan password (snapshot historis):

| Konfigurasi | Aktual saat audit | Target / tindakan kemudian |
| --- | --- | --- |
| DATABASE_URL native | MySQL PyMySQL, 127.0.0.1:13307, user silatsense, DB silatsense | localhost:3306, root, silatsense; verifikasi DB benar/kosong sebelum provisioning terpisah |
| API_PORT | 8001 | Pertahankan port bebas; Compose membaca ini, native uvicorn perlu flag port eksplisit |
| FRONTEND_ORIGIN | http://localhost:3000 | Cocok untuk FE lokal, jangan campur localhost dan 127.0.0.1 pada browser |
| JWT_SECRET | Terisi, tidak dicetak | Pertahankan secret existing; jangan rotasi di Fase 1 |
| Pose model/reference | Model lokal ada, artifact referensi tersedia | Verifikasi inference nyata pada fase validasi |
| MEDIA_ROOT / MEDIA_RETENTION_HOURS | Belum dikonfigurasi/didukung Settings | Tambahkan Fase 3, privat dan 24 jam |
| WORKER_CONCURRENCY / lease/retry/cleanup | Belum dikonfigurasi/didukung | Tambahkan Fase 3, default di Bagian 3 |
| SMTP_HOST / SMTP_PORT / SMTP_FROM | Belum dikonfigurasi/didukung | Fase 7, SMTP test adapter sebelum email nyata |
| FE bridge encryption secret | Belum diimplementasikan | Secret FE terpisah dari JWT_SECRET, Fase 7; jangan NEXT_PUBLIC |

Settings Fase 3 kini mendukung storage/worker/cleanup dengan default pada
`.env.example`; tidak memerlukan secret baru untuk memakai default tersebut.
`.env` aktual dan konfigurasi koneksi development tetap tidak diubah.

Password hanya dibaca lokal, tidak diminta lewat chat. Rakit URL dengan
SQLAlchemy URL.create/URL encoding, bukan JDBC `allowPublicKeyRetrieval`.
Jangan memakai/mengubah `event_sportainment` atau database prototype. Nama
database sama pada MySQL native dan Compose tidak berarti datanya sama.

Setelah konfigurasi native disiapkan pada pekerjaan terpisah, urutan existing:

```powershell
.venv/Scripts/alembic.exe upgrade head
.venv/Scripts/alembic.exe check
.venv/Scripts/python.exe -m scripts.seed
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Perintah di atas **tidak dijalankan pada Fase 1**. CLI worker dan cleanup kini
tersedia pada Fase 3; jalankan sesuai [phase3-api.md](phase3-api.md).
Target operasi native: API, worker, cleanup hidup sebagai proses terpisah;
migrasi sekali sebelum start. Development utama tidak memerlukan Docker.

Compose Fase 3 opsional memakai API+MySQL+worker+cleanup; override DATABASE_URL
ke host `db`, volume `silatsense-be_mysql_data`, dan shared media volume
`silatsense-be_media_data`. DB tidak expose port host. Migration step tunggal
ditunggu API/worker/cleanup; bukan beberapa proses migrasi bersamaan.
Hybrid override opsional dapat expose DB hanya `127.0.0.1:13307`; belum dibuat,
tidak boleh menganggap port itu tersedia sekarang. Hosting belum dipilih;
BE/worker tidak diasumsikan berjalan di Vercel.

### Implementasi Fase 2 — selesai pada kode, belum diterapkan ke development

1. Tambah schema/service profil Member/Coach, whitelist fullName/division/title,
   nullable NPM/email, metadata manusia read-only, dan migrasi additive profil.
2. Implementasikan shared password-change service dan transisi authVersion;
   tes token legacy, refresh race/change password, invalid password dan role.
3. Tambah empat katalog modul, capability dari referensi aktif, panduan bersumber
   atau kosong, upload/record config; jangan membuat data kalibrasi kamera.
4. Tambah router/schema bertipe serta contoh OpenAPI endpoint Fase 2; regression
   auth/prototype, MySQL disposable upgrade kosong/existing sebelum penerapan.

Keempat pekerjaan di atas sudah diimplementasikan dan diuji. Profile rows
dibuat saat PATCH jika diperlukan; baca profil tidak menulis data. Statistik
Member menggunakan evaluasi existing, Coach statistics null sampai ada binaan.
Panduan/level/deskripsi yang belum dikurasi tetap kosong/null; seed tidak
menimpa metadata manusia. Format error baru hanya berlaku endpoint domain,
error/DTO auth prototype tetap kompatibel. Refresh/login/password-change
mengunci User sebelum token sehingga kredensial/sesi lama tidak dapat hidup
kembali pada race. Panduan HTTP dan tes: [phase2-api.md](phase2-api.md).

Fase 3 sesi/storage/worker dan Fase 4 hasil/media sudah tersedia pada kode;
Fase 5 histori/dashboard juga sudah tersedia;
Fase 6 binaan/CLI/draft/review/tugas sudah tersedia dan diuji native. **Fase 7** mengimplementasikan linking email
dengan reauth, verification (termasuk akun email existing), baru password reset,
SMTP test adapter, token hash sekali pakai (link/verify 24 jam, reset 30 menit),
rate limit dan pencabutan sesi, bridge auth FE, integrasi/browser dan operasi.
Email delivery hanya ke alamat yang disahkan alurnya; reset hanya verified.
SMTP provider nyata dan deployment tidak termasuk Fase 1.

Validation berikutnya harus memakai MySQL disposable bernama `_test`, mencakup
claim/recovery/fencing, constraints/backfill, transfer/publish race, refresh
paralel, Range/expiry/delete, aggregate/tanggal dan isolation SSR. Tidak ada
klaim kapasitas puluhan akun/10–15 concurrent users sebelum pengukuran laptop.


## 8. Operasi aktual Fase 7

Recovery menggunakan SMTP sinkron berbatas timeout 10 detik, STARTTLS wajib
kecuali server loopback tes. Adapter in-memory hanya dependency injection tes,
tidak dapat diaktifkan lewat environment production. Token raw hanya melewati
memori/email, tidak disimpan di DB/log. Email dikirim sebelum commit; kegagalan
delivery membatalkan token baru dan mempertahankan token lama. Crash setelah
email terkirim tetapi sebelum commit dapat menghasilkan tautan tidak valid;
request ulang diperlukan. Tidak ada klaim outbox/retry delivery persisten.

Lock User → RecoveryToken sama urutannya dengan refresh/password change;
claim usedAt conditional dan perubahan password/email/authVersion/revocation
berada dalam satu transaksi. Unique email diperiksa DB kembali saat confirm.
Rate bucket insert/upsert + conditional increment atomik dan commit sebelum
reauth/token check agar percobaan gagal tetap tercatat, shared antar proses BE.
Fixed windows UTC; cleanup metadata expired melalui scripts.cleanup_auth.

/health dipertahankan; /health/live tidak mengakses dependency. /health/ready
memeriksa DB revision 0007 dan write probe storage privat, 200/503 tanpa detail
secret/path. Ini bukan bukti SMTP/model/reference/worker hidup. scripts.queue_status
mengeluarkan depth tiap state dan lease kedaluwarsa; heartbeat aktif hanya pada
job yang sedang diklaim. Log job memuat ID/durasi attempt, bukan isi video/hasil.
HTTP structured logger memuat route template/method/status/duration/requestId,
tanpa body/headers/query; jalankan uvicorn --no-access-log untuk menonaktifkan
access logger bawaan yang dapat menulis query string. Semua respons auth no-store;
shape error auth lama tetap sama. Model/metode scoring tidak berubah.

CI lokal source disiapkan untuk lint kritis, format modul baru, tes MySQL
disposable, migrasi/preservasi, OpenAPI check dan container build. CI remote dan
image Docker belum dijalankan pada Fase 7; native tetap default. Dockerfile kini
USER 10001:10001; volume lama perlu izin tulis UID tersebut sebelum dipakai,
tanpa chmod world-writable. Migrasi tetap satu proses sebelum API/worker.
Panduan backup/restore, konfigurasi tertunda dan bukti aktual di
[phase7-api.md](phase7-api.md). Tidak ada provisioning development/deployment.
