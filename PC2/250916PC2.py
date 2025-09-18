#region: ------------------------- Import Libraries -------------------------
import sys
from pathlib import Path
import time
from ctypes import *
import numpy as np
import matplotlib.pyplot as plt

try:
    sys.path.append(str(Path(__file__).resolve().parent))
    from dwfconstants import *
except ImportError:
    print("dwfconstants.py not found. Make sure it's in the same directory.")
    quit()
#endregion

#region: ------------------------- Configuration ----------------------------
# W1 핀으로 출력할 DC 전압 (단위: Volt)
W1_VOLTAGE_TO_SET = 3.3

# 측정할 횟수 (많을수록 통계가 정확해집니다)
N_SAMPLES = 500
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
def measure_and_plot_w1():
    """
    W1 출력을 N회 측정하여 통계를 내고 히스토그램을 플롯합니다.
    """
    print("Opening first device...")
    if dwf.FDwfDeviceOpen(c_int(-1), byref(hdwf)) == 0:
        print("Failed to open device")
        return

    measured_voltages = []

    try:
        # 1. W1 (파형 발생기) 설정
        print(f"Setting W1 output to {W1_VOLTAGE_TO_SET} V...")
        dwf.FDwfAnalogOutNodeEnableSet(hdwf, c_int(0), AnalogOutNodeCarrier, c_bool(True))
        dwf.FDwfAnalogOutNodeFunctionSet(hdwf, c_int(0), AnalogOutNodeCarrier, funcDC)
        dwf.FDwfAnalogOutNodeOffsetSet(hdwf, c_int(0), AnalogOutNodeCarrier, c_double(W1_VOLTAGE_TO_SET))
        dwf.FDwfAnalogOutConfigure(hdwf, c_int(0), c_bool(True))
        time.sleep(0.5)

        # 2. 스코프 채널 1 (1+, 1-) 설정
        print("Configuring Scope Channel 1...")
        dwf.FDwfAnalogInChannelEnableSet(hdwf, c_int(0), c_bool(True))
        # 측정 범위를 출력 전압에 맞게 자동으로 조절하면 더 정밀합니다.
        # 예: 3.3V 측정 시 +/- 5V 범위면 충분합니다.
        dwf.FDwfAnalogInChannelRangeSet(hdwf, c_int(0), c_double(5.0))
        dwf.FDwfAnalogInConfigure(hdwf, c_bool(False), c_bool(False))
        time.sleep(0.5)

        # 3. N번 샘플링하며 데이터 수집
        print(f"Collecting {N_SAMPLES} samples...")
        for i in range(N_SAMPLES):
            dwf.FDwfAnalogInStatus(hdwf, c_bool(False), None)
            
            v_reading = c_double()
            dwf.FDwfAnalogInStatusSample(hdwf, c_int(0), byref(v_reading))
            measured_voltages.append(v_reading.value)
            
            print(f"\rSample [{i+1:03d}/{N_SAMPLES}] -> {v_reading.value:.5f} V", end="")
            time.sleep(0.005) # 매우 짧은 딜레이로 빠른 샘플링

        print("\n\nMeasurement complete.")

        # 4. 통계 계산 및 히스토그램 플롯
        if measured_voltages:
            plot_histogram(measured_voltages, W1_VOLTAGE_TO_SET)

    except KeyboardInterrupt:
        print("\nMeasurement stopped by user.")
    finally:
        dwf.FDwfDeviceCloseAll()
        print("Device closed.")

def plot_histogram(data, set_voltage):
    """측정된 데이터의 히스토그램을 생성하고 통계 정보를 표시합니다."""
    
    data_array = np.array(data)
    mean = np.mean(data_array)
    std_dev = np.std(data_array, ddof=1)
    
    print("\n--- Statistics ---")
    print(f"Mean (평균):           {mean:.5f} V")
    print(f"Standard Dev (σ):    {std_dev:.5f} V")
    print(f"Max Value (최댓값):      {np.max(data_array):.5f} V")
    print(f"Min Value (최솟값):      {np.min(data_array):.5f} V")
    
    # 그래프 스타일 설정
    plt.style.use('seaborn-v0_8-whitegrid')
    plt.figure(figsize=(12, 7))

    # 히스토그램 그리기
    plt.hist(data_array, bins='auto', density=True, alpha=0.75, label='Measured Voltage Distribution')

    # 평균선 그리기
    plt.axvline(mean, color='r', linestyle='dashed', linewidth=2, label=f'Mean: {mean:.5f} V')

    # 그래프 제목 및 레이블 설정
    plt.title(f'Histogram of W1 Voltage Measurement ({len(data)} Samples)', fontsize=16)
    plt.xlabel('Voltage (V)', fontsize=12)
    plt.ylabel('Probability Density', fontsize=12)
    
    # 통계 정보 텍스트 박스 추가
    stats_text = (f'Set Voltage: {set_voltage:.3f} V\n'
                  f'Mean (μ): {mean:.5f} V\n'
                  f'Std Dev (σ): {std_dev:.5f} V')
    
    plt.text(0.05, 0.95, stats_text, transform=plt.gca().transAxes, fontsize=12,
             verticalalignment='top', bbox=dict(boxstyle='round,pad=0.5', fc='wheat', alpha=0.5))

    plt.legend()
    
    # VS Code에서 바로 그래프 창을 띄웁니다.
    print("\nPlotting graph...")
    plt.show()

if __name__ == '__main__':
    measure_and_plot_w1()
