import os
import sqlite3
from sqlite3 import Connection
from typing import Tuple, Dict, Any, List, Set, Optional
import base64
import io
import json
import hashlib
import time
import random
from datetime import datetime, timedelta

from flask import Flask, request, jsonify, Response, send_from_directory
from flask_cors import CORS
import bcrypt
import queue
from collections import defaultdict
import smtplib
from email.message import EmailMessage

# Image processing
import cv2
import numpy as np

# Video processing
import tempfile

# EXIF and geolocation processing
import piexif
from geopy.geocoders import Nominatim
import math

# Gemini AI integration
try:
    import google.generativeai as genai
except Exception:
    genai = None
from PIL import Image


DB_PATH = os.path.join(os.path.dirname(__file__), 'rewards_db.sqlite')
POINTS_PER_DETECTION = 100
NON_RECYCLABLE_FLAT_POINTS = 50

# Gemini API configuration
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
if GEMINI_API_KEY and genai is not None:
    genai.configure(api_key=GEMINI_API_KEY)


def generate_image_hash(image_bytes: bytes) -> str:
	"""
	Generate a SHA-256 hash of the image bytes for duplicate detection
	"""
	return hashlib.sha256(image_bytes).hexdigest()


def extract_gps_from_image(image_bytes: bytes) -> tuple:
	"""
	Extract GPS coordinates from image EXIF data
	Returns (latitude, longitude) or (None, None) if not found
	"""
	try:
		# Load image and extract EXIF data
		image = Image.open(io.BytesIO(image_bytes))
		exif_dict = piexif.load(image.info.get('exif', b''))
		
		# Check if GPS data exists
		if 'GPS' not in exif_dict:
			return None, None
		
		gps_data = exif_dict['GPS']
		
		# Extract latitude
		if piexif.GPSIFD.GPSLatitude in gps_data and piexif.GPSIFD.GPSLatitudeRef in gps_data:
			lat_deg = gps_data[piexif.GPSIFD.GPSLatitude]
			lat_ref = gps_data[piexif.GPSIFD.GPSLatitudeRef]
			latitude = (lat_deg[0][0] / lat_deg[0][1] + 
					   lat_deg[1][0] / lat_deg[1][1] / 60.0 + 
					   lat_deg[2][0] / lat_deg[2][1] / 3600.0)
			if lat_ref == b'S':
				latitude = -latitude
		else:
			return None, None
		
		# Extract longitude
		if piexif.GPSIFD.GPSLongitude in gps_data and piexif.GPSIFD.GPSLongitudeRef in gps_data:
			lon_deg = gps_data[piexif.GPSIFD.GPSLongitude]
			lon_ref = gps_data[piexif.GPSIFD.GPSLongitudeRef]
			longitude = (lon_deg[0][0] / lon_deg[0][1] + 
						lon_deg[1][0] / lon_deg[1][1] / 60.0 + 
						lon_deg[2][0] / lon_deg[2][1] / 3600.0)
			if lon_ref == b'W':
				longitude = -longitude
		else:
			return None, None
		
		return latitude, longitude
		
	except Exception as e:
		print(f"Error extracting GPS data: {str(e)}")
		return None, None


def reverse_geocode(latitude: float, longitude: float) -> dict:
	"""
	Convert GPS coordinates to address components using reverse geocoding
	"""
	try:
		geolocator = Nominatim(user_agent="waste_bounty_app")
		location = geolocator.reverse(f"{latitude}, {longitude}", language='en')
		
		if not location:
			print(f"Reverse geocoding failed for coordinates: {latitude}, {longitude}")
			return None
		
		address = location.raw.get('address', {})
		print(f"Address components for {latitude}, {longitude}: {address}")
		
		# Try multiple possible city fields
		city = (address.get('city') or 
		        address.get('town') or 
		        address.get('village') or 
		        address.get('municipality') or
		        address.get('suburb') or
		        address.get('county') or
		        address.get('district') or
		        'Unknown')
		
		# Try multiple possible state fields
		state = (address.get('state') or 
		         address.get('province') or 
		         address.get('region') or
		         address.get('administrative') or
		         'Unknown')
		
		result = {
			'country': address.get('country', 'Unknown'),
			'state': state,
			'city': city
		}
		
		print(f"Parsed location: {result}")
		return result
		
	except Exception as e:
		print(f"Error in reverse geocoding: {str(e)}")
		return None


def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
	"""
	Calculate distance between two GPS coordinates using Haversine formula
	Returns distance in meters
	"""
	try:
		# Convert to radians
		lat1_rad = math.radians(lat1)
		lon1_rad = math.radians(lon1)
		lat2_rad = math.radians(lat2)
		lon2_rad = math.radians(lon2)
		
		# Haversine formula
		dlat = lat2_rad - lat1_rad
		dlon = lon2_rad - lon1_rad
		a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
		c = 2 * math.asin(math.sqrt(a))
		
		# Earth's radius in meters
		earth_radius = 6371000
		distance = earth_radius * c
		
		return distance
		
	except Exception as e:
		print(f"Error calculating distance: {str(e)}")
		return float('inf')


def extract_keyframes_from_video(video_bytes: bytes) -> List[np.ndarray]:
	"""
	Intelligently extract 5 optimal frames from videos of any length (2-6 seconds)
	Adaptive algorithm that finds the best frames for waste disposal verification:
	- F1: Clear view of waste item in hand (early in video)
	- F2: Pre-disposal context frame
	- F3: Peak disposal action frame (highest motion/change)
	- F4: Post-disposal verification frame
	- F5: Final result frame (waste item in bin)
	"""
	try:
		# Create temporary file for video processing
		with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_file:
			temp_file.write(video_bytes)
			temp_video_path = temp_file.name
		
		# Load video with OpenCV
		cap = cv2.VideoCapture(temp_video_path)
		if not cap.isOpened():
			raise Exception("Could not open video file")
		
		# Get video properties
		fps = cap.get(cv2.CAP_PROP_FPS)
		total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
		duration = total_frames / fps if fps > 0 else 3.0
		
		# Ensure video is at least 2 seconds for proper analysis
		if duration < 2.0:
			raise Exception("Video too short - minimum 2 seconds required for proper disposal verification")
		
		print(f"Video analysis: duration={duration:.2f}s, fps={fps:.2f}, frames={total_frames}")
		
		# Adaptive frame selection based on video length
		# For longer videos, we have more flexibility in frame selection
		analysis_start = 0.2  # Start analysis after 0.2s (skip initial setup)
		analysis_end = duration - 0.3  # End analysis 0.3s before end (skip final cleanup)
		
		# Calculate analysis window
		analysis_duration = analysis_end - analysis_start
		start_frame = int(analysis_start * fps)
		end_frame = int(analysis_end * fps)
		
		print(f"Analysis window: {analysis_start:.2f}s to {analysis_end:.2f}s ({analysis_duration:.2f}s duration)")
		
		# Step 1: Extract all frames in analysis window for motion analysis
		frames_data = []
		for frame_idx in range(start_frame, end_frame):
			cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
			ret, frame = cap.read()
			if ret:
				frames_data.append((frame_idx, frame))
		
		if len(frames_data) < 5:
			raise Exception("Not enough frames for analysis")
		
		print(f"Analyzing {len(frames_data)} frames for optimal selection")
		
		# Step 2: Calculate motion scores for all frames
		motion_scores = []
		for i in range(1, len(frames_data) - 1):
			prev_frame = frames_data[i-1][1]
			curr_frame = frames_data[i][1]
			next_frame = frames_data[i+1][1]
			
			# Calculate motion between consecutive frames
			diff1 = cv2.absdiff(prev_frame, curr_frame)
			diff2 = cv2.absdiff(curr_frame, next_frame)
			motion_score = np.sum(diff1) + np.sum(diff2)
			
			# Calculate structural changes
			gray_prev = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
			gray_curr = cv2.cvtColor(curr_frame, cv2.COLOR_BGR2GRAY)
			gray_next = cv2.cvtColor(next_frame, cv2.COLOR_BGR2GRAY)
			
			# Edge detection for structural changes
			edges_prev = cv2.Canny(gray_prev, 50, 150)
			edges_curr = cv2.Canny(gray_curr, 50, 150)
			edges_next = cv2.Canny(gray_next, 50, 150)
			
			edge_diff1 = np.sum(cv2.absdiff(edges_prev, edges_curr))
			edge_diff2 = np.sum(cv2.absdiff(edges_curr, edges_next))
			
			# Combined motion and structural change score
			combined_score = motion_score + edge_diff1 + edge_diff2
			motion_scores.append((i, combined_score, frames_data[i][0]))
		
		# Step 3: Find peak motion frame (disposal action)
		motion_scores.sort(key=lambda x: x[1], reverse=True)
		peak_motion_idx = motion_scores[0][0]  # Index in frames_data
		peak_frame_idx = motion_scores[0][2]   # Actual frame number
		
		print(f"Peak motion detected at frame {peak_frame_idx} (score: {motion_scores[0][1]:.0f})")
		
		# Step 4: Select optimal 5 frames
		# F1: Early frame showing item in hand (first 25% of analysis window)
		f1_idx = max(0, int(len(frames_data) * 0.1))
		f1 = frames_data[f1_idx][1]
		
		# F2: Pre-disposal frame (before peak motion)
		f2_idx = max(0, peak_motion_idx - int(0.3 * fps))  # 0.3s before action
		f2_idx = min(f2_idx, len(frames_data) - 1)
		f2 = frames_data[f2_idx][1]
		
		# F3: Peak disposal action frame
		f3 = frames_data[peak_motion_idx][1]
		
		# F4: Post-disposal frame (after peak motion)
		f4_idx = min(len(frames_data) - 1, peak_motion_idx + int(0.3 * fps))  # 0.3s after action
		f4 = frames_data[f4_idx][1]
		
		# F5: Final verification frame (last 25% of analysis window)
		f5_idx = min(len(frames_data) - 1, int(len(frames_data) * 0.9))
		f5 = frames_data[f5_idx][1]
		
		print(f"Selected frames: F1={f1_idx}, F2={f2_idx}, F3={peak_motion_idx}, F4={f4_idx}, F5={f5_idx}")
		
		# Step 5: Quality check - ensure frames are not too blurry or dark
		frames = [f1, f2, f3, f4, f5]
		quality_checked_frames = []
		
		for i, frame in enumerate(frames):
			# Convert to grayscale for quality assessment
			gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
			
			# Calculate sharpness using Laplacian variance
			sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()
			
			# Calculate brightness
			brightness = np.mean(gray)
			
			# Quality thresholds
			min_sharpness = 100  # Minimum sharpness threshold
			min_brightness = 30  # Minimum brightness threshold
			max_brightness = 220  # Maximum brightness threshold (avoid overexposure)
			
			print(f"Frame F{i+1}: sharpness={sharpness:.1f}, brightness={brightness:.1f}")
			
			# If frame quality is poor, try to find a better nearby frame
			if sharpness < min_sharpness or brightness < min_brightness or brightness > max_brightness:
				print(f"Frame F{i+1} quality poor, searching for better alternative...")
				
				# Search for better frame in nearby range
				search_range = int(0.2 * fps)  # Search within 0.2 seconds
				best_frame = frame
				best_score = sharpness + brightness
				
				start_search = max(0, frames_data[f1_idx if i == 0 else f2_idx if i == 1 else peak_motion_idx if i == 2 else f4_idx if i == 3 else f5_idx][0] - search_range)
				end_search = min(len(frames_data) - 1, frames_data[f1_idx if i == 0 else f2_idx if i == 1 else peak_motion_idx if i == 2 else f4_idx if i == 3 else f5_idx][0] + search_range)
				
				for search_idx in range(start_search, end_search + 1):
					if search_idx < len(frames_data):
						search_frame = frames_data[search_idx][1]
						search_gray = cv2.cvtColor(search_frame, cv2.COLOR_BGR2GRAY)
						search_sharpness = cv2.Laplacian(search_gray, cv2.CV_64F).var()
						search_brightness = np.mean(search_gray)
						
						if (search_sharpness >= min_sharpness and 
							min_brightness <= search_brightness <= max_brightness):
							search_score = search_sharpness + search_brightness
							if search_score > best_score:
								best_frame = search_frame
								best_score = search_score
				
				quality_checked_frames.append(best_frame)
				print(f"Frame F{i+1} replaced with better quality frame")
			else:
				quality_checked_frames.append(frame)
		
		cap.release()
		
		# Clean up temporary file
		os.unlink(temp_video_path)
		
		# Return quality-checked frames in order: F1, F2, F3, F4, F5
		return quality_checked_frames
		
	except Exception as e:
		# Clean up temporary file if it exists
		if 'temp_video_path' in locals() and os.path.exists(temp_video_path):
			os.unlink(temp_video_path)
		raise Exception(f"Video processing failed: {str(e)}")


