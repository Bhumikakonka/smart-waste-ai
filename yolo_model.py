from ultralytics import YOLO

model = YOLO("runs/detect/train-9/weights/best.pt")

def detect_waste(image_path):
    results = model(image_path, conf=0.3)

    detections = []

    for r in results:
        for box in r.boxes:
            cls = int(box.cls[0])
            label = model.names[cls]
            conf = float(box.conf[0]) * 100

            x1, y1, x2, y2 = box.xyxy[0]

            detections.append({
                "label": label,
                "confidence": round(conf, 2),
                "box": [int(x1), int(y1), int(x2), int(y2)]
            })

    return detections