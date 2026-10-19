# Fase 7 — recovery email, bridge auth dan operasi

> Pembaruan 19 Oktober 2026: endpoint/schema HTTP prototype sudah dihapus.
> Rujukan kompatibilitas lama di catatan fase di bawah bersifat historis.
> Kontrak aktif dan pemetaan pengganti: [route-cleanup.md](route-cleanup.md).

**Pembaruan native 18 Oktober 2026:** koneksi pengguna ke localhost:3306/silatsense
berhasil, schema yang belum ada dibuat, upgrade 0007 dan alembic check lulus.
Empat katalog terisi, tanpa akun/sesi/profil referensi dummy. API readiness,
Swagger/OpenAPI HTTP 200; worker antrean kosong berhasil. API sementara ditutup,
database development disimpan. Catatan Fase 7 di bawah merekam kondisi sebelum
provisioning ini; SMTP masih disabled. Tidak ada secret yang didokumentasikan.

Status 18 Oktober 2026: kode backend head **0007** dan integrasi **auth/keamanan**
FE tersedia. Database development belum dimigrasi; `.env` dan prototype tidak
diubah. Native adalah default; tidak menyalakan Docker selama fase ini.
Integrasi data latihan FE masih terpisah, bukan seluruh frontend sudah selesai.

## Endpoint aktual

Prefix `/api/v1`; auth existing mempertahankan DTO/cookie/deadline/rotasi.

| Endpoint POST | Otorisasi dan body | Hasil |
| --- | --- | --- |
| `/auth/email-link/request` | Bearer + `{email,currentPassword}` | 202 generik; email belum berubah |
| `/auth/email-link/confirm` | Bearer akun pemohon + `{token}` | 204; email verified, semua sesi dicabut |
| `/auth/email-verification/request` | Bearer + `{currentPassword}` | 202 generik; email existing |
| `/auth/email-verification/confirm` | Bearer akun pemohon + `{token}` | 204; verified, sesi tetap |
| `/auth/password-reset/request` | Publik `{identifier}` NPM/email | 202 generik; hanya verified email |
| `/auth/password-reset/confirm` | Publik `{token,newPassword}` | 204; semua sesi dicabut, login ulang |

Body sukses request selalu
`{"detail":"Jika memenuhi syarat, instruksi akan dikirim."}`.
Error recovery baru `{detail,code,requestId}` + X-Request-ID, no-store. Salah
password saat reauth: 401 invalid_current_password; token salah/purpose berbeda/
akun berbeda/expired/used/superseded: 422 invalid_or_expired_token. Tidak ada
email linked saat verify request: 422 email_not_linked. Email conflict saat confirm
ditolak atomik dengan token-invalid generik; tidak memindahkan akun lain.
Password sama ditolak 422 password_unchanged. Input extra dilarang, password
8–128 karakter, email dinormalisasi lowercase, token 32–128 URL-safe karakter.
Validasi error baru tidak mengembalikan input/password/token.

Token raw acak 48 byte; DB hanya SHA256 + user/purpose/email/authVersion/deadline/
usedAt. Link/verify 24 jam, reset 30 menit, `expiresAt <= now` langsung ditolak.
Request baru mengganti token purpose sama setelah delivery berhasil; kegagalan
SMTP rollback sehingga token sebelumnya tetap valid. Confirm single-use dan
password/email/authVersion/revocation satu transaksi, lock User sebelum token.
Link/reset mencabut seluruh refresh/access termasuk sesi legacy lewat authVersion;
password change Fase 2 juga membuat recovery token lama tidak valid.
NPM tetap disimpan dan dapat dipakai login setelah linking. Legacy email tidak
dianggap verified otomatis. Akun tanpa Coach tetap mengikuti alur yang sama.

## Rate limit dan email

Counter database memakai HMAC identity+fixed-window UTC, tanpa identity/token/IP
mentah dalam key. Upsert dan increment conditional atomik, termasuk failed attempts.