def analyze_video_sequence_with_gemini(frames: List[np.ndarray], max_retries: int = 2) -> Dict[str, Any]:
	"""
	Analyze a sequence of 5 video frames using Gemini API for waste disposal verification
	Includes retry mechanism for improved consistency
	"""
	if not GEMINI_API_KEY or genai is None:
		return {
			"error": "Gemini API key not configured", 
			"waste_type": "unknown",
			"disposal_verified": False,
			"fallback": True,
			"message": "Gemini API not available"
		}
	
	for attempt in range(max_retries + 1):
		try:
			print(f"Gemini analysis attempt {attempt + 1}/{max_retries + 1}")
			result = _perform_gemini_analysis(frames)
			
			# If we get a valid result, return it
			if result and not result.get("fallback", False):
				return result
			
			# If this is not the last attempt, continue to retry
			if attempt < max_retries:
				print(f"Analysis attempt {attempt + 1} failed, retrying...")
				continue
			
			# If all attempts failed, return the last result
			return result
			
		except Exception as e:
			print(f"Gemini analysis attempt {attempt + 1} failed with error: {str(e)}")
			if attempt == max_retries:
				return {
					"error": f"Gemini analysis failed after {max_retries + 1} attempts: {str(e)}", 
					"waste_type": "unknown",
					"disposal_verified": False,
					"fallback": True,
					"message": "All analysis attempts failed"
				}
	
	return {
		"error": "Unexpected error in video analysis",
		"waste_type": "unknown", 
		"disposal_verified": False,
		"fallback": True,
		"message": "Analysis failed"
	}


def _perform_gemini_analysis(frames: List[np.ndarray]) -> Dict[str, Any]:
	"""
	Perform a single Gemini analysis attempt
	"""
	try:
		# Convert OpenCV frames to PIL Images
		pil_images = []
		for frame in frames:
			image_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
			pil_image = Image.fromarray(image_rgb)
			pil_images.append(pil_image)
		
		# Initialize Gemini model
		model = genai.GenerativeModel('gemini-2.0-flash')
		
		# Create optimized prompt for intelligent frame analysis
		prompt = """You are analyzing a sequence of 5 carefully selected frames from a waste disposal video. Each frame was chosen to show a specific part of the disposal process.

FRAME SEQUENCE ANALYSIS:
- F1: Early frame showing waste item in user's hand (item identification)
- F2: Pre-disposal frame (item still in hand, approaching bin)
- F3: Peak action frame (disposal moment - highest motion detected)
- F4: Post-disposal frame (item being released/dropped)
- F5: Final verification frame (item should be in bin)

CRITICAL ANALYSIS RULES:
1. IGNORE hands, dustbins, and containers - focus ONLY on the actual waste item
2. Look for actual waste: bottles, cans, paper, food, packaging, etc.
3. Verify the item moves from hand to inside the bin across the sequence
4. F3 should show the disposal action (item being thrown/dropped into bin)
5. F5 should show the item is no longer in hand and is in/on the bin

DETECTION CRITERIA:
- Item clearly visible in F1/F2 (in user's hand)
- Item moves toward bin in F2-F3
- Disposal action visible in F3 (item being released)
- Item no longer in hand in F4-F5
- Item appears to be in/on the bin in F5

Respond with JSON only:
{'waste_type': '[exact item name from F1/F2]', 'disposal_verified': [true/false], 'reasoning': '[step-by-step analysis of what you see in each frame]'}"""
		
		# Generate response with all 5 images
		response = model.generate_content([prompt] + pil_images)
		
		# Debug logging
		print(f"Gemini API Response: {response.text if response and response.text else 'No response'}")
		
		if not response or not response.text:
			return {
				"error": "Empty response from Gemini API",
				"waste_type": "unknown",
				"disposal_verified": False,
				"fallback": True,
				"message": "Gemini returned empty response"
			}
		
		# Parse JSON response
		response_text = response.text.strip()
		
		# Try to extract JSON from response
		json_text = None
		if '```json' in response_text:
			json_start = response_text.find('```json') + 7
			json_end = response_text.find('```', json_start)
			json_text = response_text[json_start:json_end].strip()
		elif '{' in response_text and '}' in response_text:
			json_start = response_text.find('{')
			json_end = response_text.rfind('}') + 1
			json_text = response_text[json_start:json_end]
		
		if not json_text:
			return {
				"waste_type": "unknown",
				"disposal_verified": False,
				"fallback": False,
				"raw_response": response_text,
				"message": "Unable to parse response"
			}
		
		try:
			result = json.loads(json_text)
		except json.JSONDecodeError:
			return {
				"waste_type": "unknown",
				"disposal_verified": False,
				"fallback": False,
				"raw_response": response_text,
				"message": "JSON parsing failed"
			}
		
		# Validate result structure
		if not isinstance(result, dict):
			return {
				"error": "Invalid response structure from Gemini",
				"waste_type": "unknown",
				"disposal_verified": False,
				"fallback": True,
				"message": "Invalid response structure"
			}
		
		# Ensure required keys exist
		if "waste_type" not in result:
			result["waste_type"] = "unknown"
		if "disposal_verified" not in result:
			result["disposal_verified"] = False
		if "reasoning" not in result:
			result["reasoning"] = "No reasoning provided"
		
		return result
		
	except Exception as e:
		print(f"Gemini video analysis error: {str(e)}")
		return {
			"error": f"Gemini video analysis failed: {str(e)}", 
			"waste_type": "unknown",
			"disposal_verified": False,
			"fallback": True,
			"message": "API error occurred"
		}


def analyze_with_gemini(image: np.ndarray) -> Dict[str, Any]:
	"""
	Analyze waste items in image using Gemini API as the primary detection system
	Returns comprehensive waste analysis with classification and disposal recommendations
	"""
	if not GEMINI_API_KEY or genai is None:
		return {
			"error": "Gemini API key not configured", 
			"items": [], 
			"fallback": True,
			"message": "Gemini API not available"
		}
	
	try:
		# Convert OpenCV image to PIL Image
		image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
		pil_image = Image.fromarray(image_rgb)
		
		# Initialize Gemini model
		model = genai.GenerativeModel('gemini-2.0-flash')
		
		# Create comprehensive prompt for waste detection and analysis
		prompt = """
		You are an expert waste detection and classification AI. Analyze this image thoroughly and identify ALL waste items present.
		
		IMPORTANT: You MUST respond ONLY with valid JSON. Do not include any other text.
		
		For each waste item found, provide:
		- name: Specific item name/type (be very specific)
		- category: "recyclable", "hazardous", or "general" 
		- material_type: Specific material (e.g., "PET plastic", "aluminum", "cardboard", "glass")
		- description: Detailed description of the item including size, color, condition
		- disposal_tip: Specific instructions for proper disposal
		- environmental_impact: Brief note on environmental impact
		- recyclability: "high", "medium", "low", or "not_recyclable"
		- decomposition_time: Estimated time to decompose (e.g., "450 years", "2-6 weeks", "indefinite")
		
		Look for ALL types of waste including:
		- Plastic bottles, containers, bags, packaging (specify plastic type if visible)
		- Aluminum/metal cans, containers, foil
		- Glass bottles, jars, containers (specify glass type)
		- Cardboard, paper products, newspapers, magazines
		- Batteries (all types - AA, AAA, lithium, lead-acid)
		- Chemical containers, paint cans, aerosol cans
		- Light bulbs, fluorescent tubes, LED bulbs
		- Electronic waste, cables, devices, chargers
		- Food waste, organic matter, compostable items
		- Textiles, clothing, fabric scraps
		- Construction materials, wood, metal scraps
		- Medical waste, syringes, bandages
		- Any other waste materials
		
		Classification guidelines:
		- recyclable: Items that can be recycled (plastic bottles, metal cans, glass, paper, cardboard, electronics)
		- hazardous: Items that are dangerous or require special disposal (batteries, chemicals, electronics, medical waste, fluorescent bulbs)
		- general: Items that go to regular landfill (food waste, non-recyclable plastics, mixed materials, contaminated items)
		
		If no waste items are found, return: {"items": [], "summary": "No waste items detected in the image"}
		
		Response format (JSON only):
		{
			"items": [
				{
					"name": "specific item name",
					"category": "recyclable|hazardous|general",
					"material_type": "specific material",
					"description": "detailed description",
					"disposal_tip": "specific disposal instructions",
					"environmental_impact": "brief environmental note",
					"recyclability": "high|medium|low|not_recyclable",
					"decomposition_time": "estimated time"
				}
			],
			"summary": "Overall waste analysis summary with total count and main categories",
			"total_items": "number of items found",
			"recyclable_count": "number of recyclable items",
			"hazardous_count": "number of hazardous items",
			"general_count": "number of general waste items"
		}
		"""
		
		# Generate response
		response = model.generate_content([prompt, pil_image])
		
		if not response or not response.text:
			return {
				"error": "Empty response from Gemini API",
				"items": [],
				"fallback": True,
				"message": "Gemini returned empty response"
			}
		
		# Parse JSON response
		response_text = response.text.strip()
		
		# Try to extract JSON from response
		json_text = None
		if '```json' in response_text:
			json_start = response_text.find('```json') + 7
			json_end = response_text.find('```', json_start)
			json_text = response_text[json_start:json_end].strip()
		elif '{' in response_text and '}' in response_text:
			json_start = response_text.find('{')
			json_end = response_text.rfind('}') + 1
			json_text = response_text[json_start:json_end]
		
		if not json_text:
			return {
				"items": [],
				"fallback": False,
				"raw_response": response_text,
				"summary": "Unable to parse response"
			}
		
		try:
			result = json.loads(json_text)
		except json.JSONDecodeError:
			return {
				"items": [],
				"fallback": False,
				"raw_response": response_text,
				"summary": "JSON parsing failed"
			}
		
		# Validate result structure
		if not isinstance(result, dict):
			return {
				"error": "Invalid response structure from Gemini",
				"items": [],
				"fallback": True,
				"message": "Invalid response structure"
			}
		
		# Ensure items key exists
		if "items" not in result:
			result["items"] = []
		
		return result
		
	except Exception as e:
		print(f"Gemini API error: {str(e)}")
		return {
			"error": f"Gemini analysis failed: {str(e)}", 
			"items": [], 
			"fallback": True,
			"message": "API error occurred"
		}


