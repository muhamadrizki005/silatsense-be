# Fase 3 — upload persisten, sesi, storage dan worker

Dokumen ini merekam hasil Fase 3. Evaluasi/pose/playback/acknowledge/delete
yang saat itu masih rencana kini tersedia pada Fase 4; status terkini ada di
[phase4-api.md](phase4-api.md). Contoh null playbackPath di bawah bersifat historis.

Status 17 Oktober 2026: implementasi backend tersedia dengan migrasi **0004**.
Database development belum dimigrasi; `.env`, FE, prototype dan migrasi 0001–0003
tidak diubah. Semua pengujian MySQL memakai container/schema disposable.

## API yang sudah tersedia

Base path tetap `/api/v1`, Bearer Member, Cache-Control no-store dan requestId
seperti error domain Fase 2. Endpoint baru:

| Method | Path | Hasil |
| --- | --- | --- |
| POST | `/member/sessions` | Multipart `movementSlug`, `video`, optional `retryOf`, header Idempotency-Key; 202 |
| GET | `/member/sessions/{sessionId}` | Status, timestamps, evaluationId, metadata media privat; 200, owner-only |

```http
POST {{baseUrl}}/member/sessions
Authorization: Bearer {{accessToken}}
Idempotency-Key: {{uniqueUploadKey}}
Content-Type: multipart/form-data; boundary=upload-boundary

--upload-boundary
Content-Disposition: form-data; name="movementSlug"

pukulan
--upload-boundary
Content-Disposition: form-data; name="video"; filename="latihan.mp4"
Content-Type: video/mp4

<byte video lokal>
--upload-boundary--
```

Dalam aplikasi gunakan FormData dan biarkan client membuat boundary; contoh
di atas ilustrasi wire format, bukan file video yang dapat dipaste langsung.

```json
{
  "sessionId": "<session-id>",
  "processingStatus": "queued",
  "statusUrl": "/api/v1/member/sessions/<session-id>",
  "evaluationUrl": "/api/v1/member/sessions/<session-id>/evaluation",
  "uploadedAt": "2026-10-17T00:00:00.000000Z"
}
```

Timestamp contoh bukan waktu sesi aktual. `uploadedAt` aktual dicatat saat
seluruh byte diterima, sebelum validasi selesai; expiry selalu uploadedAt+24 jam.
`evaluationUrl` dicadangkan kontrak **Fase 4**, belum GET endpoint aktif.
Untuk Fase 3 poll statusUrl; setelah completed, evaluationId dapat dipakai pada
GET `/evaluations/{evaluationId}` prototype yang tetap memiliki DTO lama.
Playback, pose/measurement API baru, acknowledge dan DELETE menunggu Fase 4.
`media.playbackPath` saat ini selalu null, bukan URL palsu ke endpoint belum ada.

GET sesi mengirim processingStatus queued/processing/completed/failed,
analysisStatus/evaluationId nullable, startedAt/completedAt nullable, retryOf,
error terstruktur atau null, media.status dan metadata byte/MIME/dimensi/durasi.
Review masih pending dan reviewAvailable false; binaan Coach Fase 6. Media
available berarti file tersimpan privat, **bukan playback publik sudah tersedia**.
Expiry segera tampil expired meski cleanup fisik belum berjalan. Owner lain,
ID invalid/nonexistent/deleted → 404; Coach tidak mendapat akses endpoint Member.

Idempotency-Key 1–128 karakter, tidak boleh hanya spasi, scope user+upload.
Fingerprint checksum byte+movementSlug+retryOf. Key/payload sama mengembalikan
respons penerimaan asli (masih queued pada body replay); status aktual selalu
dibaca lewat statusUrl. Payload berbeda → 409 idempotency_conflict. Rekaman
idempotensi saat ini dipertahankan, tidak dipangkas otomatis setelah 24 jam.
Replay yang sudah accepted tetap bekerja ketika kuota antrean penuh. Dua
unggahan identik yang lolos reservasi paralel menghasilkan satu sesi/file/job.
Request baru yang belum diterima tetap dapat ditolak kuota sebelum fingerprint
diketahui. retryOf harus sesi sendiri dengan kategori sama; tidak menimpa hasil
atau mengubah keputusan sesi lama.

## Validasi dan storage

