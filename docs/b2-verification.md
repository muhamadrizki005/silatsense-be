# Verifikasi implementasi B2 — 6 November 2026

Audit lanjutan deployment: [46 endpoint melalui 116 request HTTP](vercel-api-audit-2026-11-06.md).
Audit menemukan konfigurasi refresh cookie Secure=false; detail alur, email,
fixture dan keterbatasan tercatat pada laporan tersebut.

Branch pekerjaan: `feat/b2-object-storage`, dibuat dari checkout aktif
`codex/ai-coach-reference-comparison`. Tidak di-merge, di-commit atau di-push
oleh pekerjaan ini. Perubahan lokal yang sudah ada pada README, panduan Vercel
dan manifest dependency dipertahankan.

## Hasil aktual

Regresi awal terhadap suite existing setelah fondasi perubahan:

```text
.cache/b2-venv/Scripts/python.exe -m pytest -q --basetemp=.cache/b2-tests
336 passed, 18 skipped, 19 warnings in 54.85s
```

Ini bukan baseline checkout bersih sebelum perubahan. Percobaan awal memakai
`.venv/Scripts/python.exe` dari sandbox tidak bisa mengakses interpreter Python
asal. Lingkungan `.cache/b2-venv` disiapkan dengan akses interpreter native dan
memakai paket proyek yang sudah tersedia; tidak ada Docker.

Verifikasi akhir setelah seluruh perubahan kode dan tes:

```text
.cache/b2-venv/Scripts/python.exe -m pytest -q --basetemp=.cache/b2-final-verified --tb=short
353 passed, 18 skipped, 26 warnings in 56.50s

.cache/b2-venv/Scripts/python.exe -m scripts.export_openapi --check
OpenAPI snapshot matches application
```

Ruff critical rules `E9,F63,F7,F82` terhadap `app scripts tests alembic` lulus.
Format check 21 modul (cakupan CI Fase 7 dan modul baru B2/probe) lulus.
`git diff --check` lulus; Git hanya mengingatkan normalisasi LF/CRLF Windows.

Database API tes adalah SQLite in-memory disposable. Tes migrasi menggunakan
file SQLite terisolasi dalam direktori sementara tes, termasuk `alembic check`,
upgrade/downgrade dan preservasi media existing dari revisi 0007. Tidak ada
migrasi atau perubahan database development/Filess dari pekerjaan ini.
18 tes MySQL khusus dilewati; ini tidak membuktikan migrasi MySQL 5.7 online.

26 warning adalah deprecation Starlette TestClient dan konfigurasi Alembic
`path_separator` existing, bukan kegagalan tes.

SDK yang diuji: boto3/botocore 1.40.70, s3transfer 0.14.0, jmespath 1.0.1,
urllib3 2.5.0. Instalasi resolver mengalami kendala jaringan; wheel resmi PyPI
diunduh bertahap, SHA256 diverifikasi terhadap metadata PyPI, lalu diekstrak ke
virtualenv disposable. Ini **bukan** pengujian clean install semua versi lock
di Linux maupun pengukuran ulang bundle Vercel.

## Cakupan tes baru

- SDK boto3 asli menandatangani PUT dengan Content-Length, Content-Type dan TTL.
- Alur init/complete, idempotensi, konflik payload, kuota dan kepemilikan upload.
- Signed PUT hanya untuk staging; penyalinan versi final mencegah overwrite sesi.
- Ukuran/tipe tidak cocok, file belum diunggah dan storage outage ditangani.
- Worker mengunduh file, memeriksa SHA256, melakukan probe video nyata dan
  memperbarui metadata sebelum playback; file invalid tidak mencapai inference.
- Range B2, respons maksimum 4 MiB, deadline tepat, cleanup semua versi dan retry.
- Readiness mengecek operasi write/read/delete storage dengan layanan simulasi.
- Migrasi mempertahankan data media dan menolak downgrade yang memerlukan angka
  dummy untuk metadata belum tersedia.

## Smoke test bucket B2 asli

