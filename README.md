# 🎈 RedBalloonInterceptor

High-speed target interception and autonomous vision tracking system for drones operating at speeds exceeding **100 km/h** (~27.8 m/s), deployed on **Raspberry Pi 4 (Quad-Core Cortex-A72)**.

---

## 📌 Architecture Overview

1. **Computer Vision Model:**
   - **Backbone:** MobileNetV3-Small (Pretrained ImageNet, reduced tail disabled for weight compatibility)
   - **Detection Head:** SSDLite with depthwise separable convolutions
   - **Resolution:** 224x224 (optimizing latency and FLOPs for edge inference)
   - **Target Classes:** `red` (priority target), `blue`, `green`
   - **Quantization:** INT8 Post-Training Quantization for Raspberry Pi 4

2. **Kinematic & Control Constraints:**
   - **Flight Speed:** $> 100 \text{ km/h} \approx 27.78 \text{ m/s}$
   - **Latency Budget:** $\le 16.6 \text{ ms}$ ($\ge 60 \text{ FPS}$)
   - **Lead-Aiming Motion Predictor:** Compensates for $25 \text{ ms}$ processing + actuator lag
   - **C++ Native Engine:** Zero garbage-collection latency spikes, deterministic sub-millisecond execution

---

## 📂 Repository Structure

```
RedBalloonInterceptor/
├── 01_dataset_deduplication_and_stratified_split.ipynb # Data deduplication & 80:10:10 stratified split
├── 02_balloon_mobilenetv3_ssdlite_train_pi4.ipynb       # Model architecture, training & INT8 export
├── 03_balloon_model_evaluation.ipynb                   # Pure evaluation & benchmark notebook
├── eval_balloon_model.py                               # Standalone CLI evaluation script
├── benchmark_py_vs_cpp.py                              # Benchmark comparison tool (Python vs C++)
├── pi4_balloon_interceptor.cpp                         # C++ Native real-time inference engine
├── pi4_balloon_interceptor.py                          # Python baseline inference script
├── Makefile / CMakeLists.txt                           # C++ optimized build system
├── requirements.txt                                    # Python dependencies
├── best_balloon_ssdlite_mobilenetv3_small_224.pth      # Trained PyTorch checkpoint
├── model_evaluation_report.json                        # Comprehensive test metrics
├── precision_recall_curves.png                         # PR curves plot
├── ComputerVisionSRC/                                  # Datasets & source scripts
└── red-balloon-interceptor/                            # Simulation worlds, SITL & physics analysis
```

---

## 🚀 Quick Start Guide

### 1. Python Environment Setup
```bash
# Clone the repository
git clone https://github.com/Boatalon/RedBalloonInterceptor.git
cd RedBalloonInterceptor

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install required dependencies
pip install -r requirements.txt
```

### 2. Run Model Evaluation
```bash
# Evaluate checkpoint on test set
python eval_balloon_model.py

# Or launch Jupyter Notebook
jupyter notebook 03_balloon_model_evaluation.ipynb
```

### 3. Compile C++ Native Engine (for Raspberry Pi 4 / Linux / macOS)
```bash
# Build using Makefile (with Cortex-A72 / CPU optimization)
make

# Run the native interceptor
./pi4_balloon_interceptor_bin
```

---

## 📊 Evaluation Results (Test Dataset)

| Class | Precision | Recall | F1-Score | mAP@50 | mAP@50-95 |
| :--- | :---: | :---: | :---: | :---: | :---: |
| 🔴 **RED (Priority)** | **100.0%** | **100.0%** | **100.0%** | **100.0%** | **79.4%** |
| 🔵 **BLUE** | **93.3%** | **100.0%** | **96.5%** | **100.0%** | **72.6%** |
| 🟢 **GREEN** | **100.0%** | **100.0%** | **100.0%** | **100.0%** | **84.0%** |
| ⭐ **OVERALL** | **97.6%** | **100.0%** | **98.8%** | **100.0%** | **78.7%** |

- **Composite Overall Score:** **91.37 / 100**
