# Integrasi analisis referensi Coach — 23 November 2026

Implementasi pada branch `codex/coach-reference-api`. Ini menghubungkan pipeline
referensi temporal existing ke worker dan API. Belum di-merge, di-push, atau
diaktifkan di Vercel. Tidak ada migrasi, perubahan auth, frontend, database
development/Filess, atau `.env` pengguna. Dependency tidak ditambah.

## Status model dan batas penilaian

Dataset privat pengguna berisi 98 video dari tujuh Coach. Pengguna mengonfirmasi
semua demonstrasi benar dan menyepakati usulan nama gerakan. Dua video dengan nama
gerakan belum jelas disisihkan; tujuh video lain ditolak decoder karena jumlah
frame terbaca berbeda 2–3 frame dari metadata. Video asli tidak dimodifikasi.

Baseline menggunakan 89 video: train 62 (Coach 1–5), validation 15 (Coach 6),
test 12 (Coach 7). Pembagian ditetapkan sebelum ekstraksi; seluruh video dari
seorang Coach tetap di satu split. Seluruh klip seorang Coach juga dikelompokkan
secara konservatif sebagai satu grup rekaman asal.

Model referensi memiliki 12 profil. MediaPipe pretrained mengekstrak pose;
fit mempelajari template fitur temporal dan variasi antar-Coach pada train saja.
Ini bukan training ulang MediaPipe atau neural network baru. Fitur berupa
proyeksi sudut 2D (derajat) dan posisi relatif terhadap panjang torso (rasio).

Classifier nearest-centroid terpisah mengenali 11/15 video validation (73,33%)
dan 9/12 test (75%). Classifier itu **tidak menentukan gerakan penilaian API**;
pengguna memilih `movementId` secara eksplisit. Akurasi pengenalan jenis gerakan
bukan akurasi penilaian teknik.

Pada baseline, 5,57% pengukuran fitur-waktu teramati di validation dan 8,12% di
test diberi warna kuning/merah meskipun seluruh demonstrasi diterima benar.
Ini tingkat penandaan pengukuran, bukan persentase video salah. Percobaan private
memangkas bagian netral meningkatkan tingkat tersebut menjadi 6,36% pada
validation, sehingga **tidak dipakai**. Tidak menaikkan toleransi sekadar untuk
menghilangkan penandaan. Hasil test sebelumnya telah dilihat: jika digunakan
untuk pengembangan lebih lanjut, perlu rekaman baru untuk evaluasi akhir independen.

Karena belum ada rekaman pemula yang dinilai Coach, sensitivitas terhadap
kesalahan dan ketepatan feedback belum terukur. Warna berarti penyimpangan
eksperimental terhadap referensi, bukan keputusan benar/salah atau standar IPSI.
`score=null`, `correctness=null`, dan `qualityAssessmentValidated=false` tetap
berlaku. Penghitungan repetisi serta fase semantik belum tersedia.

## Mode dan kontrak kompatibel

`ANALYSIS_MODE=static` adalah default; analyzer existing tetap bekerja. Mode baru
diaktifkan eksplisit dengan `ANALYSIS_MODE=coach-reference` pada API dan worker.
Empat kategori dan endpoint `/api/v1` dipertahankan. Perubahan DTO bersifat aditif;
tidak menghapus atau mengganti endpoint `/sessions` maupun `/uploads`.

GET `/api/v1/member/record-config/{slug}` kini juga memberikan:

```json
{
  "movementIdRequired": true,
  "analysisMethod": "coach-reference-dtw",
  "movements": [
    {"id": "pukulan_depan", "name": "Pukulan depan / lurus"},
    {"id": "pukulan_melingkar", "name": "Pukulan melingkar"},
    {"id": "pukulan_bandul", "name": "Pukulan bandul / sangkol"}
  ]
}
```

Ini potongan field tambahan; field batas upload existing tetap disertakan.
Daftar untuk kategori lain mengikuti `movement_catalog.py`. Mapping kategori
publik `kuda-kuda` ke internal `kuda_kuda` tetap berlaku.

