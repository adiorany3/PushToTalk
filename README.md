# PTT Sederhana Streamlit

Aplikasi push-to-talk sederhana berbasis voice message.

Aplikasi ini tidak memakai WebRTC, STUN, TURN, atau Mumble.  
Pesan delay tidak masalah karena sistemnya berbasis rekam-kirim-putar.

## Isi File

- `app.py` — aplikasi utama Streamlit
- `requirements.txt` — dependency Python
- `README.md` — panduan singkat

## Cara Menjalankan Lokal

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Cara Menjalankan agar Bisa Diakses dari HP Satu Jaringan

```bash
streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

Lalu buka dari HP:

```text
http://IP-LAPTOP:8501
```

Contoh room/channel:

```text
http://IP-LAPTOP:8501?room=umum
```

## Catatan

- Mikrofon biasanya hanya bisa dipakai di `localhost` atau website HTTPS.
- Jika dibuka lewat IP lokal biasa, sebagian browser bisa memblokir akses mikrofon.
- Untuk deployment online, gunakan Streamlit Community Cloud atau server dengan HTTPS.
- Audio dan database tersimpan otomatis di folder `ptt_data`.
