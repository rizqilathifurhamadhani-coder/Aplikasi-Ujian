from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "cbt-ujian-secret-key-2026"
)

DATABASE = "cbt.db"

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"


# =========================================================
# DATABASE
# =========================================================

def get_db():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    return db


def init_db():

    db = get_db()

    db.execute("""
        CREATE TABLE IF NOT EXISTS peserta (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nama TEXT NOT NULL,
            kode TEXT UNIQUE NOT NULL,
            sekolah TEXT
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS ujian (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nama TEXT NOT NULL,
            deskripsi TEXT,
            durasi_menit INTEGER NOT NULL,
            mulai TEXT,
            selesai TEXT
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS soal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ujian_id INTEGER NOT NULL,
            pertanyaan TEXT NOT NULL,
            opsi_a TEXT NOT NULL,
            opsi_b TEXT NOT NULL,
            opsi_c TEXT NOT NULL,
            opsi_d TEXT NOT NULL,
            jawaban_benar TEXT NOT NULL,
            poin INTEGER DEFAULT 1
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS jawaban (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            peserta_id INTEGER NOT NULL,
            ujian_id INTEGER NOT NULL,
            soal_id INTEGER NOT NULL,
            jawaban TEXT,
            UNIQUE(peserta_id, ujian_id, soal_id)
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS hasil (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            peserta_id INTEGER NOT NULL,
            ujian_id INTEGER NOT NULL,
            jumlah_benar INTEGER DEFAULT 0,
            jumlah_soal INTEGER DEFAULT 0,
            nilai REAL DEFAULT 0,
            waktu_selesai TEXT
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS pelanggaran (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            peserta_id INTEGER NOT NULL,
            ujian_id INTEGER NOT NULL,
            jumlah INTEGER DEFAULT 0,
            UNIQUE(peserta_id, ujian_id)
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS sesi_ujian (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            peserta_id INTEGER NOT NULL,
            ujian_id INTEGER NOT NULL,
            mulai TEXT,
            selesai INTEGER DEFAULT 0,
            UNIQUE(peserta_id, ujian_id)
        )
    """)

    db.commit()
    db.close()


init_db()


# =========================================================
# HALAMAN UTAMA
# =========================================================

@app.route("/")
def home():

    db = get_db()

    exams = db.execute("""
        SELECT *
        FROM ujian
        ORDER BY id DESC
    """).fetchall()

    db.close()

    return render_template(
        "index.html",
        exams=exams
    )


# =========================================================
# LOGIN PESERTA
# =========================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        kode = request.form.get("kode", "").strip()

        db = get_db()

        peserta = db.execute("""
            SELECT *
            FROM peserta
            WHERE kode = ?
        """, (kode,)).fetchone()

        db.close()

        if peserta:

            session["peserta_id"] = peserta["id"]

            return redirect(
                url_for("dashboard")
            )

        return render_template(
            "login.html",
            error="Kode peserta tidak ditemukan."
        )

    return render_template("login.html")


# =========================================================
# LOGOUT PESERTA
# =========================================================

@app.route("/logout")
def logout():

    session.pop("peserta_id", None)

    return redirect(url_for("home"))


# =========================================================
# DASHBOARD PESERTA
# =========================================================

@app.route("/dashboard")
def dashboard():

    if "peserta_id" not in session:
        return redirect(url_for("login"))

    db = get_db()

    peserta = db.execute("""
        SELECT *
        FROM peserta
        WHERE id = ?
    """, (session["peserta_id"],)).fetchone()

    exams = db.execute("""
        SELECT *
        FROM ujian
        ORDER BY id DESC
    """).fetchall()

    db.close()

    return render_template(
        "dashboard.html",
        peserta=peserta,
        exams=exams
    )


# =========================================================
# MULAI UJIAN
# =========================================================

