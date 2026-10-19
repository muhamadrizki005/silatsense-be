# Penghapusan route dan schema prototype

Pada 19 Oktober 2026, pemilik proyek menyetujui penghapusan route/schema HTTP
prototype yang fungsinya sudah tersedia melalui kontrak FE sekarang. Prefix
`/api/v1` dipertahankan. Ini penghapusan endpoint, bukan redirect/alias tersembunyi.

Audit kode FE lokal menemukan pemanggilan sign-up/sign-in/session/refresh-session;
alias auth lama tidak digunakan. Tes dan script backend yang masih memakai alias
lama dipindahkan ke kontrak sekarang. Tidak ada audit terhadap konsumen eksternal
di luar kedua repository lokal.

Tautan halaman FE `/coach/members` tetap sah sebagai navigasi UI. Komentar TODO
di data dummy Coach masih menyebut endpoint lama; integrasi berikutnya memakai
`/coach/roster`. Audit tidak menemukan fetch aktif ke endpoint prototype tersebut.

## Pemetaan endpoint

Semua path berikut relatif terhadap `/api/v1`. Endpoint yang dihapus menghasilkan
404; pemanggil lama harus beralih secara eksplisit.

| Endpoint dihapus | Kontrak pengganti |
| --- | --- |
| POST `/auth/register` | POST `/auth/sign-up`: fullName, identifier, password |
| POST `/auth/login` | POST `/auth/sign-in`: identifier, password, rememberMe |
| GET `/auth/me` | GET `/auth/session` |
| POST `/auth/refresh` | POST `/auth/refresh-session` |
| GET `/profile` | GET `/member/profile` atau `/coach/profile` sesuai role |
| PATCH `/profile` | PATCH profil per role: fullName/division dan title untuk Coach |
| GET `/movements` | GET `/member/training-modules` |
| POST `/evaluations` | POST `/member/sessions`: multipart movementSlug/video, idempotensi, respons 202; worker memproses terpisah |
| GET `/evaluations` | GET `/member/history`: cursor, items/nextCursor |
| GET `/evaluations/{evaluationId}` | GET `/member/sessions/{sessionId}/evaluation` atau detail `/member/history/{sessionId}`; Coach memakai `/coach/sessions/{sessionId}` |
| GET `/coach/members` | GET `/coach/roster` |
| GET `/coach/members/{memberId}` | GET `/coach/roster/{memberId}` |
| GET `/coach/members/{memberId}/evaluations` | GET `/coach/roster/{memberId}/sessions` |
| POST `/coach/evaluations/{evaluationId}/notes` | PUT draft `/coach/sessions/{sessionId}/feedback-draft`, kemudian POST `/reviews` dengan versi/idempotensi |

ID evaluasi dan sesi berbeda; jangan mengganti nama variable saja ketika
memigrasikan pemanggil. Slug publik adalah kuda-kuda, dipetakan ke kuda_kuda hanya
di penyimpanan/analyzer. Output auth tunggal memakai accessToken/expiresIn/user,
ID string, dan role member/coach.

## Kode dan data

- Router campuran `app/api/routes.py` dihapus; auth yang aktif dipindah ke
  `app/api/auth.py`. Router domain yang sudah terpisah tetap dipakai.
- Seluruh DTO API prototype dalam `app/schemas/api.py` dihapus. Tidak ada lagi
  Register, Credentials, TokenOut, UserOut, ProfilePatch, MovementOut, NoteCreate
  atau NoteOut lama.
- Tiga validator payload analyzer yang masih dipakai worker dipindahkan ke
  `app/schemas/analysis.py`. Ini kontrak internal snake_case; DTO HTTP tetap
  camelCase di schemas auth/domain/results/coaching/reviews. Validator ini bukan
  endpoint atau schema publik duplikat.
- Jalur inference sinkron `app/services/uploads.py`, serializer prototype,
  pagination repository lama dan helper penyimpan sinkron yang tidak dipakai
  dihapus. Whitelist video dipakai bersama dari `app/services/video.py`.
- Pembuatan fixture hasil historis berada di tests/helpers.py, bukan metode
  produksi yang tidak punya pemanggil aplikasi.
- Script validasi lokal memakai signup→upload→worker→hasil→histori→review.
  Wajib --video dan database *_test. Tidak membutuhkan dataset privat dan tidak
  menyimpan kredensial/token ke disk.
- OpenAPI dan Postman dibangun ulang: 44 operasi HTTP, 53 request Postman.
  Folder kompatibilitas prototype dan variable kredensial legacy dihapus.

