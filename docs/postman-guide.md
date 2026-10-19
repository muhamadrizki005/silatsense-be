# Pengujian backend SilatSense melalui Postman

Panduan lokal 19 Oktober 2026. Tidak memerlukan frontend atau Docker. Gunakan
Postman desktop, jalankan request satu per satu, dan ikuti urutannya. Collection
ini sengaja mencakup operasi yang mengubah akun, mengirim email, dan menghapus
sesi; jangan menjalankan seluruh collection sekaligus lewat Runner.

- [Collection siap impor](postman/SilatSense.postman_collection.json)
- [Environment kosong tanpa secret](postman/SilatSense.local.postman_environment.json)
- [Seluruh URL, method, header, body, dan respons sukses](postman/requests.md)
- [Kontrak API](api-contract.md), [snapshot OpenAPI](openapi.json)

## 1. Nyalakan MySQL dan periksa lingkungan

Buka PowerShell di root backend:

```powershell
cd "C:\Projek Software\silatsense-be"
Get-Service MySQL80
Test-Path .venv/Scripts/python.exe
```

MySQL harus Running dan Python virtual environment harus True. Jika MySQL
berhenti, nyalakan service MySQL80 melalui Windows Services. Nama service bisa
berbeda pada mesin lain. `.env` native pemilik proyek sudah dikonfigurasi ke
database `silatsense` di localhost:3306. Jangan menggantinya dengan contoh Docker.

Pada checkout yang belum memiliki dependencies:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-lock.txt
```

Pastikan DATABASE_URL menuju database development yang memang ingin diuji.
Registrasi/upload/review akan menyimpan data di sana. Setelah target benar:

```powershell
.venv/Scripts/alembic.exe current
.venv/Scripts/alembic.exe upgrade head
.venv/Scripts/alembic.exe check
```

Head kontrak ini adalah 0007. Development pengguna sebelumnya sudah dimigrasi;
upgrade head akan no-op bila sudah terbaru. Katalog empat gerakan sebelumnya
sudah diisi. Jika pada database baru katalog kosong, isi kategori saja:

```powershell
.venv/Scripts/python.exe -c "from app.db.session import SessionLocal; from app.repositories.training import seed_movements; db=SessionLocal(); seed_movements(db); db.commit(); db.close()"
```

Jangan menjalankan scripts.seed default hanya untuk mengisi katalog karena
perintah itu juga mendaftarkan profil referensi prototype.

## 2. Jalankan API, worker, dan cleanup

Terminal pertama, tetap di root backend:

```powershell
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --no-access-log
```

- Base API: `http://localhost:8001/api/v1`
- Swagger: `http://localhost:8001/docs`
- OpenAPI: `http://localhost:8001/openapi.json`
- Kesiapan: `http://localhost:8001/health/ready`

Jangan tutup terminal API. Gunakan hostname localhost secara konsisten pada
semua request Postman agar cookie refresh tetap berada pada host yang sama.
API_PORT di .env tidak otomatis menentukan port uvicorn native.

Terminal kedua, untuk tes video:

```powershell
cd "C:\Projek Software\silatsense-be"
Test-Path artifacts/pose/pose_landmarker_lite.task
.venv/Scripts/python.exe -m scripts.worker
```

Jika file model belum ada, sebelum worker jalankan:

```powershell
.venv/Scripts/python.exe -m scripts.download_pose_model
```

Terminal ketiga, untuk pembersihan media berkala:

```powershell
cd "C:\Projek Software\silatsense-be"
.venv/Scripts/python.exe -m scripts.cleanup_media
```

API + MySQL cukup untuk auth/profil. Worker diperlukan untuk memproses upload.
Cleanup menghapus file yang masa retensinya sudah berakhir; tidak memperpanjang
akses media. Hentikan setiap proses dengan Ctrl+C di terminalnya; tidak perlu
menghentikan service MySQL.

## 3. Impor dan isi environment Postman

Import dua file JSON yang ditautkan di atas. Pilih environment **SilatSense Local
- isi secara privat**. Gunakan request dari collection, bukan mengimpor environment
sebagai collection. Jika tidak memakai collection, salin request lengkap dari
[referensi request](postman/requests.md).

Isi variable secara lokal:

| Variable | Isi |
| --- | --- |
| host | `http://localhost:8001` |
| baseUrl | `http://localhost:8001/api/v1` |
| memberIdentifier | NPM uji 8–12 digit yang belum terdaftar, misalnya `227006104` |
| memberPassword | Password akun uji pilihanmu, 8–128 karakter |
| memberNewPassword | Password baru berbeda, untuk tes keamanan di akhir |
| memberEmail | Alamat email milikmu yang bisa menerima pesan, untuk tes recovery |
| coachIdentifier | Email akun Coach yang dibuat lewat CLI pada langkah 6 |
| coachPassword / coachNewPassword | Password Coach dan password penggantinya |
| movementSlug | `kuda-kuda` (atau pukulan/tangkisan/tendangan) |
| uploadKey | UUID unik untuk upload pertama |
| publishKey | UUID lain untuk publikasi review |
| retryKey / retryUploadKey | UUID berbeda untuk intent retry dan upload retry |
| reviewRevision | `0` untuk publikasi pertama |

Buat UUID sesuai kebutuhan dari PowerShell:

```powershell
[guid]::NewGuid().ToString()
```

Satu operasi logis memakai satu key tetap. Retry request dengan payload yang
sama memakai key yang sama; operasi baru memakai key baru. Jangan memakai
variable UUID dinamis yang berubah setiap Send ketika menguji replay.

Biarkan token, ID, cursor, draftVersion, dan taskId dikelola scripts respons
collection. Recovery token diisi manual dari email. Template environment
tidak menyimpan password/token nyata. Jangan membagikan export environment yang
sudah terisi atau menyinkronkan secret ke workspace bersama.