@app.route("/ujian/<int:exam_id>")
def ujian(exam_id):

    if "peserta_id" not in session:
        return redirect(url_for("login"))

    peserta_id = session["peserta_id"]

    db = get_db()

    peserta = db.execute("""
        SELECT *
        FROM peserta
        WHERE id = ?
    """, (peserta_id,)).fetchone()

    exam = db.execute("""
        SELECT *
        FROM ujian
        WHERE id = ?
    """, (exam_id,)).fetchone()

    if not exam:
        db.close()
        return "Ujian tidak ditemukan.", 404

    questions = db.execute("""
        SELECT *
        FROM soal
        WHERE ujian_id = ?
        ORDER BY id
    """, (exam_id,)).fetchall()

    session_exam = db.execute("""
        SELECT *
        FROM sesi_ujian
        WHERE peserta_id = ?
        AND ujian_id = ?
    """, (peserta_id, exam_id)).fetchone()

    if not session_exam:

        db.execute("""
            INSERT INTO sesi_ujian
            (peserta_id, ujian_id, mulai)
            VALUES (?, ?, ?)
        """, (
            peserta_id,
            exam_id,
            datetime.now().isoformat()
        ))

        db.commit()

    violation = db.execute("""
        SELECT jumlah
        FROM pelanggaran
        WHERE peserta_id = ?
        AND ujian_id = ?
    """, (peserta_id, exam_id)).fetchone()

    violation_count = (
        violation["jumlah"]
        if violation else 0
    )

    db.close()

    return render_template(
        "ujian.html",
        peserta=peserta,
        exam=exam,
        questions=questions,
        violation_count=violation_count
    )


# =========================================================
# SIMPAN JAWABAN
# =========================================================

@app.route("/api/save-answer", methods=["POST"])
def save_answer():

    if "peserta_id" not in session:
        return jsonify({
            "success": False
        }), 401

    data = request.get_json()

    peserta_id = session["peserta_id"]
    exam_id = data.get("exam_id")
    soal_id = data.get("question_id")
    jawaban = data.get("answer")

    db = get_db()

    db.execute("""
        INSERT INTO jawaban
        (peserta_id, ujian_id, soal_id, jawaban)
        VALUES (?, ?, ?, ?)

        ON CONFLICT(peserta_id, ujian_id, soal_id)
        DO UPDATE SET jawaban = excluded.jawaban
    """, (
        peserta_id,
        exam_id,
        soal_id,
        jawaban
    ))

    db.commit()
    db.close()

    return jsonify({
        "success": True
    })


# =========================================================
# PELANGGARAN
# =========================================================

@app.route("/api/violation", methods=["POST"])
def violation():

    if "peserta_id" not in session:
        return jsonify({
            "success": False
        }), 401

    data = request.get_json()

    peserta_id = session["peserta_id"]
    exam_id = data.get("exam_id")

    db = get_db()

    existing = db.execute("""
        SELECT *
        FROM pelanggaran
        WHERE peserta_id = ?
        AND ujian_id = ?
    """, (
        peserta_id,
        exam_id
    )).fetchone()

    if existing:

        new_count = existing["jumlah"] + 1

        db.execute("""
            UPDATE pelanggaran
            SET jumlah = ?
            WHERE peserta_id = ?
            AND ujian_id = ?
        """, (
            new_count,
            peserta_id,
            exam_id
        ))

    else:

        new_count = 1

        db.execute("""
            INSERT INTO pelanggaran
            (peserta_id, ujian_id, jumlah)
            VALUES (?, ?, ?)
        """, (
            peserta_id,
            exam_id,
            new_count
        ))

    db.commit()

    finished = new_count >= 3

    if finished:

        finish_exam_for(
            db,
            peserta_id,
            exam_id
        )

    db.commit()
    db.close()

    return jsonify({
        "success": True,
        "violation_count": new_count,
        "finished": finished
    })


# =========================================================
# SELESAIKAN UJIAN
# =========================================================

@app.route("/finish-exam/<int:exam_id>", methods=["POST"])
def finish_exam(exam_id):

    if "peserta_id" not in session:
        return jsonify({
            "success": False
        }), 401

    peserta_id = session["peserta_id"]

    db = get_db()

    finish_exam_for(
        db,
        peserta_id,
        exam_id
    )

    db.commit()
    db.close()

    return jsonify({
        "success": True
    })


