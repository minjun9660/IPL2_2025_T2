#region: ------------------------- Import Libraries -------------------------
import sys
from pathlib import Path
import time
from ctypes import *
import matplotlib.pyplot as plt
import numpy as np

try:
    from dwfconstants import *
except ImportError:
    print("dwfconstants.py not found. Make sure it's in the same directory or in the python path.")
    quit()
#endregion

#region: ------------------------- Configuration ----------------------------
# 테스트할 입력 전압(Vin) 스윕 범위 설정
# LM324N은 +/- 5V 전원에서 약 +/- 3.5V에서 출력이 포화됩니다.
# 이득(Gain)이 2이므로, 입력이 +/- 1.75V를 넘어가면 포화가 시작됩니다.
# 포화 영역을 확인하기 위해 -2.5V ~ +2.5V 범위를 스윕합니다.
VIN_START = -2.5
VIN_END = 2.5
SWEEP_STEPS = 101

# LM324N에 공급할 전압
V_POSITIVE_SUPPLY = 5.0  # Vcc (Pin 4)
V_NEGATIVE_SUPPLY = -5.0 # Vee (Pin 11)

# 이론적인 증폭기 이득 (G = 1 + Rf/R1)
# R1=10k, Rf=10k 일 때 G = 2
THEORETICAL_GAIN = 2.0
# LM324N의 예상 출력 포화 전압 (Vcc - 1.5V, Vee + 1.5V)
OUTPUT_SATURATION_POS = V_POSITIVE_SUPPLY - 1.5
OUTPUT_SATURATION_NEG = V_NEGATIVE_SUPPLY + 1.5

# 노이즈 감소를 위해 각 스텝에서 평균 낼 샘플의 수
SAMPLES_TO_AVERAGE = 1000
#endregion

#region: ------------------------- DWF Library Setup ------------------------
# ... (기존 코드와 동일) ...
try:
    if sys.platform.startswith("win"):
        dwf = cdll.dwf
    elif sys.platform.startswith("darwin"):
        dwf = cdll.LoadLibrary("/Library/Frameworks/dwf.framework/dwf")
    else:
        dwf = cdll.LoadLibrary("libdwf.so")
except OSError:
    print("DWF library not found. Please install WaveForms and ensure it's in the system path.")
    quit()

hdwf = c_int()
#endregion

