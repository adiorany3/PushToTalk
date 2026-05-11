# Push To Talk Sederhana - Streamlit

Server:

```text
https://pushtotalk.streamlit.app/
```

Aplikasi ini adalah PTT sederhana berbasis voice message.

## Yang Diperbaiki

Versi ini lebih stabil dibanding versi sebelumnya karena:

1. Audio disimpan langsung ke SQLite sebagai BLOB.
2. Tidak memakai folder audio terpisah, sehingga tidak ada masalah file audio hilang/tidak terbaca.
3. SQLite memakai WAL mode dan busy timeout agar lebih aman untuk beberapa pengguna sederhana.
4. Ada auto-refresh pesan.
5. Link room memakai server:
   `https://pushtotalk.streamlit.app/?room=umum`
6. Ada QR Code untuk akses dari HP.
7. Database dibatasi maksimal 200 pesan per room agar tidak cepat membesar.

## File

- `app.py`
- `requirements.txt`
- `README.md`
- `.gitignore`

## Cara Deploy

Upload semua file ke GitHub, lalu deploy ke Streamlit Community Cloud.

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

## Cara Pakai

1. Buka aplikasi.
2. Isi nama pengguna.
3. Pilih room/channel.
4. Rekam suara.
5. Klik Kirim Pesan Suara.
6. Pengguna lain pada room yang sama akan melihat pesan setelah refresh/auto-refresh.

## Catatan Penting

Aplikasi ini cocok untuk demo, prototipe, dan pemakaian ringan.

Pada Streamlit Community Cloud, penyimpanan lokal dapat hilang ketika aplikasi restart atau redeploy. Untuk penggunaan serius/jangka panjang, gunakan database eksternal seperti Supabase, Firebase, PostgreSQL, atau object storage.
