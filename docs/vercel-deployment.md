# Deployment Vercel: ukuran bundle dan batas operasional

## Integrasi B2 — 6 November 2026

Adapter B2 dan endpoint direct upload tersedia pada branch `feat/b2-object-storage`.
Ikuti [setup dan kontrak B2](b2-storage.md) sebelum mengaktifkan mode ini. Bagian
filesystem/upload di bawah mencatat kondisi deployment sebelumnya; mode B2
menggunakan upload browser langsung, salinan versi final, worker terpisah dan
playback Range melalui API. File besar tidak lagi dikirim sebagai multipart ke
Vercel. Setup environment, migrasi 0008, CORS, worker dan perubahan FE tetap wajib;
hasil tes terisolasi tidak berarti deployment produksi sudah diperbarui.

## Pengurangan dependency — 19 Oktober 2026

Ukuran virtualenv Windows lokal turun dari **603.856.219 byte (603,9 MB)** menjadi
**419.213.964 byte (419,2 MB)**: hemat **184.642.255 byte (184,6 MB), 30,58%**.
Enam paket sisa instalasi lama (SciPy, scikit-learn, joblib, cloudpickle,
narwhals, threadpoolctl) dihapus melalui pip setelah pemeriksaan reverse
dependency. Paket tersebut memang sudah tidak tercantum dalam manifest proyek.
Salinan pemulihan sementara dibuang setelah seluruh pemeriksaan berhasil.

`requirements.txt` dan `requirements-lock.txt` kini khusus runtime/produksi.
Pytest, httpx, httpcore, iniconfig, pluggy, dan Pygments dipindahkan ke
`requirements-dev.txt`. Lock produksi berkurang dari 60 menjadi 54 paket;
semua pin yang dipertahankan tetap sama. Daftar paket beserta versi development
tetap sama seperti sebelum perubahan. Gunakan `requirements-dev.txt` untuk tes,
Ruff, dan CLI validasi HTTP `scripts.validate_local`.

OpenCV, NumPy, MediaPipe, Pillow dan dependency transitif wajib tetap dipertahankan.
Metadata MediaPipe mewajibkan matplotlib; paket itu tidak dihapus paksa.
Kode bisnis, endpoint, auth, migrasi, konfigurasi .env dan frontend tidak diubah.

Bukti verifikasi setelah pengurangan:

- `pip check`: tidak ada dependency rusak. Closure lock produksi beserta versi
  terpasang valid; dry-run resolver tanpa network/install berhasil untuk ketiga
  manifest requirements.
- MySQL native pada dua schema acak `*_test` terpisah: **240 passed**, tanpa skip,
  18 warning Alembic yang sudah ada, **568,29 detik**.
- SQLite terisolasi: **222 passed, 18 skipped**, 19 warning deprecation yang sudah
  ada, **60,05 detik**. Skip hanya untuk skenario khusus MySQL.
- Pencatatan HTTP suite MySQL: **44/44 operasi OpenAPI** memiliki respons sukses.
- Uvicorn HTTP nyata dan worker native dengan video sintetis: readiness, upload,
  polling completed, inference MediaPipe, evaluasi, histori, draft/publish Coach
  dan cleanup berhasil. Enam paket yang dihapus serta paket development sengaja
  diblokir pada proses API/worker dan child proses video/inference; empat proses
  mencatat guard aktif. Klien validasi terpisah tetap menggunakan httpx development.
- Snapshot OpenAPI, Ruff critical rules, pemeriksaan format 14 file yang sama
  dengan CI, serta `git diff --check` lulus.
- Tidak memakai Docker, database development/Filess, atau email nyata. Seluruh
  schema sementara sudah dihapus; hasil pemeriksaan metadata: **0 tersisa**.

