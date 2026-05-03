import base64, json, re
import openai

client = openai.OpenAI()  # uses OPENAI_API_KEY from env

def extract_from_file(file):
    file_bytes = file.read()
    base64_data = base64.b64encode(file_bytes).decode('utf-8')
    mime = file.content_type if hasattr(file, 'content_type') else 'image/jpeg'
    
    # Step 1: Use GPT-4o Vision with a very explicit extraction prompt
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime};base64,{base64_data}",
                                "detail": "high"
                            }
                        },
                        {
                            "type": "text",
                            "text": """Read this loan document image very carefully. It may be handwritten or printed.

Extract these exact fields and return ONLY a JSON object. No markdown, no explanation, no backticks. Just raw JSON.

{
  "principal": <integer, e.g. 20000>,
  "repayment_amount": <integer, e.g. 2000>,
  "repayment_frequency": <"daily" or "weekly" or "monthly">,
  "duration": <integer number of weeks or days or months as written>,
  "duration_unit": <"days" or "weeks" or "months">,
  "interest_rate": <number or null>,
  "penalty_clause": <string or null>,
  "lender_name": <string or null>,
  "borrower_name": <string or null>
}

Important rules:
- Remove all currency symbols (₹, Rs, INR) and commas from numbers
- 20,000 becomes 20000
- If you see "Weekly" or "weekly" set repayment_frequency to "weekly"
- If you see "Daily" or "daily" set repayment_frequency to "daily"  
- If you see "Monthly" or "monthly" set repayment_frequency to "monthly"
- Duration: keep it as the raw number written (10 weeks = duration 10, duration_unit weeks)
- If a field is not visible, use null
- Read handwriting carefully — ₹ symbol may look like a crossed 'र' or 'R'"""
                        }
                    ]
                }
            ],
            max_tokens=400
        )
        
        raw = response.choices[0].message.content.strip()
        raw = raw.replace('```json','').replace('```','').strip()
        result = json.loads(raw)
        
        # Normalise duration to days
        result = normalise_duration(result)
        return result
        
    except Exception as e:
        # Step 2: Tesseract OCR fallback
        return tesseract_fallback(file_bytes, str(e))


def normalise_duration(data):
    """Convert duration to days based on duration_unit"""
    duration = data.get('duration')
    unit = (data.get('duration_unit') or '').lower()
    freq = (data.get('repayment_frequency') or 'daily').lower()
    
    if duration:
        if unit == 'weeks' or freq == 'weekly':
            data['duration_days'] = duration * 7
        elif unit == 'months' or freq == 'monthly':
            data['duration_days'] = duration * 30
        else:
            data['duration_days'] = duration
    
    data['duration'] = data.get('duration_days', duration)
    return data


def tesseract_fallback(file_bytes, error_msg):
    """Use pytesseract if Vision API fails"""
    try:
        import pytesseract
        from PIL import Image
        import io
        
        img = Image.open(io.BytesIO(file_bytes))
        # Enhance image for better OCR
        img = img.convert('L')  # grayscale
        text = pytesseract.image_to_string(img, config='--psm 6')
        return parse_text_to_loan(text)
    except:
        return {
            'principal': None, 'repayment_amount': None,
            'repayment_frequency': 'daily', 'duration': None,
            'interest_rate': None, 'penalty_clause': None,
            'lender_name': None, 'borrower_name': None,
            '_error': error_msg
        }


def parse_text_to_loan(text):
    """Robust regex parser for any loan text"""
    t = text.lower()
    
    def extract_amount(keywords, txt):
        for kw in keywords:
            # Match keyword followed by optional symbols then number
            pattern = rf'{kw}[\s:₹rs.]*(\d[\d,]*)'
            m = re.search(pattern, txt, re.I)
            if m:
                return int(m.group(1).replace(',',''))
        return None
    
    principal = extract_amount(
        ['principal amount', 'principal', 'loan amount', 'amount borrowed', 'borrowed'], t
    )
    repayment = extract_amount(
        ['repayment amount', 'repayment', 'instalment', 'emi', 'pay back', 'payment'], t
    )
    
    # Duration — look for number near duration/weeks/days/months
    dur_match = re.search(
        r'(?:loan\s*duration|duration|tenure|period)[\s:]*(\d+)\s*(days?|weeks?|months?)?',
        text, re.I
    )
    duration_num  = int(dur_match.group(1)) if dur_match else None
    duration_unit = dur_match.group(2).lower() if dur_match and dur_match.group(2) else 'days'
    
    # Frequency
    if re.search(r'\bweek(ly)?\b', t): freq = 'weekly'
    elif re.search(r'\bmonth(ly)?\b', t): freq = 'monthly'
    else: freq = 'daily'
    
    # Normalise duration to days
    if duration_num:
        if 'week' in duration_unit or freq == 'weekly':
            duration_days = duration_num * 7
        elif 'month' in duration_unit or freq == 'monthly':
            duration_days = duration_num * 30
        else:
            duration_days = duration_num
    else:
        duration_days = None
    
    return {
        'principal':            principal,
        'repayment_amount':     repayment,
        'repayment_frequency':  freq,
        'duration':             duration_days,
        'interest_rate':        None,
        'penalty_clause':       None,
        'lender_name':          None,
        'borrower_name':        None
    }
