from ultralytics import YOLO

model = YOLO("runs/detect/train-9/weights/best.pt")

results = model("test.jpg", show=True)