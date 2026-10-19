# SilatSense Backend

Proyek backend mandiri dari capstone-prototype. Jalankan perintah dari root folder ini. Pertahankan kontrak `/api/v1` sampai perubahan integrasi frontend disepakati.

- Jangan masukkan secret, `.env`, dataset privat, model `.task`, atau database ke Git.
- Routing tidak boleh berisi logika computer vision/scoring; gunakan services dan intelligence.
- Skor eksperimen tidak boleh disebut standar resmi IPSI; data yang tidak tersedia tidak boleh diisi angka dummy.
- Tes: `python -m pytest -q`; migrasi: `alembic check` pada database development.
- Konfigurasi Docker memakai database/volume terpisah dari prototype lama.
- Prioritaskan menjalankan aplikasi dan tes secara native. Jangan otomatis menyalakan Docker; pakai database tes terisolasi dan gunakan Docker hanya bila diminta atau disepakati.