Dalam mode baru, `capability.scoringAvailable=false`,
`referenceComparisonAvailable=true` jika checksum referensi dikonfigurasi,
`method=coach-reference-dtw`, dan `reason=correctness_not_validated`.
Capability/readiness API memeriksa konfigurasi, bukan keberadaan proses worker
atau artifact di mesin worker. Gunakan verifier di mesin worker untuk itu.

## Upload dan versi pekerjaan

Direct upload B2 tetap memakai:

1. POST `/api/v1/member/uploads`, Bearer + `Idempotency-Key`; tambah
   `"movementId":"pukulan_depan"` pada body existing kategori `pukulan`.
2. PUT file mentah ke URL B2 yang diberikan, tanpa Bearer/cookie backend.
3. POST `/api/v1/member/uploads/{uploadId}/complete` → sessionId.
4. Poll GET `/api/v1/member/sessions/{sessionId}`.

Upload lokal POST `/api/v1/member/sessions` juga menerima field multipart
`movementId`. POST multipart ini tetap dinonaktifkan dalam mode storage B2.

`movementId` wajib pada mode Coach dan harus sesuai kategori. Target yang hilang
menghasilkan 422 `movement_id_required`; target salah 422 `invalid_movement_id`.
Checksum referensi belum dikonfigurasi: 503 `reference_configuration_required`.
Mengubah target dengan key idempotensi yang sama menghasilkan conflict.

Saat reservasi B2 dibuat, konfigurasi analyzer, target, checksum pose dan checksum
referensi dibekukan dalam metadata request privat. Complete menggunakan snapshot
tersebut, sehingga perubahan deployment tidak mengubah arti upload yang sedang
berjalan. Reservasi legacy tanpa snapshot tetap memakai analyzer statis legacy.
Fingerprint request tanpa movementId tetap kompatibel dengan versi sebelumnya.

Worker memverifikasi hash artifact pose dan referensi sebelum inference.
Artifact hilang/tidak valid: `reference_model_unavailable`; hash tidak cocok:
`reference_version_unavailable`. Tidak diam-diam memakai model lain. Sebelum
mengganti artifact aktif, selesaikan antrean versi lama; mengganti path ke model
baru sementara job lama masih berjalan dapat membuat job tersebut gagal eksplisit.

## Hasil evaluasi dan overlay

GET `/api/v1/member/sessions/{sessionId}/evaluation` mempertahankan field lama
dan menambahkan `coachComparison` (null untuk evaluasi lama/statis):

- `method=coach-reference-dtw`.
- `analysisStatus=reference_compared` bila perbandingan berhasil. Status ini
  **boleh dan selalu mempunyai score null**, berbeda dari skor statis experimental.
- `scoreReason=correctness_not_validated` untuk hasil perbandingan yang berhasil.
- `matchedVariant` menunjukkan target yang diminta, bukan hasil klasifikasi otomatis.
- `referenceVersion` adalah SHA256 artifact yang dipakai.
- `coachComparison`: movementId, status, toleranceStatus, alignmentDistance,
  frames (maksimal 32), dan ringkasan fitur dengan jumlah sampel/coverage.
- Setiap frame: timeSeconds, referenceTimeSeconds, phase nullable, features dan
  joints. Setiap pengukuran: value, referenceValue, deviation absolut, unit,
  color nullable, reason. Joints juga memuat landmarkIndices dan feedbackCode.
- Unit baru `torso_length_ratio` tidak boleh ditampilkan sebagai sentimeter atau
  `shoulder_width`. Feature ID adalah nama fitur, bukan nama properti DTO baru.
- ID Coach, sample referensi, path artifact, hash video dataset dan template
  privat tidak dikirim melalui DTO publik.

Jika observasi tidak cukup, status sesi tetap dapat completed dengan
analysisStatus insufficient_pose/insufficient_features dan comparison.status
not_assessable. Ini berbeda dari processingStatus failed untuk kegagalan teknis.
Nilai yang tidak terukur tetap null beserta alasan; tidak diisi dummy.

