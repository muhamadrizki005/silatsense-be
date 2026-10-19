# Referensi seluruh request Postman

Baca [urutan pengujian](../postman-guide.md) sebelum mengirim request. Semua `{{variable}}` berasal dari environment lokal. Jangan jalankan seluruh collection otomatis.

Untuk Bearer: tab Authorization → Bearer Token. Untuk JSON: Body → raw → JSON. Untuk multipart: Body → form-data; ubah tipe baris video menjadi File. Request tanpa body: pilih none. Cookie refresh dikelola cookie jar Postman.

## 01 - Kesiapan

API dan MySQL harus berjalan. Tidak membutuhkan token.

### /health/live

```http
GET {{host}}/health/live
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body: **none**.

Respons sukses yang diharapkan: **200** (prasyarat pada panduan harus terpenuhi).

### /health/ready

```http
GET {{host}}/health/ready
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body: **none**.

Respons sukses yang diharapkan: **200** (prasyarat pada panduan harus terpenuhi).

### /health

```http
GET {{host}}/health
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body: **none**.

Respons sukses yang diharapkan: **200** (prasyarat pada panduan harus terpenuhi).

## 02 - Member auth

Isi environment dahulu. Cookie jar Postman menyimpan refresh_token. Jangan jalankan semua folder sekaligus.

### 01 Registrasi Member baru

```http
POST {{baseUrl}}/auth/sign-up
Content-Type: application/json
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body raw JSON (angka versi adalah variable tanpa kutip):

```json
{
  "fullName": "Member Postman",
  "identifier": "{{memberIdentifier}}",
  "password": "{{memberPassword}}"
}
```

Respons sukses yang diharapkan: **201** (prasyarat pada panduan harus terpenuhi).

### 02 Login Member

```http
POST {{baseUrl}}/auth/sign-in
Content-Type: application/json
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body raw JSON (angka versi adalah variable tanpa kutip):

```json
{
  "identifier": "{{memberIdentifier}}",
  "password": "{{memberPassword}}",
  "rememberMe": false
}
```

Respons sukses yang diharapkan: **200** (prasyarat pada panduan harus terpenuhi).

### 03 Sesi Member

```http
GET {{baseUrl}}/auth/session
Authorization: Bearer {{memberToken}}
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body: **none**.

Respons sukses yang diharapkan: **200** (prasyarat pada panduan harus terpenuhi).

### 04 Refresh Member (cookie harus milik Member)

```http
POST {{baseUrl}}/auth/refresh-session
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body: **none**.

Respons sukses yang diharapkan: **200** (prasyarat pada panduan harus terpenuhi).

## 03 - Profil dan katalog Member

Semua request memakai memberToken. Null dan akun kosong adalah respons valid.

### 01 Profil Member

```http
GET {{baseUrl}}/member/profile
Authorization: Bearer {{memberToken}}
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body: **none**.

Respons sukses yang diharapkan: **200** (prasyarat pada panduan harus terpenuhi).

### 02 Edit biodata Member

```http
PATCH {{baseUrl}}/member/profile
Authorization: Bearer {{memberToken}}
Content-Type: application/json
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body raw JSON (angka versi adalah variable tanpa kutip):

```json
{
  "fullName": "Member Postman",
  "division": "UKM Silat"
}
```

Respons sukses yang diharapkan: **200** (prasyarat pada panduan harus terpenuhi).

### 03 Katalog

```http
GET {{baseUrl}}/member/training-modules
Authorization: Bearer {{memberToken}}
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body: **none**.

Respons sukses yang diharapkan: **200** (prasyarat pada panduan harus terpenuhi).

### 04 Persiapan

```http
GET {{baseUrl}}/member/training-prep/{{movementSlug}}
Authorization: Bearer {{memberToken}}
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body: **none**.

Respons sukses yang diharapkan: **200** (prasyarat pada panduan harus terpenuhi).

### 05 Konfigurasi upload

```http
GET {{baseUrl}}/member/record-config/{{movementSlug}}
Authorization: Bearer {{memberToken}}
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body: **none**.

