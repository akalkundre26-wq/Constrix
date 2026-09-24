from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
# Ollama connection ke liye
import requests
import json
import random
import string
from werkzeug.security import generate_password_hash, check_password_hash

from project_backend import project_bp, setup_project_database

app = Flask(
    __name__,
    template_folder="fronted",
    static_folder="CSS",
    static_url_path="/CSS"
)

app.secret_key = "constrix-secret-key"

app.register_blueprint(project_bp)

DATABASE = "constrix.db"


# ---------------- DATABASE CONNECTION ----------------

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------- CREATE DATABASE TABLES ----------------

def create_tables():

    conn = get_db_connection()

    # Contractor / Company Table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS contractors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT NOT NULL,
            contractor_code TEXT UNIQUE NOT NULL
        )
    """)

    # User Table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contractor_id INTEGER,
            full_name TEXT NOT NULL,
            email TEXT,
            username TEXT UNIQUE NOT NULL,
            mobile TEXT,
            password TEXT NOT NULL,
            role TEXT NOT NULL,

            FOREIGN KEY (contractor_id)
            REFERENCES contractors(id)
        )
    """)

        # Projects Table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contractor_id INTEGER NOT NULL,
            project_name TEXT NOT NULL,
            customer_name TEXT NOT NULL,
            site_address TEXT,
            start_date TEXT,
            end_date TEXT,
            progress INTEGER DEFAULT 0,
            status TEXT DEFAULT 'Ongoing',

            FOREIGN KEY (contractor_id)
            REFERENCES contractors(id)
        )
    """)

    # Activity Log Table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS activity_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contractor_id INTEGER NOT NULL,
            activity TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (contractor_id)
            REFERENCES contractors(id)
        )
    """)

    # Labor Project Assignment Table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS labor_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            labor_id INTEGER NOT NULL,
            project_id INTEGER NOT NULL,
            task TEXT NOT NULL,
            work_details TEXT,
            start_date TEXT,
            due_date TEXT,
            status TEXT DEFAULT 'Pending',

            FOREIGN KEY (labor_id)
            REFERENCES users(id),

            FOREIGN KEY (project_id)
            REFERENCES projects(id)
        )
    """)

    # Attendance Table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            labor_id INTEGER NOT NULL,
            project_id INTEGER NOT NULL,
            attendance_date TEXT NOT NULL,
            status TEXT NOT NULL,
            overtime_hours INTEGER DEFAULT 0,

            FOREIGN KEY (labor_id)
            REFERENCES users(id),

            FOREIGN KEY (project_id)
            REFERENCES projects(id)
        )
    """)
    # Labor Salary Rate Table
    conn.execute("""
    CREATE TABLE IF NOT EXISTS labor_salary (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        labor_id INTEGER UNIQUE NOT NULL,
        daily_rate REAL DEFAULT 0,
        ot_rate REAL DEFAULT 0,

        FOREIGN KEY (labor_id)
        REFERENCES users(id)
    )
""")

        # =====================================================
    # LABOR ADVANCE TABLE
    # Stores advance money given to labor.
    # salary_month tells which month's salary
    # this advance will be deducted from.
    # Example: 2026-09 = September 2026
    # =====================================================

    conn.execute("""
        CREATE TABLE IF NOT EXISTS labor_advances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            labor_id INTEGER NOT NULL,
            salary_month TEXT NOT NULL,
            amount REAL NOT NULL,
            advance_date TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (labor_id)
            REFERENCES users(id)
        )
    """)


    # =====================================================
    # LABOR SALARY PAYMENT TABLE
    # Stores salary payments made by Admin.
    # Supports partial/multiple payments.
    # Example:
    # Net Salary = 15000
    # First Payment = 13000
    # Second Payment = 2000
    # =====================================================

    conn.execute("""
        CREATE TABLE IF NOT EXISTS labor_salary_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            labor_id INTEGER NOT NULL,
            salary_month TEXT NOT NULL,
            amount REAL NOT NULL,
            payment_date TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (labor_id)
            REFERENCES users(id)
        )
    """)

    # =====================================================
# CUSTOMER QUERIES TABLE
# Stores customer questions and Admin replies
# =====================================================

    conn.execute("""
    CREATE TABLE IF NOT EXISTS customer_queries (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        customer_id INTEGER NOT NULL,

        project_id INTEGER,

        message TEXT NOT NULL,

        admin_reply TEXT,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        FOREIGN KEY (customer_id) REFERENCES users(id),

        FOREIGN KEY (project_id) REFERENCES projects(id)
    )
""")
    # =====================================================
    # SUBCONTRACTOR PERMISSIONS
    # Existing labor ko extra access dene ke liye
    # =====================================================

    user_columns = conn.execute(
        "PRAGMA table_info(users)"
    ).fetchall()

    column_names = [
        column["name"]
        for column in user_columns
    ]

    if "project_access" not in column_names:
        conn.execute("""
            ALTER TABLE users
            ADD COLUMN project_access INTEGER DEFAULT 0
        """)

    if "material_access" not in column_names:
        conn.execute("""
            ALTER TABLE users
            ADD COLUMN material_access INTEGER DEFAULT 0
        """)
    conn.commit()
    conn.close()

#=========================================
#Labour asign work
#=========================================
@app.route("/admin/labor/<int:labor_id>/assign-work",
           methods=["GET", "POST"])
def assign_work(labor_id):

    if "user_id" not in session:
        return redirect(url_for("admin_login"))

    contractor_id = session["contractor_id"]

    conn = get_db_connection()

    labor = conn.execute(
        """
        SELECT *
        FROM users
        WHERE id = ?
        AND contractor_id = ?
        AND role = 'labor'
        """,
        (labor_id, contractor_id)
    ).fetchone()

    projects = conn.execute(
        """
        SELECT *
        FROM projects
        WHERE contractor_id = ?
        ORDER BY id DESC
        """,
        (contractor_id,)
    ).fetchall()

    if request.method == "POST":

        project_id = request.form["project_id"]
        task = request.form["task"]
        work_details = request.form["work_details"]
        start_date = request.form["start_date"]
        due_date = request.form["due_date"]

        conn.execute(
            """
            INSERT INTO labor_projects
            (
                labor_id,
                project_id,
                task,
                work_details,
                start_date,
                due_date,
                status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                labor_id,
                project_id,
                task,
                work_details,
                start_date,
                due_date,
                "Pending"
            )
        )

        conn.commit()
        conn.close()

        flash("Work assigned successfully.")

        return redirect(url_for("labor"))

    conn.close()

    return render_template(
        "assign_work.html",
        labor=labor,
        projects=projects
    )

# ---------------- CONTRACTOR CODE ----------------

def generate_contractor_code(company_name):

    name = company_name.lower().replace(" ", "")

    number = random.randint(100, 999)

    return name[:8] + str(number)


# ---------------- HOME ----------------

@app.route("/")
def home():

    return render_template("home.html")


# ---------------- ROLE LOGIN PAGE ----------------

@app.route("/login")
def login():

    return render_template("login.html")


# =====================================================
# ADMIN REGISTER
# =====================================================

@app.route("/admin/register", methods=["GET", "POST"])
def admin_register():

    if request.method == "POST":

        full_name = request.form["full_name"]
        company_name = request.form["company_name"]
        email = request.form["email"]
        username = request.form["username"]
        password = request.form["password"]

        conn = get_db_connection()

        # Check username
        existing_user = conn.execute(
            "SELECT * FROM users WHERE username = ?",
            (username,)
        ).fetchone()

        if existing_user:

            conn.close()

            flash("Username already exists.")

            return redirect(url_for("admin_register"))

        # Create contractor code
        contractor_code = generate_contractor_code(company_name)

        # Save company
        cursor = conn.execute(
            """
            INSERT INTO contractors
            (company_name, contractor_code)

            VALUES (?, ?)
            """,
            (company_name, contractor_code)
        )

        contractor_id = cursor.lastrowid

        # Encrypt password
        hashed_password = generate_password_hash(password)

        # Save admin
        conn.execute(
            """
            INSERT INTO users
            (
                contractor_id,
                full_name,
                email,
                username,
                password,
                role
            )

            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                contractor_id,
                full_name,
                email,
                username,
                hashed_password,
                "admin"
            )
        )

        conn.commit()
        print("ADMIN REGISTERED")
        print("EMAIL SAVED:", email)
        print("USERNAME SAVED:", username)
        print("CONTRACTOR ID:", contractor_id)

        conn.close()

        flash(
            "Registration successful. Your Contractor Code is: "
            + contractor_code
        )

        return redirect(url_for("admin_login"))

    return render_template("admin_registern.html")


