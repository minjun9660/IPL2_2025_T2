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
# 기준 저항 값을 Ohm 단위로 정확하게 입력하세요.
R_REF = 10000.0  # 예시: 10kΩ 저항

# <<< 수정된 부분: W1 핀으로 출력할 DC 전압 목록 >>>
W1_VOLTAGES = [3.3/8,3.3/4, 3.3/2, 3.3]

# 각 전압 레벨당 측정할 횟수
N_SAMPLES = 1000 # 시간을 줄이기 위해 샘플 수를 약간 조정했습니다.
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
#endregion

#region: ------------------------- Main Logic -------------------------------
def measure_resistance_for_all_voltages():
    """
    여러 W1 전압에 대해 저항 값을 측정하고 결과를 하나의 딕셔너리로 반환합니다.
    """
    print("Opening first device...")
    if dwf.FDwfDeviceOpen(c_int(-1), byref(hdwf)) == 0:
        print("Failed to open device")
        return None

    # <<< 수정된 부분: 모든 측정 결과를 저장할 딕셔너리 >>>
    all_results = {}

    try:
        # <<< 수정된 부분: 설정된 전압 목록을 순회하는 루프 >>>
        for vin in W1_VOLTAGES:
            measured_resistances = []
            print(f"\n----- Measuring with Vin = {vin:.3f}V -----")

            # 1. W1 (파형 발생기) 설정
            dwf.FDwfAnalogOutNodeEnableSet(hdwf, c_int(0), AnalogOutNodeCarrier, c_bool(True))
            dwf.FDwfAnalogOutNodeFunctionSet(hdwf, c_int(0), AnalogOutNodeCarrier, funcDC)
            dwf.FDwfAnalogOutNodeOffsetSet(hdwf, c_int(0), AnalogOutNodeCarrier, c_double(vin))
            dwf.FDwfAnalogOutConfigure(hdwf, c_int(0), c_bool(True))
            time.sleep(0.5)

            # 2. 스코프 채널 1 (1+, 1-) 설정
            dwf.FDwfAnalogInChannelEnableSet(hdwf, c_int(0), c_bool(True))
            # 측정 범위를 입력 전압보다 약간 큰 값으로 설정
            dwf.FDwfAnalogInChannelRangeSet(hdwf, c_int(0), c_double(vin + 1.0))
            dwf.FDwfAnalogInConfigure(hdwf, c_bool(False), c_bool(False))
            time.sleep(0.5)

            # 3. N번 샘플링하며 저항 값 계산
            for i in range(N_SAMPLES):
                dwf.FDwfAnalogInStatus(hdwf, c_bool(False), None)
                v_scope = c_double()
                dwf.FDwfAnalogInStatusSample(hdwf, c_int(0), byref(v_scope))
                v_out = v_scope.value
                
                if vin > v_out and v_out > 0:
                    resistance = R_REF * (v_out / (vin - v_out))
                    measured_resistances.append(resistance)
                    print(f"\rSample [{i+1:03d}/{N_SAMPLES}] -> R: {resistance:,.2f} Ω", end="")
            
            # <<< 수정된 부분: 현재 전압의 측정 결과를 딕셔너리에 저장 >>>
            all_results[vin] = measured_resistances
            print("\nMeasurement for this voltage is complete.")
        
        return all_results

    except KeyboardInterrupt:
        print("\nMeasurement stopped by user.")
        return None
    finally:
        dwf.FDwfDeviceCloseAll()
        print("\nDevice closed.")

def plot_histograms_subplot(all_data):
    """
    여러 데이터셋을 하나의 Figure 안에 서브플롯으로 그립니다.
    """
    if not all_data:
        print("No data to plot.")
        return

    # <<< 수정된 부분: 2x2 서브플롯 그리드 생성 >>>
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    # 전체 그래프의 메인 타이틀
    fig.suptitle('Resistance Measurement Histograms at Different Voltages', fontsize=20)

    # axes.flatten()을 사용하여 2D 그리드를 1D로 만들어 쉽게 순회
    for ax, (vin, data) in zip(axes.flatten(), all_data.items()):
        if not data: continue

        data_array = np.array(data)
        mean = np.mean(data_array)
        std_dev = np.std(data_array, ddof=1)

        # 각 서브플롯에 히스토그램 그리기
        ax.hist(data_array, bins='auto', alpha=0.75, label='Resistance Distribution')
        ax.axvline(mean, color='r', linestyle='dashed', linewidth=2, label=f'Mean: {mean:,.2f} Ω')
        
        # 각 서브플롯의 타이틀과 라벨 설정
        ax.set_title(f'Vin = {vin:.3f} V', fontsize=14)
        ax.set_xlabel('Resistance (Ω)')
        ax.set_ylabel('Frequency')
        
        stats_text = (f'Mean (μ): {mean:,.2f} Ω\n'
                      f'Std Dev (σ): {std_dev:.2f} Ω')
        ax.text(0.05, 0.95, stats_text, transform=ax.transAxes, verticalalignment='top',
                bbox=dict(boxstyle='round,pad=0.5', fc='skyblue', alpha=0.5))
        ax.legend()
    
    # 서브플롯들이 겹치지 않게 레이아웃 조정
    plt.tight_layout(rect=[0, 0.03, 1, 0.95]) # 메인 타이틀과 겹치지 않도록 조정
    
    print("\nPlotting all graphs...")
    plt.show()

if __name__ == '__main__':
    results = measure_resistance_for_all_voltages()
    if results:
        plot_histograms_subplot(results)
