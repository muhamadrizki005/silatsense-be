# Fase 2 — profil, katalog dan keamanan akun

> Pembaruan 19 Oktober 2026: endpoint/schema HTTP prototype sudah dihapus.
> Rujukan kompatibilitas lama di catatan fase di bawah bersifat historis.
> Kontrak aktif dan pemetaan pengganti: [route-cleanup.md](route-cleanup.md).

Status 17 Oktober 2026: kode, migrasi `0003`, schema OpenAPI dan tes tersedia.
Database development belum dimigrasi; `.env` tidak diubah. FE/prototype tetap
read-only. Semua endpoint berada setelah `/api/v1`, memakai Bearer, role yang
sesuai, `Cache-Control: no-store`, dan `X-Request-ID`.

## Endpoint dan contoh HTTP

Contoh memakai placeholder variabel lokal, bukan secret atau data pengguna.
`baseUrl` misalnya `http://localhost:8001/api/v1` setelah API dijalankan.

```http
GET {{baseUrl}}/member/profile
Authorization: Bearer {{memberAccessToken}}

PATCH {{baseUrl}}/member/profile
Authorization: Bearer {{memberAccessToken}}
Content-Type: application/json

{"fullName":"Nama Member","division":"UKM Silat"}
```

Respons 200 profil Member memuat id string, role, fullName, npm/email nullable,
emailVerifiedAt, division, title, belt/beltTarget, passwordChangedAt, coach,
createdAt UTC `Z`, dan statistics. NPM/email/role/sabuk/identity tidak writable
melalui PATCH. PATCH `{}` atau fullName null ditolak; division null menghapus
divisi. Role Coach memakai GET/PATCH `/coach/profile`, boleh mengubah title
nullable juga. Metadata admin belum tersedia tetap null; Coach statistics null
sampai Fase 6, bukan total semua Member. Statistik Member hanya sesi hasilnya
sendiri, average dikelompokkan versi yang lengkap; legacy tanpa featureVersion
tidak diberi versi tebakan. Durasi legacy tidak diketahui (sampleCount 0).

```http
PATCH {{baseUrl}}/member/password
Authorization: Bearer {{memberAccessToken}}
Content-Type: application/json

{"currentPassword":"{{currentPassword}}","newPassword":"{{newPassword}}"}
```

Coach menggunakan `/coach/password`, service dan kebijakan sama. Password
8–128 karakter, tidak di-trim. Password lama salah → 401
`invalid_current_password`, password baru identik → 422 `password_unchanged`;
keduanya tidak mencabut sesi. Sukses → **204 tanpa body**, refresh cookie
dihapus, semua refresh token dicabut dan authVersion naik dalam satu transaksi;
seluruh access tokens lama ditolak segera. Login ulang memakai password baru.
Client jangan retry password change otomatis tanpa mempertimbangkan hasil.

```http
GET {{baseUrl}}/member/training-modules
Authorization: Bearer {{memberAccessToken}}

GET {{baseUrl}}/member/training-prep/kuda-kuda
Authorization: Bearer {{memberAccessToken}}

GET {{baseUrl}}/member/record-config/kuda-kuda
Authorization: Bearer {{memberAccessToken}}
```

Catalog → `{modules,statistics}`. Empat kategori seeded berurutan kuda-kuda,
pukulan, tangkisan, tendangan; module nonaktif tidak disajikan. Seed idempotent
menambahkan kategori/urutan tanpa mengaktifkan ulang atau menimpa panduan/nama
yang telah dikurasi. Prep → `{module,checklist,guides}`. Belum ada sumber panduan
latihan baru yang disahkan, sehingga checklist/guides kosong; record-config
memberi batas nyata dari settings dan recommendedDurationSeconds null bila
belum ditetapkan. Tidak ada data kamera/deviceId atau skor kalibrasi buatan.

Capability mengambil referensi aktif yang file/metadata/feature version valid,
bukan empat boolean hardcode. JSON rusak, debug partial, path di luar root,
statistik nonfinite atau kurang delapan fitur dengan IQR usable dilewati.
Tanpa referensi valid: scoringAvailable false, reason reference_not_ready,
referenceVersions [], repetitionCountingAvailable false. Pukulan/tendangan
belum memiliki referensi tambahan. ScoringAvailable bukan jaminan setiap video
dapat dinilai atau klaim akurasi model.

Config mengirim MP4/MOV/WebM, default 100 MiB/60 detik dan retentionSeconds
86400 sesuai kontrak upload **Fase 3–4**. Angka retensi di config bukan bukti
endpoint `/evaluations` prototype sekarang menyimpan video: prototype tetap
sinkron dan menghapus video. Endpoint sesi/media/worker belum tersedia.

