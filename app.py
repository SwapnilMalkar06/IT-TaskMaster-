from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import mysql.connector
from functools import wraps
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header # Added for secure header encoding
from datetime import timedelta, date 
import os 
import csv
from io import StringIO
from flask import Response

app = Flask(__name__)
app.secret_key = 'swapnil_mca_project_secret_key_fixed'
app.permanent_session_lifetime = timedelta(days=7)

# --- File Upload Configuration ---
UPLOAD_FOLDER = 'static/uploads/profiles'
SUBMISSION_FOLDER = 'static/uploads/submissions'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SUBMISSION_FOLDER'] = SUBMISSION_FOLDER

# Create upload directories if they don't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(SUBMISSION_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Database Configuration
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': '852456',
    'database': 'taskmaster_db'
}

# Email Configuration
EMAIL_SENDER = "organizationtaskmaster@gmail.com"
EMAIL_PASSWORD = "gqoztduerrcpepew" # Updated with the correct password

def get_db():
    return mysql.connector.connect(**db_config)

# --- Audit Log Helper Function ---
def log_action(action_type, description):
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO audit_logs (user_id, action_type, description) VALUES (%s, %s, %s)",
                       (session.get('id'), action_type, description))
        conn.commit()
        cursor.close(); conn.close()
    except Exception as e:
        print(f"Audit Log Error: {str(e)}")

# --- FIXED Email Helper Function ---
def send_email(receiver_email, subject, body):
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_SENDER
        msg['To'] = receiver_email
        msg['Subject'] = Header(subject, 'utf-8')
        
        # Explicitly set charset to utf-8
        msg.attach(MIMEText(body, 'html', 'utf-8'))

        server = smtplib.SMTP('smtp.gmail.com', 587, timeout=30)
        server.set_debuglevel(0) 
        server.ehlo()
        server.starttls() # Secure the connection
        server.ehlo()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        
        server.sendmail(EMAIL_SENDER, receiver_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"Email Error Detail: {str(e)}")
        return False

# --- Login Required Decorator ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'loggedin' not in session:
            flash("Please log in first.", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- Authentication Routes ---

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        try:
            conn = get_db()
            cursor = conn.cursor(dictionary=True)
            query = "SELECT * FROM users WHERE email = %s AND password_hash = %s"
            cursor.execute(query, (email, password))
            user = cursor.fetchone()

            if user:
                session.permanent = True 
                session['loggedin'] = True
                session['id'] = user['id']
                session['name'] = user['name']
                session['role'] = user['role']
                session['profile_pic'] = user.get('profile_pic')

                # --- LOG LOGIN EVENT ---
                cursor.execute("INSERT INTO user_logs (user_id) VALUES (%s)", (user['id'],))
                conn.commit()
                session['log_id'] = cursor.lastrowid 

                cursor.close()
                conn.close()
                flash(f"Welcome back, {user['name']}!", "success")
                return redirect(url_for('admin_dashboard' if user['role'] == 'admin' else 'employee_dashboard'))
            else:
                cursor.close()
                conn.close()
                flash("Invalid email or password", "danger")
        except Exception as e:
            flash(f"Database error: {str(e)}", "danger")
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    # --- LOG LOGOUT EVENT ---
    if 'log_id' in session:
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("UPDATE user_logs SET logout_time = CURRENT_TIMESTAMP WHERE id = %s", (session['log_id'],))
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"Logout logging error: {str(e)}")

    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for('login'))

# --- Admin Modules ---

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
    
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("SELECT COUNT(*) as count FROM user_logs WHERE logout_time IS NULL")
        active_now = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM notices WHERE is_active = TRUE")
        notice_count = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM users WHERE role='employee'")
        emp_count = cursor.fetchone()['count']
        cursor.execute("SELECT COUNT(*) as count FROM projects WHERE status='Active'")
        proj_count = cursor.fetchone()['count']
        cursor.execute("SELECT status, COUNT(*) as count FROM tasks GROUP BY status")
        task_stats_raw = cursor.fetchall()
        
        task_stats = {'Completed': 0, 'Pending': 0, 'In-Progress': 0}
        for row in task_stats_raw:
            if row['status'] in task_stats:
                task_stats[row['status']] = row['count']
        
        # Admin Dashboard Sorting: Important/Urgent first, Verified/Done last
        query_recent = """
            SELECT t.title as task_name, u.name as emp_name, p.title as proj_name, t.priority, t.status 
            FROM tasks t 
            JOIN users u ON t.assigned_to_user_id = u.id 
            JOIN projects p ON t.project_id = p.id
            ORDER BY 
                CASE WHEN t.verification_status = 'Verified' THEN 1 ELSE 0 END ASC,
                t.deadline ASC,
                FIELD(t.priority, 'High', 'Medium', 'Low') ASC
            LIMIT 5
        """
        cursor.execute(query_recent)
        recent_tasks = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return render_template('admin_dash.html', active_now=active_now, notice_count=notice_count, 
                               emp_count=emp_count, proj_count=proj_count, 
                               task_completed=task_stats['Completed'], task_pending=task_stats['Pending'],
                               task_progress=task_stats['In-Progress'], recent_tasks=recent_tasks)
    except Exception as e:
        return f"Database Error: {str(e)}"

