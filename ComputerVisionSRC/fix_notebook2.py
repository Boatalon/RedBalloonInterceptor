import json
import os

nb_paths = [
    "/Users/papajhon/Project/Red Balloon Intercepter/ComputerVisionSRC/02_balloon_mobilenetv3_ssdlite_train_pi4.ipynb",
    "/Users/papajhon/Project/Red Balloon Intercepter/02_balloon_mobilenetv3_ssdlite_train_pi4.ipynb"
]

fixed_code = '''def build_high_speed_ssdlite(num_classes=4, img_size=224, trainable_backbone_layers=6):
    """
    สร้างโมเดล SSDLite MobileNetV3-Small ปรับจูนสำหรับ High Frame Rate (>50-70+ FPS) บน Raspberry Pi 4
    """
    from torchvision.models.detection._utils import retrieve_out_channels
    norm_layer = partial(nn.BatchNorm2d, eps=0.001, momentum=0.03)
    
    # 1. โหลด MobileNetV3-Small Pretrained Backbone (ใช้ reduced_tail=False เพื่อให้ตรงกับ Pretrained Weights)
    backbone = mobilenet_v3_small(
        weights=MobileNet_V3_Small_Weights.DEFAULT,
        norm_layer=norm_layer,
        reduced_tail=False
    )
    
    # 2. แปลงเป็น SSDLite Feature Extractor
    backbone = _mobilenet_extractor(backbone, trainable_layers=trainable_backbone_layers, norm_layer=norm_layer)
    
    # 3. กำหนด Default Anchor Generator (สเกลมาตรฐาน SSD 6 ระดับ)
    anchor_generator = DefaultBoxGenerator([[2, 3] for _ in range(6)], min_ratio=0.2, max_ratio=0.95)
    
    # 4. ดึงขนาด Out Channels อัตโนมัติด้วย retrieve_out_channels
    size = (img_size, img_size)
    out_channels = retrieve_out_channels(backbone, size)
    num_anchors = anchor_generator.num_anchors_per_location()
    
    # 5. สร้าง SSDLite Detection Head
    head = SSDLiteHead(out_channels, num_anchors, num_classes, norm_layer)
    
    # 6. ประกอบโมเดล SSD ขนาด 224x224
    defaults = {
        "score_thresh": 0.01,
        "nms_thresh": 0.45,
        "detections_per_img": 100,
        "topk_candidates": 200,
        "image_mean": [0.5, 0.5, 0.5],
        "image_std": [0.5, 0.5, 0.5],
    }
    model = SSD(
        backbone,
        anchor_generator,
        size,
        num_classes,
        head=head,
        **defaults
    )
    return model

model = build_high_speed_ssdlite(num_classes=NUM_CLASSES, img_size=IMG_SIZE)
model = model.to(device)

total_params = sum(p.numel() for p in model.parameters())
trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)

print(f"🏗️ สรุปโมเดล High-Speed SSDLite MobileNetV3-Small ({IMG_SIZE}x{IMG_SIZE}):")
print(f"• จำนวนพารามิเตอร์ทั้งหมด: {total_params:,} ตัว")
print(f"• พารามิเตอร์ที่ต้องเทรน: {trainable_params:,} ตัว")
print(f"• ขนาดโมเดลใน RAM: {total_params * 4 / (1024 * 1024):.2f} MB")
print(f"• คาดการณ์ความเร็วบน Pi 4: > 50-70+ FPS")
'''

fixed_source_lines = [line + "\n" for line in fixed_code.strip().split("\n")]

for path in nb_paths:
    with open(path, "r", encoding="utf-8") as f:
        nb = json.load(f)
        
    for cell in nb["cells"]:
        if cell["cell_type"] == "code":
            src = "".join(cell["source"])
            if "def build_high_speed_ssdlite" in src:
                cell["source"] = fixed_source_lines
                print(f"Patched build_high_speed_ssdlite in {path}")
                break
                
    with open(path, "w", encoding="utf-8") as f:
        json.dump(nb, f, indent=2, ensure_ascii=False)

print("Notebook 2 successfully updated with the fix!")
