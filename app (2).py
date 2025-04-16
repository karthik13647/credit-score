from flask import Flask, render_template, request
import sqlite3
import json
import requests

app = Flask(__name__)

# Define the target URL where the JSON data will be sent (Receiver’s endpoint)
TARGET_URL = "https://loan-eligible.onrender.com/"  # Adjust accordingly

# Initialize the SQLite database and create the table if it doesn't exist
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

# Home Page (form page)
@app.route('/')
def index():
    return render_template('form.html')

# Eligibility Checker and Storage
@app.route('/check', methods=['POST'])
def check_eligibility():
    # Retrieve data from the submitted form
    credit_score = int(request.form['credit_score'])
    monthly_income = float(request.form['monthly_income'])
    debt_payments = float(request.form['debt_payments'])
    loan_amount = float(request.form['loan_amount'])
    loan_term = int(request.form['loan_term'])
    employment_status = request.form['employment_status']
    loan_type = request.form['loan_type']
    down_payment = float(request.form.get('down_payment', 0))
    state = request.form['state']
    collateral = request.form['collateral']

    # Calculate Debt-to-Income ratio
    dti = (debt_payments / monthly_income) * 100

    # Evaluate eligibility and collect reasons
    eligibility = "Eligible"
    reasons = []

    if loan_type == "Personal Loan":
        if credit_score < 600:
            eligibility = "Not Eligible"
            reasons.append("Credit score is too low for a personal loan.")
        if dti > 45:
            eligibility = "Not Eligible"
            reasons.append("DTI ratio is too high for a personal loan.")
    
    elif loan_type == "Mortgage Loan":
        if credit_score < 500:
            eligibility = "Not Eligible"
            reasons.append("Credit score is too low for an FHA mortgage.")
        elif credit_score < 620:
            eligibility = "Conditional"
            reasons.append("Eligible for FHA but not conventional mortgage.")
        if dti > 43:
            eligibility = "Not Eligible"
            reasons.append("DTI ratio exceeds mortgage requirements.")
        if down_payment <= 0:
            eligibility = "Not Eligible"
            reasons.append("Down payment required for a mortgage.")

    elif loan_type == "Auto Loan":
        if credit_score < 660:
            eligibility = "Not Eligible"
            reasons.append("Credit score is too low for an auto loan.")
        if dti > 50:
            eligibility = "Not Eligible"
            reasons.append("DTI ratio is too high for an auto loan.")
        if collateral != "Yes":
            eligibility = "Not Eligible"
            reasons.append("Collateral (vehicle) required for an auto loan.")

    elif loan_type == "Business Loan":
        if credit_score < 680:
            eligibility = "Not Eligible"
            reasons.append("Credit score is too low for a business loan.")

    elif loan_type == "Credit Card":
        if credit_score < 600:
            eligibility = "Not Eligible"
            reasons.append("Credit score is too low for a credit card.")
        if dti > 40:
            eligibility = "Not Eligible"
            reasons.append("DTI ratio is too high for a credit card.")

    # Convert the reasons list into a string for storage (e.g., separated by semicolons)
    reasons_str = "; ".join(reasons)

    # Save the data and the result into the database
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''
        INSERT INTO loan_submissions (
            credit_score, monthly_income, debt_payments, loan_amount, loan_term,
            employment_status, loan_type, down_payment, state, collateral,
            eligibility, reasons
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (credit_score, monthly_income, debt_payments, loan_amount, loan_term,
          employment_status, loan_type, down_payment, state, collateral,
          eligibility, reasons_str))
    conn.commit()
    conn.close()

    # Create a JSON file using all current records in the database and send it to the target URL
    data = create_json_file()
    send_json_to_target(data)

    return render_template('result.html', eligibility=eligibility, reasons=reasons,
                           loan_type=loan_type, loan_amount=loan_amount)

def create_json_file():
    """Retrieve all records from the database, create JSON data, and write it to a file."""
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('SELECT * FROM loan_submissions')
    rows = c.fetchall()
    columns = [desc[0] for desc in c.description]  # Get column names
    data = [dict(zip(columns, row)) for row in rows]
    conn.close()

    # Write the JSON data to a file
    with open('data.json', 'w') as json_file:
        json.dump(data, json_file, indent=4)
    
    return data

def send_json_to_target(data):
    """Send the JSON data to the target URL via HTTP POST."""
    try:
        response = requests.post(TARGET_URL, json=data)
        print(f"Sent JSON data to {TARGET_URL}. Response: {response.status_code}, {response.text}")
    except Exception as e:
        print(f"Error sending JSON data: {e}")

if __name__ == "__main__":
    app.run(debug=True,port=5001)
