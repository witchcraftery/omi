import camera
from machine import Pin, Timer

def main():
    try:
        # Initialize camera with 800x600 resolution
        cam = camera.init(0, format=camera.RGB565, framesize=camera.FRAME_SVGA)
        print(f"Camera initialized: {cam}")
        
        # Quick capture test
        buf = camera.capture()
        print(f"Captured {len(buf)} bytes")
        
        return True
    except Exception as e:
        print(f"Camera failed: {str(e)}")
        return False

if __name__ == "__main__":
    main() 