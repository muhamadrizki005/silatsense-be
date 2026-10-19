# Kontrak API SilatSense — baseline Fase 1 dan implementasi Fase 2–7

Status diperbarui: 18 Oktober 2026. Endpoint **Fase 2–7 sudah diimplementasikan** pada
kode backend dan memerlukan migrasi sampai `0007` sebelum dijalankan. Recovery email dan bridge auth FE tersedia; integrasi data latihan FE masih
terpisah. Kontrak dan bukti Fase 7: [phase7-api.md](phase7-api.md).
Panduan [phase4-api.md](phase4-api.md), [phase5-api.md](phase5-api.md), [phase6-api.md](phase6-api.md). Status aktual dan bukti
tes ada di [architecture.md](architecture.md). Perubahan FE dan matriks field
ada di [fe-integration.md](fe-integration.md).

## 1. Baseline dan kompatibilitas

Base path tetap `/api/v1`. URL host mengikuti mode operasi, bukan bagian DTO.
`auth-api.md` tetap menjadi kontrak autentikasi existing.

| Status aktual | Endpoint setelah `/api/v1` | Perilaku sekarang |
| --- | --- | --- |
| Tersedia, auth baru | `POST /auth/sign-up`, `POST /auth/sign-in` | NPM/email, DTO camelCase, Member saat registrasi publik |
| Tersedia, auth baru | `GET /auth/session`, `POST /auth/refresh-session`, `POST /auth/logout` | Bearer, refresh cookie sekali pakai, logout sesi ini |
| Kompatibilitas auth | `POST /auth/register`, `POST /auth/login`, `GET /auth/me`, `POST /auth/refresh` | DTO prototype, ID integer dan role uppercase |
| Prototype | `GET/PATCH /profile` | Data User; PATCH hanya `name` |
| Prototype | `GET /movements` | Slug internal, nama, `reference_ready` |
| Prototype | `POST /evaluations` | Multipart `movement_type`, `video`; sinkron, 201, video langsung dibersihkan |
| Prototype | `GET /evaluations`, `GET /evaluations/{evaluation_id}` | Hasil tersimpan; offset/limit, snake_case |
| Prototype dengan scope Fase 6 | `GET /coach/members`, `GET /coach/members/{member_id}`, `GET /coach/members/{member_id}/evaluations` | Daftar/detail/histori hanya binaan aktif; shape lama tetap |
| Prototype | `POST /coach/evaluations/{evaluation_id}/notes` | Catatan append-only, tanpa draft/revisi/keputusan |
| Fase 2, diimplementasikan | `GET/PATCH /member/profile`, `GET/PATCH /coach/profile` | Profil per role, nullable, whitelist field |
| Fase 2, diimplementasikan | `PATCH /member/password`, `PATCH /coach/password` | Password lama, pencabutan seluruh sesi, login ulang |
| Fase 2, diimplementasikan | `GET /member/training-modules`, `GET /member/training-prep/{slug}`, `GET /member/record-config/{slug}` | Empat modul seeded, capability referensi valid, panduan kosong bila belum bersumber |
| Fase 3, diimplementasikan | `POST /member/sessions`, `GET /member/sessions/{sessionId}` | Upload 202, status job, storage privat, worker persisten; [phase3-api.md](phase3-api.md) |

Shape endpoint lama dipertahankan; endpoint baru tidak mengganti makna URL lama.
`GET /coach/roster` dan `/coach/roster/{memberId}` menjadi kontrak daftar/detail
binaan yang baru. Endpoint lama tetap offset/limit, tidak tiba-tiba berubah
menjadi envelope cursor. Seluruh endpoint lama yang membaca detail/evaluasi
atau menulis catatan sekarang memakai scope binaan, termasuk detail evaluasi
generik untuk Coach. Scope Fase 6 tidak memberikan akses berdasarkan author lama.
Tidak ada tanggal penghapusan endpoint lama; penghapusan memerlukan audit
konsumen dan persetujuan integrasi tersendiri.

## 2. Aturan domain, null, pagination, dan error

- ID publik adalah string opaque; implementasi awal boleh menserialisasi ID
  integer database sebagai string. Jangan mengasumsikan UUID atau memakai slug
  sebagai ID sesi. Namespace `sessionId` dan `evaluationId` berbeda.
- Slug publik: `kuda-kuda`, `pukulan`, `tangkisan`, `tendangan`. Mapping internal
  hanya `kuda-kuda` → `kuda_kuda`; tiga lainnya identik. Slug lain: 404 pada GET,
  422 pada input upload. Endpoint prototype tetap menerima slug internal.