Error domain contoh (requestId dihasilkan server):

```json
{
  "detail": "Kategori gerakan tidak tersedia.",
  "code": "not_found",
  "requestId": "<request-id>"
}
```

Validation domain → 422 `validation_error` dengan errors field/message, tanpa
echo password/input. Error auth lama tetap detail string/array; schema DTO auth
tetap user/accessToken/expiresIn. Swagger runtime menampilkan endpoint, schema,
contoh input dan error Fase 2 di `/docs`; tidak perlu snapshot OpenAPI yang
mengklaim endpoint Fase 3–7 sudah ada.

## Migrasi dan menjalankan

`0003` additive: users auth_version/password_changed_at/email_verified_at,
refresh_tokens auth_version, member_profiles/coach_profiles, metadata movements.
Version legacy dibackfill 0, metadata yang tidak diketahui null. Hasil/issues/
notes, ID, hash password, identity dan refresh expiry lama dipertahankan.
Email existing tidak otomatis diverifikasi. `0001` dan `0002` tidak diubah.

**Verifikasi target koneksi dulu.** `.env` native saat audit masih
127.0.0.1:13307/user silatsense, bukan root@localhost:3306/silatsense yang
disepakati. Jangan menjalankan perintah berikut terhadap database aplikasi lain.
Setelah konfigurasi target development yang benar disiapkan secara lokal:

```powershell
.venv/Scripts/alembic.exe upgrade head
.venv/Scripts/alembic.exe check
.venv/Scripts/python.exe -m scripts.seed
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Compose opsional memerlukan rebuild agar schema/kode baru masuk image; startup
existing menjalankan migration/seed. Tidak ada perubahan `.env` atau provisioning
development pada pekerjaan Fase 2 ini. Docker yang dipakai untuk validasi hanya
container disposable khusus tes, tanpa volume/data development.

## Bukti pengujian aktual

- Regresi awal setelah implementasi: **31 passed**, seluruh auth/prototype lama.
- Suite SQLite terisolasi: **69 passed, 4 skipped, 9 warnings in 8.12s**.
  Empat skip adalah race tests yang memerlukan row lock MySQL.
- Suite API/security terhadap MySQL 8.4 disposable:
  **73 passed, 9 warnings in 85.85s**. Tes migrasi pada run ini masih SQLite.
- Migrasi diuji tambahan pada schema MySQL disposable terpisah:
  **2 passed, 9 warnings in 2.62s**. Upgrade database kosong; upgrade 0002
  dengan akun NPM/email, refresh token, evaluation dan note existing;
  downgrade 0003→0002 lalu upgrade lagi; `alembic check` bersih.
- Warning berasal dari deprecation httpx/TestClient dan Alembic path_separator;
  tidak disembunyikan. Tidak ada hasil benchmark atau inference video baru.

Perintah SQLite (terminal tes khusus):

```powershell
$env:DATABASE_URL = 'sqlite://'
$env:TEST_DATABASE_URL = ''
$env:MIGRATION_TEST_DATABASE_URL = ''
$env:TEMP = 'C:\Projek Software\silatsense-be\.cache'
$env:TMP = $env:TEMP
.venv/Scripts/python.exe -m pytest -q
```

Perintah MySQL memakai dua URL lokal di terminal tes khusus, bukan `.env`:
TEST_DATABASE_URL untuk `silatsense_phase2_test`, MIGRATION_TEST_DATABASE_URL
untuk schema **berbeda dan kosong** `silatsense_phase2_migration_test`, keduanya
hanya pada container disposable port 13308. Jangan memakai database development;
fixture tes create/drop tabel. Jalankan suite atau tes migrasi dengan:

```powershell
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m pytest tests/test_migrations.py -q
```

Cakupan baru: profile NPM-only, whitelist/atomic validation/null, isolasi role,
error/UTC/cache, password salah/identik, semua sesi dicabut vs user lain tetap
aktif, JWT legacy dan authVersion invalid, katalog/capability/source/seed,
statistik owner/versi, OpenAPI. Race MySQL membuktikan satu refresh winner,
refresh→password dan password→refresh tidak menghidupkan token lama, serta
login password lama tidak menerbitkan token setelah pergantian password.

## Berikutnya

Fase 3: training sessions, upload persisten, storage privat, antrean MySQL,
worker/lease/fencing/idempotensi. Fase 4: evaluasi baru dan retensi/playback.
Binaan/review Fase 6; linking/verifikasi email/reset dan integrasi FE Fase 7.
Pembatasan Coach prototype berdasarkan binaan **belum tersedia**; endpoint baru
profil Coach hanya menampilkan akun sendiri, tidak menambah akses global baru.