Respons sukses yang diharapkan: **200** (prasyarat pada panduan harus terpenuhi).

### 06 Dashboard

```http
GET {{baseUrl}}/member/dashboard
Authorization: Bearer {{memberToken}}
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body: **none**.

Respons sukses yang diharapkan: **200** (prasyarat pada panduan harus terpenuhi).

### 07 Histori halaman pertama

```http
GET {{baseUrl}}/member/history?limit=20
Authorization: Bearer {{memberToken}}
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body: **none**.

Respons sukses yang diharapkan: **200** (prasyarat pada panduan harus terpenuhi).

## 04 - Upload dan hasil

Pilih file video lokal di form-data. Generate uploadKey sekali per upload logis. Worker harus berjalan; polling status manual sampai completed/failed.

### 01 Upload video (pilih file dahulu)

```http
POST {{baseUrl}}/member/sessions
Authorization: Bearer {{memberToken}}
Idempotency-Key: {{uploadKey}}
```

Wajib pilih file video dan isi uploadKey unik. Klik Send ulang dengan key/file/field sama untuk tes replay; hasil sessionId harus sama. Jangan pasang Content-Type manual.

| Key | Type | Value |
| --- | --- | --- |
| movementSlug | text | {{movementSlug}} |
| video | file | Pilih video lokal |

Jangan menambahkan header Content-Type sendiri; boundary dibuat Postman.

Respons sukses yang diharapkan: **202** (prasyarat pada panduan harus terpenuhi).

### 02 Status (ulang manual tiap sekitar 2 detik)

```http
GET {{baseUrl}}/member/sessions/{{sessionId}}
Authorization: Bearer {{memberToken}}
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body: **none**.

Respons sukses yang diharapkan: **200** (prasyarat pada panduan harus terpenuhi).

### 03 Evaluasi (setelah completed)

```http
GET {{baseUrl}}/member/sessions/{{sessionId}}/evaluation
Authorization: Bearer {{memberToken}}
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body: **none**.

Respons sukses yang diharapkan: **200** (prasyarat pada panduan harus terpenuhi).

### 04 Pose

```http
GET {{baseUrl}}/member/sessions/{{sessionId}}/pose
Authorization: Bearer {{memberToken}}
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body: **none**.

Respons sukses yang diharapkan: **200** (prasyarat pada panduan harus terpenuhi).

### 05 Video penuh

```http
GET {{baseUrl}}/member/sessions/{{sessionId}}/video
Authorization: Bearer {{memberToken}}
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body: **none**.

Respons sukses yang diharapkan: **200** (prasyarat pada panduan harus terpenuhi).

### 06 Video Range

```http
GET {{baseUrl}}/member/sessions/{{sessionId}}/video
Authorization: Bearer {{memberToken}}
Range: bytes=0-1023
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body: **none**.

Respons sukses yang diharapkan: **206** (prasyarat pada panduan harus terpenuhi).

### 07 Acknowledge

```http
POST {{baseUrl}}/member/sessions/{{sessionId}}/acknowledge
Authorization: Bearer {{memberToken}}
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body: **none**.

Respons sukses yang diharapkan: **200** (prasyarat pada panduan harus terpenuhi).

### 08 Histori detail

```http
GET {{baseUrl}}/member/history/{{sessionId}}
Authorization: Bearer {{memberToken}}
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body: **none**.

Respons sukses yang diharapkan: **200** (prasyarat pada panduan harus terpenuhi).

### 09 Histori filter

```http
GET {{baseUrl}}/member/history?limit=20&movementSlug={{movementSlug}}&processingStatus=completed&reviewStatus=pending
Authorization: Bearer {{memberToken}}
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body: **none**.

Respons sukses yang diharapkan: **200** (prasyarat pada panduan harus terpenuhi).

### 10 Histori halaman berikut (hanya jika cursor tidak null)

