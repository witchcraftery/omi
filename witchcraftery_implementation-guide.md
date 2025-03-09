# Witchcraftery Implementation Guide
[![Progress](witchcraftery_progress-report.md)](https://github.com/witchcraftery/omi/blob/main/witchcraftery_progress-report.md)

**Current Status:**  
✅ Phase 0 Completed | 🚧 Phase 1 In Progress | ⏳ Phase 2-4 Planned

## Phase 0: Base System Establishment
1. **Hardware Unboxing & Validation**
   - [ ] ESP32-S3-Sense Checklist:
     ```python
     # Quick hardware test script
     from machine import Pin, Camera
     cam = Camera(0)
     print(f"Camera detected: {cam.init()}")
     # Expected output: Camera detected: True
     ```
   - [ ] Omi Dev2 Kit Baseline Flashing
     ```bash
     esptool.py --port /dev/cu.usbserial-14320 write_flash 0x0 firmware/omi-base.bin
     ```

2. **iOS App Fork Customization**
   ```swift:ios/OmiApp/AppDelegate.swift
   // Change bundle identifier immediately
   let appBundleID = "com.witchcraftery.omi"  // Original: com.basedhardware.omi
   ```

## Phase 1: Baseline Operation

### Hardware Adaptation
```cpp:firmware/main/config.h
// ESP32-S3-Sense specific pin mapping
#define MIC_PIN       12    // Original: 35
#define BUTTON_PIN    38    // Added for camera control
#define CAMERA_PWR    4     // New camera power control
```

### iOS App First-Run Customization
```swift:ios/Settings/FeatureFlags.swift
// Initial customization points
struct FeatureFlags {
  static let enableCameraSync = false  // Phase 3
  static let maxRecordingHours = 18.0  // Original: 12.0
}
```

**Phase 2: Personalization Layer

### Visual Identity Overrides
```swift:ios/Theme/ColorAssets.swift
// Branding quick wins
enum AppColors {
  static let primary = Color(hex: "#7D4CDB")  // Original: #2563EB
  static let recordingIndicator = Color.red  // Phase: Immediate
}
```

### Transcription Customization
```python:server/transcription/pipeline.py
# Adjust for personal speech patterns
CUSTOM_TERMS = {
  "witchcraftery": 0.9,  # Boost recognition of brand terms
  "athame": 0.7         # Custom vocabulary injection
}
```

**Phase 3: Vision Integration

### Camera Activation Sequence
```cpp:firmware/camera/camera_driver.c
// ESP32-S3-Sense specific init
void init_camera() {
  // Configure for 800x600 RGB565
  camera_config_t config;
  config.pin_pwdn = CAMERA_PWR;
  config.frame_size = FRAMESIZE_SVGA;
  // ... [full config]
}
```

### Image Processing Hook
```swift:ios/Services/ImageProcessor.swift
// New vision pipeline
func processCameraFrame(_ buffer: CVPixelBuffer) -> VisionAnalysis {
  // Phase: Add ML model integration here
}
```

**Phase 4: Extension Ecosystem**  

### New Extension Type Template
```swift:ios/Extensions/VisionExtension.swift
protocol VisionExtension: OmiExtension {
  var visualAnalysisThreshold: Float { get }
  func processVisualContext(_ frame: VisionAnalysis) 
}

// Example implementation stub
class ObjectTrackerExtension: VisionExtension {
  func triggerCondition(_ memory: OmiMemory) -> Bool {
    return memory.containsVisualObjects([.book, .coffeeCup])
  }
}
```