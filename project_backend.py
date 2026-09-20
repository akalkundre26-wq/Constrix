from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    send_from_directory
)

import sqlite3
import os

from werkzeug.utils import secure_filename


project_bp = Blueprint("project", __name__)

DATABASE = "constrix.db"

UPLOAD_FOLDER = os.path.join(
    os.path.dirname(__file__),
    "fronted",
    "images"
)


# =====================================================
# DATABASE CONNECTION
# =====================================================

def get_db_connection():

    conn = sqlite3.connect(DATABASE)

    conn.row_factory = sqlite3.Row

    return conn


# =====================================================
# PROJECT DATABASE SETUP
# =====================================================
def setup_project_database():

    conn = get_db_connection()

    # Create projects table if not available
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
            status TEXT DEFAULT 'Ongoing'
        )
    """)

    # Check existing columns
    columns = conn.execute(
        "PRAGMA table_info(projects)"
    ).fetchall()

    column_names = [
        column["name"]
        for column in columns
    ]

    # Add missing columns safely
    if "project_type" not in column_names:
        conn.execute("""
            ALTER TABLE projects
            ADD COLUMN project_type TEXT
        """)

    if "budget" not in column_names:
        conn.execute("""
            ALTER TABLE projects
            ADD COLUMN budget REAL DEFAULT 0
        """)

    if "description" not in column_names:
        conn.execute("""
            ALTER TABLE projects
            ADD COLUMN description TEXT
        """)

    if "image" not in column_names:
        conn.execute("""
            ALTER TABLE projects
            ADD COLUMN image TEXT
        """)

    if "customer_id" not in column_names:
        conn.execute("""
            ALTER TABLE projects
            ADD COLUMN customer_id INTEGER
        """)

    # Activity table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS activity_logs (

            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contractor_id INTEGER NOT NULL,
            activity TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

        # =====================================================
    # PROJECT DAILY UPDATES TABLE
    # Stores daily work update for each project
    # =====================================================

    conn.execute("""
        CREATE TABLE IF NOT EXISTS project_updates (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            project_id INTEGER NOT NULL,

            contractor_id INTEGER NOT NULL,

            update_date TEXT NOT NULL,

            work_details TEXT NOT NULL,

            progress INTEGER DEFAULT 0,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (project_id)
            REFERENCES projects(id)
        )
    """)


    # =====================================================
    # PROJECT UPDATE PHOTOS TABLE
    # Stores photos connected with a daily update
    # One update can have multiple photos
    # =====================================================

    conn.execute("""
        CREATE TABLE IF NOT EXISTS project_update_photos (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            update_id INTEGER NOT NULL,

            image TEXT NOT NULL,

            FOREIGN KEY (update_id)
            REFERENCES project_updates(id)
        )
    """)

    # =====================================================
    # MATERIALS TABLE
    # Stores current material stock for each project
    # =====================================================

    conn.execute("""
        CREATE TABLE IF NOT EXISTS materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            contractor_id INTEGER NOT NULL,
            material_name TEXT NOT NULL,
            quantity REAL DEFAULT 0,
            unit TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
    """)


    # =====================================================
    # EXPENSES TABLE
    # Stores expenses for each construction project
    # =====================================================

    conn.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            contractor_id INTEGER NOT NULL,
            expense_date TEXT NOT NULL,
            expense_name TEXT NOT NULL,
            amount REAL DEFAULT 0,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
    """)
    # =====================================================
# AI WORK PLAN TASKS TABLE
# File: project_backend.py
# Put inside setup_project_database()
# Put BEFORE the final conn.commit() and conn.close()
#
# Stores AI-generated tasks for each project.
# Admin will later change task status from Project Details.
# =====================================================

    conn.execute("""
    CREATE TABLE IF NOT EXISTS work_plan_tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        contractor_id INTEGER NOT NULL,
        work_name TEXT NOT NULL,
        task_name TEXT NOT NULL,
        status TEXT DEFAULT 'Pending',
        FOREIGN KEY (project_id) REFERENCES projects(id)
    )
""")

    # Save database changes
    conn.commit()
    conn.close()

# =====================================================
# SHOW PROJECT IMAGES
# =====================================================

@project_bp.route("/project-images/<path:filename>")
def project_image(filename):

    return send_from_directory(
        UPLOAD_FOLDER,
        filename
    )

# =====================================================
# PROJECT LIST
# Admin = All Projects
# Subcontractor = Only Assigned Projects
# =====================================================

