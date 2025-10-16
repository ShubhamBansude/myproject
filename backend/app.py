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
import threading
import threading


# Image processing
import cv2
import numpy as np

# Video processing
import tempfile

# EXIF and geolocation processing
import piexif
from geopy.geocoders import Nominatim
import math
import requests
import re
import html as htmllib

# Gemini AI integration
try:
    import google.generativeai as genai
except Exception:
    genai = None
from PIL import Image, ImageDraw, ImageFont, ImageFilter


DB_PATH = os.path.join(os.path.dirname(__file__), 'rewards_db.sqlite')
POINTS_PER_DETECTION = 100
NON_RECYCLABLE_FLAT_POINTS = 50

# New rewards and pricing configuration
BOUNTY_REPORTER_REWARD = 400
INDIVIDUAL_BOUNTY_REWARD = 2000
CLAN_BOUNTY_REWARD = 6000

# Detection scoring bounds for images
DETECT_IMAGE_MIN_POINTS = 10
DETECT_IMAGE_MAX_POINTS = 40

# Coupon pricing normalization
COUPON_MIN_COST = 1000
COUPON_MAX_COST = 4000

# Gemini API configuration
def _load_gemini_api_key() -> Optional[str]:
    """
    Load Gemini/Google Generative AI API key from environment variables, with sensible fallbacks.
    Checks both GEMINI_API_KEY and GOOGLE_API_KEY for compatibility.
    """
    # Primary env vars
    key = (os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY'))
    if key:
        return key.strip()

    # Fallback: look for simple .env files colocated with backend or repo root
    candidate_paths = [
        os.path.join(os.path.dirname(__file__), '.env'),
        os.path.join(os.path.dirname(__file__), '.env.txt'),
        os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'),
        os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env.txt'),
    ]
    possible_keys = ('GEMINI_API_KEY', 'GOOGLE_API_KEY')
    for env_path in candidate_paths:
        try:
            if not os.path.exists(env_path):
                continue
            with open(env_path, 'r', encoding='utf-8') as fh:
                for raw_line in fh:
                    line = raw_line.strip()
                    if not line or line.startswith('#'):
                        continue
                    for var in possible_keys:
                        prefix = f'{var}='
                        if line.startswith(prefix) and len(line) > len(prefix):
                            return line[len(prefix):].strip().strip('"').strip("'")
        except Exception:
            # Ignore parsing errors and continue searching
            pass
    return None

GEMINI_API_KEY = _load_gemini_api_key()
if GEMINI_API_KEY and genai is not None:
    genai.configure(api_key=GEMINI_API_KEY)

# Unified availability flag used throughout the app
GEMINI_AVAILABLE = bool(GEMINI_API_KEY and genai is not None)


def generate_image_hash(image_bytes: bytes) -> str:
	"""
	Generate a SHA-256 hash of the image bytes for duplicate detection
	"""
	return hashlib.sha256(image_bytes).hexdigest()


def extract_gps_from_image(image_bytes: bytes) -> tuple:
    """
    Extract GPS coordinates from image EXIF data.
    Returns (latitude, longitude) or (None, None) if not found.
    Uses piexif on raw bytes to avoid false FileNotFoundError on empty exif.
    """
    try:
        # Parse EXIF directly from the raw image bytes (more reliable than Image.info['exif'])
        exif_dict = piexif.load(image_bytes)

        # Ensure GPS block exists
        if not isinstance(exif_dict, dict) or 'GPS' not in exif_dict:
            return None, None

        gps_data = exif_dict['GPS'] or {}

        # Extract latitude
        if piexif.GPSIFD.GPSLatitude in gps_data and piexif.GPSIFD.GPSLatitudeRef in gps_data:
            lat_deg = gps_data[piexif.GPSIFD.GPSLatitude]
            lat_ref = gps_data[piexif.GPSIFD.GPSLatitudeRef]
            latitude = (
                lat_deg[0][0] / lat_deg[0][1]
                + lat_deg[1][0] / lat_deg[1][1] / 60.0
                + lat_deg[2][0] / lat_deg[2][1] / 3600.0
            )
            if lat_ref in (b'S', b's'):
                latitude = -latitude
        else:
            return None, None

        # Extract longitude
        if piexif.GPSIFD.GPSLongitude in gps_data and piexif.GPSIFD.GPSLongitudeRef in gps_data:
            lon_deg = gps_data[piexif.GPSIFD.GPSLongitude]
            lon_ref = gps_data[piexif.GPSIFD.GPSLongitudeRef]
            longitude = (
                lon_deg[0][0] / lon_deg[0][1]
                + lon_deg[1][0] / lon_deg[1][1] / 60.0
                + lon_deg[2][0] / lon_deg[2][1] / 3600.0
            )
            if lon_ref in (b'W', b'w'):
                longitude = -longitude
        else:
            return None, None

        return latitude, longitude

    except Exception as e:
        # Keep a concise log for debugging, but do not crash flow
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
	if not GEMINI_AVAILABLE:
		return {
			"error": "Gemini API key not configured. Set GEMINI_API_KEY or GOOGLE_API_KEY on backend.", 
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
	if not GEMINI_AVAILABLE:
		return {
			"error": "Gemini API key not configured. Set GEMINI_API_KEY or GOOGLE_API_KEY on backend.", 
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


# --------------------------
# Carbon estimation helpers
# --------------------------
def _load_emission_factors() -> Dict[str, float]:
    """Load emission factors in kg per item for coarse categories."""
    factors_path = os.path.join(os.path.dirname(__file__), 'emission_factors.json')
    default_factors: Dict[str, float] = {"plastic": 0.3, "paper": 0.1, "metal": 0.7}
    try:
        with open(factors_path, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
            if isinstance(data, dict):
                # sanitize values to float
                return {str(k).lower(): float(v) for k, v in data.items() if isinstance(v, (int, float, str))}
    except Exception:
        pass
    return default_factors


def _infer_carbon_category_from_text(text: str) -> Optional[str]:
    """Infer coarse carbon category (plastic, paper, metal) from free text."""
    t = (text or '').lower()
    if not t:
        return None
    # Plastics (include common polymers and items)
    plastic_keywords = [
        'plastic', 'pet', 'hdpe', 'ldpe', 'pp', 'polystyrene', 'ps', 'polyethylene', 'bottle', 'wrapper', 'bag',
        'container', 'packaging', 'tetra pak'
    ]
    # Paper/cardboard
    paper_keywords = ['paper', 'cardboard', 'carton', 'newspaper', 'magazine', 'tissue', 'paperboard']
    # Metals (aluminum/steel cans, foil)
    metal_keywords = ['aluminum', 'aluminium', 'metal', 'tin', 'steel', 'can', 'foil']
    if any(k in t for k in plastic_keywords):
        return 'plastic'
    if any(k in t for k in paper_keywords):
        return 'paper'
    if any(k in t for k in metal_keywords):
        return 'metal'
    return None


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
				('10% Off Eco-Store Voucher', 1000, 'ECOSAVE10', 'Get 10% off on sustainable products.', 1),
				('Free Digital Sticker Pack', 1000, 'DIGISTICKER', 'A pack of 5 exclusive digital stickers.', 1),
				('₹50 Discount on Coffee', 1200, 'COFFEE50', 'Valid at selected partner cafes.', 1),
			]
		)
		conn.commit()


def ensure_curated_coupons(conn: Connection) -> None:
    """
    Ensure a small curated set of brand gift vouchers and discount coupons
    exist in the `coupons` table. Idempotent via INSERT OR IGNORE.

    Points costs are randomized within sensible ranges once at first insert.
    """
    curated: List[Dict[str, Any]] = [
        {
            "name": "Amazon eGift Card ₹100",
            "code": "AMZN100",
            "desc": "Redeemable on Amazon.in eligible items.",
            "url": None,
            "points": (800, 1200),
        },
        {
            "name": "Amazon eGift Card ₹250",
            "code": "AMZN250",
            "desc": "Amazon.in eGift card (limited categories excluded).",
            "url": None,
            "points": (1500, 2200),
        },
        {
            "name": "Flipkart Gift Card ₹200",
            "code": "FLIP200",
            "desc": "Flipkart eGift card — fashion, electronics, more.",
            "url": None,
            "points": (1200, 1800),
        },
        {
            "name": "Myntra Gift Card ₹300",
            "code": "MYNTRA300",
            "desc": "Style more with Myntra eGift card.",
            "url": None,
            "points": (1600, 2300),
        },
        {
            "name": "Swiggy 20% OFF (max ₹100)",
            "code": "FOOD20",
            "desc": "Valid on select restaurants and orders above minimum.",
            "url": None,
            "points": (500, 900),
        },
        {
            "name": "Zomato ₹75 OFF Coupon",
            "code": "ZOMATO75",
            "desc": "Applicable on eligible orders above minimum value.",
            "url": None,
            "points": (400, 800),
        },
        {
            "name": "Starbucks ₹100 OFF",
            "code": "STAR100",
            "desc": "Enjoy a discount at participating Starbucks stores.",
            "url": None,
            "points": (800, 1200),
        },
        {
            "name": "Eco-Store 15% OFF",
            "code": "ECO15",
            "desc": "15% off on sustainable products at partner eco-stores.",
            "url": None,
            "points": (600, 1000),
        },
    ]

    for item in curated:
        try:
            # Normalize curated coupon costs into the global [COUPON_MIN_COST, COUPON_MAX_COST] range
            low, high = item["points"]
            # Map existing ranges into new window while preserving relative spread
            # Use midpoint as a heuristic when old range falls outside new bounds
            mid = (int(low) + int(high)) // 2
            points_cost = max(COUPON_MIN_COST, min(COUPON_MAX_COST, mid))
            conn.execute(
                'INSERT OR IGNORE INTO coupons (name, points_cost, coupon_code, description, is_active, external_url, source) '
                'VALUES (?, ?, ?, ?, 1, ?, ?)',
                (
                    item["name"],
                    points_cost,
                    item["code"],
                    item["desc"],
                    item["url"],
                    'Curated',
                ),
            )
        except Exception:
            # Ignore individual failures to allow the rest to be inserted
            continue
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
		# Add optional columns for external source-backed coupons
		cursor = conn.execute('PRAGMA table_info(coupons)')
		coupon_columns = [column[1] for column in cursor.fetchall()]
		if 'external_url' not in coupon_columns:
			conn.execute('ALTER TABLE coupons ADD COLUMN external_url TEXT')
		if 'source' not in coupon_columns:
			conn.execute('ALTER TABLE coupons ADD COLUMN source TEXT')
		conn.commit()
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
		# Per-user certificate issuance table (enforce one-time issuance)
		conn.execute(
			(
				'CREATE TABLE IF NOT EXISTS user_certificates ('
				'  id INTEGER PRIMARY KEY AUTOINCREMENT,'
				'  user_id INTEGER NOT NULL UNIQUE,'
				'  filename TEXT NOT NULL,'
				'  issued_at DATETIME DEFAULT CURRENT_TIMESTAMP,'
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

		# Clan join requests
		conn.execute(
			(
				'CREATE TABLE IF NOT EXISTS clan_join_requests ('
				'  id INTEGER PRIMARY KEY AUTOINCREMENT,'
				'  clan_id INTEGER NOT NULL,'
				'  applicant_user_id INTEGER NOT NULL,'
				'  status TEXT NOT NULL DEFAULT "pending",'
				'  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,'
				'  resolved_at DATETIME,'
				'  FOREIGN KEY(clan_id) REFERENCES clans(id),'
				'  FOREIGN KEY(applicant_user_id) REFERENCES users(id),'
				'  UNIQUE(clan_id, applicant_user_id)'
				')'
			)
		)
		conn.execute('CREATE INDEX IF NOT EXISTS idx_clan_join_requests_clan ON clan_join_requests(clan_id)')
		conn.execute('CREATE INDEX IF NOT EXISTS idx_clan_join_requests_applicant ON clan_join_requests(applicant_user_id)')
		conn.commit()

		# Clan bounty participation claims (member requests leader approval to participate)
		conn.execute(
			(
				'CREATE TABLE IF NOT EXISTS clan_bounty_claims ('
				'  id INTEGER PRIMARY KEY AUTOINCREMENT,'
				'  bounty_id INTEGER NOT NULL,'
				'  clan_id INTEGER NOT NULL,'
				'  requested_by_user_id INTEGER NOT NULL,'
				'  people_strength INTEGER NOT NULL CHECK (people_strength >= 0 AND people_strength <= 20),'
				'  scheduled_at DATETIME,'
				'  status TEXT NOT NULL CHECK (status IN ("pending","approved","rejected")) DEFAULT "pending",'
				'  decided_by_user_id INTEGER,'
				'  decided_at DATETIME,'
				'  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,'
				'  updated_at DATETIME,'
				'  FOREIGN KEY(bounty_id) REFERENCES waste_bounty(id),'
				'  FOREIGN KEY(clan_id) REFERENCES clans(id),'
				'  FOREIGN KEY(requested_by_user_id) REFERENCES users(id),'
				'  FOREIGN KEY(decided_by_user_id) REFERENCES users(id)'
				')'
			)
		)
		conn.execute('CREATE INDEX IF NOT EXISTS idx_cbc_clan_status ON clan_bounty_claims(clan_id, status)')
		conn.execute('CREATE INDEX IF NOT EXISTS idx_cbc_bounty_status ON clan_bounty_claims(bounty_id, status)')
		conn.execute('CREATE INDEX IF NOT EXISTS idx_cbc_requester ON clan_bounty_claims(requested_by_user_id)')
		conn.commit()

		# Friends and direct messages
		conn.execute(
			(
				'CREATE TABLE IF NOT EXISTS friends ('
				'  id INTEGER PRIMARY KEY AUTOINCREMENT,'
				'  user_a_id INTEGER NOT NULL,'
				'  user_b_id INTEGER NOT NULL,'
				'  status TEXT NOT NULL,'
				'  requested_by_user_id INTEGER NOT NULL,'
				'  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,'
				'  updated_at DATETIME,'
				'  FOREIGN KEY(user_a_id) REFERENCES users(id),'
				'  FOREIGN KEY(user_b_id) REFERENCES users(id),'
				'  FOREIGN KEY(requested_by_user_id) REFERENCES users(id),'
				'  UNIQUE(user_a_id, user_b_id)'
				')'
			)
		)
		conn.execute('CREATE INDEX IF NOT EXISTS idx_friends_users ON friends(user_a_id, user_b_id)')
		conn.commit()

		conn.execute(
			(
				'CREATE TABLE IF NOT EXISTS direct_messages ('
				'  id INTEGER PRIMARY KEY AUTOINCREMENT,'
				'  sender_user_id INTEGER NOT NULL,'
				'  recipient_user_id INTEGER NOT NULL,'
				'  message TEXT NOT NULL,'
				'  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,'
				'  deleted_at DATETIME,'
				'  FOREIGN KEY(sender_user_id) REFERENCES users(id),'
				'  FOREIGN KEY(recipient_user_id) REFERENCES users(id)'
				')'
			)
		)
		conn.execute('CREATE INDEX IF NOT EXISTS idx_dm_pair ON direct_messages(sender_user_id, recipient_user_id)')
		conn.commit()

		# Clean-buddy bot chat messages (per-user thread)
		conn.execute(
			(
				'CREATE TABLE IF NOT EXISTS clean_buddy_messages ('
				'  id INTEGER PRIMARY KEY AUTOINCREMENT,'
				'  user_id INTEGER NOT NULL,'
				'  role TEXT NOT NULL CHECK (role IN ("user", "bot")),'
				'  message TEXT NOT NULL,'
				'  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,'
				'  FOREIGN KEY(user_id) REFERENCES users(id)'
				')'
			)
		)
		conn.execute('CREATE INDEX IF NOT EXISTS idx_cb_user ON clean_buddy_messages(user_id, created_at)')
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
				'  context_bounty_id INTEGER,'
				'  FOREIGN KEY(user_id) REFERENCES users(id)'
				')'
			)
		)
		# Add new columns to notifications if missing (for upgrades)
		cursor = conn.execute('PRAGMA table_info(notifications)')
		n_columns = [column[1] for column in cursor.fetchall()]
		if 'context_bounty_id' not in n_columns:
			conn.execute('ALTER TABLE notifications ADD COLUMN context_bounty_id INTEGER')
			try:
				conn.execute('CREATE INDEX IF NOT EXISTS idx_notifications_user_bounty ON notifications(user_id, context_bounty_id)')
			except Exception:
				pass
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

		# Missions tables (daily/weekly eco missions)
		conn.execute(
			(
				'CREATE TABLE IF NOT EXISTS missions ('
				'  id INTEGER PRIMARY KEY AUTOINCREMENT,'
				'  title TEXT NOT NULL,'
				'  description TEXT,'
				'  goal_type TEXT NOT NULL,'
				'  points INTEGER NOT NULL DEFAULT 20,'
				'  expiry_date DATE NOT NULL'
				')'
			)
		)
		conn.execute(
			(
				'CREATE TABLE IF NOT EXISTS mission_progress ('
				'  user_id INTEGER NOT NULL,'
				'  mission_id INTEGER NOT NULL,'
				'  status TEXT NOT NULL DEFAULT "pending",'
				'  progress INTEGER NOT NULL DEFAULT 0,'
				'  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,'
				'  PRIMARY KEY (user_id, mission_id),'
				'  FOREIGN KEY(user_id) REFERENCES users(id),'
				'  FOREIGN KEY(mission_id) REFERENCES missions(id)'
				')'
			)
		)
		conn.commit()

		# Streaks table (eco-streak calendar)
		conn.execute(
			(
				'CREATE TABLE IF NOT EXISTS streaks ('
				'  user_id INTEGER PRIMARY KEY,'
				'  current_streak INTEGER NOT NULL DEFAULT 0,'
				'  best_streak INTEGER NOT NULL DEFAULT 0,'
				'  last_active_date DATE'
				')'
			)
		)
		conn.commit()

		# Moderation table (AI-powered moderation queue)
		conn.execute(
			(
				'CREATE TABLE IF NOT EXISTS moderation ('
				'  id INTEGER PRIMARY KEY AUTOINCREMENT,'
				'  user_id INTEGER NOT NULL,'
				'  file_path TEXT,'
				'  status TEXT NOT NULL DEFAULT "pending_review",'
				'  reason TEXT,'
				'  pending_points INTEGER NOT NULL DEFAULT 0,'
				'  reviewed_at DATETIME,'
				'  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,'
				'  FOREIGN KEY(user_id) REFERENCES users(id)'
				')'
			)
		)
		conn.commit()

		# Carbon events table (stores estimated CO2 savings per action)
		conn.execute(
			(
				'CREATE TABLE IF NOT EXISTS carbon_events ('
				'  id INTEGER PRIMARY KEY AUTOINCREMENT,'
				'  user_id INTEGER NOT NULL,'
				'  category TEXT NOT NULL,'
				'  amount_kg REAL NOT NULL,'
				'  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,'
				'  FOREIGN KEY(user_id) REFERENCES users(id)'
				')'
			)
		)
		conn.execute('CREATE INDEX IF NOT EXISTS idx_carbon_events_user_date ON carbon_events(user_id, created_at)')
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
_certificates_dir = os.path.join(os.path.dirname(__file__), 'certificates')

@app.route('/uploads/<path:filename>')
def serve_upload(filename: str):
    return send_from_directory(_uploads_dir, filename, as_attachment=False)

@app.route('/certificates/<path:filename>')
def serve_certificate(filename: str):
    return send_from_directory(_certificates_dir, filename, as_attachment=False)

@app.route('/certificates/download/<path:filename>')
def download_certificate(filename: str):
    return send_from_directory(_certificates_dir, filename, as_attachment=True)

# In-memory subscriber registry for SSE notification streams
# Maps username -> set of Queue instances
notification_subscribers: Dict[str, Set[queue.Queue]] = defaultdict(set)

# -----------------------------
# Background scheduler (missions rotation)
# -----------------------------
_scheduler_lock = threading.Lock()
_last_mission_rotation_check = 0.0

def _rotate_daily_weekly_missions() -> None:
    """Ensure there is an active daily and weekly mission. Creates new ones on expiry."""
    try:
        with get_db_connection() as conn:
            now = datetime.utcnow()
            today = now.date()

            # Expire old missions
            conn.execute('DELETE FROM missions WHERE DATE(expiry_date) < DATE(?)', (today.isoformat(),))

            # Check if a daily mission exists for today
            row = conn.execute('SELECT id FROM missions WHERE goal_type = ? AND DATE(expiry_date) = DATE(?)', ('daily', today.isoformat())).fetchone()
            if row is None:
                daily_templates = [
                    ('Recycle 3 plastic bottles today', 'Snap and upload for bonus.', 'daily', 25),
                    ('Pick up 5 pieces of litter', 'Dispose responsibly.', 'daily', 25),
                    ('Upload one cleanup photo', 'Keep it safe and real.', 'daily', 20),
                ]
                title, desc, gtype, pts = random.choice(daily_templates)
                conn.execute(
                    'INSERT INTO missions (title, description, goal_type, points, expiry_date) VALUES (?, ?, ?, ?, ?)',
                    (title, desc, gtype, pts, (today + timedelta(days=1)).isoformat())
                )

            # Ensure a valid weekly mission (7-day horizon)
            week_row = conn.execute('SELECT id FROM missions WHERE goal_type = ? AND DATE(expiry_date) >= DATE(?) ORDER BY expiry_date ASC LIMIT 1', ('weekly', today.isoformat())).fetchone()
            if week_row is None:
                weekly_templates = [
                    ('Upload one verified cleanup bounty this week', 'Complete or verify a cleanup bounty.', 'weekly', 60),
                    ('Recycle 10 items this week', 'Multiple uploads allowed.', 'weekly', 50),
                ]
                title, desc, gtype, pts = random.choice(weekly_templates)
                conn.execute(
                    'INSERT INTO missions (title, description, goal_type, points, expiry_date) VALUES (?, ?, ?, ?, ?)',
                    (title, desc, gtype, pts, (today + timedelta(days=7)).isoformat())
                )
            conn.commit()
    except Exception as e:
        print(f"Mission rotation error: {e}")

def _scheduler_loop() -> None:
    global _last_mission_rotation_check
    while True:
        try:
            now = time.time()
            if now - _last_mission_rotation_check > 1800:  # at most once each 30 minutes
                with _scheduler_lock:
                    _rotate_daily_weekly_missions()
                    _last_mission_rotation_check = now
        except Exception as e:
            print(f"Scheduler loop error: {e}")
        time.sleep(300)  # sleep 5 minutes

_scheduler_thread = threading.Thread(target=_scheduler_loop, daemon=True)
_scheduler_thread.start()

# Simple background scheduler using a daemon thread that runs every hour
_scheduler_lock = threading.Lock()
_last_mission_rotation_check = 0.0

def _rotate_daily_weekly_missions() -> None:
    """Ensure there is an active daily and weekly mission. Creates new ones on expiry."""
    try:
        with get_db_connection() as conn:
            now = datetime.utcnow()
            today = now.date()

            # Expire old missions
            conn.execute('DELETE FROM missions WHERE DATE(expiry_date) < DATE(?)', (today.isoformat(),))

            # Check if a daily mission exists for today
            row = conn.execute('SELECT id FROM missions WHERE goal_type = ? AND DATE(expiry_date) = DATE(?)', ('daily', today.isoformat())).fetchone()
            if row is None:
                # Create a simple randomized daily mission
                daily_templates = [
                    ('Recycle 3 plastic bottles today', 'Snap and upload for bonus.', 'daily', 25),
                    ('Pick up 5 pieces of litter', 'Dispose responsibly.', 'daily', 25),
                    ('Upload one cleanup photo', 'Keep it safe and real.', 'daily', 20),
                ]
                title, desc, gtype, pts = random.choice(daily_templates)
                conn.execute(
                    'INSERT INTO missions (title, description, goal_type, points, expiry_date) VALUES (?, ?, ?, ?, ?)',
                    (title, desc, gtype, pts, (today + timedelta(days=1)).isoformat())
                )

            # Ensure a valid weekly mission ending next Monday (or 7 days ahead)
            week_row = conn.execute('SELECT id FROM missions WHERE goal_type = ? AND DATE(expiry_date) >= DATE(?) ORDER BY expiry_date ASC LIMIT 1', ('weekly', today.isoformat())).fetchone()
            if week_row is None:
                weekly_templates = [
                    ('Upload one verified cleanup bounty this week', 'Complete or verify a cleanup bounty.', 'weekly', 60),
                    ('Recycle 10 items this week', 'Multiple uploads allowed.', 'weekly', 50),
                ]
                title, desc, gtype, pts = random.choice(weekly_templates)
                conn.execute(
                    'INSERT INTO missions (title, description, goal_type, points, expiry_date) VALUES (?, ?, ?, ?, ?)',
                    (title, desc, gtype, pts, (today + timedelta(days=7)).isoformat())
                )
            conn.commit()
    except Exception as e:
        print(f"Mission rotation error: {e}")

def _scheduler_loop() -> None:
    global _last_mission_rotation_check
    while True:
        try:
            now = time.time()
            # Run rotation at most once every 30 minutes
            if now - _last_mission_rotation_check > 1800:
                with _scheduler_lock:
                    _rotate_daily_weekly_missions()
                    _last_mission_rotation_check = now
        except Exception as e:
            print(f"Scheduler loop error: {e}")
        time.sleep(300)  # sleep 5 minutes between checks

# Start scheduler thread
_scheduler_thread = threading.Thread(target=_scheduler_loop, daemon=True)
_scheduler_thread.start()


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


def _get_user_row(conn: Connection, username: str) -> Optional[sqlite3.Row]:
    return conn.execute('SELECT id, username, total_points FROM users WHERE username = ?', (username,)).fetchone()


def _award_points(conn: Connection, user_id: int, points: int, reason: str) -> None:
    conn.execute('UPDATE users SET total_points = total_points + ? WHERE id = ?', (points, user_id))
    conn.execute('INSERT INTO transactions (user_id, points_change, reason) VALUES (?, ?, ?)', (user_id, points, reason))


def _ensure_backend_dirs() -> None:
    """Ensure required backend directories exist."""
    try:
        os.makedirs(_uploads_dir, exist_ok=True)
    except Exception:
        pass
    try:
        os.makedirs(_certificates_dir, exist_ok=True)
    except Exception:
        pass


def _load_ttf_font(path: str, size: int) -> Optional[ImageFont.FreeTypeFont]:
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return None


def generate_carbon_warrior_certificate(username: str, meta: Optional[Dict[str, Any]] = None) -> str:
    """
    Generate a premium green-themed Certificate of Appreciation PDF with
    leaf motifs, layered waves, and institutional logos. Keeps the
    existing certificate content while elevating the visual design.

    Returns the filename (not full path) placed in `_certificates_dir`.
    """
    _ensure_backend_dirs()

    # Canvas: A4 landscape at ~300dpi -> 3508x2480 px
    width, height = 3508, 2480
    # Work in RGBA for layered effects with a clean white base
    base = Image.new('RGBA', (width, height), color=(255, 255, 255, 255))

    # Create main white panel and apply a faint watermark pattern of interconnected leaves
    import math  # local import avoids global dependency

    panel = Image.new('RGBA', (width - 220, height - 220), (255, 255, 255, 255))

    # Draw subtle, faint watermark pattern on the panel
    def draw_watermark_pattern(target: Image.Image) -> None:
        emerald = (0, 122, 51, 16)  # #007A33 with very low alpha
        tsize = 220
        tile = Image.new('RGBA', (tsize, tsize), (0, 0, 0, 0))
        tdraw = ImageDraw.Draw(tile)
        # Two overlapping leaf-like ellipses
        tdraw.ellipse([24, 92, 196, 132], fill=emerald)
        tdraw.ellipse([72, 48, 132, 172], fill=emerald)
        # Rotate tile a bit for a dynamic look
        tile_rot = tile.rotate(28, resample=Image.BICUBIC, expand=True)

        # Tile across the panel with spacing for airy feel
        step = 280
        for y in range(40, target.height - 40, step):
            for x in range(40, target.width - 40, step):
                # Stagger every other row slightly
                offset_x = x + (step // 2 if ((y // step) % 2 == 1) else 0)
                target.paste(tile_rot, (min(offset_x, target.width - tile_rot.width), min(y, target.height - tile_rot.height)), tile_rot)

    draw_watermark_pattern(panel)

    # Paste the panel centered with margin
    base.paste(panel, (110, 110), panel)
    composed = base

    # Drawing context on composed image
    background = composed
    draw = ImageDraw.Draw(background)

    # Decorative corner leaf cutout
    draw.rounded_rectangle(
        [120, 120, width - 120, height - 120], radius=36, outline=(15, 118, 110, 180), width=6
    )

    # Load assets and fonts
    assets_dir = os.path.join(os.path.dirname(__file__), 'assets')
    sbm_path = os.path.join(assets_dir, 'swachh-bharat.png')
    vpkb_path = os.path.join(assets_dir, 'vpkbiet_logo.png')
    # Use at most two modern sans-serif fonts: bold for titles/name, regular for body
    poppins_bold = _load_ttf_font(os.path.join(assets_dir, 'Poppins-Bold.ttf'), 160) or ImageFont.load_default()
    poppins_semibold = _load_ttf_font(os.path.join(assets_dir, 'Poppins-Bold.ttf'), 84) or ImageFont.load_default()
    poppins_regular = _load_ttf_font(os.path.join(assets_dir, 'Poppins-Regular.ttf'), 56) or ImageFont.load_default()

    # Gold badge at left-center (define early so we can render behind text)
    def draw_badge(center_x: int, center_y: int, radius: int = 180) -> None:
        badge = Image.new('RGBA', (radius*2+8, radius*2+8), (0, 0, 0, 0))
        bdraw = ImageDraw.Draw(badge)
        # outer ring
        bdraw.ellipse([4, 4, radius*2+4, radius*2+4], fill=(234, 179, 8, 255))
        bdraw.ellipse([24, 24, radius*2-16, radius*2-16], fill=(251, 191, 36, 255))
        bdraw.ellipse([56, 56, radius*2-48, radius*2-48], fill=(253, 224, 71, 255))
        # inner circle with green
        bdraw.ellipse([86, 86, radius*2-78, radius*2-78], fill=(5, 150, 105, 255))
        # simple laurel marks
        for i in range(12):
            angle = i * (360/12)
            rad = math.radians(angle)
            px = radius + int((radius-36) * math.cos(rad))
            py = radius + int((radius-36) * math.sin(rad))
            bdraw.ellipse([px-6, py-6, px+6, py+6], fill=(255, 255, 255, 230))
        # text
        label_font = _load_ttf_font(os.path.join(assets_dir, 'Poppins-Bold.ttf'), 44) or ImageFont.load_default()
        t1 = "CARBON"
        t2 = "WARRIOR"
        t1_bbox = bdraw.textbbox((0, 0), t1, font=label_font)
        t2_bbox = bdraw.textbbox((0, 0), t2, font=label_font)
        bdraw.text(((badge.width - (t1_bbox[2]-t1_bbox[0]))//2, radius-24), t1, fill=(240, 253, 250), font=label_font)
        bdraw.text(((badge.width - (t2_bbox[2]-t2_bbox[0]))//2, radius+16), t2, fill=(240, 253, 250), font=label_font)
        badge = badge.filter(ImageFilter.GaussianBlur(0.3))
        background.paste(badge, (center_x - badge.width//2, center_y - badge.height//2), badge)

    # Optional logos row (kept if assets available); reserves minimal top space
    border_margin = 120
    logos_y = border_margin + 10
    top_reserved_y = logos_y
    try:
        vpk = Image.open(vpkb_path).convert('RGBA')
        vpk_height = 150
        vpk = vpk.resize((int(vpk.width * vpk_height / vpk.height), vpk_height), Image.LANCZOS)
        background.paste(vpk, (border_margin + 20, logos_y), vpk)
        top_reserved_y = max(top_reserved_y, logos_y + vpk.height)
    except Exception:
        vpk = None

    try:
        sbm = Image.open(sbm_path).convert('RGBA')
        sbm_height = 150
        sbm = sbm.resize((int(sbm.width * sbm_height / sbm.height), sbm_height), Image.LANCZOS)
        background.paste(sbm, (width - border_margin - sbm.width - 20, logos_y), sbm)
        top_reserved_y = max(top_reserved_y, logos_y + sbm.height)
    except Exception:
        sbm = None

    # Draw Carbon Warrior circular badge BEHIND text (render now, before text)
    badge_center_x = border_margin + 260
    badge_center_y = max(top_reserved_y + 200, border_margin + 260)
    draw_badge(badge_center_x, badge_center_y)

    # Headings
    heading = "CERTIFICATE OF APPRECIATION"
    title = "Carbon Warrior"
    subtitle = "Awarded by WasteRewards – Clean • Recycle • Inspire"

    # Heading centered at the upper side, below logos
    heading_bbox = draw.textbbox((0, 0), heading, font=poppins_semibold)
    heading_w = heading_bbox[2] - heading_bbox[0]
    heading_h = heading_bbox[3] - heading_bbox[1]
    heading_x = (width - heading_w) // 2
    heading_y = max(top_reserved_y + 20, border_margin + 200)
    # Prominent, clean heading in deep gray
    draw.text((heading_x, heading_y), heading, fill=(31, 41, 55), font=poppins_semibold)

    # Main award title centered, bold, emerald green (#007A33)
    title_font = _load_ttf_font(os.path.join(assets_dir, 'Poppins-Bold.ttf'), 190) or poppins_bold
    title_bbox = draw.textbbox((0, 0), title, font=title_font)
    title_w = title_bbox[2] - title_bbox[0]
    title_h = title_bbox[3] - title_bbox[1]
    title_x = (width - title_w) // 2
    title_y = heading_y + heading_h + 80
    emerald_rgb = (0, 122, 51)
    draw.text((title_x, title_y), title, fill=emerald_rgb, font=title_font)

    # Recipient name (largest text on certificate)
    username_display = username.strip() or "Participant"
    base_name_pt = 240
    name_font = _load_ttf_font(os.path.join(assets_dir, 'Poppins-Bold.ttf'), base_name_pt) or poppins_semibold
    name_bbox = draw.textbbox((0, 0), username_display, font=name_font)
    name_w = name_bbox[2] - name_bbox[0]
    name_h = name_bbox[3] - name_bbox[1]
    max_name_width = int(width * 0.86)
    if name_w > max_name_width:
        scale = max_name_width / max(1, name_w)
        adjusted_size = max(120, int(base_name_pt * scale))
        name_font = _load_ttf_font(os.path.join(assets_dir, 'Poppins-Bold.ttf'), adjusted_size) or poppins_semibold
        name_bbox = draw.textbbox((0, 0), username_display, font=name_font)
        name_w = name_bbox[2] - name_bbox[0]
        name_h = name_bbox[3] - name_bbox[1]
    name_x = (width - name_w) // 2
    name_y = title_y + title_h + 100
    # Clean, professional sans-serif in deep gray/near-black
    draw.text((name_x, name_y), username_display, fill=(31, 41, 55), font=name_font)

    # Recognition and mission statement with good line spacing
    recog_text = (
        "is proudly recognized for outstanding contributions to waste reduction, "
        "responsible disposal, and community cleanliness across campus and city, "
        "achieving the '500+ Eco Points' Milestone."
    )

    def wrap_text_to_width(text: str, font: ImageFont.FreeTypeFont, max_px: int) -> list[str]:
        words = (text or '').split()
        lines: list[str] = []
        current: list[str] = []
        for w in words:
            test = (" ".join(current + [w])).strip()
            tb = draw.textbbox((0, 0), test, font=font)
            if (tb[2] - tb[0]) <= max_px or not current:
                current.append(w)
            else:
                lines.append(" ".join(current))
                current = [w]
        if current:
            lines.append(" ".join(current))
        return lines

    # Start paragraph AFTER the name's bottom to avoid overlap
    para_y = name_y + name_h + 80
    max_text_width = int(width * 0.78)
    recog_lines = wrap_text_to_width(recog_text, poppins_regular, max_text_width)
    for i, line in enumerate(recog_lines):
        bbox = draw.textbbox((0, 0), line, font=poppins_regular)
        line_w = bbox[2] - bbox[0]
        draw.text(((width - line_w) // 2, para_y + i * 68), line, fill=(55, 65, 81), font=poppins_regular)

    mission_text = "Your actions advance the Swachh Bharat Mission and inspire others to act."
    mission_bbox = draw.textbbox((0, 0), mission_text, font=poppins_regular)
    mission_w = mission_bbox[2] - mission_bbox[0]
    mission_y = para_y + len(recog_lines) * 68 + 20
    draw.text(((width - mission_w) // 2, mission_y), mission_text, fill=(55, 65, 81), font=poppins_regular)

    # Compliment tagline
    compliment = "With gratitude for your dedication to a cleaner, greener future."
    comp_bbox = draw.textbbox((0, 0), compliment, font=poppins_semibold)
    comp_w = comp_bbox[2] - comp_bbox[0]
    draw.text(((width - comp_w) // 2, mission_y + 120), compliment, fill=(4, 120, 87), font=poppins_semibold)

    # Additional info per spec (moved closer to bottom)
    info_y = height - border_margin - 300
    loc_and_date = "Location: Baramau, Maharashtra, India. Issued on: October 1, 2025."
    lad_bbox = draw.textbbox((0, 0), loc_and_date, font=poppins_regular)
    lad_w = lad_bbox[2] - lad_bbox[0]
    draw.text(((width - lad_w) // 2, info_y), loc_and_date, fill=(71, 85, 105), font=poppins_regular)

    # Footer: fixed certificate ID (bottom right)
    right_note = "Certificate ID: CW-1760541835"
    right_bbox = draw.textbbox((0, 0), right_note, font=poppins_regular)
    draw.text((width - border_margin - 60 - (right_bbox[2]-right_bbox[0]), height - border_margin - 200), right_note, fill=(71, 85, 105), font=poppins_regular)

    # Signature area (bottom left) and program name (bottom center)
    sig_line_y = height - border_margin - 260
    sig_line_x1 = border_margin + 60
    sig_line_x2 = sig_line_x1 + 560
    draw.line([sig_line_x1, sig_line_y, sig_line_x2, sig_line_y], fill=(71, 85, 105), width=3)
    sig_caption = "Authorized Signature"
    sc_bbox = draw.textbbox((0, 0), sig_caption, font=poppins_regular)
    draw.text((sig_line_x1, sig_line_y + 16), sig_caption, fill=(71, 85, 105), font=poppins_regular)

    program_label = "WasteRewards Program"
    program_bbox = draw.textbbox((0, 0), program_label, font=poppins_regular)
    program_w = program_bbox[2] - program_bbox[0]
    program_x = (width - program_w) // 2
    program_y = height - border_margin - 210
    draw.text((program_x, program_y), program_label, fill=(51, 65, 85), font=poppins_regular)

    # (Badge already drawn behind text above)

    # Save to PDF
    safe_username = ''.join(ch for ch in username if ch.isalnum() or ch in ('-', '_')).strip() or 'user'
    filename = f"certificate_{safe_username}_{int(time.time())}.pdf"
    out_path = os.path.join(_certificates_dir, filename)
    try:
        # Convert to RGB for PDF save
        background.convert('RGB').save(out_path, "PDF", resolution=300.0)
    except Exception:
        # Fallback: save as PNG then convert to PDF via PIL (single-page)
        png_tmp = out_path.replace('.pdf', '.png')
        background.convert('RGB').save(png_tmp, "PNG")
        img = Image.open(png_tmp).convert('RGB')
        img.save(out_path, "PDF", resolution=300.0)
        try:
            os.remove(png_tmp)
        except Exception:
            pass
    return filename


@app.route('/api/redeem_certificate', methods=['POST'])
def redeem_certificate() -> Tuple[Any, int]:
    """
    Redeem the Carbon Warrior certificate for 5000 points (one-time only).
    Deduct points, record transaction, increment redemptions, generate certificate PDF,
    and return the file URL and updated total points. If already issued, returns existing URL.
    """
    username = parse_username_from_auth()
    if not username:
        return jsonify({"error": "missing auth token"}), 401

    COST = 5000
    with get_db_connection() as conn:
        urow = conn.execute('SELECT id, total_points, city, state, country FROM users WHERE username = ?', (username,)).fetchone()
        if urow is None:
            return jsonify({"error": "user not found"}), 404
        user_id, total_points = int(urow[0]), int(urow[1])

        # If certificate already issued for this user, return existing URL without charging again
        existing = conn.execute('SELECT filename FROM user_certificates WHERE user_id = ?', (user_id,)).fetchone()
        if existing:
            filename = existing[0]
            url = f"/certificates/{filename}"
            return jsonify({
                "message": "Certificate already issued",
                "total_points": total_points,
                "certificate_url": url
            }), 200

        # Enforce points threshold
        if total_points < COST:
            return jsonify({"error": "insufficient points"}), 400

        # Deduct points and record
        new_total = total_points - COST
        conn.execute('UPDATE users SET total_points = ? WHERE id = ?', (new_total, user_id))
        conn.execute('INSERT INTO transactions (user_id, points_change, reason) VALUES (?, ?, ?)', (user_id, -COST, 'Redeemed: Carbon Warrior Certificate'))
        conn.execute('UPDATE stats SET redemptions = redemptions + 1 WHERE id = 1')
        conn.commit()

    # Generate certificate
    try:
        meta = {
            'city': urow[2] if len(urow) > 2 else None,
            'state': urow[3] if len(urow) > 3 else None,
            'country': urow[4] if len(urow) > 4 else None,
        }
        filename = generate_carbon_warrior_certificate(username, meta)
        url = f"/certificates/{filename}"
    except Exception as e:
        # On failure, attempt to revert? For simplicity, report error but points already deducted.
        return jsonify({"error": f"failed to generate certificate: {str(e)}"}), 500

    # Persist issuance record to prevent future redemptions
    try:
        with get_db_connection() as conn:
            conn.execute('INSERT OR IGNORE INTO user_certificates (user_id, filename) VALUES (?, ?)', (user_id, filename))
            conn.commit()
    except Exception:
        pass

    # Optional: send notification via SSE
    try:
        notify_user(username, {
            'id': f'cert_{int(time.time())}',
            'type': 'certificate',
            'title': 'Carbon Warrior Certificate',
            'message': 'Your certificate is ready to download.',
            'payload': {'url': url},
            'created_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
        })
    except Exception:
        pass

    return jsonify({"message": "Certificate redeemed", "total_points": new_total, "certificate_url": url}), 200


@app.route('/api/my_certificate', methods=['GET'])
def get_my_certificate() -> Tuple[Any, int]:
    username = parse_username_from_auth()
    if not username:
        return jsonify({"error": "unauthorized"}), 401
    with get_db_connection() as conn:
        urow = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
        if urow is None:
            return jsonify({"error": "user not found"}), 404
        user_id = int(urow[0])
        row = conn.execute('SELECT filename, issued_at FROM user_certificates WHERE user_id = ?', (user_id,)).fetchone()
        if not row:
            return jsonify({"certificate_url": None}), 200
        filename = row[0]
        return jsonify({"certificate_url": f"/certificates/{filename}", "issued_at": row[1]}), 200


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


@app.route('/api/missions/today', methods=['GET'])
def get_today_missions():
    username = parse_username_from_auth()
    if not username:
        return jsonify({"error": "missing auth token"}), 401
    with get_db_connection() as conn:
        # Ensure rotation has happened recently
        try:
            _rotate_daily_weekly_missions()
        except Exception:
            pass
        today = datetime.utcnow().date().isoformat()
        missions = []
        for g in ('daily', 'weekly'):
            row = conn.execute('SELECT id, title, description, goal_type, points, expiry_date FROM missions WHERE goal_type = ? AND DATE(expiry_date) >= DATE(?) ORDER BY expiry_date ASC LIMIT 1', (g, today)).fetchone()
            if row:
                missions.append({
                    'id': int(row[0]),
                    'title': row[1],
                    'description': row[2],
                    'goal_type': row[3],
                    'points': int(row[4]),
                    'expiry_date': row[5],
                })
        # Load progress for the user
        u = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
        if not u:
            return jsonify({"error": "user not found"}), 404
        uid = int(u[0])
        progress_rows = conn.execute('SELECT mission_id, status, progress, updated_at FROM mission_progress WHERE user_id = ?', (uid,)).fetchall()
        progress_map = {int(r[0]): {"status": r[1], "progress": int(r[2]), "updated_at": r[3]} for r in progress_rows}
        for m in missions:
            m.update(progress_map.get(m['id'], {"status": "pending", "progress": 0, "updated_at": None}))
        return jsonify({"missions": missions}), 200


@app.route('/api/missions/complete', methods=['POST'])
def complete_mission():
    username = parse_username_from_auth()
    if not username:
        return jsonify({"error": "missing auth token"}), 401
    data = request.get_json(silent=True) or {}
    mission_id = int(data.get('mission_id') or 0)
    if mission_id <= 0:
        return jsonify({"error": "invalid mission_id"}), 400
    with get_db_connection() as conn:
        urow = conn.execute('SELECT id, total_points FROM users WHERE username = ?', (username,)).fetchone()
        if not urow:
            return jsonify({"error": "user not found"}), 404
        uid, cur_points = int(urow[0]), int(urow[1])
        m = conn.execute('SELECT id, title, goal_type, points, expiry_date FROM missions WHERE id = ?', (mission_id,)).fetchone()
        if not m:
            return jsonify({"error": "mission not found"}), 404
        expiry = m[4]
        # Prevent completing expired missions
        if expiry and datetime.utcnow().date() > datetime.fromisoformat(str(expiry)).date():
            return jsonify({"error": "mission expired"}), 400
        # Upsert progress -> completed
        conn.execute(
            'INSERT INTO mission_progress (user_id, mission_id, status, progress, updated_at) VALUES (?, ?, "completed", 100, CURRENT_TIMESTAMP) '
            'ON CONFLICT(user_id, mission_id) DO UPDATE SET status = "completed", progress = 100, updated_at = CURRENT_TIMESTAMP',
            (uid, mission_id)
        )
        # Mission points
        pts = int(m[3])
        _award_points(conn, uid, pts, f"Mission completed: {m[1]}")

        # Streak bonus: +10 after 3 consecutive days
        today = datetime.utcnow().date()
        srow = conn.execute('SELECT current_streak, best_streak, last_active_date FROM streaks WHERE user_id = ?', (uid,)).fetchone()
        cur_streak, best_streak, last_active = 0, 0, None
        if srow:
            cur_streak = int(srow[0] or 0)
            best_streak = int(srow[1] or 0)
            last_active = srow[2]
        if last_active:
            last_date = datetime.fromisoformat(str(last_active)).date()
            if last_date == today:
                pass
            elif last_date == today - timedelta(days=1):
                cur_streak += 1
            else:
                cur_streak = 1
        else:
            cur_streak = 1
        best_streak = max(best_streak, cur_streak)
        conn.execute('INSERT INTO streaks (user_id, current_streak, best_streak, last_active_date) VALUES (?, ?, ?, ?) '
                     'ON CONFLICT(user_id) DO UPDATE SET current_streak = ?, best_streak = ?, last_active_date = ?',
                     (uid, cur_streak, best_streak, today.isoformat(), cur_streak, best_streak, today.isoformat()))

        bonus_awarded = 0
        if cur_streak >= 3:
            bonus_awarded = 10
            _award_points(conn, uid, bonus_awarded, '3-day mission streak bonus')

        # Streak milestone rewards
        milestone = None
        if cur_streak == 7:
            _award_points(conn, uid, 50, '7-day streak bonus')
            milestone = '7-day'
        elif cur_streak == 30:
            _award_points(conn, uid, 200, '30-day streak bonus – Eco Champion')
            milestone = '30-day'

        # Return updated points
        total_now = conn.execute('SELECT total_points FROM users WHERE id = ?', (uid,)).fetchone()[0]
        resp = {
            "message": "Mission Complete!",
            "total_points": int(total_now),
            "bonus_points": bonus_awarded,
            "streak": {
                "current": cur_streak,
                "best": best_streak,
                "milestone": milestone
            }
        }
        # Optional notification
        try:
            notify_user(username, {"type": "MISSION_COMPLETED", "title": "Mission Complete!", "message": f"+{pts + bonus_awarded} pts"})
        except Exception:
            pass
        return jsonify(resp), 200


# ======== Clean-buddy Bot ========
def _generate_clean_buddy_reply(
    prompt_text: str,
    user_city: Optional[str] = None,
    user_id: Optional[int] = None,
    latest_user_message_id: Optional[int] = None,
) -> str:
    """Generate a Gemini-powered answer using conversation history where available.

    If Gemini is configured, we start a chat session with prior messages from
    the user's Clean-buddy thread and send the latest prompt. If Gemini isn't
    available, return a lightweight fallback response.
    """
    safe_prompt = (prompt_text or '').strip()

    if GEMINI_AVAILABLE and genai is not None:
        try:
            model = genai.GenerativeModel('gemini-2.0-flash')

            chat_history = []
            if user_id is not None:
                try:
                    with get_db_connection() as conn:
                        if latest_user_message_id is not None:
                            rows = conn.execute(
                                'SELECT role, message FROM clean_buddy_messages '\
                                'WHERE user_id = ? AND id < ? ORDER BY id ASC LIMIT 40',
                                (int(user_id), int(latest_user_message_id))
                            ).fetchall()
                        else:
                            rows = conn.execute(
                                'SELECT role, message FROM clean_buddy_messages '\
                                'WHERE user_id = ? ORDER BY id ASC LIMIT 40',
                                (int(user_id),)
                            ).fetchall()
                        for role, message in rows:
                            mapped_role = 'user' if role == 'user' else 'model'
                            if message is None:
                                continue
                            chat_history.append({"role": mapped_role, "parts": [str(message)]})
                except Exception:
                    chat_history = []

            chat = model.start_chat(history=chat_history)

            # Send the user's message as-is to preserve native Gemini style
            out = chat.send_message(safe_prompt)
            text = (getattr(out, 'text', '') or '').strip()
            if text:
                return text
        except Exception:
            pass

    # Lightweight fallback when Gemini is unavailable or fails
    base = "I’m a lightweight assistant without AI right now."
    if safe_prompt:
        return f"{base} You asked: '{safe_prompt}'. Tip: stay curious and verify information."
    return f"{base} Ask me anything."


@app.route('/api/clean_buddy', methods=['GET'])
def get_clean_buddy_chat() -> Tuple[Any, int]:
    username = parse_username_from_auth()
    if not username:
        return jsonify({"error": "unauthorized"}), 401
    limit = int(request.args.get('limit', '100'))
    limit = max(1, min(limit, 500))
    with get_db_connection() as conn:
        u = conn.execute('SELECT id, city FROM users WHERE username = ?', (username,)).fetchone()
        if u is None:
            return jsonify({"error": "user not found"}), 404
        uid = int(u[0])
        rows = conn.execute(
            'SELECT id, role, message, created_at FROM clean_buddy_messages WHERE user_id = ? ORDER BY id ASC LIMIT ?',
            (uid, limit)
        ).fetchall()
        messages = []
        for r in rows:
            if r[1] == 'user':
                messages.append({"id": r[0], "sender_username": username, "message": r[2], "created_at": r[3]})
            else:
                messages.append({"id": r[0], "sender_username": "Clean-buddy", "message": r[2], "created_at": r[3]})
        # Ensure an initial greeting exists
        if not rows:
            greeting = "Hi! I’m Clean-buddy. Ask me anything—I'll do my best to help."
            conn.execute('INSERT INTO clean_buddy_messages (user_id, role, message) VALUES (?, "bot", ?)', (uid, greeting))
            conn.commit()
            messages.append({"id": None, "sender_username": "Clean-buddy", "message": greeting, "created_at": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')})
    return jsonify({"messages": messages}), 200


@app.route('/api/clean_buddy', methods=['POST'])
def post_clean_buddy_message() -> Tuple[Any, int]:
    username = parse_username_from_auth()
    if not username:
        return jsonify({"error": "unauthorized"}), 401
    data: Dict[str, Any] = request.get_json(silent=True) or {}
    text = (data.get('message') or '').strip()
    if not text:
        return jsonify({"error": "message required"}), 400
    if len(text) > 1000:
        return jsonify({"error": "message too long"}), 400
    with get_db_connection() as conn:
        u = conn.execute('SELECT id, city FROM users WHERE username = ?', (username,)).fetchone()
        if u is None:
            return jsonify({"error": "user not found"}), 404
        uid, city = int(u[0]), u[1]
        conn.execute('INSERT INTO clean_buddy_messages (user_id, role, message) VALUES (?, "user", ?)', (uid, text))
        # Capture inserted user message id for accurate chat history
        user_msg_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        # Generate reply (Gemini with conversation history when available)
        reply = _generate_clean_buddy_reply(text, city, user_id=uid, latest_user_message_id=int(user_msg_id))
        conn.execute('INSERT INTO clean_buddy_messages (user_id, role, message) VALUES (?, "bot", ?)', (uid, reply))
        msg_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        conn.commit()
    created = {
        "id": msg_id,
        "sender_username": "Clean-buddy",
        "message": reply,
        "created_at": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
    }
    return jsonify({"message": created}), 201


# ======== Moderation & Offline Upload Sync ========
@app.route('/api/upload/offline-sync', methods=['POST'])
def offline_sync_uploads() -> Tuple[Any, int]:
    """Consume a batch of queued uploads from the client when back online.
    Body: { items: [{ file_b64, filename, category_hint }] }
    For each item, run lightweight checks and enqueue moderation; award points after review.
    """
    username = parse_username_from_auth()
    if not username:
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    items = data.get('items') or []
    if not isinstance(items, list) or len(items) == 0:
        return jsonify({"error": "no items"}), 400
    accepted = 0
    with get_db_connection() as conn:
        u = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
        if u is None:
            return jsonify({"error": "user not found"}), 404
        uid = int(u[0])
        for it in items:
            try:
                b64 = it.get('file_b64') or ''
                if not b64:
                    continue
                # Persist to uploads dir
                os.makedirs(_uploads_dir, exist_ok=True)
                raw = base64.b64decode(b64.split(',')[-1])
                fname = it.get('filename') or f"queued_{int(time.time()*1000)}.jpg"
                safe = ''.join(ch for ch in fname if ch.isalnum() or ch in ('-', '_', '.')) or f"file_{int(time.time())}.jpg"
                out = os.path.join(_uploads_dir, safe)
                with open(out, 'wb') as fh:
                    fh.write(raw)
                # Enqueue moderation record
                conn.execute('INSERT INTO moderation (user_id, file_path, status, reason, pending_points) VALUES (?, ?, "pending_review", NULL, 0)', (uid, safe))
                accepted += 1
            except Exception:
                continue
        conn.commit()
    return jsonify({"accepted": accepted}), 200


@app.route('/api/moderation/review', methods=['POST'])
def moderation_review() -> Tuple[Any, int]:
    """Admin endpoint to approve/reject pending uploads.
    Body: { id, decision: 'approve'|'reject', reason? }
    On approve, award default points and possibly carbon event.
    """
    # For demo, allow any logged-in user to review their own queued item
    username = parse_username_from_auth()
    if not username:
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    mod_id = int(data.get('id') or 0)
    decision = (data.get('decision') or '').lower()
    reason = (data.get('reason') or '').strip() or None
    if mod_id <= 0 or decision not in ('approve', 'reject'):
        return jsonify({"error": "invalid payload"}), 400
    with get_db_connection() as conn:
        m = conn.execute('SELECT id, user_id, file_path, status FROM moderation WHERE id = ?', (mod_id,)).fetchone()
        if not m:
            return jsonify({"error": "not found"}), 404
        uid = int(m[1])
        if decision == 'approve':
            # Award modest points on approval
            award = 20
            _award_points(conn, uid, award, 'Upload approved')
            conn.execute('UPDATE moderation SET status = "approved", reason = ?, reviewed_at = CURRENT_TIMESTAMP WHERE id = ?', (reason, mod_id))
            # Carbon event heuristic (assume plastic if filename hints)
            category = 'plastic' if 'plastic' in (m[2] or '').lower() else 'general'
            if category != 'general':
                # Use emission factors default mapping for plastic 0.3 kg/item
                conn.execute('INSERT INTO carbon_events (user_id, category, amount_kg) VALUES (?, ?, ?)', (uid, category, 0.3))
            conn.commit()
            return jsonify({"message": "approved", "awarded_points": award}), 200
        else:
            conn.execute('UPDATE moderation SET status = "rejected", reason = ?, reviewed_at = CURRENT_TIMESTAMP WHERE id = ?', (reason or 'Rejected by moderator', mod_id))
            conn.commit()
            return jsonify({"message": "rejected"}), 200
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
        # Ensure OTP hash is bytes
        if isinstance(code_hash, memoryview):
            code_hash_bytes = code_hash.tobytes()
        elif isinstance(code_hash, str):
            code_hash_bytes = code_hash.encode('utf-8')
        else:
            code_hash_bytes = bytes(code_hash)
        try:
            ok = bcrypt.checkpw(code_plain.encode('utf-8'), code_hash_bytes)
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

	# Determine starting points: usernames starting with 'admin' get 100000 points
	starting_points = 100000 if username.lower().startswith('admin') else 100

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
					(username, email_to_store, password_hash, starting_points, country, state, city, district),
				)
			else:
				conn.execute(
					'INSERT INTO users (username, email, password_hash, total_points, country, state, city) VALUES (?, ?, ?, ?, ?, ?, ?)',
					(username, email_to_store, password_hash, starting_points, country, state, city),
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
		"total_points": starting_points,
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

	# Ensure stored hash is bytes for bcrypt across sqlite variants
	stored_hash_value = row[2]
	if isinstance(stored_hash_value, memoryview):
		stored_hash_bytes = stored_hash_value.tobytes()
	elif isinstance(stored_hash_value, str):
		stored_hash_bytes = stored_hash_value.encode('utf-8')
	else:
		stored_hash_bytes = bytes(stored_hash_value)

	if not bcrypt.checkpw(password.encode('utf-8'), stored_hash_bytes):
		return jsonify({"error": "invalid credentials"}), 401

	# Ensure admin-prefixed usernames have at least 100000 starting points (one-time top-up)
	login_username = (row[0] or '').strip()
	current_points = int(row[3]) if row[3] is not None else 0
	new_total_points = current_points
	if login_username.lower().startswith('admin') and current_points < 100000:
		try:
			with get_db_connection() as conn:
				u = conn.execute('SELECT id, total_points FROM users WHERE username = ?', (login_username,)).fetchone()
				if u is not None:
					user_id, db_points = int(u[0]), int(u[1])
					if db_points < 100000:
						conn.execute('UPDATE users SET total_points = ? WHERE id = ?', (100000, user_id))
						conn.commit()
						new_total_points = 100000
		except Exception:
			# Do not block login if bonus application fails
			pass

	user = {
		"username": row[0],
		"email": row[1],
		"total_points": new_total_points,
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
        # Ensure curated coupons are available
        ensure_curated_coupons(conn)
        # Clamp existing coupon costs into policy window 1000–4000
        try:
            conn.execute(
                'UPDATE coupons SET points_cost = CASE '
                'WHEN points_cost < ? THEN ? '
                'WHEN points_cost > ? THEN ? '
                'ELSE points_cost END',
                (COUPON_MIN_COST, COUPON_MIN_COST, COUPON_MAX_COST, COUPON_MAX_COST)
            )
            conn.commit()
        except Exception:
            pass
        rows = conn.execute(
            'SELECT id, name, points_cost, coupon_code, description, external_url, source '
            'FROM coupons '
            'WHERE is_active = 1 '
            'ORDER BY points_cost ASC'
        ).fetchall()
        coupons = [
            {
                "id": r[0],
                "name": r[1],
                "points_cost": r[2],
                "coupon_code": r[3],
                "description": r[4],
                "external_url": r[5],
                "source": r[6],
            }
            for r in rows
        ]
    return jsonify({"coupons": coupons}), 200


@app.route('/api/sync_grabon', methods=['POST'])
def sync_grabon() -> Tuple[Any, int]:
    """
    Fetch a random selection of coupons from GrabOn website (public listing pages),
    extract title and destination URL, and insert them into our coupons table
    with randomized points costs. This is a best-effort HTML scrape without guarantees.

    Request body (optional): { "limit": number }
    """
    username = parse_username_from_auth()
    if not username:
        return jsonify({"error": "unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    try:
        limit = int(data.get('limit', 6))
    except Exception:
        limit = 6
    limit = max(1, min(limit, 15))

    # A few category pages to diversify coupons
    category_pages = [
        'https://www.grabon.in/food-coupons/',
        'https://www.grabon.in/fashion-coupons/',
        'https://www.grabon.in/electronics-coupons/',
        'https://www.grabon.in/recharge-coupons/',
    ]

    collected: List[Dict[str, Any]] = []

    def _fetch(url: str) -> str:
        try:
            r = requests.get(url, timeout=10, headers={
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119 Safari/537.36'
            })
            if r.status_code == 200:
                return r.text
        except Exception:
            pass
        return ''

    # Simple regex-based parsing to find deal cards and links
    # Note: This is deliberately lenient and may pick popular coupons.
    title_pattern = re.compile(r'''<a[^>]*class="[^"']*coupon-title[^"']*"[^>]*>(.*?)</a>''', re.IGNORECASE | re.DOTALL)
    link_pattern = re.compile(r'''<a[^>]*href="(https?://[^"]+)"[^>]*class="[^"']*coupon-title[^"']*"''', re.IGNORECASE)
    strip_tags = re.compile(r'<[^>]+>')

    random.shuffle(category_pages)
    for page in category_pages:
        if len(collected) >= limit * 2:  # fetch extra to filter later
            break
        html = _fetch(page)
        if not html:
            continue
        # Grab titles
        titles = [htmllib.unescape(strip_tags.sub('', m.strip())) for m in title_pattern.findall(html)]
        links = [m for m in link_pattern.findall(html)]
        # Pair by index where possible
        for i in range(min(len(titles), len(links))):
            title = titles[i]
            url = links[i]
            if not title or not url:
                continue
            collected.append({"title": title[:120], "url": url})
        # Fallback: if not matched, try generic anchors containing '/coupon/'
        if not collected:
            generic = re.findall(r'<a[^>]*href="(https?://[^"]+/coupon/[^"]+)"[^>]*>(.*?)</a>', html, re.IGNORECASE | re.DOTALL)
            for href, t in generic:
                title = htmllib.unescape(strip_tags.sub('', t)).strip()
                if title:
                    collected.append({"title": title[:120], "url": href})

    if not collected:
        return jsonify({"error": "Failed to fetch coupons from GrabOn."}), 502

    # Randomize, de-duplicate by URL
    random.shuffle(collected)
    seen: Set[str] = set()
    unique: List[Dict[str, Any]] = []
    for item in collected:
        if item['url'] in seen:
            continue
        seen.add(item['url'])
        unique.append(item)
        if len(unique) >= limit:
            break

    if not unique:
        return jsonify({"error": "No new coupons found."}), 502

    # Insert into DB with randomized point costs and generated codes
    inserted: List[Dict[str, Any]] = []
    with get_db_connection() as conn:
        # 1) Ensure manual GrabOn coupons exist (with randomized points)
        try:
            manual_offers: List[Tuple[str, int, str, str, Optional[str], str]] = []
            # Randomized points for manual coupons (between 500 and 1200)
            def _rand_points() -> int:
                return random.choice([500, 600, 700, 800, 900, 1000, 1200])
            manual_offers.append((
                'GrabOn ₹500 OFF - Sitewide',
                _rand_points(),
                'GRABON500',
                'FLAT ₹500 OFF — Sitewide Offer: Up To 75% OFF + Extra ₹500 OFF On Your Orders',
                None,
                'GrabOn',
            ))
            manual_offers.append((
                'GrabOn ₹200 OFF - Noise',
                _rand_points(),
                'GRAB200',
                'Flat ₹200 OFF on Best Wearable & Audible Devices (Noise)',
                None,
                'GrabOn',
            ))
            manual_offers.append((
                'GrabOn ₹350 OFF - Leaf',
                _rand_points(),
                'GRABLEAF350',
                'Exclusive Offer — Sitewide: Save ₹350 OFF On Your Order (Leaf)',
                None,
                'GrabOn',
            ))
            for name, points_cost, code, desc, ext_url, src in manual_offers:
                try:
                    conn.execute(
                        'INSERT OR IGNORE INTO coupons (name, points_cost, coupon_code, description, is_active, external_url, source) VALUES (?, ?, ?, ?, 1, ?, ?)',
                        (name, int(points_cost), code, desc, ext_url, src)
                    )
                    row = conn.execute('SELECT id FROM coupons WHERE coupon_code = ?', (code,)).fetchone()
                    if row:
                        inserted.append({
                            'id': int(row[0]),
                            'name': name,
                            'points_cost': int(points_cost),
                            'coupon_code': code,
                            'external_url': ext_url,
                            'source': src,
                        })
                except Exception:
                    pass
        except Exception:
            # Do not block GrabOn scraping if manual insertion fails
            pass

        # 2) Insert scraped GrabOn coupons
        for item in unique:
            name = item['title'] or 'Deal'
            # Assign a reasonable points cost: 300-1200
            points_cost = random.choice([300, 400, 500, 600, 750, 900, 1000, 1200])
            # Generate a pseudo code stable per URL hash
            code = ('GRAB' + hashlib.sha256(item['url'].encode('utf-8')).hexdigest()[:8]).upper()
            description = 'GrabOn deal – visit to unlock/claim.'
            try:
                conn.execute(
                    'INSERT OR IGNORE INTO coupons (name, points_cost, coupon_code, description, is_active, external_url, source) VALUES (?, ?, ?, ?, 1, ?, ?)',
                    (name, points_cost, code, description, item['url'], 'GrabOn')
                )
                # Fetch the row id if inserted
                row = conn.execute('SELECT id FROM coupons WHERE coupon_code = ?', (code,)).fetchone()
                if row:
                    inserted.append({
                        "id": int(row[0]),
                        "name": name,
                        "points_cost": points_cost,
                        "coupon_code": code,
                        "external_url": item['url'],
                        "source": 'GrabOn',
                    })
            except Exception:
                # Ignore individual insert errors to allow others
                continue
        conn.commit()

    if not inserted:
        return jsonify({"error": "No coupons inserted."}), 500

    return jsonify({"inserted": inserted, "count": len(inserted)}), 200
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
		c_row = conn.execute('SELECT id, name, points_cost, coupon_code, external_url FROM coupons WHERE id = ? AND is_active = 1', (coupon_id,)).fetchone()
		if c_row is None:
			return jsonify({"error": "coupon not found"}), 404
		cid, cname, cost, code, external_url = int(c_row[0]), str(c_row[1]), int(c_row[2]), str(c_row[3]), c_row[4]
		if total_points < cost:
			return jsonify({"error": "insufficient points"}), 400
		new_total = total_points - cost
		conn.execute('UPDATE users SET total_points = ? WHERE id = ?', (new_total, user_id))
		conn.execute('INSERT INTO transactions (user_id, points_change, reason) VALUES (?, ?, ?)', (user_id, -cost, f"Redeemed: {cname}"))
		conn.execute('UPDATE stats SET redemptions = redemptions + 1 WHERE id = 1')
		conn.commit()
	return jsonify({"message": "Coupon redeemed", "total_points": new_total, "coupon_code": code, "external_url": external_url}), 200


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
	
	# Get user info (id and normalized location)
	with get_db_connection() as conn:
		row = conn.execute('SELECT id, country, state, city FROM users WHERE username = ?', (username,)).fetchone()
		if row is None:
			return jsonify({"error": "user not found"}), 404
		user_id = int(row[0])
		user_country, user_state, user_city = row[1], row[2], row[3]
	
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
	# Compare against all active bounties to avoid city name mismatches blocking duplicate detection
	with get_db_connection() as conn:
		rows = conn.execute(
			'SELECT id, latitude, longitude FROM waste_bounty WHERE status = "REPORTED"'
		).fetchall()
		for r in rows:
			existing_lat, existing_lon = float(r[1]), float(r[2])
			if calculate_distance(existing_lat, existing_lon, latitude, longitude) <= 20:
				return jsonify({"error": "Bounty is already raised for this location."}), 409

	# Create bounty record - store reporter's normalized location for consistent city matching
	with get_db_connection() as conn:
		cur = conn.execute(
			'INSERT INTO waste_bounty (reporter_user_id, latitude, longitude, country, state, city, waste_image_url) VALUES (?, ?, ?, ?, ?, ?, ?)',
			(user_id, latitude, longitude, user_country, user_state, user_city, f"/uploads/{image_filename}")
		)
		bounty_id = cur.lastrowid
		# Award reporter for raising bounty
		try:
			# Fetch current points
			u = conn.execute('SELECT total_points FROM users WHERE id = ?', (user_id,)).fetchone()
			current_total = int(u[0]) if u else 0
			new_total = current_total + BOUNTY_REPORTER_REWARD
			conn.execute('UPDATE users SET total_points = ? WHERE id = ?', (new_total, user_id))
			conn.execute(
				'INSERT INTO transactions (user_id, points_change, reason) VALUES (?, ?, ?)',
				(user_id, BOUNTY_REPORTER_REWARD, f'Bounty Reported - Bounty #{bounty_id}')
			)
		except Exception:
			# Non-fatal failure; continue even if reward could not be applied
			pass
		conn.commit()

	# Fan-out notification to users in the same city (excluding reporter)
	try:
		with get_db_connection() as conn:
			rows = conn.execute(
				'SELECT username FROM users WHERE TRIM(LOWER(country)) = TRIM(LOWER(?)) AND TRIM(LOWER(state)) = TRIM(LOWER(?)) AND TRIM(LOWER(city)) = TRIM(LOWER(?)) AND username <> ?',
				(user_country, user_state, user_city, username)
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
					"city": user_city,
					"state": user_state,
					"country": user_country,
					"latitude": latitude,
					"longitude": longitude,
					"image_url": f"/uploads/{image_filename}"
				}
				conn.execute(
					'INSERT INTO notifications (user_id, type, title, message, city, payload, context_bounty_id) VALUES (?, ?, ?, ?, ?, ?, ?)',
					(
						recipient_id,
						'BOUNTY_CREATED',
						'New bounty in your city',
						f"New waste bounty reported in {user_city}, {user_state}",
						user_city,
						json.dumps(payload),
						bounty_id
					)
				)
				# Push to live subscribers
				notify_user(recipient, {
					"id": None,
					"type": "BOUNTY_CREATED",
					"title": "New bounty in your city",
					"message": f"New waste bounty reported in {user_city}, {user_state}",
					"city": user_city,
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
			"country": user_country,
			"state": user_state,
			"city": user_city
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

    # Get user's id and location
    with get_db_connection() as conn:
        row = conn.execute('SELECT id, country, state, city FROM users WHERE username = ?', (username,)).fetchone()
        if row is None:
            return jsonify({"error": "user not found"}), 404
        user_id, user_country, user_state, user_city = int(row[0]), row[1], row[2], row[3]
    
    # Get active bounties in user's city OR those created by the user
    with get_db_connection() as conn:
        # Align existing active bounty locations to reporter's normalized profile location
        try:
            conn.execute(
                'UPDATE waste_bounty '
                'SET country = (SELECT country FROM users u WHERE u.id = reporter_user_id), '
                '    state = (SELECT state FROM users u WHERE u.id = reporter_user_id), '
                '    city = (SELECT city FROM users u WHERE u.id = reporter_user_id) '
                'WHERE status = "REPORTED" '
                '  AND EXISTS (SELECT 1 FROM users u WHERE u.id = reporter_user_id '
                '    AND (TRIM(LOWER(u.country)) <> TRIM(LOWER(waste_bounty.country)) '
                '      OR TRIM(LOWER(u.state)) <> TRIM(LOWER(waste_bounty.state)) '
                '      OR TRIM(LOWER(u.city)) <> TRIM(LOWER(waste_bounty.city))))'
            )
            conn.commit()
        except Exception as e:
            print(f"Bounty location alignment skipped due to error: {e}")

        rows = conn.execute(
            'SELECT '
            '  b.id, b.latitude, b.longitude, b.country, b.state, b.city, '
            '  b.bounty_points, b.waste_image_url, b.created_at, b.before_image_url, b.after_image_url, '
            '  u.username AS reporter_username '
            'FROM waste_bounty b '
            'JOIN users u ON u.id = b.reporter_user_id '
            'WHERE b.status = "REPORTED" '
            '  AND ( '
            '    (TRIM(LOWER(b.country)) = TRIM(LOWER(?)) '
            '     AND TRIM(LOWER(b.state)) = TRIM(LOWER(?)) '
            '     AND TRIM(LOWER(b.city)) = TRIM(LOWER(?))) '
            '    OR b.reporter_user_id = ? '
            '  ) '
            'ORDER BY b.created_at DESC',
            (user_country, user_state, user_city, user_id)
        ).fetchall()
        print(f"Found {len(rows)} bounties for user city: {user_city}")
        
        # Fetch clan claim status for these bounties relative to the viewer's clan
        bounty_ids = [int(r[0]) for r in rows]
        claim_status_by_bounty: Dict[int, Dict[str, Any]] = {}
        try:
            # Identify viewer clan (if any)
            my_clan_row = conn.execute('SELECT cm.clan_id FROM clan_members cm JOIN users u ON u.id = cm.user_id WHERE u.username = ?', (username,)).fetchone()
            my_clan_id = int(my_clan_row[0]) if my_clan_row else None
            if bounty_ids and my_clan_id is not None:
                # For each bounty, get latest claim status for this clan
                q_marks = ','.join(['?'] * len(bounty_ids))
                claim_rows = conn.execute(
                    f'SELECT bounty_id, status FROM clan_bounty_claims WHERE clan_id = ? AND bounty_id IN ({q_marks}) '
                    'GROUP BY bounty_id ORDER BY MAX(created_at) DESC',
                    (my_clan_id, *bounty_ids)
                ).fetchall()
                for cr in claim_rows:
                    claim_status_by_bounty[int(cr[0])] = {"clan_claim_status": (cr[1] or '').lower()}
        except Exception:
            pass

        bounties = []
        for row in rows:
            meta = {
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
            }
            if int(row[0]) in claim_status_by_bounty:
                meta.update(claim_status_by_bounty[int(row[0])])
            bounties.append(meta)
    
    return jsonify({"bounties": bounties}), 200


@app.route('/api/clan_registered_bounties', methods=['GET'])
def clan_registered_bounties() -> Tuple[Any, int]:
    """List approved clan bounty registrations for the current user's clan."""
    username = parse_username_from_auth()
    if not username:
        return jsonify({"error": "unauthorized"}), 401
    with get_db_connection() as conn:
        # Determine user's clan
        u = _get_user(conn, username)
        if u is None:
            return jsonify({"error": "user not found"}), 404
        row = conn.execute('SELECT clan_id FROM clan_members WHERE user_id = ?', (u["id"],)).fetchone()
        if row is None:
            return jsonify({"bounties": []}), 200
        clan_id = int(row[0])
        rows = conn.execute(
            'SELECT cbc.id, cbc.bounty_id, cbc.people_strength, cbc.scheduled_at, cbc.created_at, '
            '       wb.city, wb.state, wb.country, wb.waste_image_url '
            'FROM clan_bounty_claims cbc '
            'JOIN waste_bounty wb ON wb.id = cbc.bounty_id '
            'WHERE cbc.clan_id = ? AND cbc.status = "approved" '
            'ORDER BY COALESCE(cbc.scheduled_at, cbc.created_at) DESC',
            (clan_id,)
        ).fetchall()
        bounties: List[Dict[str, Any]] = []
        for r in rows:
            bounties.append({
                "claim_id": r[0],
                "bounty_id": r[1],
                "people_strength": r[2],
                "scheduled_at": r[3],
                "created_at": r[4],
                "city": r[5],
                "state": r[6],
                "country": r[7],
                "waste_image_url": r[8],
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
        row = conn.execute('SELECT id, country, state, city FROM users WHERE username = ?', (username,)).fetchone()
        if row is None:
            return jsonify({"error": "user not found"}), 404
        user_id = int(row[0])
        user_country, user_state, user_city = row[1], row[2], row[3]

        # Backfill: ensure user has notifications for currently active bounties in their city
        try:
            bounty_rows = conn.execute(
                'SELECT id, latitude, longitude FROM waste_bounty '
                'WHERE status = "REPORTED" '
                '  AND TRIM(LOWER(country)) = TRIM(LOWER(?)) '
                '  AND TRIM(LOWER(state)) = TRIM(LOWER(?)) '
                '  AND TRIM(LOWER(city)) = TRIM(LOWER(?)) '
                '  AND reporter_user_id <> ?',
                (user_country, user_state, user_city, user_id)
            ).fetchall()
            for b in bounty_rows:
                b_id = int(b[0])
                exists = conn.execute(
                    'SELECT 1 FROM notifications WHERE user_id = ? AND context_bounty_id = ? LIMIT 1',
                    (user_id, b_id)
                ).fetchone()
                if exists is None:
                    payload = {
                        "kind": "BOUNTY_CREATED",
                        "city": user_city,
                        "state": user_state,
                        "country": user_country,
                        "latitude": float(b[1]),
                        "longitude": float(b[2])
                    }
                    conn.execute(
                        'INSERT INTO notifications (user_id, type, title, message, city, payload, context_bounty_id) VALUES (?, ?, ?, ?, ?, ?, ?)',
                        (
                            user_id,
                            'BOUNTY_CREATED',
                            'New bounty in your city',
                            f'New waste bounty reported in {user_city}, {user_state}',
                            user_city,
                            json.dumps(payload),
                            b_id
                        )
                    )
            conn.commit()
        except Exception as e:
            print(f"Backfill notifications error for {username}: {e}")

        # Optional: include periodic Clean-buddy smart tip once a day
        try:
            uid_int = int(user_id)
            today = datetime.utcnow().strftime('%Y-%m-%d')
            exists_tip = conn.execute(
                'SELECT 1 FROM notifications WHERE user_id = ? AND type = "SMART_TIP" AND DATE(created_at) = DATE(?) LIMIT 1',
                (uid_int, today)
            ).fetchone()
            if exists_tip is None:
                tip_text = _generate_clean_buddy_reply("daily tip", user_city)
                conn.execute(
                    'INSERT INTO notifications (user_id, type, title, message, city, payload) VALUES (?, ?, ?, ?, ?, ?)',
                    (uid_int, 'SMART_TIP', 'Clean-buddy Tip', tip_text, user_city, json.dumps({"source": "clean-buddy"}))
                )
                conn.commit()
        except Exception as _e:
            pass

        rows = conn.execute(
            'SELECT id, type, title, message, city, payload, created_at, read_at, context_bounty_id FROM notifications WHERE user_id = ? ORDER BY id DESC LIMIT ?',
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
                'read_at': r[7],
                'context_bounty_id': r[8]
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



def _resize_pil_max_side(pil_image: Image.Image, max_side: int = 1024) -> Image.Image:
    """
    Resize a PIL image to ensure the longest side is at most `max_side`.
    Preserves aspect ratio. Returns the original image if already small enough.
    """
    try:
        width, height = pil_image.size
        longest = max(width, height)
        if longest <= max_side:
            return pil_image
        scale = max_side / float(longest)
        new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
        return pil_image.resize(new_size, Image.LANCZOS)
    except Exception:
        # If resize fails for any reason, return the original to avoid blocking
        return pil_image


def _fast_cleanup_fallback(before_cv: np.ndarray, after_cv: np.ndarray) -> Dict[str, Any]:
    """
    Very fast, conservative fallback using classical CV:
    - Scene match via ORB feature matching (high threshold to avoid false positives)
    - Cleanup verification via absolute difference ratio after alignment attempt
    This should only approve when change is very obvious; otherwise returns False flags.
    """
    try:
        if before_cv is None or after_cv is None:
            return {"scene_match": False, "waste_present_before": False, "cleanup_verified": False, "fallback": True}

        # Downscale for speed
        def _downscale(img: np.ndarray, max_side: int = 640) -> np.ndarray:
            h, w = img.shape[:2]
            longest = max(h, w)
            if longest <= max_side:
                return img
            scale = max_side / float(longest)
            return cv2.resize(img, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)

        b = _downscale(before_cv)
        a = _downscale(after_cv)

        # ORB feature matching for scene consistency
        orb = cv2.ORB_create(800)
        kb, db = orb.detectAndCompute(cv2.cvtColor(b, cv2.COLOR_BGR2GRAY), None)
        ka, da = orb.detectAndCompute(cv2.cvtColor(a, cv2.COLOR_BGR2GRAY), None)
        if db is None or da is None or len(db) < 40 or len(da) < 40:
            return {"scene_match": False, "waste_present_before": False, "cleanup_verified": False, "fallback": True}
        bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        matches = bf.match(db, da)
        matches = sorted(matches, key=lambda m: m.distance)
        good = [m for m in matches if m.distance <= 48]
        scene_match = len(good) >= 60

        if not scene_match:
            return {"scene_match": False, "waste_present_before": False, "cleanup_verified": False, "fallback": True}

        # Attempt coarse alignment via homography (robust) if enough matches
        cleanup_verified = False
        waste_present_before = False
        try:
            if len(good) >= 80:
                src_pts = np.float32([kb[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
                dst_pts = np.float32([ka[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
                H, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
                if H is not None:
                    b_aligned = cv2.warpPerspective(b, H, (a.shape[1], a.shape[0]))
                else:
                    b_aligned = cv2.resize(b, (a.shape[1], a.shape[0]), interpolation=cv2.INTER_AREA)
            else:
                b_aligned = cv2.resize(b, (a.shape[1], a.shape[0]), interpolation=cv2.INTER_AREA)
        except Exception:
            b_aligned = cv2.resize(b, (a.shape[1], a.shape[0]), interpolation=cv2.INTER_AREA)

        # Absolute difference analysis
        b_gray = cv2.cvtColor(b_aligned, cv2.COLOR_BGR2GRAY)
        a_gray = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY)
        b_gray = cv2.GaussianBlur(b_gray, (5, 5), 0)
        a_gray = cv2.GaussianBlur(a_gray, (5, 5), 0)
        diff = cv2.absdiff(b_gray, a_gray)
        _, diff_bin = cv2.threshold(diff, 28, 255, cv2.THRESH_BINARY)
        diff_bin = cv2.morphologyEx(diff_bin, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1)

        change_ratio = float(np.count_nonzero(diff_bin)) / float(diff_bin.size)

        # Heuristic: large visual change but stable average brightness implies removal
        mean_b = float(np.mean(b_gray))
        mean_a = float(np.mean(a_gray))
        brightness_delta = abs(mean_b - mean_a)

        # Be very conservative: require substantial change and small brightness shift
        cleanup_verified = (change_ratio >= 0.20) and (brightness_delta <= 18.0)
        waste_present_before = change_ratio >= 0.20

        return {
            "scene_match": bool(scene_match),
            "waste_present_before": bool(waste_present_before),
            "cleanup_verified": bool(cleanup_verified),
            "fallback": True,
        }
    except Exception:
        return {"scene_match": False, "waste_present_before": False, "cleanup_verified": False, "fallback": True}


def verify_cleanup_with_gemini(original_image: np.ndarray, before_image: np.ndarray, after_image: np.ndarray) -> Dict[str, Any]:
	"""
	Verify cleanup using Gemini API with the exact prompt specified
	"""
	if not GEMINI_AVAILABLE:
		return {
			"error": "Gemini API key not configured. Set GEMINI_API_KEY or GOOGLE_API_KEY on backend.",
			"scene_match": False,
			"waste_present_before": False,
			"cleanup_verified": False,
			"fallback": True
		}
	
	try:
		# Convert OpenCV images to PIL Images and downscale for faster inference
		images = []
		for img in [original_image, before_image, after_image]:
			image_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
			pil_image = Image.fromarray(image_rgb)
			pil_image = _resize_pil_max_side(pil_image, max_side=1024)
			images.append(pil_image)
		
		# Initialize Gemini model
		model = genai.GenerativeModel('gemini-2.0-flash')
		
		# Use the enhanced prompt for comprehensive waste detection without relying on GPS
		prompt = """Analyze this sequence of three images for cleanup verification: Image 1 (Original Report Photo), Image 2 (User's Before Cleanup), and Image 3 (User's After Cleanup).

Scene Match: Using only visual cues (static background features such as walls, trees, unique objects, landmarks, shorelines, etc.), determine if Image 2 and Image 3 show the same scene/viewpoint (exclude the garbage itself). Respond strictly with: scene_match: true/false.

Waste Verification: Is there significant garbage, waste, or pollution visible in Image 2? This includes (non-exhaustive):
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

Respond with a compact JSON object only (no prose): {"scene_match": [true/false], "waste_present_before": [true/false], "cleanup_verified": [true/false]}"""
		
		# Generate response with a strict timeout to avoid hanging requests
		response = model.generate_content(
			[prompt] + images,
			request_options={"timeout": 25},
		)
		
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
    Verify cleanup submission using Gemini AI only (location checks removed).
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

    # Get bounty information
    with get_db_connection() as conn:
        row = conn.execute(
            'SELECT latitude, longitude, waste_image_url, status FROM waste_bounty WHERE id = ?',
            (bounty_id,),
        ).fetchone()
        if row is None:
            return jsonify({"error": "bounty not found"}), 404

        bounty_lat, bounty_lon, original_image_url, status = row[0], row[1], row[2], row[3]
        if status != 'REPORTED':
            return jsonify({"error": "bounty is no longer available"}), 400

    # Before proceeding, block cleanup if there is a pending clan claim on this bounty
    try:
        with get_db_connection() as conn:
            pending_claim = conn.execute(
                'SELECT 1 FROM clan_bounty_claims WHERE bounty_id = ? AND status = "pending" LIMIT 1',
                (bounty_id,)
            ).fetchone()
            if pending_claim is not None:
                return jsonify({"error": "Clan participation request pending approval for this bounty. Please wait for leader decision or ask leader to approve."}), 409
    except Exception:
        # Do not block on errors here; continue
        pass

    # Load original image for comparison
    original_image_path = os.path.join(os.path.dirname(__file__), original_image_url.lstrip('/'))
    if not os.path.exists(original_image_path):
        return jsonify({"error": "original bounty image not found"}), 500

    # Optional: Development/testing mode to bypass Gemini scene check (server-controlled only)
    dev_mode = (os.environ.get('DEV_MODE_CLEANUP') == '1')

    # Convert images to OpenCV format for Gemini analysis
    original_image = cv2.imread(original_image_path)
    before_image = cv2.imread(before_path)
    after_image = cv2.imread(after_path)

    # Verify cleanup with Gemini AI
    if not GEMINI_AVAILABLE and not dev_mode:
        return jsonify({
            "error": "Gemini verification is not available on the server. Set GEMINI_API_KEY to enable verification."
        }), 503

    verification_result = (
        verify_cleanup_with_gemini(original_image, before_image, after_image)
        if not dev_mode
        else {
            "scene_match": True,
            "waste_present_before": True,
            "cleanup_verified": True,
            "fallback": True,
        }
    )

    # If Gemini timed out/failed, attempt a conservative classical CV fallback to avoid hanging
    if (verification_result.get("fallback", False) or verification_result.get("error")) and not dev_mode:
        heuristic = _fast_cleanup_fallback(before_image, after_image)
        # Only override if heuristic approves; otherwise keep Gemini result to provide error context
        if heuristic.get("scene_match") and heuristic.get("waste_present_before") and heuristic.get("cleanup_verified"):
            verification_result = heuristic

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
            # Determine if clan-approved participation exists for this bounty for the user's clan
            u_clan_id = None
            try:
                u_clan_row = conn.execute('SELECT clan_id FROM clan_members WHERE user_id = (SELECT id FROM users WHERE username = ?)', (username,)).fetchone()
                u_clan_id = int(u_clan_row[0]) if u_clan_row else None
            except Exception:
                u_clan_id = None

            # Update bounty status and persist image URLs
            conn.execute(
                'UPDATE waste_bounty SET status = "CLOSED", claimed_by_user_id = ?, claimed_at = CURRENT_TIMESTAMP, completed_at = CURRENT_TIMESTAMP, before_image_url = ?, after_image_url = ? WHERE id = ?',
                (user_id, f"/uploads/{before_filename}", f"/uploads/{after_filename}", bounty_id),
            )

            points_awarded_to_requester = 0
            # If there is an approved clan claim for the user's clan, distribute clan reward equally
            clan_awarded = False
            if u_clan_id is not None:
                approved = conn.execute(
                    'SELECT 1 FROM clan_bounty_claims WHERE bounty_id = ? AND clan_id = ? AND status = "approved" LIMIT 1',
                    (bounty_id, u_clan_id)
                ).fetchone()
                if approved is not None:
                    clan_awarded = True
                    # Fetch all clan members
                    members = conn.execute(
                        'SELECT u.id FROM clan_members cm JOIN users u ON u.id = cm.user_id WHERE cm.clan_id = ?',
                        (u_clan_id,)
                    ).fetchall()
                    member_ids = [int(r[0]) for r in members] if members else []
                    if member_ids:
                        base = CLAN_BOUNTY_REWARD // len(member_ids)
                        remainder = CLAN_BOUNTY_REWARD - (base * len(member_ids))
                        # Leader should receive remainder first if exists
                        leader_row = conn.execute('SELECT leader_user_id FROM clans WHERE id = ?', (u_clan_id,)).fetchone()
                        leader_id = int(leader_row[0]) if leader_row else None
                        # Build distribution map
                        distribution: Dict[int, int] = {mid: base for mid in member_ids}
                        if remainder > 0:
                            # Try to allocate to leader
                            if leader_id in distribution:
                                distribution[leader_id] += remainder
                            else:
                                # Allocate remainder to the first N members deterministically
                                for i in range(remainder):
                                    distribution[member_ids[i % len(member_ids)]] += 1
                        # Apply updates and transactions
                        for mid, inc in distribution.items():
                            conn.execute('UPDATE users SET total_points = total_points + ? WHERE id = ?', (inc, mid))
                            conn.execute('INSERT INTO transactions (user_id, points_change, reason) VALUES (?, ?, ?)', (mid, inc, f'Clan Bounty Cleanup Completed - Bounty #{bounty_id}'))
                        # Set requester share for response
                        if user_id in distribution:
                            points_awarded_to_requester = distribution[user_id]
                    else:
                        # No members? Fallback award to requester only
                        conn.execute('UPDATE users SET total_points = total_points + ? WHERE id = ?', (CLAN_BOUNTY_REWARD, user_id))
                        conn.execute('INSERT INTO transactions (user_id, points_change, reason) VALUES (?, ?, ?)', (user_id, CLAN_BOUNTY_REWARD, f'Clan Bounty Cleanup Completed - Bounty #{bounty_id}'))
                        points_awarded_to_requester = CLAN_BOUNTY_REWARD

            if not clan_awarded:
                # Individual reward
                conn.execute('UPDATE users SET total_points = total_points + ? WHERE id = ?', (INDIVIDUAL_BOUNTY_REWARD, user_id))
                conn.execute('INSERT INTO transactions (user_id, points_change, reason) VALUES (?, ?, ?)', (user_id, INDIVIDUAL_BOUNTY_REWARD, f'Bounty Cleanup Completed - Bounty #{bounty_id}'))
                points_awarded_to_requester = INDIVIDUAL_BOUNTY_REWARD

            # Read back updated total for requester
            total_row = conn.execute('SELECT total_points FROM users WHERE id = ?', (user_id,)).fetchone()
            new_total = int(total_row[0]) if total_row else (current_points + points_awarded_to_requester)

            # Also record a conservative carbon event for the cleanup (treat as 1 plastic item saved)
            try:
                factors = _load_emission_factors()
                amount = round(float(factors.get('plastic', 0.3)) * 1, 3)
                if amount > 0:
                    conn.execute('INSERT INTO carbon_events (user_id, category, amount_kg) VALUES (?, ?, ?)', (user_id, 'plastic', amount))
            except Exception:
                pass
            conn.commit()

        return jsonify({
            "message": "Cleanup verified successfully! Points awarded.",
            "points_awarded": points_awarded_to_requester,
            "total_points": new_total,
            "verification_result": verification_result,
            "dev_mode": dev_mode,
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
            "verification_result": verification_result,
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

		# Points awarding logic (image): 10–40 per image based on hazard/recyclability
		awarded_points = 0
		message = ''
		if hazardous_items:
			awarded_points = DETECT_IMAGE_MAX_POINTS  # 40
			message = 'Hazardous waste detected. Maximum image points awarded.'
		elif recyclable_items:
			awarded_points = max(DETECT_IMAGE_MIN_POINTS, min(DETECT_IMAGE_MAX_POINTS, 30))
			message = 'Recyclable waste detected. Elevated image points awarded.'
		elif all_detected_items:
			awarded_points = DETECT_IMAGE_MIN_POINTS
			message = 'General waste detected. Minimum image points awarded.'
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
			# Record carbon footprint estimate based on Gemini-detected items (per item factors)
			try:
				factors = _load_emission_factors()
				counts: Dict[str, int] = defaultdict(int)
				for item in gemini_result.get('items', []):
					text = ' '.join([
						str(item.get('material_type', '')),
						str(item.get('name', '')),
						str(item.get('description', '')),
					]).strip()
					cat = _infer_carbon_category_from_text(text) or ''
					if cat in ('plastic','paper','metal'):
						counts[cat] += 1
				# Insert aggregated events per category
				for cat, cnt in counts.items():
					per_item = float(factors.get(cat, 0.0))
					amount = round(per_item * max(0, int(cnt)), 3)
					if amount > 0:
						conn.execute('INSERT INTO carbon_events (user_id, category, amount_kg) VALUES (?, ?, ?)', (user_id, cat, amount))
			except Exception as _:
				# Do not block on carbon logging
				pass
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
					# Record carbon estimate for one disposed item when disposal is verified
					try:
						if disposal_verified:
							factors = _load_emission_factors()
							infer_text = f"{waste_type} {reasoning}"
							cat = _infer_carbon_category_from_text(infer_text)
							if cat in ('plastic','paper','metal'):
								per_item = float(factors.get(cat, 0.0))
								amount = round(per_item * 1, 3)
								if amount > 0:
									conn.execute('INSERT INTO carbon_events (user_id, category, amount_kg) VALUES (?, ?, ?)', (user_id, cat, amount))
					except Exception:
						pass
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
				"gemini_available": GEMINI_AVAILABLE
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
			"gemini_available": GEMINI_AVAILABLE,
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
				"gemini_available": GEMINI_AVAILABLE
			}), 500

		# Calculate potential points for video
		potential_points = 0
		if video_analysis.get("disposal_verified", False):
			potential_points = POINTS_PER_DETECTION

		response = {
			"video_analysis": video_analysis,
			"potential_points": potential_points,
			"gemini_available": GEMINI_AVAILABLE,
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


@app.route('/api/streak', methods=['GET'])
def get_streak() -> Tuple[Any, int]:
    username = parse_username_from_auth()
    if not username:
        return jsonify({"error": "unauthorized"}), 401
    with get_db_connection() as conn:
        u = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
        if u is None:
            return jsonify({"error": "user not found"}), 404
        uid = int(u[0])
        row = conn.execute('SELECT current_streak, best_streak, last_active_date FROM streaks WHERE user_id = ?', (uid,)).fetchone()
        if row is None:
            return jsonify({"current_streak": 0, "best_streak": 0, "last_active_date": None, "days": []}), 200
        # Build last 7 days calendar
        today = datetime.utcnow().date()
        days = []
        for i in range(7):
            d = today - timedelta(days=6 - i)
            active = (str(row[2]) == d.isoformat()) if row[2] else False
            days.append({"date": d.isoformat(), "active": active})
        return jsonify({
            "current_streak": int(row[0] or 0),
            "best_streak": int(row[1] or 0),
            "last_active_date": row[2],
            "days": days
        }), 200

@app.route('/api/stats/carbon', methods=['GET'])
def carbon_stats():
    username = parse_username_from_auth()
    if not username:
        return jsonify({"error": "missing auth token"}), 401
    # Load emission factors from JSON file if available; else defaults
    factors_path = os.path.join(os.path.dirname(__file__), 'emission_factors.json')
    default_factors = {"plastic": 0.3, "paper": 0.1, "metal": 0.7}
    try:
        with open(factors_path, 'r', encoding='utf-8') as fh:
            factors = json.load(fh)
            if not isinstance(factors, dict):
                factors = default_factors
    except Exception:
        factors = default_factors

    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)
    with get_db_connection() as conn:
        u = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
        if not u:
            return jsonify({"error": "user not found"}), 404
        uid = int(u[0])
        rows = conn.execute('SELECT category, amount_kg FROM carbon_events WHERE user_id = ? AND created_at >= ?', (uid, week_ago.strftime('%Y-%m-%d %H:%M:%S'))).fetchall()
        total = 0.0
        by_cat: Dict[str, float] = defaultdict(float)
        for r in rows:
            cat = str(r[0]).lower()
            amt = float(r[1])
            total += amt
            by_cat[cat] += amt
        # Normalize output to known categories
        result_sources = {
            'plastic': round(by_cat.get('plastic', 0.0), 3),
            'paper': round(by_cat.get('paper', 0.0), 3),
            'metal': round(by_cat.get('metal', 0.0), 3),
        }
        return jsonify({
            'week_total_kg': round(total, 3),
            'sources': result_sources,
            'factors': factors,
            'planet_health': min(100, int(total * 5))
        }), 200


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
        clans = []
        for r in rows:
            leader_username = conn.execute('SELECT username FROM users WHERE id = ?', (r["leader_user_id"],)).fetchone()
            clans.append({
                "id": r["id"],
                "name": r["name"],
                "city": r["city"],
                "state": r["state"],
                "country": r["country"],
                "leader_user_id": r["leader_user_id"],
                "leader_username": leader_username[0] if leader_username else None,
                "created_at": r["created_at"],
            })
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
    # Accept either a 4-digit code or a direct clan_id, or post a join request
    clan_id_req = data.get('clan_id')
    with get_db_connection() as conn:
        u = _get_user(conn, username)
        if u is None:
            return jsonify({"error": "user not found"}), 404
        already = conn.execute('SELECT 1 FROM clan_members WHERE user_id = ?', (u["id"],)).fetchone()
        if already:
            return jsonify({"error": "already in a clan"}), 400
        clan = None
        if clan_id_req:
            try:
                clan = conn.execute('SELECT * FROM clans WHERE id = ?', (int(clan_id_req),)).fetchone()
            except Exception:
                return jsonify({"error": "invalid clan_id"}), 400
        elif code and code.isdigit() and len(code) == 4:
            clan = conn.execute('SELECT * FROM clans WHERE join_code = ?', (code,)).fetchone()
        else:
            return jsonify({"error": "provide code or clan_id"}), 400
        if (clan["city"] or '').strip().lower() != (u["city"] or '').strip().lower():
            return jsonify({"error": "can only join clan in your city"}), 400
        # Create join request and notify leader
        leader_row = conn.execute('SELECT username FROM users WHERE id = ?', (clan["leader_user_id"],)).fetchone()
        conn.execute('INSERT OR IGNORE INTO clan_join_requests (clan_id, applicant_user_id, status) VALUES (?, ?, "pending")', (clan["id"], u["id"]))
        conn.commit()
        try:
            if leader_row and leader_row[0]:
                notify_user(leader_row[0], {
                    "id": None,
                    "type": "CLAN_JOIN_REQUEST",
                    "title": "New clan join request",
                    "message": f"@{username} requested to join your clan {clan['name']}",
                    "city": clan["city"],
                    "payload": {"clan_id": clan["id"], "applicant": username},
                    "created_at": time.strftime('%Y-%m-%d %H:%M:%S')
                })
        except Exception:
            pass
        return jsonify({"status": "requested", "clan_id": clan["id"]}), 200


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


@app.route('/api/clan_join_requests', methods=['GET'])
def list_clan_join_requests():
    """List pending join requests for the clan led by the current user."""
    username = parse_username_from_auth()
    if not username:
        return jsonify({"error": "unauthorized"}), 401
    with get_db_connection() as conn:
        leader = _get_user(conn, username)
        if leader is None:
            return jsonify({"error": "user not found"}), 404
        clan_row = conn.execute('SELECT id FROM clans WHERE leader_user_id = ?', (leader["id"],)).fetchone()
        if clan_row is None:
            return jsonify({"requests": []}), 200
        clan_id = clan_row["id"]
        rows = conn.execute(
            'SELECT r.id, u.username as applicant_username, r.created_at '\
            'FROM clan_join_requests r JOIN users u ON u.id = r.applicant_user_id '\
            'WHERE r.clan_id = ? AND r.status = "pending" ORDER BY r.created_at ASC',
            (clan_id,)
        ).fetchall()
        requests = [
            {"id": r["id"], "applicant_username": r["applicant_username"], "created_at": r["created_at"]}
            for r in rows
        ]
        return jsonify({"requests": requests}), 200


@app.route('/api/clan_join_requests/decision', methods=['POST'])
def decide_clan_join_request():
    """Leader approves or rejects a join request."""
    username = parse_username_from_auth()
    if not username:
        return jsonify({"error": "unauthorized"}), 401
    data: Dict[str, Any] = request.get_json(silent=True) or {}
    try:
        request_id = int(data.get('request_id'))
    except Exception:
        return jsonify({"error": "invalid request_id"}), 400
    decision = (data.get('decision') or '').strip().lower()
    if decision not in ('approve', 'reject'):
        return jsonify({"error": "decision must be approve or reject"}), 400
    with get_db_connection() as conn:
        leader = _get_user(conn, username)
        if leader is None:
            return jsonify({"error": "user not found"}), 404
        r = conn.execute('SELECT clan_id, applicant_user_id, status FROM clan_join_requests WHERE id = ?', (request_id,)).fetchone()
        if r is None:
            return jsonify({"error": "request not found"}), 404
        clan_id, applicant_user_id, status = r["clan_id"], r["applicant_user_id"], (r["status"] or '').lower()
        # Ensure current user is the leader of this clan
        is_leader = conn.execute('SELECT 1 FROM clans WHERE id = ? AND leader_user_id = ?', (clan_id, leader["id"])).fetchone()
        if is_leader is None:
            return jsonify({"error": "forbidden"}), 403
        if status != 'pending':
            return jsonify({"error": "request already decided"}), 400
        if decision == 'approve':
            # Add as member if not already in any clan
            exists = conn.execute('SELECT 1 FROM clan_members WHERE user_id = ?', (applicant_user_id,)).fetchone()
            if exists is None:
                conn.execute('INSERT INTO clan_members (clan_id, user_id, role) VALUES (?, ?, ?)', (clan_id, applicant_user_id, 'member'))
            conn.execute('UPDATE clan_join_requests SET status = "approved", resolved_at = CURRENT_TIMESTAMP WHERE id = ?', (request_id,))
        else:
            conn.execute('UPDATE clan_join_requests SET status = "rejected", resolved_at = CURRENT_TIMESTAMP WHERE id = ?', (request_id,))
        # Persist + notify applicant
        applicant_row = conn.execute('SELECT username FROM users WHERE id = ?', (applicant_user_id,)).fetchone()
        try:
            if applicant_row and applicant_row[0]:
                app_user = applicant_row[0]
                app_id_row = conn.execute('SELECT id FROM users WHERE username = ?', (app_user,)).fetchone()
                if app_id_row:
                    conn.execute(
                        'INSERT INTO notifications (user_id, type, title, message, payload) VALUES (?, ?, ?, ?, ?)',
                        (int(app_id_row[0]), 'CLAN_JOIN_DECISION', 'Clan join request updated', f'Your request was {decision} for clan #{clan_id}', json.dumps({"clan_id": clan_id, "decision": decision}))
                    )
                conn.commit()
                notify_user(app_user, {
                    "id": None,
                    "type": "CLAN_JOIN_DECISION",
                    "title": "Clan join request updated",
                    "message": f"Your request was {decision} for clan #{clan_id}",
                    "payload": {"clan_id": clan_id, "decision": decision},
                    "created_at": time.strftime('%Y-%m-%d %H:%M:%S')
                })
        except Exception:
            pass
        return jsonify({"status": decision}), 200


@app.route('/api/bounty_clan_claims', methods=['POST'])
def create_bounty_clan_claim() -> Tuple[Any, int]:
    """Create a clan participation claim for a bounty. Members require leader approval."""
    username = parse_username_from_auth()
    if not username:
        return jsonify({"error": "unauthorized"}), 401
    data: Dict[str, Any] = request.get_json(silent=True) or {}
    try:
        bounty_id = int(data.get('bounty_id'))
    except Exception:
        return jsonify({"error": "invalid bounty_id"}), 400
    people_strength = data.get('people_strength')
    try:
        people_strength = int(people_strength)
    except Exception:
        return jsonify({"error": "people_strength must be 0-20"}), 400
    if people_strength < 0 or people_strength > 20:
        return jsonify({"error": "people_strength must be 0-20"}), 400
    scheduled_at_raw = (data.get('scheduled_at') or '').strip() or None
    # Normalize scheduled_at to 'YYYY-MM-DD HH:MM:SS' if provided
    def _normalize_dt(s: Optional[str]) -> Optional[str]:
        if not s:
            return None
        try:
            # Accept 'YYYY-MM-DD HH:MM[:SS]' or ISO 'YYYY-MM-DDTHH:MM[:SS]'
            s2 = s.replace('T', ' ')
            for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M'):
                try:
                    dt = datetime.strptime(s2, fmt)
                    return dt.strftime('%Y-%m-%d %H:%M:%S')
                except Exception:
                    continue
        except Exception:
            return None
        return None
    scheduled_at = _normalize_dt(scheduled_at_raw)

    with get_db_connection() as conn:
        # Validate user and clan
        u = _get_user(conn, username)
        if u is None:
            return jsonify({"error": "user not found"}), 404
        user_id = int(u["id"]) if isinstance(u, dict) else int(u[0])
        clan_row = conn.execute(
            'SELECT c.id as clan_id, c.leader_user_id, cu.username as leader_username '\
            'FROM clans c JOIN users cu ON cu.id = c.leader_user_id '\
            'JOIN clan_members cm ON cm.clan_id = c.id '\
            'WHERE cm.user_id = ?',
            (user_id,)
        ).fetchone()
        if clan_row is None:
            return jsonify({"error": "not in a clan"}), 400
        clan_id = int(clan_row["clan_id"]) if isinstance(clan_row, dict) else int(clan_row[0])
        leader_user_id = int(clan_row["leader_user_id"]) if isinstance(clan_row, dict) else int(clan_row[1])
        leader_username = str(clan_row["leader_username"]) if isinstance(clan_row, dict) else str(clan_row[2])

        # Validate bounty exists
        b = conn.execute('SELECT id, city FROM waste_bounty WHERE id = ?', (bounty_id,)).fetchone()
        if b is None:
            return jsonify({"error": "bounty not found"}), 404

        # Prevent duplicate outstanding claim for same clan+bounty
        existing = conn.execute(
            'SELECT id, status FROM clan_bounty_claims WHERE bounty_id = ? AND clan_id = ? ORDER BY id DESC LIMIT 1',
            (bounty_id, clan_id)
        ).fetchone()
        if existing is not None:
            status = (existing[1] or '').lower()
            if status in ('pending', 'approved'):
                return jsonify({"error": f"clan already has a {status} claim for this bounty"}), 400

        # Insert claim
        is_leader = (user_id == leader_user_id)
        if is_leader:
            conn.execute(
                'INSERT INTO clan_bounty_claims (bounty_id, clan_id, requested_by_user_id, people_strength, scheduled_at, status, decided_by_user_id, decided_at) '
                'VALUES (?, ?, ?, ?, ?, "approved", ?, CURRENT_TIMESTAMP)',
                (bounty_id, clan_id, user_id, people_strength, scheduled_at, user_id)
            )
            claim_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
            conn.commit()
            return jsonify({"status": "approved", "claim_id": int(claim_id)}), 201
        else:
            conn.execute(
                'INSERT INTO clan_bounty_claims (bounty_id, clan_id, requested_by_user_id, people_strength, scheduled_at, status) '
                'VALUES (?, ?, ?, ?, ?, "pending")',
                (bounty_id, clan_id, user_id, people_strength, scheduled_at)
            )
            claim_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
            # Notify clan leader
            try:
                # Persist leader notification with context_bounty_id
                leader_id_row = conn.execute('SELECT id FROM users WHERE username = ?', (leader_username,)).fetchone()
                if leader_id_row:
                    conn.execute(
                        'INSERT INTO notifications (user_id, type, title, message, payload, context_bounty_id) VALUES (?, ?, ?, ?, ?, ?)',
                        (
                            int(leader_id_row[0]),
                            'CLAN_BOUNTY_REQUEST',
                            'Bounty participation request',
                            f'@{username} requested to participate in bounty #{bounty_id}',
                            json.dumps({"clan_id": clan_id, "bounty_id": bounty_id, "people_strength": people_strength, "scheduled_at": scheduled_at}),
                            bounty_id
                        )
                    )
                conn.commit()
                notify_user(leader_username, {
                    "id": None,
                    "type": "CLAN_BOUNTY_REQUEST",
                    "title": "Bounty participation request",
                    "message": f"@{username} requested to participate in bounty #{bounty_id}",
                    "payload": {"clan_id": clan_id, "bounty_id": bounty_id, "people_strength": people_strength, "scheduled_at": scheduled_at},
                    "context_bounty_id": bounty_id,
                    "created_at": time.strftime('%Y-%m-%d %H:%M:%S')
                })
            except Exception:
                pass
            conn.commit()
            return jsonify({"status": "pending", "claim_id": int(claim_id)}), 201


@app.route('/api/clan_bounty_claims', methods=['GET'])
def list_clan_bounty_claims() -> Tuple[Any, int]:
    """Leader: list pending clan bounty claims for my clan."""
    username = parse_username_from_auth()
    if not username:
        return jsonify({"error": "unauthorized"}), 401
    with get_db_connection() as conn:
        leader = _get_user(conn, username)
        if leader is None:
            return jsonify({"error": "user not found"}), 404
        # Identify clan led by user
        row = conn.execute('SELECT id FROM clans WHERE leader_user_id = ?', (leader["id"] if isinstance(leader, dict) else leader[0],)).fetchone()
        if row is None:
            return jsonify({"claims": []}), 200
        clan_id = int(row[0])
        rows = conn.execute(
            'SELECT cbc.id, cbc.bounty_id, u.username as requester, cbc.people_strength, cbc.scheduled_at, cbc.created_at, '
            '       wb.city, wb.state, wb.country, wb.waste_image_url '
            'FROM clan_bounty_claims cbc '
            'JOIN users u ON u.id = cbc.requested_by_user_id '
            'JOIN waste_bounty wb ON wb.id = cbc.bounty_id '
            'WHERE cbc.clan_id = ? AND cbc.status = "pending" '
            'ORDER BY cbc.created_at ASC',
            (clan_id,)
        ).fetchall()
        claims: List[Dict[str, Any]] = []
        for r in rows:
            claims.append({
                "id": r[0],
                "bounty_id": r[1],
                "requested_by_username": r[2],
                "people_strength": r[3],
                "scheduled_at": r[4],
                "created_at": r[5],
                "city": r[6],
                "state": r[7],
                "country": r[8],
                "waste_image_url": r[9],
            })
        return jsonify({"claims": claims}), 200


@app.route('/api/clan_bounty_claims/decision', methods=['POST'])
def decide_clan_bounty_claim() -> Tuple[Any, int]:
    """Leader approves or rejects a clan bounty participation request."""
    username = parse_username_from_auth()
    if not username:
        return jsonify({"error": "unauthorized"}), 401
    data: Dict[str, Any] = request.get_json(silent=True) or {}
    try:
        claim_id = int(data.get('claim_id'))
    except Exception:
        return jsonify({"error": "invalid claim_id"}), 400
    decision = (data.get('decision') or '').strip().lower()
    if decision not in ('approve', 'reject'):
        return jsonify({"error": "decision must be approve or reject"}), 400
    with get_db_connection() as conn:
        leader = _get_user(conn, username)
        if leader is None:
            return jsonify({"error": "user not found"}), 404
        # Load claim and clan
        r = conn.execute('SELECT bounty_id, clan_id, requested_by_user_id, status FROM clan_bounty_claims WHERE id = ?', (claim_id,)).fetchone()
        if r is None:
            return jsonify({"error": "claim not found"}), 404
        bounty_id, clan_id, requested_by_user_id, status = int(r[0]), int(r[1]), int(r[2]), (r[3] or '').lower()
        if status != 'pending':
            return jsonify({"error": "claim already decided"}), 400
        # Verify current user is the leader of this clan
        is_leader = conn.execute('SELECT 1 FROM clans WHERE id = ? AND leader_user_id = ?', (clan_id, leader["id"] if isinstance(leader, dict) else leader[0])).fetchone()
        if is_leader is None:
            return jsonify({"error": "forbidden"}), 403
        new_status = 'approved' if decision == 'approve' else 'rejected'
        conn.execute(
            'UPDATE clan_bounty_claims SET status = ?, decided_by_user_id = ?, decided_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
            (new_status, leader["id"] if isinstance(leader, dict) else leader[0], claim_id)
        )
        # Notify requester
        req_user_row = conn.execute('SELECT username FROM users WHERE id = ?', (requested_by_user_id,)).fetchone()
        if req_user_row:
            req_username = req_user_row[0]
            # Persist notification with context_bounty_id
            conn.execute(
                'INSERT INTO notifications (user_id, type, title, message, payload, context_bounty_id) VALUES (?, ?, ?, ?, ?, ?)',
                (
                    requested_by_user_id,
                    'CLAN_BOUNTY_DECISION',
                    'Clan bounty request updated',
                    f'Your clan bounty request was {new_status} for bounty #{bounty_id}',
                    json.dumps({"decision": new_status, "bounty_id": bounty_id, "claim_id": claim_id}),
                    bounty_id
                )
            )
            conn.commit()
            try:
                notify_user(req_username, {
                    "id": None,
                    "type": "CLAN_BOUNTY_DECISION",
                    "title": "Clan bounty request updated",
                    "message": f"Your clan bounty request was {new_status} for bounty #{bounty_id}",
                    "payload": {"decision": new_status, "bounty_id": bounty_id, "claim_id": claim_id},
                    "context_bounty_id": bounty_id,
                    "created_at": time.strftime('%Y-%m-%d %H:%M:%S')
                })
            except Exception:
                pass
        conn.commit()
        return jsonify({"status": new_status}), 200

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


@app.route('/api/leaderboard/city_co2', methods=['GET'])
def leaderboard_city_co2():
    """
    Top CO₂ savers in the authenticated user's city over the last 7 days,
    ranked by total carbon_events.amount_kg.
    Query params: limit (default 10)
    """
    limit = int(request.args.get('limit', '10'))
    limit = max(1, min(limit, 50))
    username = parse_username_from_auth()
    if not username:
        return jsonify({"error": "unauthorized"}), 401
    week_ago = (datetime.utcnow() - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
    with get_db_connection() as conn:
        u = conn.execute('SELECT id, city FROM users WHERE username = ?', (username,)).fetchone()
        if not u:
            return jsonify({"error": "user not found"}), 404
        city = u[1]
        if not city:
            return jsonify({"users": []}), 200
        rows = conn.execute(
            'SELECT users.username AS username, users.city AS city, '
            'COALESCE(SUM(carbon_events.amount_kg), 0) AS saved_kg '
            'FROM users '
            'LEFT JOIN carbon_events ON carbon_events.user_id = users.id '
            '  AND carbon_events.created_at >= ? '
            'WHERE users.city = ? '
            'GROUP BY users.id '
            'ORDER BY saved_kg DESC '
            'LIMIT ?',
            (week_ago, city, limit)
        ).fetchall()
        users = [
            {"username": r[0], "city": r[1], "saved_kg": round(float(r[2] or 0.0), 3)}
            for r in rows
        ]
        return jsonify({"users": users, "city": city}), 200


# ======== Friends & Direct Messages ========
def _get_user_id(conn: Connection, username: str) -> Optional[int]:
    row = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
    return int(row[0]) if row else None


def _normalize_pair(a_id: int, b_id: int) -> Tuple[int, int]:
    return (a_id, b_id) if a_id < b_id else (b_id, a_id)


# ======== Public User Profile ========
@app.route('/api/user_profile', methods=['GET'])
def get_user_profile() -> Tuple[Any, int]:
    """
    Public profile for a given username.
    Returns basic location, clan, lifetime stats.
    """
    target_username = (request.args.get('username') or '').strip()
    if not target_username:
        return jsonify({"error": "username required"}), 400
    # Require auth but allow viewing others
    viewer = parse_username_from_auth()
    if not viewer:
        return jsonify({"error": "unauthorized"}), 401
    with get_db_connection() as conn:
        u = conn.execute(
            'SELECT id, username, total_points, country, state, city FROM users WHERE username = ?',
            (target_username,)
        ).fetchone()
        if u is None:
            return jsonify({"error": "user not found"}), 404
        uid = int(u[0])
        total_now = int(u[2])
        # Lifetime points = current + total spent
        spent_row = conn.execute(
            'SELECT COALESCE(SUM(CASE WHEN points_change < 0 THEN -points_change ELSE 0 END),0) FROM transactions WHERE user_id = ?',
            (uid,)
        ).fetchone()
        spent_points = int(spent_row[0]) if spent_row else 0
        lifetime_points = total_now + spent_points
        # Lifetime detections from reasons that represent detections
        det_row = conn.execute(
            'SELECT COUNT(*) FROM transactions WHERE user_id = ? AND points_change > 0 AND reason IN ("Waste Detected", "Video Disposal Verified")',
            (uid,)
        ).fetchone()
        lifetime_detections = int(det_row[0]) if det_row else 0
        # Lifetime claimed bounties
        cb_row = conn.execute(
            'SELECT COUNT(*) FROM waste_bounty WHERE claimed_by_user_id = ?',
            (uid,)
        ).fetchone()
        lifetime_claimed_bounties = int(cb_row[0]) if cb_row else 0
        # Clan info
        clan_row = conn.execute(
            'SELECT c.id, c.name, cm.role FROM clan_members cm JOIN clans c ON c.id = cm.clan_id WHERE cm.user_id = ?',
            (uid,)
        ).fetchone()
        clan = None
        if clan_row:
            clan = {
                "id": clan_row[0],
                "name": clan_row[1],
                "role": clan_row[2],
            }
        return jsonify({
            "username": u[1],
            "location": {"city": u[5], "state": u[4], "country": u[3]},
            "total_points": total_now,
            "lifetime_points": lifetime_points,
            "lifetime_detections": lifetime_detections,
            "lifetime_claimed_bounties": lifetime_claimed_bounties,
            "clan": clan,
        }), 200


@app.route('/api/friends', methods=['GET'])
def list_friends():
    username = parse_username_from_auth()
    if not username:
        return jsonify({"error": "unauthorized"}), 401
    with get_db_connection() as conn:
        me = _get_user(conn, username)
        if me is None:
            return jsonify({"error": "user not found"}), 404
        uid = me["id"]
        # Accepted friends
        rows = conn.execute(
            'SELECT f.user_a_id, f.user_b_id, u.username AS other_username '\
            'FROM friends f JOIN users u ON (u.id = CASE WHEN f.user_a_id = ? THEN f.user_b_id ELSE f.user_a_id END) '\
            'WHERE (f.user_a_id = ? OR f.user_b_id = ?) AND f.status = "accepted"',
            (uid, uid, uid)
        ).fetchall()
        friends = [{"username": r["other_username"]} for r in rows]
        # Incoming pending
        rows_in = conn.execute(
            'SELECT u.username FROM friends f JOIN users u ON u.id = CASE WHEN f.user_a_id = ? THEN f.user_b_id ELSE f.user_a_id END '
            'WHERE (f.user_a_id = ? OR f.user_b_id = ?) AND f.status = "pending" AND f.requested_by_user_id <> ?',
            (uid, uid, uid, uid)
        ).fetchall()
        pending_incoming = [r[0] for r in rows_in]
        # Outgoing pending
        rows_out = conn.execute(
            'SELECT u.username FROM friends f JOIN users u ON u.id = CASE WHEN f.user_a_id = ? THEN f.user_b_id ELSE f.user_a_id END '
            'WHERE (f.user_a_id = ? OR f.user_b_id = ?) AND f.status = "pending" AND f.requested_by_user_id = ?',
            (uid, uid, uid, uid)
        ).fetchall()
        pending_outgoing = [r[0] for r in rows_out]
        return jsonify({"friends": friends, "pending_incoming": pending_incoming, "pending_outgoing": pending_outgoing}), 200


@app.route('/api/friends/add', methods=['POST'])
def add_friend():
    username = parse_username_from_auth()
    if not username:
        return jsonify({"error": "unauthorized"}), 401
    data: Dict[str, Any] = request.get_json(silent=True) or {}
    target = (data.get('username') or '').strip()
    if not target:
        return jsonify({"error": "username required"}), 400
    if target == username:
        return jsonify({"error": "cannot add yourself"}), 400
    with get_db_connection() as conn:
        me_id = _get_user_id(conn, username)
        you_id = _get_user_id(conn, target)
        if me_id is None or you_id is None:
            return jsonify({"error": "user not found"}), 404
        a_id, b_id = _normalize_pair(me_id, you_id)
        pair = conn.execute('SELECT id, status, requested_by_user_id FROM friends WHERE user_a_id = ? AND user_b_id = ?', (a_id, b_id)).fetchone()
        if pair is None:
            conn.execute('INSERT INTO friends (user_a_id, user_b_id, status, requested_by_user_id, updated_at) VALUES (?, ?, "pending", ?, CURRENT_TIMESTAMP)', (a_id, b_id, me_id))
            # persist + notify recipient
            try:
                you_row = conn.execute('SELECT id FROM users WHERE username = ?', (target,)).fetchone()
                if you_row:
                    conn.execute(
                        'INSERT INTO notifications (user_id, type, title, message, payload) VALUES (?, ?, ?, ?, ?)',
                        (int(you_row[0]), 'FRIEND_REQUEST', 'New friend request', f'@{username} sent you a friend request', json.dumps({"from": username}))
                    )
                conn.commit()
                notify_user(target, {
                    "id": None,
                    "type": "FRIEND_REQUEST",
                    "title": "New friend request",
                    "message": f"@{username} sent you a friend request",
                    "payload": {"from": username},
                    "created_at": time.strftime('%Y-%m-%d %H:%M:%S')
                })
            except Exception:
                pass
            return jsonify({"status": "pending"}), 200
        status = (pair["status"] or '').lower()
        requested_by = int(pair["requested_by_user_id"])
        if status == 'accepted':
            return jsonify({"status": "accepted"}), 200
        if status == 'pending' and requested_by != me_id:
            # Auto-accept if they already requested you
            conn.execute('UPDATE friends SET status = "accepted", updated_at = CURRENT_TIMESTAMP WHERE id = ?', (pair["id"],))
            try:
                tgt_row = conn.execute('SELECT id FROM users WHERE username = ?', (target,)).fetchone()
                if tgt_row:
                    conn.execute(
                        'INSERT INTO notifications (user_id, type, title, message, payload) VALUES (?, ?, ?, ?, ?)',
                        (int(tgt_row[0]), 'FRIEND_ACCEPTED', 'Friend request accepted', f'@{username} accepted your friend request', json.dumps({"user": username}))
                    )
                conn.commit()
                notify_user(target, {
                    "id": None,
                    "type": "FRIEND_ACCEPTED",
                    "title": "Friend request accepted",
                    "message": f"@{username} accepted your friend request",
                    "payload": {"user": username},
                    "created_at": time.strftime('%Y-%m-%d %H:%M:%S')
                })
            except Exception:
                pass
            return jsonify({"status": "accepted"}), 200
        return jsonify({"status": status}), 200


@app.route('/api/friends/decision', methods=['POST'])
def decide_friend():
    username = parse_username_from_auth()
    if not username:
        return jsonify({"error": "unauthorized"}), 401
    data: Dict[str, Any] = request.get_json(silent=True) or {}
    target = (data.get('username') or '').strip()
    decision = (data.get('decision') or '').strip().lower()
    if decision not in ('accept', 'reject'):
        return jsonify({"error": "decision must be accept or reject"}), 400
    with get_db_connection() as conn:
        me_id = _get_user_id(conn, username)
        you_id = _get_user_id(conn, target)
        if me_id is None or you_id is None:
            return jsonify({"error": "user not found"}), 404
        a_id, b_id = _normalize_pair(me_id, you_id)
        pair = conn.execute('SELECT id, status FROM friends WHERE user_a_id = ? AND user_b_id = ?', (a_id, b_id)).fetchone()
        if pair is None:
            return jsonify({"error": "no request found"}), 404
        status = (pair["status"] or '').lower()
        if status == 'accepted':
            return jsonify({"status": "accepted"}), 200
        if decision == 'accept':
            conn.execute('UPDATE friends SET status = "accepted", updated_at = CURRENT_TIMESTAMP WHERE id = ?', (pair["id"],))
            try:
                tgt_row = conn.execute('SELECT id FROM users WHERE username = ?', (target,)).fetchone()
                if tgt_row:
                    conn.execute(
                        'INSERT INTO notifications (user_id, type, title, message, payload) VALUES (?, ?, ?, ?, ?)',
                        (int(tgt_row[0]), 'FRIEND_ACCEPTED', 'Friend request accepted', f'@{username} accepted your friend request', json.dumps({"user": username}))
                    )
                conn.commit()
                notify_user(target, {
                    "id": None,
                    "type": "FRIEND_ACCEPTED",
                    "title": "Friend request accepted",
                    "message": f"@{username} accepted your friend request",
                    "payload": {"user": username},
                    "created_at": time.strftime('%Y-%m-%d %H:%M:%S')
                })
            except Exception:
                pass
            return jsonify({"status": "accepted"}), 200
        else:
            conn.execute('UPDATE friends SET status = "rejected", updated_at = CURRENT_TIMESTAMP WHERE id = ?', (pair["id"],))
            conn.commit()
            return jsonify({"status": "rejected"}), 200


@app.route('/api/dm', methods=['GET'])
def get_direct_messages():
    username = parse_username_from_auth()
    if not username:
        return jsonify({"error": "unauthorized"}), 401
    with_user = (request.args.get('with') or '').strip()
    limit = int(request.args.get('limit', '100'))
    limit = max(1, min(limit, 500))
    if not with_user:
        return jsonify({"error": "with is required"}), 400
    with get_db_connection() as conn:
        me_id = _get_user_id(conn, username)
        you_id = _get_user_id(conn, with_user)
        if me_id is None or you_id is None:
            return jsonify({"error": "user not found"}), 404
        # Require accepted friendship
        a_id, b_id = _normalize_pair(me_id, you_id)
        pair = conn.execute('SELECT status FROM friends WHERE user_a_id = ? AND user_b_id = ?', (a_id, b_id)).fetchone()
        if pair is None or (pair["status"] or '').lower() != 'accepted':
            return jsonify({"error": "not friends"}), 403
        rows = conn.execute(
            'SELECT m.id, s.username as sender_username, r.username as recipient_username, m.message, m.created_at '
            'FROM direct_messages m '
            'JOIN users s ON s.id = m.sender_user_id '
            'JOIN users r ON r.id = m.recipient_user_id '
            'WHERE ((m.sender_user_id = ? AND m.recipient_user_id = ?) OR (m.sender_user_id = ? AND m.recipient_user_id = ?)) '
            '  AND m.deleted_at IS NULL '
            'ORDER BY m.id ASC LIMIT ?',
            (me_id, you_id, you_id, me_id, limit)
        ).fetchall()
        messages = [
            {
                "id": r["id"],
                "sender_username": r["sender_username"],
                "recipient_username": r["recipient_username"],
                "message": r["message"],
                "created_at": r["created_at"],
            } for r in rows
        ]
        return jsonify({"messages": messages}), 200


@app.route('/api/dm', methods=['POST'])
def send_direct_message():
    username = parse_username_from_auth()
    if not username:
        return jsonify({"error": "unauthorized"}), 401
    data: Dict[str, Any] = request.get_json(silent=True) or {}
    to_user = (data.get('to') or '').strip()
    text = (data.get('message') or '').strip()
    if not to_user or not text:
        return jsonify({"error": "to and message required"}), 400
    if len(text) > 2000:
        return jsonify({"error": "message too long"}), 400
    with get_db_connection() as conn:
        me_id = _get_user_id(conn, username)
        you_id = _get_user_id(conn, to_user)
        if me_id is None or you_id is None:
            return jsonify({"error": "user not found"}), 404
        a_id, b_id = _normalize_pair(me_id, you_id)
        pair = conn.execute('SELECT status FROM friends WHERE user_a_id = ? AND user_b_id = ?', (a_id, b_id)).fetchone()
        if pair is None or (pair["status"] or '').lower() != 'accepted':
            return jsonify({"error": "not friends"}), 403
        conn.execute('INSERT INTO direct_messages (sender_user_id, recipient_user_id, message) VALUES (?, ?, ?)', (me_id, you_id, text))
        msg_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        row = conn.execute('SELECT id, created_at FROM direct_messages WHERE id = ?', (msg_id,)).fetchone()
        conn.commit()
        created = {
            "id": row["id"],
            "sender_username": username,
            "recipient_username": to_user,
            "message": text,
            "created_at": row["created_at"],
        }
        try:
            notify_user(to_user, {
                "id": None,
                "type": "DM",
                "title": f"Message from @{username}",
                "message": text[:80],
                "payload": {"from": username},
                "created_at": time.strftime('%Y-%m-%d %H:%M:%S')
            })
        except Exception:
            pass
        return jsonify({"message": created}), 201


@app.route('/api/dm/<int:message_id>', methods=['DELETE'])
def delete_direct_message(message_id: int):
    username = parse_username_from_auth()
    if not username:
        return jsonify({"error": "unauthorized"}), 401
    with get_db_connection() as conn:
        me_id = _get_user_id(conn, username)
        row = conn.execute('SELECT sender_user_id FROM direct_messages WHERE id = ? AND deleted_at IS NULL', (message_id,)).fetchone()
        if row is None:
            return jsonify({"error": "message not found"}), 404
        if int(row[0]) != me_id:
            return jsonify({"error": "forbidden"}), 403
        conn.execute('UPDATE direct_messages SET deleted_at = CURRENT_TIMESTAMP WHERE id = ?', (message_id,))
        conn.commit()
        return jsonify({"status": "deleted"}), 200

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
