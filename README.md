# Push To Talk Sederhana - Secret Room Admin CRUD

Server:

```text
https://pushtotalk.streamlit.app/
```

## Fitur Versi Ini

1. Tetap ada 5 room publik.
2. Admin dapat membuat secret room.
3. Admin dapat melihat **list semua secret room**.
4. Admin dapat **mengubah/modifikasi** secret room:
   - mengubah kode room;
   - mengubah nama tampilan;
   - memilih apakah pesan lama dipindahkan ke kode room baru.
5. Admin dapat **menghapus** secret room.
6. User biasa tidak melihat daftar secret room.
7. User bisa masuk secret room dengan mengetik kode/nama secret room.
8. Secret room juga bisa dibuka langsung melalui URL: `https://pushtotalk.streamlit.app/?room=nama-secret-room`
9. Room publik menyimpan **5 pesan terbaru per room**.
10. Secret room menyimpan **20 pesan terbaru per room**.
11. Pesan paling lama otomatis dihapus saat ada pesan baru.
12. Audio disimpan sebagai BLOB di SQLite.
13. Ada auto-refresh.
14. Ada QR Code room.
15. Ada migrasi otomatis dari schema database lama.
16. Jika nama pengguna dikosongkan, sistem otomatis membuat nama unik seperti `User-A7K9Q2`.

## Daftar 5 Room Publik

| Kode Room | Nama Room |
|---|---|
| `umum` | Room 1 - Umum |
| `lapangan` | Room 2 - Lapangan |
| `tim-1` | Room 3 - Tim 1 |
| `tim-2` | Room 4 - Tim 2 |
| `darurat` | Room 5 - Darurat |

## Password Admin Default

Password bawaan:

```text
admin12345
```

## Cara Mengganti Password Admin di Streamlit Cloud

Lebih aman mengganti password melalui Streamlit Secrets.

1. Buka aplikasi di Streamlit Cloud.
2. Klik **Manage app**.
3. Buka menu **Secrets**.
4. Isi:

```toml
ADMIN_PASSWORD = "password_baru_anda"
```

5. Save.
6. Reboot app.

Jika `ADMIN_PASSWORD` tidak diisi di Secrets, aplikasi akan memakai password default:

```text
admin12345
```

## Cara Admin Membuat Secret Room

1. Buka sidebar.
2. Buka menu **Admin room**.
3. Masukkan password admin.
4. Isi **Nama/kode secret room baru**.
5. Klik **Buat Secret Room**.
6. Bagikan kode room kepada user.

Contoh kode room:

```text
operasi-alpha
```

User yang tahu kode tersebut dapat masuk melalui:

- pilihan **Secret Room** di sidebar, lalu mengetik `operasi-alpha`; atau
- URL langsung:

```text
https://pushtotalk.streamlit.app/?room=operasi-alpha
```

## Cara Admin Modifikasi Secret Room

1. Login sebagai admin.
2. Buka **List Semua Secret Room**.
3. Pada secret room yang ingin diedit:
   - ubah kode room; atau
   - ubah nama tampilan.
4. Klik **Simpan Perubahan**.

Jika kode room diubah, centang **Pindahkan pesan lama ke kode room baru** agar pesan tetap ikut pindah.

## Retensi Pesan

Aplikasi menyimpan:

```text
Room publik  : 5 pesan terbaru per room
Secret room  : 20 pesan terbaru per room
```

Saat batas pesan terlampaui, pesan paling lama otomatis dihapus.

## Cara Deploy

Upload semua file ke GitHub, lalu deploy/redeploy ke Streamlit Community Cloud.

Main file:

```text
app.py
```

## Catatan Penting

Folder `ptt_data/` tidak perlu di-upload ke GitHub.

Pada Streamlit Community Cloud, penyimpanan lokal bisa reset saat aplikasi restart/redeploy. Untuk penggunaan permanen, gunakan database/storage eksternal seperti Supabase, PostgreSQL, Firebase, atau object storage.

## Nama Pengguna Otomatis

Jika kolom **Nama pengguna** dikosongkan, aplikasi otomatis membuat nama unik, misalnya:

```text
User-A7K9Q2
```

Nama otomatis disimpan pada sesi pengguna agar tidak berubah saat refresh. Sistem juga mengecek database agar nama otomatis tidak sama dengan nama otomatis lain dan tidak sama dengan nama yang sudah pernah muncul pada pesan.
