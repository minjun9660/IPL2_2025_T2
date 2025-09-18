#region: ------------------------- Import Libraries -------------------------
import sys
from pathlib import Path
import time
from ctypes import *
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit
import csv

try:
    from dwfconstants import *
except ImportError:
    print("dwfconstants.py not found. Make sure it's in the same directory.")
    quit()
#endregion

#region: ------------------------- Configuration ----------------------------
R_SENSE_OHMS = 1000.0
CAPACITOR_FARADS = 10e-6 
TAU = R_SENSE_OHMS * CAPACITOR_FARADS

# 충전/방전 시간을 시정수(TAU)의 몇 배로 할지 결정합니다. 
# 5배 이상이면 충분합니다.
CHARGING_PERIOD_FACTOR = 20.0 
SQUARE_WAVE_FREQ_HZ = 1.0 / (TAU * CHARGING_PERIOD_FACTOR)

# ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★
# 수정된 부분: 하드웨어 버퍼 한계와 측정 시간에 맞춰 설정 변경

# 1. Analog Discovery 2의 최대 버퍼 크기를 명시적으로 정의합니다.
MAX_BUFFER_SIZE = 16384

# 2. 전체 샘플 수를 최대 버퍼 크기로 고정합니다.
N_SAMPLES = MAX_BUFFER_SIZE

# 3. 원하는 측정 시간(1주기)을 이 버퍼에 담을 수 있도록 샘플링 주파수를 계산합니다.
# Sampling Freq = Total Samples / Total Time = N_SAMPLES / (1 / SQUARE_WAVE_FREQ_HZ)
SAMPLING_FREQUENCY_HZ = N_SAMPLES * SQUARE_WAVE_FREQ_HZ
# ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★

print("--- 최종 설정값 ---")
print(f"커패시터 (C): {CAPACITOR_FARADS * 1e6} µF")
print(f"시간 상수 (τ): {TAU * 1000:.2f} ms")
print(f"구형파 주파수: {SQUARE_WAVE_FREQ_HZ:.2f} Hz (측정 시간: {1/SQUARE_WAVE_FREQ_HZ * 1000:.0f} ms)")
print(f"샘플링 주파수: {SAMPLING_FREQUENCY_HZ / 1000:.2f} kHz (하드웨어 한계에 맞춰 자동 조절됨)")
print(f"총 샘플 수: {N_SAMPLES} 개")
print("--------------------")

WAVEGEN_AMPLITUDE_V = 1.65
WAVEGEN_OFFSET_V = 1.65
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

