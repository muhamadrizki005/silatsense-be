# Handoff: kuota koneksi database worker

Pemeriksaan 23 November 2026, branch `codex/coach-reference-api`.
Perubahan Coach API yang sudah ada dipertahankan. Tidak ada push, merge atau deploy.

## Penyebab dan bukti yang boleh dibagikan

Koneksi diagnostik dengan konfigurasi `.env.worker` ditolak oleh Filess sebelum
`SELECT 1` dapat berjalan. Pemeriksaan ulang setelah implementasi menghasilkan:

```json
{"status":"unavailable","errorCategory":"database_capacity","dbErrorCode":1226,"resource":"max_user_connections","resourceLimit":5}
```

Ini mengonfirmasi kuota koneksi simultan akun penuh, bukan kegagalan model/B2.
Saat inventaris lokal dilakukan, tidak ditemukan proses yang cocok sebagai API,
worker atau cleanup, maupun socket lokal ke port database. Proses Python lain
tidak dihentikan. Pemilik koneksi yang masih memenuhi kuota **belum teridentifikasi**:
login ditolak sehingga process list tidak dapat diperiksa dari akun aplikasi.
Instance Vercel production/preview, web client database atau klien lain adalah
kemungkinan, bukan penyebab yang sudah terbukti. Kesehatan B2 tidak diuji ulang.

