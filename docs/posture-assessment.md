# Penilaian postur eksperimen — v1

Tambahan read-time pada `coachComparison.postureAssessment`, untuk 12 target yang
sudah ada. Ini poin kedekatan geometri proyeksi terhadap Coach, bukan standar IPSI,
akurasi model, diagnosis biomekanik 3D, atau penilaian manual Coach. `score` utama,
`coachComparison.score`, `correctness`, status validasi, statistik similarity dan
review manual tidak diganti oleh poin ini.

## Kontrak dan cara FE memakai hasil

```json
{
  "status": "assessed",
  "points": 95.0,
  "maxPoints": 100,
  "reason": null,
  "aspects": [
    {"id":"bent_knee","points":85,"correctionCode":"knee_bend_insufficient","reason":null,"unit":"deg"},
    {"id":"other_leg_extension","points":100,"correctionCode":null,"reason":null,"unit":"deg"},
    {"id":"stance_width","points":100,"correctionCode":null,"reason":null,"unit":"torso_length_ratio"}
  ],
  "rubricVersion": "posture-reference-v1"
}
```

- `assessed`: seluruh aspek utama bisa dinilai; total merupakan rata-rata poin
  aspek, bobot setara, dinormalisasi 0–100 dan dibulatkan dua desimal.
- `partial`: sebagian aspek punya poin, tetapi total `null` karena aspek utama
  belum bisa dinilai. Tampilkan poin aspek yang tersedia dan alasannya.
- `not_assessable`: semua poin `null`, bukan nol.
- Saat ini semua aspek pada tabel rubrik ditandai `primary=True`. Jika kelak
  kebijakan ini berubah, ganti versi rubrik dan tesnya.
- Poin aspek 0–100. `unit` menyatakan satuan pengukuran sumber, bukan satuan poin.
- `correctionCode=null` dapat berarti tidak menyimpang, arah tidak konsisten,
  atau aspek yang tidak memiliki koreksi berarah; jangan otomatis menganggapnya
  100 atau gerakan benar. Kode koreksi baru tidak mengganti feedback/color frame.
- Contoh respons berupa **fragmen sintetis** dengan koreksi, tanpa koreksi dan
  tidak dapat dinilai ada di [posture-assessment-examples.json](posture-assessment-examples.json).
  Objek di sana bukan respons evaluasi lengkap dan bukan output video privat.

Kontrak `/api/v1` tidak berganti. Field tampil melalui evaluation Member,
detail history Member dan detail sesi Coach yang sudah memakai `evaluation_out`.
Ownership dan akses Coach tetap berlaku. Swagger/OpenAPI diperbarui di
`docs/openapi.json`.

## Pemetaan demo dan aspek

Pemetaan nama demo mengikuti `app/intelligence/movement_catalog.py`. Pada API,
target numerik diambil dari **`referenceValue` pada frame perbandingan Coach yang
sudah tersimpan untuk movementId tersebut**. Referensi itu sudah dipilih dan
diselaraskan oleh pipeline Coach saat analisis. Read-time tidak membaca video
demo/model privat, memilih ulang Coach, menjalankan MediaPipe/DTW lagi, atau
mengubah artifact. Dengan demikian rekaman lama memakai pasangan referensi yang
benar-benar dipakai saat rekaman itu dianalisis, bukan model terbaru secara diam-diam.

| movementId | Demo yang sudah dipetakan | Aspek publik |
| --- | --- | --- |
| kuda_kuda_tengah | kuda kuda 1.mp4 | knees_bend, knee_symmetry, stance_width |
| kuda_kuda_depan | kuda kuda 2.mp4 | front_knee_bend, rear_leg_extension, torso_inclination |
| kuda_kuda_samping | kuda kuda 3.mp4 | bent_knee, other_leg_extension, stance_width |
| pukulan_depan | pukulan 1.mp4 | elbow_extension, wrist_path |
| pukulan_melingkar | pukulan 2.mp4 | curved_wrist_path, elbow_change |
| pukulan_bandul | pukulan 3.mp4 | upward_wrist_path, elbow_change |
| tendangan_depan | tendangan 1.mp4 | knee_change, ankle_path, torso_inclination |
| tendangan_sabit | tendangan 2.mp4 | swing_ankle_path, knee_change, hip_change |
| tendangan_t | tendangan 3.mp4 | lateral_leg_position, knee_extension, torso_inclination |
| tangkisan_atas | tangkisan 1.mp4 | upward_wrist_path, wrist_end_position, elbow_bend |
| tangkisan_dalam | tangkisan 2.mp4 | inward_wrist_path, elbow_bend |
| tangkisan_bawah | tangkisan 3.mp4 | downward_wrist_path, wrist_end_position, elbow_bend |

