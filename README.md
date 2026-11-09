# Food Donation Management System

## Requirements
- Python 3.10 or newer
- VS Code (recommended)

## Run on Windows (PowerShell)
1. Extract this ZIP and open the folder in VS Code.
2. Open the terminal in this folder.
3. Create a virtual environment (recommended):
   `python -m venv venv`
4. Activate it:
   `venv\Scripts\Activate.ps1`
5. Install packages:
   `pip install -r requirements.txt`
6. Start the app:
   `python app.py`
7. Open: http://127.0.0.1:5000

## Demo admin
- Email: admin@foodshare.com
- Password: Admin123!

Register separate donor and receiver accounts to test the workflow.

## Important
This is an educational MVP. Before real-world deployment:
- Change `app.secret_key` to a long random secret stored in an environment variable.
- Turn off Flask debug mode.
- Add CSRF protection, rate limiting, email verification, audit logging and secure deployment.
- Verify food safety, donor identity, receiver identity and local food-donation rules.
- The current MVP does not upload food images or send SMS/email notifications.