GET `/api/v1/member/sessions/{sessionId}/pose` mempertahankan `pose` keyframe
existing, dan menambahkan `timeline` pada analisis temporal. Timeline memiliki
imageWidth, imageHeight, coordinateSystem=image-normalized, origin=top-left,
maximumInterpolationGapSeconds=0.15 dan paling banyak 900 frame observasi aktual.
Masing-masing memuat frameIndex, timeSeconds dan landmark index/x/y/visibility.
Tidak membuat koordinat z palsu. Filter visibilitas dan batas frame diterapkan;
pose tidak diisi sepanjang interval yang hilang. Frame sangat banyak diambil
berjarak agar payload terbatas; waktu asli setiap observasi dipertahankan.

Untuk FE:

1. Sediakan pilihan gerakan dari record-config dan kirim movementId.
2. Setelah sesi completed, baca evaluation dan pose; gunakan original video
   playback existing. API tidak membuat atau menyimpan MP4 overlay tambahan.
3. Gambar koordinat `x * lebarVideo`, `y * tinggiVideo` pada area gambar video,
   dengan penyesuaian letterbox/object-fit; jangan memakai ukuran layar mentah.
4. Gunakan landmarkIndices dan warna dari comparison untuk garis sendi. Jangan
   memakai pose melewati gap 0,15 detik atau mengekstrapolasi warna jauh dari waktu
   pengukuran. Perbandingan temporal beresolusi 32 titik; jarak waktu antarbin
   membesar pada video panjang. Abu-abu/tanpa garis untuk yang belum dinilai.
5. Garis yang dipakai beberapa sendi mengambil warna paling tinggi merah > kuning
   > hijau. Tangani not_assessable dan tampilkan penjelasan eksperimental.
6. Jangan mengubah null menjadi skor nol, label teknik salah, atau jumlah repetisi.

Hak akses Member/Coach, transfer binaan, Range, masa akses video tepat 24 jam,
dan akses hasil setelah video kedaluwarsa tetap memakai layanan existing.
Hasil juga tersedia pada detail histori dan detail sesi Coach. Statistik tidak
menganggap hasil score null sebagai sampel skor yang sebanding.

## Menyiapkan worker native

Artifact model dan dataset tetap privat di `.cache`/`.data`, di luar Git.
Artifact referensi yang sudah dihasilkan pada laptop ini:
`.cache/coach-baseline-20261123/reference-model.json`.
Pose model: `artifacts/pose/pose_landmarker_lite.task`.

API Vercel hanya memerlukan konfigurasi mode/checksum, bukan file model atau
dataset. Worker harus memiliki kedua artifact, dependency yang sama dengan
extractionSignature, serta koneksi MySQL/B2 yang sama dengan API. Jangan
menggunakan SQLite untuk worker produksi. Satu proses inference adalah default.

Contoh PowerShell pada laptop, dari root backend, dengan environment hanya untuk
terminal tersebut (tidak mengubah `.env`):

```powershell
$env:ANALYSIS_MODE = "coach-reference"
$env:COACH_REFERENCE_MODEL_PATH = (Resolve-Path ".cache/coach-baseline-20261123/reference-model.json").Path
$env:COACH_REFERENCE_SHA256 = (Get-FileHash -LiteralPath $env:COACH_REFERENCE_MODEL_PATH -Algorithm SHA256).Hash.ToLowerInvariant()
$env:POSE_MODEL_PATH = (Resolve-Path "artifacts/pose/pose_landmarker_lite.task").Path
$env:POSE_MODEL_SHA256 = (Get-FileHash -LiteralPath $env:POSE_MODEL_PATH -Algorithm SHA256).Hash.ToLowerInvariant()
python -m scripts.verify_coach_model
```

Verifier memeriksa schema, checksum artifact pose/referensi dan versi dependency;
tidak mengakses DB/B2 atau menampilkan secret. Verifikasi artifact berhasil bukan
bukti model akurat pada pengguna pemula.

Untuk worker online, gunakan mesin yang dapat menjalankan Python persisten dan
mengakses internet. Instal dependency sesuai versi artifact, salin artifact
secara privat ke lokasi yang stabil, isi konfigurasi DB/B2/mode/checksum, lalu:

