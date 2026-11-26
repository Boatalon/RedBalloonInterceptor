#!/usr/bin/env python3
"""
📊 Standalone Model Evaluation & Benchmarking Engine
====================================================
Evaluates the trained MobileNetV3-Small SSDLite model on the test dataset.
Computes comprehensive metrics:
- Precision, Recall, F1-Score (per class and overall)
- mAP@0.50 (PASCAL VOC metric)
- mAP@0.50:0.95 (COCO primary standard metric)
- Composite Overall Score
- Host Machine Inference Latency (ms) & FPS
- Confusion Matrix (TP, FP, FN)
"""

import os
import glob
import time
import json
import xml.etree.ElementTree as ET
from collections import defaultdict
from functools import partial

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image

import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
import torchvision
from torchvision.models import mobilenet_v3_small, MobileNet_V3_Small_Weights
from torchvision.models.detection.anchor_utils import DefaultBoxGenerator
from torchvision.models.detection.ssd import SSD
from torchvision.models.detection.ssdlite import SSDLiteHead, _mobilenet_extractor
from torchvision.models.detection._utils import retrieve_out_channels
import torchvision.transforms.functional as F

CLASSES = ["__background__", "red", "blue", "green"]
NUM_CLASSES = len(CLASSES)
EVAL_CLASSES = ["red", "blue", "green"] # Non-background target classes
CLASS_TO_IDX = {name: i for i, name in enumerate(CLASSES)}
IDX_TO_CLASS = {i: name for i, name in enumerate(CLASSES)}

CLASS_COLORS = {
    "red": "#e74c3c",
    "blue": "#3498db",
    "green": "#2ecc71"
}

DATASET_ROOT = "/Users/papajhon/Project/Red Balloon Intercepter/ComputerVisionSRC/balloon_dataset_stratified"
CHECKPOINT_PATH = "/Users/papajhon/Project/Red Balloon Intercepter/ComputerVisionSRC/best_balloon_ssdlite_mobilenetv3_small_224.pth"
IMG_SIZE = 224

device = torch.device("cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu"))

class TestDataset(Dataset):
    def __init__(self, data_dir, img_size=224):
        self.data_dir = data_dir
        self.img_size = img_size
        self.xml_files = sorted(glob.glob(os.path.join(data_dir, "*.xml")))
        self.img_files = [f.replace(".xml", ".jpg") for f in self.xml_files]

    def __len__(self):
        return len(self.xml_files)

    def __getitem__(self, idx):
        image = Image.open(self.img_files[idx]).convert("RGB")
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
        return img_tensor, {"boxes": boxes, "labels": labels, "filename": os.path.basename(self.img_files[idx])}

def collate_fn(batch):
    return tuple(zip(*batch))

def build_model(num_classes=4, img_size=224):
    norm_layer = partial(nn.BatchNorm2d, eps=0.001, momentum=0.03)
    backbone = mobilenet_v3_small(weights=None, norm_layer=norm_layer, reduced_tail=False)
    backbone = _mobilenet_extractor(backbone, trainable_layers=6, norm_layer=norm_layer)
    anchor_generator = DefaultBoxGenerator([[2, 3], [2, 3], [2, 3], [2, 3], [2], [2]], min_ratio=0.2, max_ratio=0.95)
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

def compute_iou(box1, box2):
    # box format: [xmin, ymin, xmax, ymax]
    xA = max(box1[0], box2[0])
    yA = max(box1[1], box2[1])
    xB = min(box1[2], box2[2])
    yB = min(box1[3], box2[3])

    interArea = max(0.0, xB - xA) * max(0.0, yB - yA)
    boxAArea = max(0.0, box1[2] - box1[0]) * max(0.0, box1[3] - box1[1])
    boxBArea = max(0.0, box2[2] - box2[0]) * max(0.0, box2[3] - box2[1])

    denom = boxAArea + boxBArea - interArea
    return interArea / denom if denom > 0 else 0.0