Sebelumnya Engine aplikasi hanya mengaktifkan `pool_pre_ping`. QueuePool bawaan
SQLAlchemy dapat mempertahankan 5 koneksi dan membuka 10 overflow per Engine.
Koneksi dibuka sesuai kebutuhan, bukan langsung 15 saat startup. Batas potensial
ini melampaui kuota akun 5. Menutup Session mengembalikan koneksi ke pool;
koneksi idle di pool tetap menggunakan jatah server.
[Dokumentasi SQLAlchemy](https://docs.sqlalchemy.org/en/20/core/pooling.html).

Audit kode: API dan worker memakai Engine masing-masing bila dijalankan sebagai
proses berbeda. Thread dalam satu proses worker berbagi Engine. Repository job
menutup Session pada akhir claim/heartbeat/complete/fail; claim selesai sebelum
inference. Heartbeat dilakukan berurutan, tanpa thread koneksi tambahan khusus.
Child inference/probe tidak mengakses database. Tidak ditemukan kebocoran Session
heartbeat pada jalur tersebut. CLI cleanup mempunyai Engine sendiri jika dijalankan;
Alembic memakai NullPool tersendiri. Proses ganda tetap menggandakan anggaran pool.

## Implementasi dalam perubahan ini

- `app/core/config.py`: konfigurasi pool/timeouts tervalidasi dan jeda error worker.
- `app/db/session.py`: default QueuePool 1 + overflow 0 untuk database jaringan,
  opsi NullPool, timeout PyMySQL, `hide_parameters=True`. Perilaku pool SQLite
  dipertahankan; argumen timeout MySQL tidak dikirim ke SQLite.
- `app/core/error_metadata.py`: hanya kategori, kode DB dan resource/limit yang
  diizinkan. Tidak mengeluarkan exception mentah, username, URL, SQL atau parameter.
- `app/services/worker.py`: error iterasi menjadi JSON aman; retry 5, 10, 20, 40,
  60 detik lalu maksimal 60. Setelah iterasi berhasil, kembali ke jeda normal.
  Penantian tetap memakai stop event sehingga shutdown dapat menyela backoff.
  Lease, fencing, heartbeat dan transaksi job tidak diubah.
- `scripts/worker.py`: preflight database juga mengeluarkan metadata aman.
- `scripts/db_status.py`: satu `SELECT 1`, tanpa query job atau akses storage,
  lalu dispose Engine diagnostik sendiri. Exit 0=berhasil, 1=tidak tersedia.
- `.env.example`, README dan CI: contoh konfigurasi, dokumentasi dan format checks.
- `tests/test_db_pooling.py`, `tests/test_worker_errors.py`: uji batas nyata pool
  dengan SQLite disposable, pengembalian/rollback koneksi, konfigurasi, NullPool,
  CLI read-only, redaksi log dan reset/cap backoff. Tes worker memakai iterasi palsu.

Tidak ada perubahan schema/data/auth, artifact model, frontend atau isi `.env`
privat. Kontrak `/api/v1` dan payload FE tetap sama.

## Konfigurasi yang disarankan

Nilai berikut adalah konfigurasi non-secret; **belum diterapkan ke Vercel atau
file env privat**. Nilai default kode sudah sama dengan contoh ini.

| Variabel | API lokal | Worker laptop | Vercel per instance |
| --- | --- | --- | --- |
| `DB_POOL_MODE` | `queue` | `queue` | `queue` |
| `DB_POOL_SIZE` | `1` | `1` | `1` |
| `DB_MAX_OVERFLOW` | `0` | `0` | `0` |
| `DB_POOL_TIMEOUT_SECONDS` | `5` | `5` | `5` |
| `DB_POOL_RECYCLE_SECONDS` | `300` | `300` | `300` |
| `DB_CONNECT_TIMEOUT_SECONDS` | `5` | `5` | `5` |
| `DB_READ_TIMEOUT_SECONDS` | `10` | `10` | `10` |
| `DB_WRITE_TIMEOUT_SECONDS` | `10` | `10` | `10` |
| `WORKER_CONCURRENCY` | tidak relevan | `1` | jangan jalankan worker di sini |
| `WORKER_ERROR_BACKOFF_SECONDS` | tidak relevan | `5` | tidak relevan |
| `WORKER_ERROR_MAX_BACKOFF_SECONDS` | tidak relevan | `60` | tidak relevan |

Untuk QueuePool, batas checkout per Engine = `DB_POOL_SIZE + DB_MAX_OVERFLOW`.
Ini **bukan batas global lintas proses/instance**. Contoh anggaran: satu API lokal
1 + satu worker 1 + satu instance Vercel 1 + satu web client 1 = 4, menyisakan
1 untuk administrasi/diagnostik. Contoh ini hanya berlaku bila tidak ada koneksi
lain dan setiap slot benar-benar dibatasi; autoscaling/preview Vercel dapat
membuka lebih dari satu Engine. Tidak ada jaminan deployment Vercel cukup hanya
memakai satu koneksi secara total. Sisakan ruang untuk diagnostik.

`pool_pre_ping` memeriksa koneksi, bukan mengurangi kuota. Recycle 300 detik baru
berlaku saat checkout; bukan timer yang menutup koneksi idle setiap 300 detik.
Pool size 0 dan overflow -1 ditolak agar tidak sengaja menjadi tanpa batas.

Opsi `DB_POOL_MODE=null` menutup koneksi saat dikembalikan dan dapat mengurangi
retensi idle pada serverless, tetapi **tidak membatasi koneksi simultan** dan
menambah frekuensi login. Jangan menganggapnya solusi kuota global. Gunakan hanya
jika anggaran concurrency seluruh instance dikendalikan. Untuk trafik/instance
yang tidak bisa dibatasi, perlu kapasitas/pooling yang didukung provider atau
database development terpisah; perubahan layanan tersebut belum dilakukan.

## Tindakan manual untuk membebaskan kuota yang sudah penuh

1. Hentikan request/polling berulang. Tutup API/worker lokal yang dikenal secara
   normal melalui terminalnya; jangan menghentikan semua Python secara sembarang.
2. Disconnect web client Filess/Workbench/klien lain secara normal. Menutup tab
   belum tentu menutup koneksi pool backend web client.
3. Periksa deployment production dan preview Vercel serta trafiknya melalui
   dashboard. Pool lama di instance yang masih hidup tidak berubah hanya karena
   file lokal telah diperbaiki. Tidak ada instance/deployment yang diubah di sini.
4. Gunakan halaman koneksi provider secara read-only atau hubungi dukungan Filess
   untuk melihat pemilik, jumlah, umur, status idle dan transaksi koneksi akun.
   Saat login aplikasi ditolak, pemeriksaan mungkin memerlukan administrator
   provider. Minta identifikasi terlebih dahulu.
5. Tunggu disconnect normal atau idle timeout server bila memang ada koneksi
   idle. Durasi timeout aktual harus dicek ke provider; tidak ada janji selesai
   dalam 300 detik. Mereset counter pemakaian tidak mereset jumlah koneksi aktif.
   [Dokumentasi batas akun MySQL](https://dev.mysql.com/doc/refman/9.7/en/user-resources.html).

**Jangan klik Kill connections, membunuh transaksi, restart database, ALTER USER,
atau mengubah batas akun tanpa persetujuan khusus.** Jika langkah normal belum
membebaskan slot, sampaikan hasil pemeriksaan provider sebelum tindakan tersebut.
Implementasi pool lokal tidak dapat memutus koneksi existing milik Vercel/klien lain.

## Urutan menjalankan kembali

Gunakan kode perubahan ini secara lokal. Jangan menjalankan worker sebelum kuota
tersedia: startup worker biasa dapat mengambil job nyata. Langkah menjalankan
worker di bawah adalah handoff operasional, **tidak dijalankan dalam pengujian ini**.

1. Setelah slot dibebaskan, dari root backend:

   ```powershell
   .\.venv\Scripts\python.exe -m scripts.db_status --env-file .env.worker
   ```

   Harus exit 0 dan `status: ok`. Perintah ini menutup koneksi diagnostiknya.
   Bila masih 1226, kembali ke pemeriksaan provider; jangan loop/hammer database.
2. Pastikan anggaran seluruh instance cukup. Jalankan hanya satu API lokal tanpa
   reload/multi-worker selama pemulihan:

   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --workers 1 --env-file .env.worker
   ```

3. Setelah siap mengizinkan pemrosesan antrean existing, jalankan satu worker pada
   terminal berbeda:

   ```powershell
   .\.venv\Scripts\python.exe -m scripts.worker --env-file .env.worker
   ```

   Tetapkan `WORKER_CONCURRENCY=1`. Jangan menjalankan cleanup/worker tambahan dulu.
   `--env-file` worker menggunakan override: nilai dalam file terpilih mengalahkan
   environment shell untuk key yang sama. Pengguna mengelola file privat sendiri.
4. Indikator awal: DB status berhasil, API tidak menghasilkan error kapasitas,
   worker tidak lagi mengeluarkan `database_capacity`/`database_pool_timeout`.
   Ini belum membuktikan analisis end-to-end. Setelah mendapat izin tes job,
   periksa transisi queued → processing → completed/hasil analisis, tanpa
   memaksa retry/reset data existing. Job yang lease-nya habis tetap mengikuti
   kebijakan lease/attempt existing, bukan otomatis direset oleh perubahan ini.

`scripts.worker --check` bukan pengganti cek read-only: preflight existing juga
memeriksa storage (dapat membuat/menghapus marker). Karena itu tidak dijalankan
pada Filess/B2 produksi untuk tugas ini.

## Hasil pengujian

- Suite native: `python -m pytest -q --basetemp=.cache/pytest-db-connection-fix`
  → **402 passed, 18 skipped, 26 warnings**, 63,50 detik.
- Tes fokus pool/logging/env: **28 passed**, termasuk 25 tes baru dan 3 tes env
  worker existing. Bukti suite lengkap lokal: `.cache/db-connection-fix/tests.log`.
- Ruff fatal-error checks (`E9,F63,F7,F82`), format modul pool/diagnostik dan
  `scripts/worker.py`, OpenAPI snapshot serta `git diff --check` lulus.
- Suite mencakup tes lease/heartbeat/fencing existing dan migrasi SQLite disposable.
  18 tes MySQL dilewati karena URL database tes sengaja dikosongkan; tidak ada
  pengujian integrasi MySQL disposable pada mesin ini. Peringatan adalah
  deprecation TestClient/httpx dan konfigurasi Alembic existing.
- Pemeriksaan Filess setelah patch: exit 1, `database_capacity`, 1226,
  `max_user_connections`, limit 5. Pemulihan runtime belum terbukti.

Tidak ada worker nyata, cleanup produksi, migrasi Filess, pemutusan koneksi atau
modifikasi limit yang dilakukan. Tes yang membuat job/cleanup memakai fixture
SQLite/media sementara, tidak menggunakan antrean Filess atau B2 existing.
