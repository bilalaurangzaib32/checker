# 🛡️ VPS Sentinel — 24/7 Autonomous VPS, Docker & Website Monitor

VPS Sentinel ek complete 24/7 automated monitoring solution hai jo aapke VPS, websites, custom Docker containers, aur security events ko continuously monitor karta hai. 

- 🕒 **24/7 Continuous Background Monitoring**: Har 60 seconds baad VPS aur websites ki health check karta hai.
- 🚨 **Instant Unusual Activity Alerts**: Agar CPU/RAM spike kare (>85%), Docker container band ho jaye, ya website down ho jaye toh **foran Discord pe alert send karta hai**.
- 📊 **6-Hour Scheduled Reports**: Har 6 ghante baad Discord pe comprehensive status & analytics report embed bhejta hai.
- 🐳 **Docker Auto-Discovery**: VPS pe chalne wale tamam custom Docker containers ki CPU %, RAM usage, aur status track karta hai.
- 🌐 **Websites & Endpoints Monitor**: Monitored websites ki HTTP status, latency (ms), aur uptime monitor karta hai.
- 🛡️ **SSH Security Audit**: VPS ke auth logs scan karke failed SSH logins aur brute-force attacker IPs detect karta hai.
- 💻 **Modern Web GUI Dashboard**: Beautiful Dark Mode Web GUI (responsive on Mobile & PC) jahan se aap live analytics dekh sakte hain aur settings control kar sakte hain.

---

## 🚀 Quick Start (Local Machine)

### Windows 1-Click Launch
Aap project folder me simply **`start.bat`** file par double-click karein:
1. Yeh automatic virtual environment banayega.
2. Dependencies install karega.
3. Web dashboard browser me **`http://localhost:8000`** par open kar dega.

### Manual Terminal Run:
```bash
# Virtual environment create & activate
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate # Linux/Mac

# Install dependencies
python -m pip install -r requirements.txt

# Run Monitor & Dashboard
python app.py
```
Open **http://localhost:8000** in your browser.

---

## 🌐 100% Free 24/7 Cloud Deployment Guide

Aapko is program ko apne personal computer par har waqt khula rakhne ki zaroorat nahi hai. Aap isko kisi bhi **Free Cloud Provider** par 24/7 host kar sakte hain:

### Option 1: Render.com (Recommended - 100% Free)
1. Apne code ko GitHub repository me push karein.
2. [Render.com](https://render.com) par free account banayein.
3. Click **"New +"** -> **"Web Service"** -> Apni GitHub repo select karein.
4. Render automatically `render.yaml` detect kar lega:
   - **Environment:** `Python`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python app.py`
5. Click **Deploy Web Service**! Aapko ek free HTTPS URL mil jayega (e.g. `https://vps-sentinel.onrender.com`).

---

### Option 2: VPS k Apne Andar (Docker Compose)
Agar aap chahein toh is monitor ko VPS k apne andar bhi aik isolated container me chala sakte hain:
```bash
docker compose up -d --build
```
Yeh background me 24/7 chalta rahega aur server reboot hone par bhi automatic restart ho jayega (`restart: always`).

---

### Option 3: Koyeb ya Railway Free Tier
- **Koyeb:** Connect GitHub repo -> Auto detects `Dockerfile` -> Deploy Free Nano instance.
- **Railway:** Connect GitHub -> Deploy using `Procfile`.

---

## ⚙️ Configuration Setup (GUI k Zariye)

Dashboard open karke top-right par **"Settings"** button dabayein:

1. **VPS Credentials:**
   - **VPS IP:** Aapke VPS ka public IP (e.g., `159.65.x.x`)
   - **SSH Port:** `22` (default)
   - **Username:** `root` (ya aapka sudo user)
   - **Password / Private Key:** SSH login password ya private key text paste karein.
   - Click **"Test VPS SSH Connection"** to verify!

2. **Discord Webhook:**
   - Discord channel settings -> Integrations -> **Webhooks** -> "New Webhook" -> Copy URL.
   - Sentinel settings me paste karein.
   - Click **"Test Discord Notification"** — Discord me test message aayega!
   - Report interval: `6` hours (customizable).

3. **Thresholds (Alert Triggers):**
   - CPU Alert Limit: `85%`
   - RAM Alert Limit: `90%`
   - Disk Alert Limit: `90%`

4. **Websites Monitor:**
   - Dashboard me **"+ Add URL"** dabayein aur apni custom website / API link enter karein.

---

## 📁 Project Structure

```text
vps_sentinel/
├── app.py                # Web GUI server & REST API (FastAPI-compatible native server)
├── monitor_engine.py     # 24/7 Autonomous background worker & scheduler
├── ssh_client.py         # Paramiko SSH connector (CPU, RAM, Disk, Docker, Logs)
├── website_monitor.py    # HTTP latency & uptime checker
├── discord_notifier.py   # Discord Webhook embeds (Instant alerts & 6hr reports)
├── config.py             # Persistent settings manager (config.json)
├── templates/
│   └── index.html        # Modern Dark-mode dashboard (Tailwind CSS, Chart.js)
├── Dockerfile            # Container build for cloud deployment
├── docker-compose.yml    # Docker compose configuration
├── render.yaml           # 1-Click Render.com free deployment blueprint
├── Procfile              # Cloud process declaration
├── requirements.txt      # Dependencies
├── start.bat             # 1-Click Windows launcher
└── README.md             # Documentation
```
