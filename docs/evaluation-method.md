# Metode evaluasi prototype-v1

## Representasi dan fitur

MediaPipe Pose Landmarker Lite memproses frame secara independen dalam mode IMAGE. Tidak mengklaim pengenalan temporal. `num_poses=2` dipakai agar frame dengan lebih dari satu pose terdeteksi ditolak. Ini tidak menjamin detektor selalu menemukan setiap orang.

Koordinat x/z dikoreksi dengan rasio lebar/tinggi gambar. Landmark dengan visibility < 0,5 atau nilai nonfinite tidak dipakai. Ambang ini adalah parameter kualitas deteksi prototipe, bukan standar silat. Origin adalah titik tengah pinggul; skala adalah jarak bahu 2D. Bahu/pinggul yang tidak terlihat atau skala mendekati nol membuat frame tidak valid.

Sudut menggunakan vektor pada bidang gambar (x,y):

- Siku: bahu–siku–pergelangan tangan.
- Bahu: siku–bahu–pinggul.
- Pinggul: bahu–pinggul–lutut.
- Lutut: pinggul–lutut–pergelangan kaki.
- Inklinasi torso: garis tengah pinggul ke tengah bahu terhadap vertikal gambar.
- Lebar stance: jarak antarkedua pergelangan kaki dibagi lebar bahu.
- Posisi pergelangan tangan relatif terhadap bahu serta pergelangan kaki relatif terhadap pinggul: komponen x/y setelah normalisasi.
- Alignment bahu/pinggul: besar kemiringan garis pasangan sendi terhadap horizontal gambar.

Sudut dengan vektor nol atau landmark hilang tidak diisi; fitur tersebut dihilangkan. Perhitungan murni berada dalam modul features dan diuji dengan geometri yang diketahui serta invariansi translasi/skala.

## Profil terukur

Builder membaca gambar dan label COCO, menerapkan EXIF dan rotasi eksplisit, resize maksimal 1280 piksel, lalu memakai pipeline pose/fitur yang sama. Keypoint COCO tidak dipakai. Duplikat byte-identik diabaikan. Gambar dengan jumlah anotasi bukan satu dilewati. Per fitur, median/IQR dicatat hanya jika ada minimal 10 sampel terukur. Setiap profil memuat jumlah sampel, versi fitur, rotasi, checksum model dan provenance.

Profil aktual: enam varian kuda-kuda × 200 pose; tangkisan3 × 202 pose. `build-report.json` mencatat cakupan ekstraksi. Nilai bukan konstanta teknik buatan. Opsi `--limit` hanya debug; hasil partial ditandai dan tidak diaktifkan oleh seed/repository.

Untuk mengganti dataset di masa depan, hasilkan artifact berversi baru, sesuaikan version/nama file agar tidak menimpa artifact yang masih dirujuk histori, dan nonaktifkan profil lama melalui kolom `active`. Riwayat menyimpan hasil serta versi analyzer/referensi saat evaluasi.

## Pemilihan pose dan skor

Video didekode berurutan dengan OpenCV. Metadata orientasi video ditangani melalui ORIENTATION_AUTO. Metadata FPS/durasi harus valid. Frame disampel dengan stride `round(video_fps / sample_fps)`, minimal satu. Dengan demikian FPS sampling mendekati konfigurasi, bukan resampling temporal presisi.

Fitur dengan IQR ≤ 1e-6 tidak diberi skala buatan; dikeluarkan dari scoring. Perbandingan memerlukan setidaknya 8 fitur bersama dan cakupan 70% fitur referensi yang usable.

```text
distance(feature) = abs(observed - median) / IQR
distance(pose) = mean(min(distance(feature), 10))
score = round(100 / (1 + distance(pose)), 1)
```

Pasangan frame/profil dengan distance terkecil dipilih; tie memakai urutan frame lalu profil. Skor adalah pemetaan matematis untuk eksplorasi dataset. Nilai 100 berarti fitur yang dibandingkan berada di median referensi, bukan teknik sempurna. Batas cakupan, clipping, dan rumus skor adalah heuristik eksperimen yang dapat diganti, tidak diklaim berasal dari standar pencak silat.

Maksimal enam deviasi terbesar ditampilkan jika setidaknya 1 IQR dari median. Severity low/medium/high memetakan 1–2 / 2–3 / ≥3 IQR dan hanya berarti ukuran perbedaan relatif terhadap dataset. `deviation` adalah selisih bertanda dalam derajat atau unit normalisasi, bukan distance/IQR. Feedback menggunakan bahasa perbedaan, bukan menyatakan gerakan salah.

## Validitas

Sejak Fase 4, hasil baru menyimpan landmark image-normalized, measurement mentah,
median/IQR referensi terpilih dan assessment pada frame yang sama dalam result_json.
Konversi overlay membalik koreksi rasio x/z sebelum normalisasi pinggul/bahu;
z relatif skala lebar gambar, bukan meter. Dimensi adalah frame inference setelah
resize maksimal 1280 piksel dan orientasi. Landmark nonfinite atau visibility
di luar 0–1 diomit, koordinat x/y di luar gambar tidak diclamp.

Tanpa perbandingan comparable, frame pertama dengan ≥8 fitur valid dipakai untuk
pose dan nilai mentah, dengan assessment not_assessed. Tanpa frame valid, pose
null dan measurements kosong. Hasil lama yang tidak menyimpan data ini tetap
null/kosong dengan alasan; tidak ada inference ulang otomatis. Measurements
memuat 20 fitur yang dikenal, nilai fitur hilang null, unit deg atau shoulder_width.
Assessment within_reference berarti jarak <1 IQR pada fitur yang dibandingkan;
deviates berarti ≥1 IQR. Issues tetap maksimum enam. Rumus skor tidak berubah.
Data hasil tersebut bertahan setelah video expired; DELETE menutup akses biasa
dan statistik sambil mempertahankan hasil/catatan untuk audit.

Gambar berdekatan dari subjek/urutan sama dapat membuat profil terlalu sempit. Frame terbaik dapat menutupi kesalahan pada frame lain. Viewpoint, occlusion, karakteristik tubuh, bias dataset, dan landmark jitter dapat mengubah skor. Belum ada validasi pakar UKM atau holdout subjek independen; skor tidak boleh dipresentasikan sebagai akurasi biomekanik atau standar resmi.
