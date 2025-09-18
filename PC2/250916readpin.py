#region: ------------------------- Import Libraries -------------------------
import sys
from pathlib import Path
import time
from ctypes import *

try:
    sys.path.append(str(Path(__file__).resolve().parent))
    from dwfconstants import *
except ImportError:
    print("dwfconstants.py not found. Make sure it's in the same directory or in the python path.")
    quit()
#endregion

#region: ------------------------- Configuration ----------------------------
# W1 핀으로 출력할 DC 전압을 설정합니다 (단위: Volt).
W1_VOLTAGE_TO_SET = 1.5

# 몇 초 간격으로 값을 읽어올지 설정합니다.
READ_INTERVAL_SECONDS = 0.5
#endregion

#region: ------------------------- DWF Library Setup ------------------------
try:
    if sys.platform.startswith("win"):
        dwf = cdll.dwf
    elif sys.platform.startswith("darwin"):
        dwf = cdll.LoadLibrary("/Library/Frameworks/dwf.framework/dwf")
    else:
        dwf = cdll.LoadLibrary("libdwf.so")
except OSError:
    print("DWF library not found. Please install WaveForms.")
    quit()

hdwf = c_int()
#endregion

#region: ------------------------- Main Logic -------------------------------
def read_voltages():
    """
    W1에 전압을 출력하고, 스코프 채널 1 (1+ vs 1-)의 전압을 지속적으로 읽어옵니다.
    """
    print("Opening first device...")
    if dwf.FDwfDeviceOpen(c_int(-1), byref(hdwf)) == 0:
        print("Failed to open device")
        return

    try:
        # 1. W1 (파형 발생기) 설정: 설정된 DC 전압을 출력합니다.
        print(f"Setting W1 output to {W1_VOLTAGE_TO_SET} V...")
        dwf.FDwfAnalogOutNodeEnableSet(hdwf, c_int(0), AnalogOutNodeCarrier, c_bool(True))
        dwf.FDwfAnalogOutNodeFunctionSet(hdwf, c_int(0), AnalogOutNodeCarrier, funcDC)
        dwf.FDwfAnalogOutNodeOffsetSet(hdwf, c_int(0), AnalogOutNodeCarrier, c_double(W1_VOLTAGE_TO_SET))
        dwf.FDwfAnalogOutConfigure(hdwf, c_int(0), c_bool(True))
        time.sleep(0.5) # 전압 안정화 대기

        # 2. 스코프 채널 1 (1+, 1-) 설정
        print("Configuring Scope Channel 1...")
        dwf.FDwfAnalogInChannelEnableSet(hdwf, c_int(0), c_bool(True))
        dwf.FDwfAnalogInChannelRangeSet(hdwf, c_int(0), c_double(5.0)) # +/- 5V 범위로 설정
        dwf.FDwfAnalogInConfigure(hdwf, c_bool(False), c_bool(False))
        time.sleep(0.5)

        print("\n--- Starting to read voltages ---")
        print("Press Ctrl+C to stop.")

        # 3. 무한 루프를 돌며 값 읽기 및 출력
        while True:
            # 새로운 측정을 위해 상태 확인
            dwf.FDwfAnalogInStatus(hdwf, c_bool(False), None) 
            
            # 스코프 채널 1의 샘플 값(차동 전압)을 저장할 변수
            v_scope1 = c_double()
            dwf.FDwfAnalogInStatusSample(hdwf, c_int(0), byref(v_scope1))
            
            # 터미널에 현재 값들을 출력 (\r을 이용해 한 줄에서 업데이트)
            print(f"\rSet W1: {W1_VOLTAGE_TO_SET:.3f} V   |   Measured (1+ vs 1-): {v_scope1.value:.4f} V  ", end="")
            
            time.sleep(READ_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print("\n\nMeasurement stopped by user.")
    finally:
        # 프로그램 종료 시 장치 리셋 및 연결 해제
        dwf.FDwfAnalogOutConfigure(hdwf, c_int(0), c_bool(False)) # 파형 발생기 정지
        dwf.FDwfDeviceCloseAll()
        print("Device closed.")

if __name__ == '__main__':
    read_voltages()
