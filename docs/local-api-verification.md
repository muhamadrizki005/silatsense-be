# Verifikasi API lokal — 19 Oktober 2026

Seluruh **44 operasi HTTP pada OpenAPI** menerima setidaknya satu respons sukses
dalam gabungan pengujian MySQL terisolasi dan dua tes tambahan. Status negatif
di tabel merupakan skenario error yang memang diuji, bukan kegagalan suite.
Ini adalah cakupan operasi/respons, bukan klaim cakupan seluruh baris kode.

## Hasil aktual

| Pengujian | Hasil |
| --- | --- |
| Suite lengkap native MySQL | **238 passed**, 18 warnings, 567.55 detik |
| Dua tes tambahan native MySQL | **2 passed**, 6.49 detik |
| Suite lengkap SQLite | **220 passed, 18 skipped**, 18 warnings, 60.45 detik |
| Dua tes tambahan SQLite | **2 passed**, 0.63 detik |
| Cakupan operasi HTTP gabungan | **44/44** memiliki respons sukses |
| HTTP Uvicorn + worker native | **Lulus**, database/storage readiness 200 |
| Pemeriksaan database sementara setelah tes | **0 tersisa** |
| Ruff critical rules dan git diff --check | **Lulus** |

Suite lengkap dikoleksi sebelum penambahan dua tes; keduanya diuji terpisah
pada SQLite dan MySQL. Delapan belas skip hanya ada pada SQLite karena
skenario tersebut memerlukan semantik MySQL. Seluruh 238 tes pada jalur MySQL
berjalan tanpa skip. Warning Alembic mengenai `path_separator` dan warning
deprecation TestClient dari pencatat cakupan tidak membuat tes gagal.

## Perintah dan isolasi

Perintah dasar suite: `.venv/Scripts/python.exe -m pytest -q --tb=short`.
Audit memakai helper lokal `.cache/run_route_mysql.py` untuk membuat dua schema
baru dengan nama acak `silatsense_route_api_<acak>_test` dan
`silatsense_route_migration_<acak>_test`, meneruskan TEST_DATABASE_URL dan
MIGRATION_TEST_DATABASE_URL hanya ke proses tes, lalu menghapus kedua schema
dalam blok finally. DATABASE_URL proses suite adalah `sqlite://` agar tidak
ada koneksi implisit ke development; fixture API memakai MySQL tes eksplisit.
Schema migrasi terpisah dari schema API. Kredensial tidak dicetak.

Tes tambahan:

```powershell
.venv/Scripts/python.exe -m pytest -q tests/test_coaching.py::test_coach_pose_follows_active_assignment_and_preserves_member_result tests/test_operations.py::test_public_health_identifies_application
```

Helper `.cache/local_api_coverage.py` mencatat method, path dan status dari
TestClient, kemudian memetakannya ke operasi OpenAPI. Tidak mencatat body,
password, cookie atau token. Helper audit dan laporan JSON mentah berada di
direktori .cache yang diabaikan Git; helper tersebut bukan syarat runtime.

Tes HTTP terpisah menjalankan Uvicorn pada port loopback kosong, worker native,
dan cleanup --once menggunakan schema baru `silatsense_http_<acak>_test`, folder
media terisolasi dan MAIL_ADAPTER=disabled. Video sintetis hitam dua detik dibuat
melalui OpenCV. `scripts.validate_local` menguji sign-up, katalog, upload queued,
polling sampai completed, evaluasi, histori, draft dan published review Coach.
Worker menjalankan child inference MediaPipe nyata dengan model pose lokal.
Seluruh proses HTTP/worker tes dihentikan dan schema tes dihapus setelah selesai.

Recovery email menggunakan MemoryMailAdapter dan pengujian SMTP loopback.
Tidak ada email nyata dikirim. Tidak ada Docker, koneksi Filess atau request
Vercel pada audit lokal ini. Data/schema development dan .env tidak diubah.

## Tambahan tes

- Pose Coach: respons berisi landmark yang tersimpan, sama dengan milik Member;
  Coach yang tidak ditugaskan ditolak; transfer mencabut akses lama dan memberi
  akses ke Coach baru; pencabutan assignment menutup akses Coach.
- Health: respons publik mengidentifikasi aplikasi dan mode experimental.

Tidak ditemukan kebutuhan perubahan kode bisnis dalam pengujian ini.