```http
GET {{baseUrl}}/member/history?limit=20&cursor={{historyCursor}}
Authorization: Bearer {{memberToken}}
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body: **none**.

Respons sukses yang diharapkan: **200** (prasyarat pada panduan harus terpenuhi).

## 05 - Coach dan review

Buat akun Coach lewat CLI lalu assign Member. Login Coach mengganti refresh cookie jar; memberToken tetap variabel terpisah. Sesi wajib completed untuk review.

### 01 Login Coach

```http
POST {{baseUrl}}/auth/sign-in
Content-Type: application/json
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body raw JSON (angka versi adalah variable tanpa kutip):

```json
{
  "identifier": "{{coachIdentifier}}",
  "password": "{{coachPassword}}",
  "rememberMe": false
}
```

Respons sukses yang diharapkan: **200** (prasyarat pada panduan harus terpenuhi).

### 02 Sesi Coach

```http
GET {{baseUrl}}/auth/session
Authorization: Bearer {{coachToken}}
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body: **none**.

Respons sukses yang diharapkan: **200** (prasyarat pada panduan harus terpenuhi).

### 03 Profil Coach

```http
GET {{baseUrl}}/coach/profile
Authorization: Bearer {{coachToken}}
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body: **none**.

Respons sukses yang diharapkan: **200** (prasyarat pada panduan harus terpenuhi).

### 04 Edit profil Coach

```http
PATCH {{baseUrl}}/coach/profile
Authorization: Bearer {{coachToken}}
Content-Type: application/json
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body raw JSON (angka versi adalah variable tanpa kutip):

```json
{
  "fullName": "Coach Postman",
  "division": "UKM Silat",
  "title": "Pelatih"
}
```

Respons sukses yang diharapkan: **200** (prasyarat pada panduan harus terpenuhi).

### 05 Overview

```http
GET {{baseUrl}}/coach/overview
Authorization: Bearer {{coachToken}}
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body: **none**.

Respons sukses yang diharapkan: **200** (prasyarat pada panduan harus terpenuhi).

### 06 Roster

```http
GET {{baseUrl}}/coach/roster?limit=20
Authorization: Bearer {{coachToken}}
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body: **none**.

Respons sukses yang diharapkan: **200** (prasyarat pada panduan harus terpenuhi).

### 07 Detail binaan

```http
GET {{baseUrl}}/coach/roster/{{memberId}}
Authorization: Bearer {{coachToken}}
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body: **none**.

Respons sukses yang diharapkan: **200** (prasyarat pada panduan harus terpenuhi).

### 08 Sesi binaan

```http
GET {{baseUrl}}/coach/roster/{{memberId}}/sessions?limit=20
Authorization: Bearer {{coachToken}}
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body: **none**.

Respons sukses yang diharapkan: **200** (prasyarat pada panduan harus terpenuhi).

### 09 Detail sesi dan draft

```http
GET {{baseUrl}}/coach/sessions/{{sessionId}}
Authorization: Bearer {{coachToken}}
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body: **none**.

Respons sukses yang diharapkan: **200** (prasyarat pada panduan harus terpenuhi).

### 10 Pose Coach

```http
GET {{baseUrl}}/coach/sessions/{{sessionId}}/pose
Authorization: Bearer {{coachToken}}
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body: **none**.

Respons sukses yang diharapkan: **200** (prasyarat pada panduan harus terpenuhi).

### 11 Video Coach

```http
GET {{baseUrl}}/coach/sessions/{{sessionId}}/video
Authorization: Bearer {{coachToken}}
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body: **none**.

Respons sukses yang diharapkan: **200** (prasyarat pada panduan harus terpenuhi).

### 12 Simpan draft baru

