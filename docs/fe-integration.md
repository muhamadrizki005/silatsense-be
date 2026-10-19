# Integrasi frontend SilatSense — audit dan perubahan yang diperlukan

> Pembaruan 19 Oktober 2026: endpoint/schema HTTP prototype sudah dihapus.
> Rujukan kompatibilitas lama di catatan fase di bawah bersifat historis.
> Kontrak aktif dan pemetaan pengganti: [route-cleanup.md](route-cleanup.md).

Status diperbarui: 18 Oktober 2026. Fase 1–6 membaca FE saja; **Fase 7 kini
mengubah FE untuk auth bridge dan keamanan akun**. Backend Fase 2–7 tersedia
dengan migrasi head 0007; kontrak [api-contract.md](api-contract.md), bukti native
dan batas pengujian [phase7-api.md](phase7-api.md). Panduan FE aktual berada di
silatsense-fe/docs/backend-phase7-auth.md. Matriks di bawah tetap memetakan
kemampuan backend, bukan klaim semua halaman sudah terhubung.

## 1. Kondisi aktual dan alur target

Audit sumber: `features/auth/types.ts` dan forms; `features/member/types.ts`,
`features/member/data/get-*.ts`, dummy, pages dan komponen upload/evaluasi;
`features/profile/types.ts`, schema, data dan action; specs Member di
`docs/superpowers/specs`, roadmap Coach, serta `docs/CODE_STANDARD.md` FE.

Auth forms sudah memanggil server action login/sign-up. Layout Member/Coach
memvalidasi GET auth/session ke BE; token tidak masuk props. lib/api-client.ts
server-only menambahkan Bearer per request/no-store. /account-security membaca
profil nyata dan menyediakan link/verify/password change; /confirm-email,
/forgot-password dan /reset-password terhubung ke API recovery.

Data latihan/dashboard/history/profil biodata/Coach masih dummy dengan use cache,
evaluasi memakai slug dan detail ID contoh, update profil echo input, upload
timer simulasi. Banner guard menandai layar latihan sebagai demo. Koneksi data
pribadi berikutnya wajib menghapus use cache tersebut, memakai sessionId/null/
pagination serta menghapus metrik/label dummy. Kamera preview browser-only;
storage/playback FE masih placeholder. Spec dummy bukan legitimasi angka teknik.

Alur integrasi utama: login → katalog/persiapan → pilih video existing → upload
nyata → terima sessionId → poll status → evaluasi tersimpan → histori/dashboard
→ Coach aktif publish review → Member membaca review/tugas. Rekam kamera bukan
prioritas awal; preview/device browser tidak perlu endpoint BE.

| Halaman / action FE | API target | Delta |
| --- | --- | --- |
| sign-in/sign-up | Auth existing `/auth/sign-in`, `/auth/sign-up` | Server actions, cookie bridge, error nyata |
| dashboard | `/member/dashboard` | Empty/null, kelompok similarity dan tanggal lokal |
| latihan | `/member/training-modules` | Empat kategori, capability tanpa referensi |
| persiapan | `/member/training-prep/{slug}` | Panduan bersumber, checklist pengguna, bukan kalibrasi palsu |
| rekam | `/member/record-config/{slug}` | Optional browser capture; hapus TODO `/member/cameras` |
| sesi/upload | `POST /member/sessions`, `GET /member/sessions/{sessionId}` | File nyata, sessionId, polling; slug hanya kategori |
| evaluasi | `/member/sessions/{sessionId}/evaluation`, `/pose`, `/video` | Nullable/status, keyframe, playback privat |
| Selesai dan Simpan | `/member/sessions/{sessionId}/acknowledge` | Hasil sudah persisted sebelum tombol; acknowledge idempotent |
| Hapus/latihan ulang | DELETE sesi, POST follow-ups; upload baru membawa retryOf | Tidak menghapus hasil lama ketika sekadar ingin mengulang |
| riwayat dan detail | `/member/history`, `/member/history/{sessionId}` | Cursor, item ber-ID, review pending/approved/needs_revision |
| profil | `/member/profile` atau `/coach/profile`, PATCH/password sesuai role | Identity read-only, kamera lokal, role dari sesi |
| Coach (belum ada UI) | `/coach/overview`, `/coach/roster`, `/coach/sessions/{sessionId}` dan review | UI binaan, draft pribadi, konflik revisi, transfer |

FE dapat mempertahankan layout katalog `/latihan/[slug]`, tetapi hasil harus
membawa sessionId, misalnya `/latihan/[slug]/evaluasi?sessionId=<id>`; detail
`/riwayat/[id]` memakai ID sesi. Jangan fallback ke hasil dummy bila 404.