#region: ------------------------- Main Logic & Plotting --------------------
def measure_rc_circuit():
    # ... (이하 로직은 이전과 동일하게 작동합니다) ...
    # print("Opening first device...")
    if dwf.FDwfDeviceOpen(c_int(-1), byref(hdwf)) == 0:
        print("Failed to open device")
        return

    voltage_samples_ch1 = (c_double * N_SAMPLES)()
    voltage_samples_ch2 = (c_double * N_SAMPLES)()

    try:
        # 1. 파형 발생기 설정
        dwf.FDwfAnalogOutNodeEnableSet(hdwf, c_int(0), AnalogOutNodeCarrier, c_bool(True))
        dwf.FDwfAnalogOutNodeFunctionSet(hdwf, c_int(0), AnalogOutNodeCarrier, funcSquare)
        dwf.FDwfAnalogOutNodeFrequencySet(hdwf, c_int(0), AnalogOutNodeCarrier, c_double(SQUARE_WAVE_FREQ_HZ))
        dwf.FDwfAnalogOutNodeAmplitudeSet(hdwf, c_int(0), AnalogOutNodeCarrier, c_double(WAVEGEN_AMPLITUDE_V))
        dwf.FDwfAnalogOutNodeOffsetSet(hdwf, c_int(0), AnalogOutNodeCarrier, c_double(WAVEGEN_OFFSET_V))
        dwf.FDwfAnalogOutRepeatSet(hdwf, c_int(0), c_int(0))
        dwf.FDwfAnalogOutConfigure(hdwf, c_int(0), c_bool(True))
        time.sleep(0.5)

        # 2. 오실로스코프 설정
        dwf.FDwfAnalogInChannelEnableSet(hdwf, c_int(0), c_bool(True))
        dwf.FDwfAnalogInChannelEnableSet(hdwf, c_int(1), c_bool(True))
        dwf.FDwfAnalogInChannelRangeSet(hdwf, c_int(0), c_double(5.0))
        dwf.FDwfAnalogInChannelRangeSet(hdwf, c_int(1), c_double(5.0))
        dwf.FDwfAnalogInFrequencySet(hdwf, c_double(SAMPLING_FREQUENCY_HZ))
        dwf.FDwfAnalogInBufferSizeSet(hdwf, c_int(N_SAMPLES))

        # 3. 트리거 설정
        dwf.FDwfAnalogInTriggerSourceSet(hdwf, trigsrcDetectorAnalogIn)
        dwf.FDwfAnalogInTriggerChannelSet(hdwf, c_int(0))
        dwf.FDwfAnalogInTriggerTypeSet(hdwf, trigtypeEdge)
        dwf.FDwfAnalogInTriggerConditionSet(hdwf, DwfTriggerSlopeRise)
        dwf.FDwfAnalogInTriggerLevelSet(hdwf, c_double(1.0))

        # 4. 데이터 수집
        # print("Starting acquisition...")
        dwf.FDwfAnalogInConfigure(hdwf, c_bool(False), c_bool(True))
        
        status = c_byte()
        while True:
            dwf.FDwfAnalogInStatus(hdwf, c_bool(True), byref(status))
            if status.value == DwfStateDone.value:
                break
            time.sleep(0.1)
        
        # print("Acquisition complete.")

        # 5. 데이터 읽기 및 처리
        dwf.FDwfAnalogInStatusData(hdwf, c_int(0), voltage_samples_ch1, N_SAMPLES)
        dwf.FDwfAnalogInStatusData(hdwf, c_int(1), voltage_samples_ch2, N_SAMPLES)

        v_source = np.frombuffer(voltage_samples_ch1, dtype=np.double)
        v_capacitor = np.frombuffer(voltage_samples_ch2, dtype=np.double)
        v_resistor = v_source - v_capacitor
        current_amperes = v_resistor / R_SENSE_OHMS
        time_seconds = np.arange(0, N_SAMPLES) / SAMPLING_FREQUENCY_HZ
        total_len=len(time_seconds)
        tmp=plot_results(time_seconds[total_len//4:total_len//2], v_source[total_len//4:total_len//2], v_capacitor[total_len//4:total_len//2], current_amperes[total_len//4:total_len//2])

    except KeyboardInterrupt:
        print("\nMeasurement stopped by user.")
    finally:
        dwf.FDwfDeviceCloseAll()
        # print("Device closed.")
        return tmp

def exp_decay(t, i, RC):
    return i * np.exp(-t / RC)

def plot_results(t, v_source, v_cap, current):
    # fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    for i in range(len(v_source)-1):
        if v_source[i]/v_source[i+1]>1.000005:
            break
    
    params, covariance = curve_fit(exp_decay, t[i:], v_source[i:])
    # plt.style.use('seaborn-v0_8-whitegrid')
    # ax1.plot(t * 1000, v_source, label=f'Source Voltage ($V_{{source}}$)', color='blue')
    # ax1.plot(t*1000,[exp_decay(i,params[0],params[1]) for i in t],label=f'Capacity={params[1]/R_SENSE_OHMS*10**6:.2f}mu',ls='--')
    # ax1.plot(t * 1000, v_cap, label=f'Capacitor Voltage ($V_C$)', color='red')
    # ax1.set_title('RC Circuit Voltage and Current Measurement (Full Cycle)', fontsize=16)
    # ax1.set_ylabel('Voltage (V)', fontsize=12)
    # ax1.legend()
    # ax1.grid(True)
    # ax2.plot(t * 1000, current * 1000, label='Circuit Current (I)', color='green')
    # ax2.set_xlabel('Time (ms)', fontsize=12)
    # ax2.set_ylabel('Current (mA)', fontsize=12)
    # ax2.legend()
    # ax2.grid(True)
    # plt.tight_layout()
    # plt.show()
    return params

if __name__ == '__main__':
    temp=measure_rc_circuit()
    data=[]
    data.append((temp[1]/R_SENSE_OHMS*10**6)/10-1)
    for i in range(200):
        print(f'{i}/200')
        temp=measure_rc_circuit()
        data.append((temp[1]/R_SENSE_OHMS*10**6)/10-1)
    print(data)
    filename = "data.csv"
    with open(filename, mode='w', newline='') as file:
        writer = csv.writer(file)
        for i in range(len(data)):
            writer.writerow([data[i]])
            
        
    # plt.hist(data)
    # plt.show()
    
#endregion