```http
PUT {{baseUrl}}/coach/sessions/{{sessionId}}/feedback-draft
Authorization: Bearer {{coachToken}}
Content-Type: application/json
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body raw JSON (angka versi adalah variable tanpa kutip):

```json
{
  "expectedVersion": 0,
  "decision": "needs_revision",
  "note": "Contoh review manual untuk pengujian alur.",
  "bodyAssessments": [
    {
      "bodyPart": "left_knee",
      "status": "not_assessed",
      "note": "Belum dinilai pada tes ini."
    }
  ],
  "tasks": [
    {
      "instruction": "Unggah latihan lanjutan setelah berkonsultasi dengan pelatih."
    }
  ]
}
```

Respons sukses yang diharapkan: **200** (prasyarat pada panduan harus terpenuhi).

### 13 Publikasikan review

```http
POST {{baseUrl}}/coach/sessions/{{sessionId}}/reviews
Authorization: Bearer {{coachToken}}
Content-Type: application/json
Idempotency-Key: {{publishKey}}
```

Sebelum Send, reviewRevision=0 untuk publikasi pertama dan draftVersion dari draft. Nilai versi berupa angka JSON tanpa tanda kutip. Setelah sukses, reviewRevision terbarui. Untuk replay, kembalikan payload revisi ke nilai semula dan gunakan publishKey yang sama.

Body raw JSON (angka versi adalah variable tanpa kutip):

```json
{
  "expectedRevision": {{reviewRevision}},
  "expectedDraftVersion": {{draftVersion}}
}
```

Respons sukses yang diharapkan: **201** (prasyarat pada panduan harus terpenuhi).

## 06 - Member membaca review dan tindak lanjut

Bearer tetap memberToken; tidak perlu login ulang jika access masih berlaku. Login ulang Member sebelum refresh/logout Member.

### 01 Baca review dan tugas

```http
GET {{baseUrl}}/member/history/{{sessionId}}
Authorization: Bearer {{memberToken}}
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body: **none**.

Respons sukses yang diharapkan: **200** (prasyarat pada panduan harus terpenuhi).

### 02 Selesaikan tugas

```http
PATCH {{baseUrl}}/member/follow-up-tasks/{{taskId}}
Authorization: Bearer {{memberToken}}
Content-Type: application/json
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body raw JSON (angka versi adalah variable tanpa kutip):

```json
{
  "status": "completed"
}
```

Respons sukses yang diharapkan: **200** (prasyarat pada panduan harus terpenuhi).

### 03 Intent latihan ulang

```http
POST {{baseUrl}}/member/sessions/{{sessionId}}/follow-ups
Authorization: Bearer {{memberToken}}
Content-Type: application/json
Idempotency-Key: {{retryKey}}
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body raw JSON (angka versi adalah variable tanpa kutip):

```json
{
  "intent": "retry"
}
```

Respons sukses yang diharapkan: **201** (prasyarat pada panduan harus terpenuhi).

### 04 Upload ulang (pilih video; key baru)

```http
POST {{baseUrl}}/member/sessions
Authorization: Bearer {{memberToken}}
Idempotency-Key: {{retryUploadKey}}
```

retryOf adalah ID sesi sumber, bukan ID intent. sessionId sumber tidak ditimpa; hasil baru disimpan sebagai retrySessionId.

| Key | Type | Value |
| --- | --- | --- |
| movementSlug | text | {{movementSlug}} |
| video | file | Pilih video lokal |
| retryOf | text | {{sessionId}} |

Jangan menambahkan header Content-Type sendiri; boundary dibuat Postman.

Respons sukses yang diharapkan: **202** (prasyarat pada panduan harus terpenuhi).

## 07 - Keamanan akun (manual, setelah tes fitur)

Request email benar-benar mengirim melalui SMTP. Isi alamat sendiri; ambil token dari email. Link dan reset mencabut sesi; login ulang. Jangan Run Collection keseluruhan.

### 01 Login ulang Member (cookie Member)

```http
POST {{baseUrl}}/auth/sign-in
Content-Type: application/json
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body raw JSON (angka versi adalah variable tanpa kutip):

```json
{
  "identifier": "{{memberIdentifier}}",
  "password": "{{memberPassword}}",
  "rememberMe": false
}
```

Respons sukses yang diharapkan: **200** (prasyarat pada panduan harus terpenuhi).

### 02 Request penautan email

```http
POST {{baseUrl}}/auth/email-link/request
Authorization: Bearer {{memberToken}}
Content-Type: application/json
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body raw JSON (angka versi adalah variable tanpa kutip):

```json
{
  "email": "{{memberEmail}}",
  "currentPassword": "{{memberPassword}}"
}
```

