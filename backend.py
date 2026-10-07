from contextlib import asynccontextmanager
from datetime import datetime, timezone
import math
import os
from pathlib import Path
import time

import bcrypt
import cv2
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import numpy as np
from pydantic import BaseModel, Field
import requests
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

# ================= Security Setup =================


def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode("utf-8"), hashed_password.encode("utf-8")
    )


def get_utc_now():
    return datetime.now(timezone.utc)


# ================= Database Setup =================
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/ssr"
)
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ================= ORM Models =================


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(256), nullable=False)

    cars = relationship(
        "Car", back_populates="owner", cascade="all, delete-orphan"
    )


class Car(Base):
    __tablename__ = "cars"

    id = Column(Integer, primary_key=True, index=True)
    car_name = Column(String(128), nullable=False)
    wifi_password = Column(String(256), nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    owner = relationship("User", back_populates="cars")
    videos = relationship(
        "Video", back_populates="car", cascade="all, delete-orphan"
    )


class Video(Base):
    __tablename__ = "videos"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(256), nullable=False)
    filepath = Column(Text, nullable=False)
    recorded_at = Column(
        DateTime(timezone=True), default=get_utc_now, nullable=False
    )
    car_id = Column(Integer, ForeignKey("cars.id"), nullable=False)

    car = relationship("Car", back_populates="videos")