def categorize_gemini_items(gemini_result: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
	"""
	Categorize items detected by Gemini into recyclable, hazardous, and general waste
	Returns full item details for each category
	"""
	recyclable_items = []
	hazardous_items = []
	general_items = []
	
	if "items" in gemini_result:
		for item in gemini_result["items"]:
			category = item.get("category", "general").lower()
			
			# Categorize based on Gemini's classification
			if category == "recyclable":
				recyclable_items.append(item)
			elif category == "hazardous":
				hazardous_items.append(item)
			else:
				general_items.append(item)
	
	return {
		"recyclable": recyclable_items,
		"hazardous": hazardous_items,
		"general": general_items
	}


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
		# Create users table with new schema
		conn.execute(
			(
				'CREATE TABLE IF NOT EXISTS users ('
				'  id INTEGER PRIMARY KEY AUTOINCREMENT,'
				'  username TEXT UNIQUE NOT NULL,'
                '  email TEXT UNIQUE NOT NULL,'
				'  password_hash BLOB NOT NULL,'
				'  total_points INTEGER NOT NULL DEFAULT 100,'
				'  last_awarded_signature TEXT,'
				'  country TEXT NOT NULL,'
				'  state TEXT NOT NULL,'
				'  city TEXT NOT NULL,'
				'  district TEXT NOT NULL DEFAULT "Unknown"'
				')'
			)
		)
		
		# Check if location columns exist, if not add them
		cursor = conn.execute("PRAGMA table_info(users)")
		columns = [column[1] for column in cursor.fetchall()]
		
		# Backfill legacy schemas missing any of these columns
		if 'email' not in columns:
			conn.execute('ALTER TABLE users ADD COLUMN email TEXT')
		if 'country' not in columns:
			conn.execute('ALTER TABLE users ADD COLUMN country TEXT DEFAULT "Unknown"')
		if 'state' not in columns:
			conn.execute('ALTER TABLE users ADD COLUMN state TEXT DEFAULT "Unknown"')
		if 'city' not in columns:
			conn.execute('ALTER TABLE users ADD COLUMN city TEXT DEFAULT "Unknown"')
		if 'district' not in columns:
			conn.execute('ALTER TABLE users ADD COLUMN district TEXT DEFAULT "Unknown"')
		# Ensure unique index on email (allows multiple NULLs for legacy rows)
		conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email)')
		conn.commit()
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
		# Seed default coupons once
		seed_coupons(conn)
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
		
		# Image hashes table for duplicate detection
		conn.execute(
			'CREATE TABLE IF NOT EXISTS image_hashes ('
			'  id INTEGER PRIMARY KEY AUTOINCREMENT,'
			'  user_id INTEGER NOT NULL,'
			'  image_hash TEXT NOT NULL,'
			'  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,'
			'  FOREIGN KEY(user_id) REFERENCES users(id),'
			'  UNIQUE(user_id, image_hash)'
			')'
		)
		# WasteBounty table for bounty system
		conn.execute(
			'CREATE TABLE IF NOT EXISTS waste_bounty ('
			'  id INTEGER PRIMARY KEY AUTOINCREMENT,'
			'  reporter_user_id INTEGER NOT NULL,'
			'  latitude REAL NOT NULL,'
			'  longitude REAL NOT NULL,'
			'  country TEXT NOT NULL,'
			'  state TEXT NOT NULL,'
			'  city TEXT NOT NULL,'
			'  bounty_points INTEGER NOT NULL DEFAULT 200,'
			'  waste_image_url TEXT NOT NULL,'
			'  before_image_url TEXT,'
			'  after_image_url TEXT,'
			'  status TEXT NOT NULL DEFAULT "REPORTED",'
			'  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,'
			'  claimed_at DATETIME,'
			'  claimed_by_user_id INTEGER,'
			'  completed_at DATETIME,'
			'  FOREIGN KEY(reporter_user_id) REFERENCES users(id),'
			'  FOREIGN KEY(claimed_by_user_id) REFERENCES users(id)'
			')'
		)
		# Add new columns if they don't exist (for upgrades)
		cursor = conn.execute('PRAGMA table_info(waste_bounty)')
		columns = [column[1] for column in cursor.fetchall()]
		if 'before_image_url' not in columns:
			conn.execute('ALTER TABLE waste_bounty ADD COLUMN before_image_url TEXT')
		if 'after_image_url' not in columns:
			conn.execute('ALTER TABLE waste_bounty ADD COLUMN after_image_url TEXT')
		# Bounty chat messages table for per-bounty chat
		conn.execute(
			'CREATE TABLE IF NOT EXISTS bounty_chat_messages ('
			'  id INTEGER PRIMARY KEY AUTOINCREMENT,'
			'  bounty_id INTEGER NOT NULL,'
			'  sender_user_id INTEGER NOT NULL,'
			'  message TEXT NOT NULL,'
			'  city TEXT NOT NULL,'
			'  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,'
			'  deleted_at DATETIME,'
			'  deleted_by_user_id INTEGER,'
			'  FOREIGN KEY(bounty_id) REFERENCES waste_bounty(id),'
			'  FOREIGN KEY(sender_user_id) REFERENCES users(id),'
			'  FOREIGN KEY(deleted_by_user_id) REFERENCES users(id)'
			')'
		)
		conn.execute('CREATE INDEX IF NOT EXISTS idx_bounty_chat_bounty_id ON bounty_chat_messages(bounty_id)')
		conn.commit()

		# Clans core tables
		conn.execute(
			(
				'CREATE TABLE IF NOT EXISTS clans ('
				'  id INTEGER PRIMARY KEY AUTOINCREMENT,'
				'  name TEXT NOT NULL,'
				'  city TEXT NOT NULL,'
				'  state TEXT,'
				'  country TEXT,'
				'  leader_user_id INTEGER NOT NULL,'
				'  join_code TEXT UNIQUE NOT NULL,'
				'  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,'
				'  FOREIGN KEY(leader_user_id) REFERENCES users(id)'
				')'
			)
		)
		conn.execute(
			(
				'CREATE TABLE IF NOT EXISTS clan_members ('
				'  id INTEGER PRIMARY KEY AUTOINCREMENT,'
				'  clan_id INTEGER NOT NULL,'
				'  user_id INTEGER NOT NULL,'
				'  role TEXT NOT NULL DEFAULT "member",'
				'  joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,'
				'  FOREIGN KEY(clan_id) REFERENCES clans(id),'
				'  FOREIGN KEY(user_id) REFERENCES users(id),'
				'  UNIQUE(user_id),'
				'  UNIQUE(clan_id, user_id)'
				')'
			)
		)
		conn.execute('CREATE INDEX IF NOT EXISTS idx_clan_members_clan ON clan_members(clan_id)')
		conn.execute('CREATE INDEX IF NOT EXISTS idx_clans_city ON clans(city)')
		conn.execute(
			(
				'CREATE TABLE IF NOT EXISTS clan_messages ('
				'  id INTEGER PRIMARY KEY AUTOINCREMENT,'
				'  clan_id INTEGER NOT NULL,'
				'  sender_user_id INTEGER NOT NULL,'
				'  message TEXT NOT NULL,'
				'  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,'
				'  deleted_at DATETIME,'
				'  deleted_by_user_id INTEGER,'
				'  FOREIGN KEY(clan_id) REFERENCES clans(id),'
				'  FOREIGN KEY(sender_user_id) REFERENCES users(id),'
				'  FOREIGN KEY(deleted_by_user_id) REFERENCES users(id)'
				')'
			)
		)
		conn.execute('CREATE INDEX IF NOT EXISTS idx_clan_messages_clan ON clan_messages(clan_id)')
		conn.commit()

		# Notifications table
		conn.execute(
			(
				'CREATE TABLE IF NOT EXISTS notifications ('
				'  id INTEGER PRIMARY KEY AUTOINCREMENT,'
				'  user_id INTEGER NOT NULL,'
				'  type TEXT NOT NULL,'
				'  title TEXT NOT NULL,'
				'  message TEXT NOT NULL,'
				'  city TEXT,'
				'  payload TEXT,'
				'  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,'
				'  read_at DATETIME,'
				'  FOREIGN KEY(user_id) REFERENCES users(id)'
				')'
			)
		)
		conn.commit()

		# Email OTP table for password reset and username change
		conn.execute(
			(
				'CREATE TABLE IF NOT EXISTS email_otps ('
				'  id INTEGER PRIMARY KEY AUTOINCREMENT,'
				'  email TEXT NOT NULL,'
				'  purpose TEXT NOT NULL,'
				'  code_hash BLOB NOT NULL,'
				'  metadata TEXT,'
				'  attempts INTEGER NOT NULL DEFAULT 0,'
				'  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,'
				'  expires_at DATETIME NOT NULL,'
				'  consumed_at DATETIME'
				')'
			)
		)
		conn.execute('CREATE INDEX IF NOT EXISTS idx_email_otps_email_purpose ON email_otps(email, purpose)')
		conn.commit()


# Ensure database schema exists even when app is imported via WSGI
try:
    init_db()
except Exception as e:
    print(f"init_db on import failed: {e}")


app = Flask(__name__)

# Limit upload size (MB) to mitigate abuse; default 25MB
try:
    app.config['MAX_CONTENT_LENGTH'] = int(os.environ.get('MAX_UPLOAD_MB', '25')) * 1024 * 1024
except Exception:
    app.config['MAX_CONTENT_LENGTH'] = 25 * 1024 * 1024

# CORS configuration from env (CORS_ORIGINS="*") or comma-separated origins
_cors_env = (os.environ.get('CORS_ORIGINS', '*') or '*').strip()
_cors_origins = '*'
if _cors_env != '*':
    _cors_origins = [o.strip() for o in _cors_env.split(',') if o.strip()]
CORS(app, resources={r"/api/*": {"origins": _cors_origins}})

# Serve uploaded files safely from a dedicated directory
_uploads_dir = os.path.join(os.path.dirname(__file__), 'uploads')
@app.route('/uploads/<path:filename>')
def serve_upload(filename: str):
    return send_from_directory(_uploads_dir, filename, as_attachment=False)

# In-memory subscriber registry for SSE notification streams
# Maps username -> set of Queue instances
notification_subscribers: Dict[str, Set[queue.Queue]] = defaultdict(set)


def parse_username_from_auth() -> Optional[str]:
	auth_header = request.headers.get('Authorization', '')
	if not auth_header.startswith('Bearer '):
		return None
	token = auth_header.split(' ', 1)[1]
	if not token.startswith('token_'):
		return None
	return token.replace('token_', '', 1)


def parse_username_from_token_param() -> Optional[str]:
    """Parse username from token in query string (for SSE/EventSource)."""
    token = (request.args.get('token') or '').strip()
    if not token.startswith('token_'):
        return None
    return token.replace('token_', '', 1)


def notify_user(recipient_username: str, payload: Dict[str, Any]) -> None:
    """Push a notification payload to all active SSE subscribers for the user."""
    try:
        subscribers = notification_subscribers.get(recipient_username, set())
        dead_queues = []
        for q in list(subscribers):
            try:
                q.put_nowait(payload)
            except Exception:
                dead_queues.append(q)
        for dq in dead_queues:
            try:
                subscribers.discard(dq)
            except Exception:
                pass
    except Exception as e:
        print(f"notify_user error: {e}")


# ======== Email OTP Helpers ========
def _now() -> datetime:
    return datetime.utcnow()


def _fmt_dt(dt: datetime) -> str:
    return dt.strftime('%Y-%m-%d %H:%M:%S')


def generate_otp_code(length: int = 6) -> str:
    digits = '0123456789'
    return ''.join(random.choice(digits) for _ in range(length))


def store_email_otp(email: str, purpose: str, code_plain: str, metadata: Optional[Dict[str, Any]] = None, ttl_minutes: int = 10) -> None:
    code_hash = bcrypt.hashpw(code_plain.encode('utf-8'), bcrypt.gensalt())
    expires_at = _fmt_dt(_now() + timedelta(minutes=ttl_minutes))
    meta_text = json.dumps(metadata) if metadata else None
    with get_db_connection() as conn:
        # Invalidate older active OTPs for this email & purpose
        try:
            conn.execute(
                'UPDATE email_otps SET consumed_at = CURRENT_TIMESTAMP WHERE email = ? AND purpose = ? AND consumed_at IS NULL AND expires_at > CURRENT_TIMESTAMP',
                (email, purpose)
            )
        except Exception:
            pass
        conn.execute(
            'INSERT INTO email_otps (email, purpose, code_hash, metadata, expires_at) VALUES (?, ?, ?, ?, ?)',
            (email, purpose, code_hash, meta_text, expires_at)
        )
        conn.commit()


def validate_and_consume_email_otp(email: str, purpose: str, code_plain: str) -> Optional[Dict[str, Any]]:
    with get_db_connection() as conn:
        row = conn.execute(
            'SELECT id, code_hash, metadata, attempts, expires_at, consumed_at FROM email_otps WHERE email = ? AND purpose = ? ORDER BY id DESC LIMIT 1',
            (email, purpose)
        ).fetchone()
        if row is None:
            return None
        otp_id, code_hash, metadata_text, attempts, expires_at, consumed_at = row
        if consumed_at is not None:
            return None
        # Expiry check
        try:
            if datetime.strptime(str(expires_at), '%Y-%m-%d %H:%M:%S') < _now():
                return None
        except Exception:
            return None
        # Attempts limit
        if int(attempts or 0) >= 5:
            return None
        # Verify
        ok = False
        try:
            ok = bcrypt.checkpw(code_plain.encode('utf-8'), code_hash)
        except Exception:
            ok = False
        if not ok:
            try:
                conn.execute('UPDATE email_otps SET attempts = attempts + 1 WHERE id = ?', (otp_id,))
                conn.commit()
            except Exception:
                pass
            return None
        # Consume
        conn.execute('UPDATE email_otps SET consumed_at = CURRENT_TIMESTAMP WHERE id = ?', (otp_id,))
        conn.commit()
        try:
            return json.loads(metadata_text) if metadata_text else {}
        except Exception:
            return {}


def send_email_otp(email: str, purpose: str, otp_code: str) -> None:
    """Send OTP via SMTP if configured, else log to console.

    Env vars:
      SMTP_HOST, SMTP_PORT (default 587), SMTP_USER, SMTP_PASS,
      SMTP_TLS (default '1'), MAIL_FROM (default 'no-reply@localhost').
    """
    host = (os.environ.get('SMTP_HOST') or '').strip()
    if not host:
        print(f"[DEV] OTP for {purpose} to {email}: {otp_code}")
        return
    port = int(os.environ.get('SMTP_PORT', '587') or '587')
    user = os.environ.get('SMTP_USER')
    password = os.environ.get('SMTP_PASS')
    use_tls = (os.environ.get('SMTP_TLS', '1') or '1') not in ('0', 'false', 'False')
    from_addr = (os.environ.get('MAIL_FROM') or 'no-reply@localhost').strip()

    msg = EmailMessage()
    msg['Subject'] = f"Your {purpose.replace('_', ' ').title()} OTP"
    msg['From'] = from_addr
    msg['To'] = email
    msg.set_content(
        f"Your one-time code is: {otp_code}\n\n"
        f"This code expires in 10 minutes. If you did not request this, you can ignore this email."
    )

    try:
        with smtplib.SMTP(host, port, timeout=15) as server:
            if use_tls:
                server.starttls()
            if user:
                server.login(user, password or '')
            server.send_message(msg)
        print(f"[SMTP] OTP email sent to {email} for {purpose}")
    except Exception as e:
        print(f"[SMTP] Failed to send OTP email to {email}: {e}. Falling back to console log.")
        print(f"[DEV] OTP for {purpose} to {email}: {otp_code}")


@app.route('/api/health', methods=['GET'])
def health() -> Tuple[Any, int]:
	return jsonify({"status": "ok"}), 200