## 2. Matriks field DTO FE

Legenda: **A tersedia** pada auth/prototype/hasil existing; **C bisa dihitung**
dari data nyata (belum berarti endpoint agregat ada); **H input manusia** yang
memerlukan sumber/otoritas; **B browser-only** atau presentasi lokal;
**R membutuhkan riset** sebelum nilai ilmiah bisa diberikan. Kombinasi berarti
sumber berbeda per subfield. Kolom nullable mengacu nilai target, bukan tipe
dummy FE yang masih mewajibkan field. Label/warna selalu diformat FE dari nilai
mentah atau copy lokal, tidak menjadi field permanen REST.

### Auth dan profil

| DTO.field FE existing | Kelas / sumber | Target, nullable, perubahan |
| --- | --- | --- |
| AuthUser.id, fullName, identifier, role | A — users/auth serializer | Sudah cocok; id string, role member/coach, non-null |
| SignInRequest.identifier, password, rememberMe | A — schema auth | Sudah cocok; password tidak disimpan client/log |
| SignUpRequest.fullName, identifier, password | A — schema auth | Sudah cocok; confirmPassword/terms validasi browser saja |
| SignInResponse.user, accessToken, expiresIn; SignUpResponse field sama | A — auth baru | Tidak ubah DTO; tokens hanya server bridge untuk arsitektur target |
| AthleteProfile.role, name; CoachProfile.role, name | A — users | name → fullName; role dari pengguna terautentikasi |
| AthleteProfile.handle; CoachProfile.handle | B — label FE | Tidak ada username baru; tampilkan identifier atau inisial, bukan identity fiktif |
| AthleteProfile.nim; UpdateProfileInput.nim | A — users.npm | Rename npm, nullable akun email-only, read-only; contoh NIM di UI tidak mengubah aturan NPM auth |
| AthleteProfile.email; CoachProfile.email; UpdateProfileInput.email | A — users.email | Nullable NPM-only; read-only Fase 2; linking/verification Fase 7 |
| AthleteProfile.roleLabel | B — role | Format FE, non-null jika role ada |
| AthleteProfile.division; CoachProfile.division | H — profil pengguna | String/null, PATCH diizinkan |
| CoachProfile.titleLabel | H/B — title dan format | title nullable, PATCH Coach diizinkan |
| AthleteProfile.beltLabel, beltTargetLabel | H/B — admin dan format | belt/beltTarget nullable, Member tidak boleh mengubah; tidak disimpulkan dari skor |
| AthleteProfile.avgAccuracyPct, accuracyNote | C/B — kelompok skor + penjelasan | Ganti similarityGroups/sampleCount; average null bila tidak ada sampel sebanding |
| AthleteProfile.totalSessionsLabel | C/B — completedSessionCount | Count 0 akun kosong; FE memformat |
| AthleteProfile.totalPosturesLabel | R — definisi jumlah postur belum ada | Hilangkan/null; validPoseFrames tidak menjadi jumlah postur atau repetisi |
| AthleteProfile.cameraDeviceLabel; CoachProfile.cameraDeviceLabel; UpdateProfileInput.cameraDeviceId | B — enumerateDevices/settings browser | Simpan lokal per browser, jangan kirim PATCH profil |
| AthleteProfile.passwordUpdatedLabel; CoachProfile.passwordUpdatedLabel | C/B — passwordChangedAt | Timestamp/null (legacy), format FE; jangan memakai createdAt sebagai pengganti |
| CoachProfile.teamAccuracyPct | C — skor binaan aktif per kelompok | similarityGroups, bukan average seluruh tim lintas metode; null jika tanpa sampel |
| CoachProfile.coachedSessionsLabel | C/B — statistik binaan aktif | Count completed sesi binaan, bukan klaim sesi yang personally direview |
| UpdateProfileInput.name | H — perubahan nama | Rename fullName, trim 3–120; field PATCH lain memakai whitelist kontrak |

### Dashboard

