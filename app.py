from flask import Flask, jsonify, request, send_file, render_template
from flask_cors import CORS
import anthropic
import os
import re
import json
from dotenv import load_dotenv
from loan_analyser import analyse_loan

# Load Environment Variables
load_dotenv()

app = Flask(__name__)
# Allow CORS for local dev. Update origins in production.
CORS(app, resources={r"/api/*": {"origins": "*"}})

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "service": "KhataShield API"})

from openai import OpenAI
import base64

def get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        return OpenAI(api_key=api_key)
    return None

from ocr_extractor import extract_from_file

@app.route('/api/extract-loan', methods=['POST'])
def extract_loan():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    result = extract_from_file(file)
    
    missing = [
        f for f, v in [
            ('Principal Amount', result.get('principal')),
            ('Repayment Amount', result.get('repayment_amount')),
            ('Loan Duration',    result.get('duration'))
        ] if not v
    ]
    
    return jsonify({
        'success':          True,
        'extracted':        result,
        'missing_fields':   missing,
        'needs_confirmation': True
    })

@app.route('/api/analyse-loan', methods=['POST'])
def analyse_loan_route():
    req = request.json
    try:
        principal = float(req.get('principal', 0))
        repayment = float(req.get('repayment_amount', 0)) or float(req.get('repayment', 0))
        duration = float(req.get('duration', 0))
        frequency = req.get('repayment_frequency', '') or req.get('frequency', 'daily')
        
        result = analyse_loan(principal, repayment, frequency, duration)
        
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/voice-to-text', methods=['POST'])
def voice_to_text():
    file = request.files.get('audio')
    client = get_openai_client()
    
    if client and file:
        try:
            # Whisper expects a filename with a supported extension
            file.filename = "audio.webm"
            transcript = client.audio.transcriptions.create(
                model="whisper-1", 
                file=file
            )
            return jsonify({"transcript": transcript.text})
        except Exception as e:
            print(f"OpenAI transcription failed: {e}")
            
    # Fallback
    return jsonify({"transcript": "Mock transcript: Principal 10000 rupees, daily repayment 500 rupees, 30 days"})

@app.route('/api/voice-output', methods=['POST'])
def voice_output():
    data = request.json
    text = data.get('text', '')
    language = data.get('language', 'english')
    
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if api_key and text:
        try:
            from elevenlabs.client import ElevenLabs
            client = ElevenLabs(api_key=api_key)
            audio = client.generate(text=text, voice="Rachel")
            
            from flask import send_file
            import io
            return send_file(
                io.BytesIO(audio),
                mimetype='audio/mpeg'
            )
        except Exception as e:
            print(f"ElevenLabs TTS failed: {e}")

    # Fallback expects text, returns audio stream or base64 audio
    return jsonify({"audio_url": None, "message": "Voice unavailable"})

@app.route('/api/generate-pdf', methods=['POST'])
def generate_pdf():
    data = request.json
    try:
        from weasyprint import HTML
        import io
        html_content = render_template('report_template.html', data=data)
        pdf_bytes = HTML(string=html_content).write_pdf()
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype='application/pdf',
            as_attachment=True,
            download_name='KhataShield-Report.pdf'
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/extract-loan-vision', methods=['POST'])
def extract_loan_vision():
    try:
        data         = request.get_json()
        image_base64 = data.get('image_base64')
        media_type   = data.get('media_type', 'image/jpeg')

        if not image_base64:
            return jsonify({'success': False, 'error': 'No image data provided'}), 400

        client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env automatically

        message = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=600,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type":       "base64",
                            "media_type": media_type,
                            "data":       image_base64,
                        },
                    },
                    {
                        "type": "text",
                        "text": """You are a loan document reader. The document may be handwritten or printed in English, Tamil, Hindi, or any Indian language.

Read every detail carefully and return ONLY this raw JSON with no markdown, no backticks, no explanation:

{"principal":0,"repayment_amount":0,"repayment_frequency":"daily","duration":0,"interest_rate":null,"penalty_clause":null,"lender_name":null,"borrower_name":null}

Rules:
- principal: loan/borrowed amount as plain integer. Remove Rs INR and commas. "20,000" -> 20000
- repayment_amount: amount paid per period as plain integer
- repayment_frequency: exactly "daily" or "weekly" or "monthly"
- duration: TOTAL days as integer. 10 weeks -> 70. 6 months -> 180. 30 days -> 30
- If a field is missing use null (0 for numbers means not found)
- Read handwriting carefully

Example: "Principal Amount: 20,000  Repayment Amount: 2000  Loan Duration: 10  Frequency: Weekly"
Returns: {"principal":20000,"repayment_amount":2000,"repayment_frequency":"weekly","duration":70,"interest_rate":null,"penalty_clause":null,"lender_name":null,"borrower_name":null}"""
                    }
                ],
            }]
        )

        raw   = message.content[0].text.strip()
        raw   = raw.replace('```json', '').replace('```', '').strip()
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if not match:
            raise ValueError('No JSON found in Claude response')

        extracted = json.loads(match.group())
        return jsonify({'success': True, 'extracted': extracted})

    except anthropic.AuthenticationError:
        return jsonify({'success': False, 'error': 'Invalid Anthropic API key — set ANTHROPIC_API_KEY in backend .env'}), 401
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, port=5000, host='0.0.0.0')
