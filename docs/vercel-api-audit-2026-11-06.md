# Audit API Vercel - 6 November 2026

Target: https://silatsense-be.vercel.app. Audit nyata melalui HTTP pada 17:22-17:26 WIB, memakai akun dan data uji baru.

## Hasil aktual

- 46/46 operasi OpenAPI teruji melalui 116 request HTTP, ditambah direct PUT ke B2 dan proses worker native.
- 45 operasi memiliki respons sukses 2xx. POST multipart lama /api/v1/member/sessions mengembalikan 503 direct_upload_required sesuai mode B2.
- Tidak ada respons 500 atau kegagalan HTTP yang tidak diharapkan. Respons 401/403/404/409/410/416/422 yang tercatat berasal dari kasus negatif yang disengaja.
- Respons JSON sukses yang memiliki response_model divalidasi terhadap model Pydantic kode API. /docs dan /openapi.json juga mengembalikan 200.
- Empat kategori katalog tersedia. Analisis video sintetis selesai dengan reference_not_ready dan skor null; ini bukan uji akurasi model.

## Temuan dan tindakan

1. Refresh cookie dari deployment HTTPS memiliki HttpOnly=true tetapi Secure=false. Atur COOKIE_SECURE=true di environment Production Vercel, deploy ulang, lalu verifikasi Set-Cookie. Pengaturan ini belum diubah oleh audit.
2. Worker native memakai perbaikan MySQL 5.7 pada branch fix/mysql57-worker-claim. Perbaikan belum commit/push/merge. Worker tes berjalan satu iterasi; belum ada proses persisten yang disiapkan oleh audit.
3. Endpoint multipart lama tetap tercantum tetapi dinonaktifkan pada mode B2. Integrasi menggunakan POST /member/uploads, PUT langsung ke B2, lalu POST complete.

## Cakupan operasi dan status yang diamati

Kolom status mencakup kasus sukses dan penolakan yang disengaja; respons 4xx tidak berarti endpoint gagal.

| Method | Endpoint | Status HTTP |
| --- | --- | --- |
| POST | /api/v1/auth/sign-up | 201, 409 |
| POST | /api/v1/auth/sign-in | 200, 401 |
| GET | /api/v1/auth/session | 200, 401 |
| POST | /api/v1/auth/refresh-session | 200, 401 |
| POST | /api/v1/auth/logout | 204 |
| GET | /api/v1/member/profile | 200, 403 |
| PATCH | /api/v1/member/profile | 200, 422 |
| GET | /api/v1/coach/profile | 200, 403 |
| PATCH | /api/v1/coach/profile | 200 |
| PATCH | /api/v1/member/password | 204, 401 |
| PATCH | /api/v1/coach/password | 204, 401 |
| GET | /api/v1/member/training-modules | 200 |
| GET | /api/v1/member/training-prep/{slug} | 200, 404 |
| GET | /api/v1/member/record-config/{slug} | 200 |
| POST | /api/v1/member/sessions | 503 |
| GET | /api/v1/member/sessions/{session_id} | 200, 404 |
| DELETE | /api/v1/member/sessions/{session_id} | 204 |
| GET | /api/v1/member/sessions/{session_id}/evaluation | 200, 409 |
| GET | /api/v1/member/sessions/{session_id}/pose | 200 |
| GET | /api/v1/member/sessions/{session_id}/video | 200, 206, 404, 410, 416 |
| POST | /api/v1/member/sessions/{session_id}/acknowledge | 200 |
| POST | /api/v1/member/uploads | 201, 409 |
| POST | /api/v1/member/uploads/{upload_id}/complete | 202, 409 |
| GET | /api/v1/member/history | 200, 422 |
| GET | /api/v1/member/history/{session_id} | 200 |
| GET | /api/v1/member/dashboard | 200 |
| GET | /api/v1/coach/overview | 200 |
| GET | /api/v1/coach/roster | 200 |
| GET | /api/v1/coach/roster/{member_id} | 200, 404 |
| GET | /api/v1/coach/roster/{member_id}/sessions | 200 |
| GET | /api/v1/coach/sessions/{session_id} | 200, 404 |
| GET | /api/v1/coach/sessions/{session_id}/pose | 200 |
| GET | /api/v1/coach/sessions/{session_id}/video | 206, 404 |
| PUT | /api/v1/coach/sessions/{session_id}/feedback-draft | 200, 409 |
| POST | /api/v1/coach/sessions/{session_id}/reviews | 201 |
| POST | /api/v1/member/sessions/{session_id}/follow-ups | 201 |
| PATCH | /api/v1/member/follow-up-tasks/{task_id} | 200, 404 |
| POST | /api/v1/auth/email-link/request | 202, 401 |
| POST | /api/v1/auth/email-verification/request | 202, 422 |
| POST | /api/v1/auth/password-reset/request | 202 |
| POST | /api/v1/auth/email-link/confirm | 204 |
| POST | /api/v1/auth/email-verification/confirm | 204, 422 |
| POST | /api/v1/auth/password-reset/confirm | 204, 422 |
| GET | /health/live | 200 |
| GET | /health/ready | 200 |
| GET | /health | 200 |