#region: ------------------------- Main Logic -------------------------------
def get_amplifier_transfer_curve():
    """
    Op-Amp 증폭기의 전달 특성 곡선(Vout vs Vin)을 측정하고 그래프로 플롯합니다.
    """
    transfer_curve_data = None
    vin_data = []
    vout_data = []

    print("Opening first device...")
    if dwf.FDwfDeviceOpen(c_int(-1), byref(hdwf)) == 0:
        print("Failed to open device")
        szerr = create_string_buffer(512)
        dwf.FDwfGetLastErrorMsg(szerr)
        print(str(szerr.value))
        return

    try:
        # 1. Op-Amp 전원 공급 (V+, V-) 켜기
        print(f"Configuring Power Supplies: V+={V_POSITIVE_SUPPLY}V, V-={V_NEGATIVE_SUPPLY}V")
        # V+ (Red wire)
        dwf.FDwfAnalogIOChannelNodeSet(hdwf, c_int(0), c_int(0), c_double(True)) # Enable
        dwf.FDwfAnalogIOChannelNodeSet(hdwf, c_int(0), c_int(1), c_double(V_POSITIVE_SUPPLY))
        # V- (White wire)
        dwf.FDwfAnalogIOChannelNodeSet(hdwf, c_int(1), c_int(0), c_double(True)) # Enable
        dwf.FDwfAnalogIOChannelNodeSet(hdwf, c_int(1), c_int(1), c_double(V_NEGATIVE_SUPPLY))
        # 전원 공급 시작
        dwf.FDwfAnalogIOEnableSet(hdwf, c_bool(True))
        print("Power supplies ON. Waiting 1 sec to stabilize...")
        time.sleep(1.0) # 전원이 안정화될 때까지 대기

        # 2. 파형 발생기 W1(Vin) 설정
        print("Configuring Waveform Generator W1 (as Vin)...")
        # W1 (Vin 스윕용)
        dwf.FDwfAnalogOutNodeEnableSet(hdwf, c_int(0), AnalogOutNodeCarrier, c_bool(True))
        dwf.FDwfAnalogOutNodeFunctionSet(hdwf, c_int(0), AnalogOutNodeCarrier, funcDC)
        # W2는 사용하지 않음
        dwf.FDwfAnalogOutNodeEnableSet(hdwf, c_int(1), AnalogOutNodeCarrier, c_bool(False))

        # 3. 스코프 Ch1(Vin 측정), Ch2(Vout 측정) 설정
        print("Configuring Scope Channels...")
        # Ch 1 (Vin 실제 값 측정용)
        dwf.FDwfAnalogInChannelEnableSet(hdwf, c_int(0), c_bool(True))
        dwf.FDwfAnalogInChannelRangeSet(hdwf, c_int(0), c_double(5.0)) # Range +/- 5V
        # Ch 2 (Vout 실제 값 측정용)
        dwf.FDwfAnalogInChannelEnableSet(hdwf, c_int(1), c_bool(True))
        dwf.FDwfAnalogInChannelRangeSet(hdwf, c_int(1), c_double(5.0)) # Range +/- 5V
        
        # 샘플링 설정
        dwf.FDwfAnalogInAcquisitionModeSet(hdwf, acqmodeRecord)
        dwf.FDwfAnalogInFrequencySet(hdwf, c_double(100000))
        dwf.FDwfAnalogInRecordLengthSet(hdwf, c_double(SAMPLES_TO_AVERAGE / 100000.0))
        time.sleep(0.5)

        # --- 루프: Vin을 스윕하며 데이터 수집 ---
        print(f"--- Starting Vin sweep from {VIN_START}V to {VIN_END}V ---")
        vin_setpoints = np.linspace(VIN_START, VIN_END, SWEEP_STEPS)
        
        for v_in_setpoint in vin_setpoints:
            # W1(Vin)에 스윕 전압 설정
            dwf.FDwfAnalogOutNodeOffsetSet(hdwf, c_int(0), AnalogOutNodeCarrier, c_double(v_in_setpoint))
            dwf.FDwfAnalogOutConfigure(hdwf, c_int(0), c_bool(True))
            time.sleep(0.05) # 전압 안정화 대기

            # 스코프 측정 시작 및 대기
            dwf.FDwfAnalogInConfigure(hdwf, c_bool(False), c_bool(True))
            while True:
                sts = c_byte()
                dwf.FDwfAnalogInStatus(hdwf, c_bool(True), byref(sts))
                if sts.value == DwfStateDone.value: break
                time.sleep(0.01)

            # Ch1 버퍼 데이터 읽기 및 평균 계산 (Vin)
            buffer_ch1 = (c_double * SAMPLES_TO_AVERAGE)()
            dwf.FDwfAnalogInStatusData(hdwf, c_int(0), buffer_ch1, SAMPLES_TO_AVERAGE)
            v_in_actual = np.mean(buffer_ch1)

            # Ch2 버퍼 데이터 읽기 및 평균 계산 (Vout)
            buffer_ch2 = (c_double * SAMPLES_TO_AVERAGE)()
            dwf.FDwfAnalogInStatusData(hdwf, c_int(1), buffer_ch2, SAMPLES_TO_AVERAGE)
            v_out_actual = np.mean(buffer_ch2)

            # 디버깅을 위한 상세 정보 출력
            print(f"\rVin_target: {v_in_setpoint:+.2f}V | Vin_actual: {v_in_actual:+.3f}V | Vout_actual: {v_out_actual:+.3f}V", end="")

            vin_data.append(v_in_actual)
            vout_data.append(v_out_actual)
                
        transfer_curve_data = (vin_data, vout_data)
        print("\n\nSweep finished for all Vin values.")

    except Exception as e:
        print(f"\nAn error occurred: {e}")
    finally:
        # 프로그램 종료 시 장치 리셋 및 연결 해제
        dwf.FDwfAnalogOutConfigure(hdwf, c_int(0), c_bool(False)) # W1 정지
        dwf.FDwfAnalogIOEnableSet(hdwf, c_bool(False)) # 전원 공급 정지
        dwf.FDwfDeviceCloseAll()
        print("Power supplies OFF. Device closed.")

    # 4. 수집된 모든 데이터로 그래프 플로팅
    if transfer_curve_data:
        vin, vout = transfer_curve_data
        
        plt.figure(figsize=(10, 7))
        
        # (1) 측정된 Vout vs Vin 플롯
        plt.plot(vin, vout, marker='.', linestyle='-', label=f'Measured Vout vs Vin (G={THEORETICAL_GAIN:.1f})')
        
        # (2) 이론적인 이득 및 포화 곡선 플롯
        theoretical_vin = np.linspace(VIN_START, VIN_END, SWEEP_STEPS)
        theoretical_vout = theoretical_vin * THEORETICAL_GAIN
        # LM324N의 포화 특성 적용
        theoretical_vout = np.clip(theoretical_vout, OUTPUT_SATURATION_NEG, OUTPUT_SATURATION_POS)
        plt.plot(theoretical_vin, theoretical_vout, 'r--', label=f'Theoretical G={THEORETICAL_GAIN:.1f} (with Saturation)')

        plt.title('LM324N Non-Inverting Amplifier Transfer Curve')
        plt.xlabel('Input Voltage (Vin) [V]')
        plt.ylabel('Output Voltage (Vout) [V]')
        plt.legend()
        plt.grid(True)
        plt.axhline(0, color='black', linewidth=0.5) # y=0 축
        plt.axvline(0, color='black', linewidth=0.5) # x=0 축
        plt.show()

if __name__ == '__main__':
    get_amplifier_transfer_curve()
#endregion
