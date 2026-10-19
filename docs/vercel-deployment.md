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