# --- Employee CRUD Management ---
@app.route('/admin/employees', methods=['GET', 'POST'])
@login_required
def manage_employees():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))

    conn = get_db(); cursor = conn.cursor(dictionary=True)
    if request.method == 'POST':
        name, email = request.form.get('name'), request.form.get('email')
        pwd, desg = request.form.get('password'), request.form.get('designation')
        try:
            cursor.execute("INSERT INTO users (name, email, password_hash, role, designation) VALUES (%s, %s, %s, 'employee', %s)", 
                           (name, email, pwd, desg))
            conn.commit()
            
            # --- PROFESSIONAL WELCOME DRAFT ---
            subject = "Get off to a great start with TaskMaster"
            body = f"""
            <div style="font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; color: #444; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #eee;">
                <div style="text-align: center; margin-bottom: 30px;">
                    <h1 style="color: #28a745; margin-bottom: 5px;">TaskMaster</h1>
                    <p style="font-size: 20px; color: #666; font-weight: 300;">Official Onboarding</p>
                </div>
                <p>Hi <b>{name}</b>,</p>
                <p>TaskMaster Success Team here... We're so pleased to meet you!</p>
                <p>We're here to make sure you're productive. And, as a wise man once said, the first step to productivity is a properly set up account.</p>
                <p>You have been registered as a <b>{desg}</b>. Logging into your dashboard will help you manage your tasks and verification status seamlessly.</p>
                <div style="background: #f9f9f9; border-radius: 10px; padding: 25px; text-align: center; margin: 30px 0; border: 1px dashed #28a745;">
                    <h3 style="color: #28a745; margin-top: 0;">Your Account Credentials</h3>
                    <p style="margin-bottom: 20px;">Use the credentials below to log in:</p>
                    <p style="font-size: 16px;"><b>Email:</b> {email}<br><b>Temporary Password:</b> {pwd}</p>
                    <a href="http://localhost:5000" style="display: inline-block; padding: 12px 25px; background-color: #28a745; color: white; text-decoration: none; border-radius: 5px; font-weight: bold; margin-top: 10px;">Login to Portal</a>
                </div>
                <p>Until next time,</p>
                <p><b>Your Success Geckos</b></p>
            </div>
            """
            send_email(email, subject, body)
            
            flash(f"Employee {name} added!", "success")
        except Exception as e:
            flash(f"Error: {str(e)}", "danger")
        return redirect(url_for('manage_employees'))

    search = request.args.get('search', '')
    if search:
        query = "SELECT id, name, email, designation, created_at FROM users WHERE role='employee' AND (name LIKE %s OR email LIKE %s) ORDER BY created_at DESC"
        cursor.execute(query, (f'%{search}%', f'%{search}%'))
    else:
        cursor.execute("SELECT id, name, email, designation, created_at FROM users WHERE role='employee' ORDER BY created_at DESC")
    employees = cursor.fetchall()
    cursor.close(); conn.close()
    return render_template('manage_employees.html', employees=employees, search=search)

@app.route('/admin/edit_employee/<int:id>', methods=['POST'])
@login_required
def edit_employee(id):
    data = (request.form.get('name'), request.form.get('email'), request.form.get('designation'), id)
    conn = get_db(); cursor = conn.cursor()
    cursor.execute("UPDATE users SET name=%s, email=%s, designation=%s WHERE id=%s", data)
    conn.commit(); cursor.close(); conn.close()
    flash("Employee updated!", "success")
    return redirect(url_for('manage_employees'))

@app.route('/admin/delete_employee/<int:id>')
@login_required
def delete_employee(id):
    conn = get_db(); cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE id=%s", (id,))
    conn.commit(); cursor.close(); conn.close()
    flash("Employee deleted!", "info")
    return redirect(url_for('manage_employees'))

@app.route('/admin/projects', methods=['GET', 'POST'])
@login_required
def manage_projects():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
    conn = get_db(); cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        data = (request.form.get('title'), request.form.get('description'), request.form.get('start_date'), request.form.get('deadline'), request.form.get('status'))
        cursor.execute("INSERT INTO projects (title, description, start_date, deadline, status) VALUES (%s, %s, %s, %s, %s)", data)
        conn.commit(); flash("Project created!", "success")
        return redirect(url_for('manage_projects'))

    search = request.args.get('search', '')
    if search:
        cursor.execute("SELECT * FROM projects WHERE title LIKE %s ORDER BY deadline ASC", (f'%{search}%',))
    else:
        cursor.execute("SELECT * FROM projects ORDER BY deadline ASC")
    projects = cursor.fetchall()
    cursor.close(); conn.close()
    return render_template('manage_projects.html', projects=projects, search=search)

@app.route('/admin/edit_project/<int:id>', methods=['POST'])
@login_required
def edit_project(id):
    title = request.form.get('title')
    data = (title, request.form.get('description'), request.form.get('start_date'), request.form.get('deadline'), request.form.get('status'), id)
    conn = get_db(); cursor = conn.cursor()
    cursor.execute("UPDATE projects SET title=%s, description=%s, start_date=%s, deadline=%s, status=%s WHERE id=%s", data)
    conn.commit(); cursor.close(); conn.close()
    
    # --- LOG ACTION: PROJECT UPDATE ---
    log_action("Project Update", f"Updated details for project: {title}")
    
    flash("Project updated!", "success")
    return redirect(url_for('manage_projects'))

@app.route('/admin/delete_project/<int:id>')
@login_required
def delete_project(id):
    conn = get_db(); cursor = conn.cursor()
    cursor.execute("DELETE FROM projects WHERE id=%s", (id,))
    conn.commit(); cursor.close(); conn.close()
    flash("Project removed!", "info")
    return redirect(url_for('manage_projects'))

