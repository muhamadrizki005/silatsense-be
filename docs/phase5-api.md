# Fase 5 — histori dan dashboard Member

> Pembaruan 19 Oktober 2026: endpoint/schema HTTP prototype sudah dihapus.
> Rujukan kompatibilitas lama di catatan fase di bawah bersifat historis.
> Kontrak aktif dan pemetaan pengganti: [route-cleanup.md](route-cleanup.md).

Dokumen ini merekam Fase 5. Binaan, review/tugas dan Coach profile statistics
yang saat itu belum tersedia kini diimplementasikan pada [Fase 6](phase6-api.md).
Head source terkini 0006; nullable/kosong dalam contoh Fase 5 bukan pembatasan
fitur published review Fase 6.

Status 18 Oktober 2026: tersedia pada kode backend. Base path tetap `/api/v1`.
Migrasi additive **0005** hanya menambah dua indeks pada training_sessions;
tidak mengubah isi data, auth, hasil analisis atau rumus skor. Database
development, `.env`, FE dan prototype tidak diubah.

## Endpoint tersedia

| Method | Path setelah `/api/v1` | Respons |
| --- | --- | --- |
| GET | `/member/history` | `{items: HistoryItem[], nextCursor: string|null}` |
| GET | `/member/history/{sessionId}` | SessionDetail: sesi, evaluasi nullable, legacyNotes dan placeholder review/tugas |
| GET | `/member/dashboard` | Statistics, lastSession, latestCoachNote, coach, dominantMovementSlug, weeklyActivity, timezone |

Bearer Member wajib pada setiap request, semua respons/error memakai no-store
dan X-Request-ID. Owner lain/ID invalid/sesi deleted → 404; tanpa token → 401;
role Coach → 403. Endpoint Coach Fase 6 belum tersedia. Error baru mengikuti
`{detail,code,requestId,errors?}`. DTO lengkap di [api-contract.md](api-contract.md),
schema aktif dan Try it out pada `/docs`.

```http
GET {{baseUrl}}/member/history?limit=20&movementSlug=kuda-kuda&processingStatus=completed&reviewStatus=pending&from=2026-10-11T17%3A00%3A00Z&to=2026-10-18T17%3A00%3A00Z
Authorization: Bearer {{accessToken}}

GET {{baseUrl}}/member/history/{{sessionId}}
Authorization: Bearer {{accessToken}}

GET {{baseUrl}}/member/dashboard
Authorization: Bearer {{accessToken}}
```

`baseUrl` mencakup `/api/v1`. Tanggal pada contoh merepresentasikan minggu
12–18 Oktober di Jakarta, dikonversi ke UTC; bukan hasil pengguna aktual.
Gunakan URLSearchParams agar karakter `+` pada offset di-encode dengan benar.
Respons histori akun kosong:

```json
{"items": [], "nextCursor": null}
```

## Pagination dan filter

- limit default 20, minimum 1, maksimum 100; ambil limit+1 untuk menentukan
  nextCursor. Tanpa item berikutnya nextCursor null; tidak memakai offset.
- Urutan menurun `(createdAt,id)` dan posisi keyset memakai keduanya, sehingga
  timestamp sama tidak membuat item terulang. ID tetap string pada wire DTO.
- Cursor bertanda HMAC, versi/scope histori, owner dan seluruh filter terikat.
  Cursor bukan kredensial akses atau enkripsi. Perubahan pengguna/filter,
  signature tidak cocok, cursor kosong/rusak → 422 invalid_cursor.
  Rotasi JWT secret juga menginvalidasi cursor. Ukuran cursor maksimum 4096.
- Sertakan filter yang sama pada halaman selanjutnya; limit boleh berubah.
  Halaman bukan snapshot lintas request: insert lebih baru tidak muncul di
  halaman lanjutan, deleted item hilang, posisi tidak mensyaratkan item cursor
  masih ada. Ulang dari halaman pertama untuk mengambil perubahan terbaru.
- movementSlug: kuda-kuda/pukulan/tangkisan/tendangan, mapping internal
  kuda_kuda. processingStatus: queued/processing/completed/failed.
