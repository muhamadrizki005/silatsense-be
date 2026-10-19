# Deployment Vercel: ukuran bundle dan batas operasional

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
