# Pipeline offline untuk 12 gerakan

Status: pipeline pengenalan jenis gerakan tersedia, belum ada model terlatih dari dataset nyata yang memadai. Pipeline ini berada dalam `app/intelligence`, dengan CLI di `scripts/movement_pipeline.py`. Tidak mengubah API, empat kategori katalog publik, database, worker, frontend, atau aturan skor existing. Tidak menambah dependency produksi.

## Daftar label yang disepakati

Nama video merupakan pemetaan referensi lokal, bukan data yang dimasukkan ke Git.

| movementId | Kategori API internal | Nama | Video referensi |
| --- | --- | --- | --- |
| pukulan_depan | pukulan | Pukulan depan / lurus | pukulan 1.mp4 |
| pukulan_melingkar | pukulan | Pukulan melingkar | pukulan 2.mp4 |
| pukulan_bandul | pukulan | Pukulan bandul / sangkol | pukulan 3.mp4 |
| tendangan_depan | tendangan | Tendangan depan / lurus | tendangan 1.mp4 |
| tendangan_sabit | tendangan | Tendangan sabit | tendangan 2.mp4 |
| tendangan_t | tendangan | Tendangan T / samping | tendangan 3.mp4 |
| kuda_kuda_tengah | kuda_kuda | Kuda-kuda tengah | kuda kuda 1.mp4 |
| kuda_kuda_depan | kuda_kuda | Kuda-kuda depan | kuda kuda 2.mp4 |
| kuda_kuda_samping | kuda_kuda | Kuda-kuda samping | kuda kuda 3.mp4 |
| tangkisan_atas | tangkisan | Tangkisan atas | tangkisan 1.mp4 |
| tangkisan_dalam | tangkisan | Tangkisan dalam | tangkisan 2.mp4 |
| tangkisan_bawah | tangkisan | Tangkisan bawah | tangkisan 3.mp4 |

Identifikasi visual awal beberapa video memiliki ketidakpastian sudut kamera; pengguna kemudian menyetujui nama tersebut sebagai label kerja. Simpan provenance `user_confirmed_reference`; jangan ubah menjadi `coach_review` tanpa review sebenarnya. Penamaan tidak mengesahkan kualitas teknik.

Kategori publik `kuda-kuda` tetap dipetakan menjadi `kuda_kuda`. `movementId` di atas adalah label offline; tidak otomatis menjadi ID/slug endpoint baru.

## Format dataset

Salin header `docs/templates/movement-dataset.csv` ke folder privat seperti `.cache/my-dataset/manifest.csv`. Satu baris mewakili satu video berisi satu repetisi lengkap, dari sikap normal hingga kembali normal. Satu frame bukan satu sampel independen.

| Field | Isi |
| --- | --- |
| sampleId | ID unik video/sampel |
| participantId | Identitas pseudonim orang yang sama, konsisten di seluruh rekaman |
| recordingId | Identitas rekaman asal; semua potongan dari rekaman sama memakai ID sama |
| split | train, validation, atau test |
| movementId | Salah satu dari 12 label di atas |
| labelSource | coach_review atau user_confirmed_reference |
| qualityLabel | unlabeled, correct, atau needs_correction; dua terakhir hanya dengan coach_review |
| observationsPath | Path JSON hasil ekstraksi, relatif terhadap data-root |

Contoh satu baris referensi, bukan dataset training lengkap:

```csv
sampleId,participantId,recordingId,split,movementId,labelSource,qualityLabel,observationsPath
reference-punch-01,coach-01,recording-punch-01,train,pukulan_depan,user_confirmed_reference,unlabeled,observations/pukulan_depan.json
```

`movementId` adalah target pengenalan gerakan. `qualityLabel` adalah metadata terpisah yang **tidak dipakai oleh trainer ini**. Jangan menyimpulkan model benar/salah dari prediksi nama gerakan.

Validasi menolak ID ganda, salinan byte video yang sama, path keluar data-root, metadata ekstraksi berbeda, dan peserta/rekaman asal yang muncul di lebih dari satu split. Hash tidak mendeteksi semua video hasil encoding ulang; participantId/recordingId yang jujur tetap diperlukan. Jangan mengacak frame dari satu orang ke tiga split.

Trainer mengharuskan seluruh 12 kelas tersedia pada tiap split, minimal dua video per kelas di train dan satu di validation/test. Minimum strukturalnya 48 video, **bukan rekomendasi kecukupan dataset atau jaminan generalisasi**. Diperlukan peserta berbeda antar-split, variasi peserta/repetisi yang lebih luas, serta jumlah yang ditentukan melalui evaluasi. Semua video dari satu Coach harus tetap dalam satu split, meskipun gerakannya berbeda.

## Fitur dan urutan waktu

Ekstraksi menggunakan MediaPipe pretrained existing, mode IMAGE per frame, maksimum dimensi 1280 px, target sampling 15 FPS melalui stride frame. FPS efektif dapat berbeda mengikuti FPS sumber; waktu disimpan sebagai frameIndex/containerFPS. Video dibatasi 60 detik, hanya satu orang, kamera depan tetap sesuai kesepakatan; posisi kamera merupakan asumsi input yang belum otomatis diverifikasi.

