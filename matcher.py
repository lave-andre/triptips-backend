import json
from typing import List, Dict, Any, Tuple

class TravelMatcher:
    """
    Matches group travel preferences to destinations using a scoring algorithm.
    """

    def __init__(self, regions_file: str, cities_file: str):
        """Load destination databases"""
        # Load regions
        with open(regions_file, 'r') as f:
            data = json.load(f)
            # Handle both new format (object with "regions" key) and old format (direct array)
            if isinstance(data, dict) and "regions" in data:
                self.regions = data["regions"]
            else:
                self.regions = data

        # Load cities
        with open(cities_file, 'r') as f:
            data = json.load(f)
            if isinstance(data, dict) and "cities" in data:
                self.cities = data["cities"]
            else:
                self.cities = data

    print(f"✅ Loaded {len(self.regions)} regions and {len(self.cities)} cities")
    print(f"Sample region: {self.regions[0]['name'] if self.regions else 'NONE'}")

    def calculate_region_match(self, users_preferences: List[Dict], geographic_scope: str, trip_type: str = "friends_vacation") -> List[Dict]:
        """
        Calculate match scores for all regions based on user preferences.
        Returns sorted list of regions with match details.
        """
        print(f"🔍 calculate_region_match called with scope: {geographic_scope}, users: {len(users_preferences)}")
        
        scored_regions = []
        
        for region in self.regions:
            print(f"  Checking region: {region.get('name', 'unknown')}")
            # Skip if geographic scope doesn't match
            if geographic_scope not in ["Anywhere", region.get("continent", "")] and \
               geographic_scope not in region.get("tags", []):
                continue
            if geographic_scope not in ["Anywhere", region.get("continent", "")] and geographic_scope not in region.get("tags", []):
                print(f"    ❌ Geographic mismatch")
                continue
            else:
                print(f"    ✅ Geographic match")
            # Calculate score for this region
            region_score = 0
            user_breakdown = []
            
            for user in users_preferences:
                user_score = 0
                match_reasons = []
                mismatch_reasons = []
                
                # Environment match
                env_match = set(user.get('environment', [])) & set(region.get('environment', []))
                if env_match:
                    user_score += 10 * len(env_match)
                    match_reasons.append(f"Environment: {', '.join(list(env_match)[:2])}")
                else:
                    mismatch_reasons.append("Environment doesn't match your preference")
                
                # Style match
                style_match = set(user.get('style', [])) & set(region.get('style', []))
                if style_match:
                    user_score += 8 * len(style_match)
                    match_reasons.append(f"Style: {', '.join(list(style_match)[:2])}")
                
                # Activities match
                user_activities = set(user.get('activities', []))
                region_activities = set(region.get('activities', []))
                activity_match = user_activities & region_activities
                if activity_match:
                    user_score += 5 * len(activity_match)
                    match_reasons.append(f"Activities: {', '.join(list(activity_match)[:2])}")
                
                # Budget match
                user_budget_min, user_budget_max = user.get('budget_range', [50, 150])
                region_budget_min, region_budget_max = region.get('budget_range', [50, 150])
                
                # Check if ranges overlap
                if user_budget_max >= region_budget_min and region_budget_max >= user_budget_min:
                    user_score += 5
                    match_reasons.append("Budget range compatible")
                else:
                    mismatch_reasons.append("Outside your budget range")
                    user_score -= 10
                
                # Normalize to 0-100
                max_possible_score = 30  # Environment (max 20) + Style (max 16) + Activities (max 15) + Budget (5) = 56, but we cap at 30
                normalized_score = min(100, (user_score / 30) * 100) if user_score > 0 else 0
                
                # Determine sentiment
                if normalized_score >= 70:
                    sentiment = "Perfect for"
                elif normalized_score >= 50:
                    sentiment = "Good for"
                else:
                    sentiment = "Compromise for"
                
                region_score += normalized_score
                user_breakdown.append({
                    "user_name": user.get('name', 'Anonymous'),
                    "match_percentage": round(normalized_score, 1),
                    "sentiment": sentiment,
                    "match_reasons": match_reasons[:3],
                    "mismatch_reasons": mismatch_reasons[:2]
                })
            
            # Average score across users
            avg_score = region_score / len(users_preferences) if users_preferences else 0
            
            # Only include if average score > 20 (threshold)
            if avg_score > 20:
                scored_regions.append({
                    "region": region,
                    "score": avg_score,
                    "match_percentage": round(avg_score, 1),
                    "user_breakdown": user_breakdown,
                    "details": {
                        "pros": self._extract_pros(region, user_breakdown),
                        "cons": self._extract_cons(region, user_breakdown)
                    }
                })
        
        # Sort by score descending
        scored_regions.sort(key=lambda x: x['score'], reverse=True)
        print(f"🔚 Returning {len(scored_regions)} regions")
        return scored_regions[:10]  # Return top 10

    def calculate_city_match(self, region_id: str, users_preferences: List[Dict], trip_type: str = "friends_vacation") -> List[Dict]:
        """
        Calculate match scores for cities within a specific region.
        """
        # Find cities belonging to this region
        region_cities = [c for c in self.cities if c.get('region_id') == region_id or c.get('region') == region_id]
        
        if not region_cities:
            return []
        
        scored_cities = []
        for city in region_cities:
            city_score = 0
            user_breakdown = []
            
            for user in users_preferences:
                user_score = 0
                # Simplified scoring for cities (can be expanded)
                # Environment match
                env_match = set(user.get('environment', [])) & set(city.get('environment', []))
                if env_match:
                    user_score += 10 * len(env_match)
                
                # Activities match
                act_match = set(user.get('activities', [])) & set(city.get('activities', []))
                if act_match:
                    user_score += 5 * len(act_match)
                
                # Budget match
                user_budget_min, user_budget_max = user.get('budget_range', [50, 150])
                city_budget_min, city_budget_max = city.get('budget_range', [50, 150])
                if user_budget_max >= city_budget_min and city_budget_max >= user_budget_min:
                    user_score += 5
                
                normalized_score = min(100, (user_score / 20) * 100) if user_score > 0 else 0
                
                if normalized_score >= 70:
                    sentiment = "Perfect for"
                elif normalized_score >= 50:
                    sentiment = "Good for"
                else:
                    sentiment = "Compromise for"
                
                city_score += normalized_score
                user_breakdown.append({
                    "user_name": user.get('name', 'Anonymous'),
                    "match_percentage": round(normalized_score, 1),
                    "sentiment": sentiment
                })
            
            avg_score = city_score / len(users_preferences) if users_preferences else 0
            
            scored_cities.append({
                "city": city,
                "score": avg_score,
                "match_percentage": round(avg_score, 1),
                "user_breakdown": user_breakdown,
                "details": {
                    "best_for": self._best_for(city, user_breakdown),
                    "pros": self._city_pros(city, user_breakdown)
                }
            })
        
        scored_cities.sort(key=lambda x: x['score'], reverse=True)
        return scored_cities[:5]

    def _extract_pros(self, region: Dict, user_breakdown: List[Dict]) -> List[str]:
        """Extract top pros for a region based on user breakdown"""
        pros = []
        if region.get('environment'):
            pros.append(f"{', '.join(region['environment'][:2])} environment")
        if region.get('style'):
            pros.append(f"{', '.join(region['style'][:2])} vibe")
        if region.get('activities'):
            pros.append(f"{', '.join(region['activities'][:2])} available")
        if user_breakdown:
            # Count how many users it's good for
            good_count = sum(1 for u in user_breakdown if u['match_percentage'] >= 50)
            pros.append(f"Good for {good_count}/{len(user_breakdown)} travelers")
        return pros[:3]

    def _extract_cons(self, region: Dict, user_breakdown: List[Dict]) -> List[str]:
        """Extract top cons for a region"""
        cons = []
        if user_breakdown:
            # Count how many users it's a compromise for
            compromise_count = sum(1 for u in user_breakdown if u['match_percentage'] < 50)
            if compromise_count > 0:
                cons.append(f"Compromise for {compromise_count} traveler(s)")
        return cons[:2]

    def _best_for(self, city: Dict, user_breakdown: List[Dict]) -> str:
        """Generate a short 'best for' description"""
        tags = []
        if city.get('style'):
            tags.extend(city['style'][:2])
        if city.get('environment'):
            tags.extend(city['environment'][:1])
        return f"{', '.join(tags)} seekers" if tags else "Versatile destination"

    def _city_pros(self, city: Dict, user_breakdown: List[Dict]) -> List[str]:
        """Extract city pros"""
        pros = []
        if city.get('environment'):
            pros.append(f"{', '.join(city['environment'][:2])}")
        if city.get('budget_range'):
            pros.append(f"Budget: ${city['budget_range'][0]}-${city['budget_range'][1]}/day")
        if user_breakdown:
            good_count = sum(1 for u in user_breakdown if u['match_percentage'] >= 50)
            pros.append(f"Matches {good_count}/{len(user_breakdown)} preferences")
        return pros[:3]