## Batas kesimpulan

Keberhasilan lokal memerlukan dependency, MySQL, migrasi, seed katalog, storage
yang dapat ditulis, model pose dan worker yang tersedia. Hasil ini tidak
menyelesaikan storage/worker Vercel dan tidak membuktikan pengiriman SMTP Zoho
dari deployment. Video sintetis menguji alur sistem dan mempertahankan skor null
ketika referensi belum tersedia; ini bukan validasi akurasi teknik silat atau
standar penilaian IPSI. Bukan pengujian beban atau pembuktian semua kemungkinan
kombinasi input.

## Cakupan operasi HTTP

| Method | Path | Status teramati |
| --- | --- | --- |
| POST | `/api/v1/auth/sign-up` | 201, 403, 409, 422 |
| POST | `/api/v1/auth/sign-in` | 200, 401, 403, 422, 429 |
| GET | `/api/v1/auth/session` | 200, 401 |
| POST | `/api/v1/auth/refresh-session` | 200, 401, 403 |
| POST | `/api/v1/auth/logout` | 204, 403 |
| GET | `/api/v1/member/profile` | 200, 401, 403 |
| PATCH | `/api/v1/member/profile` | 200, 403, 422 |
| GET | `/api/v1/coach/profile` | 200, 403 |
| PATCH | `/api/v1/coach/profile` | 200 |
| PATCH | `/api/v1/member/password` | 204, 401, 403, 422 |
| PATCH | `/api/v1/coach/password` | 204 |
| GET | `/api/v1/member/training-modules` | 200, 403 |
| GET | `/api/v1/member/training-prep/{slug}` | 200, 404 |
| GET | `/api/v1/member/record-config/{slug}` | 200, 404 |
| POST | `/api/v1/member/sessions` | 202, 401, 404, 409, 413, 415, 422, 429, 500 |
| GET | `/api/v1/member/sessions/{session_id}` | 200, 401, 404 |
| DELETE | `/api/v1/member/sessions/{session_id}` | 204, 403, 404 |
| GET | `/api/v1/member/sessions/{session_id}/evaluation` | 200, 401, 404, 409 |
| GET | `/api/v1/member/sessions/{session_id}/pose` | 200, 401, 404, 409 |
| GET | `/api/v1/member/sessions/{session_id}/video` | 200, 206, 401, 403, 404, 410, 416 |
| POST | `/api/v1/member/sessions/{session_id}/acknowledge` | 200, 404, 409 |
| GET | `/api/v1/member/history` | 200, 401, 403, 422 |
| GET | `/api/v1/member/history/{session_id}` | 200, 401, 403, 404 |
| GET | `/api/v1/member/dashboard` | 200, 401, 403 |
| GET | `/api/v1/coach/overview` | 200 |
| GET | `/api/v1/coach/roster` | 200, 403, 422 |
| GET | `/api/v1/coach/roster/{member_id}` | 200, 404 |
| GET | `/api/v1/coach/roster/{member_id}/sessions` | 200, 404 |
| GET | `/api/v1/coach/sessions/{session_id}` | 200, 404 |
| GET | `/api/v1/coach/sessions/{session_id}/pose` | 200, 404 |
| GET | `/api/v1/coach/sessions/{session_id}/video` | 200, 206, 404 |
| PUT | `/api/v1/coach/sessions/{session_id}/feedback-draft` | 200, 404, 409, 422 |
| POST | `/api/v1/coach/sessions/{session_id}/reviews` | 201, 404, 409, 422, 500 |
| POST | `/api/v1/member/sessions/{session_id}/follow-ups` | 201, 404, 409 |
| PATCH | `/api/v1/member/follow-up-tasks/{task_id}` | 200, 404, 422 |
| POST | `/api/v1/auth/email-link/request` | 202, 401, 429 |
| POST | `/api/v1/auth/email-verification/request` | 202, 503 |
| POST | `/api/v1/auth/password-reset/request` | 202, 403 |
| POST | `/api/v1/auth/email-link/confirm` | 204, 422 |
| POST | `/api/v1/auth/email-verification/confirm` | 204, 422 |
| POST | `/api/v1/auth/password-reset/confirm` | 204, 422 |
| GET | `/health/live` | 200 |
| GET | `/health/ready` | 200, 503 |
| GET | `/health` | 200 |
