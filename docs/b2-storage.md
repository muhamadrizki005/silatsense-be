# Penyimpanan privat Backblaze B2

Implementasi ini menambahkan adapter `b2`; default `local` dan endpoint multipart
native tetap tersedia. B2 menyimpan video, bukan menjalankan inference. Worker
dan cleanup harus dijalankan terpisah dengan database dan bucket yang sama.
Jangan menganggap `/health/ready` sebagai bukti worker sedang hidup.

## Konfigurasi

Bucket yang disiapkan: `silatsense-media-rizki`, Private, Object Lock disabled.
Endpoint dari dashboard pengguna: `s3.us-west-004.backblazeb2.com`.
Gunakan application key Read and Write yang dibatasi pada bucket tersebut.

Isi pada environment API Vercel **dan** worker/cleanup:

```dotenv
STORAGE_ADAPTER=b2
B2_ENDPOINT_URL=https://s3.us-west-004.backblazeb2.com
B2_REGION=us-west-004
B2_BUCKET=silatsense-media-rizki
B2_KEY_ID=<keyID>
B2_APPLICATION_KEY=<applicationKey>
POSE_MODEL_SHA256=<sha256 artifact pose yang dipakai worker>
```

`DATABASE_URL` tetap MySQL online yang sama. Di worker, `POSE_MODEL_PATH` menunjuk
file `.task` lokal yang sebenarnya. API tidak perlu membawa file model ke Vercel.
Ambil checksum dengan PowerShell:

```powershell
(Get-FileHash -Algorithm SHA256 artifacts/pose/pose_landmarker_lite.task).Hash.ToLower()
```

Model worker harus memiliki checksum tersebut; path worker boleh berbeda dari API.
Jangan menaruh key, token, URL upload bertanda tangan, atau video privat di Git/log.
Environment lokal `.env` tidak diubah otomatis oleh implementasi ini.

Pasang dependensi dan migrasikan secara eksplisit ke database target yang benar:

```powershell
python -m pip install -r requirements-dev.txt
python -m alembic upgrade head
python -m alembic check
```

Migrasi baru `0008` menambahkan `direct_uploads` dan membuat metadata durasi/resolusi
nullable sebelum validasi worker; data existing dipertahankan. Jangan jalankan
migrasi produksi hanya untuk mencoba koneksi. Backup dan pastikan target URL.
Aktifkan deployment API/worker baru setelah migrasi berhasil.

Untuk menjaga fungsi lokal, biarkan `STORAGE_ADAPTER=local`. Mengganti adapter
tidak memindahkan video existing: semua proses harus menggunakan satu adapter
yang sama. Selesaikan/arsipkan antrean dan video lokal sebelum beralih; histori
hasil analisis di MySQL tetap tersimpan. Jangan bolak-balik adapter pada antrean aktif.

## CORS bucket

Browser mengirim video langsung ke B2. Tambahkan CORS untuk origin FE yang tepat
(development dan deployment), metode PUT, header Content-Type. CORS backend
sendiri tidak menggantikan CORS bucket. Contoh S3 CORS melalui boto3:

```python
from app.services.storage import B2Storage

storage = B2Storage()
storage.client.put_bucket_cors(
    Bucket=storage.bucket,
    CORSConfiguration={"CORSRules": [{
        "AllowedOrigins": ["http://localhost:3000", "https://DOMAIN-FE-KAMU"],
        "AllowedMethods": ["PUT"],
        "AllowedHeaders": ["content-type"],
        "MaxAgeSeconds": 300,
    }]},
)
```

Ganti domain sebelum menjalankan; contoh mengganti konfigurasi CORS bucket, jadi
gabungkan aturan existing jika ada. Key tetap hanya pada server. Bucket tetap Private.

## Perubahan integrasi frontend

Endpoint baru di bawah `/api/v1`, auth Member dan pemeriksaan Origin yang sama:

1. `POST /api/v1/member/uploads`, JSON dengan Bearer dan `Idempotency-Key`.
2. `PUT uploadUrl` langsung ke B2, **raw File/Blob**, bukan FormData. Pakai
   `headers` dari response; jangan teruskan Bearer/cookie backend. Browser
   menetapkan Content-Length dari File/Blob; jangan mengaturnya manual.
3. Setelah PUT berhasil, `POST completePath` dengan Bearer, tanpa body.
4. Response 202 berisi `sessionId`, `statusUrl`, `evaluationUrl` yang sama dengan
   alur sesi existing. Poll status; hasil evaluasi/media belum tersedia seketika.

Contoh request init (checksum wajib SHA256 isi file, bukan nama file):

```json
{
  "movementSlug": "pukulan",
  "filename": "latihan.mp4",
  "mimeType": "video/mp4",
  "byteSize": 123456,
  "sha256": "<64 karakter hex lowercase SHA256 file>",
  "retryOf": null
}
```

Contoh browser setelah mendapatkan File:

```javascript
const bytes = await file.arrayBuffer();
const digest = await crypto.subtle.digest("SHA-256", bytes);
const sha256 = Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, "0")).join("");
// Kirim init lewat auth bridge FE yang sudah disepakati.
// ticket adalah JSON dari endpoint init; jangan log ticket.uploadUrl.
if (ticket.acceptedSession) return ticket.acceptedSession;
const put = await fetch(ticket.uploadUrl, {
  method: "PUT", headers: ticket.headers, body: file, credentials: "omit",
});
if (!put.ok) throw new Error("Upload ke storage gagal");
// Panggil ticket.completePath melalui bridge dengan Bearer server per request.
```

