from ultralytics import YOLO
import os

# ---------------- CHECK DATASET ----------------
DATA_YAML = "dataset/data.yaml"

if not os.path.exists(DATA_YAML):
    raise FileNotFoundError("❌ data.yaml not found! Check dataset path.")

print("✅ Dataset found")

# ---------------- LOAD MODEL ----------------
# You can change to yolov8s.pt for better accuracy (slower)
model = YOLO("yolov8n.pt")

# ---------------- TRAIN MODEL ----------------
model.train(
    data=DATA_YAML,   # dataset config
    epochs=20,        # increase later (50–100 for better results)
    imgsz=640,        # image size
    batch=8,          # reduce if low RAM
    name="waste_model",  # folder name
    patience=5        # early stopping
)

print("🎉 Training completed!")

# ---------------- SHOW RESULT PATH ----------------
print("\n📦 Your model is saved at:")
print("runs/detect/waste_model/weights/best.pt")