## Pemilihan bagian gerakan

Implementasi murni Python ada di `app/intelligence/posture_assessment.py`;
konfigurasi per gerakan dan toleransi ada di `posture_rubric.py`.

- Kuda-kuda: gunakan frame Coach dengan sudut lutut yang lebih kecil berada pada
  kuartil bawah, sekaligus tidak lebih dari 20° di atas tekukan terdalam Coach.
  Harus ada minimal empat frame dan tekukan referensi tidak mendekati sikap tegak
  (>165°). Ini memilih posisi yang terbentuk, bukan rata-rata setup/return.
- Dua lutut: pasangkan sudut setelah diurutkan untuk menoleransi variasi sisi.
  Tekukan kedua lutut memakai rata-rata deviasi absolut kedua lutut, bukan
  rata-rata sudut yang dapat saling meniadakan kesalahan. Simetri memakai beda
  kedua sudut. Kuda-kuda depan memakai lutut paling menekuk sebagai proxy lutut
  depan; kedalaman kaki depan/belakang tidak dibuktikan dari proyeksi 2D ini.
- Gerakan dinamis: sisi aktif diperkirakan terpisah pada pengguna dan Coach dari
  rentang x/y pergelangan relatif bahu atau pergelangan kaki relatif pinggul.
  Excursion minimum 0,20 torso; sisi dominan harus minimal 1,25 kali sisi lain.
  Kedua sisi perlu cakupan 60% dan empat pengamatan agar tidak menebak sisi yang
  kebetulan tertutup. Jika tidak jelas, poin dinamis kosong.
- Lintasan: baseline dari bagian awal Coach yang terlihat, lalu gerak keluar
  menuju perpindahan terjauh dari baseline. Onset adalah titik terakhir sebelum
  puncak dengan perpindahan <=max(0,10 torso, 15% perpindahan puncak). Gerak terlalu
  cepat yang tersimpan dalam <4 frame tidak dinilai. `peak` memakai empat frame
  terakhir menuju puncak untuk siku/kaki merentang, kemiringan dan posisi akhir.
- Lintasan gerak dibandingkan sebagai vektor x/y relatif awal gerak pada waktu
  yang telah dipasangkan. Ini mempertahankan beda bentuk kurva dan arah, bukan
  hanya jarak awal–akhir. Posisi akhir memakai posisi absolut relatif tubuh.
  Perubahan siku/lutut/pinggul dibandingkan sebagai perubahan dari sudut awal.
  Belum ada estimasi lintasan 3D atau label fase semantik baru.
- Bila sisi aktif berbeda, tukar sisi anatomis dan balik tanda x proyeksi pengguna
  sebelum membandingkan. Ini asumsi variasi kiri–kanan pada kamera tetap, bukan
  detektor otomatis kamera mirror. Penyelarasan DTW lama tidak dihitung ulang.

## Toleransi dan poin awal

Kebijakan **eksperimen**, sengaja tersentralisasi dan berversi; belum dikalibrasi
pada dataset kesalahan pemula atau disetujui sebagai ambang teknik resmi.

| Satuan sumber | Dead band (100 poin) | Tambahan deviasi per pengurangan 15 poin |
| --- | --- | --- |
| derajat (`deg`) | <=20° | 30° |
| rasio panjang torso (`torso_length_ratio`) | <=0,20 | 0,30 |