@project_bp.route("/admin/projects")
def projects():

    if "user_id" not in session:
        return redirect(
            url_for("admin_login")
        )

    contractor_id = session["contractor_id"]
    role = session.get("role")

    conn = get_db_connection()


    # =================================================
    # ADMIN - SHOW ALL PROJECTS
    # =================================================

    if role == "admin":

               projects = conn.execute("""
            SELECT p.*,
            CASE WHEN COUNT(w.id)=0 THEN 0
            ELSE ROUND(100.0 * SUM(w.status='Completed') / COUNT(w.id))
            END AS ai_progress
            FROM projects p
            LEFT JOIN work_plan_tasks w ON p.id=w.project_id
            WHERE p.contractor_id=?
            GROUP BY p.id
            ORDER BY p.id DESC
        """, (contractor_id,)).fetchall()


    # =================================================
    # LABOR / SUBCONTRACTOR
    # Show only assigned projects when access is ON
    # =================================================

    elif role == "labor":

        labor_id = session["user_id"]

        labor = conn.execute(
            """
            SELECT project_access
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


        # No Project Permission
        if labor is None or labor["project_access"] != 1:

            conn.close()

            flash("You do not have project access.")

            return redirect(
                url_for("labor_dashboard")
            )

        projects = conn.execute("""
            SELECT p.*,
            CASE WHEN COUNT(w.id)=0 THEN 0
            ELSE ROUND(100.0 * SUM(w.status='Completed') / COUNT(w.id))
            END AS ai_progress
            FROM projects p
            JOIN labor_projects lp ON p.id=lp.project_id
            LEFT JOIN work_plan_tasks w ON p.id=w.project_id
            WHERE lp.labor_id=? AND p.contractor_id=?
            GROUP BY p.id
            ORDER BY p.id DESC
        """, (labor_id, contractor_id)).fetchall()


    else:

        conn.close()

        return redirect(
            url_for("admin_login")
        )


    conn.close()


    return render_template(
        "project.html",
        projects=projects
    )

# =====================================================
# ADD PROJECT
# =====================================================

@project_bp.route(
    "/admin/projects/add",
    methods=["GET", "POST"]
)
def add_project():

    # Check admin login
    if "user_id" not in session:
        return redirect(
            url_for("admin_login")
        )

    contractor_id = session["contractor_id"]

    # Save project when form is submitted
    if request.method == "POST":

        project_name = request.form["project_name"]
        customer_id = request.form["customer_id"]
        project_type = request.form["project_type"]
        site_address = request.form["site_address"]
        start_date = request.form["start_date"]
        end_date = request.form["end_date"]
        status = request.form["status"]
        budget = request.form["budget"]
        description = request.form["description"]

        conn = get_db_connection()

        # Get selected registered customer
        customer = conn.execute(
            """
            SELECT full_name
            FROM users
            WHERE id = ?
            AND contractor_id = ?
            AND role = 'customer'
            """,
            (customer_id, contractor_id)
        ).fetchone()

        if customer is None:
            conn.close()
            flash("Invalid customer selected.")
            return redirect(
                url_for("project.add_project")
            )

        customer_name = customer["full_name"]

        # Project image
        image_name = None

        if "image" in request.files:
            image = request.files["image"]

            if image.filename != "":
                image_name = secure_filename(
                    image.filename
                )

                image_name = (
                    str(contractor_id)
                    + "_"
                    + image_name
                )

                image.save(
                    os.path.join(
                        UPLOAD_FOLDER,
                        image_name
                    )
                )

        # Save project
        cursor = conn.execute(
            """
            INSERT INTO projects
            (
                contractor_id,
                project_name,
                customer_name,
                customer_id,
                project_type,
                site_address,
                start_date,
                end_date,
                progress,
                status,
                budget,
                description,
                image
            )
            VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                contractor_id,
                project_name,
                customer_name,
                customer_id,
                project_type,
                site_address,
                start_date,
                end_date,
                0,
                status,
                budget,
                description,
                image_name
            )
        )

        project_id = cursor.lastrowid

        # Save activity
        conn.execute(
            """
            INSERT INTO activity_logs
            (contractor_id, activity)
            VALUES (?, ?)
            """,
            (
                contractor_id,
                "New project added: " + project_name
            )
        )

        conn.commit()
        conn.close()

        flash("Project added successfully.")

        return redirect(
            url_for("project.projects")
        )

    # Load registered customers for dropdown
    conn = get_db_connection()

    customers = conn.execute(
        """
        SELECT id, full_name
        FROM users
        WHERE contractor_id = ?
        AND role = 'customer'
        ORDER BY full_name
        """,
        (contractor_id,)
    ).fetchall()

    conn.close()

    return render_template(
        "add_project.html",
        customers=customers
    )

