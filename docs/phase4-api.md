# Fase 4 — evaluasi, pose dan media privat

Dokumen ini merekam implementasi Fase 4. Histori/dashboard yang saat itu masih
rencana kini tersedia pada [Fase 5](phase5-api.md), disusul binaan/review
[Fase 6](phase6-api.md); head source saat ini 0006.

Status 17 Oktober 2026: tersedia pada kode backend. Base path `/api/v1` tetap,
head migrasi **0004**; Fase 4 memakai kolom result_json, soft-delete dan
acknowledged_at yang sudah ada. Tidak ada migrasi baru, perubahan `.env`,
database development, FE, prototype, dataset atau model.

## Endpoint tersedia

Semua endpoint berikut khusus Member pemilik sesi, Bearer per request, no-store.
Coach belum mendapat akses baru; binaan dan review manusia berada pada Fase 6.

| Method | Path setelah `/api/v1` | Hasil |
| --- | --- | --- |
| GET | `/member/sessions/{sessionId}/evaluation` | Evaluation camelCase, ID string, UTC Z |
| GET | `/member/sessions/{sessionId}/pose` | `{sessionId,pose,reason}`; pose nullable |
| GET | `/member/sessions/{sessionId}/video` | 200 penuh atau 206 single byte Range |
| POST | `/member/sessions/{sessionId}/acknowledge` | `{acknowledgedAt}` UTC; timestamp pertama, idempotent |
| DELETE | `/member/sessions/{sessionId}` | 204; owner dapat mengulang, hasil audit dipertahankan |

GET status sesi sekarang memberi playbackPath jika media available.
evaluationUrl dari upload sudah aktif. Poll statusUrl sampai completed sebelum
membaca evaluasi/pose. queued/processing → 409 evaluation_pending, failed → 409
analysis_failed. Acknowledge juga hanya untuk completed; tidak membuat hasil
atau memperpanjang retensi. Unknown/invalid/owner lain/deleted → 404;
tanpa Bearer → 401; role Coach → 403. Mutasi memeriksa Origin jika dikirim.

```http
GET {{baseUrl}}/member/sessions/{{sessionId}}/evaluation
Authorization: Bearer {{accessToken}}

GET {{baseUrl}}/member/sessions/{{sessionId}}/pose
Authorization: Bearer {{accessToken}}

GET {{baseUrl}}/member/sessions/{{sessionId}}/video
Authorization: Bearer {{accessToken}}
Range: bytes=0-1023

POST {{baseUrl}}/member/sessions/{{sessionId}}/acknowledge
Authorization: Bearer {{accessToken}}

DELETE {{baseUrl}}/member/sessions/{{sessionId}}
Authorization: Bearer {{accessToken}}
```

`baseUrl` mencakup `/api/v1`. Isi token/ID dari akun tes sendiri; jangan menaruh
token pada query URL. Swagger `/docs` menyediakan schema dan Try it out.

## Evaluasi dan data terukur

DTO lengkap mengikuti [api-contract.md](api-contract.md). Hasil baru menyimpan
20 fitur yang dikenal pada keyframe yang sama: value mentah, bodyPart, unit
deg/shoulder_width, referenceMedian/referenceIqr, deviation bertanda,
assessment dan reason. Angka hilang null, bukan nol. Fitur tidak dibandingkan
not_assessed meski tidak muncul pada issues. Assessment within_reference
berarti <1 IQR, deviates berarti ≥1 IQR. Ini statistik referensi eksperimen,
bukan keputusan Coach atau standar IPSI. Issues tetap maksimum enam deviasi.

Pemilihan frame/referensi terbaik dan rumus skor tidak berubah. Snapshot nilai
measurement dan statistik disimpan, tidak dihitung ulang dari artifact aktif
pada GET. Jika referensi tidak comparable, frame pertama dengan ≥8 fitur valid
menjadi keyframe pose/nilai mentah tanpa skor. Jika tidak ada frame valid, pose
null dan measurements kosong. Pukulan/tendangan tetap dapat menghasilkan
reference_not_ready dengan score null. Repetisi dan analisis temporal belum
didukung; validRepetitions/deviatedRepetitions null, alasan ada pada
unavailableReasons. reviewStatus tetap pending dan reviewAvailable false.

Pose berisi raw image-normalized landmark sebelum hip centering/shoulder scale.
Koreksi rasio x/z extractor dibalik untuk overlay, origin top-left; z relatif
lebar gambar, bukan meter. Index mengikuti anatomi MediaPipe, bukan mirror UI.
Dimensi pose adalah frame inference setelah orientasi/resize, dapat berbeda
dari metadata media. Landmark nonfinite atau visibility di luar 0–1 diomit;
nilai x/y di luar gambar tidak diclamp. Ini satu keyframe, bukan animasi video.

