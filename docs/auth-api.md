# Auth API untuk SilatSense FE

Base URL: `http://localhost:8000/api/v1`. Semua body request memakai JSON.
Endpoint lama `/auth/register`, `/auth/login`, `/auth/me`, dan `/auth/refresh`
tetap tersedia dengan nama field prototype.

| Method | Path | Kegunaan |
| --- | --- | --- |
| POST | `/auth/sign-up` | Daftar Member, sekaligus membuat sesi (201) |
| POST | `/auth/sign-in` | Login Member atau Coach (200) |
| GET | `/auth/session` | Pengguna aktif dengan format FE (200) |
| POST | `/auth/refresh-session` | Rotasi refresh token dan access token baru (200) |
| POST | `/auth/logout` | Cabut refresh token sesi ini dan hapus cookie (204) |

## Registrasi

```json
{
  "fullName": "Member SilatSense",
  "identifier": "227006104",
  "password": "password123"
}
```

`identifier` menerima NPM 8–12 digit ASCII atau email valid. Email dinormalisasi
ke huruf kecil; spasi di awal/akhir identifier dan nama dihapus. Nama minimal
3 karakter, maksimal 120. Password 8–128 karakter, tidak di-trim.
`confirmPassword` dan persetujuan syarat adalah validasi FE, tidak dikirim.
Registrasi publik selalu membuat role Member; field tambahan seperti `role`
ditolak. Akun Coach dibuat melalui script seed yang sudah tersedia.
Registrasi dengan NPM tidak membuat email fiktif. Satu akun terdaftar dengan
satu identifier; penautan NPM dan email ke akun yang sama belum tersedia.

## Login

```json
{
  "identifier": "227006104",
  "password": "password123",
  "rememberMe": true
}
```

Respons registrasi, login, dan refresh-session mengikuti DTO auth FE:

```json
{
  "user": {
    "id": "1",
    "fullName": "Member SilatSense",
    "identifier": "227006104",
    "role": "member"
  },
  "accessToken": "<JWT>",
  "expiresIn": 900
}
```

`role` adalah `member` atau `coach`. `GET /auth/session` mengembalikan objek
`user` di atas secara langsung, dengan header `Authorization: Bearer <JWT>`.
Endpoint lama `/auth/me` dan `/profile` tetap mengembalikan `id` numerik,
`name`, `email`, role huruf besar, dan `created_at`. Untuk akun NPM, `email`
pada respons lama bernilai `null`.

## Sesi, refresh, dan logout

Access token berlaku 15 menit. Refresh token hanya dikirim melalui cookie
`refresh_token`: HttpOnly, SameSite=Strict, path `/api/v1/auth`; Secure mengikuti
konfigurasi `COOKIE_SECURE` (aktifkan untuk HTTPS).

- `rememberMe: false` (default): cookie sesi browser, refresh berlaku maksimal
  24 jam. Registrasi juga menggunakan kebijakan ini.
- `rememberMe: true`: cookie persisten dan refresh berlaku maksimal 7 hari.
- Refresh mempertahankan batas waktu sesi awal dan pilihan persistensi.
  Token lama dicabut secara atomik; penggunaan ulang menghasilkan 401.
- Logout mencabut refresh token sesi ini. Access token yang sudah diterbitkan
  masih berlaku sampai kedaluwarsa; FE harus menghapus access token saat logout.

Untuk browser, gunakan `credentials: "include"` saat login, registrasi,
refresh, dan logout. Simpan access token di memori dan gunakan header Bearer
untuk endpoint terlindungi. Panggil refresh sekali saat sesi perlu dipulihkan;
hindari refresh paralel memakai cookie yang sama.

`FRONTEND_ORIGIN` harus sesuai origin FE. Konfigurasi cookie Strict saat ini
mendukung development localhost dan deployment FE–BE pada site yang sama.
Jika FE menggunakan server actions, server FE harus meneruskan cookie request
ke BE dan meneruskan `Set-Cookie` ke browser dengan path/domain yang sesuai;
cookie tidak otomatis sampai ke browser dari fetch server.

## Error

- 401: kredensial salah, access token tidak valid, refresh hilang/kedaluwarsa/dicabut.
- 403: Origin yang dikirim tidak sesuai konfigurasi, atau role tidak berhak.
- 409: NPM/email sudah terdaftar.
- 422: body tidak valid; mengikuti format validasi FastAPI.

Error aplikasi memakai `{"detail": "pesan"}`. Error validasi memakai
`{"detail": [...]}`. FE perlu menangani kedua bentuk ini.

## Menjalankan

Migrasi `0002` menambahkan NPM, mengizinkan email null untuk akun NPM, dan
menyimpan kebijakan persistensi refresh. Untuk environment native:

```powershell
.venv/Scripts/alembic.exe upgrade head
.venv/Scripts/alembic.exe check
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Untuk Docker: `docker compose up -d --build --wait`; startup menjalankan migrasi.
Swagger tersedia di `http://localhost:8000/docs`.
Recovery baru tersedia pada Fase 7; lihat tambahan di bawah.

## Tambahan Fase 2

Profil/password per role tersedia setelah migrasi `0003`; contoh di
[phase2-api.md](phase2-api.md). DTO auth, cookie, rememberMe dan deadline rotasi
tetap sama. JWT baru menambahkan claim internal `authVersion`, dan refresh token
menyimpan versi akun. JWT lama tanpa claim tersebut masih berlaku untuk akun
version 0. Ganti password melalui endpoint Member/Coach menaikkan versi dan
mencabut seluruh access/refresh sesi akun, termasuk token legacy; wajib login
ulang. Logout biasa tetap hanya mencabut refresh sesi saat ini.

Penautan/verifikasi email dan password reset kini tersedia pada Fase 7. Email
akun existing tidak otomatis verified. Kontrak baru terpisah dari auth existing:
[phase7-api.md](phase7-api.md), [OpenAPI](openapi.json), [contoh HTTP](examples.http).
Rate limit login/IP dapat menghasilkan 429 detail-compatible; cookie, rememberMe,
rotasi/deadline dan DTO login existing dipertahankan. Request ID/no-store ditambahkan
sebagai header, bukan perubahan body auth.