# =====================================================
# VIEW PROJECT
# File: project_backend.py
#
# Shows:
# 1. Project details
# 2. Daily updates + photos
# 3. Material stock (READ ONLY)
# 4. Expenses + automatic total (READ ONLY)
# =====================================================

@project_bp.route("/admin/projects/<int:project_id>")
def view_project(project_id):

    # Check Admin Login
    if "user_id" not in session:
        return redirect(url_for("admin_login"))

    contractor_id = session["contractor_id"]

    conn = get_db_connection()


    # =================================================
    # GET PROJECT DETAILS
    # =================================================

    project = conn.execute("""
        SELECT *
        FROM projects
        WHERE id = ?
        AND contractor_id = ?
    """, (
        project_id,
        contractor_id
    )).fetchone()

    if project is None:
        conn.close()
        return "Project not found", 404


    # =================================================
    # GET DAILY UPDATES
    # =================================================

    updates_data = conn.execute("""
        SELECT *
        FROM project_updates
        WHERE project_id = ?
        AND contractor_id = ?
        ORDER BY update_date DESC, id DESC
    """, (
        project_id,
        contractor_id
    )).fetchall()


    # Get photos for every daily update
    updates = []

    for update in updates_data:

        photos = conn.execute("""
            SELECT *
            FROM project_update_photos
            WHERE update_id = ?
            ORDER BY id ASC
        """, (
            update["id"],
        )).fetchall()

        updates.append({
            "update": update,
            "photos": photos
        })


    # =================================================
    # GET MATERIALS
    # Only for display on Project Details page
    # =================================================

    materials = conn.execute("""
        SELECT *
        FROM materials
        WHERE project_id = ?
        AND contractor_id = ?
        ORDER BY material_name
    """, (
        project_id,
        contractor_id
    )).fetchall()


    # =================================================
    # GET EXPENSES
    # Only for display on Project Details page
    # =================================================

    expenses = conn.execute("""
        SELECT *
        FROM expenses
        WHERE project_id = ?
        AND contractor_id = ?
        ORDER BY expense_date DESC, id DESC
    """, (
        project_id,
        contractor_id
    )).fetchall()


    # =================================================
    # CALCULATE TOTAL EXPENSE AUTOMATICALLY
    # =================================================

    total_row = conn.execute("""
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM expenses
        WHERE project_id = ?
        AND contractor_id = ?
    """, (
        project_id,
        contractor_id
    )).fetchone()

    total_expense = total_row["total"]


    # =================================================
    # AI WORK PLANS + AUTOMATIC PROJECT PROGRESS
    # Progress = Completed AI Tasks / Total AI Tasks * 100
    # Existing project data is not changed.
    # =================================================

    work_plan_rows = conn.execute("""
        SELECT id, work_name, task_name, status
        FROM work_plan_tasks
        WHERE project_id = ?
        AND contractor_id = ?
        ORDER BY id ASC
    """, (
        project_id,
        contractor_id
    )).fetchall()

    work_plans = {}

    for task in work_plan_rows:
        work = task["work_name"]

        if work not in work_plans:
            work_plans[work] = []

        work_plans[work].append(task)

    total_tasks = len(work_plan_rows)

    completed_tasks = sum(
        1 for task in work_plan_rows
        if task["status"] == "Completed"
    )

    ai_progress = 0

    if total_tasks > 0:
        ai_progress = round(
            (completed_tasks / total_tasks) * 100
        )


    conn.close()


    # =================================================
    # SEND ALL DATA TO PROJECT DETAILS HTML
    # =================================================

    return render_template(
        "proejct_details.html",
        project=project,
        updates=updates,
        materials=materials,
        expenses=expenses,
        total_expense=total_expense,
        work_plans=work_plans,
        ai_progress=ai_progress
    )

# =====================================================
# EDIT PROJECT - REGISTERED CUSTOMER CONNECTION
# This code allows Admin to select a registered customer
# and connects that customer with the project.
# =====================================================

