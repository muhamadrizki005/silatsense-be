# Verifikasi implementasi B2 — 6 November 2026

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

## Yang belum diverifikasi pada layanan asli

CORS browser FE, migrasi MySQL online, deploy API Vercel, player video FE dan host
worker/cleanup belum diuji dari implementasi ini. Suite otomatis tetap memakai
layanan ber-versi dalam memori dan key dummy; smoke test bucket asli di atas
melengkapi pengujian itu.

Environment `.env` privat diisi pengguna; kode frontend tidak diubah. Lanjutkan
aktivasi deployment dan integrasi FE sesuai [panduan B2](b2-storage.md).
Lulus tes lokal tidak berarti deployment yang sudah ada otomatis diperbarui.