| Operasi | Limit default |
| --- | --- |
| Login existing | 10/15 menit per identifier (`AUTH_ATTEMPTS_PER_15_MINUTES`) |
| Auth login/refresh POST | 120/15 menit per IP (`AUTH_IP_REQUESTS_PER_15_MINUTES`) |
| Registrasi | 20/jam per IP (`SIGNUP_IP_REQUESTS_PER_HOUR`) |
| Recovery request, lintas purpose | 5/jam per identity, 20/jam per IP |
| Recovery confirm | 10/15 menit per IP |

Logout tidak diblokir throttle. Auth existing tetap error `{detail}` termasuk
429; response/cookie/rememberMe tidak berubah. Upload tetap memakai body limit,
kuota storage dan maksimum sesi pending/reservation Fase 3, bukan angka dummy
request rate baru. IP dari koneksi langsung; FE proxy satu laptop berbagi IP,
per-identifier tetap berlaku. Jangan mempercayai X-Forwarded-For client tanpa
konfigurasi trusted proxy tersendiri. Fixed-window memungkinkan burst di batas
window; ini bukan adaptive anti-bot. Jalankan `python -m scripts.cleanup_auth`
berkala untuk metadata expired, misalnya tiap hari saat operasi lokal.

MAIL_ADAPTER default **disabled**. Request email menghasilkan 503 mail_unavailable
secara seragam sampai SMTP diaktifkan. Konfigurasi tersedia di `.env.example`:
MAIL_ADAPTER=smtp, SMTP_HOST/PORT/FROM, SMTP_STARTTLS, SMTP_TIMEOUT_SECONDS;
SMTP_USERNAME/PASSWORD di environment privat bila provider membutuhkan.
STARTTLS memvalidasi sertifikat; plain SMTP hanya diizinkan host loopback tes.
Tidak ada email nyata terkirim selama pengujian. MemoryMailAdapter hanya melalui
dependency override tes, bukan mode environment. SMTP loopback tes juga diuji
dengan koneksi socket nyata. Provider nyata belum dikonfigurasi/diverifikasi.

Link email memakai fragment `/confirm-email#link:<token>` atau `#verify:<token>`;
reset `/reset-password#reset:<token>`, tidak masuk request URL/access log server.
UI menyalin token ke form dan membersihkan fragment, konfirmasi harus dikirim
eksplisit. Tidak ada password di email. Public reset 202 tetap sama untuk akun
tidak ada/NPM-only/nonverified/delivery gagal. Timing SMTP belum diseragamkan;
jangan mengklaim resistensi timing-enumeration penuh. SMTP sinkron maksimal
10 detik default, tanpa outbox; crash setelah send sebelum commit dapat membuat
email tidak valid dan perlu request ulang. Tidak ada retry delivery otomatis.

## Bridge FE dan batas integrasi

FE branch lokal `experiment/backend-phase7-auth`, dibuat dari origin/development.
Tidak ada deployment atau PR dipublikasikan. Panduan di
`silatsense-fe/docs/backend-phase7-auth.md`. Gunakan API_BASE_URL server-only
misalnya http://localhost:8001/api/v1, FRONTEND_ORIGIN sama dengan BE,
SESSION_ENCRYPTION_KEY 32 byte hex tersendiri, FE_PROCESS_COUNT=1. `.env.local`
aktual tidak dibuat/diubah. Jangan mengirim secret lewat chat atau Git.

Cookie silatsense_session AES-256-GCM, HttpOnly, Strict, host-only `/`, Secure
untuk HTTPS, payload maksimum 3800 karakter. Browser tidak menerima Bearer/refresh
di props/localStorage. Upstream getSetCookie menangani Expires comma; FE hanya
forward cookie refresh_token ke BE saat refresh/logout. Deadline awal dipertahankan;
tanpa rememberMe cookie session-only maksimal 24 jam, persistent maksimal 7 hari.
Request privat no-store/Bearer per request. Login/logout hard navigation dan
QueryClient.clear memutus cache antaruser; role guard diverifikasi GET auth/session
ke BE, bukan sekadar role cookie. Semua action memvalidasi Origin dan input.

