# Serah terima backend untuk frontend

Status 19 Oktober 2026: **backend MVP siap dipakai untuk integrasi fitur aplikasi**.
Seluruh layar FE belum terhubung; penilaian AI silat belum tervalidasi. Ini bukan
klaim production-ready atau model AI final.

## Akses, kontrak, dan setup

- Base URL native: `http://localhost:8001/api/v1`.
- Swagger: `http://localhost:8001/docs`; OpenAPI: `/openapi.json`, di root host.
  URL tersebut tersedia setelah proses API dijalankan, bukan layanan staging online.
- [Snapshot OpenAPI](openapi.json), [kontrak API](api-contract.md),
  [contoh HTTP](examples.http), [matriks/delta FE](fe-integration.md).
- Native: Python 3.12, dependencies `requirements-lock.txt`, MySQL 8, migrasi
  Alembic head `0007`. `DATABASE_URL` memakai driver `mysql+pymysql`.
- Database development pemilik proyek sudah dimigrasi/check, katalog empat
  gerakan diisi tanpa akun/sesi atau profil referensi. Pengembang lain menyiapkan
  DB dan `.env` sendiri; data serta `.env` tidak ikut Git.
- File model MediaPipe `.task` tidak ikut Git. Pada mesin baru, siapkan lewat
  `python -m scripts.download_pose_model` sebelum menjalankan analisis.
  Jangan mengimpor profil prototype sebagai referensi tervalidasi.
- `localhost` berarti mesin proses FE/BE masing-masing. Tim pada mesin berbeda
  perlu menjalankan backend sendiri atau menyepakati URL bersama dan origin FE.
  Belum ada deployment/staging bersama.

Jalankan dari root backend setelah konfigurasi/migrasi benar; tiga terminal native:

```powershell
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --no-access-log
.venv/Scripts/python.exe -m scripts.worker
.venv/Scripts/python.exe -m scripts.cleanup_media
```

`/health/live` memeriksa proses; `/health/ready` memeriksa revision DB dan storage.
Worker perlu berjalan agar status upload bergerak dari queued. Tidak perlu Docker.

## Auth yang perlu diterima tim FE

Bridge auth tersedia secara lokal di repo FE, branch
`experiment/backend-phase7-auth`, **masih perubahan belum di-commit/push**.
Mengirim repo backend saja belum mengirim perubahan tersebut ke rekan FE.
Panduan FE: `docs/backend-phase7-auth.md` di repo FE.

Konfigurasi FE server-only: `API_BASE_URL=http://localhost:8001/api/v1`,
`FRONTEND_ORIGIN=http://localhost:3000`, `SESSION_ENCRYPTION_KEY` 32 byte hex
terpisah dari JWT backend, `FE_PROCESS_COUNT=1`. Jangan memakai NEXT_PUBLIC
untuk secret. Samakan origin BE/FE; jangan mencampur localhost dan 127.0.0.1
pada browser. Kredensial SMTP/DB/JWT backend tidak dibutuhkan tim FE dan tidak
dibagikan melalui Git/chat.

Login/sign-up/session/refresh/logout tetap kontrak existing. Public sign-up hanya
membuat Member; akun Coach disiapkan operator. Bearer disisipkan per request dari
bridge cookie HttpOnly terenkripsi; tidak dikirim ke props/localStorage/query URL.
Cookie refresh BE hanya path `/api/v1/auth`; server fetch FE wajib menangani
Set-Cookie dan forward refresh cookie secara eksplisit.

RSC hanya membaca sesi. Expired/401 autentikasi dipulihkan melalui server action,
lalu pembacaan diulang sekali. Single-flight per sesi, hasil rotasi 30 detik;
network error bukan otomatis sesi dicabut. Salah kredensial saat login/reauth
ditampilkan sebagai error, bukan refresh loop. Mutasi tidak direplay tanpa
idempotensi. Fetch privat no-store dan cache browser dibersihkan saat user berganti.
Registry FE saat ini untuk satu proses; multi-process perlu koordinasi bersama.

