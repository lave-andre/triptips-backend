import json
from typing import List, Dict, Any, Optional

class TravelMatcher:
    """
    Matches group travel preferences to destinations using a scoring algorithm.
    Works with the new enhanced database structure (150 regions, 500 cities).
    """

    def __init__(self, regions_file: str, cities_file: str, continents_file: Optional[str] = None):
        """
        Load destination databases.
        """
        # Load regions
        with open(regions_file, 'r') as f:
            data = json.load(f)
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

        # Load continents and build name -> id mapping
        self.continent_name_to_id = {}
        if continents_file:
            try:
                with open(continents_file, 'r') as f:
                    continents_data = json.load(f)
                    if isinstance(continents_data, dict) and "continents" in continents_data:
                        for cont in continents_data["continents"]:
                            name = cont.get("name")
                            cid = cont.get("id")
                            if name and cid:
                                self.continent_name_to_id[name] = cid
            except Exception as e:
                print(f"⚠️ Could not load continents file: {e}")

        print(f"✅ Loaded {len(self.regions)} regions and {len(self.cities)} cities")
        if self.regions:
            print(f"✅ Sample region: {self.regions[0].get('name', 'NONE')}")
        else:
            print("❌ No regions loaded!")

    def _flatten_activities(self, activities_obj: Dict) -> List[str]:
        """
        Convert nested activities object to flat list.
        NEW DB: {"water": ["swimming", "diving"], "cultural": ["museums"]}
        Returns: ["swimming", "diving", "museums"]
        """
        if isinstance(activities_obj, list):
            return activities_obj  # Already a list
        
        flat_list = []
        if isinstance(activities_obj, dict):
            for category, items in activities_obj.items():
                if isinstance(items, list):
                    flat_list.extend(items)
        return flat_list

    def _extract_style_tags(self, style_obj: Dict) -> List[str]:
        """
        Convert style scores to tags.
        NEW DB: {"romantic_score": 95, "adventure_level": 80, "party_scene": 60}
        Returns: ["romantic", "adventure"] (scores >= 75)
        """
        if isinstance(style_obj, list):
            return style_obj  # Already a list
        
        tags = []
        if isinstance(style_obj, dict):
            # Map score keys to simple tags
            mappings = {
                'romantic_score': 'romantic',
                'adventure_level': 'adventure',
                'party_scene': 'party',
                'culture_richness': 'cultural',
                'nature_immersion': 'nature',
                'luxury_level': 'luxury'
            }
            for key, tag in mappings.items():
                if style_obj.get(key, 0) >= 75:
                    tags.append(tag)
        return tags

    def _get_budget_range(self, budget_ranges_obj: Dict, user_budget: List[int]) -> List[int]:
        """
        Get appropriate budget range from new database structure.
        NEW DB: {"budget": [50, 95], "moderate": [95, 175], "comfortable": [175, 320], "luxury": [320, 650]}
        Returns best matching range as [min, max]
        """
        if isinstance(budget_ranges_obj, list):
            return budget_ranges_obj  # Old format
        
        if not isinstance(budget_ranges_obj, dict):
            return [50, 150]  # Default
        
        user_min, user_max = user_budget
        user_avg = (user_min + user_max) / 2
        
        # Find best matching tier
        tiers = ['budget', 'moderate', 'comfortable', 'luxury']
        for tier in tiers:
            if tier in budget_ranges_obj:
                tier_range = budget_ranges_obj[tier]
                if isinstance(tier_range, list) and len(tier_range) == 2:
                    tier_min, tier_max = tier_range
                    if user_avg <= tier_max:
                        return tier_range
        
        # Return moderate as fallback
        return budget_ranges_obj.get('moderate', [50, 150])

    def calculate_region_match(self, users_preferences: List[Dict], geographic_scope: str, trip_type: str = "friends_vacation") -> List[Dict]:
        """
        Calculate match scores for all regions based on user preferences.
        Returns sorted list of regions with match details.
        """
        print(f"🔍 calculate_region_match called with scope: {geographic_scope}, users: {len(users_preferences)}")
        scored_regions = []

        # Convert user's geographic scope (continent name) to continent ID
        scope_id = self.continent_name_to_id.get(geographic_scope, geographic_scope.lower().replace(' ', '-'))

        for region in self.regions:
            region_name = region.get('name', 'unknown')
            print(f"  Checking region: {region_name}")

            # Geographic scope matching using continent ID
            region_continent_id = region.get('continent', '').lower()
            is_geo_match = False

            if geographic_scope == "Anywhere":
                is_geo_match = True
            elif scope_id == region_continent_id:
                is_geo_match = True
            else:
                # Also check environment tags (for backward compatibility)
                tags = region.get('environment', [])
                normalized_tags = [tag.lower().replace(' ', '-') for tag in tags]
                if scope_id in normalized_tags or geographic_scope.lower() in normalized_tags:
                    is_geo_match = True

            if not is_geo_match:
                print(f"    ❌ Geographic mismatch (continent: {region_continent_id}, looking for: {scope_id})")
                continue

            print(f"    ✅ Geographic match")

            # Calculate score for this region
            region_score = 0
            user_breakdown = []

            for user in users_preferences:
                user_score = 0
                match_reasons = []
                mismatch_reasons = []

                # Environment match (same in both old and new DB)
                user_env = set(user.get('environment', []))
                region_env = set(region.get('environment', []))
                env_match = user_env & region_env
                
                if env_match:
                    user_score += 10 * len(env_match)
                    match_reasons.append(f"Environment: {', '.join(list(env_match)[:2])}")
                else:
                    mismatch_reasons.append("Environment doesn't match your preference")

                # Style match (NEW: convert style object to tags)
                user_style = set(user.get('style', []))
                region_style_obj = region.get('style', {})
                region_style_tags = set(self._extract_style_tags(region_style_obj))
                style_match = user_style & region_style_tags
                
                if style_match:
                    user_score += 8 * len(style_match)
                    match_reasons.append(f"Style: {', '.join(list(style_match)[:2])}")

                # Activities match (NEW: flatten nested activities)
                user_activities = set(user.get('activities', []))
                region_activities_obj = region.get('activities', {})
                region_activities_flat = set(self._flatten_activities(region_activities_obj))
                activity_match = user_activities & region_activities_flat
                
                if activity_match:
                    user_score += 5 * len(activity_match)
                    match_reasons.append(f"Activities: {', '.join(list(activity_match)[:2])}")

                # Budget match (NEW: handle budget_ranges object)
                user_budget_min, user_budget_max = user.get('budget_range', [50, 150])
                region_budget_obj = region.get('budget_ranges', {})
                region_budget_min, region_budget_max = self._get_budget_range(region_budget_obj, [user_budget_min, user_budget_max])

                # Check if ranges overlap
                if user_budget_max >= region_budget_min and region_budget_max >= user_budget_min:
                    user_score += 5
                    match_reasons.append("Budget range compatible")
                else:
                    mismatch_reasons.append("Outside your budget range")
                    user_score -= 10

                # Normalize to 0-100
                max_possible_score = 30
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
        return scored_regions[:10]

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
                
                # Environment match (cities have simpler structure)
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
        
        # NEW: Handle style as object
        style_obj = region.get('style', {})
        if isinstance(style_obj, dict):
            style_tags = self._extract_style_tags(style_obj)
            if style_tags:
                pros.append(f"{', '.join(style_tags[:2])} vibe")
        elif isinstance(style_obj, list) and style_obj:
            pros.append(f"{', '.join(style_obj[:2])} vibe")
        
        # NEW: Handle activities as nested object
        activities_obj = region.get('activities', {})
        if isinstance(activities_obj, dict):
            # Get first 2 activities from any category
            flat_activities = self._flatten_activities(activities_obj)[:2]
            if flat_activities:
                pros.append(f"{', '.join(flat_activities)} available")
        elif isinstance(activities_obj, list) and activities_obj:
            pros.append(f"{', '.join(activities_obj[:2])} available")
        
        if user_breakdown:
            good_count = sum(1 for u in user_breakdown if u['match_percentage'] >= 50)
            pros.append(f"Good for {good_count}/{len(user_breakdown)} travelers")
        
        return pros[:3]

    def _extract_cons(self, region: Dict, user_breakdown: List[Dict]) -> List[str]:
        """Extract top cons for a region"""
        cons = []
        if user_breakdown:
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