@project_bp.route(
    "/admin/projects/<int:project_id>/edit",
    methods=["GET", "POST"]
)
def edit_project(project_id):

    # Check Admin Login
    if "user_id" not in session:
        return redirect(url_for("admin_login"))

    contractor_id = session["contractor_id"]

    conn = get_db_connection()

    # Get selected project
    project = conn.execute(
        """
        SELECT *
        FROM projects
        WHERE id = ?
        AND contractor_id = ?
        """,
        (project_id, contractor_id)
    ).fetchone()

    if project is None:
        conn.close()
        return "Project not found", 404


    # =================================================
    # UPDATE PROJECT AFTER FORM SUBMIT
    # =================================================

    if request.method == "POST":

        project_name = request.form["project_name"]

        # Selected registered customer
        customer_id = request.form["customer_id"]

        project_type = request.form["project_type"]
        site_address = request.form["site_address"]
        start_date = request.form["start_date"]
        end_date = request.form["end_date"]
        status = request.form["status"]
        budget = request.form["budget"]
        description = request.form["description"]


        # Get selected customer's name
        customer = conn.execute(
            """
            SELECT id, full_name
            FROM users
            WHERE id = ?
            AND contractor_id = ?
            AND role = 'customer'
            """,
            (customer_id, contractor_id)
        ).fetchone()


        # Check customer
        if customer is None:

            conn.close()

            flash("Invalid customer selected.")

            return redirect(
                url_for(
                    "project.edit_project",
                    project_id=project_id
                )
            )


        customer_name = customer["full_name"]


        # Update project
        conn.execute(
            """
            UPDATE projects
            SET
                project_name = ?,
                customer_name = ?,
                customer_id = ?,
                project_type = ?,
                site_address = ?,
                start_date = ?,
                end_date = ?,
                status = ?,
                budget = ?,
                description = ?
            WHERE id = ?
            AND contractor_id = ?
            """,
            (
                project_name,
                customer_name,
                customer_id,
                project_type,
                site_address,
                start_date,
                end_date,
                status,
                budget,
                description,
                project_id,
                contractor_id
            )
        )


        # Save activity
        conn.execute(
            """
            INSERT INTO activity_logs
            (contractor_id, activity)
            VALUES (?, ?)
            """,
            (
                contractor_id,
                "Project updated: " + project_name
            )
        )


        conn.commit()
        conn.close()

        flash("Project updated successfully.")

        return redirect(
            url_for(
                "project.view_project",
                project_id=project_id
            )
        )


    # =================================================
    # LOAD REGISTERED CUSTOMERS FOR DROPDOWN
    # =================================================

    customers = conn.execute(
        """
        SELECT id, full_name
        FROM users
        WHERE contractor_id = ?
        AND role = 'customer'
        ORDER BY full_name
        """,
        (contractor_id,)
    ).fetchall()

    conn.close()


    return render_template(
        "edit_project.html",
        project=project,
        customers=customers
    )
# =====================================================
# DELETE PROJECT
# =====================================================

@project_bp.route(
    "/admin/projects/<int:project_id>/delete",
    methods=["POST"]
)
def delete_project(project_id):

    if "user_id" not in session:
        return redirect(url_for("admin_login"))

    contractor_id = session["contractor_id"]

    conn = get_db_connection()

    project = conn.execute(
        """
        SELECT *
        FROM projects
        WHERE id = ?
        AND contractor_id = ?
        """,
        (project_id, contractor_id)
    ).fetchone()

    if project is None:
        conn.close()
        return "Project not found", 404

    project_name = project["project_name"]

    conn.execute(
        """
        DELETE FROM projects
        WHERE id = ?
        AND contractor_id = ?
        """,
        (project_id, contractor_id)
    )

    conn.execute(
        """
        INSERT INTO activity_logs
        (contractor_id, activity)
        VALUES (?, ?)
        """,
        (
            contractor_id,
            "Project deleted: " + project_name
        )
    )

    conn.commit()
    conn.close()

    flash("Project deleted successfully.")

    return redirect(
        url_for("project.projects")
    )

# =====================================================
# ADD PROJECT DAILY UPDATE
# Saves Date + Work Done + Photos only
# =====================================================