- Timestamp baru adalah ISO 8601 UTC dengan `Z`. Ukuran byte, durasi detik,
  sudut `deg`, posisi relatif `shoulder_width`, skor `similarity_points`
  pada rentang 0–100. Skor bukan probabilitas, akurasi, atau persentase lulus.
- Field nullable selalu dikirim sebagai `null` saat tidak diketahui; tidak
  diisi nol atau string kosong. Array kosong tetap `[]`. Field opsional request
  yang tidak dikirim tidak diubah; `null` hanya untuk field yang boleh dikosongkan.
- Status: `processingStatus=queued|processing|completed|failed`;
  `analysisStatus=experimental|reference_not_ready|insufficient_pose|insufficient_features`
  (null sebelum hasil tersedia); `reviewStatus=pending|needs_revision|approved`.
  Tanpa Coach dan tanpa review, `reviewStatus=pending`; `reviewAvailable=false`.
  Published review tetap terlihat Member setelah revoke dengan keputusan historis.
  reviewAvailable true hanya untuk completed dengan Coach aktif. Selesai analisis
  tanpa referensi adalah completed, bukan failed. Draft bukan keputusan published.
- `score`, `matchedVariant`, `referenceVersion`, `keyFrame`, `pose`, dan metrik
  yang belum diukur nullable. `unavailableReasons` berisi kode, misalnya
  `reference_not_ready`, `not_measured`, `no_comparable_samples`.
- Field object yang tidak boleh diubah (role, owner, author, NPM/email, sabuk)
  ditolak sebagai field tambahan (422), bukan diam-diam diabaikan.

Pagination baru: `?limit=20&cursor=<opaque>`, 1–100, respons
`{items: T[], nextCursor: string|null}`. Urut descending `(createdAt,id)`;
roster memakai waktu akun dibuat dan ID Member. Cursor mencakup posisi, filter,
dan scope pengguna; cursor invalid/tidak cocok menghasilkan 422
`invalid_cursor`. Setiap halaman memeriksa akses ulang. Hasil dapat berubah
karena transfer/delete, bukan snapshot lintas request; tidak mengembalikan
ulang item yang sama hanya karena timestamp sama.

Filter histori/sesi: `movementSlug`, `processingStatus`, `reviewStatus`,
`from`, `to`; from inclusive, to exclusive berdasarkan createdAt sesi,
timestamp ISO 8601 UTC dengan zona wajib. `from >= to`: 422.
FE mengubah rentang tanggal Jakarta ke UTC sebelum mengirim. Search roster
`q` mencari nama/NPM/email dalam binaan saja; whitespace di-trim, max 120.

Error endpoint baru:

```json
{
  "detail": "Evaluasi belum tersedia.",
  "code": "evaluation_pending",
  "requestId": "<opaque-request-id>"
}
```

| HTTP | Semantik / kode utama |
| --- | --- |
| 401 | `unauthenticated`; FE dapat mencoba pemulihan sesi sekali |
| 403 | `forbidden_role` atau `origin_not_allowed` |
| 404 | `not_found`; objek tidak ada, dihapus, milik orang lain, atau non-binaan memakai respons yang sama |
| 409 | `evaluation_pending`, `analysis_failed`, `version_conflict`, `idempotency_conflict`, `identifier_conflict` |
| 410 | `media_expired`, `media_deleted`, `media_unavailable`; hanya sesudah akses objek disahkan |
| 413 / 415 | `upload_too_large` / `unsupported_media_type` |
| 416 | `invalid_range`, dengan `Content-Range: bytes */<size>` (implementasi Fase 4) |
| 422 | `validation_error` dengan `errors:[{field,message}]`, atau `invalid_cursor` |
| 429 | `rate_limited` / `quota_exceeded`, sertakan `Retry-After` bila sementara |
| 503 | `service_unavailable`; retry aman hanya sesuai idempotensi |

`detail` error baru selalu string; jangan bocorkan SQL, storage path, atau stack
trace. Error auth existing tetap `detail` string/array FastAPI, tanpa mewajibkan
`code`/`requestId` baru. Semua respons pribadi dan error pribadi: `Cache-Control:
no-store`. Header Bearer bukan query parameter.

## 3. Profil, katalog, dan keamanan akun (Fase 2 dan recovery Fase 7 tersedia)