Hasil sebelum Fase 4 tidak diproses ulang. Jika tidak tersimpan, pose null dengan
pose_not_stored, measurements kosong dengan measurements_not_stored,
featureVersion null dengan feature_version_not_stored. Data versi aktif tidak
dipakai untuk menebak histori. Expiry video tidak menghapus evaluasi/pose/note.
Restart API dan worker setelah memperbarui kode agar analisis baru menyimpan
data Fase 4; job lama masih kompatibel dengan DTO legacy.

## Playback, expiry dan delete

Media privat hanya selama uploadedAt+86400 detik. Setiap request, termasuk
Range, memeriksa pemilik dan deadline sebelum membaca file. Setelah pemilik
disahkan: expired → 410 media_expired, media dihapus → 410 media_deleted,
legacy tanpa media/file hilang → 410 media_unavailable. Sesi soft-deleted selalu
404 melalui semua endpoint biasa; 410 tidak membocorkan objek milik orang lain.

Mendukung `bytes=start-end`, `bytes=start-`, `bytes=-suffix`; end/suffix lebih
besar dari file dibatasi ukuran file. Range invalid, di luar file, suffix nol,
atau multi-range → 416 invalid_range + Content-Range `bytes */size`.
200/206 mengirim Content-Length, Content-Type, Accept-Ranges, no-store dan
nosniff; 206 juga Content-Range. Tidak memuat seluruh file ke RAM, chunk 256 KiB.
Bearer tetap wajib, tidak ada signed public URL/static mount/path storage.

Stream mengecek DB dalam transaksi baru per chunk dan deadline sebelum yield.
Watchdog terpisah memeriksa akses tiap 0,5 detik serta deadline, sehingga client
yang lambat/stall juga dibatalkan saat delete/password revocation/expiry.
Gangguan DB menutup stream. Stream yang terpotong membutuhkan request baru;
byte yang sudah diterima client tidak dapat ditarik kembali. Batas pemeriksaan
akses mengasumsikan DB responsif, bukan janji penarikan byte pada jaringan.

DELETE mengunci User, lalu job → session → media konsisten dengan worker dan
cleanup. Soft-delete langsung menutup akses, membatalkan claim/fence hasil;
lease reader inference dipertahankan sampai worker berhenti/lease berakhir.
Cleanup sekarang mengambil deletion_requested_at sekaligus expired, unlink
idempotent. File terbuka di Windows dapat menunda unlink sampai siklus berikut.
Hasil, issue dan catatan audit dipertahankan; endpoint legacy daftar/detail/note
juga menolak hasil dari sesi terhapus, shape respons legacy tetap sama.
Statistik profil existing sudah mengecualikan sesi deleted. Replay key upload
lama tidak dapat menghidupkan sesi yang dihapus.

## Integrasi FE berikutnya

FE belum diubah. Gunakan sessionId, tampilkan null/reason tanpa angka dummy,
render measurement dinamis dan bedakan processing/analysis/review status.
Overlay memakai dimensi/koordinat pose dan memperhatikan letterbox/mirror.
Gunakan proxy FE terautentikasi yang meneruskan Range/Bearer, status 206/416,
Content-Range/Length/Type dan Accept-Ranges. Elemen video tidak dapat memasang
Bearer sendiri; jangan memakai playbackPath BE sebagai URL publik langsung.
Bridge cookie/refresh tetap Fase 7, desain di [fe-integration.md](fe-integration.md).
Tampilkan media expired sebagai kondisi normal sementara hasil tetap terbaca.
Acknowledge setelah hasil dilihat dan DELETE dari aksi pengguna; UI perlu
memperbarui data/cache sesudah mutasi. Kamera tetap browser-only.

## Verifikasi dan batas

Tes memakai SQLite
memory/file sementara atau dua schema MySQL disposable `_test`, tidak memakai
DATABASE_URL development. Folder sementara khusus `.cache/phase4-*` dipakai
karena folder pytest OS default mengalami PermissionError Windows.

Baseline historis Fase 3: 95 passed, 9 skipped pada SQLite; 104 passed MySQL.
Regresi suite lama pada Fase 4: **95 passed, 9 skipped, 9 warnings in 18.94s**
dengan `python -m pytest -q --basetemp=.cache/phase4-regression-01`.
Tes baru mencakup HTTP Range/416/401/403/404/410, expiry tepat tenggat,
stream lambat dan pencabutan, data pose/measurement, legacy, acknowledge,
delete/fencing/cleanup/audit serta race delete–complete dan acknowledge MySQL.

