"""
Travel Matcher API - Flask Backend
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import uuid
from datetime import datetime
import os
import sys

# Add the travel_matcher directory to path
from matcher import TravelMatcher

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*", "methods": ["GET", "POST", "OPTIONS"]}})  # Enable CORS for all origins

# Initialize matcher
MATCHER = TravelMatcher(
    'regions.json',
    'cities.json'
)
# In-memory storage for trips (in production, use a real database)
TRIPS = {}

# --- API ENDPOINTS ---

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "message": "Travel Matcher API is running"})


@app.route('/api/trip/create', methods=['POST'])
def create_trip():
    """
    Create a new trip
    Body: {
        "trip_name": str,
        "organizer_name": str,
        "trip_type": str,
        "duration_days": int
    }
    """
    data = request.json
    
    trip_id = str(uuid.uuid4())[:8]  # Short ID
    
    trip = {
        "id": trip_id,
        "trip_name": data.get('trip_name', 'Untitled Trip'),
        "organizer_name": data.get('organizer_name'),
        "trip_type": data.get('trip_type'),
        "duration_days": data.get('duration_days'),
        "created_at": datetime.now().isoformat(),
        "status": "collecting_preferences",
        "participants": [],
        "results": None
    }
    
    TRIPS[trip_id] = trip
    
    return jsonify({
        "success": True,
        "trip_id": trip_id,
        "share_link": f"/join/{trip_id}"
    })


@app.route('/api/trip/<trip_id>', methods=['GET'])
def get_trip(trip_id):
    """Get trip details"""
    if trip_id not in TRIPS:
        return jsonify({"success": False, "error": "Trip not found"}), 404
    
    return jsonify({"success": True, "trip": TRIPS[trip_id]})


@app.route('/api/trip/<trip_id>/preferences', methods=['POST'])
def submit_preferences(trip_id):
    """
    Submit user preferences for a trip
    Body: {
        "name": str,
        "geographic_preference": str,
        "environment": [str],
        "style": [str],
        "activities": [str],
        "budget_range": [int, int],
        "climate": str
    }
    """
    if trip_id not in TRIPS:
        return jsonify({"success": False, "error": "Trip not found"}), 404
    
    data = request.json
    
    # Add participant
    participant = {
        "name": data.get('name'),
        "geographic_preference": data.get('geographic_preference'),
        "environment": data.get('environment', []),
        "style": data.get('style', []),
        "activities": data.get('activities', []),
        "budget_range": data.get('budget_range', [50, 150]),
        "climate": data.get('climate', 'flexible'),
        "submitted_at": datetime.now().isoformat()
    }
    
    # Check if user already submitted
    existing = [p for p in TRIPS[trip_id]['participants'] if p['name'] == participant['name']]
    if existing:
        # Update existing
        TRIPS[trip_id]['participants'] = [
            p if p['name'] != participant['name'] else participant
            for p in TRIPS[trip_id]['participants']
        ]
    else:
        # Add new
        TRIPS[trip_id]['participants'].append(participant)
    
    return jsonify({
        "success": True,
        "message": "Preferences saved",
        "participant_count": len(TRIPS[trip_id]['participants'])
    })


@app.route('/api/trip/<trip_id>/calculate', methods=['POST'])
def calculate_matches(trip_id):
    """
    Calculate destination matches for a trip
    """
    if trip_id not in TRIPS:
        return jsonify({"success": False, "error": "Trip not found"}), 404
    
    trip = TRIPS[trip_id]
    
    if len(trip['participants']) < 2:
        return jsonify({
            "success": False,
            "error": "Need at least 2 participants"
        }), 400
    
    # Analyze geographic preferences
    from collections import Counter
    geo_prefs = [p['geographic_preference'] for p in trip['participants']]
    geo_counter = Counter(geo_prefs)
    
    # Search across top geographic preferences
    all_results = []
    
    # Get unique scopes (excluding "Anywhere")
    scopes_to_search = [g for g in geo_counter.keys() if g != "Anywhere"]
    if not scopes_to_search:
        scopes_to_search = ["Europe", "Asia"]  # Default
    
    for scope in scopes_to_search[:3]:  # Top 3 geographic preferences
        try:
            results = MATCHER.calculate_region_match(
                users_preferences=trip['participants'],
                geographic_scope=scope,
                trip_type=trip['trip_type']
            )
            all_results.extend(results[:3])  # Top 3 from each
        except Exception as e:
            print(f"Error calculating for {scope}: {e}")
    
    # Sort all results by score
    all_results.sort(key=lambda x: x['score'], reverse=True)
    
    # Take top 7
    top_results = all_results[:7]
    
    # Format for frontend
    formatted_results = []
    for r in top_results:
        formatted_results.append({
            "region_id": r['region']['id'],
            "region_name": r['region']['name'],
            "country": r['region']['country'],
            "match_percentage": r['match_percentage'],
            "budget_range": r['region']['budget_range'],
            "environment": r['region']['environment'],
            "style": r['region']['style'],
            "pros": r['details']['pros'],
            "cons": r['details']['cons'],
            "user_breakdown": [
                {
                    "name": ub['user_name'],
                    "match_percentage": ub['match_percentage'],
                    "sentiment": ub['sentiment'],
                    "match_reasons": ub['match_reasons'][:3],
                    "mismatch_reasons": ub['mismatch_reasons'][:2]
                }
                for ub in r['user_breakdown']
            ]
        })
    
    # Save results
    trip['results'] = {
        "regions": formatted_results,
        "geographic_analysis": {
            "preferences": dict(geo_counter),
            "is_split": len(set(geo_prefs)) > 2
        },
        "calculated_at": datetime.now().isoformat()
    }
    trip['status'] = "results_ready"
    
    return jsonify({
        "success": True,
        "results": trip['results']
    })


@app.route('/api/trip/<trip_id>/vote', methods=['POST'])
def vote_destination(trip_id):
    """
    Vote for a destination
    Body: {
        "user_name": str,
        "region_id": str
    }
    """
    if trip_id not in TRIPS:
        return jsonify({"success": False, "error": "Trip not found"}), 404
    
    data = request.json
    
    if 'votes' not in TRIPS[trip_id]:
        TRIPS[trip_id]['votes'] = []
    
    # Remove any existing vote from this user
    TRIPS[trip_id]['votes'] = [
        v for v in TRIPS[trip_id]['votes']
        if v['user_name'] != data['user_name']
    ]
    
    # Add new vote
    TRIPS[trip_id]['votes'].append({
        "user_name": data['user_name'],
        "region_id": data['region_id'],
        "voted_at": datetime.now().isoformat()
    })
    
    # Count votes
    from collections import Counter
    vote_counts = Counter(v['region_id'] for v in TRIPS[trip_id]['votes'])
    
    return jsonify({
        "success": True,
        "vote_counts": dict(vote_counts),
        "total_votes": len(TRIPS[trip_id]['votes'])
    })


@app.route('/api/trip/<trip_id>/cities', methods=['POST'])
def get_cities(trip_id):
    """
    Get city recommendations for a chosen region
    Body: {
        "region_id": str
    }
    """
    if trip_id not in TRIPS:
        return jsonify({"success": False, "error": "Trip not found"}), 404
    
    data = request.json
    region_id = data.get('region_id')
    
    trip = TRIPS[trip_id]
    
    try:
        city_results = MATCHER.calculate_city_match(
            region_id=region_id,
            users_preferences=trip['participants'],
            trip_type=trip['trip_type']
        )
        
        # Format for frontend
        formatted_cities = []
        for c in city_results:
            formatted_cities.append({
                "city_name": c['city']['name'],
                "match_percentage": c['match_percentage'],
                "budget_range": c['city']['budget_range'],
                "best_for": c['details']['best_for'],
                "pros": c['details']['pros'],
                "user_breakdown": [
                    {
                        "name": ub['user_name'],
                        "match_percentage": ub['match_percentage'],
                        "sentiment": ub['sentiment']
                    }
                    for ub in c['user_breakdown']
                ]
            })
        
        return jsonify({
            "success": True,
            "cities": formatted_cities
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


if __name__ == '__main__':
    print("=" * 80)
    print("🚀 Travel Matcher API Starting...")
    print("=" * 80)
    print(f"Server running on http://localhost:5000")
    print(f"Health check: http://localhost:5000/api/health")
    print("=" * 80)
    
    app.run(debug=True, host='0.0.0.0', port=5001)

