import json
from typing import List, Dict, Any, Optional

class TravelMatcher:
    """
    Matches group travel preferences to destinations using a scoring algorithm.
    """

    def __init__(self, regions_file: str, cities_file: str, continents_file: Optional[str] = None):
        """
        Load destination databases.
        If continents_file is provided, build a name->id mapping for geographic matching.
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
                # Also check tags (normalized)
                tags = region.get('tags', [])
                normalized_tags = [tag.lower().replace(' ', '-') for tag in tags]
                if scope_id in normalized_tags or geographic_scope.lower() in normalized_tags:
                    is_geo_match = True

            if not is_geo_match:
                print(f"    ❌ Geographic mismatch (continent ID: {region_continent_id})")
                continue

            print(f"    ✅ Geographic match")

            # Calculate score for this region (same as before)
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

                if user_budget_max >= region_budget_min and region_budget_max >= user_budget_min:
                    user_score += 5
                    match_reasons.append("Budget range compatible")
                else:
                    mismatch_reasons.append("Outside your budget range")
                    user_score -= 10

                # Normalize to 0-100
                max_possible_score = 30
                normalized_score = min(100, (user_score / 30) * 100) if user_score > 0 else 0

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

            avg_score = region_score / len(users_preferences) if users_preferences else 0

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

        scored_regions.sort(key=lambda x: x['score'], reverse=True)
        print(f"🔚 Returning {len(scored_regions)} regions")
        return scored_regions[:10]

    # --- all other methods (_extract_pros, _extract_cons, calculate_city_match, etc.) remain exactly the same as before ---
    # (I'll include them in the full file below, but for brevity they are unchanged)
