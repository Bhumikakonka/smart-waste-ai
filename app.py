from flask import Flask, render_template, request, redirect, session, jsonify
import sqlite3
import os
from werkzeug.utils import secure_filename
from collections import defaultdict, Counter
from yolo_model import detect_waste
from ultralytics import YOLO
model = YOLO("best.pt")


app = Flask(__name__)
app.secret_key = "secret123"



UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


# ================= DATABASE =================
def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row   # 
    return conn
#==============================Scrap========================

# ================= CATEGORY MAPPING =================
def map_category(label):
    label = label.lower()

    if "plastic" in label:
        return "plastic"
    elif "metal" in label or "aluminum" in label or "tin" in label:
        return "metal"
    elif "glass" in label:
        return "glass"
    elif "paper" in label or "cardboard" in label:
        return "paper"
    elif "organic" in label or "food" in label:
        return "organic"
    elif "wood" in label:
        return "wood"
    else:
        return "trash"


# ================= SCRAP RATES =================
def get_scrap_value(category, weight=1):
    rates = {
        "metal": 35,
        "plastic": 18,
        "glass": 10,
        "paper": 6,
        "organic": 2,
        "wood": 4,
        "trash": 0
    }
    return round(rates.get(category, 0) * weight, 2)


# ================= AI DECISION =================
def ai_scrap_decision(category):
    if category == "metal":
        return "💰 Sell Now", "High scrap value"
    elif category == "plastic":
        return "♻️ Recycle", "Recyclable material"
    elif category == "paper":
        return "📦 Store & Sell", "Better in bulk"
    elif category == "glass":
        return "♻️ Recycle", "Handled by recycling units"
    elif category == "organic":
        return "🌱 Compost", "Good for composting"
    else:
        return "🗑️ Dispose", "Low value waste"


# ================= HOME =================
@app.route('/')
def home():
    return render_template("index.html")


# ================= LOGIN =================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE email=? AND password=?",
            (request.form['email'], request.form['password'])
        ).fetchone()

        if user:
            session['user_id'] = user[0]
            session['username'] = user[1]
            return redirect('/dashboard')

    return render_template("login.html")


# ================= DASHBOARD =================
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect('/login')

    db = get_db()
    records = db.execute(
        "SELECT category FROM waste_records WHERE user_id=?",
        (session['user_id'],)
    ).fetchall()

    scrap_breakdown = defaultdict(float)
    total_scrap = 0

    for r in records:
        cat = map_category(r[0])
        value = get_scrap_value(cat, 1)
        scrap_breakdown[cat] += value
        total_scrap += value

    return render_template(
        "dashboard.html",
        total=len(records),
        total_scrap=round(total_scrap, 2),
        scrap_breakdown=dict(scrap_breakdown)
    )


# ================= CALCULATE SCRAP =================
@app.route('/calculate_scrap', methods=['POST'])
def calculate_scrap():
    weight = float(request.json.get("weight", 1))

    db = get_db()
    records = db.execute(
        "SELECT category FROM waste_records WHERE user_id=?",
        (session['user_id'],)
    ).fetchall()

    count_map = Counter([map_category(r[0]) for r in records])

    total_items = sum(count_map.values())
    breakdown = {}
    total_value = 0

    for cat, count in count_map.items():
        cat_weight = (weight * count) / total_items if total_items else 0
        val = get_scrap_value(cat, cat_weight)

        breakdown[cat] = round(val, 2)
        total_value += val

    return jsonify({
        "breakdown": breakdown,
        "total": round(total_value, 2)
    })


# ================= UPLOAD =================
@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if 'user_id' not in session:
        return redirect('/login')

    if request.method == 'POST':
        file = request.files.get('image')

        if not file or file.filename == "":
            return redirect('/upload')

        filename = secure_filename(file.filename)
        path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(path)

        try:
            detections = detect_waste(path)
        except:
            detections = []

        # DEFAULT SAFE VALUES
        result = {
            "image": filename,
            "category": "Unknown",
            "confidence": 0,
            "eco_score": 0,
            "scrap_value": 0,
            "total_value": 0,
            "decision": "❌ No waste detected",
            "reason": "Try clearer image",
            "detections": []
        }

        if detections:
            total = 0
            eco = 0

            for d in detections:
                label = d.get("label", "Unknown")
                conf = round(d.get("confidence", 0), 2)

                # SMART CATEGORY LOGIC
                if "plastic" in label.lower():
                    value = 15
                    decision = "♻️ Recycle"
                    eco += 80
                elif "metal" in label.lower():
                    value = 30
                    decision = "💰 Sell"
                    eco += 90
                elif "glass" in label.lower():
                    value = 10
                    decision = "♻️ Recycle"
                    eco += 70
                else:
                    value = 5
                    decision = "🗑️ Dispose"
                    eco += 40

                total += value

                result["detections"].append({
                    "label": label,
                    "confidence": conf,
                    "value": value,
                    "decision": decision
                })

            main = result["detections"][0]

            category = map_category(main["label"])

            db = get_db()
            buyers = db.execute(
                        "SELECT * FROM scrap_buyers WHERE waste_types LIKE ?",
                          ('%' + category + '%',)
             ).fetchall()
            

            result["buyers"] = buyers

            result.update({
                "category": main["label"],
                "confidence": main["confidence"],
                "scrap_value": main["value"],
                "total_value": total,
                "eco_score": round(eco / len(detections), 2),
                "decision": main["decision"],
                "reason": "AI optimized waste handling"
            })

            db = get_db()

            for d in result["detections"]:
                db.execute("""
        INSERT INTO waste_records (user_id, image, category, date)
        VALUES (?, ?, ?, datetime('now'))
    """, (
        session['user_id'],
        filename,
        d["label"]
    ))

        db.commit()

        return render_template("result.html", **result,)

    return render_template("upload.html")