Angka ukuran berasal dari disk Windows lokal, bukan hasil build Linux/Vercel.
Manifest produksi mengeluarkan enam paket khusus tes; penghematan bundle akhir
perlu diukur pada deployment baru. Tidak ada dependency aplikasi yang dinaikkan
versinya atau fitur yang dinonaktifkan. Pengurangan ukuran ini tidak mengubah
batas upload Functions, menyediakan storage persisten, atau mendeploy worker cloud.
Video sintetis memverifikasi alur sistem, bukan akurasi penilaian teknik silat.

## Perbaikan LAMBDA_SIZE_EXCEEDED

Deployment pengguna melaporkan bundle 586.48 MB, melebihi batas function Python
500 MB pada konfigurasi deployment tersebut. Ukuran mencakup dependency terpasang,
bukan hanya source Git. Menghapus video/model dari Git saja tidak cukup.

Audit import app/scripts/tests tidak menemukan penggunaan scikit-learn atau joblib.
Kedua dependency langsung itu dihapus dari requirements.txt. Pin transitif yang
khusus ditariknya (SciPy, cloudpickle, narwhals dan threadpoolctl) juga dihapus dari
requirements-lock.txt. MediaPipe/OpenCV/NumPy tetap ada; matplotlib tetap diperlukan
oleh metadata dependency MediaPipe, sehingga tidak dihapus paksa.

.vercelignore dan excludeFiles untuk entrypoint app/main.py di vercel.json
mengecualikan virtualenv, cache, data/media lokal, dataset, model
.task privat/lokal, .env, tes dan dokumentasi. Source app, migrasi, requirements dan
script tetap tersedia. .python-version menetapkan Python 3.12 sesuai pengujian
native. Perubahan ini tidak menghapus file lokal atau mengubah
database/.env/model analisis.

Langkah penerapan:

1. Commit/push perubahan dependency, .vercelignore, vercel.json dan .python-version.
2. Di Vercel, deploy commit terbaru. Saat Redeploy, nonaktifkan penggunaan existing
   Build Cache jika opsinya tersedia agar dependency lama tidak ikut dari cache.
3. Periksa Install Command: gunakan requirements.txt atau requirements-lock.txt
   yang telah diperbarui; jangan memakai requirements lama dari commit sebelumnya.
4. Periksa ulang ukuran bundle di build log. Ukuran akhir harus diverifikasi di
   Linux/Vercel; ukuran site-packages Windows lokal bukan ukuran bundle Vercel.

## Bukti pemeriksaan lokal

- Audit import app/scripts/tests: tidak memakai enam package yang dihapus.
- Closure dependency berdasarkan metadata paket terpasang: semua dependency wajib
  dari root requirements tetap memiliki pin; tidak membutuhkan paket yang dihapus.
- Regresi SQLite native dengan import sklearn/scipy/joblib/cloudpickle/narwhals/
  threadpoolctl sengaja diblokir melalui sitecustomize, termasuk pada child process:
  **219 passed, 18 skipped, 19 warnings, 47.61 detik**. Kedua URL tes MySQL dikosongkan
  dan SMTP nyata disabled; tidak memakai database development.
- Snapshot OpenAPI tetap cocok; API/schema aplikasi tidak diubah.

Pemeriksaan metadata memakai environment Windows yang sudah terpasang; bukan
instalasi Linux baru atau pengukuran bundle Vercel. Deployment belum dijalankan
dari tugas ini, sehingga hasil ukuran akhir dan keberhasilan hosting belum diklaim.

Jangan menghapus scipy/sklearn secara manual dari direktori paket setelah pip
install. Perubahan manifest memastikan paket tidak diminta lagi, sehingga
dependency resolver dapat menjaga konsistensi instalasi.

## Deployment berhasil bukan berarti seluruh alur video siap

Penurunan bundle belum menyelesaikan kebutuhan operasional backend:

- DATABASE_URL harus menunjuk MySQL online yang sesuai; localhost Vercel bukan
  MySQL di laptop pengguna. Migrasi perlu dilakukan ke target yang benar.
