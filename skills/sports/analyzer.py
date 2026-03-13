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

    def validate_bet(self, stake: float, probability: float, current_loss: float = 0.0) -> Tuple[bool, List[str], float]:
        """
        Validates a bet based on APEX rules.
        Returns: (is_approved, messages, adjusted_stake)
        """
        messages = []
        is_approved = True
        adjusted_stake = stake

        # Rule 1: Stop-Loss (12%)
        if current_loss >= self.stop_loss_limit:
            return False, ["❌ STOP-LOSS DIÁRIO ATINGIDO (12%). Operações suspensas!"], 0.0

        # Rule 2: Minimum Probability (40%)
        if probability < self.min_probability:
            return False, [f"❌ Probabilidade muito baixa ({probability*100:.1f}% < 40%)"], 0.0

        # Rule 3: Max Stake (5%)
        if stake > self.max_stake_limit:
            messages.append(f"⚠️ Stake ajustado: R${stake:.2f} → R${self.max_stake_limit:.2f} (Limite 5%)")
            adjusted_stake = self.max_stake_limit

        if is_approved:
            messages.append("✅ Aprovado pela validação APEX")

        return is_approved, messages, adjusted_stake

    def analyze_opportunity(self, probability: float, odds: float, current_loss: float = 0.0) -> Dict:
        """
        Full analysis of a betting opportunity.
        """
        raw_stake = self.calculate_kelly_stake(probability, odds)
        is_approved, messages, final_stake = self.validate_bet(raw_stake, probability, current_loss)
        
        return {
            "approved": is_approved,
            "messages": messages,
            "recommended_stake": final_stake,
            "potential_return": final_stake * odds if is_approved else 0.0,
            "expected_profit": (final_stake * odds) - final_stake if is_approved else 0.0
        }