def evaluate_metrics(all_preds, all_gts, iou_thresholds=None, conf_threshold=0.40):
    if iou_thresholds is None:
        iou_thresholds = np.linspace(0.50, 0.95, 10) # [0.50, 0.55, ..., 0.95]

    # Map predictions and GTs per class
    # structure: {cls_id: [ {img_id, score, box} ]}
    results = {}
    per_class_summary = {}

    total_gt_all = 0
    total_tp_all = 0
    total_fp_all = 0
    total_fn_all = 0

    ap_per_class_all_iou = defaultdict(list)
    pr_curves_data = {}

    for cls_name in EVAL_CLASSES:
        cls_id = CLASS_TO_IDX[cls_name]
        
        # Gather all ground truths for this class across images
        gts_by_img = defaultdict(list)
        n_gt_class = 0
        for img_id, gt_dict in enumerate(all_gts):
            for b, l in zip(gt_dict["boxes"], gt_dict["labels"]):
                if l == cls_id:
                    gts_by_img[img_id].append({"box": b.tolist(), "matched": False})
                    n_gt_class += 1
        total_gt_all += n_gt_class

        # Gather all predictions for this class
        preds_class = []
        for img_id, pred_dict in enumerate(all_preds):
            for b, s, l in zip(pred_dict["boxes"], pred_dict["scores"], pred_dict["labels"]):
                if l == cls_id:
                    preds_class.append({"img_id": img_id, "score": float(s), "box": b.tolist()})

        # Sort predictions by score descending
        preds_class.sort(key=lambda x: x["score"], reverse=True)

        # Evaluate across IoU thresholds
        ap_list = []
        best_tp, best_fp, best_fn = 0, 0, 0

        for iou_idx, iou_thresh in enumerate(iou_thresholds):
            # Reset matched flags for this iou threshold
            current_gts = {img_id: [{"box": g["box"], "matched": False} for g in g_list] for img_id, g_list in gts_by_img.items()}
            tp = np.zeros(len(preds_class))
            fp = np.zeros(len(preds_class))

            for p_idx, pred in enumerate(preds_class):
                img_id = pred["img_id"]
                pred_box = pred["box"]
                best_match_iou = 0.0
                best_match_idx = -1

                if img_id in current_gts:
                    for g_idx, gt in enumerate(current_gts[img_id]):
                        if not gt["matched"]:
                            iou = compute_iou(pred_box, gt["box"])
                            if iou > best_match_iou:
                                best_match_iou = iou
                                best_match_idx = g_idx

                if best_match_iou >= iou_thresh and best_match_idx >= 0:
                    tp[p_idx] = 1
                    current_gts[img_id][best_match_idx]["matched"] = True
                else:
                    fp[p_idx] = 1

            # Accumulate TP and FP
            tp_cum = np.cumsum(tp)
            fp_cum = np.cumsum(fp)
            recalls = tp_cum / max(n_gt_class, 1)
            precisions = tp_cum / np.maximum(tp_cum + fp_cum, np.finfo(np.float64).eps)

            # Compute AP using 101-point interpolation (COCO/VOC standard)
            ap = 0.0
            for r in np.linspace(0, 1.0, 101):
                prec_at_r = precisions[recalls >= r]
                ap += np.max(prec_at_r) if len(prec_at_r) > 0 else 0.0
            ap /= 101.0
            ap_list.append(ap)

            # Store for IoU=0.50 (VOC benchmark)
            if abs(iou_thresh - 0.50) < 1e-4:
                ap_50 = ap
                pr_curves_data[cls_name] = {"recall": recalls.tolist(), "precision": precisions.tolist()}
                
                # Count TP, FP, FN at operational confidence threshold
                op_tp = 0
                op_fp = 0
                for p_idx, pred in enumerate(preds_class):
                    if pred["score"] >= conf_threshold:
                        if tp[p_idx] == 1:
                            op_tp += 1
                        else:
                            op_fp += 1
                op_fn = n_gt_class - op_tp
                best_tp, best_fp, best_fn = op_tp, op_fp, max(0, op_fn)

        ap_per_class_all_iou[cls_name] = ap_list
        ap_50_95 = float(np.mean(ap_list))

        prec = best_tp / (best_tp + best_fp) if (best_tp + best_fp) > 0 else 0.0
        rec = best_tp / (best_tp + best_fn) if (best_tp + best_fn) > 0 else 0.0
        f1 = 2 * (prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0

        per_class_summary[cls_name] = {
            "gt_count": n_gt_class,
            "tp": best_tp,
            "fp": best_fp,
            "fn": best_fn,
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1": round(f1, 4),
            "ap50": round(ap_50, 4),
            "ap50_95": round(ap_50_95, 4)
        }

        total_tp_all += best_tp
        total_fp_all += best_fp
        total_fn_all += best_fn

    # Overall Summary
    overall_prec = total_tp_all / (total_tp_all + total_fp_all) if (total_tp_all + total_fp_all) > 0 else 0.0
    overall_rec = total_tp_all / (total_tp_all + total_fn_all) if (total_tp_all + total_fn_all) > 0 else 0.0
    overall_f1 = 2 * (overall_prec * overall_rec) / (overall_prec + overall_rec) if (overall_prec + overall_rec) > 0 else 0.0

    mean_ap50 = float(np.mean([v["ap50"] for v in per_class_summary.values()]))
    mean_ap50_95 = float(np.mean([v["ap50_95"] for v in per_class_summary.values()]))

    # Composite Overall Score (Harmonic Mean of mAP50, mAP50-95, and F1)
    composite_score = (3.0 * mean_ap50 * mean_ap50_95 * overall_f1) / (
        mean_ap50 * mean_ap50_95 + mean_ap50 * overall_f1 + mean_ap50_95 * overall_f1 + 1e-6
    )

    summary = {
        "overall": {
            "total_ground_truth": total_gt_all,
            "total_tp": total_tp_all,
            "total_fp": total_fp_all,
            "total_fn": total_fn_all,
            "precision": round(overall_prec, 4),
            "recall": round(overall_rec, 4),
            "f1_score": round(overall_f1, 4),
            "mAP50": round(mean_ap50, 4),
            "mAP50_95": round(mean_ap50_95, 4),
            "composite_score": round(composite_score, 4),
            "conf_threshold_used": conf_threshold
        },
        "per_class": per_class_summary,
        "pr_curves": pr_curves_data
    }
    return summary

def main():
    print("=" * 75)
    print("🚀 RED BALLOON INTERCEPTOR - DEDICATED MODEL EVALUATION & BENCHMARK")
    print(f"• Dataset:        {DATASET_ROOT}/test")
    print(f"• Model Weights:  {CHECKPOINT_PATH}")
    print(f"• Target Classes: {EVAL_CLASSES} (Red Balloon Priority)")
    print(f"• Resolution:     {IMG_SIZE}x{IMG_SIZE}")
    print("=" * 75)

    if not os.path.exists(CHECKPOINT_PATH):
        print(f"❌ Checkpoint file not found: {CHECKPOINT_PATH}")
        return

    # Load Model
    print("\n[1/4] Loading model checkpoint...")
    model = build_model(num_classes=NUM_CLASSES, img_size=IMG_SIZE)
    ckpt = torch.load(CHECKPOINT_PATH, map_location=device)
    model.load_state_dict(ckpt["model_state_dict"])
    model.to(device)
    model.eval()
    print(f"✅ Checkpoint loaded from Epoch {ckpt.get('epoch', 'N/A')} (Val Loss: {ckpt.get('val_loss', 'N/A'):.4f})")

    # Load Test Dataset
    print("\n[2/4] Loading test dataset...")
    test_ds = TestDataset(os.path.join(DATASET_ROOT, "test"), img_size=IMG_SIZE)
    test_loader = DataLoader(test_ds, batch_size=1, shuffle=False, collate_fn=collate_fn)
    print(f"✅ Loaded {len(test_ds)} test images.")

    # Run Benchmark & Predictions
    print("\n[3/4] Running inference & latency benchmark on host machine...")
    latencies = []
    forward_times = []
    all_preds = []
    all_gts = []

    # Warmup 5 images
    with torch.no_grad():
        for i in range(min(5, len(test_ds))):
            im, _ = test_ds[i]
            _ = model([im.to(device)])

    with torch.no_grad():
        for images, targets in test_loader:
            im = images[0].to(device)
            gt = targets[0]

            t0 = time.perf_counter()
            pred = model([im])[0]
            t1 = time.perf_counter()

            total_ms = (t1 - t0) * 1000.0
            latencies.append(total_ms)

            # Move pred to cpu numpy
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

    # Host Machine Performance Statistics
    mean_lat = np.mean(latencies)
    std_lat = np.std(latencies)
    p50_lat = np.percentile(latencies, 50)
    p95_lat = np.percentile(latencies, 95)
    p99_lat = np.percentile(latencies, 99)
    fps_host = 1000.0 / mean_lat

    # Calculate Object Detection Metrics
    print("\n[4/4] Computing Precision, Recall, F1, mAP@50, mAP@50-95...")
    eval_res = evaluate_metrics(all_preds, all_gts, conf_threshold=0.40)
    ov = eval_res["overall"]

    # Print Formatted Results Table
    print("\n" + "=" * 78)
    print(f"{'CLASS EVALUATION METRICS':<20} | {'PREC':<8} | {'REC':<8} | {'F1':<8} | {'mAP@50':<8} | {'mAP@50-95':<10}")
    print("=" * 78)
    for c_name, c_data in eval_res["per_class"].items():
        print(f"{c_name.upper():<20} | {c_data['precision']*100:>7.1f}% | {c_data['recall']*100:>7.1f}% | {c_data['f1']*100:>7.1f}% | {c_data['ap50']*100:>7.1f}% | {c_data['ap50_95']*100:>9.1f}%")
    print("-" * 78)
    print(f"{'OVERALL (ALL CLASSES)':<20} | {ov['precision']*100:>7.1f}% | {ov['recall']*100:>7.1f}% | {ov['f1_score']*100:>7.1f}% | {ov['mAP50']*100:>7.1f}% | {ov['mAP50_95']*100:>9.1f}%")
    print("=" * 78)
    print(f"⭐ COMPOSITE OVERALL SCORE:  {ov['composite_score']*100:.2f} / 100")
    print("=" * 78)

    print("\n" + "=" * 78)
    print("💻 HOST MACHINE PERFORMANCE BENCHMARK (This Machine)")
    print("=" * 78)
    print(f"• Hardware Device:         {device.type.upper()}")
    print(f"• Average Inference FPS:   {fps_host:.1f} FPS")
    print(f"• Mean Total Latency:      {mean_lat:.2f} ms")
    print(f"• Median Latency (P50):    {p50_lat:.2f} ms")
    print(f"• 95th Percentile (P95):   {p95_lat:.2f} ms")
    print(f"• 99th Percentile (P99):   {p99_lat:.2f} ms")
    print(f"• Jitter Stability (Std):  {std_lat:.2f} ms")
    print("=" * 78)

    # Save Results JSON
    output_json = "/Users/papajhon/Project/Red Balloon Intercepter/ComputerVisionSRC/model_evaluation_report.json"
    eval_res["host_performance"] = {
        "device": device.type,
        "mean_latency_ms": round(mean_lat, 2),
        "median_latency_ms": round(p50_lat, 2),
        "p95_latency_ms": round(p95_lat, 2),
        "p99_latency_ms": round(p99_lat, 2),
        "fps": round(fps_host, 1),
        "std_jitter_ms": round(std_lat, 2)
    }
    with open(output_json, "w") as f:
        json.dump(eval_res, f, indent=2)
    print(f"\n📄 Saved detailed JSON report: {output_json}")

    # Plot Precision-Recall Curves
    try:
        fig, ax = plt.subplots(figsize=(8, 6))
        for c_name, pr in eval_res["pr_curves"].items():
            if len(pr["recall"]) > 0:
                ax.plot(pr["recall"], pr["precision"], label=f"{c_name.capitalize()} (AP50={eval_res['per_class'][c_name]['ap50']*100:.1f}%)",
                        color=CLASS_COLORS.get(c_name, "blue"), linewidth=2.5)
        ax.set_title("Precision-Recall Curves @ IoU=0.50 (Test Set)", fontsize=14, fontweight="bold")
        ax.set_xlabel("Recall", fontsize=12)
        ax.set_ylabel("Precision", fontsize=12)
        ax.set_xlim([0.0, 1.05])
        ax.set_ylim([0.0, 1.05])
        ax.grid(True, linestyle="--", alpha=0.6)
        ax.legend(fontsize=11)
        plot_path = "/Users/papajhon/Project/Red Balloon Intercepter/ComputerVisionSRC/precision_recall_curves.png"
        plt.tight_layout()
        plt.savefig(plot_path, dpi=200)
        print(f"📈 Saved Precision-Recall Curves Plot: {plot_path}")
    except Exception as e:
        print(f"Plotting note: {e}")

if __name__ == "__main__":
    main()