def finish_exam_for(db, peserta_id, exam_id):

    existing_result = db.execute("""
        SELECT *
        FROM hasil
        WHERE peserta_id = ?
        AND ujian_id = ?
    """, (
        peserta_id,
        exam_id
    )).fetchone()

    if existing_result:
        return

    questions = db.execute("""
        SELECT *
        FROM soal
        WHERE ujian_id = ?
    """, (exam_id,)).fetchall()

    answers = db.execute("""
        SELECT *
        FROM jawaban
        WHERE peserta_id = ?
        AND ujian_id = ?
    """, (
        peserta_id,
        exam_id
    )).fetchall()

    answer_map = {
        row["soal_id"]: row["jawaban"]
        for row in answers
    }

    jumlah_benar = 0
    total_poin = 0
    max_poin = 0

    for question in questions:

        poin = question["poin"] or 1

        max_poin += poin

        answer = answer_map.get(
            question["id"]
        )

        if answer == question["jawaban_benar"]:

            jumlah_benar += 1
            total_poin += poin

    jumlah_soal = len(questions)

    if max_poin > 0:
        nilai = (total_poin / max_poin) * 100
    else:
        nilai = 0

    db.execute("""
        INSERT INTO hasil
        (
            peserta_id,
            ujian_id,
            jumlah_benar,
            jumlah_soal,
            nilai,
            waktu_selesai
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        peserta_id,
        exam_id,
        jumlah_benar,
        jumlah_soal,
        round(nilai, 2),
        datetime.now().isoformat()
    ))

    db.execute("""
        UPDATE sesi_ujian
        SET selesai = 1
        WHERE peserta_id = ?
        AND ujian_id = ?
    """, (
        peserta_id,
        exam_id
    ))


# =========================================================
# HASIL PESERTA
# =========================================================

@app.route("/hasil/<int:exam_id>")
def hasil(exam_id):

    if "peserta_id" not in session:
        return redirect(url_for("login"))

    db = get_db()

    peserta = db.execute("""
        SELECT *
        FROM peserta
        WHERE id = ?
    """, (
        session["peserta_id"],
    )).fetchone()

    exam = db.execute("""
        SELECT *
        FROM ujian
        WHERE id = ?
    """, (
        exam_id,
    )).fetchone()

    result = db.execute("""
        SELECT *
        FROM hasil
        WHERE peserta_id = ?
        AND ujian_id = ?
    """, (
        session["peserta_id"],
        exam_id
    )).fetchone()

    db.close()

    if not result:
        return redirect(
            url_for(
                "dashboard"
            )
        )

    return render_template(
        "hasil.html",
        peserta=peserta,
        exam=exam,
        hasil=result
    )


# =========================================================
# LOGIN ADMIN
# =========================================================

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        )

        password = request.form.get(
            "password",
            ""
        )

        if (
            username == ADMIN_USERNAME
            and password == ADMIN_PASSWORD
        ):

            session["admin"] = True

            return redirect(
                url_for("admin_dashboard")
            )

        return render_template(
            "admin_login.html",
            error="Username atau password salah."
        )

    return render_template(
        "admin_login.html"
    )


# =========================================================
# CEK ADMIN
# =========================================================

def admin_required():

    return session.get(
        "admin"
    ) is True


# =========================================================
# LOGOUT ADMIN
# =========================================================

@app.route("/admin/logout")
def admin_logout():

    session.pop("admin", None)

    return redirect(
        url_for("admin_login")
    )


# =========================================================
# DASHBOARD ADMIN
# =========================================================

@app.route("/admin/dashboard")
def admin_dashboard():

    if not admin_required():
        return redirect(
            url_for("admin_login")
        )

    return render_template(
        "admin_dashboard.html"
    )


# =========================================================
# KELOLA PESERTA
# =========================================================

@app.route(
    "/admin/peserta",
    methods=["GET", "POST"]
)
def admin_peserta():

    if not admin_required():
        return redirect(
            url_for("admin_login")
        )

    db = get_db()
    error = None

    if request.method == "POST":

        nama = request.form.get(
            "nama",
            ""
        ).strip()

        kode = request.form.get(
            "kode",
            ""
        ).strip()

        sekolah = request.form.get(
            "sekolah",
            ""
        ).strip()

        try:

            db.execute("""
                INSERT INTO peserta
                (nama, kode, sekolah)
                VALUES (?, ?, ?)
            """, (
                nama,
                kode,
                sekolah
            ))

            db.commit()

        except sqlite3.IntegrityError:

            error = "Kode peserta sudah digunakan."

    peserta_list = db.execute("""
        SELECT *
        FROM peserta
        ORDER BY id DESC
    """).fetchall()

    db.close()

    return render_template(
        "admin_peserta.html",
        peserta_list=peserta_list,
        error=error
    )


# =========================================================
# KELOLA UJIAN
# =========================================================

@app.route(
    "/admin/ujian",
    methods=["GET", "POST"]
)
def admin_ujian():

    if not admin_required():
        return redirect(
            url_for("admin_login")
        )

    db = get_db()
    error = None

    if request.method == "POST":

        nama = request.form.get(
            "nama",
            ""
        )

        deskripsi = request.form.get(
            "deskripsi",
            ""
        )

        durasi = request.form.get(
            "durasi_menit",
            60
        )

        mulai = request.form.get(
            "mulai",
            ""
        )

        selesai = request.form.get(
            "selesai",
            ""
        )

        db.execute("""
            INSERT INTO ujian
            (
                nama,
                deskripsi,
                durasi_menit,
                mulai,
                selesai
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            nama,
            deskripsi,
            durasi,
            mulai,
            selesai
        ))

        db.commit()

    exams = db.execute("""
        SELECT *
        FROM ujian
        ORDER BY id DESC
    """).fetchall()

    db.close()

    return render_template(
        "admin_ujian.html",
        exams=exams,
        error=error
    )