@app.route('/api/signup', methods=['POST'])
def signup() -> Tuple[Any, int]:
	data: Dict[str, Any] = request.get_json(silent=True) or {}
	username: str = (data.get('username') or '').strip()
	email: str = (data.get('email') or '').strip()
	password: str = (data.get('password') or '').strip()
	country: str = (data.get('country') or '').strip()
	state: str = (data.get('state') or '').strip()
	city: str = (data.get('city') or '').strip()
	district: str = (data.get('district') or '').strip()

	# Email is optional now; keep other fields required
	if not username or not password or not country or not state or not city:
		return jsonify({"error": "username, password, country, state, and city are required"}), 400

	# Minimal email format check (only when provided)
	if email:
		if '@' not in email or '.' not in email.split('@')[-1]:
			return jsonify({"error": "invalid email address"}), 400

	# Hash password
	password_bytes = password.encode('utf-8')
	salt = bcrypt.gensalt()
	password_hash = bcrypt.hashpw(password_bytes, salt)

	try:
		with get_db_connection() as conn:
			# Enforce uniqueness for username and email (when provided)
			existing_u = conn.execute(
				'SELECT 1 FROM users WHERE TRIM(LOWER(username)) = TRIM(LOWER(?))',
				(username,)
			).fetchone()
			if existing_u:
				return jsonify({"error": "username already exists"}), 409

			if email:
				existing_e = conn.execute(
					'SELECT 1 FROM users WHERE TRIM(LOWER(email)) = TRIM(LOWER(?))',
					(email,)
				).fetchone()
				if existing_e:
					return jsonify({"error": "email already exists"}), 409

			# Persist district when provided; otherwise DB default of "Unknown" applies
			# When email omitted, store unique placeholder to satisfy NOT NULL/UNIQUE constraints
			email_to_store = email if email else f"{username.lower()}@noemail.local"
			if district:
				conn.execute(
					'INSERT INTO users (username, email, password_hash, total_points, country, state, city, district) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
					(username, email_to_store, password_hash, 100, country, state, city, district),
				)
			else:
				conn.execute(
					'INSERT INTO users (username, email, password_hash, total_points, country, state, city) VALUES (?, ?, ?, ?, ?, ?, ?)',
					(username, email_to_store, password_hash, 100, country, state, city),
				)
			conn.commit()
	except sqlite3.IntegrityError:
		return jsonify({"error": "username or email already exists"}), 409
	except Exception as e:
		print(f"Database error during signup: {str(e)}")
		return jsonify({"error": f"Database error: {str(e)}"}), 500

	user = {
		"username": username,
		"email": (email or None),
		"total_points": 100,
		"country": country,
		"state": state,
		"city": city,
	}
	# Simple token stub; replace with real JWT/session later
	token = f"token_{username}"

	return jsonify({"user": user, "token": token}), 201


@app.route('/api/login', methods=['POST'])
def login() -> Tuple[Any, int]:
	data: Dict[str, Any] = request.get_json(silent=True) or {}
	# Accept username OR email in the 'username' field (identifier)
	identifier: str = (data.get('username') or '').strip()
	password: str = (data.get('password') or '').strip()

	if not identifier or not password:
		return jsonify({"error": "username/email and password are required"}), 400

	with get_db_connection() as conn:
		try:
			row = conn.execute(
				'SELECT username, email, password_hash, total_points, country, state, city FROM users WHERE TRIM(LOWER(username)) = TRIM(LOWER(?)) OR TRIM(LOWER(email)) = TRIM(LOWER(?))',
				(identifier, identifier),
			).fetchone()
		except sqlite3.OperationalError as e:
			# Backward-compat: fall back to username-only query if email column is missing
			if 'no such column: email' in str(e):
				row = conn.execute(
					'SELECT username, NULL as email, password_hash, total_points, country, state, city FROM users WHERE TRIM(LOWER(username)) = TRIM(LOWER(?))',
					(identifier,),
				).fetchone()
			else:
				raise

	if row is None:
		return jsonify({"error": "invalid credentials"}), 401

	# sqlite3.Row supports key-based access
	stored_hash: bytes = row[2]
	if not bcrypt.checkpw(password.encode('utf-8'), stored_hash):
		return jsonify({"error": "invalid credentials"}), 401

	user = {
		"username": row[0],
		"email": row[1],
		"total_points": row[3],
		"country": row[4],
		"state": row[5],
		"city": row[6],
	}
	# Issue token bound to actual username to keep auth consistent
	token = f"token_{row[0]}"

	return jsonify({"user": user, "token": token}), 200


# ======== Username change (email OTP) ========
@app.route('/api/request_username_change', methods=['POST'])
def request_username_change() -> Tuple[Any, int]:
    data: Dict[str, Any] = request.get_json(silent=True) or {}
    email: str = (data.get('email') or '').strip()
    new_username: str = (data.get('new_username') or '').strip()
    if not email or not new_username:
        return jsonify({"error": "email and new_username are required"}), 400
    with get_db_connection() as conn:
        row = conn.execute('SELECT username FROM users WHERE TRIM(LOWER(email)) = TRIM(LOWER(?))', (email,)).fetchone()
        if row is None:
            # Do not reveal existence
            return jsonify({"message": "If the email exists, an OTP has been sent."}), 200
        exists = conn.execute('SELECT 1 FROM users WHERE TRIM(LOWER(username)) = TRIM(LOWER(?))', (new_username,)).fetchone()
        if exists:
            return jsonify({"error": "username already exists"}), 409
    otp = generate_otp_code(6)
    store_email_otp(email=email, purpose='change_username', code_plain=otp, metadata={"new_username": new_username}, ttl_minutes=10)
    send_email_otp(email, 'change_username', otp)
    resp = {"message": "OTP sent to email for username change"}
    if os.environ.get('DEV_MODE_OTP') == '1':
        resp['dev_otp'] = otp
    return jsonify(resp), 200


@app.route('/api/confirm_username_change', methods=['POST'])
def confirm_username_change() -> Tuple[Any, int]:
    data: Dict[str, Any] = request.get_json(silent=True) or {}
    email: str = (data.get('email') or '').strip()
    otp: str = (data.get('otp') or '').strip()
    if not email or not otp:
        return jsonify({"error": "email and otp are required"}), 400
    meta = validate_and_consume_email_otp(email=email, purpose='change_username', code_plain=otp)
    if meta is None:
        return jsonify({"error": "invalid or expired otp"}), 400
    new_username = (meta.get('new_username') or '').strip()
    if not new_username:
        return jsonify({"error": "invalid request"}), 400
    with get_db_connection() as conn:
        row = conn.execute('SELECT username, email, total_points, country, state, city FROM users WHERE TRIM(LOWER(email)) = TRIM(LOWER(?))', (email,)).fetchone()
        if row is None:
            return jsonify({"error": "user not found"}), 404
        exists = conn.execute('SELECT 1 FROM users WHERE TRIM(LOWER(username)) = TRIM(LOWER(?))', (new_username,)).fetchone()
        if exists:
            return jsonify({"error": "username already exists"}), 409
        conn.execute('UPDATE users SET username = ? WHERE TRIM(LOWER(email)) = TRIM(LOWER(?))', (new_username, email))
        conn.commit()
        user = {
            "username": new_username,
            "email": row[1],
            "total_points": row[2],
            "country": row[3],
            "state": row[4],
            "city": row[5],
        }
    token = f"token_{new_username}"
    return jsonify({"message": "username updated", "user": user, "token": token}), 200


# ======== Password reset (email OTP) ========
@app.route('/api/request_password_reset', methods=['POST'])
def request_password_reset() -> Tuple[Any, int]:
    data: Dict[str, Any] = request.get_json(silent=True) or {}
    email: str = (data.get('email') or '').strip()
    if not email:
        return jsonify({"error": "email is required"}), 400
    if '@' not in email or '.' not in email.split('@')[-1]:
        return jsonify({"error": "invalid email address"}), 400
    with get_db_connection() as conn:
        row = conn.execute('SELECT 1 FROM users WHERE TRIM(LOWER(email)) = TRIM(LOWER(?))', (email,)).fetchone()
    if row is not None:
        otp = generate_otp_code(6)
        store_email_otp(email=email, purpose='reset_password', code_plain=otp, metadata=None, ttl_minutes=10)
        send_email_otp(email, 'reset_password', otp)
    resp = {"message": "If the email exists, an OTP has been sent."}
    if os.environ.get('DEV_MODE_OTP') == '1' and row is not None:
        resp['dev_otp'] = otp
    return jsonify(resp), 200


@app.route('/api/reset_password', methods=['POST'])
def reset_password() -> Tuple[Any, int]:
    data: Dict[str, Any] = request.get_json(silent=True) or {}
    email: str = (data.get('email') or '').strip()
    otp: str = (data.get('otp') or '').strip()
    new_password: str = (data.get('new_password') or '').strip()
    if not email or not otp or not new_password:
        return jsonify({"error": "email, otp, and new_password are required"}), 400
    if len(new_password) < 6:
        return jsonify({"error": "password must be at least 6 characters"}), 400
    meta = validate_and_consume_email_otp(email=email, purpose='reset_password', code_plain=otp)
    if meta is None:
        return jsonify({"error": "invalid or expired otp"}), 400
    password_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
    with get_db_connection() as conn:
        conn.execute('UPDATE users SET password_hash = ? WHERE TRIM(LOWER(email)) = TRIM(LOWER(?))', (password_hash, email))
        conn.commit()
    return jsonify({"message": "password reset successful"}), 200

@app.route('/api/me', methods=['GET'])
def me() -> Tuple[Any, int]:
	"""
	Return the authenticated user's profile with location fields
	"""
	username = parse_username_from_auth()
	if not username:
		return jsonify({"error": "unauthorized"}), 401
	with get_db_connection() as conn:
		row = conn.execute(
			'SELECT username, email, total_points, country, state, city, district FROM users WHERE username = ?',
			(username,),
		).fetchone()
		if row is None:
			return jsonify({"error": "user not found"}), 404
		user = {
			"username": row[0],
			"email": row[1],
			"total_points": row[2],
			"country": row[3],
			"state": row[4],
			"city": row[5],
			"district": row[6],
		}
	return jsonify({"user": user}), 200


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


@app.route('/api/create_bounty', methods=['POST'])
def create_bounty() -> Tuple[Any, int]:
	"""
	Create a new waste bounty from a geotagged photo
	"""
	username = parse_username_from_auth()
	if not username:
		return jsonify({"error": "missing auth token"}), 401

	if 'bounty_report_photo' not in request.files:
		return jsonify({"error": "no photo uploaded"}), 400
	
	file = request.files['bounty_report_photo']
	if file.filename == '':
		return jsonify({"error": "empty filename"}), 400

	# Read file bytes
	file_bytes = file.read()
	
	# Extract GPS coordinates from image
	latitude, longitude = extract_gps_from_image(file_bytes)
	
	# If no GPS in photo, check if location data was provided in form
	if latitude is None or longitude is None:
		latitude_str = request.form.get('latitude')
		longitude_str = request.form.get('longitude')
		
		if latitude_str and longitude_str:
			try:
				latitude = float(latitude_str)
				longitude = float(longitude_str)
				print(f"Using provided location: {latitude}, {longitude}")
			except ValueError:
				return jsonify({"error": "Invalid location data provided"}), 400
		else:
			return jsonify({"error": "Photo must contain valid GPS location data. Please enable location services and take a new photo."}), 400
	
	# Reverse geocode to get address components
	address_data = reverse_geocode(latitude, longitude)
	if not address_data:
		# Fallback: use provided location data or default values
		address_data = {
			'country': request.form.get('country', 'India'),
			'state': request.form.get('state', 'Maharashtra'),
			'city': request.form.get('city', 'Unknown')
		}
		print(f"Using fallback location data: {address_data}")
	else:
		print(f"Reverse geocoding successful: {address_data}")
	
	# Get user info
	with get_db_connection() as conn:
		row = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
		if row is None:
			return jsonify({"error": "user not found"}), 404
		user_id = int(row[0])
	
	# Save image to a temporary location (in production, use cloud storage)
	image_filename = f"bounty_{user_id}_{int(time.time())}.jpg"
	image_path = os.path.join(os.path.dirname(__file__), 'uploads', image_filename)
	
	# Create uploads directory if it doesn't exist
	os.makedirs(os.path.dirname(image_path), exist_ok=True)
	
	with open(image_path, 'wb') as f:
		f.write(file_bytes)
	
	# Validate with Gemini that the photo shows a public waste area
	# Decode the saved image for analysis
	np_arr = np.frombuffer(file_bytes, np.uint8)
	image_cv = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
	gemini_result = analyze_with_gemini(image_cv) if image_cv is not None else {"items": []}
	items = gemini_result.get("items", [])
	if not items:
		return jsonify({"error": "Image does not appear to show a waste area. Please capture a clear scene with visible waste in a public place."}), 400

	# Prevent duplicate bounties for the same coordinates (within ~20m)
	with get_db_connection() as conn:
		rows = conn.execute(
			'SELECT id, latitude, longitude FROM waste_bounty WHERE status = "REPORTED" AND TRIM(LOWER(city)) = TRIM(LOWER(?))',
			(address_data['city'],)
		).fetchall()
		for r in rows:
			existing_lat, existing_lon = float(r[1]), float(r[2])
			if calculate_distance(existing_lat, existing_lon, latitude, longitude) <= 20:
				return jsonify({"error": "Bounty is already raised for this location."}), 409

	# Create bounty record
	with get_db_connection() as conn:
		conn.execute(
			'INSERT INTO waste_bounty (reporter_user_id, latitude, longitude, country, state, city, waste_image_url) VALUES (?, ?, ?, ?, ?, ?, ?)',
			(user_id, latitude, longitude, address_data['country'], address_data['state'], address_data['city'], f"/uploads/{image_filename}")
		)
		conn.commit()

	# Fan-out notification to users in the same city (excluding reporter)
	try:
		with get_db_connection() as conn:
			rows = conn.execute(
				'SELECT username FROM users WHERE TRIM(LOWER(country)) = TRIM(LOWER(?)) AND TRIM(LOWER(state)) = TRIM(LOWER(?)) AND TRIM(LOWER(city)) = TRIM(LOWER(?)) AND username <> ?',
				(address_data['country'], address_data['state'], address_data['city'], username)
			).fetchall()
			# Persist notifications and push to SSE subscribers
			for r in rows:
				recipient = r[0]
				# Persist
				user_row = conn.execute('SELECT id FROM users WHERE username = ?', (recipient,)).fetchone()
				if user_row is None:
					continue
				recipient_id = int(user_row[0])
				payload = {
					"kind": "BOUNTY_CREATED",
					"city": address_data['city'],
					"state": address_data['state'],
					"country": address_data['country'],
					"latitude": latitude,
					"longitude": longitude,
					"image_url": f"/uploads/{image_filename}"
				}
				conn.execute(
					'INSERT INTO notifications (user_id, type, title, message, city, payload) VALUES (?, ?, ?, ?, ?, ?)',
					(
						recipient_id,
						'BOUNTY_CREATED',
						'New bounty in your city',
						f"New waste bounty reported in {address_data['city']}, {address_data['state']}",
						address_data['city'],
						json.dumps(payload)
					)
				)
				# Push to live subscribers
				notify_user(recipient, {
					"id": None,
					"type": "BOUNTY_CREATED",
					"title": "New bounty in your city",
					"message": f"New waste bounty reported in {address_data['city']}, {address_data['state']}",
					"city": address_data['city'],
					"payload": payload,
					"created_at": time.strftime('%Y-%m-%d %H:%M:%S')
				})
			conn.commit()
	except Exception as e:
		print(f"Notification fan-out error: {e}")
	
	return jsonify({
		"message": "Bounty created successfully",
		"location": {
			"latitude": latitude,
			"longitude": longitude,
			"country": address_data['country'],
			"state": address_data['state'],
			"city": address_data['city']
		}
	}), 201