RSC membaca cookie; action menulis cookie. Access expired/BE 401 menampilkan
boundary tanpa data privat, action rotate sekali lalu GET auth/session memvalidasi
hasil sebelum render data diulang. Single-flight per bridgeSessionId+hash refresh,
hasil winner 30 detik, maksimum 1000 entry/tombstone per proses. Cookie stale
memakai hasil winner tanpa mengirim token lama lagi. Registry bukan Bearer global.
Logout menandai tombstone, menunggu refresh, revoke winner, menghapus cookie;
client mengabaikan navigasi refresh setelah intent logout. Network error tidak
dianggap revocation; retry logout dengan winner tersedia dalam jendela 30 detik.
Mutasi dikirim satu kali, tanpa replay buta. Satu proses FE saja; multi-process
perlu koordinasi bersama. Crash setelah rotasi BE sebelum penyimpanan hasil atau
cookie stale setelah 30 detik dapat memerlukan login ulang. Logout existing hanya
revoke refresh; access yang disalin sebelumnya tetap berlaku hingga 900 detik,
kecuali password change/link/reset yang memakai authVersion.

Aktual FE: login/sign-up/logout, guard Member/Coach, halaman keamanan/profil email
asli, link/verify/password change, forgot/reset/confirm email. Dashboard/katalog/
upload/status/evaluasi/media/history/profil biodata/Coach tetap demo/stub dan diberi
banner. Streaming upload/media adapter belum dibuat. Delta selanjutnya: sessionId,
polling, pagination, nullable/empty/media expired, Coach optional, author historis,
conflict/idempotensi review, penghapusan semua metrik/label dummy dan IPSI pada
layar latihan. Kamera tetap browser-only. Jangan memakai demo sebagai hasil akun.

## Operasi dan kontrak

- `/health` tetap kompatibel; `/health/live` liveness, `/health/ready` DB revision
  0007 + storage write probe, 200 atau 503. Tidak memeriksa keberadaan worker idle,
  model/referensi atau SMTP. Tidak mengungkap URL DB/secret/path.
- `python -m scripts.queue_status`: depth tiap state dan expiredLeases tanpa PII.
  Heartbeat job aktif tetap mekanisme Fase 3, bukan heartbeat service baru.
- HTTP log JSON route template/method/status/durationMs/requestId, job log ID/
  durasi attempt. Jalankan uvicorn dengan **--no-access-log** agar logger bawaan
  tidak menulis query string. Tidak mengaktifkan SQL echo/body/header logging.
- [OpenAPI snapshot](openapi.json), [collection HTTP](examples.http).
  `python -m scripts.export_openapi --check` menjaga kontrak sama dengan kode.
  Endpoint prototype tidak dihapus: konsumen belum dipastikan pindah. Gunakan
  endpoint camelCase baru; DTO/error legacy tetap kompatibel.
- `.github/workflows/backend.yml` menyiapkan lint kritis, format modul Fase 7,
  MySQL disposable/migration/contract checks dan container build. Dependencies
  Python dipin; Ruff pengembangan dipin terpisah requirements-dev.txt. Dockerfile
  memakai UID/GID 10001. CI remote dan container build belum dijalankan di sesi
  ini, sesuai native-first. Izin volume existing harus dicek sebelum Docker dipakai.
- Migrasi sekali oleh operator sebelum API/worker/cleanup, tanpa replica racing
  migration. Development belum di-upgrade/check karena konfigurasi lokal belum
  sesuai target localhost:3306/root/silatsense; password root existing tidak diketahui
  dan tidak direset. Jangan memakai event_sportainment/prototype.