| DTO.field FE existing | Kelas / sumber | Target, nullable, perubahan |
| --- | --- | --- |
| MemberDashboard.greeting | A/C/B — profil dan sesi | Compose FE, bukan object greeting berisi copy dari BE |
| GreetingData.name | A — user.fullName | Non-null |
| GreetingData.lastSessionDaysAgo | C — lastSession completedAt | Nullable bila belum latihan; selisih tanggal Jakarta, bukan pembulatan jam UTC |
| GreetingData.focusTechnique | C/H — dominantMovementSlug atau tugas Coach | Nullable; label sebagai aktivitas terbanyak jika derivasi count, bukan kelemahan teknis otomatis |
| MemberDashboard.heroMetric | C/R/B — campuran | Pecah field; jangan wajib object metrik contoh |
| HeroMetricData.accuracyPct | C — similarity group | Rename averageScore, nullable, label kemiripan eksperimen |
| HeroMetricData.elbowToleranceDeg, targetDeg | R — rubric belum tervalidasi | Null/hilangkan; median/IQR dataset jika ditampilkan harus bernama statistik referensi, bukan toleransi resmi |
| HeroMetricData.cameraDistanceM | R — kalibrasi fisik belum ada | Null/hilangkan |
| HeroMetricData.cameraReady | B — permission/preview | Bukan skor kalibrasi backend |
| MemberDashboard.pillars; PillarStat.slug, name | A — katalog | Ringkasan empat kategori; tidak empat hasil dari satu sesi |
| PillarStat.avgPct | C — similarity per kategori/versi | Nullable; nama averageScore dengan sampleCount |
| PillarStat.status, statusLabel, detail | H/B — keputusan atau label capability | Jangan derive optimal/stabil dari ambang dummy; pending/not_assessed tanpa data manusia |
| PillarStat.active | B — kategori dipilih UI | Optional state lokal |
| MemberDashboard.lastSession | C — completed terbaru | Nullable |
| LastSessionData.technique, time | A/C/B — movement/UTC timestamp | movementName/completedAt; FE format |
| LastSessionData.reps | R — counting tidak ada | Null/hilangkan |
| LastSessionData.scorePct, scoreLabel | A/B — hasil score | Nullable similarity_points; bukan accuracyPct |
| LastSessionData.observations | A/H — issues/published review | Array boleh kosong; bedakan observasi analyzer dan catatan manusia |
| SessionObservation.tone, title, body | A/H/B — severity/feature/feedback atau review | Tone/title FE; body nyata, jangan kesimpulan yang tidak terukur |
| MemberDashboard.weekly; WeeklyData.days | C — weeklyActivity | Tujuh tanggal, sessionCount dan durationSeconds |
| WeeklyData.title, weekLabel | B — copy/rentang tanggal | Format FE dari tanggal Jakarta |
| WeeklyData.targetLabel | H/B — target latihan yang ditetapkan | Nullable/hilangkan bila belum ada target; bukan angka tetap UI |
| WeekDay.label, value, state | C/B — date/count | label/date FE, value=count (0 tanpa sesi); filled/active/empty dari tanggal/count, jangan infer rest terjadwal |
| MemberDashboard.coachNote | H — latest published note | Nullable, termasuk author historis |
| CoachNoteData.initials, name, quote | H/B — author snapshot/text | Inisial dihitung FE, name/text tidak dikarang |

### Katalog, persiapan, kamera, dan upload