@project_bp.route(
    "/admin/projects/<int:project_id>/add-update",
    methods=["GET", "POST"]
)
def add_project_update(project_id):

    # Check Admin Login
    if "user_id" not in session:
        return redirect(url_for("admin_login"))

    contractor_id = session["contractor_id"]

    conn = get_db_connection()

    # Get Project
    project = conn.execute(
        """
        SELECT *
        FROM projects
        WHERE id = ?
        AND contractor_id = ?
        """,
        (project_id, contractor_id)
    ).fetchone()

    if project is None:
        conn.close()
        return "Project not found", 404

    # =============================================
    # SAVE DAILY UPDATE
    # =============================================

    if request.method == "POST":

        update_date = request.form["update_date"]
        work_details = request.form["work_details"].strip()

        # Save update
        cursor = conn.execute(
            """
            INSERT INTO project_updates
            (
                project_id,
                contractor_id,
                update_date,
                work_details
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                project_id,
                contractor_id,
                update_date,
                work_details
            )
        )

        update_id = cursor.lastrowid

        # =============================================
        # SAVE PHOTOS
        # =============================================

        photos = request.files.getlist("photos")

        for photo in photos:

            if photo and photo.filename:

                filename = secure_filename(photo.filename)

                filename = (
                    "update_"
                    + str(update_id)
                    + "_"
                    + filename
                )

                photo.save(
                    os.path.join(
                        UPLOAD_FOLDER,
                        filename
                    )
                )

                conn.execute(
                    """
                    INSERT INTO project_update_photos
                    (update_id, image)
                    VALUES (?, ?)
                    """,
                    (update_id, filename)
                )

        conn.commit()
        conn.close()

        flash("Daily update saved successfully.")

        return redirect(
            url_for(
                "project.view_project",
                project_id=project_id
            )
        )

    conn.close()

    # Open Add Update page
    return render_template(
        "add_project_update.html",
        project=project
    )

# =====================================================
# EDIT DAILY UPDATE
# Admin can correct date, work details and photos
# =====================================================

@project_bp.route(
    "/admin/project-update/<int:update_id>/edit",
    methods=["GET", "POST"]
)
def edit_project_update(update_id):

    if "user_id" not in session:
        return redirect(url_for("admin_login"))

    contractor_id = session["contractor_id"]

    conn = get_db_connection()

    # Get update
    update = conn.execute(
        """
        SELECT *
        FROM project_updates
        WHERE id = ?
        AND contractor_id = ?
        """,
        (update_id, contractor_id)
    ).fetchone()

    if update is None:
        conn.close()
        return "Update not found", 404

    project_id = update["project_id"]


    # =============================================
    # SAVE CHANGES
    # =============================================

    if request.method == "POST":

        update_date = request.form["update_date"]

        work_details = request.form[
            "work_details"
        ].strip()

        conn.execute(
            """
            UPDATE project_updates
            SET update_date = ?,
                work_details = ?
            WHERE id = ?
            AND contractor_id = ?
            """,
            (
                update_date,
                work_details,
                update_id,
                contractor_id
            )
        )


        # =========================================
        # IF NEW PHOTOS SELECTED:
        # Replace old photos with new photos
        # =========================================

        photos = request.files.getlist("photos")

        new_photos = [
            photo for photo in photos
            if photo and photo.filename
        ]

        if new_photos:

            # Remove old photo records
            conn.execute(
                """
                DELETE FROM project_update_photos
                WHERE update_id = ?
                """,
                (update_id,)
            )

            # Save new photos
            for photo in new_photos:

                filename = secure_filename(
                    photo.filename
                )

                filename = (
                    "update_"
                    + str(update_id)
                    + "_"
                    + filename
                )

                photo.save(
                    os.path.join(
                        UPLOAD_FOLDER,
                        filename
                    )
                )

                conn.execute(
                    """
                    INSERT INTO project_update_photos
                    (update_id, image)
                    VALUES (?, ?)
                    """,
                    (
                        update_id,
                        filename
                    )
                )


        conn.commit()
        conn.close()

        flash("Daily update updated successfully.")

        return redirect(
            url_for(
                "project.view_project",
                project_id=project_id
            )
        )


    conn.close()

    return render_template(
        "edit_project_update.html",
        update=update
    )

# =====================================================
# MATERIAL & EXPENSES
# Admin = All Projects
# Subcontractor = Only Assigned Projects
# =====================================================

@project_bp.route("/admin/material-expenses")
def material_expenses():

    if "user_id" not in session:
        return redirect(url_for("admin_login"))

    contractor_id = session["contractor_id"]
    role = session.get("role")

    conn = get_db_connection()

    # =================================================
    # ADMIN - ALL PROJECTS
    # =================================================
    if role == "admin":

        projects = conn.execute("""
            SELECT id, project_name
            FROM projects
            WHERE contractor_id = ?
            ORDER BY project_name
        """, (contractor_id,)).fetchall()

    # =================================================
    # LABOR WITH MATERIAL PERMISSION
    # =================================================
    elif role == "labor":

        labor_id = session["user_id"]

        labor = conn.execute("""
            SELECT material_access
            FROM users
            WHERE id = ?
            AND contractor_id = ?
            AND role = 'labor'
        """, (
            labor_id,
            contractor_id
        )).fetchone()

        # Permission OFF
        if labor is None or labor["material_access"] != 1:
            conn.close()
            flash("You do not have Material & Expenses access.")
            return redirect(url_for("labor_dashboard"))

        # Only assigned projects
        projects = conn.execute("""
            SELECT DISTINCT
                projects.id,
                projects.project_name
            FROM projects

            JOIN labor_projects
            ON projects.id = labor_projects.project_id

            WHERE labor_projects.labor_id = ?
            AND projects.contractor_id = ?

            ORDER BY projects.project_name
        """, (
            labor_id,
            contractor_id
        )).fetchall()

    else:
        conn.close()
        return redirect(url_for("admin_login"))


    # Selected project
    project_id = request.args.get("project_id", type=int)

    selected_project = None
    materials = []
    expenses = []
    total_expense = 0


    if project_id:

        # Labor can open only assigned project
        if role == "labor":

            assigned = conn.execute("""
                SELECT 1
                FROM labor_projects
                WHERE labor_id = ?
                AND project_id = ?
            """, (
                session["user_id"],
                project_id
            )).fetchone()

            if assigned is None:
                conn.close()
                flash("This project is not assigned to you.")
                return redirect(
                    url_for("project.material_expenses")
                )


        selected_project = conn.execute("""
            SELECT *
            FROM projects
            WHERE id = ?
            AND contractor_id = ?
        """, (
            project_id,
            contractor_id
        )).fetchone()


        if selected_project:

            materials = conn.execute("""
                SELECT *
                FROM materials
                WHERE project_id = ?
                AND contractor_id = ?
                ORDER BY material_name
            """, (
                project_id,
                contractor_id
            )).fetchall()


            expenses = conn.execute("""
                SELECT *
                FROM expenses
                WHERE project_id = ?
                AND contractor_id = ?
                ORDER BY expense_date DESC, id DESC
            """, (
                project_id,
                contractor_id
            )).fetchall()


            total_row = conn.execute("""
                SELECT COALESCE(SUM(amount), 0) AS total
                FROM expenses
                WHERE project_id = ?
                AND contractor_id = ?
            """, (
                project_id,
                contractor_id
            )).fetchone()

            total_expense = total_row["total"]


    conn.close()

    return render_template(
        "material_expenses.html",
        projects=projects,
        selected_project=selected_project,
        materials=materials,
        expenses=expenses,
        total_expense=total_expense
    )


# =====================================================
# ADD MATERIAL
# Adds a new material with starting stock
# =====================================================

@project_bp.route(
    "/admin/material/<int:project_id>/add",
    methods=["POST"]
)
def add_material(project_id):

    if "user_id" not in session:
        return redirect(url_for("admin_login"))

    contractor_id = session["contractor_id"]

    material_name = request.form["material_name"].strip()
    quantity = request.form["quantity"]
    unit = request.form["unit"]

    conn = get_db_connection()

    conn.execute("""
        INSERT INTO materials
        (
            project_id,
            contractor_id,
            material_name,
            quantity,
            unit
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        project_id,
        contractor_id,
        material_name,
        quantity,
        unit
    ))

    conn.commit()
    conn.close()

    flash("Material added successfully.")

    return redirect(
        url_for(
            "project.material_expenses",
            project_id=project_id
        )
    )