## Endpoint yang dipakai integrasi baru

Semua path berikut setelah `/api/v1`; detail DTO mengikuti OpenAPI.

| Fitur | Method/path |
| --- | --- |
| Profil dan password | GET/PATCH `/member/profile` atau `/coach/profile`; PATCH `/member/password` atau `/coach/password` |
| Katalog/panduan/konfigurasi | GET `/member/training-modules`, `/member/training-prep/{slug}`, `/member/record-config/{slug}` |
| Upload/status | POST `/member/sessions`; GET `/member/sessions/{sessionId}` |
| Evaluasi/pose/video | GET `/member/sessions/{sessionId}/evaluation`, `/pose`, `/video` |
| Acknowledge/hapus | POST `/member/sessions/{sessionId}/acknowledge`; DELETE `/member/sessions/{sessionId}` |
| Histori/dashboard | GET `/member/history`, `/member/history/{sessionId}`, `/member/dashboard` |
| Binaan Coach | GET `/coach/overview`, `/coach/roster`, `/coach/roster/{memberId}`, `/coach/roster/{memberId}/sessions` |
| Review Coach | GET `/coach/sessions/{sessionId}`; PUT `/coach/sessions/{sessionId}/feedback-draft`; POST `/coach/sessions/{sessionId}/reviews` |
| Media Coach | GET `/coach/sessions/{sessionId}/pose`, `/coach/sessions/{sessionId}/video` |
| Tindak lanjut | POST `/member/sessions/{sessionId}/follow-ups`; PATCH `/member/follow-up-tasks/{taskId}` |
| Keamanan email | POST `/auth/email-link/request`, `/auth/email-link/confirm`, `/auth/email-verification/request`, `/auth/email-verification/confirm`, `/auth/password-reset/request`, `/auth/password-reset/confirm` |

Endpoint `/profile`, `/evaluations`, `/coach/members` adalah kompatibilitas
prototype, dengan shape berbeda. Gunakan kontrak Member/Coach baru untuk fitur baru.

## Alur upload sampai review

1. Ambil konfigurasi upload dan capability katalog. Slug publik `kuda-kuda`,
   `pukulan`, `tangkisan`, `tendangan`; jangan mengirim internal `kuda_kuda`.
2. POST multipart: `movementSlug`, `video`, opsional `retryOf`. Wajib header
   `Idempotency-Key` unik per operasi; retry payload sama memakai key yang sama.
   Jangan menetapkan Content-Type boundary sendiri ketika memakai FormData.
3. Respons 202 berisi `sessionId`, `processingStatus`, `statusUrl`, `evaluationUrl`.
   Simpan sessionId; halaman hasil tidak memakai slug sebagai identitas sesi.
4. Poll status sekitar dua detik saat halaman aktif; berhenti saat completed,
   failed, logout/unmount atau akses ditolak. Progres transfer berbeda dari analisis.
5. Setelah completed, baca evaluation/pose. Status analisis tanpa referensi tetap
   completed dengan score null; bukan kegagalan pemrosesan. Render alasan unavailable.
6. Histori/evaluasi sudah tersimpan. Acknowledge tidak membuat hasil baru.
7. Coach aktif menyimpan draft dengan expectedVersion, lalu publish memakai
   expectedRevision + expectedDraftVersion dan Idempotency-Key. Konflik 409 perlu
   refetch/review perubahan, bukan overwrite/retry otomatis.

Draft baru memakai expectedVersion=0; publikasi pertama expectedRevision=0.
Gunakan versi yang dikembalikan server untuk perubahan berikutnya.

Upload default maksimum 100 MiB/60 detik, MIME MP4/MOV/WebM yang diverifikasi
decoder, kuota 500 MiB/member dan maksimum dua sesi pending/reservation. Ambil
nilai aktif dari record-config; jangan hanya mengandalkan hardcode UI.

