import os
import msal
from dotenv import load_dotenv
import requests
import sqlite3
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime, timezone

# Load environment variables
load_dotenv()

# Get credentials from .env
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
TENANT_ID = os.getenv("TENANT_ID")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
REDIRECT_URI = "http://localhost:8000/getAToken"  # Ensure this matches the registered redirect URI

access_token = None  # Initialize access_token

class OAuthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if "/getAToken" in self.path:
            code = self.path.split("code=")[1].split("&")[0]
            token = get_token_from_code(code)
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"Authorization successful. You can close this window.")
            global access_token
            access_token = token["access_token"]

def create_authorization_url():
    """Create the authorization URL for Outlook authentication."""
    authority = "https://login.microsoftonline.com/consumers"
    scopes = ["https://graph.microsoft.com/.default"]
    auth_url = f"{authority}/oauth2/v2.0/authorize?client_id={CLIENT_ID}&response_type=code&redirect_uri={REDIRECT_URI}&response_mode=query&scope={' '.join(scopes)}&state=12345"
    return auth_url

def get_token_from_code(code):
    """Exchange the authorization code for an access token."""
    authority = "https://login.microsoftonline.com/consumers"
    token_url = f"{authority}/oauth2/v2.0/token"
    token_data = {
        "client_id": CLIENT_ID,
        "scope": "https://graph.microsoft.com/.default",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
        "client_secret": CLIENT_SECRET,
    }
    token_r = requests.post(token_url, data=token_data)
    token = token_r.json()
    return token

def get_outlook_access_token():
    """Authenticate and get access token from Microsoft Graph API."""
    global access_token
    if access_token:
        return access_token

    auth_url = create_authorization_url()
    webbrowser.open(auth_url)

    server = HTTPServer(("localhost", 8000), OAuthHandler)
    server.handle_request()

    return access_token

def test_access_token():
    """Test the access token by querying Microsoft Graph API."""
    try:
        access_token = get_outlook_access_token()
        test_url = "https://graph.microsoft.com/v1.0/users"
        headers = {"Authorization": f"Bearer {access_token}"}
        response = requests.get(test_url, headers=headers)

        if response.status_code == 200:
            print("Access token test successful. User data retrieved.")
        else:
            print(f"Access token test failed with status {response.status_code}: {response.json()}")
    except Exception as e:
        print(f"Error testing access token: {e}")

def send_email_via_outlook(to, subject, body, cc=None, bcc=None):
    """Send an email via Outlook using Microsoft Graph API and log the details."""
    try:
        access_token = get_outlook_access_token()

        url = f"https://graph.microsoft.com/v1.0/users/{SENDER_EMAIL}/sendMail"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        email_data = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "HTML",
                    "content": body
                },
                "toRecipients": [{"emailAddress": {"address": addr.strip()}} for addr in to.split(",")],
                "ccRecipients": [{"emailAddress": {"address": addr.strip()}} for addr in cc.split(",")] if cc else [],
                "bccRecipients": [{"emailAddress": {"address": addr.strip()}} for addr in bcc.split(",")] if bcc else []
            },
            "saveToSentItems": "true"
        }

        response = requests.post(url, headers=headers, json=email_data)

        # Log email details to the database
        conn = sqlite3.connect('mass_mail.db')
        cursor = conn.cursor()

        if response.status_code == 202:
            # Log success
            message_id = response.headers.get('Message-Id', None)  # Optional
            cursor.execute("""
                INSERT INTO sent_emails (sender, recipient, subject, message_id, status, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                SENDER_EMAIL,
                to,
                subject,
                message_id,
                "inbox",
                datetime.now(timezone.utc)
            ))
            conn.commit()
            conn.close()
            print("Email sent successfully.")
            return {"status": "success", "message": "Email sent successfully."}
        else:
            # Log failure
            error_details = response.json()
            cursor.execute("""
                INSERT INTO sent_emails (sender, recipient, subject, message_id, status, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                SENDER_EMAIL,
                to,
                subject,
                None,
                "not delivered",
                datetime.now(timezone.utc)
            ))
            conn.commit()
            conn.close()
            print(f"Failed to send email: {response.status_code} - {error_details}")
            return {
                "status": "failure",
                "error_code": response.status_code,
                "error_message": error_details,
            }
    except Exception as e:
        print(f"An error occurred while sending email via Outlook: {e}")
        raise


