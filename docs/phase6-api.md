# Fase 6 — binaan, review dan tindak lanjut

> Pembaruan 19 Oktober 2026: endpoint/schema HTTP prototype sudah dihapus.
> Rujukan kompatibilitas lama di catatan fase di bawah bersifat historis.
> Kontrak aktif dan pemetaan pengganti: [route-cleanup.md](route-cleanup.md).

Status 18 Oktober 2026: tersedia pada kode backend dengan migrasi additive
**0006**. Seluruh pengujian dan smoke fase ini berjalan **native, tanpa Docker**.
Database development, `.env`, FE, prototype, migrasi 0001–0005 dan rumus skor
tidak diubah. Auth/cookie/JWT existing tetap kompatibel.

## Penugasan administrator

Satu Member maksimal satu Coach aktif, ditegakkan PK/unique member_id pada
coach_member_assignments. Satu Coach dapat memiliki banyak Member. Penugasan
bukan endpoint publik/self-assignment, melainkan CLI operator lokal:

```powershell
.venv/Scripts/python.exe -m scripts.assign_coach --member-id 12 --coach-id 3 --actor "admin-laptop" --reason "Penugasan awal"
.venv/Scripts/python.exe -m scripts.assign_coach --member-id 12 --coach-id 5 --actor "admin-laptop" --reason "Pergantian pembina"
.venv/Scripts/python.exe -m scripts.assign_coach --member-id 12 --unassign --actor "admin-laptop" --reason "Pembinaan berakhir"
```

ID di atas hanya ilustrasi. CLI memakai DATABASE_URL aktif; verifikasi target
dan migrasi sebelum menggunakannya pada data nyata. actor adalah label operator
OS untuk audit, bukan identitas admin HTTP. actor/reason wajib, trim, maksimum
120/2000 karakter. Role Member/Coach divalidasi; Coach tidak dapat menugaskan
dirinya melalui API. Assignment, transfer atau revoke berjalan dalam satu
transaksi dan mencatat AssignmentEvent append-only. Menetapkan Coach yang sama
atau revoke Member yang sudah tanpa Coach adalah no-op tanpa event palsu.

Member tanpa Coach tetap dapat upload, menerima analisis otomatis, membaca hasil,
membuat retry-intent dan mengunggah ulang dengan retryOf. Profil coach null;
reviewAvailable false. Tanpa published review status pending; review yang sudah
published tetap terlihat oleh Member setelah revoke dan mempertahankan keputusan
historisnya. reviewAvailable true hanya untuk sesi completed dengan Coach aktif.

Setelah transfer, Coach baru membaca seluruh histori Member yang belum deleted,
termasuk author review/note lama dan tugas lama. Coach lama kehilangan akses
detail, video, pose, draft dan revisi, termasuk review yang pernah ditulisnya.
Idempotency replay tidak melewati pengecekan akses. Draft terikat event penugasan;
draft lama menjadi arsip privat, tidak diwariskan dan tidak muncul kembali
meskipun Coach yang sama ditugaskan lagi.

## API tersedia

Base path `/api/v1`, Bearer sesuai role, ID string/UTC Z, no-store. Endpoint baru
memakai error `{detail,code,requestId,errors?}`; endpoint prototype mempertahankan
shape DTO/error dan offset/limit lama, sekarang dibatasi binaan. Unknown,
non-binaan, deleted atau akses Coach lama → 404. Member pada endpoint Coach →
403; tanpa sesi → 401. Mutasi baru memeriksa Origin jika dikirim. CORS mendukung PUT.

| Method | Path setelah `/api/v1` | Hasil |
| --- | --- | --- |
| GET | `/coach/overview` | memberCount, reviewQueueCount, statistics, recentSessions max 5, topIssues max 6 |
| GET | `/coach/roster` | `{items,nextCursor}`; limit default 20/max 100, q trim/max 120 |
| GET | `/coach/roster/{memberId}` | profile, statistics, latestSession nullable |
| GET | `/coach/roster/{memberId}/sessions` | Pagination/filter histori dalam binaan |
| GET | `/coach/sessions/{sessionId}` | SessionDetail + feedbackDraft pribadi nullable |
| GET | `/coach/sessions/{sessionId}/pose` | PoseData nullable dengan alasan, kebijakan Fase 4 |
| GET | `/coach/sessions/{sessionId}/video` | Privat 200/206, Range/expiry sama dengan Member |
| PUT | `/coach/sessions/{sessionId}/feedback-draft` | DraftInput → DraftOut, optimistic version |
| POST | `/coach/sessions/{sessionId}/reviews` | PublishInput + Idempotency-Key → PublishedReview, 201 |
| POST | `/member/sessions/{sessionId}/follow-ups` | `{intent:"retry"}` + Idempotency-Key → RetryIntent, 201 |
| PATCH | `/member/follow-up-tasks/{taskId}` | `{status:"completed"|"dismissed"}` → FollowUpTask |