| DTO.field FE existing | Kelas / sumber | Target, nullable, perubahan |
| --- | --- | --- |
| MemberTraining.modules | A — movements + metadata | Empat modul; array tidak hardcode jumlah histori |
| TrainingModule.slug, name | A — movements | Slug mapping publik eksplisit |
| TrainingModule.order, orderLabel | C/B — urutan katalog seed | order 1–4 untuk kuda-kuda/pukulan/tangkisan/tendangan; label FE |
| TrainingModule.levelLabel, description, estimateLabel | H/B — katalog bersumber | level/description/estimatedDurationSeconds nullable; FE tidak mengarang level/durasi |
| MemberTraining.hero; TrainingHero.badges, title, subtitle | B — copy halaman | Tidak dikirim sebagai API DTO |
| TrainingHero.sessionsLabel, accuracyLabel | C/B — statistics | Count nyata dan kelompok kemiripan nullable, label FE |
| PersiapanDetail.slug, title | A/B — katalog | slug/name non-null; title format FE |
| PersiapanDetail.eyebrow, readinessLabel | B — copy/checklist | Readiness pengguna/browser, bukan bukti MediaPipe siap |
| PersiapanDetail.accuracyLabel, accuracyValue | R/B — klaim benchmark dummy | Hapus/null; capability referensi bukan akurasi model |
| PersiapanDetail.description | H — metadata modul | Nullable jika sumber panduan belum tersedia |
| PersiapanDetail.coachQuote | H — authored guidance/review | Nullable tanpa sumber dan tanpa Coach; jangan atribusi nama palsu |
| PersiapanDetail.checks; CalibrationCheck.title, detail | H/B — checklist panduan | GuideItem.text/source atau copy browser yang disahkan |
| CalibrationCheck.stateLabel | B — checklist/permission | State lokal; bukan hasil ukur jarak/sudut kamera |
| PersiapanDetail.guides; PostureGuide.term, detail | H — panduan bersumber | GuideItem, array kosong bila belum disahkan; jangan mengubah median dataset menjadi nasihat resmi |
| CameraDevice.id, label, resolution, fps, latencyMs | B — MediaDevices/getSettings | Lokal; permission dapat membuat label kosong; resolution/fps/latency null jika tidak benar-benar diukur |
| RekamSession.slug, trainingName | A — katalog | movementSlug/name |
| RekamSession.eyebrow | B — copy | Lokal |
| RekamSession.countdownSec | B — UI capture | Lokal, bukan konfigurasi analisis |
| RekamSession.targetDurationSec | H/C — guidance dan maxDurationSeconds | recommendedDurationSeconds nullable; batas upload bukan target performa |
| RekamSession.camera | B — device aktif | Nullable; alur upload file tidak memerlukan kamera |
| TrainingSession.slug, trainingName, eyebrow | A/B — katalog/copy | Tambah sessionId dari 202; tidak memakai slug sebagai identitas sesi |
| TrainingSession.durationSec, durationLabel | C/B — decoder metadata | durationSeconds nullable sebelum validasi; label FE |
| TrainingSession.recordedAtLabel | B/C — file metadata jika ada | Waktu rekam file tidak terpercaya; tampilkan uploadedAt server, jangan menyamakannya dengan tanggal rekaman |
| TrainingSession.fileSizeLabel | C/B — byteSize file/server | FE format, byteSize server sumber setelah penerimaan |
| TrainingSession.camera | B — optional capture metadata | Tidak wajib untuk file yang sudah ada |
| TrainingSession.videoStatus | B/C — File lokal lalu Session.media.status | Ganti literal recorded/placeholder dengan state upload/media nyata |
| SesiUploadState idle/uploading/failed/success | B — upload transport | Pisahkan sukses transfer dari queued/processing/completed/failed analisis; hapus simulasi timer |

### Evaluasi dan postur

| DTO.field FE existing | Kelas / sumber | Target, nullable, perubahan |
| --- | --- | --- |
| EvaluationSession.slug, techniqueName, evaluatedAtLabel | A/B — hasil/katalog/timestamp | movementSlug/evaluatedAt; tambahkan sessionId dan evaluationId |
| EvaluationSession.validReps, deviatedReps | R — tidak ada counting | validRepetitions/deviatedRepetitions null; hapus badge angka |
| EvaluationSession.qualityLabel | R/B — mutu video vs hasil | Status analisis/capability nyata; jangan label mutu biomekanik otomatis |
| EvaluationSession.score | A — result score | Nullable numeric + scoreUnit/scoreReason, bukan object KinematicScore wajib |
| KinematicScore.value, unit | A — score existing | similarity_points (0–100), bukan persen akurasi |
| KinematicScore.targetPct, targetLabel | R/B — ambang 85% dummy | Null/hilangkan; keputusan approved hanya Coach |
| KinematicScore.deltaLabel | C/B — perbandingan sebanding jika ada | Nullable; tidak selisih terhadap ambang dummy |
| KinematicScore.alertLabel, summary | B/A/H — status/reason/feedback | Copy FE yang jujur, feedback analyzer vs manusia dibedakan |
| EvaluationSession.postures | A/C/H — measurements + review | Array dinamis, dapat kosong; measurements untuk hasil baru dipersist sejak Fase 4; legacy tidak direkonstruksi |
| EvaluationSession.videoStatus | C — media status | available/expired/deleted/unavailable, tanpa URL palsu |
| PostureAssessment.id, name | A/B — feature/bodyPart + mapping | ID tidak terbatas lima literal; nama FE dari key stabil |
| PostureAssessment.status, statusLabel | A/C/H/B — measurement assessment atau review manusia | within_reference/deviates/not_assessed; jangan menyamakan dengan approved/needs_revision Coach |
| PostureAssessment.reading | C/B — measurement value/referenceMedian/referenceIqr/unit | Null jika tak terukur; FE format; legacy issue saja tidak memberi observed value |
| PostureAssessment.detail | A/H — issue feedback / published body note | Nullable/empty; label sumber jelas |
| PostureAssessment.correctionCue | H/R — instruksi Coach atau koreksi cm belum valid | Hanya catatan manusia yang sah; null otomatis, tidak membuat cm dari posisi 2D |
| PostureAssessment.thumbnailLabel, thumbnailSrc | B/C — render pose keyframe | Label lokal; thumbnail/pose null bila tak disimpan; tidak menjanjikan image asset dari analyzer lama |

