import os
import sqlite3
from sqlite3 import Connection
from typing import Tuple, Dict, Any, List, Set, Optional

from flask import Flask, request, jsonify
from flask_cors import CORS
import bcrypt

# YOLO and image processing
from ultralytics import YOLO
import cv2
import numpy as np


DB_PATH = os.path.join(os.path.dirname(__file__), 'rewards_db.sqlite')
WEIGHTS_PATH = os.path.join(os.path.dirname(__file__), 'weights', 'best.pt')
POINTS_PER_DETECTION = 100
NON_RECYCLABLE_FLAT_POINTS = 50

# Categories (aligned with Streamlit prototype)
RECYCLABLE: Set[str] = set(['cardboard_box','can','plastic_bottle_cap','plastic_bottle','reuseable_paper','glass'])
HAZARDOUS: Set[str] = set(['battery','chemical_spray_can','chemical_plastic_bottle','chemical_plastic_gallon','light_bulb','paint_bucket'])


# Lazy-loaded YOLO model
_yolo_model: Optional[YOLO] = None

def get_model() -> YOLO:
	global _yolo_model
	if _yolo_model is None:
		if not os.path.exists(WEIGHTS_PATH):
			raise RuntimeError(f"Model weights not found at {WEIGHTS_PATH}")
		_yolo_model = YOLO(WEIGHTS_PATH)
	return _yolo_model


def get_db_connection() -> Connection:
	conn = sqlite3.connect(DB_PATH)
	conn.row_factory = sqlite3.Row
	return conn


def seed_coupons(conn: Connection) -> None:
	cur = conn.execute('SELECT COUNT(*) FROM coupons')
	count = int(cur.fetchone()[0])
	if count == 0:
		conn.executemany(
			'INSERT INTO coupons (name, points_cost, coupon_code, description, is_active) VALUES (?, ?, ?, ?, ?)',
			[
				('10% Off Eco-Store Voucher', 500, 'ECOSAVE10', 'Get 10% off on sustainable products.', 1),
				('Free Digital Sticker Pack', 100, 'DIGISTICKER', 'A pack of 5 exclusive digital stickers.', 1),
				('₹50 Discount on Coffee', 750, 'COFFEE50', 'Valid at selected partner cafes.', 1),
			]
		)
		conn.commit()


def init_db() -> None:
	with get_db_connection() as conn:
		conn.execute(
			(
				'CREATE TABLE IF NOT EXISTS users ('
				'  id INTEGER PRIMARY KEY AUTOINCREMENT,'
				'  username TEXT UNIQUE NOT NULL,'
				'  password_hash BLOB NOT NULL,'
				'  total_points INTEGER NOT NULL DEFAULT 100,'
				'  last_awarded_signature TEXT'
				')'
			)
		)
		# Coupons table
		conn.execute(
			(
				'CREATE TABLE IF NOT EXISTS coupons ('
				'  id INTEGER PRIMARY KEY AUTOINCREMENT,'
				'  name TEXT NOT NULL,'
				'  points_cost INTEGER NOT NULL,'
				'  coupon_code TEXT UNIQUE NOT NULL,'
				'  description TEXT,'
				'  is_active INTEGER NOT NULL DEFAULT 1'
				')'
			)
		)
		# Transactions table
		conn.execute(
			(
				'CREATE TABLE IF NOT EXISTS transactions ('
				'  id INTEGER PRIMARY KEY AUTOINCREMENT,'
				'  user_id INTEGER NOT NULL,'
				'  points_change INTEGER NOT NULL,'
				'  reason TEXT NOT NULL,'
				'  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,'
				'  FOREIGN KEY(user_id) REFERENCES users(id)'
				')'
			)
		)
		# Simple stats table (detections/redemptions counters)
		conn.execute(
			'CREATE TABLE IF NOT EXISTS stats ('
			'  id INTEGER PRIMARY KEY CHECK (id = 1),'
			'  detections INTEGER NOT NULL DEFAULT 0,'
			'  redemptions INTEGER NOT NULL DEFAULT 0'
			')'
		)
		# Ensure single row
		row = conn.execute('SELECT id FROM stats WHERE id = 1').fetchone()
		if row is None:
			conn.execute('INSERT INTO stats (id, detections, redemptions) VALUES (1, 0, 0)')
		conn.commit()


app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})


def parse_username_from_auth() -> Optional[str]:
	auth_header = request.headers.get('Authorization', '')
	if not auth_header.startswith('Bearer '):
		return None
	token = auth_header.split(' ', 1)[1]
	if not token.startswith('token_'):
		return None
	return token.replace('token_', '', 1)


@app.route('/api/health', methods=['GET'])
def health() -> Tuple[Any, int]:
	return jsonify({"status": "ok"}), 200