Respons sukses yang diharapkan: **202** (prasyarat pada panduan harus terpenuhi).

### 03 Konfirmasi penautan (login ulang sesudahnya)

```http
POST {{baseUrl}}/auth/email-link/confirm
Authorization: Bearer {{memberToken}}
Content-Type: application/json
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body raw JSON (angka versi adalah variable tanpa kutip):

```json
{
  "token": "{{linkToken}}"
}
```

Respons sukses yang diharapkan: **204** (prasyarat pada panduan harus terpenuhi).

### 04 Request verifikasi (alternatif untuk email existing)

```http
POST {{baseUrl}}/auth/email-verification/request
Authorization: Bearer {{memberToken}}
Content-Type: application/json
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body raw JSON (angka versi adalah variable tanpa kutip):

```json
{
  "currentPassword": "{{memberPassword}}"
}
```

Respons sukses yang diharapkan: **202** (prasyarat pada panduan harus terpenuhi).

### 05 Konfirmasi verifikasi

```http
POST {{baseUrl}}/auth/email-verification/confirm
Authorization: Bearer {{memberToken}}
Content-Type: application/json
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body raw JSON (angka versi adalah variable tanpa kutip):

```json
{
  "token": "{{verifyToken}}"
}
```

Respons sukses yang diharapkan: **204** (prasyarat pada panduan harus terpenuhi).

### 06 Request reset (hanya email verified)

```http
POST {{baseUrl}}/auth/password-reset/request
Content-Type: application/json
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body raw JSON (angka versi adalah variable tanpa kutip):

```json
{
  "identifier": "{{memberIdentifier}}"
}
```

Respons sukses yang diharapkan: **202** (prasyarat pada panduan harus terpenuhi).

### 07 Konfirmasi reset (login ulang sesudahnya)

```http
POST {{baseUrl}}/auth/password-reset/confirm
Content-Type: application/json
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body raw JSON (angka versi adalah variable tanpa kutip):

```json
{
  "token": "{{resetToken}}",
  "newPassword": "{{memberNewPassword}}"
}
```

Respons sukses yang diharapkan: **204** (prasyarat pada panduan harus terpenuhi).

### 08 Ganti password Member

```http
PATCH {{baseUrl}}/member/password
Authorization: Bearer {{memberToken}}
Content-Type: application/json
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body raw JSON (angka versi adalah variable tanpa kutip):

```json
{
  "currentPassword": "{{memberPassword}}",
  "newPassword": "{{memberNewPassword}}"
}
```

Respons sukses yang diharapkan: **204** (prasyarat pada panduan harus terpenuhi).

### 09 Ganti password Coach (opsional)

```http
PATCH {{baseUrl}}/coach/password
Authorization: Bearer {{coachToken}}
Content-Type: application/json
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body raw JSON (angka versi adalah variable tanpa kutip):

```json
{
  "currentPassword": "{{coachPassword}}",
  "newPassword": "{{coachNewPassword}}"
}
```

Respons sukses yang diharapkan: **204** (prasyarat pada panduan harus terpenuhi).

### 10 Refresh Coach (login Coach dahulu)

```http
POST {{baseUrl}}/auth/refresh-session
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body: **none**.

Respons sukses yang diharapkan: **200** (prasyarat pada panduan harus terpenuhi).

### 11 Logout akun yang cookie-nya aktif

```http
POST {{baseUrl}}/auth/logout
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body: **none**.

Respons sukses yang diharapkan: **204** (prasyarat pada panduan harus terpenuhi).

## 08 - Hapus sesi (paling akhir)

Soft-delete sesi uji; sesudahnya detail/media sesi tidak lagi bisa diakses melalui API. Jangan jalankan sebelum review selesai.

### Hapus sesi sumber

```http
DELETE {{baseUrl}}/member/sessions/{{sessionId}}
Authorization: Bearer {{memberToken}}
```

Body kosong jika tidak disebutkan. Jalankan manual sesuai panduan.

Body: **none**.

Respons sukses yang diharapkan: **204** (prasyarat pada panduan harus terpenuhi).