# =====================================================
# ADMIN LOGIN
# =====================================================

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        print("EMAIL ENTERED:", email)

        conn = get_db_connection()

        user = conn.execute(
            """
            SELECT users.*, contractors.company_name,
            contractors.contractor_code
            FROM users
            JOIN contractors
            ON users.contractor_id = contractors.id
            WHERE users.email = ?
            AND users.role = 'admin'
            """,
            (email,)
        ).fetchone()

        conn.close()

        if user:
            print("USER FOUND")
            print("DB EMAIL:", user["email"])

            if check_password_hash(user["password"], password):
                print("PASSWORD CORRECT")

                session["user_id"] = user["id"]
                session["contractor_id"] = user["contractor_id"]
                session["full_name"] = user["full_name"]
                session["company_name"] = user["company_name"]
                session["contractor_code"] = user["contractor_code"]
                session["role"] = "admin"

                print("GOING TO DASHBOARD")

                return redirect(url_for("admin_dashboard"))

            else:
                print("PASSWORD WRONG")

        else:
            print("EMAIL NOT FOUND")

        flash("Invalid email or password.")

    return render_template("admin.html")


# =====================================================
# ADMIN DASHBOARD
# =====================================================

@app.route("/admin/dashboard")
def admin_dashboard():

    if "user_id" not in session:
        return redirect(url_for("admin_login"))

    contractor_id = session["contractor_id"]

    conn = get_db_connection()

    # Total Projects
    total_projects = conn.execute(
        """
        SELECT COUNT(*) AS total
        FROM projects
        WHERE contractor_id = ?
        """,
        (contractor_id,)
    ).fetchone()["total"]

    # Ongoing Projects
    ongoing_projects = conn.execute(
        """
        SELECT COUNT(*) AS total
        FROM projects
        WHERE contractor_id = ?
        AND status = 'Ongoing'
        """,
        (contractor_id,)
    ).fetchone()["total"]

    # Total Labor
    total_labor = conn.execute(
        """
        SELECT COUNT(*) AS total
        FROM users
        WHERE contractor_id = ?
        AND role = 'labor'
        """,
        (contractor_id,)
    ).fetchone()["total"]

    # Total Customers
    total_customers = conn.execute(
        """
        SELECT COUNT(*) AS total
        FROM users
        WHERE contractor_id = ?
        AND role = 'customer'
        """,
        (contractor_id,)
    ).fetchone()["total"]

     # Recent Projects
    recent_projects = conn.execute("""
        SELECT p.*,
        CASE WHEN COUNT(w.id) = 0 THEN 0
        ELSE ROUND(100.0 * SUM(w.status = 'Completed') / COUNT(w.id))
        END AS ai_progress
        FROM projects p
        LEFT JOIN work_plan_tasks w ON p.id = w.project_id
        WHERE p.contractor_id = ?
        GROUP BY p.id
        ORDER BY p.id DESC
        LIMIT 5
    """, (contractor_id,)).fetchall()
    # Recent Activity
    recent_activity = conn.execute(
        """
        SELECT *
        FROM activity_logs
        WHERE contractor_id = ?
        ORDER BY id DESC
        LIMIT 5
        """,
        (contractor_id,)
    ).fetchall()

    conn.close()

    return render_template(
        "admin_Dashboard.html",
        total_projects=total_projects,
        ongoing_projects=ongoing_projects,
        total_labor=total_labor,
        total_customers=total_customers,
        recent_projects=recent_projects,
        recent_activity=recent_activity
    )





# =====================================================
# CUSTOMERS
# =====================================================

@app.route("/admin/customers")
def customers():

    if "user_id" not in session:
        return redirect(url_for("admin_login"))

    contractor_id = session["contractor_id"]

    conn = get_db_connection()

    customers = conn.execute(
        """
        SELECT *
        FROM users
        WHERE contractor_id = ?
        AND role = 'customer'
        ORDER BY id DESC
        """,
        (contractor_id,)
    ).fetchall()

    conn.close()

    return render_template(
        "costomer.html",
        customers=customers
    )

# =====================================================
# ADMIN - CUSTOMER DETAILS & MESSAGE REPLY
# Shows customer profile, project, questions
# and allows Admin to send reply
# =====================================================