Rincian DTO di [api-contract.md](api-contract.md) dan Swagger `/docs`.
Member profile sekarang berisi Coach aktif; statistik profil Coach dan overview
hanya menghitung binaan aktif, termasuk akun kosong dengan counts 0/groups [].
Tidak ada agregat global lintas Coach atau rata-rata lintas versi/kategori.

Roster mencari substring literal nama/NPM/email dalam binaan; %/_ tidak menjadi
wildcard dari client. Urutan `(createdAt,id)` Member menurun; cursor bertanda,
terikat Coach, scope dan q. Histori Coach memakai filter Fase 5 dan scope cursor
Coach+Member, sehingga cursor Member/Coach lain tidak dapat dipakai silang.
Limit boleh berubah, filter harus sama; mismatch/rusak → 422 invalid_cursor.
Setiap request memeriksa penugasan saat ini. Endpoint legacy `/coach/members`,
detail/histori Member, `/evaluations/{id}` untuk Coach, serta POST catatan legacy
semuanya memakai scope yang sama; list legacy tetap array, tidak berubah envelope.

Review queue menghitung completed non-deleted tanpa published review; analisis
reference_not_ready tetap boleh ditinjau manusia. Top issues menghitung sesi
berbeda per feature, tie nama feature ascending, maksimal enam dengan jumlah
eksplisit. Recent sessions menampilkan lima sesi terbaru binaan menurut createdAt/ID.

## Draft, publikasi dan revisi

```http
PUT {{baseUrl}}/coach/sessions/{{sessionId}}/feedback-draft
Authorization: Bearer {{coachAccessToken}}
Content-Type: application/json

{
  "expectedVersion": 0,
  "decision": "needs_revision",
  "note": "Ulangi latihan sesuai arahan pelatih.",
  "bodyAssessments": [
    {"bodyPart": "left_knee", "status": "needs_revision", "note": "Periksa posisi lutut."}
  ],
  "tasks": [{"instruction": "Ulangi latihan lalu unggah sesi baru."}]
}
```

Contoh adalah input manusia ilustratif, bukan keluaran scoring atau koreksi
IPSI. Draft pertama expectedVersion 0 → version 1; update berikutnya harus
memakai versi sekarang. note trim/max 5000/null; note kosong menjadi null.
bodyAssessments maksimum 33, bodyPart unik setelah trim, panjang 1–80;
status not_assessed/needs_revision/approved, note bagian max 2000/null.
tasks maksimum 20, instruction trim 1–2000. Author dari auth, tidak dapat
diisi client. Draft hanya disajikan kepada pembuat yang masih berwenang;
Member tidak menerima draft lewat histori/detail.

```http
POST {{baseUrl}}/coach/sessions/{{sessionId}}/reviews
Authorization: Bearer {{coachAccessToken}}
Idempotency-Key: {{uniquePublishKey}}
Content-Type: application/json

{"expectedRevision": 0, "expectedDraftVersion": 1}
```

Publish memerlukan sesi/evaluasi completed, decision non-null, versi draft dan
revision terbaru cocok (0 bila belum ada). Konflik → 409 version_conflict;
keputusan kosong → 422 decision_required; pending/failed → 409. Snapshot review,
author name/title, body assessments, task IDs, review head, penghapusan draft
dan rekaman idempotensi commit atomik. Kegagalan tidak meninggalkan tugas/review
parsial. Note review tidak diduplikasi ke coach_notes legacy.

Published review immutable setelah commit. Revisi dibuat dengan draft baru
(expectedVersion 0 setelah draft sebelumnya published), lalu publish memakai
expectedRevision terbaru. Revision bertambah, supersedesReviewId menunjuk
review lama, author baru tercatat tanpa menimpa author historis. ORM menolak
update/delete ReviewRevision dan AssignmentEvent; admin SQL tetap merupakan
privilege terpercaya, bukan API pengguna. Head terbaru mutable, isi revisi lama
tidak diedit. Nilai analyzer/score tidak berubah akibat keputusan manusia.

Idempotency-Key 1–128 karakter nonblank, scope actor+operation+session, payload
ternormalisasi sama mengembalikan body/status penerimaan yang sama; payload
berbeda → 409 idempotency_conflict. Replay tetap membutuhkan akses current
assignment/non-deleted. Rekaman tidak dipangkas otomatis.

Member history/detail dan sesi sekarang memuat latest review/status, seluruh
reviewHistory, followUpTasks dan Coach aktif. LegacyNotes tetap sumber terpisah.
Filter reviewStatus memakai published head, bukan draft atau catatan legacy.
Dashboard latestCoachNote memilih note published review/legacy terbaru; note
review memakai ID `review:<id>` untuk membedakannya dari ID catatan legacy.
Review tanpa note tidak menciptakan note dummy. Setelah revoke, review lama
tetap terlihat Member dengan author historis, sementara Coach aktif null.

