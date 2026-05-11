# PTT Sederhana Streamlit

Server publik yang dipakai:

```text
https://pushtotalk.streamlit.app/
```

Aplikasi ini adalah push-to-talk sederhana berbasis voice message.

Tidak memakai WebRTC, STUN, TURN, atau Mumble.  
Sistemnya berbasis rekam, kirim, lalu putar.

## Isi File

- `app.py` — aplikasi utama Streamlit
- `requirements.txt` — dependency Python
- `README.md` — panduan singkat
- `.gitignore` — file/folder yang tidak perlu di-upload ke GitHub

## Fitur

- Rekam audio dari browser
- Kirim pesan suara ke room/channel
- Putar pesan suara terbaru
- Link room otomatis memakai server:
  `https://pushtotalk.streamlit.app/?room=umum`
- QR Code untuk akses cepat dari HP
- Room/channel sederhana via query parameter `?room=nama-room`

## Cara Deploy ke Streamlit Community Cloud

1. Upload semua file ke GitHub.
2. Buka Streamlit Community Cloud.
3. Pilih repository.
4. Set main file ke:

```text
app.py
```

5. Deploy.

## Contoh Link Room

Room umum:

```text
https://pushtotalk.streamlit.app/?room=umum
```

Room tim:

```text
https://pushtotalk.streamlit.app/?room=tim
```

Room lapangan:

```text
https://pushtotalk.streamlit.app/?room=lapangan
```

## Catatan Penting

- Karena server memakai HTTPS, akses mikrofon dari browser biasanya lebih aman dan lebih mudah diizinkan.
- Penyimpanan audio memakai folder lokal `ptt_data`.
- Di Streamlit Community Cloud, file lokal bisa hilang saat aplikasi restart/redeploy.
- Aplikasi ini cocok untuk demo, komunikasi sederhana, atau prototipe.
- Untuk produksi jangka panjang, sebaiknya gunakan database/storage eksternal.