# =========================================================
# KELOLA SOAL
# =========================================================

@app.route(
    "/admin/soal/<int:exam_id>",
    methods=["GET", "POST"]
)
def admin_soal(exam_id):

    if not admin_required():
        return redirect(
            url_for("admin_login")
        )

    db = get_db()

    exam = db.execute("""
        SELECT *
        FROM ujian
        WHERE id = ?
    """, (
        exam_id,
    )).fetchone()

    if not exam:
        db.close()
        return "Ujian tidak ditemukan.", 404

    error = None

    if request.method == "POST":

        pertanyaan = request.form.get(
            "pertanyaan",
            ""
        )

        opsi_a = request.form.get(
            "opsi_a",
            ""
        )

        opsi_b = request.form.get(
            "opsi_b",
            ""
        )

        opsi_c = request.form.get(
            "opsi_c",
            ""
        )

        opsi_d = request.form.get(
            "opsi_d",
            ""
        )

        jawaban_benar = request.form.get(
            "jawaban_benar",
            ""
        )

        poin = request.form.get(
            "poin",
            1
        )

        db.execute("""
            INSERT INTO soal
            (
                ujian_id,
                pertanyaan,
                opsi_a,
                opsi_b,
                opsi_c,
                opsi_d,
                jawaban_benar,
                poin
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            exam_id,
            pertanyaan,
            opsi_a,
            opsi_b,
            opsi_c,
            opsi_d,
            jawaban_benar,
            poin
        ))

        db.commit()

    questions = db.execute("""
        SELECT *
        FROM soal
        WHERE ujian_id = ?
        ORDER BY id
    """, (
        exam_id,
    )).fetchall()

    db.close()

    return render_template(
        "admin_soal.html",
        exam=exam,
        questions=questions,
        error=error
    )


# =========================================================
# MONITORING
# =========================================================

@app.route("/admin/monitoring")
def admin_monitoring():

    if not admin_required():
        return redirect(
            url_for("admin_login")
        )

    db = get_db()

    sessions = db.execute("""
        SELECT
            sesi_ujian.peserta_id,
            peserta.nama,
            peserta.kode,
            ujian.nama AS nama_ujian
        FROM sesi_ujian

        JOIN peserta
        ON peserta.id = sesi_ujian.peserta_id

        JOIN ujian
        ON ujian.id = sesi_ujian.ujian_id

        WHERE sesi_ujian.selesai = 0
    """).fetchall()

    db.close()

    return render_template(
        "admin_monitoring.html",
        sessions=sessions
    )


# =========================================================
# HASIL ADMIN
# =========================================================

@app.route("/admin/hasil")
def admin_hasil():

    if not admin_required():
        return redirect(
            url_for("admin_login")
        )

    db = get_db()

    hasil_list = db.execute("""
        SELECT
            hasil.*,
            peserta.nama AS nama_peserta,
            ujian.nama AS nama_ujian
        FROM hasil

        JOIN peserta
        ON peserta.id = hasil.peserta_id

        JOIN ujian
        ON ujian.id = hasil.ujian_id

        ORDER BY hasil.id DESC
    """).fetchall()

    db.close()

    return render_template(
        "admin_hasil.html",
        hasil_list=hasil_list
    )


# =========================================================
# JALANKAN SERVER
# =========================================================

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                5000
            )
        )
    )