Backup: hentikan penulisan API/worker/cleanup, dump schema MySQL dengan
single-transaction/no-tablespaces, salin storage privat pada jeda penulisan sama,
catat checksum dan revision, simpan bundle di lokasi privat dengan perlindungan
akses/enkripsi. Jangan commit dump/media/config credential. Restore ke schema
baru yang diverifikasi kosong dan direktori media baru, periksa row/checksum/
revision, jalankan alembic check dan smoke sebelum mengganti konfigurasi aplikasi.
Jangan restore ke schema development/prototype tanpa rencana pemulihan eksplisit.
Drill native Fase 7 memakai schema *_restore_test baru: **24 tabel seluruh row
dan checksum identik**, byte media opaque tersalin identik; target/bundle tes
dihapus setelahnya. Ini bukan uji backup terenkripsi/provider produksi atau RPO/RTO;
file opaque membuktikan backup bytes, bukan decoder video.

## Bukti pengujian aktual

Semua perintah backend memakai `.venv/Scripts/python.exe` dari root; tidak memakai
Python global yang belum memiliki pytest. Baseline BE sebelum perubahan:
`python -m pytest -q --basetemp=.cache/phase7-baseline --tb=short` → **185 passed,
15 skipped, 19 warnings, 74.94s**. Skip khusus MySQL. Baseline FE development:
`pnpm test` → **238 passed**.

SQLite regresi sebelum tambahan batas mikrodetik: `python -m pytest -q --basetemp=.cache/phase7-sqlite-final
--tb=short` → **202 passed, 18 skipped, 19 warnings, 53.33s**. Termasuk auth
compatible, recovery, SMTP, readiness, structured log, migrasi/preservasi dan
seluruh domain lama. Response-model recovery final diuji tambahan **13 passed**
setelah deklarasi schema OpenAPI diselesaikan, shape runtime tetap sama.

MySQL native 8.0.46 terpisah: mysqld --no-defaults, bind 127.0.0.1:13308,
datadir `.cache/phase7-mysql-native`, kredensial disposable instance ini saja.
TEST_DATABASE_URL menuju **silatsense_phase7_api_test**, MIGRATION_TEST_DATABASE_URL
menuju **silatsense_phase7_migration_test**; smoke schema terpisah
**silatsense_phase7_smoke_test**. Test fixture menolak schema tanpa akhiran _test
dan migrasi harus mulai kosong. Tidak memakai service MySQL80 pengguna atau
DATABASE_URL aktual. Suite awal **217 passed, 19 warnings, 451.77s**; suite final
setelah observability/throttle: `python -m pytest -q
--basetemp=.cache/phase7-mysql-final --tb=short` → **220 passed, 19 warnings,
457.21s**. Model respons 202 dan aktivasi handler log final diperiksa terpisah
setelah suite penuh; body/otorisasi tetap sama.

Race MySQL: satu pemenang reset, reset vs refresh mencabut semua sesi lama,
counter parallel tepat 5 sukses/3 throttle; seluruh race lease/job/idempotensi/
assignment/review lama ikut suite. Upgrade/downgrade/re-upgrade dan alembic check
pada schema tes menjaga akun/token/history existing, tanpa auto-verifikasi email.
Smoke HTTP native: auth→upload video sintetis→worker nyata→Range→draft/publish/
revision→transfer/revoke→histori/tugas/retry Member **lulus**. Skor null ketika
referensi tidak siap, bukan validasi ilmiah silat manusia atau benchmark 10–15 user.

FE final **249 passed**, `pnpm build`, `pnpm typecheck`, `pnpm lint` lulus tanpa
warning lint. Tes bridge behavioral mencakup tamper/expiry, winner parallel/stale,
logout race/retry, network vs rejected, cookie parsing/deadline dan Bearer isolasi.
Browser Next start + FastAPI + MySQL + SMTP loopback: login Coach, role redirect,
request verify, confirm, profil verified pada read berikutnya, logout dan penolakan
halaman privat lulus. Confirm UI memakai token fixture deterministik di schema tes;
SMTP real socket diuji terpisah. Overflow security 1239<=1254 desktop dan 390<=390
mobile. Refresh dua tab/menunggu 15 menit belum diuji browser; coordinator dan
API race diuji deterministik. Tidak mengklaim semua layar/upload FE terintegrasi.

