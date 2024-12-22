import MassMail
import streamlit as st
import sqlite3

conn = sqlite3.connect('mass_mail.db')
cursor = conn.cursor()

# Create template table
cursor.execute('''
CREATE TABLE IF NOT EXISTS templates (
    template_id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_name TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    created_by TEXT NOT NULL
)
''')

conn.commit()
conn.close()
def get_templates():
    conn = sqlite3.connect('mass_mail.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM templates')
    templates = cursor.fetchall()
    conn.close()
    return templates
user_id = st.session_state.get('user_id', None)

def add_template(name, subject, body, user):
    conn = sqlite3.connect('mass_mail.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO templates (template_name, subject, body, created_by) VALUES (?, ?, ?, ?)', 
                   (name, subject, body, user))
    conn.commit()
    conn.close()

def edit_template(template_id, name, subject, body):
    conn = sqlite3.connect('mass_mail.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE templates SET template_name=?, subject=?, body=? WHERE template_id=?', 
                   (name, subject, body, template_id))
    conn.commit()
    conn.close()

def delete_template(template_id):
    conn = sqlite3.connect('mass_mail.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM templates WHERE template_id=?', (template_id,))
    conn.commit()
    conn.close()

def get_template_by_id(template_id):
    conn = sqlite3.connect('mass_mail.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM templates WHERE template_id=?', (template_id,))
    template = cursor.fetchone()
    conn.close()
    return template

# Function to navigate between pages
def switch_page(page_name):
    st.session_state.page = page_name

# Function to logout the user
def logout():
    # Clear session state related to login and redirection
    st.session_state.logged_in = False
    st.session_state.is_superuser = False
    st.success("You have been logged out. Refresh to Login again")


def template_management():
    st.title("Email Template Management")

    # Add New Template
    st.header("Add New Template")
    with st.form("add_template"):
        name = st.text_input("Template Name")
        subject = st.text_input("Subject")
        body = st.text_area("Body")
        user = user_id  # Replace with actual logged-in user's name or ID
        if st.form_submit_button("Add Template"):
            add_template(name, subject, body, user)
            st.success("Template added successfully!")

    # Edit or Delete Templates
    st.header("Manage Existing Templates")
    templates = get_templates()
    template_options = [f"{template[1]} - {template[2]}" for template in templates]
    template_id = st.selectbox("Select Template to Edit/Delete", [template[0] for template in templates], format_func=lambda x: template_options[x-1] if x > 0 else "None")


    if template_id:
        template = next(t for t in templates if t[0] == template_id)
        name = st.text_input("Template Name", value=template[1])
        subject = st.text_input("Subject", value=template[2])
        body = st.text_area("Body", value=template[3])

        with st.form("edit_template"):
            if st.form_submit_button("Update Template"):
                edit_template(template_id, name, subject, body)
                st.success("Template updated successfully!")

            if st.form_submit_button("Delete Template"):
                delete_template(template_id)
                st.success("Template deleted successfully!")
                st.rerun()

    # Display a button for superusers to redirect to the superuser portal
    if st.session_state.is_superuser:
        st.markdown("<hr>", unsafe_allow_html=True)
        st.markdown("<h4>Superuser Options</h4>", unsafe_allow_html=True)
        if st.button("Go to Superuser Portal"):
            st.session_state.page="super_user_portal"
            st.rerun()

    # Add the logout button
    if st.button("Logout"):
        logout()

if st.session_state.page == "super_user_portal":
    MassMail.super_user_portal()
elif st.session_state.page =="login_page":
    MassMail.login_page()