# --- Task Management with Project and Employee Filtering ---
@app.route('/admin/tasks', methods=['GET', 'POST'])
@login_required
def manage_tasks():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
    conn = get_db(); cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        project_id = request.form.get('project_id')
        user_id = request.form.get('user_id')
        title = request.form.get('title')
        description = request.form.get('description')
        priority = request.form.get('priority')
        deadline = request.form.get('deadline') 
        
        cursor.execute("INSERT INTO tasks (project_id, assigned_to_user_id, title, description, priority, deadline, status) VALUES (%s, %s, %s, %s, %s, %s, 'Pending')", 
                       (project_id, user_id, title, description, priority, deadline))
        conn.commit()

        cursor.execute("SELECT email, name FROM users WHERE id = %s", (user_id,))
        emp = cursor.fetchone()
        cursor.execute("SELECT title FROM projects WHERE id = %s", (project_id,))
        proj = cursor.fetchone()

        # --- PROFESSIONAL TASK ASSIGNMENT DRAFT ---
        subject = f"Action Required: New Task Assigned - {title}"
        body = f"""
        <div style="font-family: Arial, sans-serif; color: #333; max-width: 600px; margin: auto; padding: 25px; border: 1px solid #ddd; border-top: 4px solid #007bff;">
            <h2 style="color: #007bff; margin-top: 0;">New Task Assignment</h2>
            <p>Hi {emp['name']},</p>
            <p>You have been assigned a new task within the project <b>{proj['title']}</b>. Please find the details below:</p>
            <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                <tr style="background: #f8f9fa;">
                    <td style="padding: 10px; border: 1px solid #eee;"><b>Task Name:</b></td>
                    <td style="padding: 10px; border: 1px solid #eee;">{title}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; border: 1px solid #eee;"><b>Priority:</b></td>
                    <td style="padding: 10px; border: 1px solid #eee;"><span style="color: {'#dc3545' if priority == 'High' else '#ffc107' if priority == 'Medium' else '#28a745'}; font-weight: bold;">{priority}</span></td>
                </tr>
                <tr style="background: #f8f9fa;">
                    <td style="padding: 10px; border: 1px solid #eee;"><b>Deadline:</b></td>
                    <td style="padding: 10px; border: 1px solid #eee; color: #dc3545; font-weight: bold;">{deadline}</td>
                </tr>
            </table>
            <p><b>Description:</b><br>{description}</p>
            <div style="text-align: center; margin-top: 30px;">
                <a href="http://localhost:5000" style="padding: 12px 30px; background-color: #007bff; color: white; text-decoration: none; border-radius: 4px; font-weight: bold;">View Task Dashboard</a>
            </div>
        </div>
        """
        send_email(emp['email'], subject, body)

        flash("Task assigned!", "success")
        return redirect(url_for('manage_tasks'))

    # --- Filtering Logic ---
    proj_filter = request.args.get('project_filter')
    emp_filter = request.args.get('employee_filter')

    query_tasks = """
        SELECT t.*, u.name as emp_name, p.title as proj_name 
        FROM tasks t 
        JOIN users u ON t.assigned_to_user_id = u.id 
        JOIN projects p ON t.project_id = p.id 
    """
    params = []
    where_clauses = []

    if proj_filter:
        where_clauses.append("t.project_id = %s")
        params.append(proj_filter)
    if emp_filter:
        where_clauses.append("t.assigned_to_user_id = %s")
        params.append(emp_filter)
    
    search = request.args.get('search', '')
    if search:
        where_clauses.append("t.title LIKE %s")
        params.append(f'%{search}%')

    if where_clauses:
        query_tasks += " WHERE " + " AND ".join(where_clauses)

    query_tasks += """
        ORDER BY 
            CASE WHEN t.verification_status = 'Verified' THEN 1 ELSE 0 END ASC,
            t.deadline ASC,
            FIELD(t.priority, 'High', 'Medium', 'Low') ASC
    """

    cursor.execute(query_tasks, tuple(params))
    tasks = cursor.fetchall()
    
    cursor.execute("SELECT id, name FROM users WHERE role='employee'")
    employees = cursor.fetchall()
    cursor.execute("SELECT id, title FROM projects")
    projects = cursor.fetchall()
    
    cursor.close(); conn.close()
    return render_template('manage_tasks.html', tasks=tasks, employees=employees, projects=projects, 
                           proj_filter=int(proj_filter) if proj_filter else None, 
                           emp_filter=int(emp_filter) if emp_filter else None,
                           search=search)

@app.route('/admin/edit_task/<int:id>', methods=['POST'])
@login_required
def edit_task(id):
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
    
    project_id = request.form.get('project_id')
    user_id = request.form.get('user_id')
    title = request.form.get('title')
    description = request.form.get('description')
    priority = request.form.get('priority')
    status = request.form.get('status')
    deadline = request.form.get('deadline') 
    
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("UPDATE tasks SET project_id=%s, assigned_to_user_id=%s, title=%s, description=%s, priority=%s, deadline=%s, status=%s WHERE id=%s",
                   (project_id, user_id, title, description, priority, deadline, status, id))
    conn.commit()

    cursor.execute("SELECT email, name FROM users WHERE id = %s", (user_id,))
    emp = cursor.fetchone()

    # --- PROFESSIONAL TASK UPDATE DRAFT ---
    subject = f"Task Update: {title}"
    body = f"""
    <div style="font-family: Arial; padding: 25px; border: 1px solid #eee; border-radius: 8px;">
        <h2 style="color: #6c757d;">Task Modification Notice</h2>
        <p>Hello {emp['name']},</p>
        <p>The details for your task <b>"{title}"</b> have been updated by the administrator.</p>
        <p><b>New Status:</b> <span style="font-weight: bold; color: #007bff;">{status}</span></p>
        <p><b>Updated Description:</b><br>{description}</p>
        <p>Please log in to your dashboard to review any changes in requirements or timelines.</p>
    </div>
    """
    send_email(emp['email'], subject, body)

    cursor.close(); conn.close()
    flash("Task updated!", "success")
    return redirect(url_for('manage_tasks'))

@app.route('/admin/delete_task/<int:id>')
@login_required
def delete_task(id):
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT title FROM tasks WHERE id=%s", (id,))
    task = cursor.fetchone()
    if task:
        log_action("Task Deletion", f"Deleted task: {task['title']}")
        cursor.execute("DELETE FROM tasks WHERE id=%s", (id,))
        conn.commit()
        flash("Task removed.", "info")
    cursor.close(); conn.close()
    return redirect(url_for('manage_tasks'))

@app.route('/admin/submissions')
@login_required
def admin_submissions():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
    
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        # Sort submissions: Review needed first, Verified last
        query = """
            SELECT t.id, t.title, t.remarks, t.submission_file, t.status, t.verification_status,
                   u.name as emp_name, u.designation, p.title as proj_name, t.created_at
            FROM tasks t
            JOIN users u ON t.assigned_to_user_id = u.id
            JOIN projects p ON t.project_id = p.id
            WHERE t.status = 'Completed' AND t.submission_file IS NOT NULL
            ORDER BY 
                CASE WHEN t.verification_status = 'Verified' THEN 1 ELSE 0 END ASC,
                t.created_at DESC
        """
        cursor.execute(query)
        submissions = cursor.fetchall()
        cursor.close()
        conn.close()
        return render_template('admin_submissions.html', submissions=submissions)
    except Exception as e:
        return f"Database Error: {str(e)}"