Tidak perlu menambahkan Origin pada Postman. Jika menambahkannya, gunakan
FRONTEND_ORIGIN backend (default http://localhost:3000) atau origin API sendiri
(http://localhost:8001 saat memakai URL localhost). Swagger memakai origin API.
Origin lain tetap ditolak. Biarkan cookie jar
aktif; refresh_token HttpOnly tetap bisa dikelola Postman. Konfigurasi lokal HTTP
memerlukan COOKIE_SECURE=false; jangan menonaktifkan Secure pada deployment HTTPS.

## 4. Tes kesiapan, auth, profil dan katalog

1. Folder 01: GET health/live dan health/ready harus 200. Ready memeriksa database,
   revision migrasi dan storage, bukan memastikan SMTP/model/worker sehat.
2. Folder 02: registrasi sekali → 201. Jika identifier sudah ada, gunakan login
   atau pilih identifier uji baru. Public signup hanya membuat Member.
3. Login → 200. Scripts menyimpan memberToken dan memberId dari accessToken/user.id.
4. GET auth/session → 200 dengan role member.
5. POST refresh-session, Body none, tanpa Bearer → 200. Postman mengirim cookie
   refresh_token dan menerima cookie pengganti. Scripts mengganti memberToken.
6. Folder 03: GET profil, PATCH profil, GET profil lagi. Pastikan nama/division
   tersimpan. Jangan mengirim role, NPM, email, sabuk atau cameraDeviceId di PATCH.
7. GET katalog, persiapan dan record-config. Untuk API baru slug adalah kuda-kuda,
   bukan kuda_kuda. Panduan bisa kosong jika belum dikurasi.
8. Dashboard/history pada akun baru valid bila count 0, items [], lastSession null
   dan rata-rata belum tersedia. Simpan baseline sebelum upload.

Untuk mengetik manual, Authorization → Bearer Token → `{{memberToken}}`. Jangan
menulis kata Bearer lagi di kolom Token. Untuk JSON gunakan Body → raw → JSON.
GET, refresh, logout, acknowledge dan DELETE tidak memerlukan body.

## 5. Upload, status, evaluasi, video dan histori

Gunakan video uji milik sendiri dengan badan terlihat jelas. Ambil batas aktif
dari record-config; default maksimum 100 MiB, 60 detik, MP4/MOV/WebM. Ekstensi saja
tidak cukup: backend memeriksa file dengan decoder.

1. Folder 04 upload: Body → form-data. movementSlug tipe Text, video tipe File.
   Klik pilihan file dan pilih video lokal. Header Idempotency-Key = {{uploadKey}}.
   Jangan pasang Content-Type manual karena Postman harus membuat boundary.
2. Send → 202, berisi sessionId, statusUrl, evaluationUrl dan uploadedAt. Scripts
   menyimpan sessionId. 202 berarti diterima antrean, bukan analisis selesai.
3. GET status berulang manual sekitar dua detik sampai completed/failed. Jangan
   terus upload saat queued. Worker mati membuat antrean tetap queued. Jika gagal,
   baca error.code/detail dan log worker; hasil gagal bukan completed.
4. Setelah completed, GET evaluation dan pose → 200. MediaPipe/model pose bukan
   model penilaian silat yang telah ditrain. Tanpa referensi, score null dan
   analysisStatus reference_not_ready adalah hasil yang valid, bukan API rusak.
   Video tanpa pose juga bisa menghasilkan pose null beserta alasan.
5. GET video → 200; simpan response ke file jika Postman tidak memutar video.
   GET video dengan Range bytes=0-1023 → 206 dan Content-Range (untuk file cukup
   besar). Jangan mengharapkan JSON dari endpoint video.
6. POST acknowledge → 200. Mengulangnya mempertahankan timestamp pertama; hasil
   evaluasi sudah tersimpan sebelum acknowledge.
7. GET history detail dan dashboard lagi. Sesi selesai masuk statistik yang sesuai.
8. Pagination: gunakan nextCursor hanya jika tidak null; masukkan melalui tab
   Params agar encoding ditangani Postman. Cursor terikat user/filter. Pertahankan
   filter yang sama dari halaman pertama; default limit 20/maksimum 100.

Filter history yang didukung: movementSlug, processingStatus, reviewStatus, from,
to. Contoh from=2026-10-19T00:00:00Z, to=2026-10-20T00:00:00Z; awal inklusif,
akhir eksklusif. Pilih tanggal yang sesuai waktu sesi. Jangan mengisi cursor
kosong/null atau menyalin cursor dari user/filter lain.

Media privat berlaku 24 jam sejak upload selesai. Sesudah itu video → 410 meskipun
file belum dibersihkan; hasil dan review tetap tersedia. Tidak perlu menunggu
24 jam untuk menuntaskan smoke test ini; expiry tepat tenggat memerlukan pengujian
terkontrol, bukan mengubah jam mesin atau database development.

## 6. Buat Coach dan tugaskan Member lewat CLI

Lewati pembuatan jika sudah ada akun Coach khusus uji. Jangan mengubah role Member
langsung lewat database. CLI seed existing juga mengimpor reference profiles;
untuk membuat Coach tanpa mendaftarkan profil prototype, arahkan REFERENCE_ROOT
sementara ke folder kosong unik hanya di terminal CLI tersebut:

```powershell
cd "C:\Projek Software\silatsense-be"
$postmanReferenceBefore = [Environment]::GetEnvironmentVariable('REFERENCE_ROOT', 'Process')
$postmanEmptyReference = Join-Path (Get-Location) ('.cache/postman-empty-' + [guid]::NewGuid().ToString())
New-Item -ItemType Directory -Path $postmanEmptyReference | Out-Null
try {
    $env:REFERENCE_ROOT = $postmanEmptyReference
    .venv/Scripts/python.exe -m scripts.seed --coach-email coach.postman@example.com --coach-name "Coach Postman"
} finally {
    if ($null -eq $postmanReferenceBefore) {
        Remove-Item Env:REFERENCE_ROOT -ErrorAction SilentlyContinue
    } else {
        $env:REFERENCE_ROOT = $postmanReferenceBefore
    }
}
```

Password diminta interaktif. Alamat example.com di atas hanya identitas akun uji,
bukan kotak surat untuk tes SMTP. Perintah ini menulis akun/katalog, tidak mengubah
.env atau file referensi, dan tidak mengirim email.

Isi coachIdentifier/coachPassword, lalu folder 05 → Login Coach. Simpan coachId
yang diisi scripts. Login Coach mengganti cookie refresh pada host yang sama;
memberToken masih tetap variabel terpisah dan bisa dipakai selama access valid.
Bearer Coach tidak membuat cookie refresh otomatis menjadi cookie Member.

Di terminal CLI, ganti 12 dan 3 dengan **memberId dan coachId aktual** dari Postman:

```powershell
.venv/Scripts/python.exe -m scripts.assign_coach --member-id 12 --coach-id 3 --actor "admin-postman" --reason "Pengujian binaan lokal"
```

Member hanya boleh punya satu Coach aktif. Sebelum assign, roster kosong dan
detail non-binaan 404 adalah benar. Setelah assign, GET profil Member menampilkan
Coach; roster Coach menampilkan Member tersebut. Assign bukan endpoint HTTP.

## 7. Review Coach sampai dibaca Member

1. Folder 05: GET profil/overview/roster/detail Member/daftar sesi/detail sesi.
2. Pastikan sesi completed. Hasil reference_not_ready tetap dapat direview manusia.
3. PUT feedback-draft dengan expectedVersion=0 → 200 dan version=1. Isi contoh
   review hanyalah input manusia untuk tes, bukan diagnosis otomatis.
4. Untuk mengedit draft sebelum publish, gunakan expectedVersion terbaru dari
   server. Salah versi → 409; muat ulang draft, jangan overwrite otomatis.
5. POST reviews dengan expectedRevision=0 dan expectedDraftVersion dari draft,
   serta publishKey yang baru → 201. Scripts menyimpan revision dan taskId pertama.
6. GET detail Member dari folder 06: review, reviewHistory dan followUpTasks muncul.
   Draft yang belum dipublish tidak terlihat oleh Member.
7. PATCH tugas dengan status completed → 200. dismissed juga didukung.
8. POST follow-ups intent retry → 201. Ini mencatat niat, tidak mengunggah video.
9. Upload ulang membawa retryOf=sessionId sumber dan retryUploadKey baru. Pilih
   file lagi; respons menyimpan retrySessionId tanpa menimpa sessionId sumber.

Untuk revisi review: sesudah publish, buat draft baru dengan expectedVersion=0,
isi keputusan/catatan baru, lalu publish memakai revision terbaru dan key baru.
Review lama tetap immutable; draft baru tidak memakai version draft yang sudah
dipublish. Replay publish harus membawa payload/key persis seperti request asli;
scripts yang menaikkan reviewRevision perlu diingat saat menguji replay manual.

Opsional tes transfer/revoke (sesudah alur utama): buat Coach kedua dengan email
lain, login/simpan ID, lalu jalankan assign_coach dengan ID Coach baru. Coach lama
kehilangan akses detail/media/draft, Coach baru membaca histori, dan author review
lama tetap ada. Revoke:

```powershell
.venv/Scripts/python.exe -m scripts.assign_coach --member-id 12 --unassign --actor "admin-postman" --reason "Selesai menguji pencabutan binaan"
```

Gunakan ID aktual. Member tetap dapat upload dan melihat analisis otomatis saat
tidak punya Coach. Jika ingin melanjutkan tes Coach, assign kembali lewat CLI.

## 8. Tes email, reset, ganti password dan logout

Jalankan manual setelah tes fitur. Request email memakai Zoho SMTP yang sudah
dikonfigurasi; gunakan kotak surat sendiri. Cek folder Spam juga. Respons 202
bersifat generik dan bukan bukti email pasti terkirim/akun memenuhi syarat.

### A. Akun NPM-only: tautkan email

1. Login ulang Member agar token dan cookie milik Member.
2. Isi memberEmail dengan email milikmu yang belum digunakan akun lain.
3. POST email-link/request: email dan currentPassword → 202.
4. Buka email sebagai teks/copy link. Bentuknya
   http://localhost:3000/confirm-email#link:TOKEN. Untuk Postman tidak perlu FE
   berjalan: salin **hanya bagian TOKEN setelah #link:** ke linkToken.
5. POST email-link/confirm dengan token → 204. Penautan sekaligus memverifikasi
   alamat itu dan mencabut seluruh sesi; token tidak bisa dipakai ulang.
6. Login ulang memakai NPM dan password yang sama; GET profil menunjukkan email
   serta emailVerifiedAt. NPM tetap dapat dipakai untuk login.

### B. Akun yang sudah punya email tetapi belum verified

Ini alternatif A, tidak wajib dijalankan pada akun yang baru selesai linking.
Login akun email, POST email-verification/request dengan currentPassword → 202.
Ambil token setelah #verify: ke verifyToken; POST email-verification/confirm →
204. GET profil memastikan emailVerifiedAt terisi. Konfirmasi verification tidak
mencabut sesi seperti konfirmasi penautan/reset.

### C. Reset password

1. Pastikan email verified dan memberNewPassword berbeda dari password sekarang.
2. POST password-reset/request tanpa Bearer, body identifier NPM/email → 202.
3. Ambil token setelah #reset: dari email ke resetToken.
4. POST password-reset/confirm tanpa Bearer, body token/newPassword → 204.
5. Sesi lama tidak berlaku. Ubah variable memberPassword ke password baru dan
   login lagi. GET profil harus sukses, login password lama harus ditolak.

Token link/verify berlaku 24 jam; reset 30 menit; sekali pakai. Request terbaru
yang berhasil dikirim menggantikan token sebelumnya untuk tujuan yang sama.
Token asli tidak dikembalikan JSON atau disimpan plaintext di database/log.
Jika tidak ada email, periksa kelayakan akun/alamat, Spam dan konfigurasi SMTP;
jangan mencoba mencari token asli lewat query database.

### D. Ganti password saat login

PATCH member/password (atau coach/password) dengan currentPassword dan
newPassword → 204. Lakukan terpisah dari reset: sesuaikan kembali variable password
dan token setelah tiap perubahan. Semua sesi akun itu dicabut; login ulang.

### E. Refresh dan logout

Login akun yang ingin diuji dahulu. POST refresh-session tanpa body/Bearer memakai
refresh cookie; pilih request refresh Member atau Coach yang sesuai agar scripts
menyimpan token ke variable yang benar. POST logout tanpa body → 204 dan cookie
dihapus. Refresh sesudah logout → 401. Access token yang sudah diterbitkan masih
dapat valid sampai kedaluwarsa (15 menit); logout hanya mencabut refresh sesi itu.
Ganti password/reset/link mencabut access seluruh sesi melalui authVersion.

## 9. Penghapusan dan tes negatif

Folder 08 DELETE sesi sumber → 204. Jalankan paling akhir; detail/history/media
sesi yang dihapus tidak lagi tersedia melalui API. Ini soft-delete dengan audit,
bukan penghapusan seluruh akun/DB. Jika retrySessionId dibuat, sesi retry terpisah
dan dapat dihapus dengan ID itu bila memang ingin membersihkan video ujinya.

Tes negatif berikut dilakukan dengan request salinan agar alur utama tetap utuh:

| Kasus | Hasil yang diharapkan |
| --- | --- |
| GET profil tanpa Bearer/token invalid | 401 |
| Member memanggil endpoint Coach | 403 |
| Coach meminta detail Member bukan binaan | 404 |
| Member lain meminta sesi orang lain | 404 |
| PATCH profil berisi role/email/sabuk | 422 |
| NPM bukan 8–12 digit atau password kurang dari 8 karakter | 422 |
| File non-video/format tidak didukung | 415/422 sesuai tahap validasi |
| File melebihi batas ukuran | 413 |
| Sesi masih pending lalu meminta hasil/review | Konflik/belum tersedia sesuai endpoint |
| Key idempotensi sama tetapi payload berbeda | 409 |
| expectedVersion/expectedRevision sudah usang | 409 |
| Range video di luar ukuran file | 416 |
| Media telah berakhir masa akses, sesi masih terlihat | 410 |
| Token recovery dipakai ulang/invalid | 422 |
| Terlalu banyak request auth/recovery | 429; tunggu jendela rate limit |

Respons error domain baru berisi detail, code dan requestId; auth existing dapat
tetap berisi detail string/array. Simpan method, URL, status dan requestId untuk
diagnosis, tanpa membagikan Bearer/cookie/password/token recovery.

Folder prototype sudah dihapus dari collection. Seluruh tes memakai kontrak
auth dan domain sekarang; lihat [pemetaan penghapusan](route-cleanup.md).

## 10. Diagnosis dan kriteria selesai

| Gejala | Pemeriksaan |
| --- | --- |
| ECONNREFUSED/connection refused | Terminal API aktif, URL/port 8001 benar |
| Port 8001 sedang dipakai | Gunakan instance backend yang benar atau pilih port lain dan samakan host/baseUrl |
| health/ready 503 | Service MySQL, .env target development, migrasi 0007, izin storage |
| Refresh 401 setelah login | Cookie jar aktif, localhost konsisten, cookie tidak Secure pada HTTP, akun cookie benar |
| Token access kedaluwarsa | Refresh memakai cookie akun yang benar atau login ulang |
| Upload tetap queued | Worker aktif; python -m scripts.queue_status untuk diagnosis antrean |
| Worker gagal | File model tersedia, decoder dapat membaca video, error status/log worker |
| score null/reference_not_ready | Wajar tanpa dataset/profil referensi; bukan bukti upload gagal |
| Coach roster kosong | Role benar dan sudah assign lewat CLI |
| 429 | Kurangi pengulangan; jangan menghapus throttle database development |

Smoke test tuntas bila login/refresh, perubahan profil, katalog, upload→completed,
hasil nullable, video/Range, histori/dashboard, assignment, draft/publish dan tugas
berhasil. Recovery dinilai terpisah setelah email benar-benar diterima dan token
dikonfirmasi. Catat tahap yang belum dijalankan; jangan menyebut seluruh E2E lulus
hanya karena health 200. Penilaian ilmiah AI, benchmark kapasitas dan expiry 24 jam
tidak dibuktikan oleh smoke manual singkat ini.

Artefak panduan ini diperiksa secara statis terhadap snapshot OpenAPI: **53
request mencakup 44/44 operasi**, referensi variable dan field body JSON sesuai
schema. Pemeriksaan ini tidak mengirim HTTP/email, menjalankan aplikasi, atau
mengubah database; hasil Send Postman tetap harus dicatat setelah dijalankan.