Model database, migrasi 0001–0007, .env, frontend, data pengguna dan artifact
intelligence tidak diubah. Evaluation/CoachNote historis tetap tersimpan dan
dibaca melalui detail/history sekarang (termasuk legacyNotes), tanpa membuka
kembali jalur penulisan prototype. Health/live/ready tetap ada karena memiliki
fungsi diagnosis yang berbeda.

## Pengujian

Baseline native sebelum perubahan:

```powershell
$env:TEST_DATABASE_URL = ''
$env:MIGRATION_TEST_DATABASE_URL = ''
.venv/Scripts/python.exe -u -m pytest -q --basetemp=.cache/route-cleanup-baseline-native --tb=short
```

Hasil aktual: **204 passed, 18 skipped, 19 warnings, 49.16 detik**. SQLite in-memory
dan file migrasi sementara; tidak memakai database development. Percobaan awal
di sandbox tidak mengeluarkan hasil dan dihentikan; angka ini dari pengulangan
native yang selesai.

Sesudah perubahan, dengan isolasi sama:

```powershell
.venv/Scripts/python.exe -u -m pytest -q --basetemp=.cache/route-cleanup-current-2 --tb=short
```

Hasil aktual: **212 passed, 18 skipped, 19 warnings, 48.01 detik**. Tes khusus
MySQL dilewati pada jalur SQLite. Tambahan regresi memastikan seluruh 14 operasi
lama menghasilkan 404 dan tidak ada DTO prototype di OpenAPI. Tes fitur memakai
kontrak baru, termasuk hasil nullable, scope Coach, revisi review dan retensi audit.

Suite MySQL native penuh: **230 passed, 19 warnings, 575.29 detik (9:35)**.
Orkestrasi lokal `.venv/Scripts/python.exe -u .cache/run_route_mysql.py` membuat
dua schema baru bernama `silatsense_route_api_<acak>_test` dan
`silatsense_route_migration_<acak>_test`, lalu menjalankan:

```powershell
.venv/Scripts/python.exe -u -m pytest -q --tb=short --basetemp=.cache/route-cleanup-mysql
```

TEST_DATABASE_URL dan MIGRATION_TEST_DATABASE_URL hanya diteruskan ke proses tes;
MAIL_ADAPTER=disabled. File .env tidak ditulis dan schema development silatsense
tidak menjadi target tes. Kedua schema tes dihapus pada blok finally setelah
selesai. Docker tidak dijalankan. Suite ini mencakup locking/refresh race,
recovery, migrasi, worker, akses media, assignment dan transaksi review.

Sesudah memperketat assertion ketiadaan route bertemplate di OpenAPI, regresi
kontrak SQLite dijalankan lagi: **17 passed, 1 warning, 2.32 detik** melalui
`pytest -q tests/test_api.py --basetemp=.cache/route-cleanup-contract-final --tb=short`.
Tidak ada perubahan kode aplikasi setelah suite penuh dimulai.

Pemeriksaan lain yang lulus:

- Ruff critical rules E9/F63/F7/F82; format/import untuk modul baru.
- `python -m scripts.export_openapi --check`: snapshot sesuai aplikasi.
- Referensi variable, field JSON dan cakupan collection terhadap 44/44 operasi.
- `alembic check` pada MySQL development: No new upgrade operations detected.

Peringatan yang tersisa berasal dari deprecation TestClient/httpx dan konfigurasi
path_separator Alembic. Pengujian ini tidak membuktikan validitas ilmiah skor AI.

## Perbaikan lanjutan: origin Swagger

Login melalui Swagger awalnya ditolak karena Origin API (localhost:8001) berbeda
dari FRONTEND_ORIGIN (localhost:3000). check_origin sekarang menerima origin FE
yang dikonfigurasi atau origin request API sendiri. Tidak ada wildcard; origin
asing, port/skema berbeda dan literal null tetap ditolak. Postman tanpa Origin
tetap didukung. Runtime API perlu direstart untuk memuat perubahan.

Regresi terfokus SQLite native: **54 passed, 1 warning, 7.18 detik**, melalui
`pytest -q tests/test_auth.py tests/test_api.py tests/test_recovery.py
--basetemp=.cache/swagger-origin-tests --tb=short`. Tes mencakup origin sah/asing,
login→refresh→logout melalui origin Swagger, route yang sudah dihapus, dan
recovery dengan adapter tes. Database development, .env dan SMTP nyata tidak
diubah/dipakai untuk pengiriman pada pengujian ini. Suite MySQL di atas adalah
bukti pembersihan route sebelum perbaikan origin; tidak diulang untuk perubahan ini.
