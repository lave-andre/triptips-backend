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
    'cities.json',
    'continents.json' 
)
# In-memory storage for trips (in production, use a real database)
TRIPS = {}

# --- API ENDPOINTS ---

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "message": "Travel Matcher API is running"})


@app.route('/api/trip', methods=['POST'])
def create_trip():
    """
    Create a new trip
    Body: {
        "trip_name": str,
        "organizer_name": str,
        "geographic_scope": str,
        "organizer_preferences": {...}  (optional - organizer's preferences)
    }
    """
    data = request.json
    
    trip_id = str(uuid.uuid4())[:8]  # Short ID
    
    # Create trip
    trip = {
        "id": trip_id,
        "trip_name": data.get('trip_name', 'Untitled Trip'),
        "organizer_name": data.get('organizer_name'),
        "geographic_scope": data.get('geographic_scope', 'Anywhere'),
        "trip_type": data.get('trip_type', 'friends_adventure'),
        "duration_days": data.get('duration_days', 7),
        "created_at": datetime.now().isoformat(),
        "status": "collecting_preferences",
        "participants": [],
        "results": None
    }
    
    # If organizer submitted preferences, add them as first participant
    if 'organizer_preferences' in data:
        organizer_prefs = data['organizer_preferences']
        organizer_prefs['name'] = data.get('organizer_name')
        trip['participants'].append(organizer_prefs)
    
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
        "environment": [str],
        "style": [str],
        "activities": [str],
        "budget_range": [int, int]
    }
    """
    if trip_id not in TRIPS:
        return jsonify({"success": False, "error": "Trip not found"}), 404
    
    data = request.json
    
    # Add participant
    participant = {
        "name": data.get('name'),
        "environment": data.get('environment', []),
        "style": data.get('style', []),
        "activities": data.get('activities', []),
        "budget_range": data.get('budget_range', [50, 150]),
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
    
    if len(trip['participants']) < 1:
        return jsonify({
            "success": False,
            "error": "Need at least 1 participant"
        }), 400
    
    # Get geographic scope from trip
    geographic_scope = trip.get('geographic_scope', 'Anywhere')

    print(f"DEBUG: Participants = {trip['participants']}")
    print(f"DEBUG: Geographic scope = {geographic_scope}")
    
    try:
        results = MATCHER.calculate_region_match(
            users_preferences=trip['participants'],
            geographic_scope=geographic_scope,
            trip_type="friends_vacation"
        )
        
        # Take top 10
        top_results = results[:10]
        
        # Format for frontend
        formatted_results = []
        for r in top_results:
            # Get budget range from new structure
            budget_ranges_obj = r['region'].get('budget_ranges', {})
            if isinstance(budget_ranges_obj, dict):
                budget_range = budget_ranges_obj.get('moderate', [50, 150])
            else:
                budget_range = [50, 150]
            
            # Get style from new structure
            style_obj = r['region'].get('style', {})
            if isinstance(style_obj, dict):
                # Extract high-scoring styles
                style_list = []
                style_mappings = {
                    'romantic_score': 'romantic',
                    'adventure_level': 'adventure',
                    'party_scene': 'party',
                    'culture_richness': 'cultural',
                    'nature_immersion': 'nature',
                    'luxury_level': 'luxury'
                }
                for key, tag in style_mappings.items():
                    if style_obj.get(key, 0) >= 75:
                        style_list.append(tag)
                style = style_list
            else:
                style = style_obj if isinstance(style_obj, list) else []
            
            formatted_results.append({
                "region_id": r['region']['id'],
                "region_name": r['region']['name'],
                "country": r['region']['country'],
                "match_percentage": r['match_percentage'],
                "budget_range": budget_range,
                "environment": r['region'].get('environment', []),
                "style": style,
                "pros": r['details']['pros'],
                "cons": r['details']['cons'],
                "user_breakdown": [
                    {
                        "name": ub['user_name'],
                        "match_percentage": ub['match_percentage'],
                        "sentiment": ub['sentiment'],
                        "match_reasons": ub.get('match_reasons', [])[:3],
                        "mismatch_reasons": ub.get('mismatch_reasons', [])[:2]
                    }
                    for ub in r['user_breakdown']
                ]
            })
        print(f"DEBUG: Got {len(results)} results")
        for r in results[:3]:
            print(f"  - {r['region']['name']}: {r['score']}")
        # Save results
        trip['results'] = {
            "regions": formatted_results,
            "geographic_scope": geographic_scope,
            "calculated_at": datetime.now().isoformat()
        }
        trip['status'] = "results_ready"
        
        return jsonify({
            "success": True,
            "results": trip['results']
        })
        
    except Exception as e:
        print(f"❌ Error in calculate_matches: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


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

    print(f"🏙️ get_cities called for region_id: {region_id}", flush=True)
    print(f"🏙️ Trip has {len(trip['participants'])} participants", flush=True)
    
    trip = TRIPS[trip_id]
    
    try:
        city_results = MATCHER.calculate_city_match(
            region_id=region_id,
            users_preferences=trip['participants'],
            trip_type="friends_vacation"
        )
        
        # Format for frontend
        formatted_cities = []
        for c in city_results:
            formatted_cities.append({
                "city_name": c['city']['name'],
                "match_percentage": c['match_percentage'],
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
        print(f"❌ Error getting cities: {e}")
        import traceback
        traceback.print_exc()
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