| Fase | Method + path | Input → respons |
| --- | --- | --- |
| 2 | `GET /member/profile`, `GET /coach/profile` | Role sesuai → Profile, 200 |
| 2 | `PATCH /member/profile` | `{fullName?,division?}` → Profile, 200 |
| 2 | `PATCH /coach/profile` | `{fullName?,division?,title?}` → Profile, 200 |
| 2 | `PATCH /member/password`, `PATCH /coach/password` | `{currentPassword,newPassword}` → 204; service yang sama |
| 2 | `GET /member/training-modules` | `{modules: TrainingModule[], statistics: ActivitySummary}` |
| 2 | `GET /member/training-prep/{slug}` | `{module,checklist: GuideItem[],guides: GuideItem[]}` |
| 2 | `GET /member/record-config/{slug}` | UploadConfig; bukan daftar kamera/hasil kalibrasi |
| 7 | `POST /auth/email-link/request` | Bearer + `{email,currentPassword}` → 202 generik |
| 7 | `POST /auth/email-link/confirm` | Bearer + `{token}` → 204; terikat akun pemohon |
| 7 | `POST /auth/email-verification/request` | Bearer + `{currentPassword}` → 202 generik; email existing |
| 7 | `POST /auth/email-verification/confirm` | Bearer + `{token}` → 204, emailVerifiedAt terisi |
| 7 | `POST /auth/password-reset/request` | `{identifier}` → 202 generik |
| 7 | `POST /auth/password-reset/confirm` | `{token,newPassword}` → 204; login ulang |

Schema berikut adalah notasi kontrak. Profil/katalog Fase 2 memiliki schema
Pydantic profil di `app/schemas/domain.py`, recovery di `app/schemas/recovery.py`.
Link/verify/reset token hash sekali pakai dengan expiry 24 jam/24 jam/30 menit.
MAIL_ADAPTER default disabled → 503 mail_unavailable pada request email,
seragam untuk semua identifier reset; aktifkan SMTP setelah konfigurasi benar.
`Id=string`, `Utc=string`, `MovementSlug` memakai empat slug publik.

```typescript
type CoachIdentity = { id: Id; fullName: string; title: string | null };
type SimilarityGroup = {
  movementSlug: MovementSlug; method: string; analyzerVersion: string;
  featureVersion: string; referenceVersion: string;
  averageScore: number | null; sampleCount: number;
};
type ActivitySummary = {
  completedSessionCount: number; totalDurationSeconds: number;
  durationSampleCount: number; scoredSessionCount: number;
  excludedScoreCount: number; similarityGroups: SimilarityGroup[];
};
type Profile = {
  id: Id; role: "member" | "coach"; fullName: string;
  npm: string | null; email: string | null; emailVerifiedAt: Utc | null;
  division: string | null; title: string | null;
  belt: string | null; beltTarget: string | null;
  passwordChangedAt: Utc | null; coach: CoachIdentity | null;
  createdAt: Utc; statistics: ActivitySummary | null;
};
type Capability = {
  scoringAvailable: boolean; reason: "reference_not_ready" | null;
  method: "static-reference-pose";
  referenceVersions: string[]; repetitionCountingAvailable: false;
};
type GuideItem = { id: Id; text: string; source: string };
type TrainingModule = {
  slug: MovementSlug; name: string; order: number;
  description: string | null; level: string | null;
  estimatedDurationSeconds: number | null;
  capability: Capability;
};
type UploadConfig = {
  movementSlug: MovementSlug; acceptedMimeTypes: string[];
  maxBytes: number; maxDurationSeconds: number;
  retentionSeconds: 86400; recommendedDurationSeconds: number | null;
};
```

Full name mengikuti auth: trim, 3–120 karakter; division/title trim, 1–120
karakter atau null. PATCH kosong ditolak. NPM dan email read-only pada PATCH
profil; tidak dapat mengubah role/sabuk lewat API tersebut. Metadata sabuk dan
target adalah input administrator yang berwenang, nullable sampai workflow
tersebut tersedia; tidak dihitung dari score. Avatar upload bukan scope MVP;
FE memakai inisial. `title` berlaku Coach, `belt/beltTarget/coach` berlaku Member;
field yang tidak berlaku null. Email legacy belum otomatis terverifikasi.
`passwordChangedAt` akun legacy null, bukan waktu registrasi yang disamarkan.
ActivitySummary Coach mencakup binaan aktif, Member hanya sesinya sendiri.
Sebelum tabel sesi tersedia, Fase 2 menghitung evaluasi legacy sebagai completed
untuk ringkasan profil, tanpa menghitung duplikat saat backfill Fase 3. Durasi
legacy tidak diketahui (durationSampleCount 0); versi fitur yang tidak disimpan
mengecualikan skor dari rata-rata. Statistik Coach berbasis binaan baru tersedia
Fase 6; kini profil Coach/overview berisi statistik binaan aktif, termasuk nol
untuk scope kosong, bukan ringkasan global Member. ActivitySummary dalam dashboard tetap non-null; FE profil
menampilkan statistik belum tersedia bila statistics null.