- Worker CLI dan cleanup perlu lingkungan eksekusi tersendiri. Upload 202 akan
  tetap queued jika worker tidak berjalan.
- Storage sekarang berupa filesystem privat bersama API/worker. Deployment
  Functions memerlukan adapter storage persisten bersama sebelum alur video
  dapat digunakan lintas instance/restart; tidak cukup mengganti MEDIA_ROOT ke /tmp.
- Endpoint upload sampai 100 MiB tidak bisa langsung melewati batas body Functions
  4.5 MB. Upload langsung ke object storage dan alur finalize/validasi membutuhkan
  perubahan kontrak/implementasi tersendiri, bukan sekadar menaikkan konfigurasi.
- Library inference dan file model hanya disiapkan di lingkungan yang memang
  menjalankan worker. Tidak ada worker otomatis hanya karena API terdeploy.

Rujukan resmi: [Python runtime](https://vercel.com/docs/functions/runtimes/python),
[batas Functions](https://vercel.com/docs/functions/limitations).

Dokumentasi Vercel juga menawarkan Large Functions beta untuk project yang
memenuhi syarat, tetapi error pengguna masih menunjukkan batas 500 MB. Jangan
menganggap fitur tersebut aktif atau bahwa kenaikan batas bundle menyelesaikan
worker, storage dan upload. Verifikasi eligibility/kuota di project sebelum
menggunakan opsi itu.

## FUNCTION_INVOCATION_FAILED karena libxcb.so.1

Log runtime pengguna menunjukkan kegagalan import app/main.py melalui rantai
api/sessions → services/sessions → services/video → cv2, dengan pesan
`ImportError: libxcb.so.1: cannot open shared object file`. Import OpenCV native
terjadi bahkan ketika browser hanya meminta / atau favicon.

Perbaikan: services/video.py tidak lagi mengimpor cv2 pada level modul. Whitelist
format video dapat diimpor API tanpa memuat library native; cv2 dimuat hanya saat
sampled_frames dipakai untuk decoding. MediaPipe sebelumnya sudah dimuat secara
lazy di konstruktor extractor. Kontrak API dan rumus analisis tidak berubah.

Tes startup pada interpreter baru memblokir semua import cv2/mediapipe dengan
error libxcb yang sama. API harus tetap dapat mengembalikan /health/live, /health,
/docs dan /openapi.json dengan 200, auth tanpa token dengan 401, dan root dengan
404. Ini menguji kegagalan native dependency secara eksplisit, bukan hanya
menjalankan tes di Windows yang kebetulan memiliki library OpenCV lengkap.

Regresi aktual native SQLite: **220 passed, 18 skipped, 19 warnings, 47.28 detik**
melalui `pytest -q --basetemp=.cache/vercel-native-import-regression --tb=short`.
TEST_DATABASE_URL dan MIGRATION_TEST_DATABASE_URL dikosongkan; MAIL_ADAPTER=disabled.
Tidak ada database development, email nyata atau Docker yang digunakan. Ruff
critical rules dan pemeriksaan snapshot OpenAPI lulus. Vercel belum dideploy ulang
dari tugas ini, sehingga hasil remote perlu diperiksa setelah commit/push.

Commit/push perubahan dan deploy commit terbaru. Jika memakai Redeploy, pilih
commit yang memuat perbaikan; redeploy commit lama tidak mengubah rantai import.
Nonaktifkan existing Build Cache jika perlu agar runtime tidak memakai artefak
deployment lama. Setelah deploy, buka /health/live dan /docs. Root / tidak
memiliki halaman aplikasi, sehingga 404 pada root adalah respons yang wajar.

Perbaikan ini mengisolasi startup API dari dependency video. Library native tetap
harus tersedia di lingkungan yang menjalankan decoding/inference. Ini tidak
mengklaim upload/worker/media sudah siap dipakai di Vercel; persyaratan storage,
database online dan batas payload pada bagian sebelumnya tetap berlaku.
