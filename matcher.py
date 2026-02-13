import json
from typing import List, Dict, Any
from collections import Counter

class TravelMatcher:
    """
    Matches group travel preferences to destinations using a scoring algorithm.
    """
    
def __init__(self, regions_file: str, cities_file: str):
    """Load destination databases"""
    with open(regions_file, 'r') as f:
        data = json.load(f)
        # New format: data is an object with "regions" key containing the array
        if isinstance(data, dict) and "regions" in data:
            self.regions = data["regions"]
        else:
            # Fallback for old format (direct array)
            self.regions = data

    with open(cities_file, 'r') as f:
        data = json.load(f)
        if isinstance(data, dict) and "cities" in data:
            self.cities = data["cities"]
        else:
            self.cities = data
    
    def calculate_region_match(
        self,
        users_preferences: List[Dict[str, Any]],
        geographic_scope: str,
        trip_type: str
    ) -> List[Dict[str, Any]]:
        """
        Calculate match scores for regions based on group preferences.
        
        Args:
            users_preferences: List of user preference dictionaries
            geographic_scope: Continent or region (e.g., "Europe", "Asia")
            trip_type: Type of trip (affects weighting)
        
        Returns:
            Sorted list of regions with match scores and details
        """
        scored_regions = []
        
        # Filter regions by geographic scope
        eligible_regions = [
            r for r in self.regions 
            if geographic_scope in r.get('region_tags', []) or geographic_scope == "Anywhere"
        ]
        
        for region in eligible_regions:
            score_details = self._score_region(region, users_preferences, trip_type)
            
            # Include all regions (we'll filter later if needed)
            scored_regions.append({
                'region': region,
                'score': score_details['total_score'],
                'match_percentage': score_details['match_percentage'],
                'details': score_details,
                'user_breakdown': score_details['user_breakdown']
            })
        
        # Sort by score descending
        scored_regions.sort(key=lambda x: x['score'], reverse=True)
        
        return scored_regions[:7]  # Return top 7
    
    def _score_region(
        self,
        region: Dict,
        users_preferences: List[Dict],
        trip_type: str
    ) -> Dict[str, Any]:
        """Score a single region against all users' preferences"""
        
        total_score = 0
        max_possible_score = 0
        user_scores = []
        
        # Get user weights based on trip type
        weights = self._get_user_weights(users_preferences, trip_type)
        
        for i, user_prefs in enumerate(users_preferences):
            user_weight = weights[i]
            user_score = 0
            user_max = 0
            match_reasons = []
            mismatch_reasons = []
            
            # 1. HARD CONSTRAINTS - Budget (veto power)
            budget_min, budget_max = user_prefs.get('budget_range', [0, 1000])
            region_budget_max = region['budget_range'][1]
            
            if region_budget_max > budget_max + 50:  # Allow $50 flexibility
                # Budget veto - this user can't afford it
                mismatch_reasons.append(f"Above budget (${region_budget_max}/day vs ${budget_max}/day max)")
                user_score -= 20 * user_weight
                user_max += 20 * user_weight
            else:
                # Budget OK
                match_reasons.append("Within budget")
            
            # 2. ENVIRONMENT MATCH (High priority - 10 points per match)
            user_envs = set(user_prefs.get('environment', []))
            region_envs = set(region.get('environment', []))
            env_matches = user_envs & region_envs
            
            if env_matches:
                env_score = len(env_matches) * 10 * user_weight
                user_score += env_score
                match_reasons.append(f"Environment: {', '.join(env_matches)}")
            else:
                mismatch_reasons.append(f"Environment mismatch (wants: {', '.join(user_envs)})")
            
            user_max += len(user_envs) * 10 * user_weight
            
            # 3. TRIP STYLE MATCH (High priority - 8 points per match)
            user_styles = set(user_prefs.get('style', []))
            region_styles = set(region.get('style', []))
            style_matches = user_styles & region_styles
            
            if style_matches:
                style_score = len(style_matches) * 8 * user_weight
                user_score += style_score
                match_reasons.append(f"Style: {', '.join(style_matches)}")
            else:
                mismatch_reasons.append(f"Style mismatch (wants: {', '.join(user_styles)})")
            
            user_max += len(user_styles) * 8 * user_weight
            
            # 4. ACTIVITIES MATCH (Medium priority - 3 points per match)
            user_activities = set(user_prefs.get('activities', []))
            region_activities = set(region.get('activities', []))
            activity_matches = user_activities & region_activities
            
            if activity_matches:
                activity_score = len(activity_matches) * 3 * user_weight
                user_score += activity_score
                match_reasons.append(f"{len(activity_matches)} activities available")
            
            user_max += len(user_activities) * 3 * user_weight
            
            # 5. CLIMATE PREFERENCE (Low priority - 2 points)
            user_climate = user_prefs.get('climate')
            region_climate = region.get('climate')
            
            if user_climate and user_climate == region_climate:
                climate_score = 2 * user_weight
                user_score += climate_score
                match_reasons.append(f"Climate: {region_climate}")
            
            user_max += 2 * user_weight
            
            # 6. ADDITIONAL SCORING FACTORS
            # Nightlife (if user wants party)
            if 'party' in user_prefs.get('style', []):
                nightlife_score = region.get('nightlife_score', 0)
                if nightlife_score >= 4:
                    user_score += 3 * user_weight
                    match_reasons.append("Good nightlife")
                user_max += 5 * user_weight
            
            # Family friendly (if family trip)
            if trip_type in ['family_with_kids', 'family_without_kids']:
                family_score = region.get('family_friendly', 0)
                if family_score >= 4:
                    user_score += 3 * user_weight
                    match_reasons.append("Family friendly")
                user_max += 5 * user_weight
            
            # Culture (if user wants cultural)
            if 'cultural' in user_prefs.get('style', []):
                culture_score = region.get('culture_score', 0)
                if culture_score >= 4:
                    user_score += 3 * user_weight
                    match_reasons.append("Rich culture")
                user_max += 5 * user_weight
            
            # Calculate user's match percentage
            user_match_pct = (user_score / user_max * 100) if user_max > 0 else 0
            
            user_scores.append({
                'user_index': i,
                'user_name': user_prefs.get('name', f'User {i+1}'),
                'score': user_score,
                'max_possible': user_max,
                'match_percentage': user_match_pct,
                'match_reasons': match_reasons,
                'mismatch_reasons': mismatch_reasons,
                'sentiment': self._get_sentiment(user_match_pct)
            })
            
            total_score += user_score
            max_possible_score += user_max
        
        # Calculate overall match percentage
        match_percentage = (total_score / max_possible_score * 100) if max_possible_score > 0 else 0
        
        # Identify consensus and conflicts
        consensus_analysis = self._analyze_consensus(region, users_preferences)
        
        return {
            'total_score': total_score,
            'max_possible_score': max_possible_score,
            'match_percentage': round(match_percentage, 1),
            'user_breakdown': user_scores,
            'consensus': consensus_analysis,
            'pros': self._generate_pros(region, users_preferences),
            'cons': self._generate_cons(region, users_preferences)
        }
    
    def _get_user_weights(self, users_preferences: List[Dict], trip_type: str) -> List[float]:
        """Calculate weighting for each user based on trip type"""
        weights = [1.0] * len(users_preferences)
        
        # For family trips, parents might get slightly higher weight
        # For now, keeping equal weights for MVP
        # Could add: organizer gets 1.2x, first-timers get 1.1x, etc.
        
        return weights
    
    def _get_sentiment(self, match_pct: float) -> str:
        """Get sentiment label based on match percentage"""
        if match_pct >= 85:
            return "Perfect for"
        elif match_pct >= 70:
            return "Great for"
        elif match_pct >= 55:
            return "Good for"
        else:
            return "Compromise for"
    
    def _analyze_consensus(self, region: Dict, users_preferences: List[Dict]) -> Dict:
        """Analyze group consensus on key preferences"""
        
        # Environment preferences
        all_envs = [env for user in users_preferences for env in user.get('environment', [])]
        env_counter = Counter(all_envs)
        
        # Style preferences  
        all_styles = [style for user in users_preferences for style in user.get('style', [])]
        style_counter = Counter(all_styles)
        
        # Check what % of group wants each preference
        group_size = len(users_preferences)
        
        consensus = {
            'environment': {
                'majority': env_counter.most_common(1)[0] if env_counter else None,
                'split': len(set(all_envs)) > 2,
                'distribution': dict(env_counter)
            },
            'style': {
                'majority': style_counter.most_common(1)[0] if style_counter else None,
                'split': len(set(all_styles)) > 2,
                'distribution': dict(style_counter)
            }
        }
        
        return consensus
    
    def _generate_pros(self, region: Dict, users_preferences: List[Dict]) -> List[str]:
        """Generate list of pros for this region"""
        pros = []
        
        # Check environment variety
        if len(region.get('environment', [])) >= 3:
            pros.append(f"Diverse environments: {', '.join(region['environment'])}")
        
        # Check activity variety
        if len(region.get('activities', [])) >= 7:
            pros.append(f"Wide range of activities ({len(region['activities'])} options)")
        
        # Budget friendly?
        if region['budget_range'][1] < 100:
            pros.append(f"Budget-friendly (${region['budget_range'][0]}-${region['budget_range'][1]}/day)")
        
        # Family friendly?
        if region.get('family_friendly', 0) >= 4:
            pros.append("Family-friendly destination")
        
        # Nightlife?
        if region.get('nightlife_score', 0) >= 4:
            pros.append("Excellent nightlife scene")
        
        # Culture?
        if region.get('culture_score', 0) >= 4:
            pros.append("Rich cultural experiences")
        
        return pros[:5]  # Limit to top 5
    
    def _generate_cons(self, region: Dict, users_preferences: List[Dict]) -> List[str]:
        """Generate list of potential compromises/cons"""
        cons = []
        
        # Budget concerns
        budget_over_count = sum(
            1 for user in users_preferences 
            if region['budget_range'][1] > user.get('budget_range', [0, 1000])[1]
        )
        if budget_over_count > 0:
            cons.append(f"Above budget for {budget_over_count}/{len(users_preferences)} travelers")
        
        # Environment mismatches
        all_wanted_envs = set(env for user in users_preferences for env in user.get('environment', []))
        region_envs = set(region.get('environment', []))
        missing_envs = all_wanted_envs - region_envs
        
        if missing_envs:
            cons.append(f"No {', '.join(list(missing_envs)[:2])} environment")
        
        # Style mismatches
        all_wanted_styles = set(style for user in users_preferences for style in user.get('style', []))
        region_styles = set(region.get('style', []))
        missing_styles = all_wanted_styles - region_styles
        
        if missing_styles:
            cons.append(f"Limited {', '.join(list(missing_styles)[:2])} options")
        
        # Low nightlife
        if region.get('nightlife_score', 0) <= 2 and any('party' in user.get('style', []) for user in users_preferences):
            cons.append("Limited nightlife")
        
        # Not family friendly
        if region.get('family_friendly', 0) <= 2:
            cons.append("Less suitable for young children")
        
        return cons[:4]  # Limit to top 4
    
    def calculate_city_match(
        self,
        region_id: str,
        users_preferences: List[Dict],
        trip_type: str
    ) -> List[Dict[str, Any]]:
        """
        Calculate match scores for cities within a chosen region.
        Similar to region matching but more granular.
        """
        # Get cities for this region
        region_cities = [c for c in self.cities if c.get('region_id') == region_id]
        
        scored_cities = []
        
        for city in region_cities:
            score_details = self._score_city(city, users_preferences, trip_type)
            
            scored_cities.append({
                'city': city,
                'score': score_details['total_score'],
                'match_percentage': score_details['match_percentage'],
                'details': score_details,
                'user_breakdown': score_details['user_breakdown']
            })
        
        # Sort by score
        scored_cities.sort(key=lambda x: x['score'], reverse=True)
        
        return scored_cities[:5]  # Return top 5 cities
    
    def _score_city(self, city: Dict, users_preferences: List[Dict], trip_type: str) -> Dict:
        """Score a city - similar logic to region scoring but with city-specific data"""
        # Very similar to _score_region, using city-level data
        # For MVP, we can reuse the same logic
        
        total_score = 0
        max_possible_score = 0
        user_scores = []
        
        weights = self._get_user_weights(users_preferences, trip_type)
        
        for i, user_prefs in enumerate(users_preferences):
            user_weight = weights[i]
            user_score = 0
            user_max = 0
            match_reasons = []
            mismatch_reasons = []
            
            # Budget check
            budget_min, budget_max = user_prefs.get('budget_range', [0, 1000])
            city_budget_max = city['budget_range'][1]
            
            if city_budget_max > budget_max + 50:
                mismatch_reasons.append(f"Above budget")
                user_score -= 20 * user_weight
                user_max += 20 * user_weight
            else:
                match_reasons.append("Within budget")
            
            # Environment
            user_envs = set(user_prefs.get('environment', []))
            city_envs = set(city.get('environment', []))
            env_matches = user_envs & city_envs
            
            if env_matches:
                user_score += len(env_matches) * 10 * user_weight
                match_reasons.append(f"{', '.join(env_matches)}")
            
            user_max += len(user_envs) * 10 * user_weight
            
            # Style
            user_styles = set(user_prefs.get('style', []))
            city_styles = set(city.get('style', []))
            style_matches = user_styles & city_styles
            
            if style_matches:
                user_score += len(style_matches) * 8 * user_weight
                match_reasons.append(f"{', '.join(style_matches)}")
            
            user_max += len(user_styles) * 8 * user_weight
            
            # Activities
            user_activities = set(user_prefs.get('activities', []))
            city_activities = set(city.get('activities', []))
            activity_matches = user_activities & city_activities
            
            if activity_matches:
                user_score += len(activity_matches) * 3 * user_weight
                match_reasons.append(f"{len(activity_matches)} activities")
            
            user_max += len(user_activities) * 3 * user_weight
            
            # Nightlife, family-friendly, culture (same as region)
            if 'party' in user_prefs.get('style', []):
                if city.get('nightlife_score', 0) >= 4:
                    user_score += 3 * user_weight
                    match_reasons.append("Great nightlife")
                user_max += 5 * user_weight
            
            user_match_pct = (user_score / user_max * 100) if user_max > 0 else 0
            
            user_scores.append({
                'user_index': i,
                'user_name': user_prefs.get('name', f'User {i+1}'),
                'score': user_score,
                'max_possible': user_max,
                'match_percentage': user_match_pct,
                'match_reasons': match_reasons,
                'mismatch_reasons': mismatch_reasons,
                'sentiment': self._get_sentiment(user_match_pct)
            })
            
            total_score += user_score
            max_possible_score += user_max
        
        match_percentage = (total_score / max_possible_score * 100) if max_possible_score > 0 else 0
        
        return {
            'total_score': total_score,
            'max_possible_score': max_possible_score,
            'match_percentage': round(match_percentage, 1),
            'user_breakdown': user_scores,
            'best_for': city.get('best_for', ''),
            'pros': self._generate_city_pros(city),
            'cons': self._generate_city_cons(city, users_preferences)
        }
    
    def _generate_city_pros(self, city: Dict) -> List[str]:
        """Generate pros for a specific city"""
        pros = []
        
        if city.get('nightlife_score', 0) >= 4:
            pros.append("Excellent nightlife")
        if city.get('family_friendly', 0) >= 4:
            pros.append("Very family-friendly")
        if city.get('culture_score', 0) >= 4:
            pros.append("Rich cultural attractions")
        if city['budget_range'][1] < 100:
            pros.append("Budget-friendly")
        if len(city.get('activities', [])) >= 6:
            pros.append(f"Many activities available")
        
        # Add the city's "best_for" description
        if city.get('best_for'):
            pros.append(city['best_for'])
        
        return pros[:4]
    
    def _generate_city_cons(self, city: Dict, users_preferences: List[Dict]) -> List[str]:
        """Generate cons for a specific city"""
        cons = []
        
        # Check budget mismatches
        budget_issues = sum(
            1 for user in users_preferences 
            if city['budget_range'][1] > user.get('budget_range', [0, 1000])[1]
        )
        if budget_issues > 0:
            cons.append(f"May be pricey for some")
        
        if city.get('nightlife_score', 0) <= 2:
            cons.append("Limited nightlife")
        if city.get('family_friendly', 0) <= 2:
            cons.append("Not ideal for young kids")
        
        return cons[:3]