`points = max(0, 100 - 15 * ceil(max(0, medianDeviation - deadBand) / step))`.
Contoh derajat: <=20 mendapat 100; >20 sampai 50 mendapat 85; >50 sampai 80
mendapat 70. Tidak menjumlahkan derajat dengan rasio tubuh. Agregasi lintasan
memakai median panjang vektor error, sudut memakai median deviasi absolut.
Setiap aspek memerlukan >=4 pengamatan dan >=60% frame terpilih yang valid.
Gerak juga membutuhkan minimal tiga waktu Coach berbeda, sehingga alignment yang
membeku tidak menghasilkan poin lintasan.

Dua video regresi yang diminta menjadi **acceptance/calibration fixtures** v1,
bukan ukuran akurasi atau uji independen untuk toleransi ini. Split dataset lama
tidak diubah dan tidak ada model yang di-training ulang.

## Kapan koreksi berarah tersedia

Koreksi hanya keluar bila poin <100, median selisih bertanda melampaui dead band,
dan >=75% pengamatan valid melampaui dead band ke arah yang sama. Deviasi campuran
tetap mengurangi poin tetapi tidak dipaksakan menjadi instruksi berarah.

| Kelompok | Selisih negatif / positif terhadap Coach |
| --- | --- |
| lutut menekuk | knee_bend_excessive / knee_bend_insufficient |
| siku menekuk | elbow_bend_excessive / elbow_bend_insufficient |
| siku merentang | elbow_extension_insufficient / elbow_extension_excessive |
| lutut merentang | knee_extension_insufficient / knee_extension_excessive |
| kaki belakang | rear_leg_extension_insufficient / rear_leg_extension_excessive |
| kaki satunya | other_leg_extension_insufficient / other_leg_extension_excessive |
| kemiringan torso | torso_lean_insufficient / torso_lean_excessive |
| lebar kaki | stance_too_narrow / stance_too_wide |
| simetri lutut | knee_asymmetry_less_than_reference / knee_asymmetry_excessive |
| pergelangan naik | wrist_raise_excessive / wrist_raise_insufficient |
| pergelangan turun | wrist_lower_insufficient / wrist_lower_excessive |
| posisi akhir pergelangan | wrist_position_too_high / wrist_position_too_low |

Sumbu y gambar bertambah ke bawah. Kode lintasan vertikal hanya diberikan bila
komponen vertikal mendominasi error horizontal secara konsisten. Lintasan kurva,
lintasan ke dalam, ayunan kaki dan perubahan sudut tidak diberi kode arah yang
tidak dapat dibuktikan oleh proyeksi yang tersimpan. `knee_bend_insufficient`
dapat ditampilkan FE sebagai “Lutut kurang menekuk dibanding referensi Coach”.

## Data kurang memadai

Pengukuran null, NaN/infinity, unit salah, sudut di luar 0–180°, rasio ekstrem,
visibility rendah atau reason geometri tidak valid tidak dijadikan nol. Status
warna `tolerance_pending` lama boleh dinilai karena rubrik poin ini mempunyai
toleransi terpisah; bukan menganggap warna null sebagai data hilang.

Jika timeline landmark tersedia, gunakan observasi aktual terdekat <=0,15 detik,
visibility >=0,5 dan koreksi aspect ratio gambar. Torso yang kolaps atau segmen
sendi terproyeksi terlalu pendek (<0,08 torso) tidak dinilai. Lebar/simetri/lintasan
juga ditolak bila baseline bahu terproyeksi <0,20 torso. Hanya aspek terdampak yang
kosong; bila cakupannya kurang, total ikut kosong.

Heuristik ini **tidak membuktikan sudut kamera benar** pada semua rekaman.
Foreshortening/occlusion/perspektif yang tidak tampak dari fitur tersimpan masih
merupakan keterbatasan 2D. Untuk hasil lama tanpa timeline, fitur berpasangan
yang sudah lolos filter ekstraksi dapat dinilai, tetapi kamera tidak bisa
divalidasi ulang. Tidak membuat landmark atau angka pengganti yang tidak tersedia.

