"""
view_db.py — Smart GuardX PostgreSQL Database Viewer
Run: python view_db.py
"""

from backend import SessionLocal, User, Car, Session, Video

def show_database():
    db = SessionLocal()
    try:
        print("\n" + "=" * 60)
        print("  SMART GUARDX DATABASE VIEWER (PostgreSQL: ssr)")
        print("=" * 60)

        # 1. Users
        users = db.query(User).all()
        print(f"\n[1] USERS TABLE ({len(users)} record(s)):")
        print(f"{'ID':<6} {'Username':<20} {'Password Hash (preview)':<30}")
        print("-" * 60)
        for u in users:
            pw_preview = (u.password_hash[:25] + "...") if u.password_hash else "None"
            print(f"{u.id:<6} {u.username:<20} {pw_preview:<30}")

        # 2. Cars
        cars = db.query(Car).all()
        print(f"\n[2] CARS TABLE ({len(cars)} record(s)):")
        print(f"{'ID':<6} {'Car Name':<20} {'WiFi Password':<15} {'Owner ID':<10}")
        print("-" * 60)
        for c in cars:
            print(f"{c.id:<6} {c.car_name:<20} {c.wifi_password:<15} {c.owner_id:<10}")

        # 3. Sessions (Last 10)
        sessions = db.query(Session).order_by(Session.id.desc()).limit(10).all()
        total_sessions = db.query(Session).count()
        print(f"\n[3] SESSIONS TABLE (Latest 10 of {total_sessions} total records):")
        print(f"{'ID':<6} {'User ID':<10} {'Car ID':<8} {'Status':<12} {'Connected At':<26} {'Duration (s)':<12}")
        print("-" * 80)
        for s in sessions:
            conn_at = str(s.connected_at) if s.connected_at else "-"
            dur = str(s.duration_seconds) if s.duration_seconds is not None else "-"
            print(f"{s.id:<6} {s.user_id:<10} {s.car_id:<8} {s.status:<12} {conn_at:<26} {dur:<12}")

        # 4. Videos
        videos = db.query(Video).all()
        print(f"\n[4] VIDEOS TABLE ({len(videos)} record(s)):")
        if videos:
            print(f"{'ID':<6} {'Filename':<30} {'Recorded At':<26} {'Car ID':<8}")
            print("-" * 70)
            for v in videos:
                print(f"{v.id:<6} {v.filename:<30} {str(v.recorded_at):<26} {v.car_id:<8}")
        else:
            print("  (No video records saved in database yet)")

        print("\n" + "=" * 60 + "\n")
    finally:
        db.close()

if __name__ == "__main__":
    show_database()
