# ==============================================================================
# Makefile for Red Balloon Interceptor (Raspberry Pi 4 Native C++ Build)
# ==============================================================================
# Target: ARMv8 Cortex-A72 Optimization (Raspberry Pi 4 / Pi 400 / CM4)
# ==============================================================================

CXX = g++
CXXFLAGS = -O3 -std=c++14 -pthread -Wall \
           -march=armv8-a+crc -mtune=cortex-a72 \
           `pkg-config --cflags opencv4 2>/dev/null || pkg-config --cflags opencv`

LDFLAGS = `pkg-config --libs opencv4 2>/dev/null || pkg-config --libs opencv`

TARGET = pi4_balloon_interceptor
SRC = pi4_balloon_interceptor.cpp

all: $(TARGET)

$(TARGET): $(SRC)
	$(CXX) $(CXXFLAGS) $(SRC) -o $(TARGET) $(LDFLAGS)
	@echo "=========================================================="
	@echo "✅ Build completed successfully: ./$(TARGET)"
	@echo "Run: ./$(TARGET) --model balloon_ssdlite_mobilenetv3_small_224.onnx"
	@echo "=========================================================="

benchmark: $(TARGET)
	./$(TARGET) --benchmark --frames 300

clean:
	rm -f $(TARGET) *.o

.PHONY: all clean benchmark
