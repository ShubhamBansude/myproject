# Project Working Guide

This document explains how the app works end‑to‑end, what each part does, and how data flows between frontend and backend.

## 1) Architecture Overview

- Frontend: React + Vite + Tailwind (v4). Location: `frontend/`
  - Screens: Welcome, Auth (Login/Signup), Dashboard (tabs: Earn Points, Rewards, Profile)
  - Communicates with backend via REST, stores token in `localStorage` as `authToken`.

- Backend: Flask (Python) + SQLite. Location: `backend/`
  - Auth endpoints (`/api/signup`, `/api/login`)
  - Detection endpoint (`/api/detect`) using YOLO weights at `backend/weights/best.pt`
  - Rewards endpoints (`/api/coupons`, `/api/redeem`)
  - Stats endpoint (`/api/stats`) for detections, redemptions, lifetime points
  - Database file: `backend/rewards_db.sqlite`

- Model: YOLO (Ultralytics). One set of weights at `backend/weights/best.pt`.

## 2) Data Model (SQLite)

- `users(id, username, password_hash, total_points, last_awarded_signature)`
- `coupons(id, name, points_cost, coupon_code, description, is_active)`
- `transactions(id, user_id, points_change, reason, created_at)`
- `stats(id=1, detections, redemptions)` — global counters

Notes:
- `transactions.points_change` positive for awarded points (detections), negative for spent points (redemptions).
- `last_awarded_signature` prevents duplicate awards for the exact same detection set.

## 3) Backend Endpoints

- `POST /api/signup { username, password }` → `{ user, token }`
- `POST /api/login { username, password }` → `{ user, token }`
- `POST /api/detect` (form-data: `file`, header `Authorization: Bearer token_...`)
  - Runs YOLO, calculates points:
    - Recyclable/Hazardous: `100 × unique items`
    - Only non-recyclables: `50` flat
    - Same detection set twice → no additional points
  - Updates `users.total_points`, `transactions`, and increments `stats.detections` when points are awarded.
  - Response: `{ detected_items, recyclable_items, hazardous_items, awarded_points, total_points, duplicate, message }`
- `GET /api/coupons` → `{ coupons: [...] }`
- `POST /api/redeem { coupon_id }`
  - Deducts points, inserts negative transaction, increments `stats.redemptions`
  - Response: `{ message, total_points, coupon_code }`
- `GET /api/stats`
  - Returns `{ detections, redemptions, lifetime_points }`
  - `lifetime_points = current total_points + absolute(sum of negative points for this user)`

## 4) Frontend Flows

### 4.1 Auth
- Token saved in `localStorage.authToken` on success.
- Login/Signup uses glass UI and shows errors inline.

### 4.2 Dashboard
- Tabs:
  - Earn Points:
    - Upload image and press "Analyze & Earn".
    - Shows preview, awarded points (e.g., `+100 pts`), and lists detected items by category.
    - On award, updates user points and stats (detections).
  - Rewards:
    - Lists coupons from `/api/coupons`.
    - Redeem updates points and increments `redemptions`.
    - Stats row shows:
      - Total Points = user current balance
      - Redemptions = total times redeemed (global counter)
      - Detections = total detections that awarded points (global counter)
    - Lifetime Points ring shows total points earned to date (does not decrease on redeems).
  - Profile:
    - Displays username and current total points + eco tips.

### 4.3 Styling Consistency
- Welcome, Auth, and Dashboard share:
  - Dark background with dotted grid and soft gradient glows
  - Glass surfaces (`bg-white/5`, `border-white/10`, `backdrop-blur`)
  - Inter (body) + Outfit (headings)

## 5) Running Locally

### 5.1 Backend
```powershell
cd backend
python -m venv .venv
. .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```
- Server: `http://127.0.0.1:5000`
- Ensure `backend/weights/best.pt` exists.

### 5.2 Frontend
```powershell
cd frontend
npm install
npm run dev
```
- Open the shown local URL (e.g., `http://127.0.0.1:5173`)

## 6) Points & Stats Logic

- Awarding Rules (backend `/api/detect`):
  - If recyclable/hazardous items detected → `100 × unique such items` points
  - Else if any items but none recyclable/hazardous → `+50` points
  - Else → `0` points
  - Duplicate detections (same set) → `0` points
- Redemptions deduct coupon cost and log a negative transaction.
- Lifetime Points = `current total_points + sum(spent)` so they never go down.
- Stats refresh after detection and redemption on the frontend.

## 7) Troubleshooting

- No model? Place `best.pt` at `backend/weights/best.pt`.
- CORS/Network: confirm backend on `http://127.0.0.1:5000` and token present.
- Large folder size: `.venv`, `node_modules`, and `weights` dominate. Safe to delete and reinstall when needed.

## 8) Files to Know

- Frontend
  - `src/components/WelcomePage.jsx` — hero page
  - `src/components/AuthGateway.jsx` — login/signup
  - `src/components/Dashboard.jsx` — tabs + stats + overlays
  - `src/components/EarnPoints.jsx` — detection upload and results
  - `index.css` — Tailwind theme
- Backend
  - `app.py` — all endpoints & DB init
  - `rewards_db.sqlite` — database
  - `weights/best.pt` — YOLO weights

## 9) Security Notes (Next Steps)
- Replace demo token (`token_username`) with proper JWT.
- Validate image size/type server-side.
- Per-user stats if needed (currently detections/redemptions counters are global).

## 10) Extending
- Add transaction history endpoint & UI.
- Add real-time toasts for detect/redeem.
- Add "streaks" and goals using stats.