Ganti password memeriksa password lama, kebijakan 8–128 karakter, menolak
password baru yang identik, kemudian mencabut seluruh refresh dan access
tokens melalui authVersion (lihat rancangan transisi di architecture.md).
Tidak otomatis login ulang. Ini sudah berlaku pada endpoint password Fase 2;
logout existing tetap mencabut refresh sesi saat ini. JWT lama tanpa authVersion
diterima hanya selama authVersion akun masih 0. Lihat contoh dan bukti di
[phase2-api.md](phase2-api.md).

Fase 7: penautan email wajib reauth; hanya email terverifikasi yang boleh
menerima reset. Email baru tidak mengganti identifier sampai konfirmasi valid;
setelah linking, NPM dan email terverifikasi dapat dipakai login pada akun yang
sama. Tidak menghapus NPM atau memindahkan email milik akun lain. Email akun
existing yang belum verified memakai alur request/confirm yang sama. Conflict
uniqueness diperiksa kembali saat confirm, tanpa enumerasi pada request publik.
Request generik: `{"detail":"Jika memenuhi syarat, instruksi akan dikirim."}`.
Token salah/kedaluwarsa/terpakai → 422 `invalid_or_expired_token`.
Konfirmasi reset mencabut seluruh sesi; password/email tidak muncul dalam URL
log atau respons. SMTP test adapter, rate limit dan token hashing/expiry
sudah tersedia pada Fase 7. Link confirm mencabut seluruh sesi; verifikasi
email existing mempertahankan sesi. Token terikat authVersion dan alamat email;
password change/reset atau linking membatalkan token pending lama. Request baru
menggantikan token purpose yang sama hanya jika pengiriman berhasil.

Recovery request: 5/jam per identity dan 20/jam per IP; confirm 10/15 menit
per IP. IP berasal dari koneksi langsung, bukan header forwarded arbitrer.
Login existing dibatasi 10/15 menit per identifier; endpoint auth POST selain
logout mendapat limit IP 120/15 menit, registrasi 20/jam. Auth existing tetap
error `{detail}` termasuk 429; recovery baru memakai `{detail,code,requestId}`
pada error, UUID juga di X-Request-ID. Rate limit login/IP dapat dikonfigurasi
di Settings; reset request tetap generik pada email nonverified/tidak ada/SMTP
gagal. Detail operasi dan batas timing: [phase7-api.md](phase7-api.md).

## 4. Sesi upload/job, evaluasi/media (Fase 3–4 tersedia)

Seluruh endpoint Member pada tabel berikut tersedia. evaluationUrl pada
AcceptedSession aktif; media.playbackPath menunjuk endpoint video privat hanya
jika media available. Endpoint Coach dengan scope penugasan tersedia pada Fase 6.

| Fase | Method + path | Perilaku |
| --- | --- | --- |
| 3 | `POST /member/sessions` | Multipart `movementSlug`, `video`, optional `retryOf`; 202 + AcceptedSession |
| 3 | `GET /member/sessions/{sessionId}` | Session, 200; status job tanpa persentase progres buatan |
| 4 | `GET /member/sessions/{sessionId}/evaluation` | Evaluation, 200 jika completed; queued/processing → 409 `evaluation_pending`; failed → 409 `analysis_failed` |
| 4 | `GET /member/sessions/{sessionId}/pose` | `{sessionId,pose: PoseData|null,reason:string|null}`, 200; sebelum selesai → 409 |
| 4 | `POST /member/sessions/{sessionId}/acknowledge` | Idempotent; `{acknowledgedAt}` 200, hanya completed |
| 4 | `DELETE /member/sessions/{sessionId}` | 204; soft-delete akses, cancel/fence job, cleanup media; pengulangan owner tetap 204 |
| 4 | `GET /member/sessions/{sessionId}/video` | 200/206 streaming privat; expiry/deletion/unavailable → 410 |

