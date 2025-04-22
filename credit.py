from flask import Flask, jsonify, render_template, request
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import threading
import time
import json
import uuid
import random
import requests
import os

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test_responses.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Database Model
class TestResponse(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    offer_id = db.Column(db.String(36), nullable=False)
    test_id = db.Column(db.String(36), nullable=False)
    response_number = db.Column(db.Integer, nullable=False)
    response_data = db.Column(db.Text, nullable=False)
    postback_url = db.Column(db.String(255), nullable=True)
    postback_status = db.Column(db.String(50), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<TestResponse {self.id} for offer {self.offer_id}>'

# In-memory storage of active tests
active_tests = {}

# Function to create a JSON data file with offer_id
def create_json_file(path, offer_id):
    data = {
        "offer_id": offer_id,
        "timestamp": datetime.utcnow().isoformat(),
        "tracking_id": str(uuid.uuid4()),
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "ip_address": "192.168.1.1"
    }
    
    with open(path, 'w') as f:
        json.dump(data, f)
    
    return data

# Function to send the JSON payload to a URL
def send_json_file_payload(file_path, url):
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        response = requests.post(url, json=data)
        return {
            "url": url,
            "status_code": response.status_code,
            "response": response.text if len(response.text) < 100 else response.text[:100] + "..."
        }
    except Exception as e:
        return {
            "url": url,
            "status": "error",
            "error": str(e)
        }

# Generate mock credit score response
def generate_mock_response(offer_id):
    score = random.randint(300, 850)
    risk_level = "low" if score > 700 else "medium" if score > 600 else "high"
    return {
        "offer_id": offer_id,
        "credit_score": score,
        "risk_level": risk_level,
        "decision": "approved" if score > 650 else "review" if score > 550 else "denied",
        "timestamp": datetime.utcnow().isoformat()
    }

def run_test_sequence(test_id, offer_id):
    """Run a test sequence that sends 10 responses, one every 20 minutes"""
    print(f"Starting test sequence for offer {offer_id} with test ID {test_id}")
    
    # Base URLs for postbacks
    base_urls = [
        "https://surveytitans.com/postback/7b7662e8159314ef0bdb32bf038bba29?",
        "https://kingopinions.com/postback/d90a817d5474da1feb49ec55c69f6bbf?",
        "https://surveytitans.com/postback/6ccfb58eb8c47a7a54f4ca8a9bbcabcc?",
        "https://surveytitans.com/postback/db2321a6b97f71653fd07f2ac70af751?"
    ]
    payout_options = [100, 75, 35, 25, 75, 20, 30, 40, 50, 85]
    
    # Create a temporary directory for JSON files if it doesn't exist
    temp_dir = "temp_json_files"
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
    
    for i in range(10):
        if test_id not in active_tests:
            print(f"Test {test_id} was cancelled")
            break
            
        # Generate response
        response_data = generate_mock_response(offer_id)
        
        # Select a random base URL and payout
        base_url = random.choice(base_urls)
        payout = random.choice(payout_options)
        postback_url = f"{base_url}payout={payout/100.0:.2f}&offer_id={offer_id}"
        
        # Create and send JSON file
        data_file = f"{temp_dir}/data_{test_id}_{i+1}.json"
        create_json_file(path=data_file, offer_id=offer_id)
        
        # Send the payload
        postback_result = send_json_file_payload(data_file, postback_url)
        
        # Add postback information to response data
        response_data["postback"] = {
            "url": postback_url,
            "result": postback_result
        }
        
        # Save to database
        response = TestResponse(
            offer_id=offer_id,
            test_id=test_id,
            response_number=i+1,
            response_data=json.dumps(response_data),
            postback_url=postback_url,
            postback_status=str(postback_result.get("status_code", "error"))
        )
        
        with app.app_context():
            db.session.add(response)
            db.session.commit()
            print(f"Saved response {i+1} for test {test_id} with postback to {postback_url}")
        
        # Wait 20 minutes before next response
        # (Changed to 5 seconds for testing purposes - set to 1200 for production)
        if i < 9:  # Don't sleep after the last response
            time.sleep(5)  # 5 seconds for testing (1200 seconds = 20 minutes)
    
    # Clean up temporary files
    for i in range(10):
        data_file = f"{temp_dir}/data_{test_id}_{i+1}.json"
        if os.path.exists(data_file):
            os.remove(data_file)
    
    # Remove from active tests when complete
    if test_id in active_tests:
        del active_tests[test_id]
        print(f"Test {test_id} completed")

@app.route('/')
def index():
    return render_template('index1.html')

@app.route('/api/start-test', methods=['POST'])
def start_test():
    data = request.json
    offer_id = data.get('offer_id')
    
    if not offer_id:
        return jsonify({"error": "Offer ID is required"}), 400
    
    # Generate unique test ID
    test_id = str(uuid.uuid4())
    
    # Store test in active tests
    active_tests[test_id] = {
        "offer_id": offer_id,
        "start_time": datetime.utcnow().isoformat()
    }
    
    # Start test sequence in a separate thread
    test_thread = threading.Thread(
        target=run_test_sequence,
        args=(test_id, offer_id)
    )
    test_thread.daemon = True
    test_thread.start()
    
    return jsonify({
        "message": "Test started successfully",
        "test_id": test_id,
        "offer_id": offer_id,
        "expected_duration_minutes": 200
    })

@app.route('/api/cancel-test/<test_id>', methods=['POST'])
def cancel_test(test_id):
    if test_id in active_tests:
        del active_tests[test_id]
        return jsonify({"message": f"Test {test_id} cancelled successfully"})
    else:
        return jsonify({"error": "Test not found"}), 404

@app.route('/api/tests')
def list_tests():
    return jsonify(active_tests)

@app.route('/api/test-results/<offer_id>')
def test_results(offer_id):
    responses = TestResponse.query.filter_by(offer_id=offer_id).all()
    results = []
    
    for response in responses:
        results.append({
            "id": response.id,
            "test_id": response.test_id,
            "response_number": response.response_number,
            "data": json.loads(response.response_data),
            "postback_url": response.postback_url,
            "postback_status": response.postback_status,
            "timestamp": response.timestamp.isoformat()
        })
    
    return jsonify(results)

# Create the database tables
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)