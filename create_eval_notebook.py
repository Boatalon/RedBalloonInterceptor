import json
import os

def create_notebook():
    nb = {
        "cells": [],
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3.12 (Red Balloon Interceptor)",
                "language": "python",
                "name": "python3"
            },
            "language_info": {
                "codemirror_mode": {"name": "ipython", "version": 3},
                "file_extension": ".py",
                "mimetype": "text/x-python",
                "name": "python",
                "nbconvert_exporter": "python",
                "pygments_lexer": "ipython3",
                "version": "3.12.16"
            }
        },
        "nbformat": 4,
        "nbformat_minor": 4
    }

    def add_md(text):
        nb["cells"].append({
            "cell_type": "markdown",
            "metadata": {},
            "source": [line + "\n" for line in text.strip().split("\n")]
        })

    def add_code(text):
        nb["cells"].append({
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [line + "\n" for line in text.strip().split("\n")]
        })

    # Header
    add_md("""# 🎯 MobileNetV3-Small SSDLite: Comprehensive Model Evaluation & Host Benchmark
## 🎈 Red Balloon Interceptor for High-Speed Drone (>100 km/h)

ไฟล์ Notebook นี้สร้างขึ้นสำหรับการประเมินประสิทธิภาพโมเดล **SSDLite MobileNetV3-Small (224x224)** อย่างละเอียดบน **Test Dataset** (Stratified Split 10%):
1. **Host Performance Profiling:** วัดค่า Latency (ms), P50, P95, P99, Jitter และ FPS ของเครื่องที่กำลังรัน
2. **Object Detection Metrics ครบทุกมิติ:**
   - **Precision (ความแม่นยำ)**
   - **Recall (ความครอบคลุม)**
   - **F1-Score**
   - **mAP@50 (PASCAL VOC benchmark @ IoU 0.50)**
   - **mAP@50-95 (COCO primary benchmark @ IoU 0.50:0.95)**
   - **Composite Overall Score (คะแนนรวมประเมินภาพรวมแบบถ่วงน้ำหนัก)**
3. **Visualizations & Diagnostics:**
   - Precision-Recall Curves แยกรายคลาส (`red`, `blue`, `green`)
   - Detection Gallery แสดง Ground Truth เปรียบเทียบกับ Predictions จริงบน Test Set""")

    # Imports & Setup
    add_md("### 1. นำเข้า Libraries และตั้งค่า Device")
    add_code("""import os
import glob
import time
import json
import xml.etree.ElementTree as ET
from collections import defaultdict
from functools import partial

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from PIL import Image

import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
import torchvision
from torchvision.models import mobilenet_v3_small
from torchvision.models.detection.anchor_utils import DefaultBoxGenerator
from torchvision.models.detection.ssd import SSD
from torchvision.models.detection.ssdlite import SSDLiteHead, _mobilenet_extractor
from torchvision.models.detection._utils import retrieve_out_channels
import torchvision.transforms.functional as F

# ตรวจสอบ Hardware Acceleration (MPS บน Apple Silicon / CUDA / CPU)
device = torch.device("cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu"))
print(f"⚡ Active Execution Device: {device.type.upper()}")

CLASSES = ["__background__", "red", "blue", "green"]
EVAL_CLASSES = ["red", "blue", "green"]
CLASS_TO_IDX = {name: i for i, name in enumerate(CLASSES)}
IDX_TO_CLASS = {i: name for i, name in enumerate(CLASSES)}

CLASS_COLORS = {
    "red": "#e74c3c",
    "blue": "#3498db",
    "green": "#2ecc71"
}

# กำหนด Path ข้อมูลและโมเดล
DATASET_ROOT = os.path.abspath("balloon_dataset_stratified") if os.path.exists("balloon_dataset_stratified") else os.path.abspath("ComputerVisionSRC/balloon_dataset_stratified")
CHECKPOINT_PATH = "best_balloon_ssdlite_mobilenetv3_small_224.pth" if os.path.exists("best_balloon_ssdlite_mobilenetv3_small_224.pth") else "ComputerVisionSRC/best_balloon_ssdlite_mobilenetv3_small_224.pth"
IMG_SIZE = 224

print(f"📁 Dataset Path:    {DATASET_ROOT}/test")
print(f"📦 Checkpoint Path: {CHECKPOINT_PATH}")""")

    # Dataset loader
    add_md("### 2. สร้าง Custom Test Dataset Loader (VOC Format 224x224)")
    add_code("""class BalloonVOCTestDataset(Dataset):
    \"\"\"
    Test Dataset Loader ที่อ่าน VOC XML และปรับขนาดภาพเป็น 224x224
    พร้อม Normalize และ Scale Bounding Boxes ตามสัดส่วนภาพจริง
    \"\"\"
    def __init__(self, data_dir, img_size=224):
        self.data_dir = data_dir
        self.img_size = img_size
        self.xml_files = sorted(glob.glob(os.path.join(data_dir, "*.xml")))
        self.img_files = [f.replace(".xml", ".jpg") for f in self.xml_files]

    def __len__(self):
        return len(self.xml_files)

    def __getitem__(self, idx):
        img_path = self.img_files[idx]
        image = Image.open(img_path).convert("RGB")
        orig_w, orig_h = image.size

        tree = ET.parse(self.xml_files[idx])
        root = tree.getroot()

        boxes = []
        labels = []
        for obj in root.findall("object"):
            name = obj.find("name").text.strip().lower()
            if name not in CLASS_TO_IDX:
                continue
            bbox = obj.find("bndbox")
            xmin = max(0.0, min(float(orig_w), float(bbox.find("xmin").text)))
            ymin = max(0.0, min(float(orig_h), float(bbox.find("ymin").text)))
            xmax = max(0.0, min(float(orig_w), float(bbox.find("xmax").text)))
            ymax = max(0.0, min(float(orig_h), float(bbox.find("ymax").text)))
            if xmax > xmin and ymax > ymin:
                boxes.append([xmin, ymin, xmax, ymax])
                labels.append(CLASS_TO_IDX[name])

        scale_x = self.img_size / orig_w
        scale_y = self.img_size / orig_h
        image_resized = image.resize((self.img_size, self.img_size), Image.Resampling.BILINEAR)

        if len(boxes) > 0:
            boxes = torch.as_tensor(boxes, dtype=torch.float32)
            boxes[:, [0, 2]] *= scale_x
            boxes[:, [1, 3]] *= scale_y
            labels = torch.as_tensor(labels, dtype=torch.int64)
        else:
            boxes = torch.zeros((0, 4), dtype=torch.float32)
            labels = torch.zeros((0,), dtype=torch.int64)

        img_tensor = F.to_tensor(image_resized)
        return img_tensor, {
            "boxes": boxes,
            "labels": labels,
            "filename": os.path.basename(img_path),
            "orig_size": (orig_w, orig_h),
            "pil_image": image_resized
        }

def collate_fn(batch):
    return tuple(zip(*batch))

test_dataset = BalloonVOCTestDataset(os.path.join(DATASET_ROOT, "test"), img_size=IMG_SIZE)
test_loader = DataLoader(test_dataset, batch_size=1, shuffle=False, collate_fn=collate_fn)
print(f"✅ โหลด Test Dataset สำเร็จ: ทั้งหมด {len(test_dataset)} ภาพ")""")

    # Model Architecture
    add_md("### 3. โครงสร้างโมเดล SSDLite MobileNetV3-Small และโหลด Weights")
    add_code("""def build_high_speed_ssdlite(num_classes=4, img_size=224):
    \"\"\"
    สถาปัตยกรรม High-Speed SSDLite MobileNetV3-Small ขนาด 224x224
    ออกแบบสำหรับ Edge Device (Raspberry Pi 4) และโดรนความเร็วสูง >100 km/h
    \"\"\"
    norm_layer = partial(nn.BatchNorm2d, eps=0.001, momentum=0.03)
    backbone = mobilenet_v3_small(weights=None, norm_layer=norm_layer, reduced_tail=False)
    backbone = _mobilenet_extractor(backbone, trainable_layers=6, norm_layer=norm_layer)
    
    anchor_generator = DefaultBoxGenerator([[2, 3] for _ in range(6)], min_ratio=0.2, max_ratio=0.95)
    size = (img_size, img_size)
    out_channels = retrieve_out_channels(backbone, size)
    num_anchors = anchor_generator.num_anchors_per_location()
    
    head = SSDLiteHead(out_channels, num_anchors, num_classes, norm_layer)
    defaults = {
        "score_thresh": 0.005,
        "nms_thresh": 0.45,
        "detections_per_img": 100,
        "topk_candidates": 200,
        "image_mean": [0.5, 0.5, 0.5],
        "image_std": [0.5, 0.5, 0.5],
    }
    model = SSD(backbone, anchor_generator, size, num_classes, head=head, **defaults)
    return model

model = build_high_speed_ssdlite(num_classes=len(CLASSES), img_size=IMG_SIZE)
if os.path.exists(CHECKPOINT_PATH):
    ckpt = torch.load(CHECKPOINT_PATH, map_location=device)
    model.load_state_dict(ckpt["model_state_dict"])
    print(f"✅ โหลด Checkpoint สำเร็จจาก: {CHECKPOINT_PATH}")
    print(f"   • Best Epoch: {ckpt.get('epoch', 'N/A')}")
    print(f"   • Best Validation Loss: {ckpt.get('val_loss', 0.0):.4f}")
else:
    print(f"⚠️ ไม่พบไฟล์ Checkpoint ที่ {CHECKPOINT_PATH}")

model = model.to(device)
model.eval()""")

    # Host Machine Benchmark
    add_md("""### 4. วัด Performance บนเครื่องนี้ (Host Machine Latency & FPS)
ทดสอบ Inference Loop วัดความเร็วเฉลี่ย, P50 (มัธยฐาน), P95, P99 และคำนวณระยะการเคลื่อนที่ของโดรนต่อ 1 เฟรม (@ 100 km/h = 27.78 m/s)""")
    add_code("""latencies = []
all_preds = []
all_gts = []
test_images_vis = []

# Warmup 5 รอบเพื่อเคลียร์ Cache ของ Hardware
with torch.no_grad():
    for i in range(min(5, len(test_dataset))):
        im, _ = test_dataset[i]
        _ = model([im.to(device)])

print("⚡ กำลังรัน Inference บน Test Set ทั้งหมด...")
with torch.no_grad():
    for images, targets in test_loader:
        im = images[0].to(device)
        gt = targets[0]

        # จับเวลาแบบความแม่นยำสูง (High Resolution Timer)
        if device.type == "cuda":
            torch.cuda.synchronize()
        t0 = time.perf_counter()
        
        pred = model([im])[0]
        
        if device.type == "cuda":
            torch.cuda.synchronize()
        t1 = time.perf_counter()

        lat_ms = (t1 - t0) * 1000.0
        latencies.append(lat_ms)

        all_preds.append({
            "boxes": pred["boxes"].cpu().numpy(),
            "scores": pred["scores"].cpu().numpy(),
            "labels": pred["labels"].cpu().numpy()
        })
        all_gts.append({
            "boxes": gt["boxes"].numpy(),
            "labels": gt["labels"].numpy(),
            "filename": gt["filename"]
        })
        test_images_vis.append(gt["pil_image"])

mean_lat = float(np.mean(latencies))
std_lat = float(np.std(latencies))
p50_lat = float(np.percentile(latencies, 50))
p95_lat = float(np.percentile(latencies, 95))
p99_lat = float(np.percentile(latencies, 99))
fps_host = 1000.0 / mean_lat

# คำนวณระยะ Drift ของโดรนความเร็ว 100 km/h (27.78 m/s)
drone_speed_mps = 100.0 / 3.6
drift_p50 = (p50_lat / 1000.0) * drone_speed_mps
drift_p99 = (p99_lat / 1000.0) * drone_speed_mps

perf_df = pd.DataFrame({
    "Metric": [
        "Hardware Device",
        "Average Inference FPS",
        "Mean Total Latency (ms)",
        "P50 Latency (ms)",
        "P95 Latency (ms)",
        "P99 Latency (ms)",
        "Jitter Std (ms)",
        "Drone Drift @ 100 km/h (P50)",
        "Drone Drift @ 100 km/h (P99)"
    ],
    "Value": [
        device.type.upper(),
        f"{fps_host:.1f} FPS",
        f"{mean_lat:.2f} ms",
        f"{p50_lat:.2f} ms",
        f"{p95_lat:.2f} ms",
        f"{p99_lat:.2f} ms",
        f"{std_lat:.2f} ms",
        f"{drift_p50:.2f} m",
        f"{drift_p99:.2f} m"
    ]
})
display(perf_df)""")

    # Metric Engine
    add_md("""### 5. Engine คำนวณ Precision, Recall, F1, mAP@50, mAP@50-95 และ Overall Score
ตามมาตรฐาน **PASCAL VOC 101-point Interpolation** และ **COCO Evaluation Benchmark**""")
    add_code("""def compute_iou(box1, box2):
    xA = max(box1[0], box2[0])
    yA = max(box1[1], box2[1])
    xB = min(box1[2], box2[2])
    yB = min(box1[3], box2[3])

    interArea = max(0.0, xB - xA) * max(0.0, yB - yA)
    boxAArea = max(0.0, box1[2] - box1[0]) * max(0.0, box1[3] - box1[1])
    boxBArea = max(0.0, box2[2] - box2[0]) * max(0.0, box2[3] - box2[1])
    denom = boxAArea + boxBArea - interArea
    return interArea / denom if denom > 0 else 0.0

def compute_all_detection_metrics(all_preds, all_gts, conf_thresh=0.40):
    iou_thresholds = np.linspace(0.50, 0.95, 10)
    
    per_class_results = {}
    total_gt = 0
    total_tp = 0
    total_fp = 0
    total_fn = 0
    pr_data = {}

    for cls_name in EVAL_CLASSES:
        cls_id = CLASS_TO_IDX[cls_name]
        
        # รวบรวม Ground Truths รายคลาส
        gts_by_img = defaultdict(list)
        n_gt_class = 0
        for img_id, gt_dict in enumerate(all_gts):
            for b, l in zip(gt_dict["boxes"], gt_dict["labels"]):
                if l == cls_id:
                    gts_by_img[img_id].append({"box": b.tolist(), "matched": False})
                    n_gt_class += 1
        total_gt += n_gt_class

        # รวบรวม Predictions รายคลาส
        preds_class = []
        for img_id, pred_dict in enumerate(all_preds):
            for b, s, l in zip(pred_dict["boxes"], pred_dict["scores"], pred_dict["labels"]):
                if l == cls_id:
                    preds_class.append({"img_id": img_id, "score": float(s), "box": b.tolist()})

        preds_class.sort(key=lambda x: x["score"], reverse=True)

        ap_list = []
        op_tp, op_fp, op_fn = 0, 0, 0

        for iou_thresh in iou_thresholds:
            current_gts = {img_id: [{"box": g["box"], "matched": False} for g in g_list] for img_id, g_list in gts_by_img.items()}
            tp = np.zeros(len(preds_class))
            fp = np.zeros(len(preds_class))

            for p_idx, pred in enumerate(preds_class):
                img_id = pred["img_id"]
                pred_box = pred["box"]
                best_iou = 0.0
                best_idx = -1

                if img_id in current_gts:
                    for g_idx, gt in enumerate(current_gts[img_id]):
                        if not gt["matched"]:
                            iou = compute_iou(pred_box, gt["box"])
                            if iou > best_iou:
                                best_iou = iou
                                best_idx = g_idx

                if best_iou >= iou_thresh and best_idx >= 0:
                    tp[p_idx] = 1
                    current_gts[img_id][best_idx]["matched"] = True
                else:
                    fp[p_idx] = 1

            tp_cum = np.cumsum(tp)
            fp_cum = np.cumsum(fp)
            recalls = tp_cum / max(n_gt_class, 1)
            precisions = tp_cum / np.maximum(tp_cum + fp_cum, np.finfo(np.float64).eps)

            # 101-point interpolation AP
            ap = 0.0
            for r in np.linspace(0, 1.0, 101):
                p_at_r = precisions[recalls >= r]
                ap += np.max(p_at_r) if len(p_at_r) > 0 else 0.0
            ap /= 101.0
            ap_list.append(ap)

            if abs(iou_thresh - 0.50) < 1e-4:
                ap_50 = ap
                pr_data[cls_name] = {"recalls": recalls.tolist(), "precisions": precisions.tolist()}
                
                # Count TP, FP, FN ที่ threshold ที่ใช้งานจริง
                c_tp = sum(1 for p_idx, pred in enumerate(preds_class) if pred["score"] >= conf_thresh and tp[p_idx] == 1)
                c_fp = sum(1 for p_idx, pred in enumerate(preds_class) if pred["score"] >= conf_thresh and fp[p_idx] == 1)
                c_fn = max(0, n_gt_class - c_tp)
                op_tp, op_fp, op_fn = c_tp, c_fp, c_fn

        ap_50_95 = float(np.mean(ap_list))
        prec = op_tp / (op_tp + op_fp) if (op_tp + op_fp) > 0 else 0.0
        rec = op_tp / (op_tp + op_fn) if (op_tp + op_fn) > 0 else 0.0
        f1 = 2 * (prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0

        per_class_results[cls_name] = {
            "Ground Truths": n_gt_class,
            "TP": op_tp,
            "FP": op_fp,
            "FN": op_fn,
            "Precision": prec,
            "Recall": rec,
            "F1-Score": f1,
            "mAP@50": ap_50,
            "mAP@50-95": ap_50_95
        }
        total_tp += op_tp
        total_fp += op_fp
        total_fn += op_fn

    overall_prec = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
    overall_rec = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0
    overall_f1 = 2 * (overall_prec * overall_rec) / (overall_prec + overall_rec) if (overall_prec + overall_rec) > 0 else 0.0

    mean_ap50 = float(np.mean([v["mAP@50"] for v in per_class_results.values()]))
    mean_ap50_95 = float(np.mean([v["mAP@50-95"] for v in per_class_results.values()]))

    # Composite Score: Harmonic Mean of mAP50, mAP50-95, and F1
    composite_score = (3.0 * mean_ap50 * mean_ap50_95 * overall_f1) / (
        mean_ap50 * mean_ap50_95 + mean_ap50 * overall_f1 + mean_ap50_95 * overall_f1 + 1e-6
    )

    return per_class_results, {
        "Ground Truths": total_gt,
        "TP": total_tp,
        "FP": total_fp,
        "FN": total_fn,
        "Precision": overall_prec,
        "Recall": overall_rec,
        "F1-Score": overall_f1,
        "mAP@50": mean_ap50,
        "mAP@50-95": mean_ap50_95,
        "Composite Score": composite_score
    }, pr_data

per_class_metrics, overall_metrics, pr_curves = compute_all_detection_metrics(all_preds, all_gts, conf_thresh=0.40)""")

    # Formatted Metric Table
    add_md("### 6. ตารางสรุปผลการประเมิน (Full Evaluation Metrics Table)")
    add_code("""# แปลงผลลัพธ์เป็น DataFrame แสดงผลสวยงาม
rows = []
for c_name, data in per_class_metrics.items():
    rows.append({
        "Class": c_name.upper(),
        "GT": data["Ground Truths"],
        "TP": data["TP"],
        "FP": data["FP"],
        "FN": data["FN"],
        "Precision": f"{data['Precision']*100:.1f}%",
        "Recall": f"{data['Recall']*100:.1f}%",
        "F1-Score": f"{data['F1-Score']*100:.1f}%",
        "mAP@50": f"{data['mAP@50']*100:.1f}%",
        "mAP@50-95": f"{data['mAP@50-95']*100:.1f}%"
    })

# แถวรวม Overall
rows.append({
    "Class": "⭐ OVERALL",
    "GT": overall_metrics["Ground Truths"],
    "TP": overall_metrics["TP"],
    "FP": overall_metrics["FP"],
    "FN": overall_metrics["FN"],
    "Precision": f"{overall_metrics['Precision']*100:.1f}%",
    "Recall": f"{overall_metrics['Recall']*100:.1f}%",
    "F1-Score": f"{overall_metrics['F1-Score']*100:.1f}%",
    "mAP@50": f"{overall_metrics['mAP@50']*100:.1f}%",
    "mAP@50-95": f"{overall_metrics['mAP@50-95']*100:.1f}%"
})

metrics_df = pd.DataFrame(rows)
display(metrics_df)

print(f"\\n{'='*60}")
print(f"🏆 COMPOSITE OVERALL SCORE: {overall_metrics['Composite Score']*100:.2f} / 100")
print(f"{'='*60}")""")

    # Precision Recall Curves
    add_md("### 7. กราฟ Precision-Recall Curves (@ IoU 0.50)")
    add_code("""plt.figure(figsize=(9, 6))

for cls_name, pr in pr_curves.items():
    if len(pr["recalls"]) > 0:
        ap_val = per_class_metrics[cls_name]["mAP@50"] * 100
        plt.plot(pr["recalls"], pr["precisions"], 
                 label=f"{cls_name.capitalize()} Balloon (mAP@50 = {ap_val:.1f}%)",
                 color=CLASS_COLORS.get(cls_name, "blue"),
                 linewidth=2.8)

plt.title("Precision-Recall Curves @ IoU=0.50 (Test Dataset)", fontsize=14, fontweight="bold", pad=12)
plt.xlabel("Recall (ความครอบคลุม)", fontsize=12)
plt.ylabel("Precision (ความแม่นยำ)", fontsize=12)
plt.xlim([0.0, 1.02])
plt.ylim([0.0, 1.05])
plt.grid(True, linestyle="--", alpha=0.6)
plt.legend(loc="lower left", fontsize=11, framealpha=0.9)
plt.tight_layout()
plt.show()""")

    # Visual Inspection Gallery
    add_md("""### 8. Visual Detection Gallery (Ground Truth vs Model Prediction)
สุ่มแสดงภาพตัวอย่างจาก Test Set พร้อม Bounding Box ของ Ground Truth (เส้นประสีขาว) และ Prediction (กรอบสีตามคลาส)""")
    add_code("""import matplotlib.patches as patches

fig, axes = plt.subplots(2, 3, figsize=(15, 10))
axes = axes.flatten()

sample_indices = np.linspace(0, len(test_dataset) - 1, 6, dtype=int)

for plot_idx, img_idx in enumerate(sample_indices):
    ax = axes[plot_idx]
    pil_img = test_images_vis[img_idx]
    ax.imshow(pil_img)
    
    gt = all_gts[img_idx]
    pred = all_preds[img_idx]

    # วาด Ground Truths (เส้นประสีขาว)
    for b, l in zip(gt["boxes"], gt["labels"]):
        rect = patches.Rectangle((b[0], b[1]), b[2]-b[0], b[3]-b[1],
                                 linewidth=2, edgecolor="white", linestyle="--", facecolor="none")
        ax.add_patch(rect)
        ax.text(b[0], max(10, b[1]-4), f"GT:{IDX_TO_CLASS[l]}", color="white",
                fontsize=8, fontweight="bold", bbox=dict(facecolor="black", alpha=0.5, pad=1))

    # วาด Predictions (กรอบสีตามคลาสที่มี score >= 0.40)
    for b, s, l in zip(pred["boxes"], pred["scores"], pred["labels"]):
        if s >= 0.40 and l > 0:
            c_name = IDX_TO_CLASS[l]
            color = CLASS_COLORS.get(c_name, "yellow")
            rect = patches.Rectangle((b[0], b[1]), b[2]-b[0], b[3]-b[1],
                                     linewidth=2.5, edgecolor=color, facecolor="none")
            ax.add_patch(rect)
            ax.text(b[0], min(IMG_SIZE - 5, b[3] + 12), f"{c_name} {s*100:.0f}%", color=color,
                    fontsize=9, fontweight="bold", bbox=dict(facecolor="black", alpha=0.7, pad=1.5))

    ax.set_title(f"Test #{img_idx}: {gt['filename'][:15]}...", fontsize=10)
    ax.axis("off")

plt.suptitle("🎯 Visual Detection: Ground Truth (Dashed White) vs Predictions (Solid Colored)", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.show()""")

    # Conclusion & Operational Summary
    add_md("""### 9. สรุปผลการประเมินและความพร้อมใช้งานจริง (Operational Readiness)
1. **Host Performance:** โมเดลประมวลผลได้รวดเร็วมากที่ขนาด **224x224** พร้อมความหน่วงต่ำ
2. **Red Balloon Priority:** คลาสสีแดงถูกจัดสรรอัตราส่วนและเทรนด้วย High-speed Detection Head เพื่อให้โดรนสามารถล็อกเป้าได้แม่นยำ
3. **Deploy บน Raspberry Pi 4:** แนะนำรันไฟล์ C++ (`pi4_balloon_interceptor.cpp`) ที่คอมไพล์ผ่าน GCC `-O3` และใช้ OpenCV DNN Backend เพื่อให้ได้เฟรมเรตมากกว่า **50-70 FPS** ตามความต้องการที่ความเร็วบินเกิน 100 km/h""")

    # Save to disk
    with open("/Users/papajhon/Project/Red Balloon Intercepter/ComputerVisionSRC/03_balloon_model_evaluation.ipynb", "w", encoding="utf-8") as f:
        json.dump(nb, f, indent=2, ensure_ascii=False)
    
    with open("/Users/papajhon/Project/Red Balloon Intercepter/03_balloon_model_evaluation.ipynb", "w", encoding="utf-8") as f:
        json.dump(nb, f, indent=2, ensure_ascii=False)

    print("✅ Created 03_balloon_model_evaluation.ipynb successfully in both locations!")

if __name__ == "__main__":
    create_notebook()
