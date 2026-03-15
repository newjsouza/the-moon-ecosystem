from typing import Dict, List, Tuple

class SportsAnalyzer:
    """
    Implements APEX validation rules and Kelly Criterion for betting analysis.
    """
    
    def __init__(self, banca_total: float, safe_fraction: float = 0.25):
        self.banca_total = banca_total
        self.safe_fraction = safe_fraction
        self.stop_loss_limit = banca_total * 0.12
        self.max_stake_limit = banca_total * 0.05
        self.min_probability = 0.40

    def calculate_kelly_stake(self, probability: float, odds: float) -> float:
        """
        Calculates the recommended stake using the Kelly Criterion.
        Formula: f = (P * O - 1) / (O - 1) * F
        """
        if odds <= 1:
            return 0.0
            
        kelly_fraction = (probability * odds - 1) / (odds - 1)
        recommended_stake = (kelly_fraction * self.safe_fraction) * self.banca_total
        
        # Ensure minimum stake or clamp to zero if negative
        return max(0.0, recommended_stake)

    def validate_bet(self, match_data: Dict, live_data: Dict, qualitative_score: float = 5.0) -> Dict:
        """
        Validates a bet based on combined data:
        1. Base probability from odds.
        2. Adjust with qualitative score (AI reasoning).
        3. Check APEX safety rules.
        """
        messages = []
        is_approved = True
        
        # 1. Base Probability (Implied from Odds)
        # Assuming odds are for 'Home Win'
        odds = 2.0 # Default if not found
        try:
             # Basic extraction for football-data.org structure
             if 'odds' in match_data:
                 odds = match_data['odds'].get('homeWin', 2.0)
        except:
             pass
             
        implied_prob = 1 / odds
        
        # 2. Adjust with Qualitative Score (1-10)
        # 5 is neutral, >5 increases prob, <5 decreases
        adjustment = (qualitative_score - 5) * 0.05
        adjusted_prob = implied_prob + adjustment
        
        # Rules validation
        # Rule 1: Minimum Adjusted Probability
        if adjusted_prob < self.min_probability:
            messages.append(f"❌ Probabilidade ajustada baixa ({adjusted_prob*100:.1f}% < {self.min_probability*100:.0f}%)")
            is_approved = False

        # Rule 2: Kelly Criterion
        final_stake = 0.0
        if is_approved:
            final_stake = self.calculate_kelly_stake(adjusted_prob, odds)
            if final_stake <= 0:
                messages.append("❌ Valor de aposta Kelly insuficiente (valor esperado negativo)")
                is_approved = False
        
        # Rule 3: Max Stake Limit
        if final_stake > self.max_stake_limit:
            messages.append(f"⚠️ Stake reduzido para o limite de 5% (R${self.max_stake_limit:.2f})")
            final_stake = self.max_stake_limit

        if is_approved:
            messages.append(f"✅ APROVADO: Probabilidade {adjusted_prob*100:.1f}%, Stake R${final_stake:.2f}")

        return {
            "approved": is_approved,
            "messages": messages,
            "probability": adjusted_prob,
            "kelly_stake": final_stake,
            "odds": odds
        }

    def analyze_opportunity(self, match_data: Dict, live_data: Dict, qualitative_score: float = 5.0) -> Dict:
        """
        Full analysis of a betting opportunity, incorporating qualitative score.
        """
        validation_result = self.validate_bet(match_data, live_data, qualitative_score)
        
        is_approved = validation_result["approved"]
        messages = validation_result["messages"]
        final_stake = validation_result["kelly_stake"]
        odds = validation_result["odds"] # Odds used for calculation in validate_bet
        
        return {
            "approved": is_approved,
            "messages": messages,
            "recommended_stake": final_stake,
            "potential_return": final_stake * odds if is_approved else 0.0,
            "expected_profit": (final_stake * odds) - final_stake if is_approved else 0.0
        }