- MP4/MOV/WebM, default 100 MiB file + maksimum 1 MiB overhead multipart,
  60 detik, resolusi sisi panjang ≤3840 dan sisi pendek ≤2160. MIME/extension
  client hanya whitelist awal; signature container dan seluruh frame didekode
  dalam child process untuk memverifikasi metadata/validitas sebelum 202.
- Deadline probe 30 detik, memory child awal 2048 MiB; timeout validasi → 503.
  Invalid/kosong/durasi/resolusi → 422; oversized → 413; suffix/MIME → 415.
  Body chunked juga dibatasi sebelum multipart spool tumbuh tanpa batas.
- FastAPI dapat spool multipart sementara di OS temp. Storage persisten memakai
  MEDIA_ROOT privat (`.data/media` default), UUID key dan atomic rename;
  file parsial/failed/duplikat dibersihkan. Path/nama client tidak dipakai sebagai
  lokasi file. Tidak ada mount static atau token/path privat pada respons API.
- Reservasi per-user dilakukan dengan lock User: default maksimal dua sesi
  queued/processing termasuk upload in-flight dan kuota media 500 MiB. File
  expired tetap dihitung sampai benar-benar terhapus. Pelanggaran → 429.
  Ukuran reservasi memakai byte count parser server (atau batas maksimum),
  diperiksa kembali saat commit. Cleanup harus hidup agar reservasi crash dan
  byte expired tidak terus menahan kuota.
- Password berubah selama validasi: pemeriksaan authVersion ulang saat commit
  menolak request lama dengan 401, tanpa file/job yang diakui sebagai accepted.

Sesi, media, job, idempotensi dan pelepasan reservasi berada dalam satu transaksi
DB. Rename file bukan transaksi DB: kegagalan commit memeriksa linkage DB
sebelum unlink, dan reconciler menangani crash/orphan. Jangan menyajikan folder
private secara langsung melalui FE/web server.

## Worker, recovery dan retensi

Worker CLI hidup terpisah dari API; bukan FastAPI BackgroundTasks. Job MySQL
persisten memakai FOR UPDATE SKIP LOCKED, lease 60 detik, heartbeat 15 detik,
claim token fencing, maksimum tiga attempts dan retry transient setelah 5/30
detik. Satu inference default; WORKER_CONCURRENCY dapat diatur setelah mengukur
resource laptop. Inference child process terpisah, batas waktu 120 detik dan
memory 2048 MiB, diterminasi saat timeout/shutdown/expiry/kehilangan lease.
Windows job object dan Linux parent-death signal membatasi child yatim.

Snapshot seluruh referensi tervalidasi + checksum, model checksum, versi
analyzer/fitur, FPS sampling dan batas durasi disimpan saat penerimaan. Restart
atau penggantian artifact aktif tidak diam-diam mengganti referensi job lama.
Model/versi tidak tersedia adalah failure permanen dengan kode aman, bukan
angka pengganti. Tanpa referensi → completed/reference_not_ready/score null,
bukan retry error. Hasil evaluation existing dan completed status commit atomik,
unique evaluation per training session. Worker lama tidak dapat heartbeat atau
commit setelah claim berpindah. MySQL memakai DATETIME(6) pada tabel baru agar
lease/retensi tidak dibulatkan ke detik berikutnya.

Cleanup periodik 60 detik: expiry menutup eligibility inference, queued expired
menjadi failed/media_expired, active job difence dulu dan file ditahan sampai
lease reader berakhir. Baru unlink dan tandai deleted; hasil/review tidak
dihapus. Reservasi expired dibersihkan; orphan file bertipe UUID tanpa relasi
DB setelah grace 1 jam dihapus setelah pemeriksaan ulang transaksi baru.
Cleanup idempotent dan tidak mengikuti symlink/path di luar MEDIA_ROOT.

## Migrasi, native dan Compose

0004 menambah training_sessions/media_assets/analysis_jobs/upload_reservations/
idempotency_records dan unique FK evaluation_sessions.training_session_id.
Hasil legacy dibackfill satu sesi completed per evaluation, ID hasil dan note
lama tetap; uploadedAt/durasi/media legacy tidak dikarang. Endpoint prototype
sinkron masih kompatibel, dan hasil baru prototype juga mendapat relasi sesi.
Statistik profil tidak menggandakan hasil; durasi verified sesi baru dihitung,
versi feature legacy yang tidak tersimpan tetap tidak ditebak.

