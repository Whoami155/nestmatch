import os
from datetime import datetime
import random

from flask import Flask, flash, jsonify, redirect, render_template, request, send_from_directory, url_for
from flask_login import LoginManager, UserMixin, current_user, login_required, login_user, logout_user
from flask_socketio import SocketIO, emit, join_room
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from sqlalchemy import inspect
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

load_dotenv()

db = SQLAlchemy()


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(30), nullable=False, default="user")


class Profile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False)
    age = db.Column(db.Integer)
    gender = db.Column(db.String(30), default="")
    occupation = db.Column(db.String(50), default="")
    budget_min = db.Column(db.Integer, default=0)
    budget_max = db.Column(db.Integer, default=0)
    preferred_location = db.Column(db.String(120), default="")
    sleep_schedule = db.Column(db.String(20), default="")
    cleanliness = db.Column(db.Integer, default=3)
    smoke_drink = db.Column(db.String(50), default="")
    bio = db.Column(db.Text, default="")
    profile_picture = db.Column(db.String(255), default="")
    room_images_csv = db.Column(db.Text, default="")


class Swipe(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    target_user_id = db.Column(db.Integer, nullable=False)
    action = db.Column(db.String(10), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


class Match(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_a = db.Column(db.Integer, nullable=False)
    user_b = db.Column(db.Integer, nullable=False)


class Property(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(200), nullable=False)
    price = db.Column(db.Integer, nullable=False)
    property_type = db.Column(db.String(20), default="Rent")
    location = db.Column(db.String(120), default="")
    description = db.Column(db.Text, default="")
    images_csv = db.Column(db.Text, default="")


class PropertySwipe(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    property_id = db.Column(db.Integer, nullable=False)
    action = db.Column(db.String(10), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender = db.Column(db.Integer, nullable=False)
    receiver = db.Column(db.Integer, nullable=False)
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


def parse_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def get_profile(uid):
    return Profile.query.filter_by(user_id=uid).first()


def allowed_image(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in {"png", "jpg", "jpeg", "webp"}


def pair(a, b):
    return (a, b) if a < b else (b, a)


def compatibility_score(me, other):
    if not me or not other:
        return 50, "Medium"
    score = 0
    weight = 0
    if me.preferred_location and other.preferred_location:
        weight += 30
        score += 30 if me.preferred_location.lower() == other.preferred_location.lower() else 15
    if me.sleep_schedule and other.sleep_schedule:
        weight += 20
        score += 20 if me.sleep_schedule == other.sleep_schedule else 7
    if me.smoke_drink and other.smoke_drink:
        weight += 20
        score += 20 if me.smoke_drink == other.smoke_drink else 5
    if me.cleanliness and other.cleanliness:
        weight += 15
        score += max(0, 15 - abs(me.cleanliness - other.cleanliness) * 4)
    if me.budget_min and me.budget_max and other.budget_min and other.budget_max:
        weight += 15
        me_mid = (me.budget_min + me.budget_max) / 2
        ot_mid = (other.budget_min + other.budget_max) / 2
        score += max(0, 15 - min(15, abs(me_mid - ot_mid) / 2500 * 15))
    pct = int((score / weight) * 100) if weight else 55
    label = "High" if pct >= 75 else "Medium" if pct >= 45 else "Low"
    return pct, label


def compatibility_breakdown(me, other):
    location_pct = 68
    if me and other and me.preferred_location and other.preferred_location:
        location_pct = 95 if me.preferred_location.lower() == other.preferred_location.lower() else 72

    lifestyle_pct = 70
    if me and other:
        sleep_match = 90 if (me.sleep_schedule and other.sleep_schedule and me.sleep_schedule == other.sleep_schedule) else 68
        habit_match = 90 if (me.smoke_drink and other.smoke_drink and me.smoke_drink == other.smoke_drink) else 66
        clean_delta = abs((me.cleanliness or 3) - (other.cleanliness or 3))
        clean_match = max(55, 95 - clean_delta * 12)
        lifestyle_pct = int((sleep_match + habit_match + clean_match) / 3)

    budget_pct = 74
    if me and other and me.budget_min and me.budget_max and other.budget_min and other.budget_max:
        me_mid = (me.budget_min + me.budget_max) / 2
        ot_mid = (other.budget_min + other.budget_max) / 2
        diff = abs(me_mid - ot_mid)
        budget_pct = int(max(55, 98 - min(45, diff / 20000 * 45)))

    return {
        "budget": budget_pct,
        "lifestyle": lifestyle_pct,
        "location": location_pct,
    }


def infer_interests(profile):
    if not profile:
        return ["Music", "Gym", "Coding"]
    source = f"{profile.occupation}|{profile.bio}|{profile.sleep_schedule}|{profile.preferred_location}".lower()
    pool = [
        ("music", "Music"),
        ("gym", "Gym"),
        ("code", "Coding"),
        ("design", "Design"),
        ("cook", "Cooking"),
        ("movie", "Movies"),
        ("read", "Reading"),
        ("run", "Running"),
        ("yoga", "Yoga"),
        ("game", "Gaming"),
    ]
    picked = [label for key, label in pool if key in source]
    if len(picked) >= 3:
        return picked[:4]
    fallback = ["Music", "Gym", "Coding", "Movies", "Travel"]
    for label in fallback:
        if label not in picked:
            picked.append(label)
        if len(picked) >= 4:
            break
    return picked


def estimate_distance_km(me, other):
    if not me or not other or not me.preferred_location or not other.preferred_location:
        return 4.5
    if me.preferred_location.lower() == other.preferred_location.lower():
        return 1.2
    seed = f"{me.preferred_location.lower()}::{other.preferred_location.lower()}"
    rng = random.Random(seed)
    return round(rng.uniform(2.1, 8.9), 1)


def seed_demo_data():
    if User.query.count() > 0:
        return
    demo_users = [
        {"name": "Aarav Mehta", "email": "aarav@nestmatch.demo", "password": "demo123", "age": 24, "gender": "Male", "occupation": "Working", "budget_min": 15000, "budget_max": 24000, "preferred_location": "Koramangala", "sleep_schedule": "Night", "cleanliness": 4, "smoke_drink": "No", "bio": "Product designer, into fitness and weekend cafes.", "profile_picture": "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=800"},
        {"name": "Sanya Rao", "email": "sanya@nestmatch.demo", "password": "demo123", "age": 23, "gender": "Female", "occupation": "Student", "budget_min": 12000, "budget_max": 18000, "preferred_location": "Indiranagar", "sleep_schedule": "Early", "cleanliness": 5, "smoke_drink": "No", "bio": "Architecture student, early riser, loves clean spaces.", "profile_picture": "https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=800"},
        {"name": "Kabir Shah", "email": "kabir@nestmatch.demo", "password": "demo123", "age": 27, "gender": "Male", "occupation": "Working", "budget_min": 18000, "budget_max": 32000, "preferred_location": "HSR Layout", "sleep_schedule": "Night", "cleanliness": 3, "smoke_drink": "Occasionally", "bio": "Software engineer, chill vibe, likes cooking at home.", "profile_picture": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=800"},
        {"name": "Mira Nair", "email": "mira@nestmatch.demo", "password": "demo123", "age": 25, "gender": "Female", "occupation": "Working", "budget_min": 20000, "budget_max": 35000, "preferred_location": "Koramangala", "sleep_schedule": "Early", "cleanliness": 4, "smoke_drink": "No", "bio": "Marketing lead with a love for minimalist interiors.", "profile_picture": "https://images.unsplash.com/photo-1487412720507-e7ab37603c6f?w=800"},
        {"name": "Dev Malhotra", "email": "dev@nestmatch.demo", "password": "demo123", "age": 26, "gender": "Male", "occupation": "Working", "budget_min": 18000, "budget_max": 28000, "preferred_location": "Bellandur", "sleep_schedule": "Night", "cleanliness": 3, "smoke_drink": "No", "bio": "Data analyst, gamer, and weekend cyclist.", "profile_picture": "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=800"},
        {"name": "Rhea Kapoor", "email": "rhea@nestmatch.demo", "password": "demo123", "age": 24, "gender": "Female", "occupation": "Working", "budget_min": 22000, "budget_max": 38000, "preferred_location": "Indiranagar", "sleep_schedule": "Early", "cleanliness": 5, "smoke_drink": "Occasionally", "bio": "UX researcher who loves tidy homes and plants.", "profile_picture": "https://images.unsplash.com/photo-1521572267360-ee0c2909d518?w=800"},
        {"name": "Nikhil Verma", "email": "nikhil@nestmatch.demo", "password": "demo123", "age": 28, "gender": "Male", "occupation": "Working", "budget_min": 25000, "budget_max": 42000, "preferred_location": "Whitefield", "sleep_schedule": "Night", "cleanliness": 4, "smoke_drink": "No", "bio": "Consultant, foodie, and movie marathon host.", "profile_picture": "https://images.unsplash.com/photo-1506794778202-cad84cf45f1d?w=800"},
        {"name": "Ira Sen", "email": "ira@nestmatch.demo", "password": "demo123", "age": 22, "gender": "Female", "occupation": "Student", "budget_min": 10000, "budget_max": 17000, "preferred_location": "BTM Layout", "sleep_schedule": "Early", "cleanliness": 4, "smoke_drink": "No", "bio": "Master's student, reader, and clean-space enthusiast.", "profile_picture": "https://images.unsplash.com/photo-1531123897727-8f129e1688ce?w=800"},
    ]
    created = []
    for d in demo_users:
        u = User(email=d["email"], password_hash=generate_password_hash(d["password"]), name=d["name"], role="user")
        db.session.add(u)
        db.session.flush()
        db.session.add(Profile(
            user_id=u.id,
            age=d["age"],
            gender=d["gender"],
            occupation=d["occupation"],
            budget_min=d["budget_min"],
            budget_max=d["budget_max"],
            preferred_location=d["preferred_location"],
            sleep_schedule=d["sleep_schedule"],
            cleanliness=d["cleanliness"],
            smoke_drink=d["smoke_drink"],
            bio=d["bio"],
            profile_picture=d["profile_picture"],
        ))
        created.append(u.id)
    db.session.flush()
    demo_props = [
        {"owner_id": created[0], "title": "Premium 2BHK in Koramangala 5th Block", "price": 42000, "property_type": "Rent", "location": "Koramangala, Bangalore", "description": "Modern 2BHK with balcony, covered parking, and 24/7 security.", "images_csv": "https://images.unsplash.com/photo-1493666438817-866a91353ca9?w=1200|https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?w=1200"},
        {"owner_id": created[1], "title": "Compact Studio Near Indiranagar Metro", "price": 22000, "property_type": "Rent", "location": "Indiranagar, Bangalore", "description": "Fully furnished studio with high-speed WiFi and modular kitchen.", "images_csv": "https://images.unsplash.com/photo-1484154218962-a197022b5858?w=1200|https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?w=1200"},
        {"owner_id": created[2], "title": "3BHK Family Apartment in HSR", "price": 7800000, "property_type": "Buy", "location": "HSR Layout, Bangalore", "description": "Spacious 3BHK with clubhouse, gym, and landscaped open area.", "images_csv": "https://images.unsplash.com/photo-1600607687939-ce8a6c25118c?w=1200|https://images.unsplash.com/photo-1600585154340-be6161a56a0c?w=1200"},
        {"owner_id": created[3], "title": "Co-living Ready 2BHK Near EGL", "price": 36000, "property_type": "Rent", "location": "Domlur, Bangalore", "description": "Great for flatmates, semi-furnished with split AC and wardrobes.", "images_csv": "https://images.unsplash.com/photo-1618221195710-dd6b41faaea6?w=1200|https://images.unsplash.com/photo-1616046229478-9901c5536a45?w=1200"},
        {"owner_id": created[0], "title": "Smart 1BHK in Whitefield", "price": 26000, "property_type": "Rent", "location": "Whitefield, Bangalore", "description": "Contemporary apartment in gated society with coworking lounge.", "images_csv": "https://images.unsplash.com/photo-1616486029423-aaa4789e8c9a?w=1200|https://images.unsplash.com/photo-1560185007-cde436f6a4d0?w=1200"},
        {"owner_id": created[4], "title": "Sunny 2BHK in Bellandur", "price": 34000, "property_type": "Rent", "location": "Bellandur, Bangalore", "description": "Sunlit bedrooms, modular kitchen, and quick ORR access.", "images_csv": "https://images.unsplash.com/photo-1617098900591-3f90928e8c54?w=1200|https://images.unsplash.com/photo-1615529162924-f86053884613?w=1200"},
        {"owner_id": created[5], "title": "Luxury 3BHK Penthouse", "price": 14500000, "property_type": "Buy", "location": "Indiranagar, Bangalore", "description": "Premium penthouse with private deck and skyline city views.", "images_csv": "https://images.unsplash.com/photo-1617104551722-3b2d513664b1?w=1200|https://images.unsplash.com/photo-1600566753051-f0b8f9dcf0f3?w=1200"},
        {"owner_id": created[6], "title": "Work-Friendly 1BHK Loft", "price": 28000, "property_type": "Rent", "location": "Whitefield, Bangalore", "description": "Loft style apartment with dedicated study nook and fast internet.", "images_csv": "https://images.unsplash.com/photo-1600210492493-0946911123ea?w=1200|https://images.unsplash.com/photo-1616594039964-3f7b5f5f1e2a?w=1200"},
        {"owner_id": created[7], "title": "Student Budget Double Sharing Flat", "price": 16000, "property_type": "Rent", "location": "BTM Layout, Bangalore", "description": "Affordable and safe shared flat near colleges and cafes.", "images_csv": "https://images.unsplash.com/photo-1600607687644-c7171b42498f?w=1200|https://images.unsplash.com/photo-1600210491369-e753d80a41f3?w=1200"},
        {"owner_id": created[2], "title": "Gated Community Villa", "price": 21500000, "property_type": "Buy", "location": "Sarjapur Road, Bangalore", "description": "Independent villa with private garden and 2-car parking.", "images_csv": "https://images.unsplash.com/photo-1568605114967-8130f3a36994?w=1200|https://images.unsplash.com/photo-1572120360610-d971b9d7767c?w=1200"},
    ]
    for p in demo_props:
        db.session.add(Property(**p))
    db.session.commit()


def ensure_minimum_demo_cards():
    min_users = 12
    min_properties = 12

    if User.query.count() < min_users:
        extra_users = [
            {"name": "Arjun Bhat", "email": "arjun@nestmatch.demo", "password": "demo123", "age": 25, "gender": "Male", "occupation": "Working", "budget_min": 16000, "budget_max": 25000, "preferred_location": "Marathahalli", "sleep_schedule": "Night", "cleanliness": 4, "smoke_drink": "No", "bio": "Frontend dev, gym in the evenings, likes organized spaces.", "profile_picture": "https://images.unsplash.com/photo-1504593811423-6dd665756598?w=800"},
            {"name": "Neha Iyer", "email": "neha@nestmatch.demo", "password": "demo123", "age": 24, "gender": "Female", "occupation": "Working", "budget_min": 17000, "budget_max": 26000, "preferred_location": "Jayanagar", "sleep_schedule": "Early", "cleanliness": 5, "smoke_drink": "No", "bio": "Consultant, loves music and a clean minimalist home.", "profile_picture": "https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=800"},
            {"name": "Tanishq Suri", "email": "tanishq@nestmatch.demo", "password": "demo123", "age": 26, "gender": "Male", "occupation": "Working", "budget_min": 20000, "budget_max": 30000, "preferred_location": "Koramangala", "sleep_schedule": "Night", "cleanliness": 3, "smoke_drink": "Occasionally", "bio": "Sales lead, social, cooks on weekends.", "profile_picture": "https://images.unsplash.com/photo-1542178243-bc20204b769f?w=800"},
            {"name": "Pooja Menon", "email": "pooja@nestmatch.demo", "password": "demo123", "age": 23, "gender": "Female", "occupation": "Student", "budget_min": 12000, "budget_max": 20000, "preferred_location": "HSR Layout", "sleep_schedule": "Early", "cleanliness": 4, "smoke_drink": "No", "bio": "MBA student, calm lifestyle, prefers peaceful shared spaces.", "profile_picture": "https://images.unsplash.com/photo-1488426862026-3ee34a7d66df?w=800"},
            {"name": "Rohan Das", "email": "rohan@nestmatch.demo", "password": "demo123", "age": 27, "gender": "Male", "occupation": "Working", "budget_min": 22000, "budget_max": 34000, "preferred_location": "Indiranagar", "sleep_schedule": "Night", "cleanliness": 4, "smoke_drink": "No", "bio": "Backend engineer, into football and board games.", "profile_picture": "https://images.unsplash.com/photo-1521119989659-a83eee488004?w=800"},
        ]
        for d in extra_users:
            if User.query.filter_by(email=d["email"]).first():
                continue
            u = User(email=d["email"], password_hash=generate_password_hash(d["password"]), name=d["name"], role="user")
            db.session.add(u)
            db.session.flush()
            db.session.add(Profile(
                user_id=u.id,
                age=d["age"],
                gender=d["gender"],
                occupation=d["occupation"],
                budget_min=d["budget_min"],
                budget_max=d["budget_max"],
                preferred_location=d["preferred_location"],
                sleep_schedule=d["sleep_schedule"],
                cleanliness=d["cleanliness"],
                smoke_drink=d["smoke_drink"],
                bio=d["bio"],
                profile_picture=d["profile_picture"],
            ))
        db.session.commit()

    if Property.query.count() < min_properties:
        owner_ids = [u.id for u in User.query.order_by(User.id.asc()).all()]
        if owner_ids:
            extra_props = [
                {"title": "Cozy 1RK near Jayanagar 4th Block", "price": 18000, "property_type": "Rent", "location": "Jayanagar, Bangalore", "description": "Compact and bright unit, ideal for students or solo professionals.", "images_csv": "https://images.unsplash.com/photo-1493809842364-78817add7ffb?w=1200|https://images.unsplash.com/photo-1507089947368-19c1da9775ae?w=1200"},
                {"title": "Modern 2BHK close to ORR", "price": 39000, "property_type": "Rent", "location": "Marathahalli, Bangalore", "description": "Semi furnished with modular kitchen and covered parking.", "images_csv": "https://images.unsplash.com/photo-1600585154084-4e5fe7c39198?w=1200|https://images.unsplash.com/photo-1616486338812-3dadae4b4ace?w=1200"},
                {"title": "Premium Studio with Balcony", "price": 24000, "property_type": "Rent", "location": "HSR Layout, Bangalore", "description": "Well ventilated studio in a gated lane near cafes.", "images_csv": "https://images.unsplash.com/photo-1560448204-e02f11c3d0e2?w=1200|https://images.unsplash.com/photo-1560185009-5bf9f2849488?w=1200"},
                {"title": "Spacious 3BHK in Whitefield", "price": 56000, "property_type": "Rent", "location": "Whitefield, Bangalore", "description": "Family-friendly apartment with clubhouse amenities.", "images_csv": "https://images.unsplash.com/photo-1597047084897-51e81819a499?w=1200|https://images.unsplash.com/photo-1613977257363-707ba9348227?w=1200"},
                {"title": "Budget Friendly 2 Sharing Setup", "price": 15000, "property_type": "Rent", "location": "BTM Layout, Bangalore", "description": "Affordable double sharing setup with furnished essentials.", "images_csv": "https://images.unsplash.com/photo-1616593969747-4797dc75033e?w=1200|https://images.unsplash.com/photo-1616628182508-6f8827c7d8f4?w=1200"},
            ]
            for idx, p in enumerate(extra_props):
                if Property.query.filter_by(title=p["title"]).first():
                    continue
                db.session.add(Property(
                    owner_id=owner_ids[idx % len(owner_ids)],
                    title=p["title"],
                    price=p["price"],
                    property_type=p["property_type"],
                    location=p["location"],
                    description=p["description"],
                    images_csv=p["images_csv"],
                ))
            db.session.commit()


def backfill_property_media():
    fallback_images = [
        "https://images.unsplash.com/photo-1493666438817-866a91353ca9?w=1200",
        "https://images.unsplash.com/photo-1484154218962-a197022b5858?w=1200",
        "https://images.unsplash.com/photo-1600607687939-ce8a6c25118c?w=1200",
        "https://images.unsplash.com/photo-1618221195710-dd6b41faaea6?w=1200",
        "https://images.unsplash.com/photo-1616486029423-aaa4789e8c9a?w=1200",
    ]
    updated = False
    props = Property.query.order_by(Property.id.asc()).all()
    for idx, prop in enumerate(props):
        if not prop.images_csv.strip():
            prop.images_csv = fallback_images[idx % len(fallback_images)]
            updated = True
    if updated:
        db.session.commit()


def backfill_profile_media():
    fallback_avatars = [
        "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=800",
        "https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=800",
        "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=800",
        "https://images.unsplash.com/photo-1487412720507-e7ab37603c6f?w=800",
        "https://images.unsplash.com/photo-1542204625-de293a50e77b?w=800",
    ]
    updated = False
    profiles = Profile.query.order_by(Profile.id.asc()).all()
    for idx, prof in enumerate(profiles):
        if not (prof.profile_picture or "").strip():
            prof.profile_picture = fallback_avatars[idx % len(fallback_avatars)]
            updated = True
    if updated:
        db.session.commit()


def ensure_profile_room_images_column():
    inspector = inspect(db.engine)
    cols = {col["name"] for col in inspector.get_columns("profile")}
    if "room_images_csv" in cols:
        return
    if db.engine.dialect.name == "mysql":
        db.session.execute(db.text("ALTER TABLE profile ADD COLUMN room_images_csv TEXT"))
    else:
        db.session.execute(db.text("ALTER TABLE profile ADD COLUMN room_images_csv TEXT DEFAULT ''"))
    db.session.commit()


def ensure_user_role_column():
    inspector = inspect(db.engine)
    cols = {col["name"] for col in inspector.get_columns("user")}
    if "role" in cols:
        return
    if db.engine.dialect.name == "mysql":
        db.session.execute(db.text("ALTER TABLE user ADD COLUMN role VARCHAR(30) NOT NULL DEFAULT 'user'"))
    else:
        db.session.execute(db.text("ALTER TABLE user ADD COLUMN role TEXT DEFAULT 'user'"))
    db.session.commit()


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev_secret_change_me")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
        "DATABASE_URL",
        "mysql+pymysql://root:Drip123%40@localhost:3306/edustark?charset=utf8mb4",
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "uploads")
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")
    login_manager = LoginManager(app)
    login_manager.login_view = "login"

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    with app.app_context():
        db.create_all()
        ensure_user_role_column()
        ensure_profile_room_images_column()
        seed_demo_data()
        ensure_minimum_demo_cards()
        backfill_property_media()
        backfill_profile_media()

    def matched(a, b):
        x, y = pair(a, b)
        return Match.query.filter_by(user_a=x, user_b=y).first() is not None

    @app.route("/")
    def index():
        return redirect(url_for("dashboard") if current_user.is_authenticated else url_for("login"))

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            name = request.form.get("name", "").strip()
            if not email or not password or not name:
                flash("Name, email, and password are required.", "error")
                return render_template("register.html")
            if User.query.filter_by(email=email).first():
                flash("Email is already registered.", "error")
                return render_template("register.html")
            user = User(email=email, password_hash=generate_password_hash(password), name=name, role="user")
            db.session.add(user)
            db.session.flush()
            db.session.add(Profile(user_id=user.id))
            db.session.commit()
            login_user(user)
            return redirect(url_for("dashboard"))
        return render_template("register.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            user = User.query.filter_by(email=request.form.get("email", "").strip().lower()).first()
            if not user or not check_password_hash(user.password_hash, request.form.get("password", "")):
                flash("Invalid credentials.", "error")
                return render_template("login.html")
            login_user(user)
            return redirect(url_for("dashboard"))
        return render_template("login.html")

    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        return redirect(url_for("login"))

    @app.route("/dashboard")
    @login_required
    def dashboard():
        uid = current_user.id
        matches_count = Match.query.filter((Match.user_a == uid) | (Match.user_b == uid)).count()
        liked_properties_count = PropertySwipe.query.filter_by(user_id=uid, action="like").count()
        messages_count = Message.query.filter((Message.sender == uid) | (Message.receiver == uid)).count()
        return render_template("dashboard.html", matches_count=matches_count, liked_properties_count=liked_properties_count, messages_count=messages_count, profile=get_profile(uid) or {})

    @app.route("/admin/reseed-cards", methods=["POST"])
    @login_required
    def reseed_cards():
        ensure_minimum_demo_cards()
        backfill_property_media()
        backfill_profile_media()
        flash("Demo cards reseeded successfully.", "success")
        return redirect(url_for("dashboard"))

    @app.route("/discover")
    @login_required
    def discover():
        return render_template("discover.html")

    @app.route("/profile", methods=["GET", "POST"])
    @login_required
    def profile():
        p = get_profile(current_user.id) or Profile(user_id=current_user.id)
        if request.method == "POST":
            current_user.name = request.form.get("name", current_user.name).strip()
            p.age = parse_int(request.form.get("age"))
            p.gender = request.form.get("gender", "").strip()
            p.occupation = request.form.get("occupation", "").strip()
            p.budget_min = parse_int(request.form.get("budget_min"))
            p.budget_max = parse_int(request.form.get("budget_max"))
            p.preferred_location = request.form.get("preferred_location", "").strip()
            p.sleep_schedule = request.form.get("sleep_schedule", "").strip()
            p.cleanliness = parse_int(request.form.get("cleanliness"), 3)
            p.smoke_drink = request.form.get("smoke_drink", "").strip()
            p.bio = request.form.get("bio", "").strip()
            file = request.files.get("profile_picture")
            if file and file.filename and allowed_image(file.filename):
                filename = f"{current_user.id}_{secure_filename(file.filename)}"
                file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
                p.profile_picture = f"/uploads/{filename}"
            existing_room_images = [x for x in (p.room_images_csv or "").split("|") if x]
            for file in request.files.getlist("room_images"):
                if file and file.filename and allowed_image(file.filename):
                    filename = f"room_{current_user.id}_{int(datetime.utcnow().timestamp())}_{secure_filename(file.filename)}"
                    file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
                    existing_room_images.append(f"/uploads/{filename}")
            p.room_images_csv = "|".join(existing_room_images[:12])
            db.session.add(p)
            db.session.commit()
            flash("Profile updated successfully.", "success")
            return redirect(url_for("profile"))
        profile_room_images = [x for x in (p.room_images_csv or "").split("|") if x]
        return render_template("profile.html", profile=p, user=current_user, room_images=profile_room_images)

    @app.route("/uploads/<path:filename>")
    def upload_file(filename):
        return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

    @app.route("/properties")
    @login_required
    def properties():
        return render_template("properties.html")

    @app.route("/properties/new", methods=["GET", "POST"])
    @login_required
    def property_new():
        if request.method == "POST":
            image_urls = []
            for file in request.files.getlist("images"):
                if file and file.filename and allowed_image(file.filename):
                    filename = f"prop_{current_user.id}_{int(datetime.utcnow().timestamp())}_{secure_filename(file.filename)}"
                    file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
                    image_urls.append(f"/uploads/{filename}")
            prop = Property(
                owner_id=current_user.id,
                title=request.form.get("title", "").strip(),
                price=parse_int(request.form.get("price")),
                property_type=request.form.get("property_type", "Rent"),
                location=request.form.get("location", "").strip(),
                description=request.form.get("description", "").strip(),
                images_csv="|".join(image_urls),
            )
            db.session.add(prop)
            db.session.commit()
            flash("Property listed successfully.", "success")
            return redirect(url_for("properties"))
        return render_template("property_new.html")

    @app.route("/property/<int:property_id>")
    @login_required
    def property_detail(property_id):
        p = db.session.get(Property, property_id)
        if not p:
            return "Property not found", 404
        owner = db.session.get(User, p.owner_id)
        owner_profile = get_profile(p.owner_id)
        images = [x for x in p.images_csv.split("|") if x]
        return render_template(
            "property_detail.html",
            prop={
                "title": p.title,
                "price": p.price,
                "property_type": p.property_type,
                "location": p.location,
                "description": p.description,
                "images": images,
                "cover_image": images[0] if images else "",
                "room_images": images[1:] if len(images) > 1 else images,
                "owner_name": owner.name if owner else "Owner",
                "owner_email": owner.email if owner else "",
                "owner_picture": owner_profile.profile_picture if owner_profile else "",
                "owner_occupation": owner_profile.occupation if owner_profile else "",
                "owner_location": owner_profile.preferred_location if owner_profile else "",
            },
        )

    @app.route("/roommate/<int:user_id>")
    @login_required
    def roommate_profile(user_id):
        if user_id == current_user.id:
            return redirect(url_for("profile"))
        user = db.session.get(User, user_id)
        if not user:
            return "Roommate not found", 404
        prof = get_profile(user_id)
        me = get_profile(current_user.id)
        score, label = compatibility_score(me, prof)
        room_images = [x for x in ((prof.room_images_csv if prof else "") or "").split("|") if x]
        if not room_images:
            owned_props = Property.query.filter_by(owner_id=user_id).order_by(Property.id.desc()).limit(4).all()
            for prop in owned_props:
                imgs = [x for x in (prop.images_csv or "").split("|") if x]
                room_images.extend(imgs[:2])
        room_images = room_images[:6]
        return render_template(
            "roommate_profile.html",
            roommate={
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "age": prof.age if prof else None,
                "occupation": prof.occupation if prof else "",
                "preferred_location": prof.preferred_location if prof else "",
                "sleep_schedule": prof.sleep_schedule if prof else "",
                "cleanliness": prof.cleanliness if prof else 3,
                "smoke_drink": prof.smoke_drink if prof else "",
                "bio": prof.bio if prof else "",
                "profile_picture": prof.profile_picture if prof else "",
                "compatibility_score": score,
                "compatibility_label": label,
                "can_message": matched(current_user.id, user.id),
                "room_images": room_images,
            },
        )

    @app.route("/matches")
    @login_required
    def matches():
        uid = current_user.id
        rows = Match.query.filter((Match.user_a == uid) | (Match.user_b == uid)).all()
        out = []
        for m in rows:
            oid = m.user_b if m.user_a == uid else m.user_a
            u = db.session.get(User, oid)
            if u:
                out.append({"id": str(u.id), "name": u.name})
        return render_template("matches.html", matches=out)

    @app.route("/chat/<int:user_id>")
    @login_required
    def chat(user_id):
        if not matched(current_user.id, user_id):
            return "Only matched users can chat.", 403
        msgs = Message.query.filter(((Message.sender == current_user.id) & (Message.receiver == user_id)) | ((Message.sender == user_id) & (Message.receiver == current_user.id))).order_by(Message.timestamp.asc()).all()
        return render_template("chat.html", other_user=db.session.get(User, user_id), messages=msgs, other_id=str(user_id))

    @app.route("/api/swipe/roommate", methods=["POST"])
    @login_required
    def swipe_roommate():
        data = request.get_json(silent=True) or {}
        tid = parse_int(data.get("target_user_id"), -1)
        action = data.get("action")
        if tid <= 0 or tid == current_user.id or action not in {"like", "dislike", "superlike"}:
            return jsonify({"error": "Invalid request"}), 400
        s = Swipe.query.filter_by(user_id=current_user.id, target_user_id=tid).first() or Swipe(user_id=current_user.id, target_user_id=tid)
        s.action = action
        s.timestamp = datetime.utcnow()
        db.session.add(s)
        match_created = False
        reverse = Swipe.query.filter_by(user_id=tid, target_user_id=current_user.id).order_by(Swipe.timestamp.desc()).first()
        if action in {"like", "superlike"} and reverse and reverse.action in {"like", "superlike"}:
            a, b = pair(current_user.id, tid)
            if not Match.query.filter_by(user_a=a, user_b=b).first():
                db.session.add(Match(user_a=a, user_b=b))
                match_created = True
        db.session.commit()
        return jsonify({"ok": True, "match_created": match_created})

    @app.route("/api/swipe/property", methods=["POST"])
    @login_required
    def swipe_property():
        data = request.get_json(silent=True) or {}
        pid = parse_int(data.get("property_id"), -1)
        action = data.get("action")
        if pid <= 0 or action not in {"like", "dislike", "superlike"}:
            return jsonify({"error": "Invalid request"}), 400
        s = PropertySwipe.query.filter_by(user_id=current_user.id, property_id=pid).first() or PropertySwipe(user_id=current_user.id, property_id=pid)
        s.action = action
        s.timestamp = datetime.utcnow()
        db.session.add(s)
        db.session.commit()
        return jsonify({"ok": True})

    @app.route("/api/swipe/undo", methods=["POST"])
    @login_required
    def undo_swipe():
        data = request.get_json(silent=True) or {}
        kind = str(data.get("kind", "")).strip().lower()
        if kind == "roommate":
            row = Swipe.query.filter_by(user_id=current_user.id).order_by(Swipe.timestamp.desc()).first()
            if not row:
                return jsonify({"ok": False, "message": "Nothing to undo"}), 404
            db.session.delete(row)
            db.session.commit()
            return jsonify({"ok": True, "item_id": str(row.target_user_id)})
        if kind == "property":
            row = PropertySwipe.query.filter_by(user_id=current_user.id).order_by(PropertySwipe.timestamp.desc()).first()
            if not row:
                return jsonify({"ok": False, "message": "Nothing to undo"}), 404
            db.session.delete(row)
            db.session.commit()
            return jsonify({"ok": True, "item_id": str(row.property_id)})
        return jsonify({"ok": False, "message": "Invalid kind"}), 400

    @app.route("/api/discover/roommates")
    @login_required
    def discover_roommates():
        swiped = {x.target_user_id for x in Swipe.query.filter_by(user_id=current_user.id).all()}
        out = []
        for u in User.query.filter(User.id != current_user.id).all():
            if u.id in swiped:
                continue
            p = get_profile(u.id)
            me = get_profile(current_user.id)
            score, label = compatibility_score(me, p)
            breakdown = compatibility_breakdown(me, p)
            smart_tag = "🔥 Highly compatible for work-life balance" if score >= 82 else ("🎯 Perfect budget match" if breakdown["budget"] >= 88 else "✨ Promising compatibility blend")
            out.append({
                "id": str(u.id),
                "name": u.name,
                "email": u.email,
                "occupation": (p.occupation if p else ""),
                "preferred_location": (p.preferred_location if p else ""),
                "bio": (p.bio if p else ""),
                "sleep_schedule": (p.sleep_schedule if p else ""),
                "cleanliness": (p.cleanliness if p else 3),
                "smoke_drink": (p.smoke_drink if p else ""),
                "profile_picture": (p.profile_picture if p else ""),
                "can_message": matched(current_user.id, u.id),
                "compatibility_score": score,
                "compatibility_label": label,
                "budget_min": (p.budget_min if p else 0),
                "budget_max": (p.budget_max if p else 0),
                "interests": infer_interests(p),
                "distance_km": estimate_distance_km(me, p),
                "compatibility_breakdown": breakdown,
                "smart_tag": smart_tag,
            })
        return jsonify(out[:50])

    @app.route("/api/discover/properties")
    @login_required
    def discover_properties():
        swiped = {x.property_id for x in PropertySwipe.query.filter_by(user_id=current_user.id).all()}
        out = []
        for p in Property.query.order_by(Property.id.desc()).all():
            if p.id in swiped:
                continue
            owner = db.session.get(User, p.owner_id)
            owner_profile = get_profile(p.owner_id)
            out.append({
                "id": str(p.id),
                "title": p.title,
                "price": p.price,
                "property_type": p.property_type,
                "location": p.location,
                "description": p.description,
                "images": [x for x in p.images_csv.split("|") if x],
                "owner_name": owner.name if owner else "Owner",
                "owner_email": owner.email if owner else "",
                "owner_profile_picture": owner_profile.profile_picture if owner_profile else "",
                "owner_occupation": owner_profile.occupation if owner_profile else "",
                "owner_preferred_location": owner_profile.preferred_location if owner_profile else "",
            })
        return jsonify(out[:50])

    @socketio.on("join")
    def handle_join(data):
        if not current_user.is_authenticated:
            return
        oid = parse_int((data or {}).get("other_id"), -1)
        if oid <= 0:
            return
        room = "_".join(sorted([str(current_user.id), str(oid)]))
        join_room(room)
        emit("joined", {"room": room})

    @socketio.on("send_message")
    def handle_send_message(data):
        if not current_user.is_authenticated:
            return
        oid = parse_int((data or {}).get("receiver"), -1)
        txt = str((data or {}).get("message", "")).strip()
        if oid <= 0 or not txt or not matched(current_user.id, oid):
            return
        m = Message(sender=current_user.id, receiver=oid, message=txt)
        db.session.add(m)
        db.session.commit()
        room = "_".join(sorted([str(current_user.id), str(oid)]))
        emit("new_message", {"sender": str(current_user.id), "receiver": str(oid), "message": txt, "timestamp": m.timestamp.isoformat()}, room=room)

    return app, socketio


app, socketio = create_app()

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
