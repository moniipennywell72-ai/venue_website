import json
import os
import secrets
from datetime import datetime
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, abort, send_from_directory
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB per upload

# Set OWNER_PASSWORD as an environment variable before deploying; this is only a local fallback.
OWNER_PASSWORD = os.environ.get("OWNER_PASSWORD", "SandyKitchen2026!")

DATA_DIR = os.environ.get("DATA_DIR", app.root_path)
OWNER_ACCOUNT_FILE = os.environ.get(
    "OWNER_ACCOUNT_FILE",
    os.path.join(DATA_DIR, "owner_account.json"),
)
GALLERY_FOLDER = os.environ.get("GALLERY_FOLDER", os.path.join(app.static_folder, "gallery"))
CATERING_REQUESTS_FILE = os.environ.get(
    "CATERING_REQUESTS_FILE",
    os.path.join(app.root_path, "catering_requests.json"),
)
SITE_SETTINGS_FILE = os.environ.get(
    "SITE_SETTINGS_FILE",
    os.path.join(app.root_path, "site_settings.json"),
)
DEFAULT_SITE_SETTINGS = {
    "announcement": "",
    "address": "",
    "phone": "",
    "hours": "",
    "hero_title": "Authentic Southern Cooking",
    "hero_description": "Louisiana flavor made with love.",
    "catering_message": "Catering is coming soon. For more information and to speak with Sandy about your event, please contact us directly and we will be happy to help with your next gathering.",
    "bayou_blend_description": "Sandy's Bayou Blend is her own signature seasoning, years in the making. Hand-mixed with a bold balance of Louisiana spices, it's the secret behind every dish at Sandy's Louisiana Soul Food Kitchen, bringing real bayou flavor to every plate.",
}
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}
os.makedirs(GALLERY_FOLDER, exist_ok=True)
if not os.path.exists(CATERING_REQUESTS_FILE):
    os.makedirs(os.path.dirname(CATERING_REQUESTS_FILE) or ".", exist_ok=True)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def list_gallery_images():
    files = [f for f in os.listdir(GALLERY_FOLDER) if allowed_file(f)]
    files.sort(key=lambda f: os.path.getmtime(os.path.join(GALLERY_FOLDER, f)), reverse=True)
    return files


def load_catering_requests():
    if not os.path.exists(CATERING_REQUESTS_FILE):
        return []
    try:
        with open(CATERING_REQUESTS_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def save_catering_requests(requests):
    with open(CATERING_REQUESTS_FILE, "w", encoding="utf-8") as file:
        json.dump(requests, file, ensure_ascii=False, indent=2)


def load_site_settings():
    settings = DEFAULT_SITE_SETTINGS.copy()
    if os.path.exists(SITE_SETTINGS_FILE):
        try:
            with open(SITE_SETTINGS_FILE, "r", encoding="utf-8") as file:
                saved_settings = json.load(file)
            if isinstance(saved_settings, dict):
                settings.update({key: str(saved_settings.get(key, value)) for key, value in settings.items()})
        except (json.JSONDecodeError, OSError):
            pass
    return settings


def save_site_settings(settings):
    with open(SITE_SETTINGS_FILE, "w", encoding="utf-8") as file:
        json.dump(settings, file, ensure_ascii=False, indent=2)


def load_owner_account():
    if os.path.exists(OWNER_ACCOUNT_FILE):
        try:
            with open(OWNER_ACCOUNT_FILE, "r", encoding="utf-8") as file:
                account = json.load(file)
            if isinstance(account, dict) and account.get("password_hash"):
                return {
                    "email": str(account.get("email", "")).strip().lower(),
                    "password_hash": account["password_hash"],
                }
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "email": os.environ.get("OWNER_EMAIL", "").strip().lower(),
        "password_hash": generate_password_hash(OWNER_PASSWORD),
    }


def save_owner_account(account):
    os.makedirs(os.path.dirname(OWNER_ACCOUNT_FILE) or ".", exist_ok=True)
    with open(OWNER_ACCOUNT_FILE, "w", encoding="utf-8") as file:
        json.dump(account, file, ensure_ascii=False, indent=2)


def owner_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_owner"):
            return redirect(url_for("owner_login"))
        return view(*args, **kwargs)
    return wrapped


@app.route('/')
def home():
    return render_template('home/index.html', settings=load_site_settings())


@app.route("/gallery")
def gallery():
    return render_template("gallery.html", images=list_gallery_images())


@app.route("/uploaded-gallery/<path:filename>")
def uploaded_gallery(filename):
    return send_from_directory(GALLERY_FOLDER, filename)