Browser video tidak dapat menyetel Bearer melalui src. FE masih perlu adapter
streaming privat untuk media yang meneruskan Range/200/206/416 dan no-store.
Upload file besar juga perlu adapter streaming yang sesuai runtime Next; default
Server Action limit bukan jalur upload 100 MiB. Kedua adapter ini belum dibuat.
Jangan memasukkan token ke URL atau memperlebar path cookie refresh BE.

## State UI dan aturan data wajib

- ID string, field camelCase, timestamp UTC ISO 8601; FE memformat tanggal lokal.
- `processingStatus`, `analysisStatus`, dan `reviewStatus` terpisah. Jangan memakai
  approved Coach sebagai status sukses worker, atau score sebagai kelulusan sabuk.
- Pagination `{items,nextCursor}`, default 20/maksimum 100. Cursor opaque dan
  terikat filter/user. Riwayat memakai filter movementSlug/processingStatus/
  reviewStatus/from/to; tanggal from inklusif dan to eksklusif dalam UTC.
- Null bukan nol. Akun kosong memiliki jumlah 0, rata-rata/lastSession null.
  Array kosong valid. Agregat comparable disertai sampleCount; jangan mencampur
  versi/metode menjadi satu persentase tanpa dasar.
- Media privat berakhir tepat 24 jam sejak upload selesai. Tangani expired,
  deleted/unavailable dan 410; hasil/feedback tetap tersimpan.
- Member boleh tanpa Coach. Coach hanya melihat binaan aktif; setelah transfer,
  buang cache akses Coach lama. Author review historis tetap ditampilkan.
- Role/NPM/email/sabuk bukan field bebas PATCH. Email melalui alur reauth dan
  konfirmasi; kamera/deviceId tetap browser-only.
- Error baru `{detail,code,requestId}`; auth existing detail string/array.
  Tangani 401/403/404/409/410/413/415/416/422/429/503 secara sesuai konteks.

## Batas AI dan status pekerjaan FE

Dataset khusus belum tersedia; DB development tidak diisi profil referensi.
FE harus mendukung scoringAvailable=false, score=null dan reference_not_ready.
MediaPipe mendeteksi pose, tetapi penilaian teknik silat belum tervalidasi.
Jangan menampilkan dummy, label akurasi model/standar IPSI, target lulus 85%,
repetisi, timing impak, atau koreksi cm yang belum didukung metode/data.

Lokal FE sudah menghubungkan auth/keamanan. Katalog, dashboard, upload/status,
evaluasi/pose/media, histori, biodata dan review Coach masih perlu dihubungkan.
Prioritas: katalog/profil → upload/status → hasil/media → histori/dashboard →
roster/review/tindak lanjut. Hapus cache/dummy pribadi pada setiap fitur yang
dipindah ke API dan uji read-your-own-write, dua user, empty/error/expired states.

## Bukti dan pekerjaan akhir

Regresi tercatat: SQLite 204 passed/18 skip khusus MySQL; suite MySQL penuh 220
passed, lalu 24 regresi native final pada area recovery/migrasi/presisi; FE 249
passed dan build/typecheck/lint lulus. Lihat [bukti rinci](phase7-api.md).
MySQL development upgrade/check dan HTTP readiness/Swagger sudah diverifikasi.
SMTP Zoho TLS/login dan satu pengiriman nyata berhasil; penerima melaporkan masuk
Spam. E2E link/verify/reset melalui API dengan provider Zoho nyata belum diuji;
alur tersebut sudah diuji dengan adapter memory/SMTP loopback.

CI GitHub/container build belum dijalankan, staging/deployment belum tersedia,
uji kapasitas 10–15 user dan validasi ilmiah belum dilakukan. Backend dapat
dipush untuk kolaborasi/integrasi sekarang; hasil CI perlu diperiksa setelah push.
