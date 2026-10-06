# Smart GuardX Surveillance Rover (SSR-Rover)

A web-controlled surveillance rover with real-time video telemetry, remote motor navigation, camera servo pan control, and PostgreSQL session tracking.

---

## 🚀 Features

- **Live Video Streaming**: Real-time video streaming with support for ESP32-CAM, local webcam, and simulated demo stream.
- **Remote Motor Controls**:
  - Interactive on-screen direction controls.
  - Keyboard driving shortcuts: **WASD** and **Arrow keys** (with auto-stop on key release).
- **Camera Pan Control**: Interactive 0°–180° servo angle slider with live angle display.
- **3-Factor Authentication & Sessions**: Operator login with username, passcode, and car Wi-Fi passcode, with session history saved to PostgreSQL.
- **Event & Video Sync**: Review recorded `.webm` surveillance clips.
- **Theme Customizer**: Dark, Light, and High-Contrast monochrome modes.

---

## 🛠️ Tech Stack

- **Backend**: Python 3.13, FastAPI, Uvicorn, OpenCV, SQLAlchemy, Psycopg2, Bcrypt
- **Database**: PostgreSQL (`ssr`)
- **Frontend**: Responsive HTML5, CSS3 (Vanilla), JavaScript (ES6)
- **Microcontroller**: ESP32-CAM (Arduino C++)

---

## ⚙️ Installation & Setup

### 1. Clone Repository & Setup Virtual Environment
```bash
git clone https://github.com/Htunht/SSR-Rover.git
cd SSR-Rover

python -m venv venv
# On Windows PowerShell:
.\venv\Scripts\Activate.ps1
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. PostgreSQL Database Setup
Make sure PostgreSQL is running locally on port 5432, and create the database:
```sql
CREATE DATABASE ssr;
```
*(Default connection: `postgresql+psycopg2://postgres:postgres@localhost:5432/ssr` or set `DATABASE_URL` environment variable).*

### 4. Seed the Database
Initialize tables and the default administrator account:
```bash
python database.py
```

### 5. Start the Server
```bash
python backend.py
```
Open **http://127.0.0.1:8000/** in your web browser.

---

## 🔑 Default Credentials

| Field | Default Value |
| :--- | :--- |
| **Username** | `admin` |
| **Passcode** | `SecurePass@123` |
| **Car Wi-Fi Password** | `123456` |

---

## 🎮 Driving Controls

| Action | Keys | Behavior |
| :--- | :--- | :--- |
| **Forward** | <kbd>W</kbd> or <kbd>▲</kbd> | Move forward |
| **Backward** | <kbd>S</kbd> or <kbd>▼</kbd> | Move backward |
| **Left** | <kbd>A</kbd> or <kbd>◀</kbd> | Turn left |
| **Right** | <kbd>D</kbd> or <kbd>▶</kbd> | Turn right |
| **Stop** | <kbd>Space</kbd> or **Release Key** | Immediate stop |

---

## 📊 Database Viewer

To quickly view stored users, rover profiles, and login sessions in the terminal:
```bash
python view_db.py
```