@app.route(
    "/admin/customer/<int:customer_id>",
    methods=["GET", "POST"]
)
def admin_customer_details(customer_id):

    # Check Admin Login
    if "user_id" not in session:
        return redirect(url_for("admin_login"))

    if session.get("role") != "admin":
        return redirect(url_for("home"))

    contractor_id = session["contractor_id"]

    conn = get_db_connection()


    # =================================================
    # GET CUSTOMER DETAILS
    # =================================================

    customer = conn.execute(
        """
        SELECT *
        FROM users
        WHERE id = ?
        AND contractor_id = ?
        AND role = 'customer'
        """,
        (
            customer_id,
            contractor_id
        )
    ).fetchone()


    # Customer not found
    if customer is None:

        conn.close()

        flash("Customer not found.")

        return redirect(
            url_for("customers")
        )


    # =================================================
    # GET CUSTOMER PROJECT
    # =================================================

    project = conn.execute(
        """
        SELECT *
        FROM projects
        WHERE contractor_id = ?
        AND customer_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (
            contractor_id,
            customer_id
        )
    ).fetchone()


     # =================================================
    # ADMIN SEND REPLY
    # Saves Admin reply in customer_queries table
    # =================================================

    if request.method == "POST":

        query_id = request.form.get("query_id")
        admin_reply = request.form.get(
            "admin_reply",
            ""
        ).strip()

        if query_id and admin_reply:

            conn.execute(
                """
                UPDATE customer_queries
                SET admin_reply = ?
                WHERE id = ?
                AND customer_id = ?
                """,
                (
                    admin_reply,
                    query_id,
                    customer_id
                )
            )

            conn.commit()

            print("REPLY SAVED")
            print("QUERY ID:", query_id)
            print("REPLY:", admin_reply)

            flash("Reply sent successfully.")

        conn.close()

        return redirect(
            url_for(
                "admin_customer_details",
                customer_id=customer_id
            )
        )
    # =================================================
    # GET CUSTOMER QUESTIONS
    # =================================================

    queries = conn.execute(
        """
        SELECT *
        FROM customer_queries
        WHERE customer_id = ?
        ORDER BY id DESC
        """,
        (customer_id,)
    ).fetchall()


    conn.close()


    return render_template(
        "admin_customer_details.html",
        customer=customer,
        project=project,
        queries=queries
    )
# =====================================================
# LABOR LIST - ADMIN
# =====================================================

@app.route("/admin/labor")
def labor():

    if "user_id" not in session:
        return redirect(url_for("admin_login"))

    contractor_id = session["contractor_id"]

    conn = get_db_connection()

    labors = conn.execute(
        """
        SELECT *
        FROM users
        WHERE contractor_id = ?
        AND role = 'labor'
        ORDER BY id DESC
        """,
        (contractor_id,)
    ).fetchall()

    conn.close()

    return render_template(
        "labor.html",
        labors=labors
    )

# =====================================================
# ADMIN - SUBCONTRACTOR PERMISSIONS
# Project + Material access ON/OFF
# =====================================================

@app.route(
    "/admin/labor/<int:labor_id>/permissions",
    methods=["POST"]
)
def labor_permissions(labor_id):

    if "user_id" not in session:
        return redirect(url_for("admin_login"))

    if session.get("role") != "admin":
        return redirect(url_for("home"))

    contractor_id = session["contractor_id"]

    # Checkbox checked = 1, unchecked = 0
    project_access = 1 if request.form.get("project_access") else 0
    material_access = 1 if request.form.get("material_access") else 0

    conn = get_db_connection()

    conn.execute("""
        UPDATE users
        SET project_access = ?,
            material_access = ?
        WHERE id = ?
        AND contractor_id = ?
        AND role = 'labor'
    """, (
        project_access,
        material_access,
        labor_id,
        contractor_id
    ))

    conn.commit()
    conn.close()

    flash("Subcontractor permissions updated.")

    return redirect(url_for("labor"))

# ============================================================
# FILE: app.py
# FEATURE: AI WORK PLANNER - STABLE GENERATION
#
# PURPOSE:
# - Project select karna
# - Work type identify karna
# - Common construction work ke proper ordered tasks banana
# - Requested task count handle karna
# - Unknown work ke liye Ollama AI use karna
# - Complete workflow: proper starting se proper ending tak
# - SQLite me plan save karna
#
# NOTE:
# HTML / CSS / DATABASE TABLE ko change nahi karna.
# ============================================================

@app.route("/admin/ai-planner", methods=["GET", "POST"])
def ai_planner():

    # Admin login check
    if "user_id" not in session:
        return redirect(url_for("admin_login"))

    contractor_id = session["contractor_id"]
    conn = get_db_connection()

    # Contractor ke projects
    projects = conn.execute("""
        SELECT id, project_name
        FROM projects
        WHERE contractor_id = ?
        ORDER BY id DESC
    """, (contractor_id,)).fetchall()

    generated_tasks = []
    selected_project_id = None
    work_name = ""
    error = None

    # ============================================================
    # DELETE ONE SAVED WORK PLAN
    # ============================================================

    action = request.form.get("action")

    if request.method == "POST" and action == "delete_plan":

        selected_project_id = request.form.get("project_id")
        delete_work_name = request.form.get("work_name")

        conn.execute("""
            DELETE FROM work_plan_tasks
            WHERE project_id = ?
            AND contractor_id = ?
            AND work_name = ?
        """, (
            selected_project_id,
            contractor_id,
            delete_work_name
        ))

        conn.commit()

    # ============================================================
    # UPDATE ONE SAVED WORK PLAN
    # Normal manual update only - AI/Ollama is NOT called.
    # Existing task names can be edited and one new task can be added.
    # Everything else in AI Planner remains unchanged.
    # ============================================================
    if request.method == "POST" and action == "update_plan":

        selected_project_id = request.form.get("project_id")
        old_work_name = request.form.get("old_work_name")

        # Existing tasks edit/save
        task_ids = request.form.getlist("task_id")
        task_names = request.form.getlist("task_name")

        for task_id, task_name in zip(task_ids, task_names):
            task_name = task_name.strip()

            if task_name:
                conn.execute("""
                    UPDATE work_plan_tasks
                    SET task_name = ?
                    WHERE id = ?
                    AND project_id = ?
                    AND contractor_id = ?
                    AND work_name = ?
                """, (
                    task_name,
                    task_id,
                    selected_project_id,
                    contractor_id,
                    old_work_name
                ))

        # Optional new task - plan ke end me add hoga
        new_task = request.form.get("new_task", "").strip()

        if new_task:
            conn.execute("""
                INSERT INTO work_plan_tasks
                (
                    project_id,
                    contractor_id,
                    work_name,
                    task_name,
                    status
                )
                VALUES (?, ?, ?, ?, ?)
            """, (
                selected_project_id,
                contractor_id,
                old_work_name,
                new_task,
                "Pending"
            ))

        conn.commit()


    # ========================================================
    # GENERATE PLAN
    # ========================================================
    if request.method == "POST" and action not in ["delete_plan", "update_plan"]:

        selected_project_id = request.form.get("project_id")
        work_name = request.form.get("work_name", "").strip()

        if not selected_project_id:
            error = "Please select a project."

        elif not work_name:
            error = "Please enter work."

        else:
            try:
                import re

                # ------------------------------------------------
                # REQUESTED NUMBER FIND KARO
                # Example:
                # Wall painting - 8 tasks -> 8
                # ------------------------------------------------
                number_match = re.search(r"\b(\d+)\b", work_name)

                if number_match:
                    requested_count = int(number_match.group(1))
                else:
                    requested_count = 6

                # Minimum 1 and maximum 12 tasks
                requested_count = max(1, min(requested_count, 12))

                work_lower = work_name.lower()

                # =================================================
                # CONSTRUCTION KNOWLEDGE
                # Proper practical work order
                # =================================================
                workflows = {

                    "painting": [
                        "Surface Cleaning",
                        "Crack Filling",
                        "Wall Putty",
                        "Surface Sanding",
                        "Primer Application",
                        "First Paint Coat",
                        "Second Paint Coat",
                        "Final Touch Up",
                        "Site Cleaning",
                        "Final Inspection"
                    ],

                    "plumbing": [
                        "Site Inspection",
                        "Pipe Layout",
                        "Wall Marking",
                        "Pipe Cutting",
                        "Pipe Fitting",
                        "Joint Connection",
                        "Fixture Installation",
                        "Water Connection",
                        "Leak Testing",
                        "Final Inspection"
                    ],

                    "electrical": [
                        "Site Inspection",
                        "Wiring Layout",
                        "Wall Marking",
                        "Conduit Installation",
                        "Wire Pulling",
                        "Switch Fitting",
                        "Socket Fitting",
                        "Light Installation",
                        "Electrical Testing",
                        "Final Inspection"
                    ],

                    "furniture": [
                        "Site Measurement",
                        "Design Planning",
                        "Material Selection",
                        "Material Cutting",
                        "Frame Assembly",
                        "Surface Sanding",
                        "Surface Finishing",
                        "Hardware Fitting",
                        "Final Installation",
                        "Final Inspection"
                    ],

                    "plaster": [
                        "Surface Cleaning",
                        "Wall Preparation",
                        "Level Marking",
                        "Mortar Preparation",
                        "Base Coat",
                        "Surface Leveling",
                        "Finish Coat",
                        "Final Smoothing",
                        "Curing",
                        "Final Inspection"
                    ],

                    "tiling": [
                        "Surface Cleaning",
                        "Level Checking",
                        "Tile Layout",
                        "Adhesive Preparation",
                        "Tile Installation",
                        "Tile Alignment",
                        "Tile Cutting",
                        "Joint Grouting",
                        "Surface Cleaning",
                        "Final Inspection"
                    ],

                    "waterproofing": [
                        "Surface Cleaning",
                        "Crack Repair",
                        "Surface Preparation",
                        "Primer Application",
                        "First Waterproof Coat",
                        "Second Waterproof Coat",
                        "Joint Sealing",
                        "Water Testing",
                        "Surface Cleaning",
                        "Final Inspection"
                    ]
                }

                # =================================================
                # WORK TYPE IDENTIFY KARO
                # =================================================
                selected_workflow = None

                if (
                    "paint" in work_lower
                    or "painting" in work_lower
                    or "colour" in work_lower
                    or "color" in work_lower
                ):
                    selected_workflow = workflows["painting"]

                elif (
                    "plumb" in work_lower
                    or "pipe" in work_lower
                ):
                    selected_workflow = workflows["plumbing"]

                elif (
                    "electric" in work_lower
                    or "wiring" in work_lower
                ):
                    selected_workflow = workflows["electrical"]

                elif (
                    "furniture" in work_lower
                    or "carpenter" in work_lower
                    or "woodwork" in work_lower
                ):
                    selected_workflow = workflows["furniture"]

                elif "plaster" in work_lower:
                    selected_workflow = workflows["plaster"]

                elif (
                    "tile" in work_lower
                    or "tiling" in work_lower
                ):
                    selected_workflow = workflows["tiling"]

                elif "waterproof" in work_lower:
                    selected_workflow = workflows["waterproofing"]

                # =================================================
                # KNOWN WORK
                # Existing reliable workflow
                # =================================================
                if selected_workflow:

                    # ------------------------------------------------
                    # Complete workflow maintain karna
                    #
                    # Example:
                    # 5 tasks maange to starting + middle + ending
                    # milega. Sirf first 5 cut nahi honge.
                    # ------------------------------------------------

                    if requested_count >= len(selected_workflow):

                        generated_tasks = selected_workflow

                    elif requested_count == 1:

                        generated_tasks = [
                            selected_workflow[-1]
                        ]

                    elif requested_count == 2:

                        generated_tasks = [
                            selected_workflow[0],
                            selected_workflow[-1]
                        ]

                    else:

                        # First and last task compulsory
                        generated_tasks = [
                            selected_workflow[0]
                        ]

                        # Middle me kitne tasks chahiye
                        middle_needed = requested_count - 2

                        middle_tasks = selected_workflow[1:-1]

                        # Middle workflow se evenly tasks choose karo
                        if middle_needed > 0:

                            if middle_needed == 1:
                                middle_indexes = [
                                    len(middle_tasks) // 2
                                ]

                            else:
                                middle_indexes = []

                                for i in range(middle_needed):

                                    index = round(
                                        i
                                        * (len(middle_tasks) - 1)
                                        / (middle_needed - 1)
                                    )

                                    middle_indexes.append(index)

                            for index in middle_indexes:
                                generated_tasks.append(
                                    middle_tasks[index]
                                )

                        # Proper ending compulsory
                        generated_tasks.append(
                            selected_workflow[-1]
                        )

                # =================================================
                # UNKNOWN WORK -> OLLAMA AI
                # =================================================
                else:

                    prompt = f"""
You are a construction site planner.

Work:
{work_name}

Create exactly {requested_count} short and practical construction
activities for this work.

Rules:

- Only activities related to the requested work.

- Use real construction activities.

- Correct practical work order.

- Each activity maximum 4 words.

- No duplicate activities.

- No explanations.

- No numbering.

- Never write Task Name or Activity Name.


IMPORTANT COMPLETE WORKFLOW RULES:

- Always create a COMPLETE workflow from the real starting
  activity to the real final activity.

- Generate EXACTLY {requested_count} tasks.

- Do NOT create a longer workflow and simply cut the ending
  tasks to match the requested number.

- If fewer tasks are requested, combine related middle
  activities while keeping the complete work process.

- If more tasks are requested, divide the middle work into
  more detailed practical activities.

- The FIRST task must represent the real starting activity
  of the requested construction work.

- The LAST task must represent the real completion,
  finishing, testing, cleaning or inspection stage
  appropriate for that specific work.

- All middle tasks must follow the correct practical
  construction sequence.

- Every task must be different.

- Do not repeat the same activity using different words.

- The final result must represent the COMPLETE work process,
  not an incomplete portion of the work.

- Generate EXACTLY {requested_count} tasks.


Return only valid JSON:

{{
    "tasks": [
        {{"task": "actual work activity"}}
    ]
}}
"""

                    # =================================================
                    # CALL LOCAL OLLAMA
                    # Existing model - no new download
                    # =================================================
                    response = requests.post(
                        "http://localhost:11434/api/generate",
                        json={
                            "model": "qwen2.5:0.5b",
                            "prompt": prompt,
                            "stream": False,
                            "format": "json"
                        },
                        timeout=120
                    )

                    response.raise_for_status()

                    # AI response
                    ai_text = response.json()["response"].strip()

                    parsed = json.loads(ai_text)

                    raw_tasks = []

                    # ------------------------------------------------
                    # JSON FORMAT:
                    # {"tasks": [...]}
                    # ------------------------------------------------
                    if isinstance(parsed, dict):

                        if isinstance(parsed.get("tasks"), list):
                            raw_tasks = parsed["tasks"]

                    # Also support direct list
                    elif isinstance(parsed, list):

                        raw_tasks = parsed

                    clean_tasks = []

                    # =================================================
                    # CLEAN AI TASKS
                    # =================================================
                    for item in raw_tasks:

                        if isinstance(item, dict):

                            task_name = str(
                                item.get("task", "")
                            ).strip()

                        else:

                            task_name = str(item).strip()

                        # Remove accidental numbering
                        # Example:
                        # 1. Site Cleaning -> Site Cleaning
                        task_name = re.sub(
                            r"^\s*\d+[\.\)\-:]*\s*",
                            "",
                            task_name
                        )

                        # Extra spaces remove
                        task_name = " ".join(
                            task_name.split()
                        )

                        lower_name = task_name.lower()

                        # ------------------------------------------------
                        # BAD PLACEHOLDER REJECT
                        # ------------------------------------------------
                        if (
                            not task_name
                            or "task name" in lower_name
                            or "activity name" in lower_name
                        ):
                            continue

                        # ------------------------------------------------
                        # DUPLICATE REJECT
                        # ------------------------------------------------
                        if lower_name not in [
                            x.lower()
                            for x in clean_tasks
                        ]:
                            clean_tasks.append(task_name)

                    # Exact requested count
                    generated_tasks = clean_tasks[:requested_count]

                    # ------------------------------------------------
                    # Invalid AI result database me save nahi hoga
                    # ------------------------------------------------
                    if len(generated_tasks) < requested_count:

                        raise ValueError(
                            "AI could not generate the complete "
                            f"{requested_count}-task work plan. "
                            "Please Generate Plan again."
                        )

                # =================================================
                # DATABASE SAVE
                # =================================================
                for task_name in generated_tasks:

                    conn.execute("""
                        INSERT INTO work_plan_tasks
                        (
                            project_id,
                            contractor_id,
                            work_name,
                            task_name,
                            status
                        )
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        selected_project_id,
                        contractor_id,
                        work_name,
                        task_name,
                        "Pending"
                    ))

                conn.commit()

            # =====================================================
            # ERRORS
            # =====================================================
            except requests.exceptions.ConnectionError:

                error = "Ollama is not running."

            except requests.exceptions.Timeout:

                error = "AI response took too long."

            except json.JSONDecodeError:

                error = "AI returned invalid data."

            except Exception as e:

                error = str(e)
       
    # ============================================================
    # SAVED WORK PLANS + AUTOMATIC PROGRESS
    # Same AI Planner page par saved plans show karne ke liye.
    # Existing generation code/prompt above is unchanged.
    # ============================================================
    saved_plans = {}
    progress = 0

    if selected_project_id:
        saved_tasks = conn.execute("""
            SELECT id, work_name, task_name, status
            FROM work_plan_tasks
            WHERE project_id = ?
            AND contractor_id = ?
            ORDER BY id ASC
        """, (
            selected_project_id,
            contractor_id
        )).fetchall()

        for task in saved_tasks:
            work = task["work_name"]

            if work not in saved_plans:
                saved_plans[work] = []

            saved_plans[work].append(task)

        total_tasks = len(saved_tasks)

        completed_tasks = sum(
            1 for task in saved_tasks
            if task["status"] == "Completed"
        )

        if total_tasks > 0:
            progress = round(
                (completed_tasks / total_tasks) * 100
            )

    # ============================================================
    # CLOSE DATABASE
    # ============================================================
    conn.close()

    # ============================================================
    # OPEN AI PLANNER PAGE
    # ============================================================
    return render_template(
        "ai_planner.html",
        projects=projects,
        generated_tasks=generated_tasks,
        selected_project_id=selected_project_id,
        work_name=work_name,
        error=error,
        saved_plans=saved_plans,
        progress=progress
    )