@app.route('/api/bounties', methods=['GET'])
def get_bounties() -> Tuple[Any, int]:
	"""
	Get active bounties for the user's location
	"""
	username = parse_username_from_auth()
	if not username:
		return jsonify({"error": "missing auth token"}), 401

	# Get user's location
	with get_db_connection() as conn:
		row = conn.execute('SELECT country, state, city FROM users WHERE username = ?', (username,)).fetchone()
		if row is None:
			return jsonify({"error": "user not found"}), 404
		user_country, user_state, user_city = row[0], row[1], row[2]
	
	# Get active bounties strictly in user's city
	with get_db_connection() as conn:
		rows = conn.execute(
			'SELECT '\
			'  b.id, b.latitude, b.longitude, b.country, b.state, b.city, '\
			'  b.bounty_points, b.waste_image_url, b.created_at, b.before_image_url, b.after_image_url, '\
			'  u.username AS reporter_username '\
			'FROM waste_bounty b '\
			'JOIN users u ON u.id = b.reporter_user_id '\
			'WHERE b.status = "REPORTED" '\
			'  AND TRIM(LOWER(b.country)) = TRIM(LOWER(?)) '\
			'  AND TRIM(LOWER(b.state)) = TRIM(LOWER(?)) '\
			'  AND TRIM(LOWER(b.city)) = TRIM(LOWER(?)) '\
			'ORDER BY b.created_at DESC',
			(user_country, user_state, user_city)
		).fetchall()
		print(f"Found {len(rows)} bounties for user city: {user_city}")
		
		bounties = []
		for row in rows:
			bounties.append({
				"id": row[0],
				"latitude": row[1],
				"longitude": row[2],
				"country": row[3],
				"state": row[4],
				"city": row[5],
				"bounty_points": row[6],
				"waste_image_url": row[7],
				"created_at": row[8],
				"before_image_url": row[9],
				"after_image_url": row[10],
				"reporter_username": row[11]
			})
	
	return jsonify({"bounties": bounties}), 200


@app.route('/api/bounty_chat', methods=['GET'])
def get_bounty_chat():
    """Get chat messages for a bounty; only same-city users can read."""
    username = parse_username_from_auth()
    if not username:
        return jsonify({"error": "unauthorized"}), 401
    bounty_id = request.args.get('bounty_id')
    if not bounty_id:
        return jsonify({"error": "bounty_id is required"}), 400
    try:
        bounty_id_int = int(bounty_id)
    except ValueError:
        return jsonify({"error": "invalid bounty_id"}), 400

    with get_db_connection() as conn:
        user_row = conn.execute('SELECT id, city FROM users WHERE username = ?', (username,)).fetchone()
        if user_row is None:
            return jsonify({"error": "user not found"}), 404
        user_id = int(user_row[0])
        user_city = str(user_row[1])

        b_row = conn.execute('SELECT city FROM waste_bounty WHERE id = ?', (bounty_id_int,)).fetchone()
        if b_row is None:
            return jsonify({"error": "bounty not found"}), 404
        bounty_city = str(b_row[0])

        if user_city.strip().lower() != bounty_city.strip().lower():
            return jsonify({"error": "forbidden: different city"}), 403

        rows = conn.execute(
            'SELECT m.id, u.username, m.message, m.created_at '\
            'FROM bounty_chat_messages m JOIN users u ON u.id = m.sender_user_id '\
            'WHERE m.bounty_id = ? AND m.deleted_at IS NULL ORDER BY m.id ASC',
            (bounty_id_int,)
        ).fetchall()

        messages = []
        for r in rows:
            messages.append({
                'id': r[0],
                'sender_username': r[1],
                'message': r[2],
                'created_at': r[3]
            })

    return jsonify({"messages": messages}), 200


@app.route('/api/bounty_chat', methods=['POST'])
def post_bounty_chat():
    """Post a chat message to a bounty; must be in same city; bounty must be open."""
    username = parse_username_from_auth()
    if not username:
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    bounty_id = data.get('bounty_id')
    message_text = (data.get('message') or '').strip()
    if not bounty_id or not message_text:
        return jsonify({"error": "bounty_id and message are required"}), 400
    if len(message_text) > 1000:
        return jsonify({"error": "message too long"}), 400
    try:
        bounty_id_int = int(bounty_id)
    except (ValueError, TypeError):
        return jsonify({"error": "invalid bounty_id"}), 400

    with get_db_connection() as conn:
        user_row = conn.execute('SELECT id, city FROM users WHERE username = ?', (username,)).fetchone()
        if user_row is None:
            return jsonify({"error": "user not found"}), 404
        user_id = int(user_row[0])
        user_city = str(user_row[1])

        b_row = conn.execute('SELECT city, status FROM waste_bounty WHERE id = ?', (bounty_id_int,)).fetchone()
        if b_row is None:
            return jsonify({"error": "bounty not found"}), 404
        bounty_city, bounty_status = str(b_row[0]), str(b_row[1])

        if user_city.strip().lower() != bounty_city.strip().lower():
            return jsonify({"error": "forbidden: different city"}), 403
        if bounty_status != 'REPORTED':
            return jsonify({"error": "chat closed for this bounty"}), 400

        conn.execute(
            'INSERT INTO bounty_chat_messages (bounty_id, sender_user_id, message, city) VALUES (?, ?, ?, ?)',
            (bounty_id_int, user_id, message_text, bounty_city)
        )
        conn.commit()

        row = conn.execute(
            'SELECT id, ? as username, message, created_at FROM bounty_chat_messages WHERE id = last_insert_rowid()',
            (username,)
        ).fetchone()

    created = {
        'id': row[0],
        'sender_username': row[1],
        'message': row[2],
        'created_at': row[3]
    }
    return jsonify({"message": created}), 201


@app.route('/api/bounty_chat/<int:message_id>', methods=['DELETE'])
def delete_bounty_chat(message_id: int):
    """Delete a chat message. Allowed for bounty raiser or the message sender."""
    username = parse_username_from_auth()
    if not username:
        return jsonify({"error": "unauthorized"}), 401

    with get_db_connection() as conn:
        urow = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
        if urow is None:
            return jsonify({"error": "user not found"}), 404
        current_user_id = int(urow[0])

        row = conn.execute(
            'SELECT m.bounty_id, m.sender_user_id, b.reporter_user_id '
            'FROM bounty_chat_messages m JOIN waste_bounty b ON b.id = m.bounty_id '
            'WHERE m.id = ?', (message_id,)
        ).fetchone()
        if row is None:
            return jsonify({"error": "message not found"}), 404
        bounty_id, sender_user_id, reporter_user_id = int(row[0]), int(row[1]), int(row[2])

        if current_user_id not in (reporter_user_id, sender_user_id):
            return jsonify({"error": "forbidden"}), 403

        conn.execute(
            'UPDATE bounty_chat_messages SET deleted_at = CURRENT_TIMESTAMP, deleted_by_user_id = ? WHERE id = ?',
            (current_user_id, message_id)
        )
        conn.commit()

    return jsonify({"status": "ok"}), 200
@app.route('/api/notifications', methods=['GET'])
def list_notifications() -> Tuple[Any, int]:
    """List recent notifications for the authenticated user."""
    username = parse_username_from_auth()
    if not username:
        return jsonify({"error": "unauthorized"}), 401
    limit = int(request.args.get('limit', '50'))
    with get_db_connection() as conn:
        row = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
        if row is None:
            return jsonify({"error": "user not found"}), 404
        user_id = int(row[0])
        rows = conn.execute(
            'SELECT id, type, title, message, city, payload, created_at, read_at FROM notifications WHERE user_id = ? ORDER BY id DESC LIMIT ?',
            (user_id, limit)
        ).fetchall()
        notifications = []
        for r in rows:
            notifications.append({
                'id': r[0],
                'type': r[1],
                'title': r[2],
                'message': r[3],
                'city': r[4],
                'payload': json.loads(r[5]) if r[5] else None,
                'created_at': r[6],
                'read_at': r[7]
            })
    return jsonify({"notifications": notifications}), 200


@app.route('/api/notifications/read', methods=['POST'])
def mark_notifications_read() -> Tuple[Any, int]:
    """Mark notifications as read. Pass { ids: number[] } or mark all via all=true."""
    username = parse_username_from_auth()
    if not username:
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    ids = data.get('ids') or []
    mark_all = bool(data.get('all'))
    with get_db_connection() as conn:
        row = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
        if row is None:
            return jsonify({"error": "user not found"}), 404
        user_id = int(row[0])
        if mark_all:
            conn.execute('UPDATE notifications SET read_at = CURRENT_TIMESTAMP WHERE user_id = ? AND read_at IS NULL', (user_id,))
        elif ids:
            # Build dynamic placeholders for ids
            placeholders = ','.join(['?'] * len(ids))
            conn.execute(f'UPDATE notifications SET read_at = CURRENT_TIMESTAMP WHERE user_id = ? AND id IN ({placeholders})', (user_id, *ids))
        else:
            return jsonify({"error": "no ids provided"}), 400
        conn.commit()
    return jsonify({"status": "ok"}), 200


@app.route('/api/notifications/stream')
def notifications_stream():
    """Server-Sent Events stream for real-time user notifications."""
    # For SSE we accept token as query param due to EventSource limitations
    username = parse_username_from_token_param()
    if not username:
        return jsonify({"error": "unauthorized"}), 401

    # Validate user exists before opening stream
    try:
        with get_db_connection() as conn:
            row = conn.execute('SELECT 1 FROM users WHERE username = ?', (username,)).fetchone()
            if row is None:
                return jsonify({"error": "user not found"}), 404
    except Exception:
        return jsonify({"error": "unauthorized"}), 401

    q: queue.Queue = queue.Queue()
    notification_subscribers[username].add(q)

    def gen():
        try:
            # Send an initial comment to establish the stream
            yield ': connected\n\n'
            while True:
                payload = q.get()
                data = json.dumps(payload)
                yield f'data: {data}\n\n'
        except GeneratorExit:
            pass
        finally:
            try:
                notification_subscribers[username].discard(q)
            except Exception:
                pass

    headers = {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'X-Accel-Buffering': 'no'  # for some proxies
    }
    return Response(gen(), headers=headers)


