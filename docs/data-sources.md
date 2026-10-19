# Sumber data dan aset

## Dataset kuda-kuda

- Arsip pengguna: `silat.v1i.coco.zip`.
- Metadata COCO: [silat, versi 1](https://app.roboflow.com/datasets/silat-rvi2v-udapy/1), diekspor 4 Oktober 2026.
- Lisensi dalam arsip: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
- `contributor` dalam metadata kosong; identitas pembuat tidak ditambahkan secara spekulatif.
- Turunan: rotasi 90° searah jarum jam, resize untuk inference, landmark MediaPipe, statistik median/IQR enam kelas. Tidak mendistribusikan gambar mentah melalui aplikasi.

## Dataset tangkisan

- Arsip pengguna: `SilatPose.v1i.coco.zip`.
- Metadata COCO: [SilatPose, versi 1](https://app.roboflow.com/datasets/silatpose-ojtcz/1), diekspor 4 Oktober 2026.
- Lisensi dalam arsip: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
- `contributor` kosong. Satu kelas `Tangkisan3`; tidak mengklaim dataset mencakup semua tangkisan.
- Turunan: resize, landmark MediaPipe, statistik median/IQR; satu gambar multi-anotasi diabaikan.

## MediaPipe dan visual

- [Dokumentasi resmi Pose Landmarker Python](https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker/python).
- Model Lite float16 v1 diunduh oleh script dari `storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task`.
- SHA-256 model yang dipakai: `59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a`.
- Referensi UI adalah empat screenshot yang disediakan pengguna. Aset `frontend/public/reference-auth.png` menyalin screenshot autentikasi milik pengguna; CSS menampilkan area fotonya. Hak distribusi aset visual mengikuti sumber asli pengguna. Foto dekoratif tidak dijadikan referensi penilaian.
- DM Sans dan Barlow Condensed dibundel melalui Fontsource; file lisensi disertakan paket masing-masing. Lucide menyediakan ikon antarmuka.
