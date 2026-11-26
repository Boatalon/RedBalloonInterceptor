import os
import glob
import time
import xml.etree.ElementTree as ET
from functools import partial
import numpy as np
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
CLASS_TO_IDX = {name: i for i, name in enumerate(CLASSES)}
IDX_TO_CLASS = {i: name for i, name in enumerate(CLASSES)}

DATASET_ROOT = "/Users/papajhon/Project/Red Balloon Intercepter/ComputerVisionSRC/balloon_dataset_stratified"
IMG_SIZE = 224
BATCH_SIZE = 8
EPOCHS = 15
LR = 0.0005

device = torch.device("cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu"))
print(f"Training on device: {device}")

class BalloonVOCDataset(Dataset):
    def __init__(self, data_dir, img_size=224, is_train=True):
        self.data_dir = data_dir
        self.img_size = img_size
        self.is_train = is_train
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

        if len(boxes) > 0:
            boxes = torch.as_tensor(boxes, dtype=torch.float32)
            labels = torch.as_tensor(labels, dtype=torch.int64)
        else:
            boxes = torch.zeros((0, 4), dtype=torch.float32)
            labels = torch.zeros((0,), dtype=torch.int64)

        if self.is_train and np.random.rand() > 0.5:
            image = F.hflip(image)
            if len(boxes) > 0:
                new_xmin = orig_w - boxes[:, 2]
                new_xmax = orig_w - boxes[:, 0]
                boxes[:, 0] = new_xmin
                boxes[:, 2] = new_xmax

        scale_x = self.img_size / orig_w
        scale_y = self.img_size / orig_h
        image = image.resize((self.img_size, self.img_size), Image.Resampling.BILINEAR)
        if len(boxes) > 0:
            boxes[:, [0, 2]] *= scale_x
            boxes[:, [1, 3]] *= scale_y

        img_tensor = F.to_tensor(image)
        target = {
            "boxes": boxes,
            "labels": labels,
            "image_id": torch.tensor([idx]),
            "area": (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1]) if len(boxes) > 0 else torch.zeros((0,)),
            "iscrowd": torch.zeros((len(boxes),), dtype=torch.int64)
        }
        return img_tensor, target

def collate_fn(batch):
    return tuple(zip(*batch))

def build_model(num_classes=4, img_size=224):
    norm_layer = partial(nn.BatchNorm2d, eps=0.001, momentum=0.03)
    backbone = mobilenet_v3_small(weights=MobileNet_V3_Small_Weights.DEFAULT, norm_layer=norm_layer, reduced_tail=False)
    backbone = _mobilenet_extractor(backbone, trainable_layers=6, norm_layer=norm_layer)
    anchor_generator = DefaultBoxGenerator([[2, 3] for _ in range(6)], min_ratio=0.2, max_ratio=0.95)
    size = (img_size, img_size)
    out_channels = retrieve_out_channels(backbone, size)
    num_anchors = anchor_generator.num_anchors_per_location()
    head = SSDLiteHead(out_channels, num_anchors, num_classes, norm_layer)
    defaults = {
        "score_thresh": 0.01,
        "nms_thresh": 0.45,
        "detections_per_img": 100,
        "topk_candidates": 200,
        "image_mean": [0.5, 0.5, 0.5],
        "image_std": [0.5, 0.5, 0.5],
    }
    model = SSD(backbone, anchor_generator, size, num_classes, head=head, **defaults)
    return model

train_dataset = BalloonVOCDataset(os.path.join(DATASET_ROOT, "train"), img_size=IMG_SIZE, is_train=True)
val_dataset = BalloonVOCDataset(os.path.join(DATASET_ROOT, "val"), img_size=IMG_SIZE, is_train=False)

train_loader = DataLoader(train_dataset, batch_size=BATCH_SIZE, shuffle=True, collate_fn=collate_fn)
val_loader = DataLoader(val_dataset, batch_size=BATCH_SIZE, shuffle=False, collate_fn=collate_fn)

model = build_model(num_classes=NUM_CLASSES, img_size=IMG_SIZE).to(device)
optimizer = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=1e-4)
scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=EPOCHS, eta_min=1e-6)

checkpoint_path = "/Users/papajhon/Project/Red Balloon Intercepter/ComputerVisionSRC/best_balloon_ssdlite_mobilenetv3_small_224.pth"
root_checkpoint_path = "/Users/papajhon/Project/Red Balloon Intercepter/best_balloon_ssdlite_mobilenetv3_small_224.pth"

best_val_loss = float("inf")
print(f"Starting training for {EPOCHS} epochs...")

for epoch in range(1, EPOCHS + 1):
    t0 = time.time()
    model.train()
    train_loss = 0.0
    for images, targets in train_loader:
        images = [im.to(device) for im in images]
        targets = [{k: v.to(device) for k, v in t.items()} for t in targets]
        optimizer.zero_grad()
        loss_dict = model(images, targets)
        loss = sum(l for l in loss_dict.values())
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 10.0)
        optimizer.step()
        train_loss += loss.item()
    scheduler.step()
    train_loss /= len(train_loader)

    model.train() # use train mode with torch.no_grad to compute validation loss
    val_loss = 0.0
    with torch.no_grad():
        for images, targets in val_loader:
            images = [im.to(device) for im in images]
            targets = [{k: v.to(device) for k, v in t.items()} for t in targets]
            loss_dict = model(images, targets)
            val_loss += sum(l for l in loss_dict.values()).item()
    val_loss /= len(val_loader)
    elapsed = time.time() - t0

    print(f"Epoch {epoch:02d}/{EPOCHS} [{elapsed:.1f}s] - Train Loss: {train_loss:.4f} | Val Loss: {val_loss:.4f}")

    if val_loss < best_val_loss:
        best_val_loss = val_loss
        ckpt = {
            "epoch": epoch,
            "model_state_dict": model.state_dict(),
            "val_loss": val_loss,
            "classes": CLASSES,
            "img_size": IMG_SIZE
        }
        torch.save(ckpt, checkpoint_path)
        torch.save(ckpt, root_checkpoint_path)

print(f"Training completed! Best Val Loss: {best_val_loss:.4f}")

# Export ONNX
model.eval().to("cpu")
dummy_input = torch.randn(1, 3, IMG_SIZE, IMG_SIZE)
onnx_path = "/Users/papajhon/Project/Red Balloon Intercepter/ComputerVisionSRC/balloon_ssdlite_mobilenetv3_small_224.onnx"
torch.onnx.export(
    model, dummy_input, onnx_path,
    export_params=True, opset_version=14, do_constant_folding=True,
    input_names=["input"], output_names=["boxes", "scores", "labels"],
    dynamic_axes={"input": {0: "batch_size"}}
)
print(f"Exported ONNX model to {onnx_path}")
