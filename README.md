# Push To Talk Sederhana - 5 Room + Admin Password

Server:

```text
https://pushtotalk.streamlit.app/
```

## Fitur Versi Ini

1. Admin room memakai password.
2. Room dibatasi menjadi 5 room tetap.
3. Tombol hapus pesan hanya muncul jika admin sudah login.
4. Tombol hapus semua pesan room hanya muncul jika admin sudah login.
5. Ada opsi admin untuk hapus semua pesan di semua room.
6. Audio disimpan sebagai BLOB di SQLite.
7. Ada auto-refresh.
8. Ada QR Code room.
9. Ada migrasi otomatis dari schema database lama.

## Daftar 5 Room

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

## Cara Deploy

Upload semua file ke GitHub, lalu deploy/redeploy ke Streamlit Community Cloud.

Main file:

```text
app.py
```

## Contoh Link Room

```text
https://pushtotalk.streamlit.app/?room=umum
```

```text
https://pushtotalk.streamlit.app/?room=lapangan
```

```text
https://pushtotalk.streamlit.app/?room=tim-1
```

```text
https://pushtotalk.streamlit.app/?room=tim-2
```

```text
https://pushtotalk.streamlit.app/?room=darurat
```

## Catatan Penting

Folder `ptt_data/` tidak perlu di-upload ke GitHub.

Pada Streamlit Community Cloud, penyimpanan lokal bisa reset saat aplikasi restart/redeploy. Untuk penggunaan permanen, gunakan database/storage eksternal seperti Supabase, PostgreSQL, Firebase, atau object storage.