### Histori dan detail sesi

| DTO.field FE existing | Kelas / sumber | Target, nullable, perubahan |
| --- | --- | --- |
| MemberHistory.summary | C — ActivitySummary | Ringkasan dipisahkan dari envelope items/nextCursor; FE dapat memakai dashboard untuk kartu |
| MemberHistory.entries | A/C — sessions/evaluations | HistoryItem[] paginated, bukan persis empat kategori |
| HistorySummary.totalSessionsLabel, sessionsDeltaLabel | C/B — completed count + periode sebanding | Count nyata; delta null jika periode pembanding belum diberikan (tidak ada delta field MVP) |
| HistorySummary.avgAccuracyPct, accuracyNote | C/B — similarityGroups | Tidak ada global average campur versi, average null/label sampleCount |
| HistorySummary.dominantFocus, dominantSessionsLabel | C/B — dominantMovementSlug/count | Nullable saat kosong, count dari completed; bukan diagnosis kelemahan |
| HistorySummary.sensorHoursLabel, sensorNote | C/B — verified totalDurationSeconds + durationSampleCount | Rename durasi video, tidak jam penggunaan sensor |
| HistoryEntry.slug, techniqueName, dateLabel, timeLabel | A/B — Session movement/timestamp | Tambah id session; FE format UTC ke Jakarta |
| HistoryEntry.summary | A/H/B — analysisStatus/review | Deskripsi FE tanpa angka tidak tersedia |
| HistoryEntry.status, statusLabel | H/B — latest published decision | reviewStatus; pending tersedia; jangan putuskan kelulusan dari skor |
| HistoryEntry.scorePct, scoreCaption | A/B — score/unit | Nullable kemiripan eksperimen; hapus "Kinematika IPSI" / "Standar ≥85%" |
| HistoryEntry.params | A/C — measurements | Array dinamis, tidak wajib lima |
| HistoryEntry.coachNote | H — published review note | Nullable; draft tidak boleh masuk response |
| RiwayatParam.id, name, reading | A/C/B — measurement feature/value/unit | Sama measurement, bukan lima literal tetap |
| RiwayatParam.deviated, actionLabel | C/H/B — assessment / task | Boolean harus nullable atau enum not_assessed; label tugas hanya bila ada sumber |
| SessionDetail.id, techniqueName, techniqueDesc | A/H — session/katalog | sessionId; description nullable |
| SessionDetail.coach; coach.initials, name, role | H/B — current assignment/profile | coach nullable; tampilkan current Coach terpisah dari author published review |
| SessionDetail.decision, decisionLabel, decidedAtLabel | H/B — latest published review | pending/needs_revision/approved dan publishedAt nullable; bukan hanya menunggu/remidiasi |
| SessionDetail.focusTechnique | H/C — task atau kategori | Nullable, jangan infer masalah teknik dari dummy |
| SessionDetail.scorePct, targetPct | A/R — hasil / target tak tervalidasi | score null boleh; targetPct hapus/null |
| SessionDetail.pillars | C — agregat empat kategori milik Member | Bukan empat skor hasil sesi; pindah ke ringkasan terpisah bila diperlukan |
| SessionPillar.id, name, detail, scorePct | A/C/B — kategori/agregat | score nullable dan versi/sampleCount jelas; detail copy FE |
| SessionPillar.stageLabel, badge | H/B — human decision dan warna FE | Tidak otomatis Lolos/Fokus/Remidi dari threshold score |
| SessionDetail.video; SessionVideo.status | C — Media | Status retensi nyata; legacy unavailable |
| SessionVideo.cameraLabel, qualityLabel | B/R — capture optional / mutu belum tervalidasi | Nullable/hilangkan, tidak derive kamera user dari video upload |
| SessionDetail.postures | A/C/H — measurements/bodyAssessments | Pisahkan analyzer dan manusia; kosong/not_assessed valid |
| SessionDetail.retestLabel, retestValue | H/B — FollowUpTask/RetryIntent | Nullable, tidak tanggal tes ulang yang dikarang |

PillarStatus, PostureStatus, HistoryStatus, SessionDecision, DayState dan
ObservationTone adalah enum tampilan existing; tidak digunakan sebagai status
job/domain baru secara langsung. `PersiapanSlug`, `EvaluasiSlug`, `RiwayatSlug`
tetap kategori, bukan ID. Coach roadmap belum memiliki types nyata: overview,
TeamMember, CoachMemberDetail wajib mengikuti kontrak roster/review baru, tanpa
jumlah atlet/card/postur tetap, attendance, sabuk promotion atau PDF laporan
yang belum memiliki sumber/workflow.

