#region: ------------------------- Import Libraries -------------------------
import sys
from pathlib import Path
import time
from ctypes import *
import numpy as np
import matplotlib.pyplot as plt

try:
    # dwfconstants.py 파일이 같은 폴더에 있는지 확인합니다.
    sys.path.append(str(Path(__file__).resolve().parent))
    from dwfconstants import *
except ImportError:
    print("dwfconstants.py not found. Make sure it's in the same directory.")
    quit()
#endregion

#region: ------------------------- Configuration ----------------------------
# 회로에 사용한 전류 제한 저항의 정확한 값을 Ohm 단위로 입력하세요.
R_LIMIT = 100.0

# 파형 발생기 설정
V_START = 0.0  # 스윕 시작 전압 (V)
V_END = 3.3   # 스윕 종료 전압 (V). 파란색/흰색 LED를 위해 4V로 설정.
SWEEP_TIME = 5.0 # 스윕에 걸리는 시간 (초)

# 스코프 설정
SAMPLING_FREQ = 10000.0 # 샘플링 주파수 (Hz)
BUFFER_SIZE = int(SAMPLING_FREQ * SWEEP_TIME) # 버퍼 크기
#endregion

#region: ------------------------- DWF Library Setup ------------------------
try:
    if sys.platform.startswith("win"):
        dwf = cdll.dwf
    else:
        dwf = cdll.LoadLibrary("libdwf.so")
except OSError:
    print("DWF library not found. Please install WaveForms.")
    quit()

hdwf = c_int()
sts = c_byte()
#endregion

#region: ------------------------- Main Logic -------------------------------
def measure_led_iv_curve():
    """
    전압을 스윕하며 LED의 전압과 전류를 측정하여 I-V 데이터를 반환합니다.
    """
    print("Opening first device...")
    if dwf.FDwfDeviceOpen(c_int(-1), byref(hdwf)) == 0:
        print("Failed to open device")
        return None, None

    try:
        # 1. 파형 발생기(W1) 설정: 램프 신호(0V -> 4V)
        dwf.FDwfAnalogOutNodeEnableSet(hdwf, c_int(0), AnalogOutNodeCarrier, c_bool(True))
        dwf.FDwfAnalogOutNodeFunctionSet(hdwf, c_int(0), AnalogOutNodeCarrier, funcRampUp)
        dwf.FDwfAnalogOutNodeFrequencySet(hdwf, c_int(0), AnalogOutNodeCarrier, c_double(1.0 / SWEEP_TIME))
        # Offset과 Amplitude를 조절하여 0V ~ 4V 램프 생성
        dwf.FDwfAnalogOutNodeOffsetSet(hdwf, c_int(0), AnalogOutNodeCarrier, c_double((V_END - V_START) / 2))
        dwf.FDwfAnalogOutNodeAmplitudeSet(hdwf, c_int(0), AnalogOutNodeCarrier, c_double((V_END - V_START) / 2))
        
        # 2. 스코프(CH1, CH2) 설정
        dwf.FDwfAnalogInChannelEnableSet(hdwf, c_int(0), c_bool(True)) # CH1 (V_led)
        dwf.FDwfAnalogInChannelEnableSet(hdwf, c_int(1), c_bool(True)) # CH2 (V_in, W1 전압)
        dwf.FDwfAnalogInChannelRangeSet(hdwf, c_int(0), c_double(5.0))
        dwf.FDwfAnalogInChannelRangeSet(hdwf, c_int(1), c_double(5.0))
        dwf.FDwfAnalogInFrequencySet(hdwf, c_double(SAMPLING_FREQ))
        dwf.FDwfAnalogInBufferSizeSet(hdwf, c_int(BUFFER_SIZE))
        
        # 트리거 설정: W1 신호가 시작될 때 측정 시작
        dwf.FDwfAnalogInTriggerSourceSet(hdwf, trigsrcAnalogOut1)
        dwf.FDwfAnalogInTriggerTypeSet(hdwf, trigtypeEdge)
        # <<< 수정된 부분: 'trigcondRising' 대신 실제 값인 0을 사용합니다.
        dwf.FDwfAnalogInTriggerConditionSet(hdwf, c_int(0))
        dwf.FDwfAnalogInTriggerLevelSet(hdwf, c_double(0.1)) # 0.1V를 넘을 때 트리거

        # 3. 측정 시작
        print("Starting measurement...")
        dwf.FDwfAnalogOutConfigure(hdwf, c_int(0), c_bool(True))
        time.sleep(0.1)
        dwf.FDwfAnalogInConfigure(hdwf, c_bool(True), c_bool(True))
        
        while True:
            dwf.FDwfAnalogInStatus(hdwf, c_int(1), byref(sts))
            if sts.value == stsDone.value:
                break
            time.sleep(0.1)

        print("Measurement complete. Acquiring data...")

        # 4. 데이터 수집
        buffer_ch1 = (c_double * BUFFER_SIZE)() # V_led
        buffer_ch2 = (c_double * BUFFER_SIZE)() # V_in
        dwf.FDwfAnalogInStatusData(hdwf, c_int(0), buffer_ch1, BUFFER_SIZE)
        dwf.FDwfAnalogInStatusData(hdwf, c_int(1), buffer_ch2, BUFFER_SIZE)

        # 5. 데이터 처리
        v_led = np.frombuffer(buffer_ch1, dtype=np.float64)
        v_in = np.frombuffer(buffer_ch2, dtype=np.float64)

        # 저항 양단 전압을 계산하고, 이를 이용해 전류 계산
        v_resistor = v_in - v_led
        i_led = v_resistor / R_LIMIT

        # 노이즈가 심한 초기/종료 부분 데이터 일부 제거
        return v_led[100:-100], i_led[100:-100]

    except KeyboardInterrupt:
        print("\nMeasurement stopped by user.")
        return None, None
    finally:
        dwf.FDwfAnalogOutConfigure(hdwf, c_int(0), c_bool(False))
        dwf.FDwfDeviceCloseAll()
        print("Device closed.")

def plot_iv_curve(v_led, i_led, led_color="Red"):
    """
    측정된 전압, 전류 데이터를 받아 I-V 커브 그래프를 그립니다.
    """
    if v_led is None or i_led is None:
        print("No data to plot.")
        return

    # 전류 단위를 mA로 변환
    i_led_mA = i_led * 1000

    plt.figure(figsize=(10, 6))
    plt.plot(v_led, i_led_mA, 'o-', markersize=2, label=f'{led_color} LED Measured Data')
    
    # <<< 수정된 부분: 문턱 전압 시각화 코드를 제거했습니다.

    plt.title(f'{led_color} LED I-V Characteristic Curve', fontsize=16)
    plt.xlabel('LED Voltage (V)', fontsize=12)
    plt.ylabel('LED Current (mA)', fontsize=12)
    plt.grid(True)
    plt.legend()
    plt.ylim(bottom=-0.01) # Y축 하한을 약간 내려서 0이 잘 보이도록 함
    plt.xlim(left=0)   # X축 하한을 0으로 설정
    plt.show()

if __name__ == '__main__':
    # 이 부분에 실험하는 LED 색상을 입력해주세요. (그래프 제목에 사용됩니다)
    LED_COLOR_NAME = "Blue" 
    
    voltage_data, current_data = measure_led_iv_curve()
    if voltage_data is not None:
        plot_iv_curve(voltage_data, current_data, led_color=LED_COLOR_NAME)