- reviewStatus: pending/approved/needs_revision. Fase 5 belum memiliki published
  review, sehingga pending sama dengan seluruh hasil yang lolos filter lainnya;
  approved/needs_revision menghasilkan halaman kosong tanpa label manusia palsu.
- `from` inclusive dan `to` exclusive berdasarkan **createdAt sesi**, bukan
  completedAt. Timestamp ISO 8601 UTC dengan Z/+00:00 wajib; date-only,
  timestamp tanpa zona/non-UTC, from>=to → 422 validation_error.
  FE mengonversi rentang tanggal Jakarta ke UTC; BE tidak menebak zona input.
- Filter/query tidak dikenal ditolak, bukan diabaikan diam-diam.

Histori menampilkan queued/processing/failed juga. Skor null memiliki scoreReason
evaluation_pending/analysis_failed/reference_not_ready/insufficient_pose/
insufficient_features sesuai kondisi. review null; reviewStatus pada sesi tetap
pending, reviewAvailable false. Histori mengambil evaluasi/media/nama modul
secara batch, maksimal 100 item, tidak satu query tambahan per sesi.

## Detail sesi dan catatan

SessionDetail memuat session dan evaluation jika completed dan hasil tersedia;
pending/failed mengembalikan evaluation null dengan status/error pada session.
legacyNotes memetakan CoachNote append-only ke `{id,author,text,publishedAt}`;
created_at existing menjadi publishedAt, urutan waktu/ID naik. ID author lama
dipertahankan, nama/title berasal dari profil author existing, bukan diganti
menjadi Coach aktif. Catatan legacy tidak diubah menjadi PublishedReview.

coach/review masih null dan reviewHistory/followUpTasks masih kosong sampai
Fase 6. Hasil legacy yang dibackfill pada 0004 dapat dibaca memakai sessionId,
uploadedAt/media/pose yang tidak tersimpan tetap null/unavailable dengan alasan.
Jalankan seluruh migrasi sebelum membaca legacy melalui endpoint baru.

Expiry atau cleanup fisik media tidak menghapus sesi/evaluasi/catatan/durasi
verified dari histori/dashboard. PlaybackPath mengikuti status media privat
Fase 4. DELETE sesi menghilangkannya dari histori, detail, statistik, lastSession,
dominantMovement dan latestCoachNote; audit hasil/catatan tetap tersimpan.

## Statistik dan minggu berjalan

ActivitySummary dipakai bersama pada profil, katalog dan dashboard:

- completedSessionCount menghitung sesi completed non-deleted; queued/processing/
  failed tidak ikut. Dukungan hasil legacy belum terhubung dipertahankan pada
  ringkasan existing, tetapi migrasi 0004 menghubungkan seluruh hasil lama
  sebelum endpoint histori baru dipakai.
- totalDurationSeconds dan durationSampleCount hanya memakai metadata durasi
  verified pada sesi completed tersebut, termasuk media expired/dihapus fisik.
  Legacy tanpa media/durasi tidak diisi nilai pengganti. Durasi negatif/nonfinite
  diabaikan defensif. Ini durasi video, bukan jam sensor aktif atau lama latihan.
- scoredSessionCount menghitung hasil dengan score non-null; excludedScoreCount
  mencakup completed tanpa score atau tanpa metadata pembanding lengkap.
- similarityGroups terpisah berdasarkan movementSlug, method, analyzerVersion,
  featureVersion, referenceVersion. Hanya skor finite 0–100 dan metadata string
  lengkap yang masuk kelompok. averageScore dibulatkan dua desimal, sampleCount
  disertakan. Skor 0 nyata tetap sampel; null tidak menjadi sampel 0.
  Tidak ada rata-rata global atau skor kelulusan IPSI.
- Akun kosong: count/durasi 0, similarityGroups [], lastSession/latestCoachNote/
  coach/dominantMovementSlug null. FE menampilkan average belum tersedia, bukan
  menyisipkan 0% saat tidak ada kelompok comparable.

