# Eksperimen pukulan depan — 30 Oktober 2026

Branch: `codex/ai-pukulan-front-baseline`. Seluruh implementasi baru berada dalam
repo silatsense-be. Modul/script ini belum dipanggil router, worker produksi,
atau frontend. Tidak ada perubahan kontrak `/api/v1`, migrasi, database atau .env.

## Tujuan dan hasil aktual

Menguji kelayakan pengukuran sudut siku pada satu video demonstrasi Coach yang
diberikan pengguna. Status gerakan benar adalah keterangan pengguna, bukan
hasil klasifikasi program. Kamera depan adalah requirement/input yang disepakati,
bukan hasil deteksi arah kamera otomatis.

Video lokal diperiksa pada seluruh **131 frame**, sekitar **4,413 detik**.
Dengan filter visibility landmark 0,5, observasi 2D tersedia pada 116 frame siku
kiri dan 118 frame siku kanan. Model mengeluarkan lebih dari satu kandidat pose
pada 13 frame; observasi frame tersebut ditolak, tidak dipilih orangnya secara
diam-diam. Ini adalah keluaran detector, bukan bukti bahwa video berisi banyak orang.
Tambahan dua frame siku kiri tidak memenuhi filter visibility.

Pada frame 52 (waktu perkiraan 1,752 detik), proyeksi siku kanan menghasilkan
**20,6 derajat** dan estimasi world-coordinate MediaPipe **91,1 derajat**.
Median perbedaan kedua metode untuk siku kanan sepanjang observasi yang tersedia
adalah **27,3 derajat**, maksimum **81,8 derajat**. Angka ini mengukur perbedaan
dua estimasi, bukan error terhadap sudut benar yang telah diukur.

Kesimpulan: belum ada bukti bahwa sudut proyeksi 2D kamera depan cukup untuk
menerapkan batas sudut dari penelitian pandangan samping. Estimasi 3D juga belum
divalidasi sebagai ground truth. Program sengaja menghasilkan `not_assessed`,
`correctness=null`, `score=null`, bukan menyatakan demonstrasi Coach salah.
Visibility tinggi tidak otomatis menjamin akurasi geometri sendi.

## Implementasi

- `app/intelligence/punch_diagnostics.py`: pengukuran sudut 2D dengan koreksi
  aspek, sudut XYZ estimasi model, statistik dengan sampleCount, pemeriksaan
  keterlihatan/koordinat dan interval fase manual.
- `scripts/analyze_punch_reference.py`: reuse setup detector MediaPipe existing,
  decoding seluruh frame secara default, ekspor landmark/urutan sudut, preview
  lengan serta plot opsional. Mode IMAGE mempertahankan observasi per frame
  seperti backend existing; ini belum model temporal terlatih/tracker baru.
- `app/intelligence/punch_dataset.py` dan `scripts/prepare_punch_dataset.py`:
  memeriksa manifest, identitas peserta/rekaman, duplikasi konten, konsistensi
  ekstraksi dan urutan waktu; mengekspor urutan fitur tanpa melatih model.
- `docs/templates/punch-dataset.csv`: template header saja; tidak berisi dataset.

Observasi seluruh rangkaian disimpan. Timestamp dihitung dari indeks frame/FPS
metadata, sehingga merupakan pendekatan waktu untuk file dengan variable FPS.
Fase tanpa anotasi tetap null. Titik/pengukuran tak tersedia tetap null;
tidak ada imputasi, smoothing, label fase otomatis atau ambang benar/salah buatan.
Statistik seluruh video mencakup sikap awal/akhir; bukan sudut khusus fase impact.

## Menjalankan native

Jalankan dari root repo; ganti path video dengan berkas lokal milikmu. Model
MediaPipe harus sudah tersedia. Tidak ada koneksi database atau pengiriman data.

```powershell
.venv/Scripts/python.exe -m scripts.analyze_punch_reference --video "C:\path\pukulan.mp4" --output .cache/pukulan-run-001 --plot
```

Output: observations.json, preview JPG, dan elbow-diagnostics.png jika memakai
--plot. Folder output harus baru. Output berisi data privat; gunakan .cache atau
datasets yang diabaikan Git, jangan menaruhnya dalam app/docs atau mengunggahnya.
Video sumber tidak disalin ke repository. Plot bukan indikator lulus/gagal.