# --- ATTENDANCE REPORT ROUTE ---
@app.route('/admin/reports/attendance')
@login_required
def attendance_report():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
    
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT l.login_time, l.logout_time, u.name, u.designation 
            FROM user_logs l 
            JOIN users u ON l.user_id = u.id 
            ORDER BY l.login_time DESC
        """
        cursor.execute(query)
        logs = cursor.fetchall()
        cursor.close()
        conn.close()
        return render_template('attendance_report.html', logs=logs)
    except Exception as e:
        return f"Database Error: {str(e)}"

@app.route('/admin/verify_submission/<int:id>', methods=['POST'])
@login_required
def verify_submission(id):
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
    
    status = request.form.get('ver_status') 
    
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("UPDATE tasks SET verification_status = %s WHERE id = %s", (status, id))
        
        query_info = """
            SELECT u.email, u.name, t.title 
            FROM tasks t 
            JOIN users u ON t.assigned_to_user_id = u.id 
            WHERE t.id = %s
        """
        cursor.execute(query_info, (id,))
        info = cursor.fetchone()
        conn.commit()

        if info:
            subject = f"Work Status Update: {info['title']}"
            color = "#28a745" if status == "Verified" else "#dc3545"
            feedback = "Congratulations! Your task has been accepted." if status == "Verified" else "There are some issues. Please check remarks and resubmit."
            
            # --- PROFESSIONAL VERIFICATION DRAFT ---
            body = f"""
            <div style="font-family: Arial; padding: 25px; border: 1px solid #ddd; border-radius: 12px; max-width: 550px; margin: auto;">
                <div style="text-align: center; margin-bottom: 20px;">
                    <span style="display: inline-block; padding: 8px 15px; background-color: {color}; color: white; border-radius: 20px; font-weight: bold; font-size: 14px;">{status.upper()}</span>
                </div>
                <h3 style="color: #333; text-align: center;">Task Verification Result</h3>
                <p>Hello <b>{info['name']}</b>,</p>
                <p>The status of your work for task <b>"{info['title']}"</b> has been updated to <b>{status}</b>.</p>
                <p style="background-color: #fcfcfc; padding: 15px; border-left: 4px solid {color}; italic;">"{feedback}"</p>
                <p>Please log in to the portal for more details or to address required changes.</p>
                <hr style="border: none; border-top: 1px solid #eee; margin-top: 25px;">
                <p style="font-size: 12px; color: #999; text-align: center;">TaskMaster Automated Audit System</p>
            </div>
            """
            send_email(info['email'], subject, body)

        cursor.close(); conn.close()
        flash(f"Task marked as {status} and employee notified!", "success")
    except Exception as e:
        flash(f"Error: {str(e)}", "danger")
    
    return redirect(url_for('admin_submissions'))

@app.route('/admin/delete_submission/<int:id>')
@login_required
def delete_submission(id):
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
    
    conn = get_db(); cursor = conn.cursor()
    cursor.execute("DELETE FROM tasks WHERE id = %s", (id,))
    conn.commit(); cursor.close(); conn.close()
    
    flash("Submission record deleted.", "info")
    return redirect(url_for('admin_submissions'))


@app.route('/admin/reports/productivity')
@login_required
def productivity_report():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
    
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT 
                u.name, 
                u.designation,
                COUNT(t.id) AS total_tasks,
                SUM(CASE WHEN t.verification_status = 'Verified' THEN 1 ELSE 0 END) AS verified_tasks,
                SUM(CASE WHEN t.verification_status = 'Re-do Required' THEN 1 ELSE 0 END) AS redo_tasks,
                ROUND((SUM(CASE WHEN t.verification_status = 'Verified' THEN 1 ELSE 0 END) / COUNT(t.id)) * 100, 2) AS completion_rate
            FROM users u
            LEFT JOIN tasks t ON u.id = t.assigned_to_user_id
            WHERE u.role = 'employee'
            GROUP BY u.id
            ORDER BY completion_rate DESC
        """
        cursor.execute(query)
        report_data = cursor.fetchall()
        cursor.close(); conn.close()
        return render_template('productivity_report.html', report_data=report_data)
    except Exception as e:
        return f"Database Error: {str(e)}"

@app.route('/admin/export/productivity')
@login_required
def export_productivity_csv():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
    
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT 
                u.name, 
                u.designation,
                COUNT(t.id) AS total_tasks,
                SUM(CASE WHEN t.verification_status = 'Verified' THEN 1 ELSE 0 END) AS verified_tasks,
                SUM(CASE WHEN t.verification_status = 'Re-do Required' THEN 1 ELSE 0 END) AS redo_tasks,
                ROUND((SUM(CASE WHEN t.verification_status = 'Verified' THEN 1 ELSE 0 END) / NULLIF(COUNT(t.id), 0)) * 100, 2) AS completion_rate
            FROM users u
            LEFT JOIN tasks t ON u.id = t.assigned_to_user_id
            WHERE u.role = 'employee'
            GROUP BY u.id
            ORDER BY completion_rate DESC
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        
        si = StringIO()
        cw = csv.writer(si)
        cw.writerow(['Employee Name', 'Designation', 'Total Tasks', 'Verified Tasks', 'Redo Required', 'Completion Rate (%)'])
        
        for row in rows:
            cw.writerow([
                row['name'], 
                row['designation'], 
                row['total_tasks'], 
                row['verified_tasks'], 
                row['redo_tasks'], 
                row['completion_rate'] or 0
            ])
            
        output = si.getvalue()
        cursor.close(); conn.close()
        
        return Response(
            output,
            mimetype="text/csv",
            headers={"Content-disposition": "attachment; filename=productivity_report.csv"}
        )
    except Exception as e:
        return f"Error during export: {str(e)}"
    
