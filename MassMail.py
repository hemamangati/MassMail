import streamlit as st
import os
import sqlite3
import smtplib
import threading
import schedule
from dotenv import load_dotenv
import time as sleep_time
from datetime import datetime, time, timezone
from email.mime.multipart import MIMEMultipart
from email_statistics import email_stats, start_periodic_task
from outlook_api import *
from gmail_api import *
from templates import *
from email.mime.text import MIMEText
import pandas as pd


# Load environment variables from .env file
load_dotenv()


# Initialize SQLite Database
conn = sqlite3.connect("mass_mail.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    is_superuser INTEGER DEFAULT 0
)
""")
conn.commit()

# Create email_activity table to track email counts
cursor.execute("""
CREATE TABLE IF NOT EXISTS email_activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    email_count INTEGER NOT NULL DEFAULT 0,
    date DATE NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id)
)
""")
conn.commit()

cursor.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            to_email TEXT,
            cc_email TEXT,
            bcc_email TEXT,
            subject TEXT,
            body TEXT,
            signature TEXT,
            schedule_time TIMESTAMP,
            status TEXT DEFAULT 'Pending'
        )
    """)
conn.commit()



# Page Configuration
#st.set_page_config(page_title="Mass Mail", layout="centered")

# Initialize session state for navigation
if "page" not in st.session_state:
    st.session_state.page = "login"
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
#if "is_superuser" not in st.session_state:
   # st.session_state.is_superuser = False

# Function to navigate between pages
def switch_page(page_name):
    st.session_state.page = page_name

def get_template_by_id(template_id):
    conn = sqlite3.connect('mass_mail.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM templates WHERE template_id=?', (template_id,))
    template = cursor.fetchone()
    conn.close()
    return template

# Updated Function to Send Email Using SMTP and track email count
def send_email_smtp(subject, body, to_email, cc_email, bcc_email, reply_to_email, signature):
    from_email = os.getenv('EMAIL_USER')  # SMTP email
    from_password = os.getenv('EMAIL_PASS')  # Email password

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
    msg['From'] = from_email
    msg['To'] = ", ".join(to_recipients)
    msg['CC'] = ", ".join(cc_recipients)
    msg['Subject'] = subject
    if reply_to_email:
        msg.add_header('Reply-To', reply_to_email)

    msg.attach(MIMEText(body, 'plain'))

    # Add signature
    if signature:
        msg.attach(MIMEText(f"\n\n--\n{signature}", 'plain'))

    # Get user ID from session state
    user_id = st.session_state.get('user_id', None)

    # Send email and update email count
    try:
        # Connect to the SMTP server and send the email
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()  # Secure the connection
        server.login(from_email, from_password)
        server.sendmail(from_email, all_recipients, msg.as_string())
        server.quit()

        # Log email activity (daily count)
        if user_id:
            today = pd.to_datetime("today").date()  # Get today's date
            cursor.execute("""
            SELECT email_count FROM email_activity WHERE user_id = ? AND date = ? 
            """, (user_id, today))
            result = cursor.fetchone()

            if result:
                new_count = result[0] + len(all_recipients)  # Increment email count by the number of recipients
                cursor.execute("""
                UPDATE email_activity SET email_count = ? WHERE user_id = ? AND date = ? 
                """, (new_count, user_id, today))
            else:
                cursor.execute("""
                INSERT INTO email_activity (user_id, email_count, date) VALUES (?, ?, ?)
                """, (user_id, len(all_recipients), today))

            conn.commit()

        st.success(f"Emails successfully sent to {len(all_recipients)} recipients.")

    except Exception as e:
        st.error(f"Error occurred while sending email: {e}")

# Function to logout the user
def logout():
    # Clear session state related to login and redirection
    st.session_state.logged_in = False
    st.session_state.is_superuser = False
    st.success("You have been logged out.Refresh to Login again")

    

def new_page():
    st.sidebar.title("Navigation")
    pages = ["Email Dashboard", "Email Stats"]
    selected_page = st.sidebar.radio("Go to", pages)
    if selected_page == "Email Dashboard":
        email_dashboard()
    elif selected_page == "Email Stats":
        email_stats()