# =====================================================
# USE MATERIAL
# Automatically subtracts used quantity from stock
# Example: 20 Bags - 4 Bags = 16 Bags
# =====================================================

@project_bp.route(
    "/admin/material/<int:material_id>/use",
    methods=["POST"]
)
def use_material(material_id):

    if "user_id" not in session:
        return redirect(url_for("admin_login"))

    contractor_id = session["contractor_id"]
    used_quantity = float(request.form["used_quantity"])

    conn = get_db_connection()

    material = conn.execute("""
        SELECT *
        FROM materials
        WHERE id = ?
        AND contractor_id = ?
    """, (material_id, contractor_id)).fetchone()

    if material is None:
        conn.close()
        return "Material not found", 404

    # Do not allow more usage than available stock
    if used_quantity <= 0:
        conn.close()
        flash("Enter a valid quantity.")

    elif used_quantity > material["quantity"]:
        conn.close()
        flash("Not enough material available.")

    else:

        new_quantity = material["quantity"] - used_quantity

        conn.execute("""
            UPDATE materials
            SET quantity = ?
            WHERE id = ?
            AND contractor_id = ?
        """, (
            new_quantity,
            material_id,
            contractor_id
        ))

        conn.commit()
        conn.close()

        flash("Material stock updated.")

    return redirect(
        url_for(
            "project.material_expenses",
            project_id=material["project_id"]
        )
    )