Upload menerima MP4/MOV/WebM, batas awal 100 MiB (`104857600` byte), 60 detik,
sesuai konfigurasi existing. Metadata diperiksa server melalui decoder;
filename, content-type dan metadata client bukan bukti validitas. File kosong,
corrupt, durasi berlebih → 422; tidak membuat sesi sukses. Validation selesai
sebelum 202; inference dilakukan worker setelah commit. Sebelum 202 tidak ada
sessionId yang bisa dipoll. `uploadedAt` adalah waktu penerimaan seluruh byte
selesai, bukan waktu metadata validation/inference selesai.

POST sesi wajib `Idempotency-Key` (opaque, 1–128 karakter), scope owner+operation;
fingerprint dari checksum byte, movementSlug, retryOf. Key/payload sama memberi
ID dan respons penerimaan sama; beda payload → 409. Simpan dedup minimal 24 jam;
jangan menghidupkan ulang sesi yang telah dihapus lewat replay key. Acknowledge
menyimpan timestamp pertama, bukan membuat evaluasi. `retryOf` harus sesi sendiri
dengan kategori sama; sesi baru tetap mandiri dan tidak menimpa hasil sebelumnya.

```typescript
type AcceptedSession = {
  sessionId: Id; processingStatus: "queued";
  statusUrl: string; evaluationUrl: string; uploadedAt: Utc;
};
type Media = {
  status: "available" | "expired" | "deleted" | "unavailable";
  expiresAt: Utc | null; mimeType: string | null; byteSize: number | null;
  durationSeconds: number | null; width: number | null; height: number | null;
  playbackPath: string | null;
};
type Session = {
  id: Id; movementSlug: MovementSlug; createdAt: Utc; uploadedAt: Utc | null;
  startedAt: Utc | null; completedAt: Utc | null;
  processingStatus: "queued" | "processing" | "completed" | "failed";
  analysisStatus: string | null; evaluationId: Id | null;
  reviewStatus: "pending" | "needs_revision" | "approved";
  reviewAvailable: boolean; retryOf: Id | null; acknowledgedAt: Utc | null;
  error: {code: string; detail: string} | null; media: Media;
};
type Measurement = {
  feature: string; bodyPart: string; value: number | null;
  unit: "deg" | "shoulder_width";
  referenceMedian: number | null; referenceIqr: number | null;
  deviation: number | null;
  assessment: "within_reference" | "deviates" | "not_assessed";
  reason: string | null;
};
type AnalysisIssue = {
  feature: string; bodyPart: string; deviation: number;
  unit: "deg" | "shoulder_width"; severity: "low" | "medium" | "high";
  feedback: string;
};
type Evaluation = {
  id: Id; sessionId: Id; movementSlug: MovementSlug; evaluatedAt: Utc;
  analysisStatus: "experimental" | "reference_not_ready" |
    "insufficient_pose" | "insufficient_features";
  score: number | null; scoreUnit: "similarity_points";
  scoreReason: string | null; matchedVariant: string | null;
  method: "static-reference-pose"; analyzerVersion: string;
  featureVersion: string | null; referenceVersion: string | null;
  poseStatus: "detected" | "not_detected";
  framesProcessed: number; validPoseFrames: number; featuresCompared: number | null;
  keyFrame: {index:number; timeSeconds:number} | null;
  measurements: Measurement[]; issues: AnalysisIssue[];
  validRepetitions: null; deviatedRepetitions: null;
  unavailableReasons: string[];
};
type PoseData = {
  kind: "keyframe"; frameIndex: number; timeSeconds: number;
  coordinateSystem: "image-normalized"; origin: "top-left";
  imageWidth: number; imageHeight: number;
  landmarks: {index:number; x:number; y:number; z:number; visibility:number}[];
};
```

`PoseData` adalah raw image landmark yang dipersist saat keyframe dipilih,
bukan koordinat hip-centered hasil normalisasi untuk scoring. x/y relatif
lebar/tinggi frame; z relatif skala lebar gambar dan bukan meter. Sisi kiri/kanan
anatomi mengikuti index MediaPipe, bukan mirror preview. Payload menyatakan
keyframe saja, bukan animasi seluruh video. Landmark nonfinite/tidak valid
diomit; pose null bila tidak disimpan/terukur. Legacy result tidak merekam data
ini, sehingga tidak dapat direkonstruksi dari video yang sudah dihapus.
Dimensi pose adalah frame inference setelah resize/orientasi, dapat berbeda
dari dimensi media sumber. Tanpa pasangan referensi yang comparable, frame
pertama dengan minimal delapan fitur valid dipakai untuk pose/measurement;
ini tidak menghasilkan skor atau keputusan teknik.

