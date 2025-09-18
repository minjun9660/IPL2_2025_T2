# 파일 맨 위 (기존 import들보다 먼저)
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent / "py"))
from dwfconstants import *
import time
from ctypes import *

# WaveForms SDK 라이브러리 로드
dwf = cdll.dwf
hdwf = c_int()

print("Opening first device...")
if dwf.FDwfDeviceOpen(c_int(-1), byref(hdwf)) == 0:
    print("Failed to open device")
    quit()

# DIO-0 핀을 출력으로 활성화
dwf.FDwfDigitalIOOutputEnableSet(hdwf, c_uint(0x01))  # bitmask: 0x01 = DIO-0
dwf.FDwfDigitalIOConfigure(hdwf)

print("Blinking external LED on DIO-0... Press Ctrl+C to stop")

try:
    while True:
        # LED ON
        dwf.FDwfDigitalIOOutputSet(hdwf, c_uint(0x01))
        dwf.FDwfDigitalIOConfigure(hdwf)
        time.sleep(0.5)

        # LED OFF
        dwf.FDwfDigitalIOOutputSet(hdwf, c_uint(0x00))
        dwf.FDwfDigitalIOConfigure(hdwf)
        time.sleep(0.5)

except KeyboardInterrupt:
    print("Stopped by user")

# 장치 닫기
dwf.FDwfDeviceClose(hdwf)