LastSession adalah completed terbaru menurut `(completedAt,id)` menurun,
bukan createdAt/upload terbaru. Dominant movement menghitung sesi completed;
tie mengikuti display_order/ID katalog, termasuk kategori yang sedang inactive.
LatestCoachNote adalah catatan pada sesi non-deleted dengan `(created_at,id)`
terbaru, termasuk author lama; catatan sesi deleted tidak ikut.

WeeklyActivity selalu tujuh tanggal Senin–Minggu minggu berjalan Asia/Jakarta,
berdasarkan completedAt, dengan rentang UTC start-inclusive/end-exclusive.
Hari kosong memiliki sessionCount/durationSeconds 0, tanpa prediksi hari depan.
Hitungan sesi dan cakupan durasi mengikuti aturan completed/non-deleted yang
sama. Waktu Minggu 17:00 UTC tepat memasuki Senin 00:00 Jakarta. Timestamp DTO
tetap UTC Z; tanggal bucket YYYY-MM-DD. Implementasi memakai offset tetap
UTC+07:00 untuk Jakarta sehingga tidak memerlukan tzdata OS Windows.

## Migrasi dan operasi

0005 menambah ix_training_owner_history `(user_id,deleted_at,created_at,id)` dan
ix_training_owner_completed `(user_id,deleted_at,processing_status,completed_at,id)`.
Indeks mendukung scope owner/non-deleted, keyset histori dan rentang completed.
Downgrade 0005→0004 hanya menghapus kedua indeks. Tidak ada tabel hasil kedua,
backfill baru, atau reset database. Agregasi membaca batch hasil dan menyimpan
sum/count per kelompok, tanpa menumpuk daftar seluruh skor di memori.

Database development belum dimigrasi dan alembic check development ditunda
karena koneksi native masih belum sesuai target localhost:3306/silatsense yang
disetujui. Setelah konfigurasi/target tepat disiapkan, jalankan pada terminal
native bersih dari URL override tes:

```powershell
.venv/Scripts/alembic.exe upgrade head
.venv/Scripts/alembic.exe check
```

Restart API menggunakan kode terbaru. Worker/cleanup dan transport auth tetap
seperti Fase 3–4. Compose opsional memerlukan rebuild, menggunakan DB/volume
terpisah; Compose development tidak dijalankan selama tugas ini.

## Bukti pengujian

Baseline sebelum perubahan: **128 passed, 11 skipped, 9 warnings in 32.68s**,
`python -m pytest -q --basetemp=.cache/phase5-baseline-01`.
Suite final SQLite Fase 5: **158 passed, 11 skipped, 14 warnings in 41.34s**,
`python -m pytest -q --basetemp=.cache/phase5-sqlite-final`.
Database API SQLite memory, migrasi file sementara, media/tmp di `.cache`.
Sebelas skip khusus race/row-lock MySQL, bukan endpoint Fase 5 yang gagal.

Suite lengkap Linux/MySQL disposable: **169 passed, 14 warnings in 361.55s**.
Command `docker run --rm --network silatsense-phase5-test-net` menggunakan image
silatsense-be-phase5-test dan `python -m pytest -q`, TEST_DATABASE_URL ke schema
silatsense_phase5_test serta MIGRATION_TEST_DATABASE_URL ke schema **terpisah**
silatsense_phase5_migration_test, host container silatsense-phase5-mysql-test:3306;
artifact/model dipasang read-only. Host port tes 127.0.0.1:13308, bukan MySQL
development. Fixture create/drop hanya schema disposable `_test`.

Setelah suite tersebut, validasi cursor terlalu panjang diseragamkan ke
invalid_cursor dan tes timestamp numerik ditambahkan menggantikan satu kasus
validasi generik. Suite final SQLite di atas mencakup perubahan ini; regresi
MySQL modul histori dengan dua file terbaru dipasang read-only lulus:
**29 passed, 1 warning in 54.15s**, `python -m pytest -q tests/test_history_dashboard.py`
pada image/network/schema tes yang sama. Ini memverifikasi kode final, termasuk
invalid_cursor untuk cursor terlalu panjang dan validasi timestamp numerik.