Reference median/IQR adalah statistik dataset, bukan target benar teknik.
Assessment untuk fitur yang benar-benar dibandingkan mengikuti ukuran deviasi
eksperimen existing (kurang dari 1 IQR vs minimal 1 IQR); tidak menjadi keputusan
Coach. Fitur yang tidak bisa dibandingkan → not_assessed. Daftar measurement
bisa kosong dan tidak dibatasi lima bagian. Issues existing maksimal enam
deviasi terpilih, bukan daftar semua fitur; tidak boleh menganggap fitur yang
absen dari issues sebagai sesuai. Version hasil legacy yang tidak disimpan
secara eksplisit tidak diisi dengan versi analyzer yang sedang berjalan.

Contoh akun mengunggah kategori tanpa referensi, **ilustrasi kontrak**, bukan
hasil inference baru:

```json
{
  "sessionId": "<session-id>",
  "processingStatus": "completed",
  "analysisStatus": "reference_not_ready",
  "score": null,
  "scoreReason": "reference_not_ready",
  "reviewStatus": "pending",
  "reviewAvailable": false,
  "coach": null,
  "measurements": [],
  "validRepetitions": null
}
```

Objek contoh di atas adalah proyeksi field gabungan untuk menjelaskan state;
respons lengkap mengikuti Session/Evaluation masing-masing. Null bukan nol.

Media: `expiresAt=uploadedAt+86400 detik`, tidak diperpanjang oleh refresh,
acknowledge, review, atau retry job. Link playback hanya relative path ke
endpoint terproteksi, tidak mengungkap storage key. Periksa owner/binaan dan
waktu saat setiap request, termasuk Range. Gunakan proxy FE untuk Bearer (lihat
fe-integration.md), bukan URL token publik atau static directory. Dukung
single byte range dan suffix range, `Accept-Ranges: bytes`, `Content-Length`,
`Content-Type`, `Content-Range` pada 206, 416 untuk range tidak valid atau
multi-range yang belum didukung. Jangan memuat seluruh file ke RAM. Stream
ditutup saat expiry/delete/akses dicabut; pemeriksaan ulang berkala maksimal
1 detik, dan setiap chunk memeriksa deadline/deletion. Byte yang sudah terkirim
tidak dapat ditarik kembali.

Legacy evaluation dipetakan ke training session lewat migrasi Fase 3 (ID hasil
lama tetap). `uploadedAt=null`, `media.status=unavailable`, expiresAt/playbackPath
null; jangan membuat expiry seolah video lama tersimpan. DELETE menutup akses
detail baru dan statistik, tetapi hasil/review audit tetap disimpan. Media
expiry sendiri tidak menghapus sesi/evaluasi dari histori.

## 5. Histori dan agregat (Fase 5 tersedia)

| Endpoint | Respons |
| --- | --- |
| `GET /member/history` | `{items: HistoryItem[],nextCursor}` dengan filter Bagian 2 |
| `GET /member/history/{sessionId}` | SessionDetail |
| `GET /member/dashboard` | Dashboard |

Endpoint Member berikut tersedia. Sejak Fase 6, coach berasal dari assignment
aktif, review/reviewHistory/followUpTasks dari publikasi; nullable/kosong jika
belum ada. legacyNotes tetap terpisah. Filter reviewStatus memakai latest head.

```typescript
type HistoryItem = {
  session: Session; movementName: string; score: number | null;
  scoreReason: string | null; review: PublishedReview | null;
};
type SessionDetail = {
  session: Session; evaluation: Evaluation | null;
  coach: CoachIdentity | null; review: PublishedReview | null;
  reviewHistory: PublishedReview[]; legacyNotes: PublishedNote[];
  followUpTasks: FollowUpTask[];
};
type Dashboard = {
  statistics: ActivitySummary;
  lastSession: HistoryItem | null; latestCoachNote: PublishedNote | null;
  coach: CoachIdentity | null;
  dominantMovementSlug: MovementSlug | null;
  weeklyActivity: {date:string; sessionCount:number; durationSeconds:number}[];
  timezone: "Asia/Jakarta";
};
```

Total sesi = completed, non-deleted. Pending/failed ditampilkan dalam histori
tetapi tidak menambah statistik selesai. Durasi total hanya verified duration
dari sesi completed tersebut; durationSampleCount menunjukkan cakupan termasuk
legacy tanpa durasi. Jangan menyebut durasi video sebagai jam sensor aktif.
Rata-rata dihitung per `(movementSlug,method,analyzerVersion,featureVersion,
referenceVersion)` untuk score non-null; tidak ada global average lintas versi
atau lintas kategori. `excludedScoreCount` menghitung sesi completed tanpa skor
atau versi pembanding lengkap. Null bukan sampel bernilai 0.