Untuk fase manual, --annotations menerima array JSON dengan `phase`,
`startSeconds`, `endSeconds`. Pilihan fase: neutral_start, preparation, execution,
recovery, neutral_end. Interval harus berurutan, tidak tumpang tindih, dan berada
dalam video. Isi berdasarkan anotasi yang ditinjau; jangan menyalin waktu contoh
atau menganggap semua frame video mempunyai label yang sama.

Salin template manifest ke direktori privat dan isi metadata:

| Kolom | Isi |
| --- | --- |
| sampleId | ID unik satu klip/rangkaian yang dianotasi |
| participantId | ID peserta stabil dan disamarkan |
| recordingId | Rekaman asal; klip dari satu rekaman memakai ID yang sama |
| split | train, validation, atau test; pembagian peserta/rekaman utuh |
| label | correct, needs_correction, atau unlabeled |
| labelSource | coach_review, user_reports_coach_demo, atau unlabeled |
| cameraView | front sesuai ruang lingkup awal |
| observationsPath | Path JSON observasi relatif ke data-root |
| annotationsPath | Path JSON fase relatif ke data-root, atau kosong |

```powershell
.venv/Scripts/python.exe -m scripts.prepare_punch_dataset --manifest .cache/pukulan-run-001/manifest.csv --data-root .cache/pukulan-run-001 --output .cache/pukulan-run-001/temporal-dataset.json
```

Peserta, rekaman, atau hash video yang sama tidak boleh melintasi split. Konten
identik tidak dihitung sebagai sampel independen. Pose model, versi dependency
dan filter visibility harus konsisten. File di luar data-root ditolak.

Smoke test memakai satu referensi yang dilaporkan benar, dengan split train
sebagai penempatan sementara untuk uji ekspor saja. Program melaporkan
`dataStructureComplete=false`: validation/test belum ada, kelas kesalahan belum
ada. Tidak ada train/validation/test yang dibuat dari pecahan video yang sama.
Struktur lengkap di kemudian hari pun tidak berarti kualitas model tervalidasi.

## Bukti pengujian

- Dua file tes baru: **39 kasus lulus** dalam suite regresi final.
  Meliputi geometri, null/NaN, multi-pose, batas fase, leakage, versi ekstraksi,
  path, proteksi overwrite serta decoder dan MediaPipe nyata pada video sintetis.
- Regresi native SQLite terisolasi: **261 passed, 18 skipped**, 18 warning
  Alembic existing, **60,35 detik**. MAIL_ADAPTER=disabled; dua URL tes MySQL
  dikosongkan. Tidak memakai database development, Filess, SMTP nyata atau Docker.
- Pencatatan request tes: **44/44 operasi OpenAPI** mendapat respons sukses.
  Snapshot OpenAPI tidak berubah. Tes MySQL khusus belum diulang pada perubahan
  ini karena kode baru tidak mengakses SQL atau mengubah model/migrasi.
- CLI nyata menganalisis video sumber dan mengekspor satu urutan temporal;
  hasil privat tersimpan di `.cache/pukulan-front-baseline-20261030-r2/`.
- Lint critical, lint/format file baru dan pemeriksaan format CI existing lulus.

Lima perubahan optimasi dependency yang sudah ada sebelum branch dibuat tetap
dipertahankan terpisah dan tidak termasuk implementasi eksperimen ini.

## Yang belum diselesaikan

Pengukuran pembanding independen untuk kamera depan; rubrik yang cocok dengan
metode pengukuran; anotasi fase/repetisi; dataset lintas peserta dengan contoh
benar/salah yang ditinjau; pemilihan/training/evaluasi model temporal; confidence
dan abstention terkalibrasi; integrasi hasil tervalidasi ke API/FE. Implementasi
ini adalah diagnostik awal dan persiapan input training, bukan pipeline training
final atau model penilaian silat yang selesai.

Rujukan:

- [Hidayat & Sugiharto, 2024, Analisis Gerak Pukulan Lurus](https://jurnal.unimed.ac.id/2012/index.php/so/article/download/51134/23708):
  tiga atlet, pengukuran dari sisi sagital. Mean/rentang pengamatan bukan batas
  lulus universal atau standar resmi IPSI untuk kamera depan.
- [MediaPipe Pose Landmarker Python](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker/python):
  keluaran image/world landmarks merupakan hasil model; proyek ini belum
  membuktikan estimasi tersebut sebagai pengukuran sudut fisik yang akurat.
