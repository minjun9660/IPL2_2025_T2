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
# 기준 저항(Reference Resistor)의 값을 정확하게 입력하세요 (단위: Ohm)
# 정확도를 높이려면 측정하려는 저항과 비슷한 값의 기준 저항을 사용하는 것이 좋습니다.
R_REF = 1000.0

# 파형 발생기 설정
AC_AMPLITUDE = 1.0    # Volt
AC_FREQUENCY = 1000.0 # Hz

# 오실로스코프 설정
N_SAMPLES = 8192      # 한 번에 수집할 샘플 개수
SAMPLING_FREQ = 200000.0 # 샘플링 주파수 (Hz)
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

def measure_resistance():
    """
    AC 전압 분배 회로를 이용하여 저항을 측정하고,
    측정된 파형과 계산된 저항값을 반환합니다.
    """
    print("Opening first device...")
    if dwf.FDwfDeviceOpen(c_int(-1), byref(hdwf)) == 0:
        print("Failed to open device")
        return None, None, None

    # 각 채널의 샘플 데이터를 저장할 버퍼 생성
    vin_samples = (c_double * N_SAMPLES)()
    vx_samples = (c_double * N_SAMPLES)()
    
    try:
        # 1. W1 (파형 발생기) AC 설정
        print(f"Setting W1 output: Sine, {AC_AMPLITUDE} V, {AC_FREQUENCY} Hz...")
        dwf.FDwfAnalogOutNodeEnableSet(hdwf, c_int(0), AnalogOutNodeCarrier, c_bool(True))
        dwf.FDwfAnalogOutNodeFunctionSet(hdwf, c_int(0), AnalogOutNodeCarrier, funcSine)
        dwf.FDwfAnalogOutNodeFrequencySet(hdwf, c_int(0), AnalogOutNodeCarrier, c_double(AC_FREQUENCY))
        dwf.FDwfAnalogOutNodeAmplitudeSet(hdwf, c_int(0), AnalogOutNodeCarrier, c_double(AC_AMPLITUDE))
        dwf.FDwfAnalogOutConfigure(hdwf, c_int(0), c_bool(True))
        time.sleep(0.5)

        # 2. 스코프 채널 1 & 2 설정
        print("Configuring Scope Channels...")
        # 채널 1 (V_in) 활성화 및 범위 설정
        dwf.FDwfAnalogInChannelEnableSet(hdwf, c_int(0), c_bool(True))
        dwf.FDwfAnalogInChannelRangeSet(hdwf, c_int(0), c_double(5.0))
        # 채널 2 (V_x) 활성화 및 범위 설정
        dwf.FDwfAnalogInChannelEnableSet(hdwf, c_int(1), c_bool(True))
        dwf.FDwfAnalogInChannelRangeSet(hdwf, c_int(1), c_double(5.0))
        
        # [수정] 트리거를 '없음'으로 설정하여 즉시 측정을 시작하도록 합니다.
        dwf.FDwfAnalogInTriggerSourceSet(hdwf, trigsrcNone)
        
        # 샘플링 주파수 및 버퍼 크기 설정
        dwf.FDwfAnalogInFrequencySet(hdwf, c_double(SAMPLING_FREQ))
        dwf.FDwfAnalogInAcquisitionModeSet(hdwf, acqmodeRecord)
        dwf.FDwfAnalogInRecordLengthSet(hdwf, c_int(N_SAMPLES))
        time.sleep(0.1)

        # 3. 파형 데이터 동시 수집
        print(f"Collecting {N_SAMPLES} samples from each channel...")
        dwf.FDwfAnalogInConfigure(hdwf, c_bool(False), c_bool(True))
        
        while True:
            sts = c_byte()
            dwf.FDwfAnalogInStatus(hdwf, c_bool(True), byref(sts))
            if sts.value == DwfStateDone.value:
                break
            time.sleep(0.01)
        
        # 각 채널에서 데이터 읽어오기
        dwf.FDwfAnalogInStatusData(hdwf, c_int(0), vin_samples, N_SAMPLES) # Ch1 -> V_in
        dwf.FDwfAnalogInStatusData(hdwf, c_int(1), vx_samples, N_SAMPLES) # Ch2 -> V_x
        print("Acquisition complete.")

        # 4. 저항 계산
        vin_array = np.array(list(vin_samples))
        vx_array = np.array(list(vx_samples))
        
        # RMS(실효값) 계산
        vin_rms = np.sqrt(np.mean(vin_array**2))
        vx_rms = np.sqrt(np.mean(vx_array**2))
        
        # 전압 분배 법칙을 이용한 저항 계산
        # Rx = R_ref * (V_x / (V_in - V_x))
        # V_ref (기준 저항에 걸리는 전압) = V_in - V_x
        # 분모가 0이 되는 것을 방지
        v_ref_rms = vin_rms - vx_rms
        if v_ref_rms <= 0:
             print("Error: Voltage across reference resistor is zero or negative. Check connections.")
             return None, None, None
        
        calculated_resistance = R_REF * (vx_rms / v_ref_rms)
        
        return calculated_resistance, vin_array, vx_array
        
    except KeyboardInterrupt:
        print("\nMeasurement stopped by user.")
        return None, None, None
    finally:
        dwf.FDwfDeviceCloseAll()
        print("Device closed.")

def plot_waveforms(vin_array, vx_array, r_x):
    """측정된 V_in, V_x 파형과 계산된 저항값을 플롯합니다."""
    plt.style.use('seaborn-v0_8-whitegrid')
    fig, ax = plt.subplots(figsize=(12, 6))

    # 시간 축 생성
    time_axis = np.arange(0, N_SAMPLES / SAMPLING_FREQ, 1 / SAMPLING_FREQ)

    ax.plot(time_axis, vin_array, label=f'$V_{{in}}$ (Scope Ch 1)')
    ax.plot(time_axis, vx_array, label=f'$V_{{x}}$ (Scope Ch 2)')
    
    ax.set_title(f'AC Resistance Measurement Waveforms\nCalculated $R_x \\approx {r_x:.2f} \\,\\Omega$', fontsize=16)
    ax.set_xlabel('Time (s)', fontsize=12)
    ax.set_ylabel('Voltage (V)', fontsize=12)
    ax.legend()
    ax.grid(True)
    
    plt.tight_layout()
    plt.show()


if __name__ == '__main__':
    print(f"{'='*60}")
    print("AC Resistance Measurement using Voltage Divider")
    print(f"Reference Resistor (R_ref): {R_REF} Ohm")
    print("Please ensure hardware is connected correctly before proceeding.")
    input("Press Enter to start measurement...")
    print(f"{'='*60}")
    
    resistance, vin_data, vx_data = measure_resistance()
    
    if resistance is not None:
        print("\n--- Measurement Result ---")
        print(f"Calculated Resistance (R_x): {resistance:.4f} Ohm")
        
        plot_waveforms(vin_data, vx_data, resistance)