Setelah kredensial disimpan di `.env`, smoke test melalui adapter dan SDK asli
berhasil dengan status `ok`: signed PUT, HEAD/VersionId, copy versi tertentu,
GET Range, download dengan verifikasi SHA256, serta penghapusan seluruh versi
kedua objek uji. Objek uji memakai nama UUID acak dan sudah dihapus. Secret dan
URL bertanda tangan tidak dicetak. `STORAGE_ADAPTER` tetap `local`; database
tidak diubah. Ini menguji object storage dengan payload kecil, bukan analisis video.

## Integrasi Vercel dan MySQL 5.7 nyata — 6 November 2026

Database Filess sudah dimigrasikan dari 0007 ke 0008 dengan backup tabel terdampak
di `.cache/b2-migration-20261106T095737Z`; `alembic check` lulus. Deployment Vercel
mengembalikan readiness 200 dengan database/storage/workerConfiguration `ok`.

Smoke test HTTP nyata menggunakan akun uji dan video sintetis satu detik:

- POST auth/sign-up → 201.
- POST member/uploads → 201, PUT langsung ke B2 → 200.
- POST complete → 202; replay complete mengembalikan sessionId yang sama.
- GET sesi → queued; worker native satu iterasi → completed.
- GET evaluasi dan pose → 200; GET video Range → 206, byte sesuai file asal.
- DELETE sesi → 204; objek staging/final uji dihapus; sesi auth uji logout.

Hasil analisis `reference_not_ready`, score null: file sintetis tidak berisi
gerakan manusia dan database belum memiliki referensi penilaian aktif. Ini bukti
alur API/storage/worker, bukan validasi akurasi model. Akun uji tetap tercatat
karena API tidak menyediakan penghapusan akun; sesi latihan ditandai dihapus.
Laporan tanpa token/secret ada di `.cache/b2-live-e2e/report.json`.

Percobaan pertama menemukan error MySQL 1064 saat claim job: kode memakai
`FOR UPDATE SKIP LOCKED` pada MySQL 5.7. Perbaikan di branch
`fix/mysql57-worker-claim` mempertahankan SKIP LOCKED pada MySQL >=8.0.1 dan
MariaDB >=10.6, memakai FOR UPDATE biasa pada versi lama. Klaim tetap berada
dalam transaksi dan lease/fencing tidak berubah; worker lama menunggu row lock,
bukan melewati job yang terkunci. Tidak ada migrasi database tambahan.

Lease mulai dihitung ulang setelah row lock diperoleh, sehingga waktu menunggu
tidak memotong masa lease atau melewatkan pengecekan expiry media terbaru.
Regresi akhir perbaikan ini:

```text
.cache/b2-venv/Scripts/python.exe -m pytest -q --basetemp=.cache/mysql57-worker-final --tb=short
362 passed, 18 skipped, 26 warnings in 52.92s
```

Ruff critical rules, format tes baru, `git diff --check` dan snapshot OpenAPI
lulus. 18 skip tetap tes MySQL disposable; smoke test Vercel/Filess asli di atas
dijalankan terpisah. Perbaikan belum di-commit/push/merge oleh pengujian ini.

## Yang belum diverifikasi pada layanan asli

CORS browser FE dan player video FE belum diuji. Worker native berhasil dijalankan
satu iterasi untuk sesi uji, tetapi belum ada proses worker/cleanup persisten yang
disiapkan oleh smoke test ini. Tes HTTP non-browser tidak membuktikan CORS browser.
Tes MySQL nyata ini mencakup satu worker, bukan stress test banyak worker paralel.
Suite otomatis tetap memakai layanan ber-versi dalam memori dan key dummy; smoke
test bucket/Vercel asli di atas melengkapi pengujian itu.

Environment `.env` privat diisi pengguna; kode frontend tidak diubah. Lanjutkan
aktivasi deployment dan integrasi FE sesuai [panduan B2](b2-storage.md).
Lulus tes lokal tidak berarti deployment yang sudah ada otomatis diperbarui.