Dominant movement = jumlah sesi completed terbanyak; tie mengikuti urutan modul.
Akun kosong → null. Last session = completed terbaru berdasar completedAt/ID.
Latest note = published note terbaru pada sesi yang masih terlihat, termasuk
author Coach lama; timestamp publishedAt/ID menjadi tie breaker. Empat kategori
boleh diringkas, tetapi satu sesi hanya punya satu kategori.

Weekly activity = tujuh tanggal Senin–Minggu minggu berjalan di Asia/Jakarta,
berdasarkan completedAt. Tanggal dikirim `YYYY-MM-DD`, timestamp tetap UTC.
Hari tanpa completed session memiliki sessionCount/durationSeconds 0; hari
berikutnya tidak diprediksi. Empty account: similarityGroups [], lastSession,
latestCoachNote, dominantMovementSlug, coach null (coach bisa non-null bila akun
kosong sudah ditugaskan). Ringkasan UI average/target tanpa kelompok yang sah
harus menampilkan belum tersedia, bukan 0%.

## 6. Coach, review, dan tindak lanjut (Fase 6 tersedia)

| Method + path | Input → respons |
| --- | --- |
| `GET /coach/overview` | `{memberCount,reviewQueueCount,statistics,recentSessions:HistoryItem[],topIssues:IssueCount[]}`; recentSessions max 5 |
| `GET /coach/roster` | Pagination + q → `{items:RosterMember[],nextCursor}` |
| `GET /coach/roster/{memberId}` | `{profile,statistics,latestSession:HistoryItem|null}` |
| `GET /coach/roster/{memberId}/sessions` | Pagination/filter sama histori → `{items:HistoryItem[],nextCursor}` |
| `GET /coach/sessions/{sessionId}` | SessionDetail + `feedbackDraft:FeedbackDraft|null` milik pemohon |
| `GET /coach/sessions/{sessionId}/video`, `GET /coach/sessions/{sessionId}/pose` | Kebijakan media/pose sama seperti Member |
| `PUT /coach/sessions/{sessionId}/feedback-draft` | `{expectedVersion,bodyAssessments,note,decision,tasks}` → FeedbackDraft, 200 |
| `POST /coach/sessions/{sessionId}/reviews` | `{expectedRevision,expectedDraftVersion}` + Idempotency-Key → PublishedReview, 201 |
| `POST /member/sessions/{sessionId}/follow-ups` | `{intent:"retry"}` + Idempotency-Key → RetryIntent, 201 |
| `PATCH /member/follow-up-tasks/{taskId}` | `{status:"completed"|"dismissed"}` → FollowUpTask, 200 |

Review queue menghitung sesi completed non-deleted milik binaan aktif tanpa
published review; status analysis tanpa referensi tetap boleh ditinjau manusia.
Top issues menghitung sesi berbeda per feature, maksimal enam feature teratas;
tie feature ascending, jumlah eksplisit; tidak menghasilkan koreksi cm/diagnosis.
RosterMember = `{profile:Profile,latestSession:HistoryItem|null}`. IssueCount =
`{feature:string,sessionCount:number}`. Overview tanpa binaan: counts 0,
statistics kosong, recentSessions/topIssues [].

```typescript
type BodyAssessment = {
  bodyPart: string; status: "not_assessed" | "needs_revision" | "approved";
  note: string | null;
};
type FeedbackDraft = {
  version: number; author: CoachIdentity; updatedAt: Utc;
  decision: "needs_revision" | "approved" | null;
  note: string | null; bodyAssessments: BodyAssessment[];
  tasks: {instruction:string}[];
};
type PublishedNote = {
  id: Id; author: CoachIdentity; text: string; publishedAt: Utc;
};
type PublishedReview = {
  id: Id; revision: number; author: CoachIdentity; publishedAt: Utc;
  decision: "needs_revision" | "approved";
  note: string | null; bodyAssessments: BodyAssessment[];
  taskIds: Id[]; supersedesReviewId: Id | null;
};
type FollowUpTask = {
  id: Id; sessionId: Id; reviewId: Id; author: CoachIdentity;
  instruction: string; status: "open" | "completed" | "dismissed";
  createdAt: Utc; updatedAt: Utc;
};
type RetryIntent = { id: Id; sourceSessionId: Id; createdAt: Utc };
```