@app.route('/api/signup', methods=['POST'])
def signup() -> Tuple[Any, int]:
	data: Dict[str, Any] = request.get_json(silent=True) or {}
	username: str = (data.get('username') or '').strip()
	password: str = (data.get('password') or '').strip()

	if not username or not password:
		return jsonify({"error": "username and password are required"}), 400

	# Hash password
	password_bytes = password.encode('utf-8')
	salt = bcrypt.gensalt()
	password_hash = bcrypt.hashpw(password_bytes, salt)

	try:
		with get_db_connection() as conn:
			conn.execute(
				'INSERT INTO users (username, password_hash, total_points) VALUES (?, ?, ?)',
				(username, password_hash, 100),
			)
			conn.commit()
	except sqlite3.IntegrityError:
		return jsonify({"error": "username already exists"}), 409

	user = {
		"username": username,
		"total_points": 100,
	}
	# Simple token stub; replace with real JWT/session later
	token = f"token_{username}"

	return jsonify({"user": user, "token": token}), 201


@app.route('/api/login', methods=['POST'])
def login() -> Tuple[Any, int]:
	data: Dict[str, Any] = request.get_json(silent=True) or {}
	username: str = (data.get('username') or '').strip()
	password: str = (data.get('password') or '').strip()

	if not username or not password:
		return jsonify({"error": "username and password are required"}), 400

	with get_db_connection() as conn:
		row = conn.execute(
			'SELECT username, password_hash, total_points FROM users WHERE username = ?',
			(username,),
		).fetchone()

	if row is None:
		return jsonify({"error": "invalid credentials"}), 401

	stored_hash: bytes = row[1]
	if not bcrypt.checkpw(password.encode('utf-8'), stored_hash):
		return jsonify({"error": "invalid credentials"}), 401

	user = {
		"username": row[0],
		"total_points": row[2],
	}
	token = f"token_{username}"

	return jsonify({"user": user, "token": token}), 200


@app.route('/api/coupons', methods=['GET'])
def list_coupons() -> Tuple[Any, int]:
	username = parse_username_from_auth()
	if not username:
		return jsonify({"error": "unauthorized"}), 401
	with get_db_connection() as conn:
		rows = conn.execute('SELECT id, name, points_cost, coupon_code, description FROM coupons WHERE is_active = 1 ORDER BY points_cost ASC').fetchall()
		coupons = [
			{"id": r[0], "name": r[1], "points_cost": r[2], "coupon_code": r[3], "description": r[4]}
			for r in rows
		]
	return jsonify({"coupons": coupons}), 200


@app.route('/api/redeem', methods=['POST'])
def redeem_coupon() -> Tuple[Any, int]:
	username = parse_username_from_auth()
	if not username:
		return jsonify({"error": "unauthorized"}), 401
	data: Dict[str, Any] = request.get_json(silent=True) or {}
	coupon_id = data.get('coupon_id')
	if not coupon_id:
		return jsonify({"error": "coupon_id is required"}), 400
	with get_db_connection() as conn:
		user_row = conn.execute('SELECT id, total_points FROM users WHERE username = ?', (username,)).fetchone()
		if user_row is None:
			return jsonify({"error": "user not found"}), 404
		user_id, total_points = int(user_row[0]), int(user_row[1])
		c_row = conn.execute('SELECT id, name, points_cost, coupon_code FROM coupons WHERE id = ? AND is_active = 1', (coupon_id,)).fetchone()
		if c_row is None:
			return jsonify({"error": "coupon not found"}), 404
		cid, cname, cost, code = int(c_row[0]), str(c_row[1]), int(c_row[2]), str(c_row[3])
		if total_points < cost:
			return jsonify({"error": "insufficient points"}), 400
		new_total = total_points - cost
		conn.execute('UPDATE users SET total_points = ? WHERE id = ?', (new_total, user_id))
		conn.execute('INSERT INTO transactions (user_id, points_change, reason) VALUES (?, ?, ?)', (user_id, -cost, f"Redeemed: {cname}"))
		conn.execute('UPDATE stats SET redemptions = redemptions + 1 WHERE id = 1')
		conn.commit()
	return jsonify({"message": "Coupon redeemed", "total_points": new_total, "coupon_code": code}), 200


@app.route('/api/transactions', methods=['GET'])
def list_transactions() -> Tuple[Any, int]:
	username = parse_username_from_auth()
	if not username:
		return jsonify({"error": "unauthorized"}), 401
	limit = int(request.args.get('limit', '20'))
	with get_db_connection() as conn:
		row = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
		if row is None:
			return jsonify({"error": "user not found"}), 404
		user_id = int(row[0])
		rows = conn.execute('SELECT points_change, reason, created_at FROM transactions WHERE user_id = ? ORDER BY id DESC LIMIT ?', (user_id, limit)).fetchall()
		transactions = [{"points_change": r[0], "reason": r[1], "created_at": r[2]} for r in rows]
	return jsonify({"transactions": transactions}), 200