# =====================================================
# LABOR LOGIN
# =====================================================
# =====================================================
# LABOR LOGIN
# =====================================================

@app.route("/labor/login", methods=["GET", "POST"])
def labor_login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]
        contractor_code = request.form["contractor_code"]

        conn = get_db_connection()

        labor = conn.execute(
            """
            SELECT users.*, contractors.contractor_code
            FROM users
            JOIN contractors
            ON users.contractor_id = contractors.id
            WHERE users.username = ?
            AND contractors.contractor_code = ?
            AND users.role = 'labor'
            """,
            (username, contractor_code)
        ).fetchone()

        conn.close()

        if labor and check_password_hash(labor["password"], password):

            session["user_id"] = labor["id"]
            session["contractor_id"] = labor["contractor_id"]
            session["full_name"] = labor["full_name"]
            session["role"] = "labor"

               # Contractor code
            session["contractor_code"] = labor["contractor_code"]

            return redirect(url_for("labor_dashboard"))

        flash("Invalid username, password or contractor code.")

    return render_template("labor_login.html")

# =====================================================
# LABOR REGISTER
# =====================================================

@app.route("/labor/register", methods=["GET", "POST"])
def labor_register():

    if request.method == "POST":

        full_name = request.form["full_name"]
        mobile = request.form["mobile"]
        username = request.form["username"]
        password = request.form["password"]
        contractor_code = request.form["contractor_code"]

        conn = get_db_connection()

        # Find contractor using contractor code
        contractor = conn.execute(
            """
            SELECT *
            FROM contractors
            WHERE contractor_code = ?
            """,
            (contractor_code,)
        ).fetchone()

        if contractor is None:
            conn.close()
            flash("Invalid Contractor Code.")
            return redirect(url_for("labor_register"))

        # Check username
        existing_user = conn.execute(
            """
            SELECT *
            FROM users
            WHERE username = ?
            """,
            (username,)
        ).fetchone()

        if existing_user:
            conn.close()
            flash("Username already exists.")
            return redirect(url_for("labor_register"))

        hashed_password = generate_password_hash(password)

        conn.execute(
            """
            INSERT INTO users
            (
                contractor_id,
                full_name,
                username,
                mobile,
                password,
                role
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                contractor["id"],
                full_name,
                username,
                mobile,
                hashed_password,
                "labor"
            )
        )

        conn.commit()
        conn.close()

        flash("Labor registered successfully.")

        return redirect(url_for("labor_login"))

    return render_template("labor_register.html")
# =====================================================
# LABOR DASHBOARD
# =====================================================

@app.route("/labor/dashboard")
def labor_dashboard():

    if "user_id" not in session:
        return redirect(url_for("labor_login"))

    if session.get("role") != "labor":
        return redirect(url_for("labor_login"))

    labor_id = session["user_id"]

    conn = get_db_connection()

    company = conn.execute("""
        SELECT company_name
        FROM contractors
        WHERE id = ?
    """, (session["contractor_id"],)).fetchone()

    

    # =====================================================
    # ASSIGNED WORK + AI PROJECT PROGRESS
    # =====================================================

    assigned_works = conn.execute(
        """
        SELECT
            labor_projects.*,
            projects.project_name,
            projects.site_address,

            CASE
                WHEN COUNT(work_plan_tasks.id) = 0 THEN 0
                ELSE ROUND(
                    100.0 *
                    SUM(
                        CASE
                            WHEN work_plan_tasks.status = 'Completed'
                            THEN 1
                            ELSE 0
                        END
                    )
                    / COUNT(work_plan_tasks.id)
                )
            END AS ai_progress

        FROM labor_projects

        JOIN projects
        ON labor_projects.project_id = projects.id

        LEFT JOIN work_plan_tasks
        ON projects.id = work_plan_tasks.project_id
        AND projects.contractor_id = work_plan_tasks.contractor_id

        WHERE labor_projects.labor_id = ?

        GROUP BY labor_projects.id

        ORDER BY labor_projects.id DESC
        """,
        (labor_id,)
    ).fetchall()


    # =====================================================
    # LABOR / SUBCONTRACTOR PERMISSIONS
    # =====================================================

    labor = conn.execute(
        """
        SELECT project_access, material_access
        FROM users
        WHERE id = ?
        AND role = 'labor'
        """,
        (labor_id,)
    ).fetchone()

    conn.close()

    return render_template(
        "labor_dashboard.html",
        assigned_works=assigned_works,
        labor=labor,
        company=company
    )


@app.route("/labor/work/<int:work_id>/update-status", methods=["POST"])
def update_work_status(work_id):

    if "user_id" not in session:
        return redirect(url_for("labor_login"))

    if session.get("role") != "labor":
        return redirect(url_for("labor_login"))

    labor_id = session["user_id"]
    new_status = request.form["status"]

    conn = get_db_connection()

    work = conn.execute(
        """
        SELECT *
        FROM labor_projects
        WHERE id = ?
        AND labor_id = ?
        """,
        (work_id, labor_id)
    ).fetchone()

    if work is None:
        conn.close()
        flash("Work not found.")
        return redirect(url_for("labor_dashboard"))

    conn.execute(
        """
        UPDATE labor_projects
        SET status = ?
        WHERE id = ?
        AND labor_id = ?
        """,
        (
            new_status,
            work_id,
            labor_id
        )
    )


    conn.commit()


    conn.close()

    return redirect(url_for("labor_dashboard"))

# =============================================
# LABOR - MY ATTENDANCE CALENDAR
# =============================================

@app.route("/labor/my-attendance")
def labor_my_attendance():

    if "user_id" not in session:
        return redirect(url_for("labor_login"))

    if session.get("role") != "labor":
        return redirect(url_for("home"))

    from datetime import datetime
    import calendar

    labor_id = session["user_id"]

    conn = get_db_connection()

    labor = conn.execute(
        """
        SELECT *
        FROM users
        WHERE id = ?
        AND role = 'labor'
        """,
        (labor_id,)
    ).fetchone()

    if labor is None:
        conn.close()
        return redirect(url_for("labor_login"))

    # Selected month
    selected_month = request.args.get("month")

    if not selected_month:
        selected_month = datetime.now().strftime("%Y-%m")

    year, month = map(int, selected_month.split("-"))

    # Get selected month attendance
    attendance = conn.execute(
        """
        SELECT
            attendance.*,
            projects.project_name
        FROM attendance

        JOIN projects
        ON attendance.project_id = projects.id

        WHERE attendance.labor_id = ?
        AND attendance.attendance_date LIKE ?

        ORDER BY attendance.attendance_date
        """,
        (
            labor_id,
            selected_month + "%"
        )
    ).fetchall()

    conn.close()

    # Convert attendance into day dictionary
    attendance_map = {}

    for record in attendance:
        day = int(record["attendance_date"][8:10])
        attendance_map[day] = record

    # Create month calendar
    cal = calendar.Calendar(firstweekday=0)

    weeks = cal.monthdayscalendar(
        year,
        month
    )

    # Summary
    present_count = 0
    absent_count = 0
    half_count = 0
    off_count = 0
    ot_count = 0

    for record in attendance:

        if record["status"] == "Present":
            present_count += 1

        elif record["status"] == "Absent":
            absent_count += 1

        elif record["status"] == "Half Day":
            half_count += 1

        elif record["status"] == "Weekly Off":
            off_count += 1

        ot_count += int(record["overtime_hours"] or 0)

    month_name = datetime(
        year,
        month,
        1
    ).strftime("%B %Y")

    return render_template(
        "labor_my_attendance.html",
         labor=labor,
    attendance=attendance,
    weeks=weeks,
    attendance_map=attendance_map,
    selected_month=selected_month,
    month_name=month_name,
    present_count=present_count,
    absent_count=absent_count,
    half_count=half_count,
    off_count=off_count,
    ot_count=ot_count
    )

# =====================================================
# LABOR - MY SALARY
# File: app.py
#
# Labor can VIEW:
# - Month-wise attendance salary
# - Gross salary
# - Advance and advance history
# - Net payable salary
# - Salary payments
# - Remaining salary
# - Payment status
#
# Labor cannot add/edit any payment here.
# =====================================================

@app.route("/labor/my-salary")
def labor_my_salary():

    # Check labor login
    if "user_id" not in session:
        return redirect(url_for("labor_login"))

    if session.get("role") != "labor":
        return redirect(url_for("home"))

    from datetime import datetime

    labor_id = session["user_id"]


    # =================================================
    # SELECT MONTH
    # Default = current month
    # =================================================

    selected_month = request.args.get("month")

    if not selected_month:
        selected_month = datetime.now().strftime("%Y-%m")


    conn = get_db_connection()


    # =================================================
    # GET LABOR DETAILS
    # =================================================

    labor = conn.execute(
        """
        SELECT *
        FROM users
        WHERE id = ?
        AND role = 'labor'
        """,
        (labor_id,)
    ).fetchone()


    if labor is None:
        conn.close()
        return redirect(url_for("labor_login"))


    # =================================================
    # GET SALARY RATE SET BY ADMIN
    # =================================================

    salary_rate = conn.execute(
        """
        SELECT *
        FROM labor_salary
        WHERE labor_id = ?
        """,
        (labor_id,)
    ).fetchone()


    daily_rate = 0
    ot_rate = 0


    if salary_rate:

        daily_rate = float(
            salary_rate["daily_rate"]
        )

        ot_rate = float(
            salary_rate["ot_rate"]
        )


    # =================================================
    # GET SELECTED MONTH ATTENDANCE
    # =================================================

    attendance = conn.execute(
        """
        SELECT *
        FROM attendance
        WHERE labor_id = ?
        AND attendance_date LIKE ?
        """,
        (
            labor_id,
            selected_month + "%"
        )
    ).fetchall()


    present_days = 0
    half_days = 0
    absent_days = 0
    ot_hours = 0


    for record in attendance:

        if record["status"] == "Present":
            present_days += 1

        elif record["status"] == "Half Day":
            half_days += 1

        elif record["status"] == "Absent":
            absent_days += 1

        ot_hours += int(
            record["overtime_hours"] or 0
        )


    # =================================================
    # SALARY CALCULATION
    # =================================================

    present_salary = (
        present_days * daily_rate
    )

    half_salary = (
        half_days * (daily_rate / 2)
    )

    overtime_salary = (
        ot_hours * ot_rate
    )


    # Salary before advance deduction
    gross_salary = (
        present_salary
        + half_salary
        + overtime_salary
    )


    # =================================================
    # GET ADVANCE HISTORY FOR SELECTED MONTH
    # =================================================

    advances = conn.execute(
        """
        SELECT *
        FROM labor_advances
        WHERE labor_id = ?
        AND salary_month = ?
        ORDER BY advance_date DESC, id DESC
        """,
        (
            labor_id,
            selected_month
        )
    ).fetchall()


    total_advance = 0


    for advance in advances:

        total_advance += float(
            advance["amount"]
        )


    # =================================================
    # NET SALARY AFTER ADVANCE
    #
    # Example:
    # Gross Salary = 20000
    # Advance = 5000
    # Net Payable = 15000
    # =================================================

    net_salary = (
        gross_salary
        - total_advance
    )


    if net_salary < 0:
        net_salary = 0


    # =================================================
    # GET SALARY PAYMENT HISTORY
    # =================================================

    payments = conn.execute(
        """
        SELECT *
        FROM labor_salary_payments
        WHERE labor_id = ?
        AND salary_month = ?
        ORDER BY payment_date DESC, id DESC
        """,
        (
            labor_id,
            selected_month
        )
    ).fetchall()


    total_paid = 0


    for payment in payments:

        total_paid += float(
            payment["amount"]
        )


    # =================================================
    # REMAINING SALARY
    #
    # Example:
    # Net Payable = 15000
    # Paid = 13000
    # Remaining = 2000
    # =================================================

    remaining_salary = (
        net_salary
        - total_paid
    )


    if remaining_salary < 0:
        remaining_salary = 0


    # =================================================
    # PAYMENT STATUS
    # =================================================

    if net_salary <= 0:

        payment_status = "No Salary"

    elif remaining_salary == 0:

        payment_status = "Paid"

    elif total_paid > 0:

        payment_status = "Partially Paid"

    else:

        payment_status = "Pending"


    # Month name example: September 2026
    month_name = datetime.strptime(
        selected_month,
        "%Y-%m"
    ).strftime("%B %Y")


    conn.close()


    # =================================================
    # SEND DATA TO LABOR MY SALARY PAGE
    # =================================================

    return render_template(
        "labor_my_salary.html",

        labor=labor,

        selected_month=selected_month,
        month_name=month_name,

        daily_rate=daily_rate,
        ot_rate=ot_rate,

        present_days=present_days,
        half_days=half_days,
        absent_days=absent_days,
        ot_hours=ot_hours,

        present_salary=present_salary,
        half_salary=half_salary,
        overtime_salary=overtime_salary,

        gross_salary=gross_salary,

        advances=advances,
        total_advance=total_advance,

        net_salary=net_salary,

        payments=payments,
        total_paid=total_paid,

        remaining_salary=remaining_salary,

        payment_status=payment_status
    )
#=============================================
# Labor Attendance
#=============================================

@app.route("/admin/attendance", methods=["GET", "POST"])
def admin_attendance():

    if "user_id" not in session:
        return redirect(url_for("admin_login"))

    contractor_id = session["contractor_id"]
    conn = get_db_connection()

    # Contractor ke projects
    projects = conn.execute(
        """
        SELECT *
        FROM projects
        WHERE contractor_id = ?
        ORDER BY project_name
        """,
        (contractor_id,)
    ).fetchall()

    # Selected project
    selected_project_id = request.args.get("project_id")

    if request.method == "POST":
        selected_project_id = request.form["project_id"]

    # Starting me labor empty rahega
    labors = []

    # Project select hone ke baad sirf us project ke labor
    if selected_project_id:

        labors = conn.execute(
            """
            SELECT DISTINCT users.*
            FROM users

            JOIN labor_projects
            ON users.id = labor_projects.labor_id

            JOIN projects
            ON labor_projects.project_id = projects.id

            WHERE labor_projects.project_id = ?
            AND users.contractor_id = ?
            AND projects.contractor_id = ?
            AND users.role = 'labor'

            ORDER BY users.full_name
            """,
            (
                selected_project_id,
                contractor_id,
                contractor_id
            )
        ).fetchall()

    # Save attendance
    if request.method == "POST":

        attendance_date = request.form["attendance_date"]
        project_id = request.form["project_id"]

        for labor in labors:

            labor_id = labor["id"]

            status = request.form.get(
                f"status_{labor_id}"
            )

            overtime_hours = request.form.get(
                f"ot_{labor_id}",
                0
            )

            existing = conn.execute(
                """
                SELECT id
                FROM attendance
                WHERE labor_id = ?
                AND project_id = ?
                AND attendance_date = ?
                """,
                (
                    labor_id,
                    project_id,
                    attendance_date
                )
            ).fetchone()

            if existing:

                conn.execute(
                    """
                    UPDATE attendance
                    SET status = ?,
                        overtime_hours = ?
                    WHERE id = ?
                    """,
                    (
                        status,
                        overtime_hours,
                        existing["id"]
                    )
                )

            else:

                conn.execute(
                    """
                    INSERT INTO attendance
                    (
                        labor_id,
                        project_id,
                        attendance_date,
                        status,
                        overtime_hours
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        labor_id,
                        project_id,
                        attendance_date,
                        status,
                        overtime_hours
                    )
                )

        conn.commit()
        conn.close()

        flash("Attendance saved successfully.")

        return redirect(
            url_for(
                "admin_attendance",
                project_id=project_id
            )
        )

    conn.close()

    return render_template(
        "admin_attendance.html",
        labors=labors,
        projects=projects,
        selected_project_id=selected_project_id
    )