| reason | Makna untuk FE |
| --- | --- |
| comparison_not_assessable | Tidak ada perbandingan Coach yang dapat digunakan |
| formed_stance_not_observable | Posisi kuda-kuda Coach yang terbentuk tidak terbaca |
| active_side_unclear | Sisi anggota tubuh yang bergerak belum cukup jelas |
| reference_motion_not_observable | Bagian gerak Coach/waktu alignment tidak cukup |
| insufficient_comparison_samples | Frame pada bagian yang dinilai terlalu sedikit |
| joint_not_observable | Nilai/unit/coverage sendi atau fitur tidak mencukupi |
| camera_or_pose_inadequate | Landmark hilang, proyeksi terlalu pendek atau kamera tidak memadai |
| required_aspect_unavailable | Setidaknya satu aspek utama belum dapat diberi poin |

## Kompatibilitas dan verifikasi

`evaluation_out` membuat salinan objek perbandingan dan menghitung hasil setiap
read, tanpa commit/update JSON database. Field penilaian tersimpan yang mungkin
ada tidak dipercaya sebagai cache. Tidak memerlukan migrasi, model baru, B2,
worker aktif atau perubahan request FE. Hasil statis tanpa Coach comparison
tetap tidak memperoleh poin postur buatan.

Tes publik memakai geometri sintetis untuk semua 12 konfigurasi serta kasus
ambigu/missing, unit, titik batas, arah campuran, kurva, fase, mirror, camera,
bobot dan autentikasi read-time. Tes privat opsional membaca demo, observasi dan
video lokal tanpa mengubahnya; CI yang tidak punya data privat akan skip bagian
tersebut. Data privat tidak ditambahkan ke Git.

Regresi video nyata pada target `kuda_kuda_samping` (menggunakan hash video untuk
memastikan observasi cocok; bukan nama file dalam fungsi penilaian):

| Input | Poin aspek bent_knee | correctionCode | Total seluruh aspek |
| --- | --- | --- | --- |
| orang 7.mp4 | 100 | null | 95 |
| orang 1(2).mp4 | 85 | knee_bend_insufficient | 85 |

`orang 1(2).mp4` berlabel kuda-kuda tengah di dataset lama; tes ini sengaja meminta
target kuda-kuda samping sebagaimana acceptance pengguna, tanpa mengganti label.
100 pada lutut bukan pernyataan 100 pada seluruh gerakan.

Seluruh 12 demo yang dipetakan diperiksa melalui comparison replay yang tersedia:
9 dapat dinilai 100, 3 menghasilkan poin null secara konservatif. Pukulan
melingkar dan tendangan depan mempunyai sisi aktif/coverage yang belum jelas;
tendangan T tidak menyediakan cukup frame gerak keluar untuk rubrik ini. Ini
bukan klaim bahwa demonstrasi Coach salah. Dibutuhkan observasi yang lebih jelas
untuk memberi poin pada rekaman tersebut, bukan melonggarkan guard agar mendapat
angka. Dua belas comparison held-out existing juga diuji bersama timeline asli
dan timeline kosong.

Hasil native 25 November 2026:

- **476 passed, 18 skipped, 26 warnings**, 65,18 detik. Sebanyak 74 tes baru
  mencakup 48 kasus sintetis/API dan 26 kasus referensi privat yang benar-benar
  tersedia di mesin ini. Seluruh 26 tes privat berjalan, bukan skip.
- 18 tes yang skip memerlukan MySQL disposable; URL database tes sengaja kosong.
  API dan migrasi diuji pada SQLite sementara. Peringatan berasal dari deprecation
  TestClient/httpx dan konfigurasi Alembic existing.
- Ruff fatal-error checks, format modul baru, OpenAPI snapshot dan diff whitespace
  lulus. Log lokal: `.cache/posture-assessment/full-tests.log`.
- Tes API terfokus pertama terhambat sandbox TestClient Windows, dihentikan,
  lalu diulang native dengan fixture terisolasi; percobaan terhambat tidak dihitung
  sebagai hasil lulus.

Tidak ada tes terhadap layanan produksi, job nyata, perubahan schema/data produksi,
push atau deploy. Job yang dibuat tes hanya berada di database/media sementara.