Terdapat 18 fitur bersama:

- Sudut siku, bahu, pinggul, dan lutut kiri/kanan: derajat proyeksi 2D.
- Posisi x/y pergelangan relatif bahu dan pergelangan kaki relatif pinggul: rasio panjang torso.
- Jarak antarkedua pergelangan kaki: rasio panjang torso.
- Kemiringan torso: derajat proyeksi 2D.

Normalisasi panjang torso mengurangi pengaruh translasi/skala gambar. Tidak menormalkan pergantian sudut kamera, arah tubuh, handedness atau rotasi ruang. Sisi kiri/kanan tidak otomatis dicerminkan.

`FAMILY_FEATURES` mengelompokkan fitur lengan untuk pukulan/tangkisan, tungkai dan pinggul untuk tendangan, serta lutut/posisi kaki untuk kuda-kuda. Classifier menggunakan gabungan fitur yang sama untuk semua video: label gerakan tidak dipakai untuk memilih fitur saat inferensi, sehingga tidak membocorkan target.

Landmark tidak terlihat, di luar gambar, pose ambigu, atau geometri degenerat menghasilkan `null` beserta alasan. World landmark 3D, sentimeter, kecepatan fisik, gaya dan skor IPSI tidak dihasilkan. Sudut proyeksi bukan pengukuran biomekanika 3D tervalidasi. Keluaran tidak menilai teknik benar/salah.

Urutan diubah menjadi 32 titik waktu relatif memakai observasi terdekat; jarak lebih dari 0,15 detik tetap missing. Tidak menginterpolasi gap panjang. Minimal delapan frame teramati dan coverage fitur keseluruhan 50% diperlukan. Ini filter kelayakan teknis, bukan batas kebenaran teknik; fitur pada fase penting tetap perlu diperiksa. Belum ada segmentasi fase atau penyelarasan otomatis puncak gerakan. Video dengan jeda netral berbeda dapat mengurangi performa baseline.

## Training, evaluasi, dan artifact

Baseline NumPy nearest-centroid mempelajari rata-rata pola temporal tiap kelas, bukan jaringan saraf baru. Temporal vector berisi 32 × 18 fitur. Nilai hilang diimputasi hanya pada matriks internal memakai mean train; mask missingness ikut masuk ke model. Mean, standardisasi, dan centroid dihitung **hanya dari train**. Dimensi yang seluruhnya missing di train memiliki count 0 dan fallback internal 0, bukan observasi tubuh buatan. JSON observasi tetap menyimpan null. Count tersebut tersedia dalam artifact untuk audit.

Konfigurasi baseline tetap; validation dan test tidak dipakai fitting atau pemilihan parameter. Laporan memuat accuracy, macro-F1, confusion matrix, precision/recall/F1 per kelas dan jumlah sampel. Bekukan pilihan berdasarkan train/validation sebelum evaluasi test final; jangan terus mengubah model berdasarkan skor test yang sama.

Artifact JSON menyimpan jenis/versi model, urutan fitur/unit, konfigurasi ekstraksi, hash model pose, hash dataset, normalisasi train, centroid, dan hasil evaluasi. Load menolak dimensi/versi/config berbeda, NaN/Infinity, dan scale tidak positif. JSON dipakai tanpa pickle. Keluaran prediksi berisi movementId, distance, confidence=null, qualityAssessment=null dan experimental=true. Distance bukan probabilitas atau skor kualitas.

Baseline bersifat closed-set: video gerakan di luar daftar masih dapat dipetakan ke salah satu kelas. Belum mendukung deteksi unknown/OOD, validasi kualitas, generalisasi pengguna baru, maupun integrasi API. `productionReady=false` dipertahankan meski tes perangkat lunak lulus.

## Cara menjalankan secara native

Jalankan dari root backend. Gunakan direktori privat yang diabaikan Git untuk video, observasi, dataset hasil prepare, dan artifact model. Tidak perlu MySQL, SMTP atau Docker.

```powershell
# 1. Ekstrak setiap video; ulangi dengan nama file/output yang berbeda.
.\.venv\Scripts\python.exe -m scripts.movement_pipeline extract --video "C:\path\pukulan 1.mp4" --output .cache/my-dataset/observations/pukulan_depan.json

# 2. Isi manifest dengan label dan identitas peserta/rekaman sebenarnya.
.\.venv\Scripts\python.exe -m scripts.movement_pipeline prepare --manifest .cache/my-dataset/manifest.csv --data-root .cache/my-dataset --output .cache/my-dataset/prepared.json

# 3. Jalankan setelah dataset lengkap, bukan hanya 12 referensi Coach.
.\.venv\Scripts\python.exe -m scripts.movement_pipeline train --dataset .cache/my-dataset/prepared.json --output .cache/my-dataset/model.json

# 4. Ekstrak video baru dengan konfigurasi/model pose yang sama, lalu prediksi.
.\.venv\Scripts\python.exe -m scripts.movement_pipeline predict --model .cache/my-dataset/model.json --observations .cache/my-dataset/observations/new-video.json --output .cache/my-dataset/prediction.json
```