# =============================================
# INDIVIDUAL LABOR ATTENDANCE CALENDAR
# =============================================

@app.route("/admin/labor/<int:labor_id>/attendance")
def labor_attendance(labor_id):

    if "user_id" not in session:
        return redirect(url_for("admin_login"))

    from datetime import datetime
    import calendar

    contractor_id = session["contractor_id"]

    conn = get_db_connection()

    # Labor details
    labor = conn.execute(
        """
        SELECT *
        FROM users
        WHERE id = ?
        AND contractor_id = ?
        AND role = 'labor'
        """,
        (labor_id, contractor_id)
    ).fetchone()

    if labor is None:
        conn.close()
        flash("Labor not found.")
        return redirect(url_for("labor"))

    # Selected month
    selected_month = request.args.get("month")

    if not selected_month:
        selected_month = datetime.now().strftime("%Y-%m")

    year, month = map(
        int,
        selected_month.split("-")
    )

    # Get only selected month's attendance
    attendance = conn.execute(
        """
        SELECT
            attendance.*,
            projects.project_name
        FROM attendance

        JOIN projects
        ON attendance.project_id = projects.id

        WHERE attendance.labor_id = ?
        AND attendance.attendance_date LIKE ?

        ORDER BY attendance.attendance_date
        """,
        (
            labor_id,
            selected_month + "%"
        )
    ).fetchall()

    conn.close()

    # Convert attendance into date dictionary
    attendance_map = {}

    for record in attendance:

        day = int(
            record["attendance_date"][8:10]
        )

        attendance_map[day] = record

    # Create proper month calendar
    cal = calendar.Calendar(firstweekday=0)

    weeks = cal.monthdayscalendar(
        year,
        month
    )

    # Summary
    present_count = 0
    absent_count = 0
    half_count = 0
    off_count = 0
    ot_count = 0

    for record in attendance:

        if record["status"] == "Present":
            present_count += 1

        elif record["status"] == "Absent":
            absent_count += 1

        elif record["status"] == "Half Day":
            half_count += 1

        elif record["status"] == "Weekly Off":
            off_count += 1

        ot_count += int(
            record["overtime_hours"] or 0
        )

    month_name = datetime(
        year,
        month,
        1
    ).strftime("%B %Y")

    return render_template(
        "labor_attendance.html",
        labor=labor,
        weeks=weeks,
        attendance_map=attendance_map,
        selected_month=selected_month,
        month_name=month_name,
        present_count=present_count,
        absent_count=absent_count,
        half_count=half_count,
        off_count=off_count,
        ot_count=ot_count
    )