@app.route("/catering-request", methods=["GET", "POST"])
def catering_request():
    success = None
    error = None

    if request.method == "POST":
        required_fields = [
            "name",
            "phone",
            "email",
            "event_date",
            "guest_count",
            "event_type",
            "details",
        ]
        if any(not request.form.get(field, "").strip() for field in required_fields):
            error = "Please complete all required fields before submitting your request."
        else:
            requests = load_catering_requests()
            new_request = {
                "id": len(requests) + 1,
                "submitted_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
                "name": request.form.get("name", "").strip(),
                "phone": request.form.get("phone", "").strip(),
                "email": request.form.get("email", "").strip(),
                "event_date": request.form.get("event_date", "").strip(),
                "guest_count": request.form.get("guest_count", "").strip(),
                "event_type": request.form.get("event_type", "").strip(),
                "budget": request.form.get("budget", "").strip(),
                "details": request.form.get("details", "").strip(),
            }
            requests.insert(0, new_request)
            save_catering_requests(requests)
            success = "Thank you! Your catering request was submitted successfully. Sandy will reach out soon."
    return render_template("catering_request.html", success=success, error=error)


@app.route("/owner/login", methods=["GET", "POST"])
def owner_login():
    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        account = load_owner_account()
        email_matches = not account["email"] or secrets.compare_digest(email, account["email"])
        if email_matches and check_password_hash(account["password_hash"], password):
            session.clear()
            session["is_owner"] = True
            return redirect(url_for("owner_gallery"))
        error = "Incorrect email or password."
    return render_template("owner_login.html", error=error, owner_email=load_owner_account()["email"])


@app.route("/owner/settings", methods=["GET", "POST"])
@owner_required
def owner_settings():
    settings = load_site_settings()
    account = load_owner_account()
    success = None
    error = None
    if request.method == "POST":
        for key in settings:
            settings[key] = request.form.get(key, "").strip()
        new_email = request.form.get("owner_email", "").strip().lower()
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")
        changing_account = new_email != account["email"] or new_password
        if changing_account and not check_password_hash(account["password_hash"], current_password):
            error = "Enter the current password to change the owner email or password."
        elif new_password and new_password != confirm_password:
            error = "The new passwords do not match."
        elif new_password and len(new_password) < 8:
            error = "The new password must be at least 8 characters."
        else:
            account["email"] = new_email
            if new_password:
                account["password_hash"] = generate_password_hash(new_password)
            save_site_settings(settings)
            save_owner_account(account)
            success = "Site settings and owner account saved successfully."
    return render_template(
        "owner_settings.html",
        settings=settings,
        owner_email=account["email"],
        success=success,
        error=error,
    )


@app.route("/owner/logout")
def owner_logout():
    session.clear()
    return redirect(url_for("owner_login"))


@app.route("/owner/gallery", methods=["GET", "POST"])
@owner_required
def owner_gallery():
    error = None
    if request.method == "POST":
        photo = request.files.get("photo")
        if not photo or photo.filename == "":
            error = "Please choose a photo to upload."
        elif not allowed_file(photo.filename):
            error = "Only PNG, JPG, JPEG, WEBP, and GIF images are allowed."
        else:
            filename = secure_filename(photo.filename)
            base, ext = os.path.splitext(filename)
            destination = os.path.join(GALLERY_FOLDER, filename)
            counter = 1
            while os.path.exists(destination):
                filename = f"{base}-{counter}{ext}"
                destination = os.path.join(GALLERY_FOLDER, filename)
                counter += 1
            photo.save(destination)
    return render_template("owner_gallery.html", images=list_gallery_images(), error=error)


@app.route("/owner/gallery/delete/<path:filename>", methods=["POST"])
@owner_required
def owner_gallery_delete(filename):
    filename = secure_filename(filename)
    target = os.path.join(GALLERY_FOLDER, filename)
    if os.path.commonpath([target, GALLERY_FOLDER]) == GALLERY_FOLDER and os.path.isfile(target):
        os.remove(target)
    else:
        abort(404)
    return redirect(url_for("owner_gallery"))


@app.route("/owner/catering-requests")
@owner_required
def owner_catering_requests():
    return render_template("owner_catering_requests.html", requests=load_catering_requests())


@app.route("/dashboard")
def dashboard():
    restaurant_data = {
        "orders_today": 0,
        "sales_today": 0.00,
        "menu_items": 35,
        "pending_orders": 0
    }

    recent_orders = [
        {"id": "#1042", "customer": "cutomer 1", "total": 42.50, "status": "Preparing"},
        {"id": "#1041", "customer": "customer 2", "total": 28.00, "status": "Ready"},
        {"id": "#1040", "customer": "customer 3", "total": 63.25, "status": "Completed"}
    ]

    return render_template(
        "dashboard.html",
        data=restaurant_data,
        orders=recent_orders
    )


if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)