Tes baru: cursor timestamp sama/deleted/new insert/filter/scope/signature,
limit/default, UTC validation, range inclusive/exclusive, empat processing state,
owner/Coach/401/404, null/zero/legacy, kelompok seluruh lima dimensi, sampleCount,
durasi/expired/deleted, lastSession/tie katalog/latest author note, Senin Jakarta,
tujuh bucket dan jumlah query batch. Migrasi 0004→0005→0004→0005 mempertahankan
ID, hasil JSON, acknowledged_at dan password hash; upgrade existing/kosong serta
alembic check juga diuji.

Smoke HTTP Linux/MySQL pada schema terpisah berhasil: akun kosong → dua upload
202 → worker CLI dengan model MediaPipe lokal → histori/detail/dashboard 200,
pagination/filter/cursor mismatch 422, durasi dan minggu benar, score null
tanpa kelompok palsu, author catatan legacy, DELETE menutup detail/aggregate,
expiry+cleanup media tetap menyisakan histori/durasi dan audit; docs/OpenAPI 200.
Video sintetis kosong, bukan pengujian gerakan manusia. Startup API tes juga
menjalankan upgrade head dan alembic check pada schema smoke disposable.

Image silatsense-be-phase5-test berhasil dibangun; docker compose config --quiet,
AST Python dan pemeriksaan fence/JSON/link lokal Markdown lulus. Hash 234 file
terlindungi masih cocok dengan snapshot sebelumnya: `.env`, migrasi 0001–0003,
FE dan sumber rencana prototype. Migrasi 0004 juga tidak diedit.

Container API/MySQL, volume media dan network khusus Fase 5 sudah dibersihkan.
Tag image tes tetap dapat menjadi cache build lokal; Docker Desktop tidak
dihentikan dan layanan/volume development tidak diubah.

Warning deprecation httpx/TestClient dan Alembic path_separator tetap ada.
Belum ada benchmark 10–15 pengguna, validasi ilmiah skor atau integrasi browser FE.

## File yang berubah

Ditambahkan: `app/api/history.py`, `app/schemas/history.py`, `app/core/cursors.py`,
`app/repositories/history.py`, `app/services/history.py`,
`alembic/versions/0005_history_dashboard_indexes.py`, `tests/test_history_dashboard.py`,
`docs/phase5-api.md`.

Diperbarui: `app/main.py`, `app/models/entities.py`, `app/repositories/profiles.py`,
`app/services/sessions.py`, `app/services/results.py`, `tests/test_migrations.py`,
README dan `docs/api-contract.md`, `docs/architecture.md`, `docs/fe-integration.md`,
`docs/phase4-api.md`. Total 19 file deliverable. Script dan media tes sementara
di `.cache` diabaikan Git. Helper serialisasi sesi/evaluasi dipakai bersama
agar endpoint Fase 3–4 tetap memiliki shape yang sama.

## Delta FE dan pekerjaan berikutnya

FE tidak diubah. Ganti dummy fetcher histori/dashboard dengan endpoint di atas,
pakai sessionId untuk detail, cursor+filter yang sama untuk load more, UTC untuk
filter dan tanggal Jakarta untuk chart. Tampilkan status pending/failed dan media
expired; render measurement/evaluasi nullable dan catatan legacy terpisah.
Pilih kelompok statistik comparable dan tampilkan sampleCount, jangan membuat
global average, target/label IPSI atau repetisi dummy. Private fetch memakai
Bearer per request/no-store; bridge auth FE tetap Fase 7.

Fase 6 berikutnya: satu Coach aktif per Member, CLI assign/transfer/revoke dengan
histori transaksional, pembatasan seluruh endpoint Coach lama/baru, roster dan
overview, draft privat, published review/revisi immutable dengan optimistic
concurrency, serta tindak lanjut. Fase 7 tetap linking/verifikasi email, password
reset verified-email dan integrasi bridge FE. Belum ada klaim transfer scope
atau review manusia sudah aktif pada Fase 5.