# =====================================================
# ADMIN - LABOR MONTHLY SALARY
# Handles:
# 1. Salary rate
# 2. Advance payment
# 3. Salary payment
# 4. Remaining salary calculation
# =====================================================

@app.route("/admin/labor/<int:labor_id>/salary",
           methods=["GET", "POST"])
def labor_salary(labor_id):

    if "user_id" not in session:
        return redirect(url_for("admin_login"))

    if session.get("role") != "admin":
        return redirect(url_for("home"))

    from datetime import datetime

    contractor_id = session["contractor_id"]
    conn = get_db_connection()

    # =================================================
    # GET LABOR DETAILS
    # =================================================

    labor = conn.execute(
        """
        SELECT *
        FROM users
        WHERE id = ?
        AND contractor_id = ?
        AND role = 'labor'
        """,
        (
            labor_id,
            contractor_id
        )
    ).fetchone()

    if labor is None:
        conn.close()
        flash("Labor not found.")
        return redirect(url_for("labor"))


    # =================================================
    # SELECT MONTH
    # Example: 2026-09
    # =================================================

    selected_month = request.args.get("month")

    if not selected_month:
        selected_month = datetime.now().strftime("%Y-%m")


    # =================================================
    # HANDLE ADMIN FORMS
    # Different forms use action_type
    # =================================================

    if request.method == "POST":

        action_type = request.form.get("action_type")


        # =================================================
        # SAVE SALARY RATE
        # =================================================

        if action_type == "save_rate":

            daily_rate = request.form.get(
                "daily_rate",
                0
            )

            ot_rate = request.form.get(
                "ot_rate",
                0
            )

            existing_rate = conn.execute(
                """
                SELECT id
                FROM labor_salary
                WHERE labor_id = ?
                """,
                (labor_id,)
            ).fetchone()

            if existing_rate:

                conn.execute(
                    """
                    UPDATE labor_salary
                    SET daily_rate = ?,
                        ot_rate = ?
                    WHERE labor_id = ?
                    """,
                    (
                        daily_rate,
                        ot_rate,
                        labor_id
                    )
                )

            else:

                conn.execute(
                    """
                    INSERT INTO labor_salary
                    (
                        labor_id,
                        daily_rate,
                        ot_rate
                    )
                    VALUES (?, ?, ?)
                    """,
                    (
                        labor_id,
                        daily_rate,
                        ot_rate
                    )
                )

            conn.commit()

            flash("Salary rate saved successfully.")


        # =================================================
        # ADD ADVANCE
        # Advance is deducted from selected month's salary
        # =================================================

        elif action_type == "add_advance":

            advance_amount = float(
                request.form.get(
                    "advance_amount",
                    0
                )
            )

            advance_date = request.form.get(
                "advance_date"
            )

            if advance_amount > 0 and advance_date:

                conn.execute(
                    """
                    INSERT INTO labor_advances
                    (
                        labor_id,
                        salary_month,
                        amount,
                        advance_date
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        labor_id,
                        selected_month,
                        advance_amount,
                        advance_date
                    )
                )

                conn.commit()

                flash("Advance added successfully.")


        # =================================================
        # ADD SALARY PAYMENT
        # Supports partial and multiple salary payments
        # =================================================

        elif action_type == "add_payment":

            payment_amount = float(
                request.form.get(
                    "payment_amount",
                    0
                )
            )

            payment_date = request.form.get(
                "payment_date"
            )

            if payment_amount > 0 and payment_date:

                conn.execute(
                    """
                    INSERT INTO labor_salary_payments
                    (
                        labor_id,
                        salary_month,
                        amount,
                        payment_date
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        labor_id,
                        selected_month,
                        payment_amount,
                        payment_date
                    )
                )

                conn.commit()

                flash("Salary payment added successfully.")


        return redirect(
            url_for(
                "labor_salary",
                labor_id=labor_id,
                month=selected_month
            )
        )


    # =================================================
    # GET SALARY RATE
    # =================================================

    salary_rate = conn.execute(
        """
        SELECT *
        FROM labor_salary
        WHERE labor_id = ?
        """,
        (labor_id,)
    ).fetchone()

    daily_rate = 0
    ot_rate = 0

    if salary_rate:

        daily_rate = float(
            salary_rate["daily_rate"]
        )

        ot_rate = float(
            salary_rate["ot_rate"]
        )


    # =================================================
    # GET SELECTED MONTH ATTENDANCE
    # =================================================

    attendance = conn.execute(
        """
        SELECT *
        FROM attendance
        WHERE labor_id = ?
        AND attendance_date LIKE ?
        """,
        (
            labor_id,
            selected_month + "%"
        )
    ).fetchall()


    present_days = 0
    half_days = 0
    absent_days = 0
    ot_hours = 0

    for record in attendance:

        if record["status"] == "Present":
            present_days += 1

        elif record["status"] == "Half Day":
            half_days += 1

        elif record["status"] == "Absent":
            absent_days += 1

        ot_hours += int(
            record["overtime_hours"] or 0
        )


    # =================================================
    # GROSS SALARY CALCULATION
    # =================================================

    present_salary = (
        present_days * daily_rate
    )

    half_salary = (
        half_days * (daily_rate / 2)
    )

    overtime_salary = (
        ot_hours * ot_rate
    )

    gross_salary = (
        present_salary
        + half_salary
        + overtime_salary
    )


    # =================================================
    # GET ADVANCE HISTORY
    # =================================================

    advances = conn.execute(
        """
        SELECT *
        FROM labor_advances
        WHERE labor_id = ?
        AND salary_month = ?
        ORDER BY advance_date DESC, id DESC
        """,
        (
            labor_id,
            selected_month
        )
    ).fetchall()


    total_advance = 0

    for advance in advances:

        total_advance += float(
            advance["amount"]
        )


    # =================================================
    # NET PAYABLE AFTER ADVANCE
    # =================================================

    net_salary = (
        gross_salary
        - total_advance
    )

    if net_salary < 0:
        net_salary = 0


    # =================================================
    # GET SALARY PAYMENT HISTORY
    # =================================================

    payments = conn.execute(
        """
        SELECT *
        FROM labor_salary_payments
        WHERE labor_id = ?
        AND salary_month = ?
        ORDER BY payment_date DESC, id DESC
        """,
        (
            labor_id,
            selected_month
        )
    ).fetchall()


    total_paid = 0

    for payment in payments:

        total_paid += float(
            payment["amount"]
        )


    # =================================================
    # REMAINING SALARY
    # =================================================

    remaining_salary = (
        net_salary
        - total_paid
    )

    if remaining_salary < 0:
        remaining_salary = 0


    # =================================================
    # PAYMENT STATUS
    # =================================================

    if net_salary <= 0:

        payment_status = "No Salary"

    elif remaining_salary == 0:

        payment_status = "Paid"

    elif total_paid > 0:

        payment_status = "Partially Paid"

    else:

        payment_status = "Pending"


    month_name = datetime.strptime(
        selected_month,
        "%Y-%m"
    ).strftime("%B %Y")


    conn.close()


    # =================================================
    # SEND ALL DATA TO ADMIN SALARY HTML
    # =================================================

    return render_template(
        "labor_salary.html",

        labor=labor,

        selected_month=selected_month,
        month_name=month_name,

        daily_rate=daily_rate,
        ot_rate=ot_rate,

        present_days=present_days,
        half_days=half_days,
        absent_days=absent_days,
        ot_hours=ot_hours,

        present_salary=present_salary,
        half_salary=half_salary,
        overtime_salary=overtime_salary,

        gross_salary=gross_salary,

        advances=advances,
        total_advance=total_advance,

        net_salary=net_salary,

        payments=payments,
        total_paid=total_paid,

        remaining_salary=remaining_salary,

        payment_status=payment_status
    )