def format_region_results(results: List[Dict]) -> str:
    """Format region matching results for display"""
    output = []
    
    output.append("=" * 80)
    output.append("TOP DESTINATION RECOMMENDATIONS")
    output.append("=" * 80)
    output.append("")
    
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣"]
    
    for idx, result in enumerate(results):
        region = result['region']
        details = result['details']
        
        output.append(f"{medals[idx]} {idx + 1}. {region['name']} - {result['match_percentage']:.0f}% MATCH")
        output.append("-" * 80)
        
        # Budget info
        budget_str = f"${region['budget_range'][0]}-${region['budget_range'][1]}/day"
        output.append(f"💰 Budget: {budget_str}")
        output.append("")
        
        # Pros
        if details['pros']:
            output.append("✅ PROS:")
            for pro in details['pros']:
                output.append(f"   • {pro}")
            output.append("")
        
        # Cons
        if details['cons']:
            output.append("⚠️  CONSIDERATIONS:")
            for con in details['cons']:
                output.append(f"   • {con}")
            output.append("")
        
        # User breakdown
        output.append("👥 GROUP FIT:")
        for user_score in details['user_breakdown']:
            sentiment = user_score['sentiment']
            name = user_score['user_name']
            pct = user_score['match_percentage']
            
            output.append(f"   {sentiment}: {name} ({pct:.0f}% match)")
            if user_score['match_reasons']:
                output.append(f"      ↳ {', '.join(user_score['match_reasons'][:3])}")
        
        output.append("")
        output.append("")
    
    return "\n".join(output)