Verifikasi target DATABASE_URL sebelum migrasi. Native yang disepakati:
root@localhost:3306/silatsense; `.env` aktual masih mengarah ke user/port lama.
Jangan menjalankan migrasi ke database event_sportainment/prototype. Setelah
target benar disiapkan lokal, jalankan migrasi/seed **sekali**:

```powershell
.venv/Scripts/alembic.exe upgrade head
.venv/Scripts/alembic.exe check
.venv/Scripts/python.exe -m scripts.seed
```

Lalu jalankan tiga terminal dari root proyek dengan DATABASE_URL dan MEDIA_ROOT
yang sama (jangan memakai override URL SQLite dari terminal tes):

```powershell
# Terminal API
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001

# Terminal worker
.venv/Scripts/python.exe -m scripts.worker

# Terminal cleanup
.venv/Scripts/python.exe -m scripts.cleanup_media
```

Worker/cleanup mendukung `--once`; Ctrl+C menghentikan loop dan child dengan
recovery melalui lease/retry. Parameter default yang didukung Settings sudah
ditambahkan ke `.env.example`; `.env` aktual tidak ditulis. MEDIA_RETENTION_HOURS
dikunci 24, bukan knob untuk memperpanjang rekaman. Secret tetap lokal.

Compose opsional sekarang memiliki db, migrate (one-shot), backend, worker dan
cleanup, shared volume `silatsense-be_media_data`, serta model/artifact mount.
API/worker/cleanup menunggu migration berhasil, bukan berlomba migrasi sendiri.
`docker compose up -d --build --wait` memakai volume DB Compose terpisah dari
native. Konfigurasi Compose sudah divalidasi; tidak dijalankan pada development
selama tugas ini. Image Linux dan smoke test memakai resource **khusus tes**.
Health API tetap liveness sederhana; heartbeat fleet/readiness dan monitoring
operasi lengkap menunggu Fase 7, bukan klaim health worker yang belum diukur.

## Bukti pengujian

- Suite MySQL disposable: **104 passed, 9 warnings in 212.24s**. Termasuk dua
  schema terpisah API dan migrasi, upgrade kosong/existing, downgrade/re-upgrade,
  `alembic check`, quota race, duplicate upload, two-worker claim/finish dan
  password revocation selama upload. Database development tidak disentuh.
- Suite SQLite final: **95 passed, 9 skipped, 9 warnings in 17.09s**; sembilan
  skip khusus row lock/race MySQL, bukan tes decoder/inference yang gagal.
- Tes baru mencakup decoder MP4 nyata, invalid/size/durasi/resolusi/chunked,
  ownership/slug/retry/idempotensi, snapshot, atomic result/commit failure,
  lease/crash/fencing/retry cap, cleanup reservation/orphan/expired, timeout.
- Inference child MediaPipe diuji pada video sintetis kosong (model lokal
  opsional untuk tes tersebut); bukan validasi gerakan silat manusia.
- Image `silatsense-be-phase3-test` berhasil dibangun; smoke Linux HTTP auth →
  upload 202 → worker CLI → completed → score null → legacy result → replay
  idempotent → statistik durasi benar, health/docs 200. Model hanya read-only.
- Warning deprecation httpx/TestClient dan Alembic path_separator masih ada.
  Tidak ada klaim throughput 10–15 pengguna atau validitas ilmiah skor baru.

Untuk mengulang gunakan terminal tes khusus, TEST_DATABASE_URL ke schema API
disposable `_test`, MIGRATION_TEST_DATABASE_URL ke schema migrasi **lain dan
kosong** `_test`. Fixture create/drop tabel; jangan memakai development.
SQLite: kosongkan kedua URL tes dan jalankan `.venv/Scripts/python.exe -m pytest
-q`; tes row lock MySQL akan skip. Bukti SQLite final dicatat di README.

## Batas fase dan berikutnya

Fase 4: GET evaluasi baru, measurements/keyframe/pose, playback privat Range,
acknowledge/delete dan uji akses media. Jangan menghubungkan src video ke folder
MEDIA_ROOT. Fase 5 histori/dashboard lengkap, Fase 6 binaan/review, Fase 7
bridge FE/email recovery/operasi. FE masih stub/dummy dan belum diubah.