# =====================================================
# ADD STOCK
# Adds newly received quantity to existing material
# Example: 16 Bags + 10 Bags = 26 Bags
# =====================================================

@project_bp.route(
    "/admin/material/<int:material_id>/add-stock",
    methods=["POST"]
)
def add_material_stock(material_id):

    if "user_id" not in session:
        return redirect(url_for("admin_login"))

    contractor_id = session["contractor_id"]
    added_quantity = float(request.form["added_quantity"])

    conn = get_db_connection()

    material = conn.execute("""
        SELECT *
        FROM materials
        WHERE id = ?
        AND contractor_id = ?
    """, (material_id, contractor_id)).fetchone()

    if material is None:
        conn.close()
        return "Material not found", 404

    if added_quantity > 0:

        new_quantity = material["quantity"] + added_quantity

        conn.execute("""
            UPDATE materials
            SET quantity = ?
            WHERE id = ?
            AND contractor_id = ?
        """, (
            new_quantity,
            material_id,
            contractor_id
        ))

        conn.commit()

        flash("Stock added successfully.")

    conn.close()

    return redirect(
        url_for(
            "project.material_expenses",
            project_id=material["project_id"]
        )
    )


# =====================================================
# ADD EXPENSE
# Saves Date + Expense Name + Amount
# Total is calculated automatically on main page
# =====================================================

@project_bp.route(
    "/admin/expense/<int:project_id>/add",
    methods=["POST"]
)
def add_expense(project_id):

    if "user_id" not in session:
        return redirect(url_for("admin_login"))

    contractor_id = session["contractor_id"]

    expense_date = request.form["expense_date"]
    expense_name = request.form["expense_name"].strip()
    amount = request.form["amount"]

    conn = get_db_connection()

    conn.execute("""
        INSERT INTO expenses
        (
            project_id,
            contractor_id,
            expense_date,
            expense_name,
            amount
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        project_id,
        contractor_id,
        expense_date,
        expense_name,
        amount
    ))

    conn.commit()
    conn.close()

    flash("Expense added successfully.")

    return redirect(
        url_for(
            "project.material_expenses",
            project_id=project_id
        )
    )


# =====================================================
# UPDATE AI WORK PLAN TASK STATUS
# Pending -> In Progress -> Completed
# =====================================================

@project_bp.route(
    "/admin/projects/<int:project_id>/task/<int:task_id>/status",
    methods=["POST"]
)
def update_work_task_status(project_id, task_id):

    if "user_id" not in session:
        return redirect(url_for("admin_login"))

    contractor_id = session["contractor_id"]

    conn = get_db_connection()

    # Get task safely
    task = conn.execute("""
        SELECT *
        FROM work_plan_tasks
        WHERE id = ?
        AND project_id = ?
        AND contractor_id = ?
    """, (
        task_id,
        project_id,
        contractor_id
    )).fetchone()

    if task is None:
        conn.close()
        return "Task not found", 404

    # Change status in order
    if task["status"] == "Pending":
        new_status = "In Progress"

    elif task["status"] == "In Progress":
        new_status = "Completed"

    else:
        new_status = "Completed"

    conn.execute("""
        UPDATE work_plan_tasks
        SET status = ?
        WHERE id = ?
        AND project_id = ?
        AND contractor_id = ?
    """, (
        new_status,
        task_id,
        project_id,
        contractor_id
    ))

    conn.commit()
    conn.close()

    return redirect(
        url_for(
            "project.view_project",
            project_id=project_id
        )
    )