## Tugas dan latihan ulang

Tugas menyimpan instruksi/author/review asal. Revisi review tidak menghapus atau
menutup tugas lama otomatis. Hanya Member pemilik sesi yang dapat menandai
completed/dismissed; instruksi dan author tidak writable. Mengirim status yang
sama tidak mengubah updatedAt, dan Member boleh mengoreksi antara kedua status
tersebut. Status adalah pernyataan Member, bukan verifikasi kualitas gerakan AI.
Deleted session menutup akses tugas; data audit tetap tersimpan.

RetryIntent hanya untuk sesi terminal completed/failed, termasuk tanpa Coach;
queued/processing → 409 session_not_terminal. Ia bukan tugas Coach, hasil
evaluasi, upload atau perubahan keputusan. RetryIntent/replay tetap memerlukan
owner/non-deleted. Upload berikutnya membawa retryOf=sourceSessionId, memakai
validasi owner/kategori yang sudah ada, dan menghasilkan sesi/hasil baru.

## Transaksi, stream dan migrasi

Member User menjadi gerbang lock bersama saat assign/transfer/revoke, publish,
perubahan draft, baca detail Coach dan follow-up. Penugasan diperiksa ulang
setelah mengambil lock; actor authVersion diperiksa pada mutasi. Worker tetap
memakai job→session→media; publish tidak mengambil lock job, sehingga tidak
memperkenalkan urutan lock terbalik. Optimistic concurrency dan unique
(session_id,revision)/(session_id,assignment_event_id) menjaga konsistensi.

Playback Coach tetap expiresAt=uploadedAt+24 jam. Pemeriksaan setiap chunk dan
watchdog memakai transaksi DB baru, actor authVersion/role dan current event
penugasan; transfer/revoke menutup stream lama, bahkan bila Coach kemudian
ditugaskan kembali. Range/error 410/416 sama dengan Fase 4; expiry tidak
diperpanjang oleh review/tugas/retry. Byte yang sudah dikirim tidak dapat ditarik.

0006 menambah assignment_events, coach_member_assignments, feedback_drafts,
review_revisions, review_heads, follow_up_tasks, retry_intents. Tidak membuat
penugasan atau published review otomatis dari note lama. Data/auth/queue existing
dipertahankan; admin harus assign Member secara eksplisit. Downgrade menghapus
tabel Fase 6 dan datanya, bukan alat undo transfer/review; jangan downgrade
data nyata yang sudah memakai fitur ini tanpa prosedur backup yang sesuai.

Native menjadi default dan dicatat di AGENTS.md. Database development masih
belum dimigrasi; `.env` aktual belum sesuai target native yang disepakati dan
root MySQL lokal memerlukan password. Tidak ada reset password/ubah service.
Setelah konfigurasi/target benar disiapkan, pada terminal native tanpa URL tes:

```powershell
.venv/Scripts/alembic.exe upgrade head
.venv/Scripts/alembic.exe check
.venv/Scripts/python.exe -m scripts.seed
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Worker dan cleanup tetap dijalankan pada terminal native terpisah sebagaimana
Fase 3. Docker tetap opsi bila diminta/disepakati; tidak dinyalakan pada fase ini.

## Bukti pengujian

Baseline native sebelum perubahan: **158 passed, 11 skipped, 14 warnings in
32.86s**, `python -m pytest -q --basetemp=.cache/phase6-baseline`.
Suite native SQLite: **185 passed, 15 skipped, 19 warnings in 42.96s**,
`python -m pytest -q --basetemp=.cache/phase6-sqlite-complete`.
API SQLite memory, migrasi file sementara dan media/tmp workspace. Lima belas
skip khusus row-lock/race MySQL, bukan kegagalan endpoint Fase 6.

Instance MySQL tes memakai binary native **8.0.46**, port loopback 13308 dan
direktori data baru `.cache/phase6-mysql-native`, bukan service MySQL80/data
development. MySQL X Protocol dinonaktifkan dan buffer pool tes dibatasi 64 MiB.
Schema API/migrasi/smoke masing-masing silatsense_phase6_api_test,
silatsense_phase6_migration_test, silatsense_phase6_smoke_test. Semua URL fixture
diakhiri `_test`; JWT tes juga memakai signing key khusus, tidak memakai secret
development. Tidak ada Docker/container atau download runtime selama fase ini.

Tes mencakup penugasan tunggal/role/event/no-op, transfer/revoke dan arsip draft
saat Coach kembali, scope endpoint lama/baru/media, optimistic version,
single-publish/replay/task, rollback atomik, author/revision immutable, tugas
owner-only, retry terminal/tanpa Coach, cursor/search roster, top issues distinct,
statistik scope profil/overview, serta migrasi existing/kosong dan alembic check.
Race MySQL mencakup penugasan simultan, publish paralel key sama/berbeda, dan
transfer beradu publish dengan satu urutan commit yang sah.

Smoke HTTP **native** lulus: CLI assign → upload 202 → worker MediaPipe nyata
→ Range 206 → draft → publish/replay → tugas Member completed → CLI transfer
→ Coach lama 404 → Coach baru merevisi → author lama/baru dan tugas tetap ada
→ retry/replay → CLI revoke → Member tetap membaca published review; docs dan
OpenAPI 200. Video sintetis kosong, analisis reference_not_ready/score null,
bukan validasi ilmiah video manusia atau benchmark 10–15 pengguna.

Suite final **MySQL native: 200 passed, 19 warnings in 372.83s**,
`python -m pytest -q --basetemp=.cache/phase6-mysql-final --tb=short` dengan
TEST_DATABASE_URL ke schema API dan MIGRATION_TEST_DATABASE_URL ke schema
migrasi terpisah di atas, root khusus instance sementara port 13308. Termasuk
seluruh race serta upgrade/downgrade/re-upgrade/preservasi dan alembic check.
Root/password/data service development tidak dipakai.

Regresi akhir privacy/header dan join stream pada SQLite: **2 passed in 0.68s**.
Regresi yang sama pada MySQL native dengan kode final: **2 passed, 1 warning in
2.22s**, termasuk no-store error legacy dan pencabutan streaming saat transfer.
Warning deprecation httpx/TestClient dan Alembic path_separator tetap ada;
warning join cartesian pada pemeriksaan awal MySQL sudah diperbaiki, tidak
muncul pada suite final. Pemeriksaan header tambahan menggunakan kode final.

API smoke berhenti setelah pengujian. Instance MySQL native sementara dihentikan
setelah @@datadir diverifikasi menunjuk direktori tes milik tugas ini; data dan
seluruh schema tesnya sudah dihapus. Service MySQL80 pengguna tetap Running.
Database development, `.env` dan Docker tidak diubah/dijalankan pada fase ini.

## Integrasi FE dan tahap selanjutnya

FE belum diubah. Tambahkan UI roster/overview Coach, Coach optional, pembedaan
Coach aktif dan author lama, draft pribadi serta konflik 409 (refetch sebelum
menulis ulang), konfirmasi publish eksplisit, reviewHistory/task status, retry
intent lalu upload retryOf. Setelah transfer, 404 berarti scope dicabut; buang
data/cache pribadi lama. Playback tetap melalui proxy Bearer/Range, no-store.
Gunakan coach/profile/overview dengan scope binaan, bukan data dummy global.

Fase 7 berikutnya: linking email dengan reautentikasi, verifikasi email,
request/confirm password reset hanya melalui email verified, SMTP test adapter,
token sekali pakai/rate limit/pencabutan sesi, bridge auth FE/single-flight refresh,
dan pemeriksaan operasi/integrasi browser. Endpoint tersebut belum diimplementasikan.

## File yang berubah

Ditambahkan: `alembic/versions/0006_coaching_reviews.py`, `app/api/coaching.py`,
`app/schemas/coaching.py`, `app/schemas/reviews.py`,
`app/repositories/assignments.py`, `app/repositories/reviews.py`,
`app/services/assignments.py`, `app/services/coaching.py`, `app/services/reviews.py`,
`scripts/assign_coach.py`, `tests/test_coaching.py`, `tests/test_mysql_coaching.py`,
`docs/phase6-api.md`.

Diperbarui: `AGENTS.md`, README, `app/main.py`, `app/api/routes.py`,
`app/core/cursors.py`, `app/core/errors.py`, `app/models/entities.py`,
`app/repositories/history.py`, `app/repositories/profiles.py`,
`app/schemas/history.py`, `app/schemas/sessions.py`, `app/services/history.py`,
`app/services/profiles.py`, `app/services/sessions.py`, `app/services/media.py`,
`tests/conftest.py`, `tests/test_api.py`, `tests/test_results_media.py`,
`tests/test_history_dashboard.py`, `tests/test_profiles_training.py`,
`tests/test_migrations.py`, `docs/api-contract.md`, `docs/architecture.md`,
`docs/fe-integration.md`, `docs/phase4-api.md`, `docs/phase5-api.md`.
Total 39 file deliverable; skrip/data sementara `.cache` diabaikan Git.

Pemeriksaan AST Python, JSON/fence/link lokal Markdown dan whitespace lulus.
Hash 234 file terlindungi dari snapshot sebelumnya tetap cocok (`.env`, FE,
migrasi 0001–0003, sumber rencana prototype); 0004–0005 juga tidak diedit.
