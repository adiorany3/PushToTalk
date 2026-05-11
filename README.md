# Push To Talk Sederhana - 5 Public Room + Secret Room Admin

Server:

```text
https://pushtotalk.streamlit.app/
```

## Fitur Versi Ini

1. Tetap ada 5 room publik.
2. Admin dapat membuat secret room.
3. Secret room tidak muncul untuk user biasa.
4. User dapat masuk secret room dengan mengetik nama/kode secret room.
5. Secret room juga bisa dibuka langsung melalui URL:
   `https://pushtotalk.streamlit.app/?room=nama-secret-room`
6. Tombol hapus pesan hanya muncul jika admin sudah login.
7. Admin dapat menghapus secret room.
8. Admin dapat menghapus pesan pada room aktif.
9. Audio disimpan sebagai BLOB di SQLite.
10. Ada auto-refresh.
11. Ada QR Code room.
12. Ada migrasi otomatis dari schema database lama.

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

Contoh:

```text
operasi-alpha
```

User yang tahu kode tersebut dapat masuk melalui:
- pilihan **Secret Room** di sidebar, lalu mengetik `operasi-alpha`; atau
- URL langsung:

```text
https://pushtotalk.streamlit.app/?room=operasi-alpha
```

## Cara Deploy

Upload semua file ke GitHub, lalu deploy/redeploy ke Streamlit Community Cloud.

Main file:

```text
app.py
```

## Catatan Penting

Folder `ptt_data/` tidak perlu di-upload ke GitHub.

Pada Streamlit Community Cloud, penyimpanan lokal bisa reset saat aplikasi restart/redeploy. Untuk penggunaan permanen, gunakan database/storage eksternal seperti Supabase, PostgreSQL, Firebase, atau object storage.
