import math

def analyse_loan(principal, repayment_amount, frequency, duration_input):
    # Ensure inputs are numbers
    principal = float(principal) if principal else 0
    repayment_amount = float(repayment_amount) if repayment_amount else 0
    duration_input = float(duration_input) if duration_input else 0

    # Normalise duration to days
    if frequency == 'daily':
        duration_days = duration_input
    elif frequency == 'weekly':
        duration_days = duration_input * 7
    elif frequency == 'monthly':
        duration_days = duration_input * 30
    else:
        duration_days = duration_input

    # Number of repayment periods
    if frequency == 'daily':
        periods = duration_days
    elif frequency == 'weekly':
        periods = math.ceil(duration_days / 7)
    elif frequency == 'monthly':
        periods = math.ceil(duration_days / 30)
    else:
        periods = duration_days

    total_repayment = repayment_amount * periods
    total_interest = total_repayment - principal
    hidden_charges = total_interest

    # APR = (interest / principal) * (365 / durationDays) * 100
    apr = 0
    if principal > 0 and duration_days > 0:
        apr = round(((total_interest / principal) * (365 / duration_days) * 100), 1)

    # Risk score
    if apr <= 24:
        risk_score = round(apr * 0.8)
        risk_category = 'Safe'
    elif apr <= 48:
        risk_score = round(20 + (apr - 24) * 1.2)
        risk_category = 'Risky'
    elif apr <= 100:
        risk_score = round(49 + (apr - 48) * 0.6)
        risk_category = 'Dangerous'
    else:
        risk_score = min(100, round(80 + apr * 0.05))
        risk_category = 'Dangerous'

    # Legal flags
    legal_flags = []
    if apr > 36:
        legal_flags.append({'severity': 'critical', 'text': f'APR of {apr}% far exceeds RBI fair lending guideline of 36%'})
    if total_interest > principal:
        legal_flags.append({'severity': 'critical', 'text': f'You are paying ₹{total_interest:,} extra — more than your original principal'})
    if frequency == 'daily':
        legal_flags.append({'severity': 'warning', 'text': 'Daily repayment schedule increases risk of compounding penalties'})
    if duration_days < 30:
        legal_flags.append({'severity': 'warning', 'text': 'Very short loan duration increases effective APR dramatically'})

    # Delay penalty
    daily_penalty_rate = 0.02 # 2% per day of daily repayment
    penalty_per_day = repayment_amount * daily_penalty_rate

    # Debt prediction at current rate
    if frequency == 'monthly':
        monthly_repayment = repayment_amount
    elif frequency == 'weekly':
        monthly_repayment = repayment_amount * 4
    else:
        monthly_repayment = repayment_amount * 30
        
    projected_months = math.ceil(total_repayment / monthly_repayment) if monthly_repayment > 0 else 0

    return {
        'principal': principal,
        'repaymentAmount': repayment_amount,
        'frequency': frequency,
        'durationDays': duration_days,
        'totalRepayment': round(total_repayment, 2),
        'totalInterest': round(total_interest, 2),
        'hiddenCharges': round(hidden_charges, 2),
        'apr': apr,
        'riskScore': risk_score,
        'riskCategory': risk_category,
        'legalFlags': legal_flags,
        'penaltyPerDay': round(penalty_per_day, 2),
        'projectedMonths': projected_months,
        'monthlyRepayment': round(monthly_repayment, 2)
    }