@app.route('/admin/reports/projects')
@login_required
def project_status_report():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
    
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT 
                p.title, 
                p.deadline,
                COUNT(t.id) AS total_tasks,
                SUM(CASE WHEN t.verification_status = 'Verified' THEN 1 ELSE 0 END) AS completed_tasks,
                SUM(CASE WHEN t.status = 'Pending' THEN 1 ELSE 0 END) AS pending_tasks,
                ROUND((SUM(CASE WHEN t.verification_status = 'Verified' THEN 1 ELSE 0 END) / NULLIF(COUNT(t.id), 0)) * 100, 2) AS progress
            FROM projects p
            LEFT JOIN tasks t ON p.id = t.project_id
            GROUP BY p.id
            ORDER BY p.deadline ASC
        """
        cursor.execute(query)
        project_data = cursor.fetchall()
        cursor.close(); conn.close()
        return render_template('project_status_report.html', project_data=project_data)
    except Exception as e:
        return f"Database Error: {str(e)}"
    
@app.route('/admin/export/projects')
@login_required
def export_projects_csv():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
    
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT 
                p.title, 
                p.deadline,
                COUNT(t.id) AS total_tasks,
                SUM(CASE WHEN t.verification_status = 'Verified' THEN 1 ELSE 0 END) AS completed_tasks,
                SUM(CASE WHEN t.status = 'Pending' THEN 1 ELSE 0 END) AS pending_tasks,
                ROUND((SUM(CASE WHEN t.verification_status = 'Verified' THEN 1 ELSE 0 END) / NULLIF(COUNT(t.id), 0)) * 100, 2) AS progress
            FROM projects p
            LEFT JOIN tasks t ON p.id = t.project_id
            GROUP BY p.id
            ORDER BY p.deadline ASC
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        
        si = StringIO()
        cw = csv.writer(si)
        cw.writerow(['Project Title', 'Deadline', 'Total Tasks', 'Verified Tasks', 'Pending Tasks', 'Progress (%)'])
        
        for row in rows:
            cw.writerow([
                row['title'], 
                row['deadline'], 
                row['total_tasks'], 
                row['completed_tasks'] or 0, 
                row['pending_tasks'] or 0, 
                row['progress'] or 0
            ])
            
        output = si.getvalue()
        cursor.close(); conn.close()
        
        return Response(
            output,
            mimetype="text/csv",
            headers={"Content-disposition": "attachment; filename=project_status_report.csv"}
        )
    except Exception as e:
        return f"Export Error: {str(e)}"
    
@app.route('/admin/reports/custom_project', methods=['GET', 'POST'])
@login_required
def custom_project_report():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
        
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, title FROM projects ORDER BY title ASC")
    all_projects = cursor.fetchall()
    
    selected_project = request.form.get('project_id') if request.method == 'POST' else request.args.get('project_id')
    start_date = request.form.get('start_date') if request.method == 'POST' else request.args.get('start_date')
    end_date = request.form.get('end_date') if request.method == 'POST' else request.args.get('end_date')
    
    project_data = []
    if request.method == 'POST' or (request.method == 'GET' and (selected_project or start_date or end_date)):
        query = """
            SELECT 
                p.title, p.description as project_description, p.start_date, p.deadline as project_deadline, p.status as project_status,
                t.title as task_title, t.description as task_description, t.priority, t.status as task_status, t.deadline as task_deadline, t.verification_status,
                u.name as assigned_employee
            FROM projects p
            LEFT JOIN tasks t ON t.project_id = p.id
            LEFT JOIN users u ON t.assigned_to_user_id = u.id
            WHERE 1=1
        """
        params = []
        if selected_project:
            query += " AND p.id = %s"
            params.append(selected_project)
        if start_date:
            query += " AND p.start_date >= %s"
            params.append(start_date)
        if end_date:
            query += " AND p.start_date <= %s"
            params.append(end_date)
            
        query += " ORDER BY p.start_date DESC, t.deadline ASC"
        cursor.execute(query, tuple(params))
        project_data = cursor.fetchall()
        
    cursor.close(); conn.close()
    return render_template('custom_project_report.html', all_projects=all_projects, project_data=project_data, 
                           selected_project=int(selected_project) if selected_project and selected_project.isdigit() else None, 
                           start_date=start_date, end_date=end_date)

@app.route('/admin/export/custom_project_csv')
@login_required
def export_custom_project_csv():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
        
    selected_project = request.args.get('project_id')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    query = """
        SELECT 
            p.title as proj_title, p.description as proj_desc, p.start_date as proj_start, p.deadline as proj_deadline, p.status as proj_status,
            t.title as task_title, t.description as task_desc, t.priority, t.status as task_status, t.deadline as task_deadline, t.verification_status,
            u.name as assigned_employee
        FROM projects p
        LEFT JOIN tasks t ON t.project_id = p.id
        LEFT JOIN users u ON t.assigned_to_user_id = u.id
        WHERE 1=1
    """
    params = []
    if selected_project:
        query += " AND p.id = %s"
        params.append(selected_project)
    if start_date:
        query += " AND p.start_date >= %s"
        params.append(start_date)
    if end_date:
        query += " AND p.start_date <= %s"
        params.append(end_date)
            
    query += " ORDER BY p.start_date DESC, t.deadline ASC"
    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()
    
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['Project Title', 'Project Description', 'Project Start', 'Project Deadline', 'Project Status', 
                 'Task Title', 'Task Description', 'Assigned To', 'Priority', 'Task Status', 'Deadline', 'Verification Status'])
    
    for row in rows:
        cw.writerow([
            row['proj_title'],
            row['proj_desc'],
            row['proj_start'].strftime('%d/%m/%Y') if row['proj_start'] else 'N/A',
            row['proj_deadline'].strftime('%d/%m/%Y') if row['proj_deadline'] else 'N/A',
            row['proj_status'],
            row['task_title'] or 'No tasks',
            row['task_desc'] or 'N/A',
            row['assigned_employee'] or 'N/A',
            row['priority'] or 'N/A',
            row['task_status'] or 'N/A',
            row['task_deadline'].strftime('%d/%m/%Y') if row['task_deadline'] else 'N/A',
            row['verification_status'] or 'N/A'
        ])
            
    output = si.getvalue()
    cursor.close(); conn.close()
    
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=custom_project_report.csv"}
    )

@app.route('/admin/reports/employee_task', methods=['GET', 'POST'])
@login_required
def employee_report():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
        
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, name FROM users WHERE role='employee' ORDER BY name ASC")
    all_employees = cursor.fetchall()
    
    selected_employee = request.form.get('employee_id') if request.method == 'POST' else request.args.get('employee_id')
    
    task_data = []
    stats = {'Completed': 0, 'Pending': 0, 'In-Progress': 0}
    
    if selected_employee:
        query = """
            SELECT t.*, p.title as proj_name 
            FROM tasks t 
            JOIN projects p ON t.project_id = p.id 
            WHERE t.assigned_to_user_id = %s 
            ORDER BY t.deadline ASC
        """
        cursor.execute(query, (selected_employee,))
        task_data = cursor.fetchall()
        
        for task in task_data:
            if task['status'] in stats:
                stats[task['status']] += 1
                
    cursor.close(); conn.close()
    return render_template('employee_report.html', all_employees=all_employees, task_data=task_data, 
                           selected_employee=int(selected_employee) if selected_employee and selected_employee.isdigit() else None, 
                           stats=stats, today=date.today())

@app.route('/admin/export/employee_task_csv')
@login_required
def export_employee_report_csv():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
        
    selected_employee = request.args.get('employee_id')
    if not selected_employee:
        return "No employee selected", 400
        
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT name FROM users WHERE id = %s", (selected_employee,))
    emp_name = cursor.fetchone()['name']
    
    query = """
        SELECT t.*, p.title as proj_name 
        FROM tasks t 
        JOIN projects p ON t.project_id = p.id 
        WHERE t.assigned_to_user_id = %s 
        ORDER BY t.deadline ASC
    """
    cursor.execute(query, (selected_employee,))
    rows = cursor.fetchall()
    
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['Employee Name', 'Project', 'Task Title', 'Description', 'Priority', 'Status', 'Deadline', 'Verification Status'])
    
    for row in rows:
        cw.writerow([
            emp_name,
            row['proj_name'],
            row['title'],
            row['description'],
            row['priority'],
            row['status'],
            row['deadline'].strftime('%d/%m/%Y') if row['deadline'] else 'N/A',
            row['verification_status'] or 'N/A'
        ])
            
    output = si.getvalue()
    cursor.close(); conn.close()
    
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename=employee_{emp_name.replace(' ', '_')}_report.csv"}
    )
    
@app.route('/admin/notices', methods=['GET', 'POST'])
@login_required
def manage_notices():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
    
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    
    if request.method == 'POST':
        title = request.form.get('title')
        message = request.form.get('message')
        cursor.execute("INSERT INTO notices (title, message) VALUES (%s, %s)", (title, message))
        conn.commit()
        log_action("Notice Created", f"Admin posted: {title}") 
        flash("Notice published successfully!", "success")
        return redirect(url_for('manage_notices'))

    cursor.execute("SELECT * FROM notices ORDER BY created_at DESC")
    all_notices = cursor.fetchall()
    cursor.close(); conn.close()
    return render_template('manage_notices.html', notices=all_notices)

@app.route('/admin/delete_notice/<int:id>')
@login_required
def delete_notice(id):
    conn = get_db(); cursor = conn.cursor()
    cursor.execute("DELETE FROM notices WHERE id=%s", (id,))
    conn.commit(); cursor.close(); conn.close()
    flash("Notice removed.", "info")
    return redirect(url_for('manage_notices'))

@app.route('/admin/notice_tracking/<int:id>')
@login_required
def notice_tracking(id):
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
        
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT title FROM notices WHERE id = %s", (id,))
    notice = cursor.fetchone()
    if not notice:
        flash("Notice not found.", "danger")
        return redirect(url_for('manage_notices'))
        
    cursor.execute("SELECT u.name, u.designation, u.email, nr.read_at FROM users u JOIN notice_reads nr ON u.id = nr.user_id WHERE u.role = 'employee' AND nr.notice_id = %s ORDER BY nr.read_at DESC", (id,))
    recognized = cursor.fetchall()
    
    cursor.execute("SELECT u.name, u.designation, u.email FROM users u WHERE u.role = 'employee' AND u.id NOT IN (SELECT user_id FROM notice_reads WHERE notice_id = %s)", (id,))
    ignored = cursor.fetchall()
    
    cursor.close(); conn.close()
    return render_template('notice_tracking.html', notice=notice, recognized=recognized, ignored=ignored)

# --- VIEW AUDIT LOG ROUTE ---
@app.route('/admin/reports/audit')
@login_required
def system_audit_log():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
    
    try:
        conn = get_db(); cursor = conn.cursor(dictionary=True)
        query = """
            SELECT a.*, u.name as admin_name 
            FROM audit_logs a 
            JOIN users u ON a.user_id = u.id 
            ORDER BY a.action_time DESC
        """
        cursor.execute(query)
        logs = cursor.fetchall()
        cursor.close(); conn.close()
        return render_template('audit_log.html', logs=logs)
    except Exception as e:
        return f"Database Error: {str(e)}"
    
@app.route('/admin/toggle_notice/<int:id>')
@login_required
def toggle_notice(id):
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
    
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT is_active, title FROM notices WHERE id = %s", (id,))
        notice = cursor.fetchone()
        
        if notice:
            new_status = not notice['is_active']
            cursor.execute("UPDATE notices SET is_active = %s WHERE id = %s", (new_status, id))
            conn.commit()
            
            status_text = "Activated" if new_status else "Deactivated"
            log_action("Notice Status Change", f"{status_text} notice: {notice['title']}") 
            flash(f"Notice has been {status_text.lower()}.", "success")
            
        cursor.close(); conn.close()
    except Exception as e:
        flash(f"Error: {str(e)}", "danger")
        
    return redirect(url_for('manage_notices'))

@app.route('/admin/report_center')
@login_required
def admin_report_center():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
    
    return render_template('report_center.html')

@app.route('/employee/dashboard')
@login_required
def employee_dashboard():
    if session.get('role') != 'employee':
        return redirect(url_for('login'))
    
    user_id = session.get('id')
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    
    search = request.args.get('search', '')
    
    # Existing Tasks
    query = """
        SELECT t.*, p.title as proj_name 
        FROM tasks t 
        JOIN projects p ON t.project_id = p.id 
        WHERE t.assigned_to_user_id = %s 
    """
    params = [user_id]
    
    if search:
        query += " AND t.title LIKE %s "
        params.append(f'%{search}%')
        
    query += """
        ORDER BY 
            CASE WHEN t.verification_status = 'Verified' THEN 1 ELSE 0 END ASC,
            t.deadline ASC,
            FIELD(t.priority, 'High', 'Medium', 'Low') ASC
    """
    cursor.execute(query, tuple(params))
    my_tasks = cursor.fetchall()

    today = date.today()
    for task in my_tasks:
        if task['deadline']:
            delta = task['deadline'] - today
            if delta.days < 0:
                task['time_left'] = "Overdue"
            elif delta.days == 0:
                task['time_left'] = "Due Today"
            else:
                task['time_left'] = f"{delta.days} Days Left"
        else:
            task['time_left'] = "No Deadline"

    # --- NEW: Fetch Personal To-Do List ---
    cursor.execute("SELECT * FROM employee_todos WHERE user_id = %s ORDER BY created_at DESC", (user_id,))
    my_todos = cursor.fetchall()

    cursor.execute("SELECT COUNT(*) as count FROM tasks WHERE assigned_to_user_id = %s AND status != 'Completed'", (user_id,))
    pending_count = cursor.fetchone()['count']
    
    cursor.execute("SELECT * FROM notices WHERE is_active = TRUE ORDER BY created_at DESC LIMIT 1")
    latest_notice = cursor.fetchone()
    
    if latest_notice:
        cursor.execute("SELECT id FROM notice_reads WHERE notice_id = %s AND user_id = %s", (latest_notice['id'], user_id))
        if cursor.fetchone():
            latest_notice['has_acknowledged'] = True
        else:
            latest_notice['has_acknowledged'] = False
            
    cursor.close(); conn.close()
    return render_template('employee_dash.html', tasks=my_tasks, pending_count=pending_count, 
                           notice=latest_notice, todos=my_todos, search=search)

# --- NEW: To-Do List Module Routes ---
@app.route('/employee/add_todo', methods=['POST'])
@login_required
def add_todo():
    task_name = request.form.get('task_name')
    if task_name:
        conn = get_db(); cursor = conn.cursor()
        cursor.execute("SELECT id FROM employee_todos WHERE user_id = %s AND task_name = %s", (session['id'], task_name))
        if cursor.fetchone():
            flash("You have already added this task to your to-do list!", "warning")
        else:
            cursor.execute("INSERT INTO employee_todos (user_id, task_name) VALUES (%s, %s)", (session['id'], task_name))
            conn.commit()
            flash("Personal task added!", "success")
        cursor.close(); conn.close()
    return redirect(url_for('employee_dashboard'))

@app.route('/employee/acknowledge_notice/<int:id>')
@login_required
def acknowledge_notice(id):
    if session.get('role') != 'employee':
        return redirect(url_for('login'))
    conn = get_db(); cursor = conn.cursor()
    try:
        cursor.execute("INSERT IGNORE INTO notice_reads (notice_id, user_id) VALUES (%s, %s)", (id, session['id']))
        conn.commit()
        flash("Notice acknowledged successfully.", "success")
    except Exception as e:
        flash(f"Error: {e}", "danger")
    finally:
        cursor.close(); conn.close()
    return redirect(url_for('employee_dashboard'))

@app.route('/employee/toggle_todo/<int:id>')
@login_required
def toggle_todo(id):
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT is_completed FROM employee_todos WHERE id = %s AND user_id = %s", (id, session['id']))
    todo = cursor.fetchone()
    if todo:
        new_status = not todo['is_completed']
        cursor.execute("UPDATE employee_todos SET is_completed = %s WHERE id = %s", (new_status, id))
        conn.commit()
    cursor.close(); conn.close()
    return redirect(url_for('employee_dashboard'))

@app.route('/employee/delete_todo/<int:id>')
@login_required
def delete_todo(id):
    conn = get_db(); cursor = conn.cursor()
    cursor.execute("DELETE FROM employee_todos WHERE id = %s AND user_id = %s", (id, session['id']))
    conn.commit(); cursor.close(); conn.close()
    flash("Task removed from your list.", "info")
    return redirect(url_for('employee_dashboard'))

@app.route('/employee/update_status/<int:id>', methods=['POST'])
@login_required
def update_task_status(id):
    new_status = request.form.get('status')
    conn = get_db(); cursor = conn.cursor()
    cursor.execute("UPDATE tasks SET status=%s WHERE id=%s AND assigned_to_user_id=%s", (new_status, id, session.get('id')))
    conn.commit(); cursor.close(); conn.close()
    flash(f"Status updated!", "success")
    return redirect(url_for('employee_dashboard'))

@app.route('/employee/profile', methods=['GET', 'POST'])
@login_required
def employee_profile():
    if session.get('role') != 'employee':
        return redirect(url_for('login'))
    
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        designation = request.form.get('designation')
        file = request.files.get('profile_pic')
        
        if file and allowed_file(file.filename):
            ext = file.filename.rsplit('.', 1)[1].lower()
            filename = f"user_{session['id']}.{ext}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            cursor.execute("UPDATE users SET profile_pic = %s WHERE id = %s", (filename, session['id']))
            session['profile_pic'] = filename 

        cursor.execute("UPDATE users SET name = %s, email = %s, designation = %s WHERE id = %s", (name, email, designation, session['id']))
        conn.commit()
        session['name'] = name
        flash("Profile updated successfully!", "success")
        return redirect(url_for('employee_profile'))

    cursor.execute("SELECT * FROM users WHERE id = %s", (session['id'],))
    user = cursor.fetchone()
    cursor.close(); conn.close()
    return render_template('employee_profile.html', user=user)

@app.route('/employee/submit_task/<int:id>', methods=['POST'])
@login_required
def submit_task(id):
    remark = request.form.get('remark')
    
    if 'task_file' not in request.files:
        flash("No file selected", "warning")
        return redirect(url_for('employee_dashboard'))
    
    file = request.files['task_file']
    
    if file and file.filename != '':
        ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'dat'
        filename = f"task_{id}_user_{session['id']}.{ext}"
        file.save(os.path.join(app.config['SUBMISSION_FOLDER'], filename))
        
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE tasks 
                SET submission_file = %s, remarks = %s, status = 'Completed', verification_status = 'Pending Review'
                WHERE id = %s AND assigned_to_user_id = %s
            """, (filename, remark, id, session['id']))
            conn.commit()
            cursor.close(); conn.close()
            flash("Task submitted successfully with your remarks!", "success")
        except Exception as e:
            flash(f"Database error: {str(e)}", "danger")
    else:
        flash("Invalid file. Please try again.", "danger")
        
    return redirect(url_for('employee_dashboard'))