## 3. Bridge autentikasi server components/actions (tersedia Fase 7)

### Kepemilikan cookie dan batas keamanan

BE tetap menerbitkan `refresh_token`, HttpOnly, SameSite=Strict, path
`/api/v1/auth`, Secure mengikuti COOKIE_SECURE; access token 900 detik, refresh
24 jam atau 7 hari dengan deadline awal tetap. **Jangan memperlebar path cookie
BE** agar video atau halaman FE bisa mengaksesnya.

FE menggunakan cookie terpisah `silatsense_session`, terenkripsi dan
authenticated encryption, HttpOnly, SameSite=Strict, host-only, path `/`, Secure
pada HTTPS. Payload server-only: random bridgeSessionId, user, accessToken,
accessExpiresAt, refreshToken, refreshDeadline, persistent, generation.
Secret enkripsi FE terpisah dari JWT_SECRET, tidak dibundel ke browser.
Cookie size harus <4 KiB; jangan memasukkan hasil evaluasi/profil panjang.
Tidak ada token di localStorage, props komponen, query string atau log.

Cookie BE tidak otomatis dikirim browser ke route FE yang lain path/domain.
Server fetch juga tidak otomatis meneruskan Cookie masuk atau Set-Cookie keluar.
Karena itu action login membaca JSON auth dan **setiap** Set-Cookie upstream
dengan parser cookie, tidak split comma (Expires berisi comma), lalu memasukkan
refresh token ke bridge terenkripsi. Backend cookie tidak dicopy mentah sebagai
cookie path `/` di browser. Saat refresh/logout, FE membangun header
`Cookie: refresh_token=<token>` khusus origin BE yang dikonfigurasi; tidak
meneruskan semua cookie browser ke upstream.

Tanpa rememberMe, cookie FE tidak memakai Max-Age/Expires, dan enforce deadline
24 jam server-side. Dengan rememberMe, Max-Age tidak melebihi sisa deadline
refresh BE; gunakan Max-Age upstream dan anchor request-start konservatif,
bukan restart tujuh hari setiap refresh. Registrasi mengikuti non-persistent.
Parsing JWT exp dari respons tepercaya membantu jadwal refresh, tetapi BE
tetap memvalidasi token/role pada setiap request. Jangan menjadikan role cookie
sebagai satu-satunya otorisasi objek.