def verify_cleanup_with_gemini(original_image: np.ndarray, before_image: np.ndarray, after_image: np.ndarray) -> Dict[str, Any]:
	"""
	Verify cleanup using Gemini API with the exact prompt specified
	"""
	if not GEMINI_API_KEY or genai is None:
		return {
			"error": "Gemini API key not configured",
			"scene_match": False,
			"waste_present_before": False,
			"cleanup_verified": False,
			"fallback": True
		}
	
	try:
		# Convert OpenCV images to PIL Images
		images = []
		for img in [original_image, before_image, after_image]:
			image_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
			pil_image = Image.fromarray(image_rgb)
			images.append(pil_image)
		
		# Initialize Gemini model
		model = genai.GenerativeModel('gemini-2.0-flash')
		
		# Use the enhanced prompt for comprehensive waste detection
		prompt = """Analyze this sequence of three images for cleanup verification: Image 1 (Original Report Photo), Image 2 (User's Before Cleanup), and Image 3 (User's After Cleanup). GPS has confirmed Image 2 and 3 are at the correct location.

Scene Match: Based on static background features (e.g., walls, trees, unique objects, water bodies, landscape), confirm if Image 2 and Image 3 show the exact same scene/viewpoint (excluding the garbage itself). (Respond with: scene_match: true/false).

Waste Verification: Is there significant garbage, waste, or pollution visible in Image 2? This includes:
- Plastic waste, bottles, bags, containers
- Organic waste, food scraps, leaves
- Construction debris, rubble, materials
- Floating waste in water bodies (rivers, canals, lakes)
- Scattered debris in public spaces (parks, streets, markets)
- Industrial waste, metal scraps, hazardous materials
- Any visible pollution or environmental degradation

Cleanup Result: Is the garbage, waste, or pollution visible in Image 2 now absent, removed, or significantly reduced in Image 3? Look for:
- Complete removal of waste materials
- Significant reduction in pollution levels
- Restoration of clean appearance
- Improvement in environmental condition

Respond with a JSON object: {'scene_match': [true/false], 'waste_present_before': [true/false], 'cleanup_verified': [true/false]}."""
		
		# Generate response
		response = model.generate_content([prompt] + images)
		
		if not response or not response.text:
			return {
				"error": "Empty response from Gemini API",
				"scene_match": False,
				"waste_present_before": False,
				"cleanup_verified": False,
				"fallback": True
			}
		
		# Parse JSON response
		response_text = response.text.strip()
		
		# Try to extract JSON from response
		json_text = None
		if '```json' in response_text:
			json_start = response_text.find('```json') + 7
			json_end = response_text.find('```', json_start)
			json_text = response_text[json_start:json_end].strip()
		elif '{' in response_text and '}' in response_text:
			json_start = response_text.find('{')
			json_end = response_text.rfind('}') + 1
			json_text = response_text[json_start:json_end]
		
		if not json_text:
			return {
				"scene_match": False,
				"waste_present_before": False,
				"cleanup_verified": False,
				"fallback": False,
				"raw_response": response_text
			}
		
		try:
			result = json.loads(json_text)
		except json.JSONDecodeError:
			return {
				"scene_match": False,
				"waste_present_before": False,
				"cleanup_verified": False,
				"fallback": False,
				"raw_response": response_text
			}
		
		# Ensure required keys exist
		if "scene_match" not in result:
			result["scene_match"] = False
		if "waste_present_before" not in result:
			result["waste_present_before"] = False
		if "cleanup_verified" not in result:
			result["cleanup_verified"] = False
		
		return result
		
	except Exception as e:
		print(f"Gemini cleanup verification error: {str(e)}")
		return {
			"error": f"Gemini cleanup verification failed: {str(e)}",
			"scene_match": False,
			"waste_present_before": False,
			"cleanup_verified": False,
			"fallback": True
		}


@app.route('/api/verify_cleanup', methods=['POST'])
def verify_cleanup() -> Tuple[Any, int]:
	"""
	Verify cleanup submission with GPS validation and Gemini AI analysis
	"""
	username = parse_username_from_auth()
	if not username:
		return jsonify({"error": "missing auth token"}), 401

	# Get bounty ID from form data
	bounty_id = request.form.get('bounty_id')
	if not bounty_id:
		return jsonify({"error": "bounty_id is required"}), 400

	# Check for required files
	if 'before_cleanup_photo' not in request.files or 'after_cleanup_photo' not in request.files:
		return jsonify({"error": "both before and after cleanup photos are required"}), 400
	
	before_file = request.files['before_cleanup_photo']
	after_file = request.files['after_cleanup_photo']
	
	if before_file.filename == '' or after_file.filename == '':
		return jsonify({"error": "empty filenames"}), 400

	# Read and persist files (ensure both are saved correctly)
	before_bytes = before_file.read()
	after_bytes = after_file.read()

	# Create uploads directory
	uploads_dir = os.path.join(os.path.dirname(__file__), 'uploads')
	os.makedirs(uploads_dir, exist_ok=True)

	# Build filenames
	before_filename = f"before_{int(time.time())}.jpg"
	after_filename = f"after_{int(time.time())}.jpg"
	before_path = os.path.join(uploads_dir, before_filename)
	after_path = os.path.join(uploads_dir, after_filename)

	# Save both images to disk
	with open(before_path, 'wb') as f:
		f.write(before_bytes)
	with open(after_path, 'wb') as f:
		f.write(after_bytes)
	
	# Extract GPS coordinates from both photos
	before_lat, before_lon = extract_gps_from_image(before_bytes)
	after_lat, after_lon = extract_gps_from_image(after_bytes)

	# Fallback to provided coordinates if EXIF missing
	if before_lat is None or before_lon is None:
		before_lat_str = request.form.get('before_latitude')
		before_lon_str = request.form.get('before_longitude')
		if before_lat_str and before_lon_str:
			try:
				before_lat = float(before_lat_str)
				before_lon = float(before_lon_str)
			except ValueError:
				return jsonify({"error": "Invalid before photo GPS data provided"}), 400

	if after_lat is None or after_lon is None:
		after_lat_str = request.form.get('after_latitude')
		after_lon_str = request.form.get('after_longitude')
		if after_lat_str and after_lon_str:
			try:
				after_lat = float(after_lat_str)
				after_lon = float(after_lon_str)
			except ValueError:
				return jsonify({"error": "Invalid after photo GPS data provided"}), 400
	
	if before_lat is None or before_lon is None:
		return jsonify({"error": "Before cleanup photo must contain valid GPS location data"}), 400
	
	if after_lat is None or after_lon is None:
		return jsonify({"error": "After cleanup photo must contain valid GPS location data"}), 400
	
	# Get bounty information
	with get_db_connection() as conn:
		row = conn.execute('SELECT latitude, longitude, waste_image_url, status FROM waste_bounty WHERE id = ?', (bounty_id,)).fetchone()
		if row is None:
			return jsonify({"error": "bounty not found"}), 404
		
		bounty_lat, bounty_lon, original_image_url, status = row[0], row[1], row[2], row[3]
		
		if status != 'REPORTED':
			return jsonify({"error": "bounty is no longer available"}), 400
	
	# Validate GPS coordinates are within 5-10 meter radius
	before_distance = calculate_distance(bounty_lat, bounty_lon, before_lat, before_lon)
	after_distance = calculate_distance(bounty_lat, bounty_lon, after_lat, after_lon)
	
	if before_distance > 10 or after_distance > 10:
		return jsonify({
			"error": f"Photos must be taken within 10 meters of the bounty location. Before: {before_distance:.1f}m, After: {after_distance:.1f}m"
		}), 400
	
	# Load original image for comparison
	original_image_path = os.path.join(os.path.dirname(__file__), original_image_url.lstrip('/'))
	if not os.path.exists(original_image_path):
		return jsonify({"error": "original bounty image not found"}), 500
	
	# Optional: Development/testing mode to bypass Gemini scene check (server-controlled only)
	dev_mode = (os.environ.get('DEV_MODE_CLEANUP') == '1')
	if dev_mode:
		# Directly approve if GPS validation passed; persist image URLs and award points
		with get_db_connection() as conn:
			row = conn.execute('SELECT id, total_points FROM users WHERE username = ?', (username,)).fetchone()
			if row is None:
				return jsonify({"error": "user not found"}), 404
			user_id, current_points = int(row[0]), int(row[1])

			bounty_row = conn.execute('SELECT bounty_points FROM waste_bounty WHERE id = ?', (bounty_id,)).fetchone()
			bounty_points = int(bounty_row[0]) if bounty_row else 200

			conn.execute(
				'UPDATE waste_bounty SET status = "CLOSED", claimed_by_user_id = ?, claimed_at = CURRENT_TIMESTAMP, completed_at = CURRENT_TIMESTAMP, before_image_url = ?, after_image_url = ? WHERE id = ?',
				(user_id, f"/uploads/{before_filename}", f"/uploads/{after_filename}", bounty_id)
			)
			new_total = current_points + bounty_points
			conn.execute('UPDATE users SET total_points = ? WHERE id = ?', (new_total, user_id))
			conn.execute('INSERT INTO transactions (user_id, points_change, reason) VALUES (?, ?, ?)', (user_id, bounty_points, f'DEV MODE: Bounty Cleanup Completed - Bounty #{bounty_id}'))
			conn.commit()

		return jsonify({
			"message": "Cleanup verified (DEV MODE)",
			"points_awarded": bounty_points,
			"total_points": new_total,
			"dev_mode": True
		}), 200

	# Convert images to OpenCV format for Gemini analysis
	original_image = cv2.imread(original_image_path)
	before_image = cv2.imread(before_path)
	after_image = cv2.imread(after_path)
	
	# Verify cleanup with Gemini AI
	verification_result = verify_cleanup_with_gemini(original_image, before_image, after_image)
	
	# Check if all three conditions are met
	scene_match = verification_result.get("scene_match", False)
	waste_present_before = verification_result.get("waste_present_before", False)
	cleanup_verified = verification_result.get("cleanup_verified", False)
	
	# Get user info
	with get_db_connection() as conn:
		row = conn.execute('SELECT id, total_points FROM users WHERE username = ?', (username,)).fetchone()
		if row is None:
			return jsonify({"error": "user not found"}), 404
		user_id, current_points = int(row[0]), int(row[1])
	
	# Process verification result
	if scene_match and waste_present_before and cleanup_verified:
		# Cleanup approved - update bounty and award points
		with get_db_connection() as conn:
			# Get bounty points
			bounty_row = conn.execute('SELECT bounty_points FROM waste_bounty WHERE id = ?', (bounty_id,)).fetchone()
			bounty_points = int(bounty_row[0]) if bounty_row else 200
			
			# Update bounty status and persist image URLs
			conn.execute(
				'UPDATE waste_bounty SET status = "CLOSED", claimed_by_user_id = ?, claimed_at = CURRENT_TIMESTAMP, completed_at = CURRENT_TIMESTAMP, before_image_url = ?, after_image_url = ? WHERE id = ?',
				(user_id, f"/uploads/{before_filename}", f"/uploads/{after_filename}", bounty_id)
			)
			
			# Award points to user
			new_total = current_points + bounty_points
			conn.execute('UPDATE users SET total_points = ? WHERE id = ?', (new_total, user_id))
			conn.execute('INSERT INTO transactions (user_id, points_change, reason) VALUES (?, ?, ?)', (user_id, bounty_points, f'Bounty Cleanup Completed - Bounty #{bounty_id}'))
			conn.commit()
		
		return jsonify({
			"message": "Cleanup verified successfully! Points awarded.",
			"points_awarded": bounty_points,
			"total_points": new_total,
			"verification_result": verification_result
		}), 200
	else:
		# Cleanup not approved
		reasons = []
		if not scene_match:
			reasons.append("Scene mismatch - photos don't show the same location")
		if not waste_present_before:
			reasons.append("No significant waste detected in before photo")
		if not cleanup_verified:
			reasons.append("Cleanup not verified - waste still present in after photo")
		
		return jsonify({
			"message": "Cleanup verification failed",
			"reasons": reasons,
			"verification_result": verification_result
		}), 400