Model pose default adalah `artifacts/pose/pose_landmarker_lite.task`; sediakan lokal melalui mekanisme download existing. Seluruh output memakai file baru dan menolak overwrite. Tidak ada dataset/video/model pose atau artifact training privat yang dikomit. Jangan menaruh output privat di path source code atau menambahkan dengan `git add -f`.

## Bukti verifikasi 30 Oktober 2026

- Ekstraksi native terhadap 12 video asli yang diberikan pengguna: 655 frame sampel; seluruh video dapat dibentuk menjadi temporal vector tanpa menurunkan filter coverage default.
- Coverage fitur bervariasi: fitur terendah pada tendangan T hanya 41,1%; fitur yang hilang tetap null. Lulus filter coverage keseluruhan tidak berarti semua sendi atau fase terukur akurat.
- Manifest referensi berisi 12 sampel, satu participantId, semua di train dan qualityLabel=unlabeled. Prepare berhasil. Trainer menolak karena validation/test belum tersedia dan train belum memenuhi dua sampel per kelas. Tidak membuat model dari referensi tunggal ini.
- Artifact pemeriksaan privat: `.cache/movement-training-12-real-20261030/verification.json` dan `dataset.json`; tidak masuk Git.
- MediaPipe mengeluarkan warning delegate/projection dan kegagalan koneksi telemetry Clearcut pada lingkungan terbatas; proses ekstraksi tetap exit 0. Tidak mengukur akurasi landmark dari warning/coverage tersebut.
- Tes sintetis mencakup pipeline 12 kelas, simpan/muat/prediksi, geometri, skala/translasi, missingness, gap waktu, kebocoran split, metadata/provenance, artifact tidak kompatibel, normalisasi train-only, lifecycle decoder dan CLI output tanpa overwrite. Angka pengenalan fixture sintetis bukan akurasi pada video manusia.

Pemeriksaan akhir:

| Perintah / pemeriksaan | Hasil aktual |
| --- | --- |
| `python -m pytest -q --basetemp=.cache/pytest-movement-merge-final` | 295 passed, 18 skipped, 19 warnings; 62,78 detik |
| Tes baru dalam `tests/test_movement_pipeline.py` | 34 kasus, termasuk dalam hasil di atas |
| Ruff check untuk tujuh modul/script/test Python baru | Lulus |
| Ruff format check untuk tujuh file tersebut | Lulus |
| `python -m ruff check --select E9,F63,F7,F82 app scripts tests alembic` | Lulus |
| `python -m scripts.export_openapi --check` | Snapshot cocok; kontrak API tidak berubah |
| `python -m alembic check` pada database development | Exit 0: No new upgrade operations detected |
| CLI extract dengan video tendangan T asli | Exit 0 |
| CLI prepare → train → predict dengan 48 fixture sintetis | Ketiganya exit 0; model 12 kelas dapat dimuat untuk prediksi |
| CLI train dengan 12 referensi asli | Ditolak karena split/data belum lengkap; tidak membuat artifact model |

Tes aplikasi berjalan native memakai SQLite in-memory; file tes berada dalam basetemp privat. Variabel database tes MySQL tidak disediakan, sehingga 18 pengujian khusus MySQL dilewati. `alembic check` merupakan pemeriksaan read-only terpisah terhadap development, bukan pengganti tes integrasi MySQL. Tidak menjalankan upgrade, tidak mengubah data development, tidak mengirim email eksternal, dan tidak menyalakan Docker. Tes SMTP existing hanya memakai server loopback lokal.

Run full suite pertama di sandbox tidak selesai karena pembatasan lingkungan; dihentikan, lalu suite final dijalankan native di luar sandbox. Pemeriksaan database dalam sandbox juga gagal koneksi sebelum pemeriksaan read-only di luar sandbox berhasil. Warning suite final berasal dari deprecation Starlette/httpx dan konfigurasi path Alembic existing. Log suite final tersedia privat di `.cache/movement-training-12-real-20261030/pytest-full-final.txt`. Artifact model CLI sintetis berada dalam folder `.cache/movement-training-12-synthetic-cli-20261030`, jelas terpisah dari ekstraksi video nyata; tidak dipakai produksi atau di-Git.

## Pekerjaan yang masih membutuhkan data/requirement

Kumpulkan video berlabel dari beberapa peserta dan repetisi dengan kamera sesuai kesepakatan. Review label dan fase penting, lalu pisahkan peserta/rekaman menjadi train/validation/test. Setelah training nyata, bandingkan baseline dan model temporal lain bila hasil menuntutnya. Penilaian benar/salah, rubrik literatur, validasi ukuran sudut, toleransi, dan integrasi worker tetap pekerjaan terpisah; belum dinyatakan selesai oleh pipeline ini.