Backend base URL adalah konfigurasi server-only (`API_BASE_URL`,
misalnya http://localhost:8001/api/v1). `.env.example` FE kini memakai API_BASE_URL localhost:8001/api/v1 dan
SESSION_ENCRYPTION_KEY server-only; .env.local aktual tidak dibuat/diubah. Browser memakai hostname konsisten localhost; jangan
mencampur 127.0.0.1/localhost. Validasi origin/CSRF action FE sebelum memanggil
BE; upstream Origin hanya origin FE sah yang dikonfigurasi, bukan menerima
Origin client arbitrer lalu menimpanya untuk meloloskan request.

### Login, pembacaan SSR, dan pemulihan access token

1. Form memanggil server action dengan validasi Zod; action login/sign-up ke BE,
   mengambil JSON + cookie upstream, menulis cookie bridge dan mengembalikan destination; client melakukan hard
   navigation sesuai role sambil membersihkan QueryClient.
2. Data server-only membaca bridge untuk request itu, menambahkan Bearer pada
   fetch BE dengan `cache:"no-store"`. Token tidak menjadi singleton api client.
3. Jika access token masih valid, lanjut. Jika sudah lewat exp (atau BE memberi
   401), render boundary pemulihan tanpa data privat dan client boundary memanggil
   refresh action satu kali. Server component tidak menulis cookie saat render.
4. Refresh action mengikuti single-flight berikut, menyimpan Set-Cookie hasil
   rotasi ke bridge dan meminta refresh halaman. Request data diulang maksimal
   satu kali. Jika hasil tetap 401, sesi dihapus dan pengguna ke sign-in.
5. Mutasi via action boleh refresh sebelum dikirim. Setelah 401, retry mutasi
   hanya bila operasi idempotent atau memakai Idempotency-Key yang sama dan
   body dapat direplay. Jangan retry upload/delete/publish secara buta.

Tidak ada prefetch/middleware yang secara independen merotasi token. Jangan
melakukan side-effect refresh dari shared data cache. Proteksi layout Member/
Coach sudah aktif pada Fase 7; backend tetap sumber otorisasi utama.

### Refresh bersamaan, request terlambat, dan logout

Target awal **satu proses Node FE**. Registry privat pada server, key
`bridgeSessionId + SHA256(refreshToken)`; userId saja tidak cukup karena satu
akun dapat memiliki beberapa perangkat/sesi. Semua action refresh wajib memakai
registry yang sama. Ini koordinasi sesi, bukan shared Bearer global.

| Keadaan | Tindakan |
| --- | --- |
| Tidak ada entry | Pasang promise secara atomik/sinkron sebelum await fetch; hanya pemenang mengirim POST /auth/refresh-session |
| Refresh sedang berjalan | Await promise pemenang, jangan memakai token lama ke BE |
| Sukses | Simpan hasil token/cookie/generation di entry memori privat 30 detik, lalu masing-masing action mengirim bridge baru yang sama |
| Request terlambat membawa cookie lama dalam 30 detik | Pakai hasil rotasi entry; jangan refresh ulang atau menghapus cookie yang telah diperbarui request lain |
| BE 401 | Cari hasil/generation lebih baru di registry dahulu; bila tidak ada, tombstone sesi, hapus bridge, login ulang |
| Network timeout / BE 5xx | Tampilkan kegagalan sementara tanpa otomatis menghapus sesi; jangan menganggap token pasti belum dipakai |
| Logout | Koordinasi dengan lock sesi yang sama, tandai tombstone, tunggu hasil refresh aktif lalu revoke token paling baru, hapus cookie; respons refresh yang tertinggal tidak boleh menerbitkan sesi lagi |

Registry membersihkan hasil setelah 30 detik dan membatasi jumlah entry; tidak
menahan plaintext refresh sampai tujuh hari. Tombstone logout bertahan minimal
30 detik untuk menolak operasi paralel dan FE client mengabaikan hasil refresh
yang datang setelah intent logout; cookie yang mungkin ditulis oleh respons
lama tidak membuat BE refresh yang sudah dicabut valid lagi. Cache entry tidak
boleh bocor lintas bridgeSessionId, worker, atau user. Generation meningkat hanya
sesudah rotasi sukses; hasil lama tidak mengganti generation lebih baru.

Deadline sesi asli tidak diperpanjang oleh koordinasi. Request stale setelah
jendela 30 detik dapat ditolak dan perlu login ulang; jangan menambah grace
replay pada BE. BE rotasi sekali pakai tetap tidak berubah. Setelah network
timeout, rotasi mungkin sudah commit; gunakan hasil registry bila ada, jika
tidak, upaya pemulihan berikut bisa memperoleh 401 dan memerlukan login ulang.
Jangan retry tanpa batas menggunakan refresh token lama. Crash FE setelah BE
commit tetapi sebelum hasil/cookie tersimpan juga dapat memerlukan login ulang.

Satu proses adalah batas rancangan, bukan aman untuk beberapa Node worker,
serverless instance atau multi-host. Sebelum mode tersebut, ganti registry
dengan koordinasi bersama per sesi yang mempunyai lock/lease, version/CAS dan
hasil rotasi terenkripsi; mutex module-local saja tidak cukup. Backend/worker
tidak diasumsikan di Vercel. Tidak menambah Redis untuk worker MVP.

### Cache, media, dan upload

- Hilangkan `use cache`/cacheLife dari data pribadi saat integrasi. Semua
  fetch profil, dashboard, history, evaluation, roster/review dan media no-store;
  jangan shared cache keyed hanya slug/role/sessionId. Request-local dedup boleh
  selama konteks user tetap melekat. Katalog publik murni dapat dicache terpisah,
  tetapi respons katalog yang mencakup statistik Member harus no-store.
- Page routes tetap composition; data di features/data dan mutations di actions,
  mengikuti CODE_STANDARD FE. Jangan import server-only api client ke komponen
  client. Pada logout/login user lain, clear/invalidate TanStack data dan state
  video pribadi agar data akun sebelumnya tidak muncul.
- Browser `<video>` tidak menerima header Bearer dari props src. Gunakan proxy
  streaming privat FE untuk `/api/media/sessions/{sessionId}/video`, bertindak
  sebagai unduhan/media (bukan jalur page data baru). Proxy membaca bridge,
  mengirim Bearer dan Range ke BE, meneruskan status 200/206/416 dan header
  Content-Type/Length/Range/Accept-Ranges, no-store; stream dengan backpressure
  tanpa buffering seluruh video. Jika perlu refresh, kembalikan 401 agar client
  menjalankan action pemulihan lalu retry playback; proxy tidak ikut merotasi
  token di luar koordinator. Member/Coach path dipilih dari sesi sah, BE tetap
  memeriksa ownership/binaan. Jangan taruh token pada URL.
- Upload file besar memakai adapter streaming FE `POST /api/uploads/sessions`
  pada task integrasi data latihan berikutnya (belum tersedia): baca bridge, forward multipart bytes dengan backpressure, Bearer
  dan Idempotency-Key ke POST /member/sessions, batasi 100 MiB file plus 1 MiB
  overhead multipart. Jangan base64 atau parse seluruh file ke RAM. Ini delta
  eksplisit pada allowlist `app/api` FE untuk transport berkas; page reads dan
  mutasi JSON biasa tetap features/data dan actions. Penyesuaian aturan/spec FE
  dilakukan bersama implementasi adapter pada pekerjaan FE, tidak pada Fase 1.
  Adapter tidak melakukan refresh sendiri; bila access kedaluwarsa, UI memanggil
  refresh action dulu lalu mengirim ulang File dan Idempotency-Key yang sama.
  FE body limit dan stream abort diuji terhadap runtime Next yang terpasang.
  Browser XHR dapat memberi progres transfer nyata; UI boleh indeterminate bila
  tidak tersedia, tanpa timer buatan. Progres upload berbeda dari inference,
  yang dipoll setiap 2 detik saat halaman aktif dan berhenti pada completed/
  failed/401/404 atau saat unmount.

## 4. Tahapan integrasi dan uji penerimaan

| Fase BE | Yang siap direncanakan untuk FE |
| --- | --- |
| 2 | Profil nullable, katalog bersumber/capability, config upload, password change; identity NPM/email tetap read-only |
| 3 | Upload persisten, job/status, sessionId, retryOf/idempotensi |
| 4 | Evaluasi null/status, pose keyframe, media privat/expired, acknowledge/delete |
| 5 | Histori pagination, dashboard/weekly, statistik tanpa dummy |
| 6 | CLI binaan, Coach overview/roster, draft/review/revisi/tugas, author historis |
| 7 | Bridge auth dan koneksi FE, linking/verifikasi email, SMTP test adapter, reset verified email, validasi browser/operasi |

Fase 7 recovery diurutkan: reauth request linking/verifikasi → token satu kali
dan uniqueness confirm → emailVerifiedAt → request/confirm reset. Akun NPM-only
tetap dapat latihan/login sebelum linking; UI recovery memberi instruksi umum
tanpa membocorkan apakah identifier ada. Email existing belum otomatis verified.
Tidak ada reset melalui email belum terverifikasi, password dikirim email,
atau perubahan identity melalui PATCH profil biasa.

Daftar penerimaan integrasi (historis Fase 1; subset yang diuji Fase 7 disebut
secara eksplisit dalam phase7-api.md):

1. Akun NPM/email, Member/Coach, tanpa Coach, belum latihan: null/empty valid,
   tidak menampilkan Coach/angka palsu; field identity tidak writable biasa.
2. Beberapa SSR reads dan dua tab refresh dengan cookie sama: satu request BE,
   hasil pemenang sama, cookie terlambat tidak logout atau rotasi ulang dalam
   30 detik. Access expired, BE 401, outage, timeout ambigu, logout vs refresh,
   expiry 24 jam/7 hari, dan crash gap memiliki perilaku terdokumentasi.
3. Dua user berurutan/paralel dan logout/login ulang: tidak ada data/token cache
   silang; server components tidak menerbitkan Set-Cookie saat render.
4. Upload nyata (termasuk ukuran batas), pending/failed/score null, reload detail
   sessionId, retry idempotent, acknowledge tidak menduplikasi hasil.
5. Playback/seek Range, permission salah, expiry saat tepat 24 jam, stream
   setelah transfer/delete, media legacy unavailable, tanpa token di URL.
6. Assign/transfer/revoke via CLI: Coach baru membaca histori, Coach lama tidak
   lagi bisa akses/revisi; author review lama tetap, draft tidak diwariskan.
7. Email link/reset: reauth salah, email dipakai akun lain, token expired/replay,
   nonverified, rate limit dan sesi lama dicabut; SMTP test adapter tidak
   mengirim email nyata tanpa konfigurasi terpisah.

Artefak Fase 1 tidak mengubah FE. Pada Fase 7, bridge/auth/security dan browser
checks terbatas sudah dilakukan; adapter upload/media streaming dan koneksi
seluruh data latihan masih delta pekerjaan integrasi. Bukti actual dan daftar
file ada di [phase7-api.md](phase7-api.md). RSC tidak menulis cookie; action inline
use server diberikan lewat props oleh Server Components sesuai batas repo FE.