# Email Dashboard Functionality
def email_dashboard():
    st.markdown("<h3 style='text-align: center;'>Email Dashboard</h3>", unsafe_allow_html=True)
    global send_method
    # Get user ID from session state
    user_id = st.session_state.get('user_id', None)

    if "email_input_method" not in st.session_state:
        st.session_state.email_input_method = "manual"

    # Buttons for selecting email input method
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Enter Emails Manually"):
            st.session_state.email_input_method = "manual"
    with col2:
        if st.button("Upload CSV"):
            st.session_state.email_input_method = "csv"
    st.write(f"**Selected Input Method**: {st.session_state.email_input_method}")

    # Form Elements for recipients
    to = ""
    if st.session_state.email_input_method == "manual":
        to = st.text_input("To", placeholder="Enter recipient email(s) separated by commas")
    elif st.session_state.email_input_method == "csv":
        uploaded_file = st.file_uploader("Upload CSV", type=["csv"])
        if uploaded_file:
            df = pd.read_csv(uploaded_file)
            if "Email" in df.columns:
                emails = df["Email"].dropna().tolist()
                to = ", ".join(emails)
                st.write(f"Loaded {len(emails)} emails from CSV.")
            else:
                st.error("CSV must contain a column named 'Email'")

    cc = st.text_input("CC", placeholder="Enter CC email(s) (optional)")
    bcc = st.text_input("BCC", placeholder="Enter BCC email(s) (optional)")
    reply_to = st.text_input("Reply To", placeholder="Enter reply-to email address (optional)")

    use_template = st.radio("Use Template?", ["Yes", "No"], index=1)

    subject = ""
    body = ""

    if use_template == "Yes":
        # Get templates
        templates = get_templates()
        
        # Check if templates exist
        if not templates:
            st.warning("No templates found. You can create a new template.")
        
            # Form for creating a new template
            with st.form("create_template_form"):
                template_name = st.text_input("Template Name")
                template_subject = st.text_input("Template Subject")
                template_body = st.text_area("Template Body")
                create_template_button = st.form_submit_button("Create Template")
                
                if create_template_button:
                    # Insert the new template into the database
                    conn = sqlite3.connect('mass_mail.db')
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO templates (template_name, subject, body, created_by)
                        VALUES (?, ?, ?, ?)
                    """, (template_name, template_subject, template_body, user_id))
                    conn.commit()
                    conn.close()
                    st.success("New template created successfully.")
                    st.rerun()  # Refresh the page to show the new template
        else:
            # If templates exist, display them in a dropdown
            selected_template_name = st.selectbox("Select Template", [template[1] for template in templates])
            
            # Use a try-except block to avoid StopIteration error
            try:
                selected_template_id = next(template[0] for template in templates if template[1] == selected_template_name)
            except StopIteration:
                selected_template_id = None  # No template selected, handle accordingly
            
            if selected_template_id:
                template = get_template_by_id(selected_template_id)
                if template:
                    subject = template[2]  # Subject
                    body = template[3]  # Body
    else:
        # Manual entry
        subject = st.text_input("Title", value=subject, placeholder="Enter email subject")
        body = st.text_area("Body", value=body, placeholder="Write your email content here...")

    signature = st.text_area("Signature", placeholder="Add your signature here...")

    send_method = st.selectbox("Send via", ["Gmail API", "SMTP", "outlook"])


    # Checkbox to schedule email for later
    schedule_later = st.checkbox("Schedule Email for Later?")
    schedule_datetime = None
    
    if schedule_later:
        schedule_date = st.date_input("Select Schedule Date", min_value=datetime.now().date())
       # Allow user to input a time manually
        schedule_time = st.time_input("select schedule time",value=None , help="Select the time for scheduling the email")

        # Combine selected date and time into a single datetime object
        schedule_datetime = datetime.combine(schedule_date, schedule_time)
        st.write(f"Scheduled Date and Time: {schedule_datetime}")

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("Send Email"):
            if send_method == "Gmail API":
                if to or cc or bcc:
                    send_email_API(subject, body, to, cc, bcc, reply_to, signature)
                else:
                    st.error("Please enter at least one recipient email.")
            elif send_method == "SMTP":
                if to or cc or bcc:
                    send_email_smtp(subject, body, to, cc, bcc, reply_to, signature)
                else:
                    st.error("Please enter at least one recipient email.")
            elif send_method == "outlook":
                if to or cc or bcc:
                    try:
                        full_body = body + "\n\n" + signature
                        # Send email via Outlook
                        result = send_email_via_outlook(to, subject, full_body, cc, bcc)
                        if result is None:
                            st.write("Please authorize the application to send emails via Outlook.")
                        elif result["status"] == "success":
                            st.success("Email sent successfully via Outlook.")
                        else:
                            st.error(f"Failed to send email via Outlook: {result['error_code']} - {result['error_message']}")
                    except Exception as e:
                        st.error(f"An error occurred while sending email via Outlook: {str(e)}")
                else:
                    st.error("Please enter at least one recipient email.")

        else:
            with col2:
                if st.button("Schedule Later"):
                    if to or cc or bcc:
                        if schedule_datetime and schedule_datetime > datetime.now():
                            try:
                                conn = sqlite3.connect('mass_mail.db')
                                cursor = conn.cursor()
                                cursor.execute("""
                                               INSERT INTO scheduled_emails 
                                               (user_id, to_email, cc_email, bcc_email, subject, body, signature, schedule_time)
                                               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                               """, (user_id, to, cc, bcc, subject, body, signature, schedule_datetime))
                                conn.commit()
                                conn.close()
                                st.success(f"Email scheduled for {schedule_datetime}.")
                            except sqlite3.Error as e:
                                st.error(f"Error scheduling email: {e}")
                        else:
                            st.error("Please select a valid date and time for scheduling.")
                    else:
                        st.error("Please enter at least one recipient email.")


        
    #if st.button("Email Status Board"):
        #st.session_state.page = "email_stats()"

    # Display a button for superusers to redirect to the superuser portal
    if st.session_state.is_superuser:
        st.markdown("<hr>", unsafe_allow_html=True)
        st.markdown("<h4>Superuser Options</h4>", unsafe_allow_html=True)
        if st.button("Go to Superuser Portal"):
            switch_page("super_user_portal")
            st.rerun()

    # Add the logout button
    if st.button("Logout"):
        logout()

# Fetch user data
def fetch_users():
    return pd.read_sql_query(
        "SELECT id, username, is_active FROM users WHERE is_superuser = 0", conn
    )

def update_user(user_id, new_username, new_password):
    try:
        cursor.execute(
            "UPDATE users SET username = ?, password = ? WHERE id = ?",
            (new_username, new_password, user_id),
        )
        conn.commit()
    except Exception as e:
        st.error(f"Error updating user: {e}")
        conn.rollback()

def delete_user(user_id):
    try:
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
    except Exception as e:
        st.error(f"Error deleting user: {e}")
        conn.rollback()

def update_user_status(user_id, new_status):
    try:
        cursor.execute(
            "UPDATE users SET is_active = ? WHERE id = ?", (new_status, user_id))
        conn.commit()
    except Exception as e:
        st.error(f"Error updating user status: {e}")
        conn.rollback()

def super_user_portal():
    if not st.session_state.logged_in or not st.session_state.is_superuser:
        st.error("You do not have access to this portal.")
        return
    
    st.header("Super User Portal")
    st.subheader("You can manage Users & Templates data")
    
    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown("Send Mails from Super user account: ")
    with col2:
        if st.button("Send Mails"):
            st.session_state.page = "new_page"
            st.rerun()
    
    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown("Manage Users & Templates")
    with col2:
        if st.button("Manage"):
            st.session_state.page = "template_management"
            st.rerun()

    # Display user details excluding superusers
    users_df = pd.read_sql_query(
        "SELECT id, username, password, is_active FROM users WHERE is_superuser = 0",
        conn
    )

    super_users_df = pd.read_sql_query(
        "SELECT id, username, password, is_active FROM users WHERE is_superuser = 1",
        conn
    )

    col1, col2 = st.columns([15, 10])
    with col1:
        # Display Non-Superuser Accounts
        st.subheader("Non-Superuser Accounts")
        if not users_df.empty:
            users_df['is_active'] = users_df['is_active'].map({1: 'Yes', 0: 'No'})
            st.dataframe(users_df)
        else:
            st.warning("No non-superuser accounts available for management.")

    with col2:
        # Display Superuser Accounts
        st.subheader("Superuser Accounts")
        if not super_users_df.empty:
            super_users_df['is_active'] = super_users_df['is_active'].map({1: 'Yes', 0: 'No'})
            st.dataframe(super_users_df)
        else:
            st.warning("No superuser accounts available.")

    # Retrieve inactive users
    inactive_users = pd.read_sql_query(
        "SELECT id, username FROM users WHERE is_active = 0 AND is_superuser = 0", conn
    )
    
    # Display email activity of users
    st.subheader("Email Activity (Daily)")
    email_activity_df = pd.read_sql_query(""" 
    SELECT u.username, ea.email_count, ea.date 
    FROM email_activity ea
    JOIN users u ON ea.user_id = u.id
    WHERE ea.date = ? 
    """, conn, params=(pd.to_datetime("today").date(),))

    if not email_activity_df.empty:
        st.dataframe(email_activity_df)
    else:
        st.warning("No email activity recorded for today.")

    # Manage Users (CRUD)
    st.subheader("Manage Users")
    
    if not users_df.empty:
        selected_user = st.selectbox("Select User to Manage", users_df['username'])
        user_id = users_df.loc[users_df['username'] == selected_user, "id"].values[0]
        action = st.radio("Select Action", ["Enable", "Disable", "Delete", "Modify"])
        
        if action == "Modify":
            new_username = st.text_input("New Username", selected_user)
            new_password = st.text_input("New Password", type="password")
            if st.button("Update User"):
                update_user(user_id, new_username, new_password)
                st.success(f"User {selected_user} updated successfully.")
                #st.rerun()
        
        elif action == "Delete":
            if st.button("Delete User"):
                delete_user(user_id)
                st.success(f"User {selected_user} deleted.")
                
        
        elif action in ["Enable", "Disable"]:
            new_status = 1 if action == "Enable" else 0
            if st.button(f"{action} User"):
                update_user_status(user_id, new_status)
                st.success(f"User {selected_user} status updated to {action}.")
                #st.rerun()
    else:
        st.warning("No users available for management.")

    # Logout button
    if st.button("Logout"):
        logout()


def process_scheduled_emails():
    conn = sqlite3.connect('mass_mail.db')
    cursor = conn.cursor()
    current_time = datetime.now(timezone.utc)  # Use UTC time for comparison

    # Fetch all scheduled emails due for sending
    cursor.execute("""
        SELECT * FROM scheduled_emails 
        WHERE schedule_time <= ? AND status = 'Pending'
    """, (current_time,))
    emails = cursor.fetchall()
    print(f"Processing emails at {datetime.now()}")

    for email in emails:
        email_id, user_id, to_email, cc_email, bcc_email, subject, body, signature, schedule_time, status = email
        try:
            # Send email via selected method
            if send_method == "Gmail API":
                send_email_API(subject, body, to_email, cc_email, bcc_email, None, signature)
            elif send_method == "SMTP":
                send_email_smtp(subject, body, to_email, cc_email, bcc_email, None, signature)
            elif send_method == "outlook":
                full_body = body + "\n\n" + signature
                result = send_email_via_outlook(to_email, subject, full_body, cc_email, bcc_email)
                if result is None:
                    print("Please authorize the application to send emails via Outlook.")
                elif result["status"] != "success":
                    raise Exception(f"Failed to send email via Outlook: {result['error_code']} - {result['error_message']}")

            # Mark as sent
            cursor.execute("UPDATE scheduled_emails SET status = 'Sent' WHERE id = ?", (email_id,))
        except Exception as e:
            # Mark as failed
            cursor.execute("UPDATE scheduled_emails SET status = 'Failed' WHERE id = ?", (email_id,))
            print(f"Error sending scheduled email: {e}")
    
    conn.commit()
    conn.close()

# Add scheduler to run every minute
schedule.every(1).minutes.do(process_scheduled_emails)

def start_scheduler():
    while True:
        schedule.run_pending()
        sleep_time.sleep(1)

threading.Thread(target=start_scheduler, daemon=True).start()


# Login Page Functionality
def login_page():
    st.markdown("<h3 style='text-align: left;'>Mass Mail</h3>", unsafe_allow_html=True)

    with st.form("login_form"):
        st.markdown("<h2>Welcome!</h2>", unsafe_allow_html=True)
        username = st.text_input("User name", placeholder="Enter your user name")
        password = st.text_input("Password", placeholder="Enter your Password", type="password")
        login_button = st.form_submit_button("Login")

        st.markdown(
        "<p style='text-align: center; color: gray;'>Don't have an Account? Register "
        "<a href='Register' onClick='window.location.href=\"/register\"' "
        "style='color: black; text-decoration: none;'>Register</a></p>",
        unsafe_allow_html=True,
    )

    if login_button:
        if username and password:
            user = cursor.execute(
                "SELECT id, username, password, is_active, is_superuser FROM users WHERE username = ? AND password = ?",
                (username, password),
            ).fetchone()
            if user:
                if user[3] == 0:  # Check if user is inactive
                    st.error("Your account is inactive. Please contact a superuser for activation.")
                else:
                    st.session_state.logged_in = True
                    st.session_state.is_superuser = bool(user[4])
                    st.session_state.page = (
                        "super_user_portal" if st.session_state.is_superuser else "new_page"
                    )
                    
                    st.session_state.user_id = user[0]  # Stores user ID in session state
                    st.rerun()
                    st.success(f"Welcome {username}!")
            else:
                st.error("Invalid username or password.")
        else:
            st.error("Please enter both username and password.")


# Registration Page Functionality
def registration_page():
    st.markdown("<h3 style='text-align: left;'>Mass Mail</h3>", unsafe_allow_html=True)

    with st.form("registration_form"):
        st.markdown("<h2>Create an Account</h2>", unsafe_allow_html=True)
        username = st.text_input("User name", placeholder="Enter your user name")
        password = st.text_input("Password", placeholder="Enter your Password", type="password")
        confirm_password = st.text_input("Confirm Password", placeholder="Confirm your password", type="password")
        user_type = st.radio("Select User Type", ["User", "Superuser"])  # New field for user type
        register_button = st.form_submit_button("Register")

    st.markdown(
        "<p style='text-align: center; color: gray;'>Already have an Account? "
        "<a href='#' onClick='window.location.href=\"/login\"' "
        "style='color: black; text-decoration: none;'>Login</a></p>",
        unsafe_allow_html=True,
    )

    if register_button:
        if username and password:
            if password == confirm_password:
                is_superuser = 1 if user_type == "Superuser" else 0
                try:
                    cursor.execute(
                        "INSERT INTO users (username, password, is_active, is_superuser) VALUES (?, ?, ?, ?)",
                        (username, password, 1, is_superuser),  # Default is_active is 0 (inactive)
                    )
                    conn.commit()
                    st.success("Registration successful! Waiting for activation by a superuser.")
                except sqlite3.IntegrityError:
                    st.error("Username already taken.")
            else:
                st.error("Passwords do not match.")
        else:
            st.error("Please fill in all fields.")


if "page" not in st.session_state:
    st.session_state.page = "login"
    st.session_state.logged_in = False


# Application flow based on current session state
if st.session_state.page == "login":
    login_page()
elif st.session_state.page == "register":
    registration_page()
elif st.session_state.page == "new_page":
    new_page()
elif st.session_state.page == "super_user_portal":
    super_user_portal()
elif st.session_state.page=="email_stats":
    email_stats()
elif st.session_state.page == "template_management":
    template_management()



# Navigation Buttons
if not st.session_state.logged_in:
    if st.session_state.page == "login":
        if st.button("Go to Registration"):
            switch_page("register")
            st.rerun()
    elif st.session_state.page == "register":
        if st.button("Go to Login"):
            switch_page("login")
            st.rerun()