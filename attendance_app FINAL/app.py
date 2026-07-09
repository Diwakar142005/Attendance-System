from flask import Flask, render_template, request, redirect, session, send_from_directory
import sqlite3
import os
from werkzeug.utils import secure_filename
from openpyxl import Workbook
from datetime import date
from functools import wraps

app = Flask(__name__)
app.secret_key = "secret123"


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect("/")
        return f(*args, **kwargs)

    return decorated


def get_db():
    return sqlite3.connect("attendance.db")


# Create tables
conn = get_db()
conn.execute(
    "CREATE TABLE IF NOT EXISTS students (roll TEXT, name TEXT, branch TEXT, year TEXT, password TEXT)"
)
conn.execute("""
CREATE TABLE IF NOT EXISTS teachers (
    username TEXT,
    password TEXT,
    branch TEXT,
    year TEXT
)
""")
conn.execute("""
CREATE TABLE IF NOT EXISTS attendance (
    roll TEXT,
    name TEXT,
    date TEXT,
    status TEXT
)
""")
conn.execute("""
CREATE TABLE IF NOT EXISTS attendance_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    roll TEXT,
    name TEXT,
    request_date TEXT,
    status TEXT DEFAULT 'Pending'
)
""")
conn.execute("CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, roll TEXT, message TEXT, msg_date TEXT)")
conn.execute("""
CREATE TABLE IF NOT EXISTS notices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    message TEXT,
    poster TEXT,
    notice_date TEXT
)
""")
conn.execute("""
CREATE TABLE IF NOT EXISTS admins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    email TEXT UNIQUE,
    phone TEXT UNIQUE,
    password TEXT
)
""")
conn.commit()
conn.close()


USERS = {
    "admin": "admin123"
}


# ---------------- LOGIN ----------------