# =====================================================
# CUSTOMER LOGIN
# =====================================================

@app.route("/customer/login", methods=["GET", "POST"])
def customer_login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]
        contractor_code = request.form["contractor_code"]

        conn = get_db_connection()

        customer = conn.execute(
            """
            SELECT
                users.*,
                contractors.contractor_code
            FROM users

            JOIN contractors
            ON users.contractor_id = contractors.id

            WHERE users.username = ?
            AND contractors.contractor_code = ?
            AND users.role = 'customer'
            """,
            (
                username,
                contractor_code
            )
        ).fetchone()

        conn.close()

        if customer and check_password_hash(
            customer["password"],
            password
        ):

            session["user_id"] = customer["id"]
            session["contractor_id"] = customer["contractor_id"]
            session["full_name"] = customer["full_name"]
            session["role"] = "customer"

            return redirect(
                url_for("customer_dashboard")
            )

        flash(
            "Invalid username, password or contractor code."
        )

    return render_template(
        "customer_login.html"
    )


# =====================================================
# CUSTOMER DASHBOARD
# Shows customer project and handles customer questions
# =====================================================

@app.route("/customer/dashboard", methods=["GET", "POST"])
def customer_dashboard():

    # Check customer login
    if "user_id" not in session:
        return redirect(url_for("customer_login"))

    if session.get("role") != "customer":
        return redirect(url_for("home"))


    customer_id = session["user_id"]
    contractor_id = session["contractor_id"]
    customer_name = session["full_name"]

    conn = get_db_connection()


    # =================================================
    # GET CUSTOMER DETAILS
    # =================================================

    customer = conn.execute(
        """
        SELECT *
        FROM users
        WHERE id = ?
        AND role = 'customer'
        """,
        (customer_id,)
    ).fetchone()


    # =================================================
    # GET CUSTOMER ASSIGNED PROJECT
    # =================================================

    project = conn.execute(
        """
        SELECT *
        FROM projects
        WHERE contractor_id = ?
        AND customer_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (
            contractor_id,
            customer_id
        )
    ).fetchone()


    # =================================================
    # CUSTOMER SEND QUESTION
    # =================================================

    if request.method == "POST":

        message = request.form["message"].strip()

        if message:

            project_id = None

            if project:
                project_id = project["id"]


            # Save question in database
            conn.execute(
                """
                INSERT INTO customer_queries
                (
                    customer_id,
                    project_id,
                    message
                )
                VALUES (?, ?, ?)
                """,
                (
                    customer_id,
                    project_id,
                    message
                )
            )


            # Save in Admin Recent Activity
            conn.execute(
                """
                INSERT INTO activity_logs
                (
                    contractor_id,
                    activity
                )
                VALUES (?, ?)
                """,
                (
                    contractor_id,
                    "New message from " + customer_name
                )
            )


            conn.commit()

            flash("Question sent successfully.")

            conn.close()

            return redirect(
                url_for("customer_dashboard")
            )


    # =================================================
    # LOAD PREVIOUS CUSTOMER QUESTIONS
    # =================================================

    queries = conn.execute(
        """
        SELECT *
        FROM customer_queries
        WHERE customer_id = ?
        ORDER BY id DESC
        """,
        (customer_id,)
    ).fetchall()


    # =================================================
    # CUSTOMER DASHBOARD AUTOMATIC PROJECT PROGRESS
    # =================================================

    ai_progress = 0

    if project:

        work_plan_rows = conn.execute("""
            SELECT status
            FROM work_plan_tasks
            WHERE project_id = ?
            AND contractor_id = ?
        """, (
            project["id"],
            contractor_id
        )).fetchall()

        total_tasks = len(work_plan_rows)

        completed_tasks = sum(
            1 for task in work_plan_rows
            if task["status"] == "Completed"
        )

        if total_tasks > 0:
            ai_progress = round(
                (completed_tasks / total_tasks) * 100
            )


    conn.close()

    return render_template(
        "customer_dashboard.html",
        customer=customer,
        project=project,
        queries=queries,
        ai_progress=ai_progress
    )

# =====================================================
# CUSTOMER - MY PROJECT
# Shows project details + daily updates + photos
# =====================================================

@app.route("/customer/project")
def customer_project():

    if "user_id" not in session:
        return redirect(url_for("customer_login"))

    if session.get("role") != "customer":
        return redirect(url_for("home"))

    customer_id = session["user_id"]
    contractor_id = session["contractor_id"]

    conn = get_db_connection()

    # Customer details
    customer = conn.execute(
        """
        SELECT *
        FROM users
        WHERE id = ?
        AND role = 'customer'
        """,
        (customer_id,)
    ).fetchone()


    # Customer project
    project = conn.execute(
        """
        SELECT *
        FROM projects
        WHERE contractor_id = ?
        AND customer_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (
            contractor_id,
            customer_id
        )
    ).fetchone()


    # Daily updates with photos
    updates = []

    if project:

        update_rows = conn.execute(
            """
            SELECT *
            FROM project_updates
            WHERE project_id = ?
            ORDER BY update_date DESC, id DESC
            """,
            (project["id"],)
        ).fetchall()

        for update in update_rows:

            photos = conn.execute(
                """
                SELECT *
                FROM project_update_photos
                WHERE update_id = ?
                ORDER BY id ASC
                """,
                (update["id"],)
            ).fetchall()

            updates.append({
                "update": update,
                "photos": photos
            })

            
    # =====================================================
    # CUSTOMER AI WORK PLAN + AUTOMATIC PROGRESS
    # Read only for customer
    # =====================================================

    work_plan_rows = conn.execute("""
        SELECT id, work_name, task_name, status
        FROM work_plan_tasks
        WHERE project_id = ?
        AND contractor_id = ?
        ORDER BY id ASC
    """, (
        project["id"],
        project["contractor_id"]
    )).fetchall()


    # Group tasks by work name
    work_plans = {}

    for task in work_plan_rows:

        work_name = task["work_name"]

        if work_name not in work_plans:
            work_plans[work_name] = []

        work_plans[work_name].append(task)


    # Calculate automatic progress
    total_tasks = len(work_plan_rows)

    completed_tasks = sum(
        1 for task in work_plan_rows
        if task["status"] == "Completed"
    )

    if total_tasks > 0:
        ai_progress = round(
            (completed_tasks / total_tasks) * 100
        )
    else:
        ai_progress = 0


    # Close database
    conn.close()


    # Open customer project page
    return render_template(
        "customer_project.html",
        customer=customer,
        project=project,
        updates=updates,
        work_plans=work_plans,
        ai_progress=ai_progress
    )