- Suite final SQLite: **128 passed, 11 skipped, 9 warnings in 44.36s**,
  `python -m pytest -q --basetemp=.cache/phase4-sqlite-final-03`.
  Sebelas skip khusus race/row-lock MySQL, bukan kegagalan endpoint/decoder.
- Suite MySQL native disposable: **137 passed, 9 warnings in 342.37s**,
  `python -m pytest -q --basetemp=.cache/phase4-mysql-01`, dengan
  TEST_DATABASE_URL ke silatsense_phase4_test dan MIGRATION_TEST_DATABASE_URL
  ke silatsense_phase4_migration_test, host 127.0.0.1:13308 container tes.
  Termasuk upgrade/downgrade/re-upgrade existing/kosong dan alembic check.
- Setelah suite MySQL native tersebut, satu kasus pemilihan best-frame dan
  satu kasus expiry saat DB lambat ditambahkan; keduanya lulus pada suite
  final SQLite. Regresi akhir modul results/media: **33 passed in 16.47s**.
  Assertion tambahan audit note dan statistik: **1 passed in 0.91s**.
- Image Linux silatsense-be-phase4-test dibangun; subset Linux evaluasi/stream
  dan intelligence **37 passed in 9.94s** sebelum tambahan slow-DB timer.
- Suite lengkap Linux/MySQL disposable: **138 passed, 9 warnings in 264.47s**,
  `docker run --rm --network silatsense-phase4-test-net` dengan kedua URL schema
  tes di atas menuju host container `silatsense-phase4-mysql-test:3306`, artifact
  read-only, image tes, `python -m pytest -q`. Pemeriksaan final setelah perubahan
  timer dan assertion audit memakai bind read-only dua file terbaru:
  **2 passed, 1 warning in 2.11s** (slow-DB expiry dan delete/audit/statistik).
- Smoke HTTP Linux nyata: upload 202 → Range awal/suffix 206 dan multi-range
  416 → worker CLI dengan MediaPipe model lokal → completed/reference_not_ready
  dan score null → evaluasi/pose 200 → acknowledge/replay → expiry 410 tanpa
  menghapus hasil → delete/replay 204 → detail legacy 404 → cleanup;
  health/docs/OpenAPI 200. Video sintetis kosong, bukan video manusia.
- Compose config --quiet, AST Python, fence/JSON/link lokal Markdown lulus.
  Hash **234 file terlindungi** dari snapshot Fase 3 cocok: `.env`, migrasi
  0001–0003, FE dan sumber rencana prototype. 0004 juga tidak diedit.
  Warning httpx/TestClient dan Alembic path_separator tetap ada.

Container API/MySQL tes, volume media dan network disposable sudah dibersihkan.
Tag image tes dapat tetap menjadi cache build lokal; layanan/volume development
tidak diubah. Folder `.cache` hanya berisi file tes yang diabaikan Git.

## File yang berubah

Ditambahkan: `app/schemas/results.py`,
`app/intelligence/features/presentation.py`, `app/services/results.py`,
`app/services/media.py`, `tests/test_results_media.py`, `docs/phase4-api.md`.

Diperbarui: `app/api/sessions.py`, `app/api/routes.py`, `app/main.py`,
`app/services/analysis.py`, `app/services/sessions.py`, `app/services/cleanup.py`,
`app/repositories/evaluations.py`, `app/repositories/jobs.py`,
`tests/test_sessions_jobs.py`, `tests/test_mysql_sessions.py`, README dan
`docs/api-contract.md`, `docs/architecture.md`, `docs/fe-integration.md`,
`docs/phase3-api.md`, `docs/evaluation-method.md`. Total 22 file deliverable;
script dan media tes sementara di `.cache` diabaikan Git.

## Pekerjaan berikutnya

Development belum dimigrasi; alembic check development tetap tertunda karena
koneksi native belum sesuai target. Pemeriksaan schema dilakukan pada DB tes.
Tidak ada benchmark 10–15 pengguna atau validasi pakar/video silat manusia.
Fase 5 berikutnya: histori cursor/filter, dashboard/agregat comparable dengan
sampleCount, empty/null, durasi verified, serta batas tanggal Asia/Jakarta.
Fase 6 binaan/review/tugas, Fase 7 bridge auth/email recovery tetap terpisah.