Ini contoh integrasi, bukan perubahan kode frontend. `crypto.subtle` memerlukan
HTTPS atau localhost. Hash contoh di atas memakai memori sebesar file; untuk
perangkat terbatas FE dapat memakai implementasi hash incremental yang ditinjau.

Init idempotent per user dan key: payload sama memperoleh uploadId sama sampai
TTL habis, payload berbeda 409. Default TTL 300 detik. Setelah complete, init
dengan key sama mengembalikan `acceptedSession`, `uploadUrl=null`; jangan PUT lagi.
Complete idempotent: retry mengembalikan sesi yang sama. Key baru untuk unggahan
baru/expired. Tidak ada URL PUT baru setelah reservasi habis. Kuota pending dan
byte mencakup reservasi. Cleanup wajib melepaskan reservasi kedaluwarsa.

Ukuran dan Content-Type terikat signature; complete memeriksa HEAD storage,
memilih VersionId, lalu menyalin versi itu ke objek final yang tidak memiliki URL
PUT publik. Memakai ulang signed URL hanya dapat menambah versi staging, bukan
mengubah media sesi. Checksum, container, durasi, resolusi dan decoding diverifikasi
worker; sebelum itu metadata nullable dan media tidak bisa diputar. Jangan tampilkan
status queued sebagai video sudah valid. File tidak valid menjadi sesi failed.

Endpoint lama `POST /member/sessions` tetap multipart pada mode local. Pada mode
b2 endpoint itu mengembalikan 503 `direct_upload_required`; FE wajib memakai alur
baru. Menambah environment B2 saja tidak memperbaiki FE yang masih multipart.

## Playback dan retensi

Playback tetap melalui endpoint `/member/sessions/{sessionId}/video` atau endpoint
Coach existing, dengan pemeriksaan hak akses, authVersion, assignment dan deadline
selama stream. Tidak ada public bucket atau URL GET bertanda tangan yang melewati
pencabutan hak akses. Range diteruskan ke storage, tidak mengunduh seluruh video.
Untuk B2, tiap response Range dibatasi 4 MiB agar tetap di bawah batas payload
Functions. Player harus melanjutkan Range sesuai Content-Range. GET tanpa Range
untuk file lebih besar mengembalikan 413 `media_range_required`. Uji player FE nyata
di deployment; object storage tidak menghapus batas response proxy Vercel.

Deadline media adalah tepat 24 jam sejak LastModified versi upload di B2, bukan
24 jam sejak worker selesai. Hasil analisis dan feedback tetap ada. Cleanup
menghapus seluruh versi objek/delete marker secara idempotent, termasuk staging
yang tertinggal/diunggah ulang. Bucket default Keep all versions tidak otomatis
melaksanakan retensi aplikasi. Jalankan cleanup teratur, jangan hanya mengandalkan
deadline akses untuk mengurangi tagihan storage. Object Lock harus disabled.

```powershell
python -m scripts.worker
python -m scripts.cleanup_media
```

Worker mengunduh ke temporary directory privat, memverifikasi SHA256, melakukan
probe, memperbarui metadata dengan fencing claim, lalu memakai analyzer existing.
File sementara dihapus saat sukses/gagal. Lease di-heartbeat selama download dan
inference; probe bounded timeout. Default concurrency tetap satu. Sediakan ruang
disk sementara dan dependency CV/model pada host worker; tidak diperlukan Docker.

`GET /health/ready` mengecek revisi 0008, operasi write/read/delete B2 dan adanya
checksum model. Pemeriksaan ini mengonsumsi operasi B2; gunakan probe secukupnya.
`workerConfiguration=ok` berarti konfigurasi tersedia, bukan worker aktif atau model
telah divalidasi di host worker. Periksa antrean melalui `python -m scripts.queue_status`.

## Verifikasi dan keterbatasan

Tes adapter memakai object service ber-versi dalam memori; tes signature memakai
SDK boto3 asli dengan kredensial dummy tanpa jaringan. Ada tes download, checksum,
probe video nyata, Range, owner isolation, quota, retry dan expiry. Tes migrasi
SQLite memeriksa upgrade/downgrade dan `alembic check` tanpa database pengguna.
Tes MySQL khusus membutuhkan database disposable tersendiri; tidak otomatis
menyentuh Filess. Hasil aktual ada di `docs/b2-verification.md`.

Koneksi ke B2 asli, CORS browser, deployment Vercel, migrasi MySQL online dan host
worker harus diverifikasi setelah environment disiapkan. Kode ini tidak mengklaim
layanan cloud tersebut telah tersambung hanya karena tes terisolasi lulus.

Rujukan: [B2 S3 API](https://www.backblaze.com/docs/cloud-storage-s3-compatible-api),
[Copy Object](https://www.backblaze.com/apidocs/s3-copy-object),
[Boto3 presigned URLs](https://docs.aws.amazon.com/boto3/latest/guide/s3-presigned-urls.html),
[Vercel limits](https://vercel.com/docs/functions/limitations).