#================
#Customer registrtaion
#==========
# =====================================================
# CUSTOMER REGISTER
# =====================================================

@app.route("/customer/register", methods=["GET", "POST"])
def customer_register():

    if request.method == "POST":

        full_name = request.form["full_name"]
        email = request.form["email"]
        username = request.form["username"]
        mobile = request.form["mobile"]
        password = request.form["password"]
        contractor_code = request.form["contractor_code"]

        conn = get_db_connection()

        # Find contractor using code
        contractor = conn.execute(
            """
            SELECT *
            FROM contractors
            WHERE contractor_code = ?
            """,
            (contractor_code,)
        ).fetchone()

        if contractor is None:
            conn.close()
            flash("Invalid Contractor Code.")
            return redirect(
                url_for("customer_register")
            )

        # Check username
        existing_user = conn.execute(
            """
            SELECT *
            FROM users
            WHERE username = ?
            """,
            (username,)
        ).fetchone()

        if existing_user:
            conn.close()
            flash("Username already exists.")
            return redirect(
                url_for("customer_register")
            )

        hashed_password = generate_password_hash(
            password
        )

        conn.execute(
            """
            INSERT INTO users
            (
                contractor_id,
                full_name,
                email,
                username,
                mobile,
                password,
                role
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                contractor["id"],
                full_name,
                email,
                username,
                mobile,
                hashed_password,
                "customer"
            )
        )

        conn.commit()
        conn.close()

        flash("Customer registered successfully.")

        return redirect(
            url_for("customer_login")
        )

    return render_template(
        "customer_register.html"
    )
# ---------------- LOGOUT ----------------

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("home")
    )



# ---------------- START APP ----------------

# ---------------- START APP ----------------

if __name__ == "__main__":

    create_tables()

    setup_project_database()

    app.run(host="0.0.0.0", port=5000, debug=True)