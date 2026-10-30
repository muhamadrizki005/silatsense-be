# Pembandingan gerakan dengan referensi Coach benar

## Kesepakatan dan status

Video Coach yang diberikan pengguna diterima sebagai **referensi teknik benar**, begitu pula dataset demonstrasi Coach ahli yang akan dikumpulkan. Tidak perlu meminta ulang konfirmasi benar/salah untuk video tersebut. Target baru: mempelajari pola referensi per gerakan, menyelaraskan gerakan pengguna, dan menjelaskan perbedaan per bagian tubuh. Pengenalan 12 jenis gerakan existing tetap tersedia, tetapi tidak menggantikan pembandingan kualitas terhadap referensi ini.

Implementasi offline berada pada branch `codex/ai-coach-reference-comparison`. Tidak mengubah endpoint, auth, database, skema respons produksi, worker, frontend, maupun dependency. Tidak melakukan merge atau push. Integrasi ke worker/API/frontend belum dilakukan.

Pendekatan ini menggunakan contoh benar untuk mengenali penyimpangan, sejalan dengan konsep [novelty detection](https://scikit-learn.org/stable/modules/outlier_detection.html). Penerapan di sini berupa template temporal dan variasi antardemonstrasi; bukan neural network baru, dan tidak menginstal scikit-learn. Penyelarasan memakai implementasi NumPy DTW dengan batas jalur temporal, berdasarkan prinsip yang dijelaskan dalam [dokumentasi DTW tslearn](https://tslearn.readthedocs.io/en/stable/user_guide/dtw.html); tidak menambah tslearn sebagai dependency.

## Dataset referensi

Gunakan header pada `docs/templates/coach-references.csv`:

```csv
sampleId,participantId,recordingId,split,movementId,referenceSource,observationsPath,annotationsPath
coach-punch-01,coach-01,recording-punch-01,train,pukulan_depan,user_confirmed_coach_demo,observations/punch.json,
```

- Dua belas movementId tetap mengikuti `movement_catalog.py`, tanpa mengubah empat kategori API.
- `referenceSource=user_confirmed_coach_demo` menerima pernyataan pengguna bahwa video merupakan demonstrasi Coach yang benar. Alternatif `coach_reviewed_correct` untuk rekaman yang telah direview. `referenceIsCorrect=true` disimpan secara eksplisit saat prepare.
- Tidak membutuhkan contoh salah untuk membentuk referensi awal. Video pemula tidak dimasukkan sebagai referensi Coach.
- `participantId` adalah ID pseudonim Coach yang sama di semua video; menambah repetisi tidak berarti menambah jumlah Coach independen.
- `recordingId` menyatukan semua potongan rekaman asal. Duplikasi konten video dan kebocoran Coach/rekaman antar-split ditolak. Hash tidak mendeteksi semua encoding ulang; identitas asal yang konsisten tetap penting.
- Path observasi dan anotasi relatif terhadap data-root; path keluar root ditolak.
- `annotationsPath` boleh kosong. Jika ada, gunakan JSON interval fase existing: neutral_start, preparation, execution, recovery, neutral_end dengan startSeconds/endSeconds yang berurutan dan tidak overlap. Fase tidak dibuat-buat bila belum dianotasi.
- Semua video referensi awal dari Coach yang sama tetap di satu split. Validation/test berisi Coach yang berbeda dan tidak dipakai fitting pola maupun toleransi.

## Apa yang dipelajari

`fit` hanya membaca sampel train yang secara eksplisit merupakan referensi benar. Satu demonstrasi per gerakan sudah cukup untuk menyimpan template dan menghitung selisih; tidak memaksakan syarat 48 video milik classifier jenis gerakan.

Setiap template menyimpan urutan fitur 32 titik waktu, metadata asal, dan fase manual bila tersedia. Fitur tetap menggunakan proyeksi 2D dalam derajat atau rasio panjang torso. Pukulan/tangkisan menggunakan fitur lengan; tendangan menggunakan tungkai/pinggul; kuda-kuda menggunakan tungkai, lebar kaki dan torso. Tidak menambahkan angka sentimeter, gaya, atau standar IPSI.

Gerakan pengguna perlu menyebut movementId yang hendak dibandingkan; sistem tidak menebak nama gerakan sebagai pengganti tujuan latihan. Classifier existing dapat dipakai terpisah pada integrasi mendatang.

DTW membandingkan urutan dengan endpoint tetap, band maksimum 6 dari 32 titik, dan penalti langkah non-diagonal. Sudut dibagi 180 dan rasio dibagi 1 untuk menyeimbangkan unit pada pencarian jalur, bukan sebagai ambang benar/salah. Jalur tidak boleh membalik urutan atau berpindah bebas ke fase yang jauh. Median nilai referensi sepanjang pasangan jalur menjadi pembanding lokal. Template dengan jarak alignment terkecil dipilih.

Penyelarasan ini mengompensasi sebagian perbedaan kecepatan, **bukan jaminan identifikasi fase anatomis sempurna**. `referenceTimeSeconds` tersedia untuk inspeksi; `phase=null` bila fase referensi tidak dianotasi. Gerakan dengan fase terlewat, kamera berbeda, gerakan kiri/kanan terbalik, banyak orang, atau occlusion masih perlu pemeriksaan. Warping juga dapat menyembunyikan sebagian kesalahan timing; evaluasi waktu/kecepatan belum tersedia.

Nilai yang hilang tidak diimputasi menjadi ukuran sendi. Kelayakan observasi mengikuti filter pipeline existing, ditambah pasangan fitur kategori teramati minimal 50% dan delapan titik waktu yang cukup teramati. Bila tidak cukup, compare mengembalikan status `not_assessable`. Coverage keseluruhan bukan bukti fase penting terukur akurat.

## Warna dan feedback

Batas warna tidak dihitung dari perbedaan setiap frame video Coach dengan frame lain yang fasenya berbeda. Batas diperkirakan dari residual demonstrasi yang **sudah disejajarkan** antar-Coach:

1. Minimal tiga Coach independen per gerakan untuk estimasi variasi awal. Ini syarat teknis eksperimen, bukan jaminan dataset cukup.
2. Untuk masing-masing Coach, cari template Coach lain yang paling dekat; semua video orang tersebut dikeluarkan dari kandidat pembanding.
3. Ambil kuantil residual 90% dan 99% per fitur untuk tiap Coach, lalu gunakan batas terbesar antar-Coach agar orang dengan banyak repetisi tidak mendominasi hanya karena jumlah rekamannya.
4. Hanya simpan batas jika seluruh Coach menyediakan minimal delapan nilai residual dan `0 < yellowAbove < redAbove`. Variasi yang tidak bisa diperkirakan tetap tanpa toleransi.
5. Selisih di atas redAbove menjadi merah, di atas yellowAbove menjadi kuning, lainnya hijau. Nilai tepat pada batas tidak melampaui batas itu.

Kuantil tersebut adalah kebijakan statistik eksperimen yang masih harus diuji, **bukan batas teknik resmi atau hasil validasi akurasi**. Satu Coach saat ini menghasilkan `toleranceStatus=insufficient_independent_coaches`; ukuran selisih tetap tersedia, sedangkan color tetap null. Tidak ada batas derajat atau rasio default yang dikarang.

Untuk siku/lutut yang memiliki penyimpangan berwarna, feedback membedakan sudut lebih kecil (`lebih_menekuk_dari_referensi`) dan lebih besar (`lebih_lurus_dari_referensi`). Sendi lain memakai kode selisih sudut umum. Ini deskripsi geometri proyeksi, bukan diagnosis sebab kesalahan. Wording pengguna akhir dan visual frontend belum dihubungkan.

Setiap titik waktu memuat nilai pengguna, nilai referensi, deviasi absolut, unit, warna/alasan nullable, indeks landmark dan kode feedback sendi. Ringkasan menyertakan jumlah titik valid, coverage, median/maksimum deviasi, dan jumlah warna per fitur. `correctness=null`, `score=null`, `qualityAssessmentValidated=false`, dan `productionReady=false` dipertahankan: keluaran sekarang adalah kesesuaian referensi eksperimental.

`isReferenceReplay` menandai bila video yang dibandingkan sudah menjadi template. Selisih nol dari replay bukan bukti akurasi pada pengguna baru. Evaluasi held-out menolak Coach, rekaman dan hash video yang tumpang tindih dengan training. Dengan referensi benar saja, evaluator melaporkan tingkat flag pada demonstrasi benar; belum dapat mengukur kemampuan mendeteksi kesalahan pemula, sehingga correctnessAccuracy tetap null.

## CLI native

Semua JSON, video dan artifact model disimpan privat di `.cache`, `.data`, atau `datasets` yang diabaikan Git. Jalankan dari root backend, tanpa Docker, MySQL atau SMTP untuk pipeline AI ini.

```powershell
# Ekstraksi mempertahankan koordinat landmark tambahan untuk overlay.
.\.venv\Scripts\python.exe -m scripts.reference_pipeline extract --video "C:\path\pukulan 1.mp4" --output .cache/coach-data/observations/punch.json

# Isi manifest referensi Coach benar, lalu prepare dan fit.
.\.venv\Scripts\python.exe -m scripts.reference_pipeline prepare --manifest .cache/coach-data/references.csv --data-root .cache/coach-data --output .cache/coach-data/dataset.json
.\.venv\Scripts\python.exe -m scripts.reference_pipeline fit --dataset .cache/coach-data/dataset.json --output .cache/coach-data/model.json

# Ekstrak video pengguna dengan konfigurasi/model pose yang sama.
.\.venv\Scripts\python.exe -m scripts.reference_pipeline extract --video "C:\path\user.mp4" --output .cache/coach-data/user-observations.json
.\.venv\Scripts\python.exe -m scripts.reference_pipeline compare --model .cache/coach-data/model.json --observations .cache/coach-data/user-observations.json --movement pukulan_depan --output .cache/coach-data/comparison.json

# Preview offline; tidak mengubah video asli. Audio tidak disertakan.
.\.venv\Scripts\python.exe -m scripts.reference_pipeline overlay --video "C:\path\user.mp4" --observations .cache/coach-data/user-observations.json --comparison .cache/coach-data/comparison.json --output .cache/coach-data/preview.mp4

# Setelah tersedia split Coach lain:
.\.venv\Scripts\python.exe -m scripts.reference_pipeline evaluate --model .cache/coach-data/model.json --dataset .cache/coach-data/dataset.json --split test --output .cache/coach-data/evaluation.json
```

Preview menggunakan garis sudut sendi, mengambil warna dari hasil compare. Garis bersama memakai tingkat penyimpangan tertinggi agar merah tidak tertimpa hijau dari sendi lain. Abu-abu berarti belum dinilai/toleransi belum tersedia; pose hilang tidak digambar ulang melewati gap. Hash video, observasi dan hasil harus cocok. Output baru tidak boleh menimpa file existing; kegagalan rendering membersihkan output parsial milik run tersebut. Decoder/encoder harus tersedia secara native.

`movement_video.extract_video` mendapat opsi tambahan `include_landmarks=False`; default existing tetap tidak menyimpan landmark overlay. Tambahan koordinat tidak mengubah rumus fitur atau kontrak API. CLI lama tetap berjalan.

## Verifikasi aktual 30 Oktober 2026

- Dua belas referensi asli pengguna berhasil disiapkan dan dibentuk menjadi 12 profil; tidak memakai video pemula atau contoh salah untuk fitting.
- Replay masing-masing dari 12 video referensi menghasilkan status compared dengan deviasi maksimum 0 pada fitur yang teramati. Ini hanya sanity check dan tidak mengukur generalisasi.
- Seluruh profil asli masih satu Coach per gerakan; batas warna tetap pending. Tidak memanipulasi ID agar satu Coach tampak seperti tiga orang.
- CLI fit → extract → compare → overlay dijalankan pada video pukulan depan asli; seluruhnya exit 0. Preview privat berada di `.cache/coach-reference-20261030/pukulan-reference-preview.mp4`.
- Warning native MediaPipe terkait delegate/projection dan koneksi telemetry muncul; ekstraksi tetap selesai. Warning dan coverage tidak dijadikan bukti akurasi.
- Tes sintetis memeriksa seluruh kategori, perubahan kecepatan, penyimpangan siku lokal, tiga warna dan arah feedback, sendi tersembunyi, data tidak cukup, fase nullable/manual, train-only fitting, provenance, duplikasi/split leakage dan artifact tidak kompatibel.
- Tes encoder nyata memeriksa bahwa warna merah tidak tertimpa hijau pada garis bersama, file tidak ditimpa, source hash cocok dan output parsial dibersihkan saat gagal.

Pemeriksaan akhir:

| Pemeriksaan | Hasil aktual |
| --- | --- |
| `python -m pytest -q --basetemp=.cache/pytest-reference-native-final` | 336 passed, 18 skipped, 19 warnings; 59,62 detik |
| Tes baru untuk referensi/overlay | 41 kasus, termasuk hasil suite di atas |
| Ruff check dan format check terhadap tujuh file Python terkait | Lulus |
| `python -m scripts.export_openapi --check` | Snapshot cocok; kontrak API tetap |
| CLI fit/extract/compare/overlay dengan video pukulan depan asli | Exit 0; preview dapat dibaca, 131 frame |
| Posisi `main` selama pengerjaan | Tetap e480603; tidak merge/push |

Tes aplikasi memakai SQLite in-memory, file sementara dalam basetemp privat, dan SMTP loopback existing. 18 tes khusus MySQL dilewati karena konfigurasi database tes MySQL tidak disediakan; hasil ini tidak diklaim sebagai tes integrasi MySQL. Tidak menjalankan Docker atau mengirim email eksternal. Warning suite berasal dari deprecation Starlette/httpx dan path Alembic existing. Log suite privat: `.cache/coach-reference-20261030/pytest-full.txt`. Tidak ada model/video/dataset privat yang dimasukkan ke commit. Tidak ada migrasi baru; pemeriksaan `alembic check` development sebelumnya pada sesi ini telah lulus, tetapi bukan bukti akurasi model AI.

## Yang masih diperlukan sebelum dipakai pengguna

Tambahkan demonstrasi benar dari beberapa Coach dan repetisi untuk tiap gerakan, lalu evaluasi pada Coach yang tidak masuk train. Uji juga video pemula secara terpisah untuk memeriksa apakah koreksi/warna memang sesuai dan tidak salah menandai variasi teknik benar. Dataset training referensi tetap dapat berisi Coach benar saja. Validasi toleransi, fase penting, pengaruh proyeksi kamera dan variasi tubuh belum selesai. Setelah evaluasi memadai, hubungkan compare/overlay dengan worker, hasil API dan tampilan frontend melalui pekerjaan integrasi tersendiri.