Warning tersisa deprecation httpx/TestClient dan Alembic path_separator. Belum
ada benchmark laptop, audit deliverability SMTP nyata, multi-process FE, remote CI/
container runtime atau deployment. Batas analyzer/metode/dataset tetap sama.

## File yang berubah

Backend baru: migration 0007; app/api/recovery.py dan health.py;
app/schemas/recovery.py; app/services/recovery.py dan mail.py;
app/core/observability.py; scripts/cleanup_auth.py, queue_status.py,
export_openapi.py; tests/test_recovery.py, test_smtp.py, test_mysql_recovery.py,
test_operations.py; requirements-dev.txt; workflow CI; dokumen ini,
docs/openapi.json dan examples.http.

Backend diperbarui: app/main.py, core/config.py, core/errors.py, core/security.py,
models/entities.py, services/auth.py, services/worker.py, api/routes.py;
Dockerfile, docker-compose.yml, .env.example, README, docs/api-contract.md, architecture.md,
fe-integration.md dan auth-api.md. Migrasi 0001–0006 tidak ditulis ulang.

FE baru: lib/api-client.ts, lib/auth/{session-codec,session,coordinator}.ts;
features/auth/actions/{session-actions,recovery-action}.ts;
components/{session-controls,recovery-form}.tsx, pages/{session-gate,recovery-page}.tsx,
schemas/recovery.ts; empat route keamanan akun; tests/server-only.ts,
tests/unit/auth/bridge.test.ts; docs/backend-phase7-auth.md.
FE diperbarui: dua layout role, form/page/schema/types auth, profile editor/logout/security/
page, tes karakterisasi auth/profile, vitest.config.ts, .env.example dan README.
Tidak mengubah prototype, model/dataset, rumus skor, .env atau DB development.
Artefak sementara `.cache` diabaikan Git. Linear/PR tidak ditulis karena connector
linear-personal/skill linear-tracking tidak tersedia; roadmap UI FE terpisah.

Compose memakai readiness DB/storage dan mount artifact read-only; runtime Docker
belum dijalankan. Git FE belum memiliki user.name/user.email, sehingga percobaan
commit tidak dibuat; staging sudah dilepas, perubahan tetap pada branch eksperimen.

Final tambahan operasi HTTP native (kode terbaru): readiness/liveness, UUID header
cocok JSON log, redaction body/query/credential dan recovery disabled 503 lulus.


Pemeriksaan akhir menemukan pembulatan MySQL DATETIME tanpa fsp yang dapat
memperpanjang deadline pecahan detik. Model dan migrasi baru 0007 kini memakai
DATETIME(6) untuk expiry/usedAt recovery dan expiry rate bucket; migrasi lama
0001–0006 tidak diubah, development belum menerapkan 0007. Setelah perbaikan:
native recovery/operations/race/migration **22 passed, 19 warnings, 56.98s**
(`--basetemp=.cache/phase7-mysql-precision-final`), ditambah regresi deterministik
**2 passed in 4.10s** (timestamp .900123 tersimpan persis; satu mikrodetik sebelum
deadline diterima, tepat deadline ditolak). Suite SQLite final terbaru
`--basetemp=.cache/phase7-sqlite-final-deadline` **204 passed, 18 skipped,
19 warnings, 46.20s**. Suite MySQL penuh 220 di atas dijalankan sebelum perbaikan
presisi; seluruh area yang berubah diuji ulang melalui 24 tes native tambahan.


Smoke final setelah perbaikan presisi memakai schema fresh
silatsense_phase7_smoke_final_test: upgrade head + alembic check, alur API lengkap,
dan backup/restore ulang **lulus**. Sesudah semua uji, API/FE/SMTP fixture berhenti,
MySQL sementara dimatikan setelah @@datadir diverifikasi, seluruh schema/datadir
tes dan bundle backup sementara dihapus. Port 13308/3101/18001–18004 tidak lagi
listen; service MySQL80 pengguna tetap Running. Docker tidak dijalankan.
File deliverable aktual: **35 backend + 36 frontend**; staging FE kosong dan
perubahan belum di-commit karena identitas Git lokal belum tersedia.