Draft awal memakai expectedVersion 0, versi berikutnya harus cocok. Semua
payload teks trim: note max 5000 karakter (null boleh), bodyPart 1–80, note
bagian max 2000; maksimal 33 bodyAssessments dengan bodyPart unik dan 20 tasks,
instruksi 1–2000 karakter. Publish memerlukan decision non-null, evaluation
completed, versi draft dan expectedRevision cocok (0 jika belum ada review).
Publish atomik: snapshot immutable review, note/tasks, revision terbaru, dan
hapus draft versi yang diterbitkan; konflik → 409 tanpa perubahan parsial.
Review dapat direvisi melalui draft baru; tidak mengedit baris historis.
Author dari auth, bukan payload. Revisi tidak otomatis menghapus tugas lama;
tugas tetap mempunyai author/review asal dan statusnya sendiri. Tidak mengubah
skor analyzer. PublishedReview.note adalah sumber note review; legacyNotes
berasal dari coach_notes lama, tidak menggandakan note baru ke dua sumber.

Idempotency publish/retry-intent memakai aturan key sama seperti upload,
scope actor+operation+session; replay tidak membuat review/tugas duplikat.
RetryIntent bukan tugas Coach, bukan hasil evaluasi, dan tidak mengubah keputusan;
upload berikutnya membawa `retryOf=sourceSessionId`. Pengguna dapat mengulangi
latihan tanpa mempunyai Coach. Tugas hanya untuk pemilik sesi; perubahan status
tidak mengubah isi instruksi manusia.
RetryIntent hanya dapat dibuat untuk sesi terminal completed/failed; queued/
processing menghasilkan 409 `session_not_terminal`. Histori review tidak
menyembunyikan revisi sebelumnya atau mengganti author ketika dipublikasikan.

**Penugasan dan transfer:** satu Member maksimal satu Coach aktif, satu Coach
banyak Member. Penugasan hanya CLI administrator, bukan endpoint self-assignment.
Tidak ada penugasan berarti Member tetap dapat upload, scoring, membaca hasil,
dan latihan ulang. Saat transfer, Coach baru membaca seluruh histori/published
review dengan author asli. Coach lama kehilangan akses Member, media, draft,
dan revisi—even review yang ditulisnya. Draft lama tidak diwariskan ke Coach
baru dan disimpan sebagai arsip privat yang tidak disajikan endpoint aktif.
Coach baru boleh merevisi melalui review baru dengan author dirinya sendiri.
Transfer/publish memakai lock penugasan yang sama; otorisasi diperiksa ulang
di transaksi agar hasil race mempunyai satu urutan commit yang sah. Jangan
mengubah author/review lama menjadi nama Coach baru. UI membedakan pembina
sekarang dari penulis historis.

## 7. Acceptance kontrak fase berikutnya

- Fase 2: profil NPM-only valid; identity/role/sabuk tidak writable; password
  lama/sesi dicabut sesuai kebijakan; empat modul jujur tentang capability.
- Fase 3–4: idempotensi upload, corrupt/size/duration, dua worker/restart/fencing,
  satu hasil per sesi, pending/failed/null, legacy tanpa media, Range dan expiry
  tepat 24 jam, delete selama inference, akses owner/non-binaan.
- Fase 5: empty/null, kelompok versi, sampel/durasi legacy, batas Senin/hari
  Jakarta, cursor timestamp sama, filter, penghapusan dan transfer scope.
- Fase 6: CLI assign/transfer/revoke, Member tanpa Coach, author lama,
  draft tidak bocor, konflik revisi, publish/replay atomik, tindak lanjut.
- Fase 7: email verified/uniqueness, reset generik, expiry/single-use/rate limit,
  auth refresh paralel/SSR isolation, MySQL disposable, alur API dan browser.

Acceptance Fase 2–6 sudah diuji; bukti di [phase2-api.md](phase2-api.md),
[phase3-api.md](phase3-api.md), [phase4-api.md](phase4-api.md), [phase5-api.md](phase5-api.md), [phase6-api.md](phase6-api.md).
Acceptance Fase 7 dan batas uji aktual: [phase7-api.md](phase7-api.md).
Fase 6–7 diuji native tanpa Docker. Endpoint prototype tetap kompatibel;
consumernya belum dipastikan pindah, sehingga tidak dihapus atau ditandai
OpenAPI deprecated secara menyesatkan. Untuk integrasi baru gunakan endpoint
Member/Coach camelCase; endpoint lama hanya jalur kompatibilitas.
