import os
import time
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
import streamlit as st
import pickle
import base64
import sqlite3
from google.auth.transport.requests import Request
from datetime import datetime, timezone

load_dotenv()
# Connect to your SQLite database (mass_mail.db)
conn = sqlite3.connect('mass_mail.db', check_same_thread=False)
cursor = conn.cursor()

# SQL query to create the sent_emails table
cursor.execute("""
    CREATE TABLE IF NOT EXISTS sent_emails (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender TEXT,
        recipient TEXT,
        subject TEXT,
        message_id TEXT,
        status TEXT,  -- inbox, spam, not delivered
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")

# Commit changes and close the connection
conn.commit()

# Gmail API Authentication Flow for Desktop Apps
def create_gmail_service():
    SCOPES = ['https://www.googleapis.com/auth/gmail.send', 'https://www.googleapis.com/auth/gmail.readonly']
    creds = None

    # Load credentials from the token.pickle file
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    else:
        print("Token file not found.")

    # If no credentials are available or they are expired, request the user to log in again
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())  # Refresh the token if expired
        else:
            flow = Flow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            flow.redirect_uri = st.experimental_get_query_params().get("redirect_uri", [""])[0]
            auth_url, _ = flow.authorization_url(prompt="consent")
            
            st.write("Please authenticate with Gmail:")
            st.markdown(f"[Click here to authenticate]({auth_url})")

            code = st.text_input("Paste the authorization code here:")
            if code:
                flow.fetch_token(code=code)
                creds = flow.credentials

        # Save the credentials for the next run
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    service = build('gmail', 'v1', credentials=creds)
    user_profile = service.users().getProfile(userId='me').execute()
    sender_email = user_profile.get('emailAddress')
    print(f"Authenticated sender email: {sender_email}")

    return service, sender_email

def get_email_status(service, message_id):
    try:
        message = service.users().messages().get(userId="me", id=message_id, format="metadata").execute()
        print(f"Retrieved message with ID {message_id}: {message}")  # Added for debugging
        # Wait for a brief moment for the labels to be updated (to ensure status is accurate)
        time.sleep(2)  # Sleep for 2 seconds to allow Gmail to update the message status

        labels = message.get('labelIds', [])
        print(f"Labels for message ID {message_id}: {labels}")  # Added for debugging

        if 'INBOX' in labels:
            return "inbox"
        elif 'SPAM' in labels:
            return "spam"
        elif 'SENT' in labels:
            return "Sent"
        elif 'TRASH' in labels:
            return "Trash"
        else:
            return "not delivered"
    except HttpError as error:
        print(f"Error fetching message status for {message_id}: {error}")
        return "unknown"

def send_email_API(subject, body, to_email, cc_email, bcc_email, reply_to_email, signature):
    try:
        service, sender_email = create_gmail_service()
        
        # Ensure recipients are lists
        to_recipients = [email.strip() for email in to_email.split(",") if email.strip()]
        cc_recipients = [email.strip() for email in cc_email.split(",") if email.strip()]
        bcc_recipients = [email.strip() for email in bcc_email.split(",") if email.strip()]
        all_recipients = to_recipients + cc_recipients + bcc_recipients
        
        if not all_recipients:
            st.error("No valid recipients found. Please check your input.")
            return
        
        # Set up the MIME message
        msg = MIMEMultipart()
        msg['Subject'] = subject
        if reply_to_email:
            msg.add_header('Reply-To', reply_to_email)
        msg.attach(MIMEText(body, 'plain'))
        
        # Add signature
        if signature:
            msg.attach(MIMEText(f"\n\n--\n{signature}", 'plain'))

        # Send individual emails to each recipient and log unique message ID
        for recipient in all_recipients:
            msg['To'] = recipient
            message = MIMEText(body)
            message['to'] = recipient
            message['subject'] = subject
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

            sent_message = service.users().messages().send(userId="me", body={'raw': raw}).execute()
            message_id = sent_message['id']
            print(f"Unique Message ID for {recipient}: {message_id}")
            
            time.sleep(2)
            
            # Get the status for the email
            status = get_email_status(service, message_id)

            # Store email data in the database with unique message_id for each recipient
            cursor.execute("""
                INSERT INTO sent_emails (sender, recipient, subject, message_id, status, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (sender_email, recipient, subject, message_id, status, datetime.now(timezone.utc)))
            conn.commit()

        st.success(f"Emails successfully sent to {len(all_recipients)} recipients.")

    except Exception as error:
        st.error(f"An error occurred: {error}")

def update_statuses():
    conn = sqlite3.connect("mass_mail.db")
    cursor = conn.cursor()

    # Fetch message IDs and recipients with unknown status
    cursor.execute("SELECT message_id, recipient FROM sent_emails WHERE status IS NULL OR status = 'unknown'")
    rows = cursor.fetchall()

    # Log the IDs and recipients being processed
    print(f"Message IDs and recipients to update: {[(row[0], row[1]) for row in rows]}")

    service, _ = create_gmail_service()  # Create Gmail API service

    for message_id, recipient in rows:
        try:
            # Get the status of the email for this message ID
            status = get_email_status(service, message_id)
            print(f"Updating message ID {message_id} with status: {status} for recipient: {recipient}")

            # Update the status for the specific recipient
            cursor.execute("""
                UPDATE sent_emails
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE message_id = ? AND recipient = ?
            """, (status, message_id, recipient))

        except Exception as e:
            print(f"Error updating status for {recipient}: {e}")

    conn.commit()
    conn.close()
