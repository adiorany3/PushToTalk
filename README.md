# Push To Talk Sederhana - Streamlit

Server:

```text
https://pushtotalk.streamlit.app/
```

## Fix Pada Versi Ini

Versi ini memperbaiki error:

```text
sqlite3.OperationalError
SELECT id, room, sender, note, mime_type, audio_blob, created_at
```

Penyebab umumnya adalah database lama masih memakai struktur tabel versi sebelumnya, yaitu audio disimpan sebagai file dengan kolom `filename`, sedangkan versi baru membaca kolom `audio_blob`.

Versi ini sudah menambahkan:

1. Migrasi otomatis dari schema lama ke schema baru.
2. Recovery otomatis kalau tabel `messages` rusak/tidak sesuai.
3. Retry sederhana jika SQLite sedang locked/busy.
4. SQLite timeout lebih panjang.
5. Audio disimpan sebagai BLOB di SQLite.
6. Auto-refresh pesan.
7. QR Code room.
8. Link room memakai:
   `https://pushtotalk.streamlit.app/?room=umum`

## File

- `app.py`
- `requirements.txt`
- `README.md`
- `.gitignore`

## Cara Deploy

Upload semua file ke GitHub, lalu redeploy Streamlit Cloud.

Main file:

```text
app.py
```

## Jika Error Masih Muncul

Di Streamlit Cloud:

1. Klik **Manage app**.
2. Klik **Reboot app**.
3. Jika masih error, redeploy dari commit terbaru.
4. Jika tetap error karena database lokal lama terkunci, hapus folder `ptt_data` dari repository jika pernah ikut ter-upload.

Folder `ptt_data` tidak perlu di-upload ke GitHub.

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
