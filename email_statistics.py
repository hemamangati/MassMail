import streamlit as st
import sqlite3
import pandas as pd
import plotly.graph_objects as go
import sqlite3
import schedule
import time
from gmail_api import *
from datetime import datetime, timezone

# The function to update statuses
def update_statuses():
    conn = sqlite3.connect("mass_mail.db")
    cursor = conn.cursor()

    # Fetch message IDs with unknown status
    cursor.execute("SELECT message_id FROM sent_emails WHERE status IS NULL OR status = 'unknown'")
    message_ids = [row[0] for row in cursor.fetchall()]

    service = create_gmail_service()
    for message_id in message_ids:
        status = get_email_status(service, message_id)
        cursor.execute("UPDATE sent_emails SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE message_id = ?", (status, message_id))

    conn.commit()
    conn.close()

# Function to schedule the status updates
def schedule_status_updates():
    schedule.every(1).hour.do(update_statuses)  # Run every hour

    # Keep the schedule running
    while True:
        schedule.run_pending()
        time.sleep(60)  # Sleep for a minute before checking again

# Run the periodic task in a separate thread (to prevent blocking the main UI)
import threading
def start_periodic_task():
    task_thread = threading.Thread(target=schedule_status_updates)
    task_thread.daemon = True  # This allows the thread to exit when the main program exits
    task_thread.start()

# Call this function at the start of your application

# Function to logout the user
def logout():
    # Clear session state related to login and redirection
    st.session_state.logged_in = False
    st.session_state.is_superuser = False
    st.success("You have been logged out.Refresh to Login again")

def email_stats():
    # Connect to the database
    conn = sqlite3.connect("mass_mail.db")
    cursor = conn.cursor()

    # Ensure required tables exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sent_emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender TEXT,
            recipient TEXT,
            status TEXT,  -- 'delivered', 'inbox', 'spam'
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mailbox (
            id INTEGER PRIMARY KEY,
            email TEXT,
            account_health FLOAT,
            deliverability FLOAT,
            not_blacklisted BOOLEAN,
            status BOOLEAN
        )
    """)

    conn.commit()

    # --- Fetch and calculate statistics ---
    email_stats_query = """
        SELECT 
            COUNT(*) AS total_sent,
            SUM(CASE WHEN status = 'delivered' THEN 1 ELSE 0 END) AS total_undelivered,
            SUM(CASE WHEN status = 'inbox' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS inbox_percentage,
            SUM(CASE WHEN status = 'spam' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS spam_percentage
        FROM sent_emails
    """
    stats = cursor.execute(email_stats_query).fetchone()

    # Fallback for empty database
    total_sent = stats[0] if stats[0] else 0
    total_undelivered = stats[1] if stats[1] else 0
    inbox_percentage = stats[0] if stats[0] else 0
    spam_percentage = stats[3] if stats[3] else 0

    ip=(inbox_percentage/total_sent)*100
    # --- Dashboard Title ---
    st.title("Email Status Dashboard")

    # --- Daily Limit ---
    st.info("Your Daily Email Limit is 100. Please Increase by 50 Per Day.")
    if st.button("Edit Limit"):
        st.warning("Edit Limit functionality is not implemented yet.")

    # --- Performance Summary ---
    st.subheader("Performance Summary")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Sent", total_sent)
    with col2:
        st.metric("UnDelivered", total_undelivered)
    with col3:
        st.metric("Landed in Inbox", f"{ip:.2f}%")
    with col4:
        st.metric("Landed in Spam", f"{spam_percentage:.2f}%")

    # --- Deliverability Score ---
    st.subheader("Deliverability Score")
    col1, col2 = st.columns([1, 2])

    with col1:
        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=ip,
            title={"text": "Deliverability Score"},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": "green"},
            }
        ))
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.metric("Mailbox Temp.", "298/day")
        st.markdown("### SPF: ✅")
        st.markdown("### DKIM: ✅")
        st.markdown("### DMARC: ✅")
        st.markdown("### Not Blacklisted: ✅")

    # --- Engagement Chart ---
    st.subheader("Engagement")
    engagement_data_query = """
        SELECT strftime('%w', updated_at) AS day_of_week, COUNT(*) AS engagement
        FROM sent_emails
        GROUP BY day_of_week
    """
    engagement_data = cursor.execute(engagement_data_query).fetchall()

    # Prepare engagement data for the week
    days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    engagement_values = [0] * 7
    for day, count in engagement_data:
        engagement_values[int(day)] = count

    fig2 = go.Figure()
    fig2.add_trace(go.Bar(x=days, y=engagement_values, name="Engagement"))
    fig2.update_layout(title="Email Engagement Over the Week", xaxis_title="Day", yaxis_title="Engagement")
    st.plotly_chart(fig2, use_container_width=True)
    user_id = st.session_state.get('user_id', None)
    if st.button("View Scheduled Emails"):
        conn = sqlite3.connect('mass_mail.db')
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM scheduled_emails WHERE user_id = ? ORDER BY schedule_time ASC", (user_id,))
        scheduled_emails = cursor.fetchall()
        conn.close()
        if scheduled_emails:
            for email in scheduled_emails:
                # Convert UTC timestamp to local time zone for display
                local_time = datetime.fromisoformat(email[7]).astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')
                st.write(f"**To:** {email[2]} | **Subject:** {email[4]} | **Scheduled For:** {local_time} | **Status:** {email[8]}")
        else:
            st.write("No scheduled emails.")

    # --- Logout Button ---
    if st.button("Logout"):
        logout()