@app.route('/api/detect', methods=['POST'])
def detect() -> Tuple[Any, int]:
	username = parse_username_from_auth()
	if not username:
		return jsonify({"error": "missing auth token"}), 401

	# Get input type from form data
	input_type = request.form.get('input_type', 'photo')
	
	# Determine which file field to use based on input type
	file_field = None
	if input_type == 'photo':
		file_field = 'photo_file'
	elif input_type == 'video_gallery':
		file_field = 'video_gallery_file'
	elif input_type == 'video_camera':
		file_field = 'video_camera_file'
	else:
		return jsonify({"error": "invalid input type"}), 400

	if file_field not in request.files:
		return jsonify({"error": f"no {file_field} uploaded"}), 400
	file = request.files[file_field]
	if file.filename == '':
		return jsonify({"error": "empty filename"}), 400

	# Read file bytes
	file_bytes = file.read()
	
	# Process based on input type
	if input_type == 'photo':
		# Process as image
		np_arr = np.frombuffer(file_bytes, np.uint8)
		image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
		if image is None:
			return jsonify({"error": "invalid image"}), 400
		
		# Generate image hash for duplicate detection
		file_hash = generate_image_hash(file_bytes)
		
		# Use existing image analysis
		gemini_result = analyze_with_gemini(image)
		gemini_categorized = categorize_gemini_items(gemini_result)
		gemini_available = not gemini_result.get("fallback", False)
		
		# Extract item names for signature and points calculation
		all_detected_items = []
		recyclable_items = []
		hazardous_items = []
		general_items = []
		
		for item in gemini_result.get("items", []):
			item_name = item.get("name", "Unknown item")
			all_detected_items.append(item_name)
			
			category = item.get("category", "general").lower()
			if category == "recyclable":
				recyclable_items.append(item_name)
			elif category == "hazardous":
				hazardous_items.append(item_name)
			else:
				general_items.append(item_name)

		# Build a signature of all detected items to prevent repeat spamming
		detection_signature = ','.join(sorted(all_detected_items)) if all_detected_items else ''

		# Points awarding logic based on Gemini classification
		awarded_points = 0
		message = ''
		if recyclable_items or hazardous_items:
			awarded_points = POINTS_PER_DETECTION * len(set(recyclable_items) | set(hazardous_items))
			message = 'Recyclable/Hazardous waste detected. Points awarded.'
		elif all_detected_items:
			awarded_points = NON_RECYCLABLE_FLAT_POINTS
			message = 'Waste detected. Flat points awarded.'
		else:
			message = 'No waste detected.'
		
		# Check for duplicates and update database
		duplicate = False
		with get_db_connection() as conn:
			row = conn.execute('SELECT id, total_points FROM users WHERE username = ?', (username,)).fetchone()
			if row is None:
				return jsonify({"error": "user not found"}), 404
			user_id = int(row[0])
			current_total = int(row[1])

			# Check if this image hash already exists for this user
			existing_hash = conn.execute(
				'SELECT id FROM image_hashes WHERE user_id = ? AND image_hash = ?', 
				(user_id, file_hash)
			).fetchone()

			if existing_hash:
				duplicate = True
				new_total = current_total
				message = 'This exact image has already been analyzed. No additional points awarded.'
			else:
				# Store the image hash and award points
				new_total = current_total + awarded_points
				conn.execute('UPDATE users SET total_points = ? WHERE id = ?', (new_total, user_id))
				conn.execute('INSERT INTO image_hashes (user_id, image_hash) VALUES (?, ?)', (user_id, file_hash))
				if awarded_points != 0:
					conn.execute('INSERT INTO transactions (user_id, points_change, reason) VALUES (?, ?, ?)', (user_id, awarded_points, 'Waste Detected'))
					conn.execute('UPDATE stats SET detections = detections + 1 WHERE id = 1')
				conn.commit()

		# Response with Gemini-only results
		response = {
			"detected_items": sorted(all_detected_items),
			"recyclable_items": sorted(recyclable_items),
			"hazardous_items": sorted(hazardous_items),
			"general_items": sorted(general_items),
			"awarded_points": 0 if duplicate else awarded_points,
			"total_points": new_total,
			"duplicate": duplicate,
			"message": message,
			"input_type": input_type,
			"gemini_analysis": {
				"available": gemini_available,
				"items": gemini_result.get("items", []),
				"summary": gemini_result.get("summary", ""),
				"error": gemini_result.get("error", None),
				"fallback": gemini_result.get("fallback", False),
				"message": gemini_result.get("message", None)
			}
		}
		return jsonify(response), 200
	
	else:
		# Process as video
		try:
			# Extract keyframes from video
			keyframes = extract_keyframes_from_video(file_bytes)
			
			# Analyze video sequence with Gemini
			video_analysis = analyze_video_sequence_with_gemini(keyframes)
			
			# Generate hash for duplicate detection (using first frame)
			first_frame_bytes = cv2.imencode('.jpg', keyframes[0])[1].tobytes()
			file_hash = generate_image_hash(first_frame_bytes)
			
			# Determine points based on video analysis with additional validation
			awarded_points = 0
			message = ''
			
			# Additional validation to prevent false positives
			waste_type = video_analysis.get("waste_type", "unknown").lower()
			disposal_verified = video_analysis.get("disposal_verified", False)
			reasoning = video_analysis.get("reasoning", "").lower()
			
			print(f"Video validation: waste_type='{waste_type}', disposal_verified={disposal_verified}")
			print(f"Reasoning: {reasoning}")
			
			# Check for invalid waste types (hands, dustbins, etc.)
			invalid_types = ["hand", "hands", "dustbin", "trash", "bin", "container", "bag", "unknown"]
			is_valid_waste_type = not any(invalid_type in waste_type for invalid_type in invalid_types)
			
			# Check reasoning for disposal action keywords (more lenient)
			disposal_keywords = ["deposited", "thrown", "placed", "disposed", "inside", "into", "bin", "dustbin", "dropped", "put"]
			has_disposal_action = any(keyword in reasoning for keyword in disposal_keywords)
			
			# More lenient validation - if AI says disposal is verified and waste type is valid, trust it
			if disposal_verified and is_valid_waste_type:
				# Award points for successful disposal verification
				awarded_points = POINTS_PER_DETECTION
				message = f'Disposal verified for {video_analysis.get("waste_type", "waste item")}. Points awarded.'
			elif not disposal_verified:
				message = 'Disposal not verified - no clear evidence of waste being deposited into bin.'
			elif not is_valid_waste_type:
				message = f'Invalid waste type detected ({waste_type}). Only actual waste items qualify for points.'
			else:
				message = 'Disposal verification failed - insufficient evidence of proper waste disposal.'
			
			# Check for duplicates and update database
			duplicate = False
			with get_db_connection() as conn:
				row = conn.execute('SELECT id, total_points FROM users WHERE username = ?', (username,)).fetchone()
				if row is None:
					return jsonify({"error": "user not found"}), 404
				user_id = int(row[0])
				current_total = int(row[1])

				# Check if this video hash already exists for this user
				existing_hash = conn.execute(
					'SELECT id FROM image_hashes WHERE user_id = ? AND image_hash = ?', 
					(user_id, file_hash)
				).fetchone()

				if existing_hash:
					duplicate = True
					new_total = current_total
					message = 'This exact video has already been analyzed. No additional points awarded.'
				else:
					# Store the video hash and award points
					new_total = current_total + awarded_points
					conn.execute('UPDATE users SET total_points = ? WHERE id = ?', (new_total, user_id))
					conn.execute('INSERT INTO image_hashes (user_id, image_hash) VALUES (?, ?)', (user_id, file_hash))
					if awarded_points != 0:
						conn.execute('INSERT INTO transactions (user_id, points_change, reason) VALUES (?, ?, ?)', (user_id, awarded_points, 'Video Disposal Verified'))
						conn.execute('UPDATE stats SET detections = detections + 1 WHERE id = 1')
					conn.commit()

			# Response for video analysis
			response = {
				"detected_items": [video_analysis.get("waste_type", "unknown")] if video_analysis.get("disposal_verified", False) else [],
				"recyclable_items": [],
				"hazardous_items": [],
				"general_items": [],
				"awarded_points": 0 if duplicate else awarded_points,
				"total_points": new_total,
				"duplicate": duplicate,
				"message": message,
				"input_type": input_type,
				"video_analysis": {
					"waste_type": video_analysis.get("waste_type", "unknown"),
					"disposal_verified": video_analysis.get("disposal_verified", False),
					"reasoning": video_analysis.get("reasoning", "No reasoning provided"),
					"available": not video_analysis.get("fallback", False),
					"error": video_analysis.get("error", None),
					"fallback": video_analysis.get("fallback", False),
					"message": video_analysis.get("message", None)
				}
			}
			return jsonify(response), 200
			
		except Exception as e:
			return jsonify({"error": f"Video processing failed: {str(e)}"}), 500


@app.route('/api/analyze-detailed', methods=['POST'])
def analyze_detailed() -> Tuple[Any, int]:
	"""
	Detailed analysis endpoint that provides comprehensive waste analysis using Gemini AI
	"""
	username = parse_username_from_auth()
	if not username:
		return jsonify({"error": "missing auth token"}), 401

	# Get input type from form data
	input_type = request.form.get('input_type', 'photo')
	
	# Determine which file field to use based on input type
	file_field = None
	if input_type == 'photo':
		file_field = 'photo_file'
	elif input_type == 'video_gallery':
		file_field = 'video_gallery_file'
	elif input_type == 'video_camera':
		file_field = 'video_camera_file'
	else:
		return jsonify({"error": "invalid input type"}), 400

	if file_field not in request.files:
		return jsonify({"error": f"no {file_field} uploaded"}), 400
	file = request.files[file_field]
	if file.filename == '':
		return jsonify({"error": "empty filename"}), 400

	# Read file bytes
	file_bytes = file.read()
	
	# Process based on input type
	if input_type == 'photo':
		# Process as image
		np_arr = np.frombuffer(file_bytes, np.uint8)
		image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
		if image is None:
			return jsonify({"error": "invalid image"}), 400

		# Generate image hash for duplicate detection
		file_hash = generate_image_hash(file_bytes)
	else:
		# Process as video
		try:
			# Extract keyframes from video
			keyframes = extract_keyframes_from_video(file_bytes)
			
			# Generate hash for duplicate detection (using first frame)
			first_frame_bytes = cv2.imencode('.jpg', keyframes[0])[1].tobytes()
			file_hash = generate_image_hash(first_frame_bytes)
		except Exception as e:
			return jsonify({"error": f"Video processing failed: {str(e)}"}), 500

	# Check if this exact file has been uploaded by this user before
	duplicate = False
	with get_db_connection() as conn:
		row = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
		if row is None:
			return jsonify({"error": "user not found"}), 404
		user_id = int(row[0])

		# Check if this file hash already exists for this user
		existing_hash = conn.execute(
			'SELECT id FROM image_hashes WHERE user_id = ? AND image_hash = ?', 
			(user_id, file_hash)
		).fetchone()

		if existing_hash:
			# Mark as duplicate but do not abort — return analysis but flag duplicate so frontend can decide
			duplicate = True

	# Get detailed analysis based on input type
	if input_type == 'photo':
		# Get detailed Gemini analysis for image
		gemini_result = analyze_with_gemini(image)
		
		if "error" in gemini_result:
			return jsonify({
				"error": gemini_result["error"],
				"gemini_available": bool(GEMINI_API_KEY)
			}), 500

		# Categorize items
		categorized = categorize_gemini_items(gemini_result)
		
		# Calculate potential points based on detailed classification
		potential_points = 0
		recyclable_count = len(categorized["recyclable"])
		hazardous_count = len(categorized["hazardous"])
		general_count = len(categorized["general"])
		
		# Points calculation based on waste type and recyclability
		for item in categorized["recyclable"]:
			recyclability = item.get("recyclability", "medium")
			if recyclability == "high":
				potential_points += 150  # High recyclability items
			elif recyclability == "medium":
				potential_points += 100  # Medium recyclability items
			else:
				potential_points += 50   # Low recyclability items
		
		for item in categorized["hazardous"]:
			potential_points += 200  # Hazardous items get highest points
		
		for item in categorized["general"]:
			potential_points += 25   # General waste gets lower points
		
		# If no detailed classification, use old system
		if potential_points == 0:
			if recyclable_count > 0 or hazardous_count > 0:
				potential_points = POINTS_PER_DETECTION * (recyclable_count + hazardous_count)
			elif general_count > 0:
				potential_points = NON_RECYCLABLE_FLAT_POINTS

		# Persist image hash for this user to prevent future repeats
		with get_db_connection() as conn:
			try:
				if not duplicate:
					conn.execute('INSERT INTO image_hashes (user_id, image_hash) VALUES (?, ?)', (user_id, file_hash))
					conn.commit()
			except Exception as e:
				print(f"Warning: failed to persist image hash: {str(e)}")

		response = {
			"analysis": gemini_result,
			"categorized_items": categorized,
			"potential_points": potential_points,
			"gemini_available": bool(GEMINI_API_KEY),
			"disposal_tips": [item.get("disposal_tip", "") for item in gemini_result.get("items", []) if item.get("disposal_tip")],
			"environmental_impacts": [item.get("environmental_impact", "") for item in gemini_result.get("items", []) if item.get("environmental_impact")],
			"summary": gemini_result.get("summary", ""),
			"input_type": input_type,
			"duplicate": duplicate
		}
		
		return jsonify(response), 200
	
	else:
		# Get detailed video analysis
		video_analysis = analyze_video_sequence_with_gemini(keyframes)
		
		if "error" in video_analysis:
			return jsonify({
				"error": video_analysis["error"],
				"gemini_available": bool(GEMINI_API_KEY)
			}), 500

		# Calculate potential points for video
		potential_points = 0
		if video_analysis.get("disposal_verified", False):
			potential_points = POINTS_PER_DETECTION

		response = {
			"video_analysis": video_analysis,
			"potential_points": potential_points,
			"gemini_available": bool(GEMINI_API_KEY),
			"waste_type": video_analysis.get("waste_type", "unknown"),
			"disposal_verified": video_analysis.get("disposal_verified", False),
			"reasoning": video_analysis.get("reasoning", "No reasoning provided"),
			"input_type": input_type
		}

		# Persist hash to prevent repeated submissions being treated as new
		with get_db_connection() as conn:
			try:
				if not duplicate:
					conn.execute('INSERT INTO image_hashes (user_id, image_hash) VALUES (?, ?)', (user_id, file_hash))
					conn.commit()
			except Exception as e:
				print(f"Warning: failed to persist video hash: {str(e)}")

		response["duplicate"] = duplicate
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


# ======== Clan System ========
def _get_user(conn: Connection, username: str) -> Optional[sqlite3.Row]:
    return conn.execute('SELECT id, username, city, state, country, total_points FROM users WHERE username = ?', (username,)).fetchone()


def _generate_join_code(conn: Connection) -> str:
    # 4-digit zero-padded unique code
    for _ in range(100):
        code = f"{random.randint(0, 9999):04d}"
        exists = conn.execute('SELECT 1 FROM clans WHERE join_code = ?', (code,)).fetchone()
        if not exists:
            return code
    return f"{int(time.time()) % 10000:04d}"