# ================= ADMIN =================
@app.route('/admin')
def admin():
    db = get_db()

    # TOTAL COUNTS
    users = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    waste = db.execute("SELECT COUNT(*) FROM waste_records").fetchone()[0]

    # CATEGORY DATA
    rows = db.execute("SELECT category FROM waste_records").fetchall()
    categories = [map_category(r[0]) for r in rows]
    count = Counter(categories)

    labels = list(count.keys())
    values = list(count.values())

    # TOP CATEGORY
    top_category = max(count, key=count.get) if count else "N/A"

    # TREND CATEGORY
    trend_rows = db.execute("""
        SELECT category FROM waste_records
        ORDER BY date DESC
        LIMIT 20
    """).fetchall()

    if trend_rows:
        trend_list = [map_category(r[0]) for r in trend_rows]
        trend_category = Counter(trend_list).most_common(1)[0][0]
    else:
        trend_category = "N/A"

    # ✅ RECENT UPLOADS (THIS WAS MISSING)
    recent = db.execute("""
        SELECT image, category, date
        FROM waste_records
        ORDER BY date DESC
        LIMIT 10
    """).fetchall()

    # ✅ FINAL RETURN (ONLY ONE RETURN)
    return render_template(
        "admin.html",
        users=users,
        waste=waste,
        labels=labels,
        values=values,
        dates=[],
        counts=[],
        top_category=top_category,
        trend_category=trend_category,
        recent=recent
    )

# ================= ADMIN CHART API =================
from collections import Counter

@app.route('/admin_chart_data')
def admin_chart_data():
    db = get_db()

    # CATEGORY DATA
    rows = db.execute("SELECT category FROM waste_records").fetchall()
    categories = [map_category(r[0]) for r in rows]
    count = Counter(categories)

    # TREND DATA (FIXED)
    trend_rows = db.execute("""
        SELECT DATE(date) as d, COUNT(*) as total
        FROM waste_records
        GROUP BY DATE(date)
        ORDER BY DATE(date)
    """).fetchall()

    dates = [row["d"] for row in trend_rows]
    counts = [row["total"] for row in trend_rows]

    return jsonify({
        "labels": list(count.keys()),
        "values": list(count.values()),
        "dates": dates,
        "counts": counts
    })

    
   

# ---------------- REGISTER ----------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        db = get_db()
        db.execute(
            "INSERT INTO users (username,email,password) VALUES (?,?,?)",
            (request.form['username'], request.form['email'], request.form['password'])
        )
        db.commit()
        return redirect('/login')

    return render_template("register.html")


# ---------------- LOGOUT ----------------
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


# ---------------- UPLOAD ----------------# ---------------- HISTORY ----------------
@app.route('/history')
def history():
    if 'user_id' not in session:
        return redirect('/login')

    db = get_db()
    records = db.execute(
        "SELECT image, category, date FROM waste_records WHERE user_id=?",
        (session['user_id'],)
    ).fetchall()

    return render_template("history.html", records=records)

from flask import request, jsonify
import base64
from PIL import Image
import io
import os


def smart_suggestions(label):
    label = label.lower()

    if "plastic" in label:
        return {
            "recycle": "Send to plastic recycling center",
            "reuse": "Use as container or planter",
            "disposal": "Put in dry waste",
            "tip": "Plastic takes 100+ years to decompose"
        }

    elif "metal" in label:
        return {
            "recycle": "Sell to scrap dealer",
            "reuse": "Reuse in DIY",
            "disposal": "Keep separate",
            "tip": "Metal is highly recyclable"
        }

    elif "glass" in label:
        return {
            "recycle": "Send to glass recycling",
            "reuse": "Reuse as jar",
            "disposal": "Handle carefully",
            "tip": "Glass can be reused endlessly"
        }

    elif "paper" in label:
        return {
            "recycle": "Send to paper recycling",
            "reuse": "Use for notes",
            "disposal": "Keep dry",
            "tip": "Saves trees"
        }

    elif "organic" in label:
        return {
            "recycle": "Compost it",
            "reuse": "Use as fertilizer",
            "disposal": "Wet waste bin",
            "tip": "Turns into compost"
        }

    return {
        "recycle": "Check local recycling",
        "reuse": "Reuse creatively",
        "disposal": "Dispose safely",
        "tip": "Reduce waste"
    }
@app.route('/predict_camera', methods=['POST'])
def predict_camera():

    try:
        data = request.json['image']

        # 🔹 Decode base64 image
        img_data = base64.b64decode(data.split(',')[1])
        img = Image.open(io.BytesIO(img_data)).convert("RGB")

        # 🔹 Save temp image
        temp_path = "static/temp.jpg"
        img.save(temp_path)

    

        results = model(temp_path, imgsz=320)

        detections = []

        if results and len(results) > 0:
            r = results[0]

            if r.boxes is not None:
                for box in r.boxes:

                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    cls_id = int(box.cls[0])
                    conf = float(box.conf[0]) * 100
                    label = model.names[cls_id]

                    # 🧠 SMART SUGGESTION
                    suggestion = smart_suggestions(label)

                    detections.append({
                        "label": label,
                        "confidence": round(conf, 2),
                        "box": [int(x1), int(y1), int(x2), int(y2)],
                        "suggestion": suggestion
                    })

        return jsonify({"detections": detections})

    except Exception as e:
        print("Camera Error:", e)
        return jsonify({"detections": []})

@app.route('/live')
def live():
    return render_template("camera.html")


# ================= RUN =================
if __name__ == "__main__":
    
    app.run(debug=True)

