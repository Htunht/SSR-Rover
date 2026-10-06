"""
db_seed.py — Smart GuardX Database Seeder
==========================================
Run this ONCE after setting up PostgreSQL to create your first admin user and car.

Usage:
    python db_seed.py

Edit the DEFAULT_* constants below to choose your login credentials.
"""

import sys
import bcrypt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# ── Import models from main.py ──────────────────────────────────────────────
sys.path.insert(0, ".")
from backend import Base, User, Car, DATABASE_URL, datetime

# ── Your desired credentials ─────────────────────────────────────────────────
# Change these before running!
DEFAULT_USERNAME     = "admin"
DEFAULT_PASSWORD     = "SecurePass@123"   # Will be hashed with bcrypt
DEFAULT_CAR_NAME     = "Rover 1"
DEFAULT_CAR_WIFI_PW  = "123456"  # This is the 3rd login factor

# ─────────────────────────────────────────────────────────────────────────────

def seed(username: str = DEFAULT_USERNAME, password: str = DEFAULT_PASSWORD):
    print(f"[Seed] Connecting to: {DATABASE_URL}")
    engine = create_engine(DATABASE_URL)

    # Create tables if they don't exist yet
    Base.metadata.create_all(bind=engine)
    print("[Seed] Tables verified/created.")

    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        hashed = bcrypt.hashpw(
            password.encode("utf-8"),
            bcrypt.gensalt(rounds=12),
        ).decode("utf-8")

        # Check if user already exists
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            existing.password_hash = hashed
            # Ensure linked car has default wifi password
            if existing.cars:
                for c in existing.cars:
                    c.wifi_password = DEFAULT_CAR_WIFI_PW
            else:
                car = Car(
                    car_name=DEFAULT_CAR_NAME,
                    wifi_password=DEFAULT_CAR_WIFI_PW,
                    owner_id=existing.id,
                )
                db.add(car)
            db.commit()
            print()
            print("=" * 50)
            print(f"  [Seed] UPDATED — User '{username}' credentials refreshed!")
            print("=" * 50)
            print(f"  Username      : {username}")
            print(f"  Password      : {password}")
            print(f"  Car Name      : {DEFAULT_CAR_NAME}")
            print(f"  Car Wi-Fi PW  : {DEFAULT_CAR_WIFI_PW} (DEFAULT)")
            print("=" * 50)
            return

        # Create the user
        user = User(username=username, password_hash=hashed)
        db.add(user)
        db.flush()

        # Create the car linked to that user with default WiFi password
        car = Car(
            car_name=DEFAULT_CAR_NAME,
            wifi_password=DEFAULT_CAR_WIFI_PW,
            owner_id=user.id,
        )
        db.add(car)
        db.commit()

        print()
        print("=" * 50)
        print("  [Seed] SUCCESS — User and Car created!")
        print("=" * 50)
        print(f"  Username      : {username}")
        print(f"  Password      : {password}")
        print(f"  Car Name      : {DEFAULT_CAR_NAME}")
        print(f"  Car Wi-Fi PW  : {DEFAULT_CAR_WIFI_PW} (DEFAULT)")
        print("=" * 50)
        print()
        print("  Use these credentials to log into the dashboard.")
        print()

    except Exception as e:
        db.rollback()
        print(f"[Seed] ERROR: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Seed or update SSR-Rover operator credentials"
    )
    parser.add_argument(
        "--username", "-u", default=DEFAULT_USERNAME, help="Operator username"
    )
    parser.add_argument(
        "--password", "-p", default=DEFAULT_PASSWORD, help="Operator password"
    )
    args = parser.parse_args()

    seed(username=args.username, password=args.password)