## Alur yang diverifikasi

- Registrasi, login, refresh rotation/replay, logout dan penolakan Bearer lama setelah perubahan password, penautan email dan reset password.
- Profil Member/Coach, katalog empat kategori, panduan, konfigurasi rekaman, histori dan dashboard saat kosong maupun setelah sesi selesai.
- Init upload idempotent, konflik payload, complete sebelum PUT, direct upload B2, complete idempotent, job queued hingga completed dengan worker lokal.
- Evaluasi, pose, video penuh/Range, range tidak valid, akses lintas Member ditolak, media kedaluwarsa ditolak sementara hasil evaluasi tetap tersimpan.
- Binaan, overview, detail sesi, draft optimistic concurrency, publish/replay review, revisi immutable, tugas tindak lanjut dan retry intent.
- Transfer Coach: Coach lama kehilangan detail/video; Coach baru memperoleh histori; identitas penulis review lama tetap terjaga.

## Pengujian email

Tiga request pengiriman nyata telah diizinkan pengguna dan dilakukan untuk link, verifikasi dan reset ke alias Gmail milik pengguna. Semua menghasilkan 202 dan token request tersimpan, membuktikan submission SMTP diterima tanpa error aplikasi. Audit tidak membaca inbox atau memastikan lokasi inbox/spam.

Konfirmasi token melalui API menggunakan token fixture yang dimasukkan hanya untuk akun uji di database, bukan token yang dibaca dari email. Dengan demikian, alur klik tautan email/bridge FE belum teruji. Token yang dikirim melalui email dan seluruh token fixture telah dinonaktifkan setelah audit; email uji tidak perlu diklik.

## Isolasi dan cleanup

Fixture Member ID 11/12 dan Coach ID 13/14 dibuat untuk audit. Role Coach dan penugasan disiapkan secara administratif; tidak ada endpoint publik pendaftaran Coach. Tidak ada akun atau penugasan pengguna existing yang dimodifikasi.

Sesi/video uji dihapus melalui API dan storage; penugasan uji dicabut; refresh/recovery token dicabut dan authVersion akun uji dinaikkan. Cleanup selesai tanpa error atau lease tertunda. Akun uji serta histori review/penugasan immutable tetap tercatat. Audit tidak menghapus histori tersebut.

Laporan mesin tanpa password, Bearer, cookie atau signed URL berada di .cache/vercel-all-50a57cf16d/report.json (diabaikan Git).

## Keterbatasan

Tes ini memakai HTTP non-browser, bukan verifikasi CORS/player FE. Tidak mencakup semua kombinasi input, serangan, beban, multi-process, concurrency atau dataset gerakan nyata. SQL fixture digunakan untuk provisioning Coach/assignment, token konfirmasi dan simulasi expiry media; seluruh endpoint yang tercantum tetap dipanggil pada deployment Vercel asli.
