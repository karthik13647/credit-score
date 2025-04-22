from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from datetime import datetime
import os
import uuid
import json
import threading
import time
import secrets
import random
import requests

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test_cycles.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024  # Increased to 32MB max upload

# Ensure upload directories exist
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'image'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'audio'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'video'), exist_ok=True)

db = SQLAlchemy(app)

# Models
class TestCycle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    offer_id = db.Column(db.String(100), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    is_complete = db.Column(db.Boolean, default=False)
    response_data = db.Column(db.Text, nullable=True)  # Added this field# Added this field
    responses = db.relationship('TestResponse', backref='test_cycle', lazy=True)
    media_files = db.relationship('MediaFile', backref='test_cycle', lazy=True)
    
class TestResponse(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    test_cycle_id = db.Column(db.Integer, db.ForeignKey('test_cycle.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    run_number = db.Column(db.Integer, nullable=False)
    response_url = db.Column(db.String(500), nullable=True)  # Changed to nullable=True
    payout = db.Column(db.Float, nullable=False)
    response_code = db.Column(db.Integer, nullable=True)
    
class MediaFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    test_cycle_id = db.Column(db.Integer, db.ForeignKey('test_cycle.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    file_type = db.Column(db.String(50), nullable=False)  # 'image', 'audio', 'video'
    upload_timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
class PostbackURL(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    offer_id = db.Column(db.String(100), nullable=False)
    token = db.Column(db.String(100), nullable=False, unique=True)
    url = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
# Create database tables
with app.app_context():
    db.create_all()

# Helper functions
def generate_token():
    return secrets.token_urlsafe(32)

def allowed_file(filename, types):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in types
    
ALLOWED_EXTENSIONS = {
    'image': ['png', 'jpg', 'jpeg', 'gif'],
    'audio': ['mp3', 'wav', 'ogg'],
    'video': ['mp4', 'webm', 'mov']
}

def send_json_file_payload(data, url):
    try:
        response = requests.post(url, json=data)
        return response.status_code
    except:
        return None

# Test cycle background process
def run_test_cycle(offer_id, cycle_id, data_file=None):
    with app.app_context():
        test_cycle = TestCycle.query.get(cycle_id)
        if not test_cycle:
            return
        
        # Base postback URLs
        base_urls = [
            "https://surveytitans.com/postback/7b7662e8159314ef0bdb32bf038bba29?",
            "https://surveytitans.com/postback/db2321a6b97f71653fd07f2ac70af751?"
        ]
        
        # Payout options
        payout_options = [100, 75, 35, 25, 75, 20, 30, 40, 50, 85]
        
        # Run for 10 iterations with 5-second intervals
        for run_number in range(1, 11):
            for base in base_urls:
                # Pick a random payout
                pts = random.choice(payout_options)
                payout = pts / 100.0
                url = f"{base}payout={payout:.2f}"
                
                # Prepare payload data
                if data_file:
                    payload = data_file
                else:
                    payload = {
                        "offer_id": offer_id,
                        "run_number": run_number,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                
                # Send the request
                status_code = send_json_file_payload(payload, url)
                
                # Store the response
                test_response = TestResponse(
                    test_cycle_id=cycle_id,
                    run_number=run_number,
                    response_url=url,
                    payout=payout,
                    response_code=status_code
                )
                db.session.add(test_response)
                db.session.commit()
            
            # Wait 5 seconds before next iteration (except after the last one)
            if run_number < 10:
                time.sleep(20)
        
        # Mark test cycle as complete
        test_cycle.is_complete = True
        db.session.commit()

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/uploads/<type>/<filename>')
def uploaded_media(type, filename):
    return send_from_directory(os.path.join(app.config['UPLOAD_FOLDER'], type), filename)

@app.route('/api/start-test-cycle', methods=['POST'])
def start_test_cycle():
    # Get form data
    offer_id = request.form.get('offer_id')
    
    if not offer_id:
        return jsonify({"error": "Offer ID is required"}), 400
    
    # Get optional JSON data
    json_data = None
    if 'json_data' in request.form and request.form['json_data'].strip():
        try:
            json_data = json.loads(request.form['json_data'])
            json_data_str = json.dumps(json_data)  # Convert to string for storage
        except json.JSONDecodeError:
            return jsonify({"error": "Invalid JSON data format"}), 400
    else:
        json_data_str = "{}"  # Default to empty JSON object
    
    # Create a new test cycle
    test_cycle = TestCycle(
        offer_id=offer_id,
        response_data=json_data_str  # Store JSON as string
    )
    db.session.add(test_cycle)
    db.session.commit()
    
    # Rest of the function remains the same...
    # Process uploaded media file
    if 'media_file' in request.files:
        file = request.files['media_file']
        
        if file and file.filename != '':
            # Determine file type
            file_extension = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
            
            file_type = None
            if file_extension in ALLOWED_EXTENSIONS['image']:
                file_type = 'image'
            elif file_extension in ALLOWED_EXTENSIONS['audio']:
                file_type = 'audio'
            elif file_extension in ALLOWED_EXTENSIONS['video']:
                file_type = 'video'
                
            if file_type:
                filename = secure_filename(file.filename)
                unique_filename = f"{uuid.uuid4()}_{filename}"
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], file_type, unique_filename)
                file.save(file_path)
                
                # Store file info in database
                media_file = MediaFile(
                    test_cycle_id=test_cycle.id,
                    filename=unique_filename,
                    file_type=file_type
                )
                db.session.add(media_file)
                db.session.commit()
    
    # Start background thread to run the test cycle
    thread = threading.Thread(target=run_test_cycle, args=(offer_id, test_cycle.id, json_data))
    thread.daemon = True
    thread.start()
    
    return jsonify({
        "message": "Test cycle started",
        "test_cycle_id": test_cycle.id
    })

@app.route('/api/test-cycles/<offer_id>')
def get_test_cycles(offer_id):
    test_cycles = TestCycle.query.filter_by(offer_id=offer_id).all()
    result = []
    
    for cycle in test_cycles:
        try:
            responses = TestResponse.query.filter_by(test_cycle_id=cycle.id).all()
            media_files = MediaFile.query.filter_by(test_cycle_id=cycle.id).all()
            
            response_data = [{
                "run_number": resp.run_number,
                "timestamp": resp.timestamp.isoformat(),
                "url": resp.response_url,
                "payout": resp.payout,
                "response_code": resp.response_code
            } for resp in responses]
            
            media_data = [{
                "id": media.id,
                "type": media.file_type,
                "filename": media.filename,
                "timestamp": media.upload_timestamp.isoformat()
            } for media in media_files]
            
            result.append({
                "id": cycle.id,
                "offer_id": cycle.offer_id,
                "timestamp": cycle.timestamp.isoformat(),
                "is_complete": cycle.is_complete,
                "responses": response_data,
                "media": media_data
            })
        except Exception as e:
            # Handle any database errors
            print(f"Error retrieving test cycle {cycle.id}: {str(e)}")
            continue
    
    return jsonify(result)

@app.route('/api/generate-postback', methods=['POST'])
def generate_postback():
    data = request.json
    offer_id = data.get('offer_id')
    callback_url = data.get('callback_url')
    
    if not offer_id or not callback_url:
        return jsonify({"error": "Offer ID and callback URL are required"}), 400
    
    # Check if a postback URL already exists for this offer
    existing = PostbackURL.query.filter_by(offer_id=offer_id).first()
    if existing:
        # Update existing
        existing.url = callback_url
        existing.token = generate_token()
        db.session.commit()
        postback = existing
    else:
        # Create new
        postback = PostbackURL(
            offer_id=offer_id,
            token=generate_token(),
            url=callback_url
        )
        db.session.add(postback)
        db.session.commit()
    
    # Generate the full postback URL with parameters
    postback_url = f"{callback_url}?offer_id={offer_id}&token={postback.token}"
    
    return jsonify({
        "message": "Postback URL generated",
        "postback_id": postback.id,
        "offer_id": offer_id,
        "token": postback.token,
        "postback_url": postback_url
    })

if __name__ == '__main__':
    app.run(debug=True)