@app.route('/api/detect', methods=['POST'])
def detect() -> Tuple[Any, int]:
	username = parse_username_from_auth()
	if not username:
		return jsonify({"error": "missing auth token"}), 401

	if 'file' not in request.files:
		return jsonify({"error": "no file uploaded"}), 400
	file = request.files['file']
	if file.filename == '':
		return jsonify({"error": "empty filename"}), 400

	# Read image bytes to numpy array
	file_bytes = file.read()
	np_arr = np.frombuffer(file_bytes, np.uint8)
	image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
	if image is None:
		return jsonify({"error": "invalid image"}), 400

	model = get_model()
	results = model.predict(image, conf=0.6)
	names = model.names

	detected_items: Set[str] = set()
	for result in results:
		for cls_idx in result.boxes.cls:
			try:
				label = names[int(cls_idx)]
			except Exception:
				continue
			detected_items.add(label)

	recyclable_items = list(sorted(RECYCLABLE.intersection(detected_items)))
	hazardous_items = list(sorted(HAZARDOUS.intersection(detected_items)))

	# Build a signature of all detected items to prevent repeat spamming
	detection_signature = ','.join(sorted(list(detected_items))) if detected_items else ''

	# Default awarding logic
	awarded_points = 0
	message = ''
	if recyclable_items or hazardous_items:
		awarded_points = POINTS_PER_DETECTION * len(set(recyclable_items) | set(hazardous_items))
		message = 'Recyclable/Hazardous waste detected. Points awarded.'
	elif detected_items:
		awarded_points = NON_RECYCLABLE_FLAT_POINTS
		message = 'Only non-recyclables detected. Flat points awarded.'
	else:
		message = 'No waste detected.'

	# Check last awarded signature to prevent duplicate awards for identical detections
	duplicate = False
	with get_db_connection() as conn:
		row = conn.execute('SELECT id, total_points, IFNULL(last_awarded_signature, "") FROM users WHERE username = ?', (username,)).fetchone()
		if row is None:
			return jsonify({"error": "user not found"}), 404
		user_id = int(row[0])
		current_total = int(row[1])
		last_sig = str(row[2]) if row[2] is not None else ''

		if detection_signature and detection_signature == last_sig:
			duplicate = True
			new_total = current_total
			message = 'This waste was already detected. No additional points awarded.'
		else:
			new_total = current_total + awarded_points
			conn.execute('UPDATE users SET total_points = ?, last_awarded_signature = ? WHERE id = ?', (new_total, detection_signature, user_id))
			if awarded_points != 0:
				conn.execute('INSERT INTO transactions (user_id, points_change, reason) VALUES (?, ?, ?)', (user_id, awarded_points, 'Waste Detected'))
				conn.execute('UPDATE stats SET detections = detections + 1 WHERE id = 1')
			conn.commit()

	response = {
		"detected_items": sorted(list(detected_items)),
		"recyclable_items": recyclable_items,
		"hazardous_items": hazardous_items,
		"awarded_points": 0 if duplicate else awarded_points,
		"total_points": new_total,
		"duplicate": duplicate,
		"message": message,
	}
	return jsonify(response), 200


@app.route('/api/stats', methods=['GET'])
def get_stats() -> Tuple[Any, int]:
	username = parse_username_from_auth()
	if not username:
		return jsonify({"error": "unauthorized"}), 401
	with get_db_connection() as conn:
		u = conn.execute('SELECT id, total_points FROM users WHERE username = ?', (username,)).fetchone()
		if u is None:
			return jsonify({"error": "user not found"}), 404
		uid = int(u[0])
		total_now = int(u[1])
		# per-user counts from transactions
		row_pos = conn.execute('SELECT COUNT(*) FROM transactions WHERE user_id = ? AND points_change > 0', (uid,)).fetchone()
		row_neg = conn.execute('SELECT COUNT(*) FROM transactions WHERE user_id = ? AND points_change < 0', (uid,)).fetchone()
		detections = int(row_pos[0]) if row_pos else 0
		redemptions = int(row_neg[0]) if row_neg else 0
		spent_row = conn.execute('SELECT COALESCE(SUM(CASE WHEN points_change < 0 THEN -points_change ELSE 0 END),0) FROM transactions WHERE user_id = ?', (uid,)).fetchone()
		spent = int(spent_row[0]) if spent_row else 0
		lifetime_points = total_now + spent
	return jsonify({"detections": detections, "redemptions": redemptions, "lifetime_points": lifetime_points}), 200


if __name__ == '__main__':
	init_db()
	app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