@app.route("/", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        u = request.form["username"]
        p = request.form["password"]

        conn = get_db()

        # Admin Login
        admin = conn.execute(
            """
            SELECT * FROM admins
            WHERE name=? AND password=?
            """,
            (u, p)
        ).fetchone()

        if admin:

            session["admin_id"] = admin[0]
            session["user"] = admin[1]
            session["is_admin"] = True

            conn.close()

            return redirect("/dashboard")

        # Teacher Login
        teacher = conn.execute(
            """
            SELECT * FROM teachers
            WHERE username=? AND password=?
            """,
            (u, p)
        ).fetchone()

        conn.close()

        if teacher:

            session["teacher"] = teacher[0]
            session["teacher_branch"] = teacher[2]
            session["teacher_year"] = teacher[3]

            session["admin_id"] = teacher[4]

            session["user"] = teacher[0]

            return redirect("/dashboard")

        return "Invalid Login"

    return render_template("login.html")

# ---------------- DASHBOARD ----------------

@app.route("/dashboard")
@login_required
def dashboard():

    conn = get_db()

    today_str = str(date.today())

    # Pending requests
    pending_requests = conn.execute(
        """
        SELECT COUNT(*)
        FROM attendance_requests
        WHERE status='Pending'
        """
    ).fetchone()[0]

    if session.get("teacher"):

        branch = session["teacher_branch"]
        year = session["teacher_year"]

        total_students = conn.execute(
            """
            SELECT COUNT(*)
            FROM students
            WHERE branch=? AND year=?
            """,
            (branch, year)
        ).fetchone()[0]

        present_today = conn.execute(
            """
            SELECT COUNT(*)
            FROM attendance a
            JOIN students s ON a.roll=s.roll
            WHERE a.date=?
            AND a.status='Present'
            AND s.branch=?
            AND s.year=?
            """,
            (today_str, branch, year)
        ).fetchone()[0]

        absent_today = conn.execute(
            """
            SELECT COUNT(*)
            FROM attendance a
            JOIN students s ON a.roll=s.roll
            WHERE a.date=?
            AND a.status='Absent'
            AND s.branch=?
            AND s.year=?
            """,
            (today_str, branch, year)
        ).fetchone()[0]

        total_teachers = 0

    else:

        admin_id = session["admin_id"]

        total_students = conn.execute(
            "SELECT COUNT(*) FROM students WHERE admin_id=?",
            (admin_id,)
        ).fetchone()[0]

        present_today = conn.execute(
            """
            SELECT COUNT(*)
            FROM attendance
            WHERE date=? AND status='Present' AND admin_id=?
            """,
            (today_str, admin_id)
        ).fetchone()[0]

        absent_today = conn.execute(
            """
            SELECT COUNT(*)
            FROM attendance
            WHERE date=? AND status='Absent' AND admin_id=?
            """,
            (today_str, admin_id)
        ).fetchone()[0]

        total_teachers = conn.execute(
            "SELECT COUNT(*) FROM teachers WHERE admin_id=?",
            (admin_id,)
        ).fetchone()[0]

    # Admin details
    admin_name = None

    if session.get("admin_id"):

        admin = conn.execute(
            "SELECT * FROM admins WHERE id=?",
            (session["admin_id"],)
        ).fetchone()

        if admin:
            admin_name = admin[1]

    conn.close()

    return render_template(
        "dashboard.html",
        total_students=total_students,
        total_teachers=total_teachers,
        present_today=present_today,
        absent_today=absent_today,
        pending_requests=pending_requests,
        today=today_str,
        admin_name=admin_name,
        teacher_name=session.get("teacher"),
        teacher_branch=session.get("teacher_branch"),
        teacher_year=session.get("teacher_year")
    )
# ---------------- ADD STUDENT ----------------

@app.route("/add", methods=["POST"])
@login_required
def add():

    roll = request.form["roll"]
    name = request.form["name"]
    branch = request.form["branch"]
    year = request.form["year"]
    password = request.form["password"]

    admin_id = session["admin_id"]

    conn = get_db()

    conn.execute(
        """
        INSERT INTO students
        (roll, name, branch, year, password, admin_id)
        VALUES (?,?,?,?,?,?)
        """,
        (roll, name, branch, year, password, admin_id)
    )

    conn.commit()
    conn.close()

    return redirect("/students")

@app.route("/add_teacher", methods=["POST"])
@login_required
def add_teacher():

    username = request.form["username"]
    password = request.form["password"]
    branch = request.form["branch"]
    year = request.form["year"]

    admin_id = session["admin_id"]

    conn = get_db()

    conn.execute(
        """
        INSERT INTO teachers
        (username, password, branch, year, admin_id)
        VALUES (?, ?, ?, ?, ?)
        """,
        (username, password, branch, year, admin_id)
    )

    conn.commit()
    conn.close()

    return redirect("/dashboard")
# ---------------- STUDENTS ----------------

@app.route("/students")
@login_required
def students():

    conn = get_db()

    # Teacher Login
    if session.get("teacher"):

        branch = session["teacher_branch"]
        year = session["teacher_year"]

        data = conn.execute(
            "SELECT * FROM students WHERE branch=? AND year=?",
            (branch, year)
        ).fetchall()

    # Admin Login
    else:

        admin_id = session["admin_id"]

        data = conn.execute(
            "SELECT * FROM students WHERE admin_id=?",
            (admin_id,)
        ).fetchall()

    conn.close()

    return render_template(
        "students.html",
        data=data
    )

# ---------------- MARK ATTENDANCE ----------------
@app.route("/mark", methods=["POST"])
@login_required
def mark():

    roll = request.form["roll"]
    today = str(date.today())

    conn = get_db()

    if session.get("teacher"):

        branch = session["teacher_branch"]
        year = session["teacher_year"]

        student = conn.execute(
            """
            SELECT * FROM students
            WHERE roll=? AND branch=? AND year=?
            """,
            (roll, branch, year)
        ).fetchone()

    else:

        student = conn.execute(
            "SELECT * FROM students WHERE roll=?",
            (roll,)
        ).fetchone()

    if student:

        admin_id = session.get("admin_id")

        conn.execute(
            """
            INSERT INTO attendance
            VALUES (?,?,?,?,?)
            """,
            (roll, student[1], today, "Present", admin_id)
        )

        conn.commit()

    conn.close()

    return redirect("/dashboard")

# ---------------- VIEW ATTENDANCE ----------------

@app.route("/attendance")
@login_required
def attendance():

    conn = get_db()

    if session.get("teacher"):

        branch = session["teacher_branch"]
        year = session["teacher_year"]

        data = conn.execute(
            """
            SELECT a.*
            FROM attendance a
            JOIN students s
            ON a.roll = s.roll
            WHERE s.branch=? AND s.year=?
            """,
            (branch, year)
        ).fetchall()

    else:

        admin_id = session["admin_id"]

        data = conn.execute(
            """
            SELECT *
            FROM attendance
            WHERE admin_id=?
            """,
            (admin_id,)
        ).fetchall()

    conn.close()

    return render_template(
        "attendance.html",
        data=data
    )
# ---------------- DELETE ATTENDANCE ----------------

@app.route("/delete_attendance/<roll>/<date>")
@login_required
def delete_attendance(roll, date):

    conn = get_db()

    if session.get("teacher"):

        branch = session["teacher_branch"]
        year = session["teacher_year"]

        student = conn.execute(
            """
            SELECT * FROM students
            WHERE roll=? AND branch=? AND year=?
            """,
            (roll, branch, year)
        ).fetchone()

        if not student:
            conn.close()
            return "Access Denied"

    conn.execute(
        "DELETE FROM attendance WHERE roll=? AND date=?",
        (roll, date)
    )

    conn.commit()
    conn.close()

    return redirect("/attendance")


# ---------------- STUDENT LOGIN ----------------
@app.route("/student_login", methods=["GET", "POST"])
def student_login():

    if request.method == "POST":

        roll = request.form["roll"]
        password = request.form["password"]

        conn = get_db()

        student = conn.execute(
            "SELECT * FROM students WHERE roll=? AND password=?",
            (roll, password)
        ).fetchone()

        conn.close()

        if student:
            session["student_roll"] = roll
            return redirect("/student_dashboard")
        else:
            return "Invalid Roll Number or Password"

    return render_template("student_login.html")

# ---------------- STUDENT DASHBOARD ----------------

@app.route("/student_dashboard")
def student_dashboard():

    if "student_roll" not in session:
        return redirect("/student_login")

    roll = session["student_roll"]

    conn = get_db()

    # student details
    student = conn.execute(
        "SELECT * FROM students WHERE roll=?",
        (roll,)
    ).fetchone()

    # attendance details
    attendance = conn.execute(
        "SELECT * FROM attendance WHERE roll=?",
        (roll,)
    ).fetchall()

    # notices
    notices = conn.execute(
        "SELECT * FROM notices ORDER BY id DESC"
    ).fetchall()

    conn.close()

    return render_template(
        "student_dashboard.html",
        student=student,
        attendance=attendance,
        notices=notices
    )
# ---------------- STUDENT LOGOUT ----------------

@app.route("/student_logout")
def student_logout():
    session.pop("student_roll", None)
    return redirect("/student_login")


# ---------------- ADMIN LOGOUT ----------------

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# ---------------- DELETE STUDENT ----------------

@app.route("/delete_student/<roll>", methods=["POST"])
@login_required
def delete_student(roll):

    conn = get_db()

    student = conn.execute(
        "SELECT * FROM students WHERE roll=?",
        (roll,)
    ).fetchone()

    if not student:
        conn.close()
        return redirect("/students")

    conn.execute(
        "DELETE FROM students WHERE roll=?",
        (roll,)
    )

    conn.execute(
        "DELETE FROM attendance WHERE roll=?",
        (roll,)
    )

    conn.commit()
    conn.close()

    return redirect("/students")

@app.route("/export_excel")
@login_required
def export_excel():

    conn = get_db()

    data = conn.execute(
        "SELECT * FROM attendance"
    ).fetchall()

    conn.close()

    wb = Workbook()

    ws = wb.active
    ws.title = "Attendance Report"

    ws.append([
        "Roll Number",
        "Name",
        "Date",
        "Status"
    ])

    for row in data:
        ws.append(row)

    filename = "attendance_report.xlsx"

    wb.save(filename)

    return send_file(
        filename,
        as_attachment=True
    )
@app.route("/send_request", methods=["POST"])
def send_request():

    roll = session["student_roll"]

    conn = get_db()

    student = conn.execute(
        "SELECT * FROM students WHERE roll=?",
        (roll,)
    ).fetchone()

    conn.execute(
        "INSERT INTO attendance_requests (roll,name,request_date) VALUES (?,?,?)",
        (roll, student[1], str(date.today()))
    )

    conn.commit()
    conn.close()

    return redirect("/student_dashboard")
@app.route("/requests")
@login_required
def requests():

    conn = get_db()

    if session.get("teacher"):

        branch = session["teacher_branch"]
        year = session["teacher_year"]

        data = conn.execute(
            """
            SELECT ar.*
            FROM attendance_requests ar
            JOIN students s
            ON ar.roll = s.roll
            WHERE ar.status='Pending'
            AND s.branch=?
            AND s.year=?
            """,
            (branch, year)
        ).fetchall()

    else:

        data = conn.execute(
            "SELECT * FROM attendance_requests WHERE status='Pending'"
        ).fetchall()

    conn.close()

    return render_template(
        "requests.html",
        data=data
    )
@app.route("/approve/<int:id>")
@login_required
def approve(id):

    conn = get_db()

    req = conn.execute(
        "SELECT * FROM attendance_requests WHERE id=?",
        (id,)
    ).fetchone()

    if not req:
        conn.close()
        return redirect("/requests")

    # Teacher Security Check
    if session.get("teacher"):

        branch = session["teacher_branch"]
        year = session["teacher_year"]

        student = conn.execute(
            """
            SELECT * FROM students
            WHERE roll=? AND branch=? AND year=?
            """,
            (req[1], branch, year)
        ).fetchone()

        if not student:
            conn.close()
            return "Access Denied"

    admin_id = session.get("admin_id")

    conn.execute(
        """
        INSERT INTO attendance
        (roll, name, date, status, admin_id)
        VALUES (?,?,?,?,?)
        """,
        (req[1], req[2], req[3], "Present", admin_id)
    )

    conn.execute(
        "UPDATE attendance_requests SET status='Approved' WHERE id=?",
        (id,)
    )

    conn.commit()
    conn.close()

    return redirect("/requests")
@app.route("/reject/<int:id>")
@login_required
def reject(id):

    conn = get_db()

    conn.execute(
        "UPDATE attendance_requests SET status='Rejected' WHERE id=?",
        (id,)
    )

    conn.commit()
    conn.close()

    return redirect("/requests")
@app.route("/send_message", methods=["POST"])
def send_message():

    roll = session["student_roll"]

    message = request.form["message"]

    today = str(date.today())

    conn = get_db()

    conn.execute(
        "INSERT INTO messages (roll, message, msg_date) VALUES (?,?,?)",
        (roll, message, today)
    )

    conn.commit()
    conn.close()

    return redirect("/student_dashboard")
@app.route("/messages")
@login_required
def messages():

    conn = get_db()

    if session.get("teacher"):

        branch = session["teacher_branch"]
        year = session["teacher_year"]

        data = conn.execute(
            """
            SELECT m.*
            FROM messages m
            JOIN students s
            ON m.roll = s.roll
            WHERE s.branch=? AND s.year=?
            ORDER BY m.id DESC
            """,
            (branch, year)
        ).fetchall()

    else:

        data = conn.execute(
            "SELECT * FROM messages ORDER BY id DESC"
        ).fetchall()

    conn.close()

    return render_template(
        "messages.html",
        data=data
    )
@app.route("/auto_absent")
@login_required
def auto_absent():

    today = str(date.today())

    conn = get_db()

    if session.get("teacher"):

        branch = session["teacher_branch"]
        year = session["teacher_year"]

        students = conn.execute(
            """
            SELECT * FROM students
            WHERE branch=? AND year=?
            """,
            (branch, year)
        ).fetchall()

    else:

        students = conn.execute(
            "SELECT * FROM students"
        ).fetchall()

    for student in students:

        roll = student[0]
        name = student[1]

        existing = conn.execute(
            """
            SELECT * FROM attendance
            WHERE roll=? AND date=?
            """,
            (roll, today)
        ).fetchone()

        if not existing:

            admin_id = session.get("admin_id")

            conn.execute(
                """
                INSERT INTO attendance
                (roll, name, date, status, admin_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (roll, name, today, "Absent", admin_id)
            )

    conn.commit()
    conn.close()

    return redirect("/attendance")
# ---------------- NOTICE BOARD ----------------

@app.route("/notice_board")
@login_required
def notice_board():

    conn = get_db()

    data = conn.execute(
        "SELECT * FROM notices ORDER BY id DESC"
    ).fetchall()

    conn.close()

    return render_template(
        "notice_board.html",
        data=data
    )


# ---------------- ADD NOTICE ----------------

@app.route("/add_notice", methods=["POST"])
@login_required
def add_notice():

    title = request.form["title"]

    message = request.form["message"]

    today = str(date.today())

    poster = request.files["poster"]

    filename = ""

    # upload image
    if poster and poster.filename != "":

        filename = secure_filename(
            poster.filename
        )

        upload_folder = os.path.join(
            app.root_path,
            "uploads",
            "notices"
        )

        # create folder automatically
        os.makedirs(upload_folder, exist_ok=True)

        poster.save(
            os.path.join(upload_folder, filename)
        )

    conn = get_db()

    conn.execute(
        """
        INSERT INTO notices
        (title, message, poster, notice_date)
        VALUES (?,?,?,?)
        """,
        (title, message, filename, today)
    )

    conn.commit()
    conn.close()

    return redirect("/notice_board")


# ---------------- SHOW NOTICE IMAGE ----------------

@app.route("/uploads/notices/<filename>")
def notice_image(filename):

    return send_from_directory(
        os.path.join(
            app.root_path,
            "uploads",
            "notices"
        ),
        filename
    )

@app.route("/delete_notice/<int:id>", methods=["POST"])
@login_required
def delete_notice(id):

    conn = get_db()

    # get notice details
    notice = conn.execute(
        "SELECT * FROM notices WHERE id=?",
        (id,)
    ).fetchone()

    # delete image file
    if notice:

        poster = notice[3]

        if poster:

            image_path = os.path.join(
                app.root_path,
                "uploads",
                "notices",
                poster
            )

            # remove image from folder
            if os.path.exists(image_path):
                os.remove(image_path)

    # delete notice from database
    conn.execute(
        "DELETE FROM notices WHERE id=?",
        (id,)
    )

    conn.commit()
    conn.close()

    return redirect("/notice_board")
@app.route("/change_password", methods=["POST"])
def change_password():

    roll = session["student_roll"]

    current_password = request.form["current_password"]
    new_password = request.form["new_password"]

    conn = get_db()

    student = conn.execute(
        "SELECT * FROM students WHERE roll=? AND password=?",
        (roll, current_password)
    ).fetchone()

    if student:

        conn.execute(
            "UPDATE students SET password=? WHERE roll=?",
            (new_password, roll)
        )

        conn.commit()
        conn.close()

        return "Password Changed Successfully"

    conn.close()

    return "Current Password Incorrect"
@app.route("/teachers")
@login_required
def teachers():

    if not session.get("admin_id"):
        return "Access Denied"

    conn = get_db()

    admin_id = session["admin_id"]

    data = conn.execute(
        "SELECT * FROM teachers WHERE admin_id=?",
        (admin_id,)
    ).fetchall()

    conn.close()

    return render_template(
        "teachers.html",
        data=data
    )
@app.route("/delete_teacher/<username>", methods=["POST"])
@login_required
def delete_teacher(username):

    conn = get_db()

    conn.execute(
        "DELETE FROM teachers WHERE username=?",
        (username,)
    )

    conn.commit()
    conn.close()

    return redirect("/teachers")
@app.route("/check_students")
def check_students():

    conn = get_db()

    data = conn.execute(
        "SELECT * FROM students"
    ).fetchall()

    conn.close()

    return str(data)
@app.route("/delete_bad_student")
def delete_bad_student():

    conn = get_db()

    conn.execute(
        "DELETE FROM students WHERE roll=''"
    )

    conn.commit()
    conn.close()

    return "Bad Student Deleted"
@app.route("/register_admin", methods=["GET", "POST"])
def register_admin():

    if request.method == "POST":

        name = request.form["name"]
        email = request.form["email"]
        phone = request.form["phone"]
        password = request.form["password"]

        conn = get_db()

        conn.execute(
            """
            INSERT INTO admins (name, email, phone, password)
            VALUES (?, ?, ?, ?)
            """,
            (name, email, phone, password)
        )

        conn.commit()
        conn.close()

        return redirect("/")

    return render_template("register_admin.html")
@app.route("/update_db")
def update_db():

    conn = get_db()

    try:
        conn.execute("ALTER TABLE students ADD COLUMN admin_id INTEGER")
    except:
        pass

    try:
        conn.execute("ALTER TABLE teachers ADD COLUMN admin_id INTEGER")
    except:
        pass

    try:
        conn.execute("ALTER TABLE attendance ADD COLUMN admin_id INTEGER")
    except:
        pass

    conn.commit()
    conn.close()

    return "Database Updated Successfully"
@app.route("/update_teacher_table")
def update_teacher_table():

    conn = get_db()

    try:
        conn.execute(
            "ALTER TABLE teachers ADD COLUMN admin_id INTEGER"
        )
        conn.commit()
    except:
        pass

    conn.close()

    return "Teacher table updated"
@app.route("/check_teacher_table")
def check_teacher_table():

    conn = get_db()

    data = conn.execute(
        "PRAGMA table_info(teachers)"
    ).fetchall()

    conn.close()

    return str(data)
@app.route("/check_teachers")
def check_teachers():

    conn = get_db()

    data = conn.execute(
        "SELECT * FROM teachers"
    ).fetchall()

    conn.close()

    return str(data)
@app.route("/check_admins")
def check_admins():

    conn = get_db()

    data = conn.execute(
        "SELECT * FROM admins"
    ).fetchall()

    conn.close()

    return str(data)
app.run(debug=True)