@app.route('/api/clans', methods=['GET'])
def list_city_clans():
    username = parse_username_from_auth()
    if not username:
        return jsonify({"error": "unauthorized"}), 401
    with get_db_connection() as conn:
        u = _get_user(conn, username)
        if u is None:
            return jsonify({"error": "user not found"}), 404
        rows = conn.execute(
            'SELECT id, name, city, state, country, leader_user_id, created_at FROM clans WHERE city = ? ORDER BY created_at DESC',
            (u["city"],)
        ).fetchall()
        clans = [
            {
                "id": r["id"],
                "name": r["name"],
                "city": r["city"],
                "state": r["state"],
                "country": r["country"],
                "leader_user_id": r["leader_user_id"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]
        return jsonify({"clans": clans}), 200


@app.route('/api/my_clan', methods=['GET'])
def get_my_clan():
    username = parse_username_from_auth()
    if not username:
        return jsonify({"error": "unauthorized"}), 401
    with get_db_connection() as conn:
        u = _get_user(conn, username)
        if u is None:
            return jsonify({"error": "user not found"}), 404
        row = conn.execute(
            'SELECT c.* FROM clans c JOIN clan_members cm ON c.id = cm.clan_id JOIN users u ON u.id = cm.user_id WHERE u.username = ?',
            (username,)
        ).fetchone()
        if row is None:
            return jsonify({"clan": None}), 200
        clan_id = row["id"]
        members = conn.execute(
            'SELECT u.id, u.username, u.total_points, cm.role FROM clan_members cm JOIN users u ON u.id = cm.user_id WHERE cm.clan_id = ? ORDER BY CASE WHEN cm.role = "leader" THEN 0 ELSE 1 END, u.total_points DESC',
            (clan_id,)
        ).fetchall()
        leader_user = conn.execute('SELECT username FROM users WHERE id = ?', (row["leader_user_id"],)).fetchone()
        is_leader = bool(leader_user and leader_user[0] == username)
        resp = {
            "id": row["id"],
            "name": row["name"],
            "city": row["city"],
            "state": row["state"],
            "country": row["country"],
            "leader_username": (leader_user[0] if leader_user else None),
            "members": [
                {
                    "id": m["id"],
                    "username": m["username"],
                    "role": m["role"],
                    "total_points": m["total_points"],
                }
                for m in members
            ],
        }
        if is_leader:
            resp["join_code"] = row["join_code"]
        return jsonify({"clan": resp}), 200


@app.route('/api/clans', methods=['POST'])
def create_clan():
    username = parse_username_from_auth()
    if not username:
        return jsonify({"error": "unauthorized"}), 401
    data: Dict[str, Any] = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    with get_db_connection() as conn:
        u = _get_user(conn, username)
        if u is None:
            return jsonify({"error": "user not found"}), 404
        existing = conn.execute('SELECT 1 FROM clan_members WHERE user_id = ?', (u["id"],)).fetchone()
        if existing:
            return jsonify({"error": "already in a clan"}), 400
        code = _generate_join_code(conn)
        conn.execute(
            'INSERT INTO clans (name, city, state, country, leader_user_id, join_code) VALUES (?, ?, ?, ?, ?, ?)',
            (name, u["city"], u["state"], u["country"], u["id"], code)
        )
        clan_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        conn.execute('INSERT INTO clan_members (clan_id, user_id, role) VALUES (?, ?, ?)', (clan_id, u["id"], 'leader'))
        conn.commit()
        return jsonify({"clan_id": clan_id, "join_code": code}), 201


@app.route('/api/clans/join', methods=['POST'])
def join_clan():
    username = parse_username_from_auth()
    if not username:
        return jsonify({"error": "unauthorized"}), 401
    data: Dict[str, Any] = request.get_json(silent=True) or {}
    code = (data.get('code') or '').strip()
    if not code.isdigit() or len(code) != 4:
        return jsonify({"error": "invalid code"}), 400
    with get_db_connection() as conn:
        u = _get_user(conn, username)
        if u is None:
            return jsonify({"error": "user not found"}), 404
        already = conn.execute('SELECT 1 FROM clan_members WHERE user_id = ?', (u["id"],)).fetchone()
        if already:
            return jsonify({"error": "already in a clan"}), 400
        clan = conn.execute('SELECT * FROM clans WHERE join_code = ?', (code,)).fetchone()
        if clan is None:
            return jsonify({"error": "clan not found"}), 404
        if (clan["city"] or '').strip().lower() != (u["city"] or '').strip().lower():
            return jsonify({"error": "can only join clan in your city"}), 400
        conn.execute('INSERT INTO clan_members (clan_id, user_id, role) VALUES (?, ?, ?)', (clan["id"], u["id"], 'member'))
        conn.commit()
        return jsonify({"status": "joined", "clan_id": clan["id"]}), 200


@app.route('/api/my_clan/leave', methods=['DELETE'])
def leave_clan():
    username = parse_username_from_auth()
    if not username:
        return jsonify({"error": "unauthorized"}), 401
    with get_db_connection() as conn:
        u = _get_user(conn, username)
        if u is None:
            return jsonify({"error": "user not found"}), 404
        row = conn.execute('SELECT cm.clan_id, c.leader_user_id FROM clan_members cm JOIN clans c ON c.id = cm.clan_id WHERE cm.user_id = ?', (u["id"],)).fetchone()
        if row is None:
            return jsonify({"error": "not in a clan"}), 400
        clan_id, leader_user_id = row["clan_id"], row["leader_user_id"]
        if leader_user_id == u["id"]:
            count = conn.execute('SELECT COUNT(*) FROM clan_members WHERE clan_id = ?', (clan_id,)).fetchone()[0]
            if count > 1:
                return jsonify({"error": "leader cannot leave while members remain"}), 400
            conn.execute('DELETE FROM clan_members WHERE clan_id = ?', (clan_id,))
            conn.execute('DELETE FROM clan_messages WHERE clan_id = ?', (clan_id,))
            conn.execute('DELETE FROM clans WHERE id = ?', (clan_id,))
        else:
            conn.execute('DELETE FROM clan_members WHERE clan_id = ? AND user_id = ?', (clan_id, u["id"]))
        conn.commit()
        return jsonify({"status": "left"}), 200


@app.route('/api/clans/kick', methods=['POST'])
def kick_member():
    username = parse_username_from_auth()
    if not username:
        return jsonify({"error": "unauthorized"}), 401
    data: Dict[str, Any] = request.get_json(silent=True) or {}
    target_username = (data.get('username') or '').strip()
    if not target_username:
        return jsonify({"error": "username required"}), 400
    with get_db_connection() as conn:
        leader = _get_user(conn, username)
        if leader is None:
            return jsonify({"error": "user not found"}), 404
        clan_row = conn.execute('SELECT id FROM clans WHERE leader_user_id = ?', (leader["id"],)).fetchone()
        if clan_row is None:
            return jsonify({"error": "not a clan leader"}), 403
        clan_id = clan_row["id"]
        target = conn.execute('SELECT id, username FROM users WHERE username = ?', (target_username,)).fetchone()
        if target is None:
            return jsonify({"error": "target user not found"}), 404
        if target["id"] == leader["id"]:
            return jsonify({"error": "cannot kick yourself"}), 400
        mem_row = conn.execute('SELECT role FROM clan_members WHERE clan_id = ? AND user_id = ?', (clan_id, target["id"]))
        mem_row = mem_row.fetchone()
        if mem_row is None:
            return jsonify({"error": "user not in your clan"}), 400
        if (mem_row["role"] or '').lower() == 'leader':
            return jsonify({"error": "cannot kick leader"}), 400
        conn.execute('DELETE FROM clan_members WHERE clan_id = ? AND user_id = ?', (clan_id, target["id"]))
        conn.commit()
        return jsonify({"status": "kicked"}), 200


@app.route('/api/clan_chat', methods=['GET'])
def get_clan_chat():
    username = parse_username_from_auth()
    if not username:
        return jsonify({"error": "unauthorized"}), 401
    clan_id = request.args.get('clan_id')
    if not clan_id:
        return jsonify({"error": "clan_id required"}), 400
    try:
        clan_id_int = int(clan_id)
    except Exception:
        return jsonify({"error": "invalid clan_id"}), 400
    with get_db_connection() as conn:
        u = _get_user(conn, username)
        if u is None:
            return jsonify({"error": "user not found"}), 404
        mem = conn.execute('SELECT 1 FROM clan_members WHERE clan_id = ? AND user_id = ?', (clan_id_int, u["id"]))
        if mem.fetchone() is None:
            return jsonify({"error": "not a member"}), 403
        msgs = conn.execute(
            'SELECT m.id, m.message, m.created_at, u.username as sender_username FROM clan_messages m JOIN users u ON u.id = m.sender_user_id WHERE m.clan_id = ? AND m.deleted_at IS NULL ORDER BY m.created_at ASC',
            (clan_id_int,)
        ).fetchall()
        messages = [
            {
                "id": r["id"],
                "sender_username": r["sender_username"],
                "message": r["message"],
                "created_at": r["created_at"],
            }
            for r in msgs
        ]
        return jsonify({"messages": messages}), 200


@app.route('/api/clan_chat', methods=['POST'])
def post_clan_chat():
    username = parse_username_from_auth()
    if not username:
        return jsonify({"error": "unauthorized"}), 401
    data: Dict[str, Any] = request.get_json(silent=True) or {}
    try:
        clan_id = int(data.get('clan_id'))
    except Exception:
        return jsonify({"error": "invalid clan_id"}), 400
    message_text = (data.get('message') or '').trim() if hasattr((data.get('message') or ''), 'trim') else (data.get('message') or '').strip()
    if not message_text:
        return jsonify({"error": "message required"}), 400
    with get_db_connection() as conn:
        u = _get_user(conn, username)
        if u is None:
            return jsonify({"error": "user not found"}), 404
        mem = conn.execute('SELECT 1 FROM clan_members WHERE clan_id = ? AND user_id = ?', (clan_id, u["id"]))
        if mem.fetchone() is None:
            return jsonify({"error": "not a member"}), 403
        conn.execute('INSERT INTO clan_messages (clan_id, sender_user_id, message) VALUES (?, ?, ?)', (clan_id, u["id"], message_text))
        msg_row_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        msg_row = conn.execute('SELECT id, message, created_at FROM clan_messages WHERE id = ?', (msg_row_id,)).fetchone()
        conn.commit()
        return jsonify({
            "message": {
                "id": msg_row["id"],
                "sender_username": username,
                "message": msg_row["message"],
                "created_at": msg_row["created_at"],
            }
        }), 201


@app.route('/api/clan_chat/<int:message_id>', methods=['DELETE'])
def delete_clan_message(message_id: int):
    username = parse_username_from_auth()
    if not username:
        return jsonify({"error": "unauthorized"}), 401
    with get_db_connection() as conn:
        u = _get_user(conn, username)
        if u is None:
            return jsonify({"error": "user not found"}), 404
        m = conn.execute('SELECT clan_id, sender_user_id FROM clan_messages WHERE id = ? AND deleted_at IS NULL', (message_id,)).fetchone()
        if m is None:
            return jsonify({"error": "message not found"}), 404
        clan_id = m["clan_id"]
        is_sender = (m["sender_user_id"] == u["id"])
        leader_row = conn.execute('SELECT leader_user_id FROM clans WHERE id = ?', (clan_id,)).fetchone()
        is_leader = bool(leader_row and leader_row[0] == u["id"])
        if not (is_sender or is_leader):
            return jsonify({"error": "forbidden"}), 403
        conn.execute('UPDATE clan_messages SET deleted_at = CURRENT_TIMESTAMP, deleted_by_user_id = ? WHERE id = ?', (u["id"], message_id))
        conn.commit()
        return jsonify({"status": "deleted"}), 200


# ======== Leaderboard ========
@app.route('/api/leaderboard/users', methods=['GET'])
def leaderboard_users():
    limit = int(request.args.get('limit', '10'))
    limit = max(1, min(limit, 50))
    with get_db_connection() as conn:
        rows = conn.execute('SELECT username, total_points, city, state FROM users ORDER BY total_points DESC LIMIT ?', (limit,)).fetchall()
        users = [
            {
                "username": r["username"],
                "total_points": r["total_points"],
                "city": r["city"],
                "state": r["state"],
            }
            for r in rows
        ]
        return jsonify({"users": users}), 200


@app.route('/api/leaderboard/clans', methods=['GET'])
def leaderboard_clans():
    limit = int(request.args.get('limit', '10'))
    limit = max(1, min(limit, 50))
    with get_db_connection() as conn:
        rows = conn.execute(
            'SELECT c.id, c.name, c.city, SUM(u.total_points) AS points, COUNT(cm.user_id) AS members_count '
            'FROM clans c '
            'JOIN clan_members cm ON cm.clan_id = c.id '
            'JOIN users u ON u.id = cm.user_id '
            'GROUP BY c.id '
            'ORDER BY points DESC '
            'LIMIT ?',
            (limit,)
        ).fetchall()
        clans = [
            {
                "id": r["id"],
                "name": r["name"],
                "city": r["city"],
                "points": r["points"] or 0,
                "members_count": r["members_count"] or 0,
            }
            for r in rows
        ]
        return jsonify({"clans": clans}), 200


if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