```powershell
python -m scripts.verify_coach_model
python -m scripts.queue_status
python -m scripts.worker --once
python -m scripts.worker
```

`--once` mengambil **pekerjaan nyata** jika ada dalam antrean; jalankan setelah
target DB/storage sudah benar. Worker persisten harus diawasi service manager
host (misalnya systemd pada Linux), direstart ketika gagal, serta memiliki akses
ke artifact. Cleanup tetap proses terpisah `python -m scripts.cleanup_media`.
Kode lease/heartbeat/fencing/retry existing tidak diganti.

Pengguna memilih laptop sebagai worker sementara. File privat `.env.worker`
sudah disiapkan terpisah, berisi target Filess/B2 dan lokasi artifact lokal;
`.env` development tetap utuh. Artifact referensi disalin ke `.data/models/`
dengan nama berdasarkan SHA256. Keduanya diabaikan Git.

Pemeriksaan nyata `python -m scripts.worker --env-file .env.worker --check`
berhasil: model kompatibel, database terhubung pada migrasi 0008 dan probe B2
berhasil. Probe menulis/membaca marker kecil lalu menghapus seluruh versinya;
tidak mengambil pekerjaan, tidak mengubah schema/data aplikasi, dan tidak
menjalankan cleanup terhadap video existing. `workerActive=false` pada output
memang berarti proses persisten belum dimulai.

Setelah kode di-merge/deploy dan FE siap mengirim movementId, atur di Vercel:

```dotenv
ANALYSIS_MODE=coach-reference
COACH_REFERENCE_SHA256=b4f0cf199c039fefda9af4341c142fc5f0574dc9bbc0c9bdb6bf69d8a0a200c5
```

Pertahankan DATABASE_URL/B2/POSE_MODEL_SHA256 yang sesuai worker. API tidak
memerlukan file COACH_REFERENCE_MODEL_PATH; file tersebut hanya diperlukan
worker. Redeploy, lalu periksa record-config: movementIdRequired harus true dan
analysisMethod coach-reference-dtw. Jangan aktifkan mode ini sebelum FE mampu
mengirim target, karena upload tanpa movementId akan ditolak secara eksplisit.

Jalankan dari root backend, pada terminal laptop:

```powershell
python -m scripts.worker --env-file .env.worker --check
python -m scripts.queue_status --env-file .env.worker
python -m scripts.worker --env-file .env.worker
```

Terminal lain untuk cleanup, setelah memastikan target DB/B2 benar:

```powershell
python -m scripts.cleanup_media --env-file .env.worker
```

Laptop dan koneksi internet harus tetap aktif; Ctrl+C menghentikan proses.
Jangan mengandalkan worker laptop untuk layanan 24 jam. Jika laptop berhenti,
upload tetap dapat masuk antrean dan diproses saat worker kembali, selama media
belum kedaluwarsa. Tidak otomatis membuat scheduled task, Windows service, atau
memulai proses permanen pada sesi ini.

Tidak ada provider baru, langganan, pengaturan akun, atau layanan cloud yang dibuat.
Readiness yang ok tidak membuktikan ada worker aktif; periksa queue_status dan
latensi/umur pekerjaan pada host setelah mengirim upload uji.

## Pengujian dan pekerjaan tersisa

Bukti rinci eksekusi native dicatat pada `coach-reference-verification.md`.
Tes otomatis memakai data sintetis, SQLite/storage sementara dan mock B2;
smoke video asli memakai 12 video Coach terpisah dengan child MediaPipe nyata.
Pengecekan kesiapan worker laptop juga mengakses Filess/B2 seperti dijelaskan
di atas; pengujian alur video tetap lokal dan tidak mengunggah dataset ke cloud.

Sebelum menyebut koreksi tervalidasi: kumpulkan rekaman pemula yang memiliki
catatan kesalahan dari Coach, ukur kesesuaian feedback serta penandaan pada
contoh benar, dan lakukan evaluasi akhir pada rekaman baru yang belum dipakai
untuk memilih perubahan. Integrasi tampilan tetap pekerjaan FE; dokumentasi ini
menyediakan kontrak data yang sudah tersedia di backend.