def format_city_results(results: List[Dict], region_name: str) -> str:
    """Format city matching results for display"""
    output = []
    
    output.append("=" * 80)
    output.append(f"TOP CITIES IN {region_name.upper()}")
    output.append("=" * 80)
    output.append("")
    
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    
    for idx, result in enumerate(results):
        city = result['city']
        details = result['details']
        
        output.append(f"{medals[idx]} {idx + 1}. {city['name']} - {result['match_percentage']:.0f}% MATCH")
        output.append("-" * 80)
        
        # Best for
        if details['best_for']:
            output.append(f"🎯 {details['best_for']}")
            output.append("")
        
        # Budget
        budget_str = f"${city['budget_range'][0]}-${city['budget_range'][1]}/day"
        output.append(f"💰 Budget: {budget_str}")
        output.append("")
        
        # Pros
        if details['pros']:
            output.append("✅ HIGHLIGHTS:")
            for pro in details['pros']:
                output.append(f"   • {pro}")
            output.append("")
        
        # User breakdown
        output.append("👥 WHO IT'S BEST FOR:")
        for user_score in details['user_breakdown']:
            sentiment = user_score['sentiment']
            name = user_score['user_name']
            pct = user_score['match_percentage']
            
            output.append(f"   {sentiment}: {name} ({pct:.0f}%)")
        
        output.append("")
        output.append("")
    
    return "\n".join(output)
