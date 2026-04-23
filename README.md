# NestMatch

NestMatch is a full-stack Flask web app for smart roommate matching and swipe-based property discovery.  
It combines Tinder-like swiping, compatibility scoring, match-gated chat, and rich listing/profile pages in one project.

## What This Project Does

- Roommate discovery with compatibility-based cards
- Property discovery with swipe actions
- Actions: `like`, `dislike`, `superlike`, and `undo`
- Mutual roommate likes create matches
- Real-time chat for matched users only (Socket.IO)
- Profile management with avatar + room images upload
- Property listing creation with multiple photos
- Dashboard controls, including one-click demo card reseed

## Tech Stack

- Backend: Flask
- Auth/session: Flask-Login
- Database: SQLAlchemy via Flask-SQLAlchemy
- Realtime: Flask-SocketIO
- DB driver: PyMySQL
- Frontend: Jinja templates + Vanilla JS + CSS
- Config: `.env` via `python-dotenv`

## Project Structure

```text
nestmatch/
  app.py
  requirements.txt
  .env.example
  static/
    css/style.css
    js/app.js
    js/chat.js
  templates/
    base.html
    login.html
    register.html
    dashboard.html
    discover.html
    profile.html
    properties.html
    property_new.html
    property_detail.html
    roommate_profile.html
    matches.html
    chat.html
```

## Core Flows

### 1) Authentication

- Register creates a `User` + blank `Profile`
- Login establishes session with Flask-Login
- Logout clears session

### 2) Roommate Discovery

- Frontend loads cards from `/api/discover/roommates`
- Card includes compatibility score + breakdown bars
- Swipe actions sent to `/api/swipe/roommate`
- Mutual likes/superlikes create entries in `Match`

### 3) Property Discovery

- Frontend loads cards from `/api/discover/properties`
- Swipe actions sent to `/api/swipe/property`
- Property list/detail pages show owner profile snippets

### 4) Undo

- Undo action calls `/api/swipe/undo`
- Removes latest swipe for current mode (`roommate` / `property`)

### 5) Chat

- Only matched users can open `/chat/<user_id>`
- Socket.IO handles room join and message broadcast

## Data Model (High Level)

- `User`: account identity (email, password hash, name, role)
- `Profile`: lifestyle, budget, location, bio, avatar, room images
- `Property`: listing data and images
- `Swipe`: roommate swipe history
- `PropertySwipe`: property swipe history
- `Match`: roommate match pair
- `Message`: chat messages

## Compatibility Logic

Compatibility score is computed from:

- preferred location similarity
- sleep schedule match
- smoking/drinking habit match
- cleanliness difference
- budget range proximity

Roommate cards also include a breakdown:

- Budget %
- Lifestyle %
- Location %

## UI/UX Highlights

- Light premium visual theme
- Rich swipe cards (lifestyle icons, interests, budget, distance)
- Floating circular action buttons with micro animations
- Super Like and Undo controls
- Stacked-card effect in discovery deck
- Smart compatibility tag text on cards

## Environment Configuration

Create a `.env` file in project root (or copy from `.env.example`):

```env
SECRET_KEY=dev_secret_change_me
DATABASE_URL=mysql+pymysql://root:Drip123%40@localhost:3306/edustark?charset=utf8mb4
```

Notes:

- `DATABASE_URL` takes precedence over fallback in code.
- Use URL-encoded special characters in password (e.g. `@` as `%40`).

## Installation & Run

1. Create virtual environment:

   ```bash
   python -m venv .venv
   ```

2. Activate environment:

   - Windows PowerShell:

     ```powershell
     .\.venv\Scripts\Activate.ps1
     ```

3. Install dependencies:

   ```bash
   python -m pip install -r requirements.txt
   ```

4. Make sure MySQL is running and `edustark` database exists.
5. Run app:

   ```bash
   python app.py
   ```

6. Open:

   [http://localhost:5000](http://localhost:5000)

## Demo Data and Reseeding

- App auto-seeds demo users/properties on startup.
- It also tops up to minimum card counts for discovery.
- Dashboard includes **Reseed Demo Cards** button:
  - Calls `/admin/reseed-cards`
  - Refills demo cards/media quickly

## Important Routes

Pages:

- `/login`, `/register`, `/logout`
- `/dashboard`
- `/discover`
- `/profile`
- `/properties`, `/properties/new`, `/property/<id>`
- `/roommate/<id>`
- `/matches`
- `/chat/<id>`

APIs:

- `/api/discover/roommates`
- `/api/discover/properties`
- `/api/swipe/roommate`
- `/api/swipe/property`
- `/api/swipe/undo`
- `/admin/reseed-cards` (POST)

## Troubleshooting

### MySQL syntax error around `PRAGMA`

Older code used SQLite-specific migration checks.  
Current code uses SQLAlchemy inspector and is MySQL-compatible.

### `Field 'role' doesn't have a default value`

Your DB has a required `role` column in `user`.  
Current code includes `role` in model/inserts and auto-handles missing column creation.

### Empty discover cards

- Use **Reseed Demo Cards** from dashboard.
- Ensure seeded users/properties exist in DB.

## Security Notes

- Do not commit `.env` to Git.
- Change `SECRET_KEY` in production.
- Replace demo credentials/data for real deployments.

## Future Improvements

- Proper migration tool (Alembic/Flask-Migrate)
- Role-based admin panel
- Real map integration in property cards
- Better recommendation engine (beyond rule-based score)
- Cloud storage for uploads