@app.route('/employee/change_password', methods=['POST'])
@login_required
def change_password():
    current_pwd = request.form.get('current_password')
    new_pwd = request.form.get('new_password')
    confirm_pwd = request.form.get('confirm_password')

    if new_pwd != confirm_pwd:
        flash("New passwords do not match!", "danger")
        return redirect(url_for('employee_profile'))

    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT password_hash FROM users WHERE id = %s", (session['id'],))
        user = cursor.fetchone()

        if user and user['password_hash'] == current_pwd:
            cursor.execute("UPDATE users SET password_hash = %s WHERE id = %s", (new_pwd, session['id']))
            conn.commit()
            flash("Password updated successfully!", "success")
        else:
            flash("Current password is incorrect.", "danger")
        
        cursor.close(); conn.close()
    except Exception as e:
        flash(f"Error: {str(e)}", "danger")

    return redirect(url_for('employee_profile'))

@app.route('/api/chat', methods=['POST'])
@login_required
def api_chat():
    data = request.get_json()
    message = data.get('message', '').lower()
    role = session.get('role')
    user_id = session.get('id')
    
    reply = "I'm sorry, I didn't understand that. Could you try rephrasing? Try asking about 'pending tasks' or 'projects'."
    
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        
        if role == 'admin':
            if 'employee count' in message or 'how many employees' in message or 'all employees' in message:
                cursor.execute("SELECT COUNT(*) as count FROM users WHERE role='employee'")
                count = cursor.fetchone()['count']
                reply = f"There are currently <strong>{count}</strong> employees registered in the system."
            
            elif 'project status' in message or 'how many projects' in message or 'active projects' in message:
                cursor.execute("SELECT status, COUNT(*) as count FROM projects GROUP BY status")
                projects = cursor.fetchall()
                if projects:
                    reply = "Here is the current project status summary:<br><ul>"
                    for p in projects:
                        reply += f"<li>{p['status']}: <strong>{p['count']}</strong></li>"
                    reply += "</ul>"
                else:
                    reply = "There are no projects currently."
                    
            elif 'pending tasks' in message or 'tasks pending' in message:
                cursor.execute("SELECT COUNT(*) as count FROM tasks WHERE status='Pending'")
                count = cursor.fetchone()['count']
                reply = f"There are <strong>{count}</strong> pending tasks across all projects."
                
            elif 'hello' in message or 'hi' in message:
                reply = f"Hello Admin {session.get('name')}! How can I assist you today? You can ask about employee counts, project status, or pending tasks."
                
        elif role == 'employee':
            if 'my tasks' in message or 'pending tasks' in message or 'what are my tasks' in message:
                cursor.execute("""
                    SELECT title, deadline, priority 
                    FROM tasks 
                    WHERE assigned_to_user_id=%s AND status != 'Completed' 
                    ORDER BY deadline ASC LIMIT 5
                """, (user_id,))
                tasks = cursor.fetchall()
                if tasks:
                    reply = "Here are your upcoming pending tasks:<br><ul>"
                    for t in tasks:
                        color = 'red' if t['priority'] == 'High' else ('orange' if t['priority'] == 'Medium' else 'green')
                        reply += f"<li><strong>{t['title']}</strong> (Due: {t['deadline']}, <span style='color:{color}'>{t['priority']}</span>)</li>"
                    reply += "</ul>"
                else:
                    reply = "You don't have any pending tasks right now. Great job!"
                    
            elif 'my projects' in message or 'what projects' in message:
                cursor.execute("""
                    SELECT DISTINCT p.title, p.deadline 
                    FROM projects p
                    JOIN tasks t ON p.id = t.project_id
                    WHERE t.assigned_to_user_id=%s
                """, (user_id,))
                projects = cursor.fetchall()
                if projects:
                    reply = "You are currently assigned tasks in these projects:<br><ul>"
                    for p in projects:
                        reply += f"<li><strong>{p['title']}</strong> (Project Deadline: {p['deadline']})</li>"
                    reply += "</ul>"
                else:
                    reply = "You are not currently assigned to any projects."
                    
            elif 'hello' in message or 'hi' in message:
                reply = f"Hello {session.get('name')}! I can help you check your tasks or projects. What do you need?"

        cursor.close()
        conn.close()
    except Exception as e:
        reply = "Sorry, there was an error processing your request."
        print(f"Chatbot Error: {str(e)}")
        
    return jsonify({'reply': reply})

if __name__ == '__main__':
    app.run(debug=True)