class Session(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    car_id = Column(
        Integer, ForeignKey("cars.id", ondelete="CASCADE"), nullable=False
    )

    connected_at = Column(
        DateTime(timezone=True), default=get_utc_now, nullable=False
    )

    disconnected_at = Column(DateTime(timezone=True), nullable=True)

    duration_seconds = Column(Integer, nullable=True)

    status = Column(String(32), default="active", nullable=False)

    user = relationship("User")
    car = relationship("Car")


# ================= Lifespan Setup =================
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        Base.metadata.create_all(bind=engine)
        print("[DB] Tables created / verified OK.")
    except Exception as e:
        print(f"[DB] WARNING: Could not connect to database: {e}")
    yield


# ================= App Setup =================
app = FastAPI(title="Smart GuardX API Server", lifespan=lifespan)

RECORDS_DIR = Path(__file__).parent / "records"
RECORDS_DIR.mkdir(exist_ok=True)

app.mount("/records", StaticFiles(directory=str(RECORDS_DIR)), name="records")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def serve_ui():
    ui_path = Path(__file__).parent / "frontend.html"
    if not ui_path.exists():
        ui_path = Path(__file__).parent / "Combineindex.html"
    return FileResponse(ui_path)


# ================= Pydantic Schemas =================


class RegisterPayload(BaseModel):
    username: str
    password: str
    car_wifi: int = Field(..., ge=1000, le=1010)


class LoginPayload(BaseModel):
    username: str
    password: str
    car_wifi: int = Field(..., ge=1000, le=1010)


class LogoutPayload(BaseModel):
    session_id: int


class ConnectionConfig(BaseModel):
    mode: str  # "demo", "webcam", "esp32"
    ip: str = ""


class MovePayload(BaseModel):
    direction: str


class PanRequest(BaseModel):
    angle: int = Field(..., ge=0, le=180)
    session_id: int | str | None = None


PanPayload = PanRequest


class ActionPayload(BaseModel):
    action: str


class RotationPayload(BaseModel):
    rotation: int  # 0, 90, 180, 270


class SystemState:

    def __init__(self):
        self.mode = "esp32"
        self.esp32_ip = "192.168.4.1"
        self.connected = True
        self.servo_angle = 90
        self.current_direction = "stop"
        self.rotation = 90  # Default to 90 degrees (Vertical Portrait View)
        self.logs = []


state = SystemState()


def add_log(message: str):
    timestamp = time.strftime("%H:%M:%S")
    state.logs.append({"time": timestamp, "message": message})
    if len(state.logs) > 50:
        state.logs.pop(0)


add_log("System initialized. Mode: WEBCAM.")


def encode_jpeg(frame):
    ok, jpeg = cv2.imencode(".jpg", frame)
    if not ok:
        raise RuntimeError("Failed to encode frame as JPEG")
    return jpeg.tobytes()


def test_esp32_control(ip: str) -> bool:
    res = requests.get(f"http://{ip}/", timeout=1.5)
    res.raise_for_status()
    return True


def get_demo_frame(t_sec):
    if state.rotation in [90, 270]:
        w, h = 480, 640
    else:
        w, h = 640, 480
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    frame[:] = [30, 20, 15]

    grid_size = 40
    for x in range(0, w, grid_size):
        cv2.line(frame, (x, 0), (x, h), (50, 35, 25), 1)
    for y in range(0, h, grid_size):
        cv2.line(frame, (0, y), (w, y), (50, 35, 25), 1)

    center = (w // 2, h // 2)
    for r in [60, 120, 180]:
        cv2.circle(frame, center, r, (70, 50, 35), 1)

    sweep_angle = t_sec * 2.0
    sx = int(center[0] + 180 * math.cos(sweep_angle))
    sy = int(center[1] + 180 * math.sin(sweep_angle))
    cv2.line(frame, center, (sx, sy), (150, 100, 30), 1)

    t1_x = int(center[0] + 100 * math.cos(t_sec * 0.4))
    t1_y = int(center[1] + 80 * math.sin(t_sec * 0.3))
    cv2.rectangle(
        frame, (t1_x - 25, t1_y - 35), (t1_x + 25, t1_y + 35), (0, 0, 220), 2
    )
    cv2.putText(
        frame,
        "TARGET: INTRUDER (94%)",
        (max(10, t1_x - 30), t1_y - 42),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.4,
        (0, 0, 220),
        1,
        cv2.LINE_AA,
    )

    cv2.putText(
        frame,
        "SYS_STATUS: ACTIVE",
        (20, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.48,
        (0, 255, 255),
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        frame,
        f"SERVO PAN: {state.servo_angle} DEG",
        (20, 50),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.48,
        (0, 255, 255),
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        frame,
        f"DRIVE: {state.current_direction.upper()}",
        (20, 70),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.48,
        (0, 255, 255),
        1,
        cv2.LINE_AA,
    )

    right_x = max(10, w - 190)
    cv2.putText(
        frame,
        "MODE: SIMULATION",
        (right_x, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.42,
        (0, 180, 255),
        1,
        cv2.LINE_AA,
    )
    cur_time = time.strftime("%H:%M:%S")
    cv2.putText(
        frame,
        cur_time,
        (right_x, 50),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.42,
        (0, 180, 255),
        1,
        cv2.LINE_AA,
    )

    center_x = max(10, (w // 2) - 100)
    cv2.putText(
        frame,
        "SMART GUARDX SECURE VIEW",
        (center_x, h - 20),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        (0, 200, 255),
        1,
        cv2.LINE_AA,
    )

    if int(t_sec * 2) % 2 == 0:
        cv2.circle(frame, (w - 25, 25), 6, (0, 0, 255), -1)
        cv2.putText(
            frame,
            "REC",
            (w - 60, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            (0, 0, 255),
            1,
            cv2.LINE_AA,
        )

    return encode_jpeg(frame)


def process_webcam_frame(frame, t_sec):
    if state.rotation == 90:
        frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    elif state.rotation == 180:
        frame = cv2.rotate(frame, cv2.ROTATE_180)
    elif state.rotation == 270:
        frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

    if state.rotation in [90, 270]:
        frame = cv2.resize(frame, (480, 640))
    else:
        frame = cv2.resize(frame, (640, 480))

    h, w = frame.shape[:2]

    cv2.putText(
        frame,
        "SYS_STATUS: ACTIVE",
        (20, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (0, 255, 0),
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        frame,
        f"SERVO PAN: {state.servo_angle} DEG",
        (20, 50),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (0, 255, 0),
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        frame,
        f"DRIVE DIRECTION: {state.current_direction.upper()}",
        (20, 70),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (0, 255, 0),
        1,
        cv2.LINE_AA,
    )

    right_x = max(10, w - 210)
    cv2.putText(
        frame,
        "MODE: LOCAL WEBCAM",
        (right_x, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        (0, 255, 0),
        1,
        cv2.LINE_AA,
    )
    cur_time = time.strftime("%H:%M:%S")
    cv2.putText(
        frame,
        cur_time,
        (right_x, 50),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        (0, 255, 0),
        1,
        cv2.LINE_AA,
    )

    center_x = max(10, (w // 2) - 100)
    cv2.putText(
        frame,
        "SMART GUARDX WEBCAM VIEW",
        (center_x, h - 20),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        (0, 255, 0),
        1,
        cv2.LINE_AA,
    )

    if int(t_sec * 2) % 2 == 0:
        cv2.circle(frame, (w - 25, 25), 6, (0, 0, 255), -1)
        cv2.putText(
            frame,
            "REC",
            (w - 60, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            (0, 0, 255),
            1,
            cv2.LINE_AA,
        )

    return encode_jpeg(frame)


ESP32_CAPTURE_URL = "http://192.168.4.1/capture"
is_recording = False
video_writer = None


def start_recording_stream(output_filename):
    global is_recording, video_writer

    os.makedirs("recordings", exist_ok=True)
    filepath = os.path.join("recordings", output_filename)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    video_writer = cv2.VideoWriter(filepath, fourcc, 10.0, (320, 240))

    is_recording = True
    print(f"Started Recording: {filepath}")

    while is_recording:
        try:
            img_resp = requests.get(ESP32_CAPTURE_URL, timeout=2)
            img_arr = np.array(bytearray(img_resp.content), dtype=np.uint8)
            frame = cv2.imdecode(img_arr, -1)

            if frame is not None:
                video_writer.write(frame)
        except Exception as e:
            print(f"Frame Capture Error: {e}")
            break

    if video_writer:
        video_writer.release()
    print("Recording Stopped.")


def stop_recording_stream():
    global is_recording
    is_recording = False


def process_esp32_frame(jpg_bytes, t_sec):
    try:
        frame = cv2.imdecode(
            np.frombuffer(jpg_bytes, np.uint8), cv2.IMREAD_COLOR
        )
        if frame is None:
            return jpg_bytes

        if state.rotation == 90:
            frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        elif state.rotation == 180:
            frame = cv2.rotate(frame, cv2.ROTATE_180)
        elif state.rotation == 270:
            frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

        if state.rotation in [90, 270]:
            frame = cv2.resize(frame, (480, 640))
        else:
            frame = cv2.resize(frame, (640, 480))

        h, w = frame.shape[:2]

        cv2.putText(
            frame,
            "SYS_STATUS: CONNECTED",
            (20, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 255, 255),
            1,
            cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            f"SERVO PAN: {state.servo_angle} DEG",
            (20, 50),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 255, 255),
            1,
            cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            f"DRIVE: {state.current_direction.upper()}",
            (20, 70),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 255, 255),
            1,
            cv2.LINE_AA,
        )

        right_x = max(10, w - 200)
        cv2.putText(
            frame,
            f"ESP32: {state.esp32_ip}",
            (right_x, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (0, 255, 255),
            1,
            cv2.LINE_AA,
        )
        cur_time = time.strftime("%H:%M:%S")
        cv2.putText(
            frame,
            cur_time,
            (right_x, 50),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (0, 255, 255),
            1,
            cv2.LINE_AA,
        )

        center_x = max(10, (w // 2) - 100)
        cv2.putText(
            frame,
            "SMART GUARDX REMOTE VIEW",
            (center_x, h - 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (0, 255, 255),
            1,
            cv2.LINE_AA,
        )

        if int(t_sec * 2) % 2 == 0:
            cv2.circle(frame, (w - 25, 25), 6, (0, 0, 255), -1)
            cv2.putText(
                frame,
                "REC",
                (w - 60, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                (0, 0, 255),
                1,
                cv2.LINE_AA,
            )

        return encode_jpeg(frame)
    except Exception as e:
        add_log(f"Warning: ESP32 frame overlay failed: {str(e)}")
        return jpg_bytes


def event_generator():
    cap = None
    last_mode = None

    try:
        while True:
            current_mode = state.mode
            t_sec = time.time()

            if current_mode != last_mode:
                add_log(f"Stream source changed to {current_mode.upper()}")
                if cap is not None:
                    cap.release()
                    cap = None
                last_mode = current_mode

            try:
                if current_mode == "demo":
                    jpg = get_demo_frame(t_sec)
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
                    )
                    time.sleep(0.05)

                elif current_mode == "webcam":
                    if cap is None:
                        cap = cv2.VideoCapture(0)
                        if not cap.isOpened():
                            add_log(
                                "Error: Webcam could not be initialized."
                                " Defaulting to Demo."
                            )
                            state.mode = "demo"
                            cap = None
                            continue

                    ret, frame = cap.read()
                    if not ret:
                        time.sleep(0.01)
                        continue
                    jpg = process_webcam_frame(frame, t_sec)
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
                    )
                    time.sleep(0.033)

                elif current_mode == "esp32":
                    if not state.esp32_ip:
                        add_log("Error: ESP32 IP is empty. Defaulting to Demo.")
                        state.mode = "demo"
                        continue

                    capture_url = f"http://{state.esp32_ip}/capture"
                    try:
                        res = requests.get(capture_url, timeout=2.0)
                        if res.status_code == 200:
                            state.connected = True
                            processed_jpg = process_esp32_frame(
                                res.content, t_sec
                            )
                            yield (
                                b"--frame\r\n"
                                b"Content-Type: image/jpeg\r\n\r\n"
                                + processed_jpg
                                + b"\r\n"
                            )
                        else:
                            state.connected = False
                            jpg = get_demo_frame(t_sec)
                            yield (
                                b"--frame\r\n"
                                b"Content-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
                            )
                    except Exception as e:
                        state.connected = False
                        jpg = get_demo_frame(t_sec)
                        yield (
                            b"--frame\r\n"
                            b"Content-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
                        )
                    time.sleep(0.05)

            except Exception as e:
                add_log(f"Stream generation exception: {str(e)}")
                time.sleep(1.0)
    finally:
        if cap is not None:
            cap.release()


@app.get("/api/status")
def get_status():
    return {
        "mode": state.mode,
        "esp32_ip": state.esp32_ip,
        "connected": state.connected,
        "servo_angle": state.servo_angle,
        "current_direction": state.current_direction,
        "logs": state.logs,
    }


@app.post("/api/logout")
def logout_json(payload: LogoutPayload):
    db = SessionLocal()
    try:
        session = db.query(Session).filter(Session.id == payload.session_id).first()
        if session:
            now = get_utc_now()
            session.disconnected_at = now
            session.status = "terminated"
            if session.connected_at:
                conn_time = session.connected_at
                if conn_time.tzinfo is None:
                    conn_time = conn_time.replace(tzinfo=timezone.utc)
                session.duration_seconds = int((now - conn_time).total_seconds())
            db.commit()
            add_log(f"Session {payload.session_id} terminated and car lock released.")
        return {"success": True, "message": "Logged out successfully."}
    finally:
        db.close()


@app.post("/api/logout/{session_id}")
def logout(session_id: int):
    return logout_json(LogoutPayload(session_id=session_id))


@app.post("/api/connect")
def connect(config: ConnectionConfig):
    mode = config.mode.lower()
    if mode not in ["demo", "webcam", "esp32"]:
        raise HTTPException(status_code=400, detail="Invalid mode selected")

    state.mode = mode
    if mode == "esp32":
        if not config.ip:
            raise HTTPException(
                status_code=400, detail="IP address required for ESP32 mode"
            )
        state.esp32_ip = config.ip
        add_log(f"Attempting control connection to ESP32: {config.ip}")
        try:
            test_esp32_control(config.ip)
            state.connected = True
            add_log("ESP32 control API reachable.")
        except Exception as e:
            add_log(
                f"Warning: ESP32 control API unreachable: {str(e)}. Stream"
                " will still be attempted."
            )
            state.connected = False
    elif mode == "webcam":
        state.esp32_ip = ""
        state.connected = False
        add_log("Switched to Local Webcam mode.")
    else:
        state.esp32_ip = ""
        state.connected = False
        add_log("Switched to Simulation/Demo mode.")

    return get_status()


@app.post("/api/control/move")
def move(payload: MovePayload):
    direction = payload.direction.lower()
    if direction not in ["forward", "backward", "left", "right", "stop"]:
        raise HTTPException(status_code=400, detail="Invalid direction")

    state.current_direction = direction
    add_log(f"Motor direction set to: {direction.upper()}")

    if state.esp32_ip:
        command_map = {
            "forward": "F",
            "backward": "B",
            "left": "L",
            "right": "R",
            "stop": "S",
        }
        command = command_map[direction]
        esp32_url = f"http://{state.esp32_ip}/action?go={command}"

        try:
            res = requests.get(esp32_url, timeout=1.5)
            res.raise_for_status()
            return {"status": "relayed", "esp32_response": res.text}
        except Exception as e:
            add_log(f"Failed to send movement to ESP32: {str(e)}")
            return {"status": "failed", "error": str(e)}

    return {"status": "simulated", "direction": direction}


@app.post("/api/control")
def control(payload: ActionPayload):
    action = payload.action.lower()
    if action == "reverse":
        action = "backward"
    return move(MovePayload(direction=action))


@app.post("/api/control/pan")
async def control_pan(data: PanRequest):
    angle = data.angle
    state.servo_angle = angle
    add_log(f"Camera Pan set to: {angle} degrees")
    print(f"[SERVO] Camera Panned to: {angle}°")

    if state.esp32_ip:
        esp32_url = f"http://{state.esp32_ip}/pan?angle={angle}"
        try:
            res = requests.get(esp32_url, timeout=1.5)
            res.raise_for_status()
            return {
                "status": "success",
                "angle": angle,
                "relayed": True,
                "esp32_response": res.text,
            }
        except Exception as e:
            add_log(f"Failed to send pan command to ESP32: {str(e)}")
            return {"status": "success", "angle": angle, "warning": str(e)}

    return {"status": "success", "angle": angle}


@app.get("/api/stream")
def stream():
    return StreamingResponse(
        event_generator(), media_type="multipart/x-mixed-replace; boundary=frame"
    )


@app.post("/api/register")
def register(payload: RegisterPayload):
    db = SessionLocal()
    try:
        username = payload.username.strip()
        if not username:
            raise HTTPException(status_code=400, detail="Username cannot be empty")
        if not payload.password:
            raise HTTPException(status_code=400, detail="Password cannot be empty")

        # 1. Username duplicate check
        existing_user = (
            db.query(User).filter(User.username == username).first()
        )
        if existing_user:
            raise HTTPException(
                status_code=400,
                detail="Username already exists. Please choose another.",
            )

        # 2. Car Wi-Fi Key duplicate check (1000 - 1010)
        existing_car = (
            db.query(Car)
            .filter(Car.wifi_password == str(payload.car_wifi))
            .first()
        )
        if existing_car:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Car Wi-Fi Key '{payload.car_wifi}' is already registered."
                    " Please use a different key."
                ),
            )

        # 3. Create new user
        new_user = User(
            username=username,
            password_hash=get_password_hash(payload.password),
        )
        db.add(new_user)
        db.flush()  # get new_user.id

        # 4. Link car with chosen Wi-Fi key (1000 - 1010)
        new_car = Car(
            car_name=f"{username}'s Rover",
            wifi_password=str(payload.car_wifi),
            owner_id=new_user.id,
        )
        db.add(new_car)
        db.commit()

        add_log(
            f"New user registered: '{new_user.username}' with car WiFi"
            f" key ({payload.car_wifi})"
        )
        return {
            "success": True,
            "message": "Account and Rover registered successfully.",
            "username": new_user.username,
            "car_name": new_car.car_name,
            "car_wifi": payload.car_wifi,
        }
    finally:
        db.close()


@app.post("/api/login")
def login(payload: LoginPayload):
    db = SessionLocal()

    try:
        user = db.query(User).filter(User.username == payload.username).first()

        if not user:
            raise HTTPException(
                status_code=401, detail="ACCESS DENIED: User not found."
            )

        if not verify_password(payload.password, user.password_hash):
            raise HTTPException(
                status_code=401, detail="ACCESS DENIED: Incorrect password."
            )

        wifi_key_str = str(payload.car_wifi)
        # Check car belonging to user first, then fallback to any matching car
        car = (
            db.query(Car)
            .filter(Car.owner_id == user.id, Car.wifi_password == wifi_key_str)
            .first()
        )
        if not car:
            car = db.query(Car).filter(Car.wifi_password == wifi_key_str).first()

        if not car:
            raise HTTPException(
                status_code=401,
                detail="ACCESS DENIED: Incorrect Car Wi-Fi Password.",
            )

        # Single Driver Lock: Check if another user is actively using the rover
        active_session = (
            db.query(Session)
            .filter(Session.status == "active")
            .first()
        )

        if active_session:
            if active_session.user_id == user.id:
                # Same user re-connecting: release previous session to avoid locking themselves out
                active_session.status = "terminated"
                db.commit()
            else:
                raise HTTPException(
                    status_code=403,
                    detail="ROVER IS BUSY: သင့်သူငယ်ချင်း (သို့) အခြားသူတစ်ဦး လက်ရှိအသုံးပြုနေပါသည်။ ပြီးသည်အထိ ခဏစောင့်ပါ။",
                )

        session = Session(user_id=user.id, car_id=car.id)

        db.add(session)
        db.commit()
        db.refresh(session)

        add_log(
            f"Successful login: user='{user.username}' connected to"
            f" car='{car.car_name}' session_id={session.id}"
        )

        return {
            "success": True,
            "username": user.username,
            "car_connected": car.car_name,
            "session_id": session.id,
        }

    finally:
        db.close()


@app.get("/api/videos")
def list_videos():
    try:
        files = sorted(
            [f for f in os.listdir(RECORDS_DIR) if f.lower().endswith(".webm")],
            reverse=True,
        )
        add_log(f"Video list requested. Found {len(files)} recording(s).")
        return {"videos": files}
    except Exception as e:
        add_log(f"Error listing videos: {str(e)}")

        raise HTTPException(
            status_code=500,
            detail=f"Could not read records directory: {str(e)}",
        )


@app.post("/api/records/upload")
async def upload_record(request: Request, session_id: int | None = None):
    try:
        content = await request.body()
        if not content:
            raise HTTPException(status_code=400, detail="Empty video data")

        filename = f"rover_record_{datetime.now().strftime('%Y%m%d_%H%M%S')}.webm"
        file_path = RECORDS_DIR / filename
        with open(file_path, "wb") as f:
            f.write(content)

        db = SessionLocal()
        try:
            car_id = 1
            if session_id:
                s = db.query(Session).filter(Session.id == session_id).first()
                if s:
                    car_id = s.car_id
            video = Video(filename=filename, filepath=str(file_path), car_id=car_id)
            db.add(video)
            db.commit()
        finally:
            db.close()

        add_log(f"New video recording saved: {filename} ({len(content)} bytes)")
        return {"success": True, "filename": filename, "url": f"/records/{filename}"}
    except Exception as e:
        add_log(f"Error saving video upload: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/camera/rotation")
def get_camera_rotation():
    return {"rotation": state.rotation}


@app.post("/api/camera/rotation")
def set_camera_rotation(payload: RotationPayload):
    if payload.rotation not in [0, 90, 180, 270]:
        raise HTTPException(
            status_code=400,
            detail="Invalid rotation angle. Must be 0, 90, 180, or 270.",
        )
    state.rotation = payload.rotation
    orientation = "Vertical" if state.rotation in [90, 270] else "Horizontal"
    add_log(f"Camera rotation set to {state.rotation}° ({orientation} view)")
    return {"success": True, "rotation": state.rotation, "orientation": orientation}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend:app", host="0.0.0.0", port=8000, reload=True)