"""v5 board: parts and connections (the schematic, as data).

Every part: footprint (KiCad library), value, manufacturer part, and pad -> net. make_board.py builds the PCB from
this; erc.py checks it (every net driven and used, power pins, decoupling, straps, pin names against KiCad's symbols).

Power: USB-C 5 V -> MCP73831 charger -> 1S Li-ion pouch (VBAT, 3.0-4.2 V) -> RT9080 LDO (2 uA quiescent) -> 3V3.
The motor driver runs straight from VBAT. Both H-bridges of the DRV8833 are paralleled; its current regulation
(0.2 V across RSENSE) caps the motor current, and with it the torque, in hardware.
"""

from layout import GPIO

ESP_PAD = {  # ESP32-C6-MINI-1: GPIO -> module pad (from KiCad's RF_Module symbol)
    0: "12", 1: "13", 2: "5", 3: "6", 4: "9", 5: "10", 6: "15", 7: "16", 8: "22", 9: "23",
    12: "17", 13: "18", 14: "19", 15: "20", 18: "24", 19: "25", 20: "26", 21: "27", 22: "28", 23: "29",
}
ESP_GND = ["1", "2", "11", "14"] + [str(n) for n in range(36, 54)]


def esp_pads():
    pads = {p: "GND" for p in ESP_GND}
    pads["3"] = "3V3"
    pads["8"] = "EN"
    pads[ESP_PAD[8]] = "STRAP_IO8"                     # must be high at boot: pull-up
    for name, gpio in GPIO.items():
        pads[ESP_PAD[gpio]] = name
    return pads


R0402, C0402, C0603, R0805 = ("Resistor_SMD:R_0402_1005Metric", "Capacitor_SMD:C_0402_1005Metric",
                              "Capacitor_SMD:C_0603_1608Metric", "Resistor_SMD:R_0805_2012Metric")

# ref: (footprint, value, manufacturer part, {pad: net}, anchor ref for automatic placement)
PARTS = {
    "U1": ("RF_Module:ESP32-C6-MINI-1", "ESP32-C6-MINI-1-N4", "ESP32-C6-MINI-1-N4", esp_pads(), None),
    "U2": ("Package_SO:TSSOP-16_4.4x5mm_P0.65mm", "DRV8833PW", "DRV8833PWR", {
        "1": "MOTOR_SLEEP", "2": "MOT_A", "3": "ISENSE", "4": "MOT_B", "5": "MOT_B", "6": "ISENSE", "7": "MOT_A",
        "8": "MOTOR_FAULT", "9": "MOTOR_IN1", "10": "MOTOR_IN2", "11": "VCP", "12": "VBAT", "13": "GND", "14": "VINT",
        "15": "MOTOR_IN2", "16": "MOTOR_IN1"}, None),
    "U3": ("Package_TO_SOT_SMD:SOT-23-5", "MCP73831-2", "MCP73831T-2ACI/OT", {
        "1": "CHG_STAT", "2": "GND", "3": "VBAT", "4": "VBUS", "5": "PROG"}, None),
    "U4": ("Package_TO_SOT_SMD:SOT-23-5", "RT9080-33", "RT9080-33GJ5", {
        "1": "VBAT", "2": "GND", "3": "VBAT", "5": "3V3"}, None),
    "U5": ("Package_TO_SOT_SMD:SOT-23", "DRV5032 (hub)", "DRV5032FBDBZR", {"1": "3V3", "2": "HALL_HUB", "3": "GND"}, None),
    "U6": ("Package_TO_SOT_SMD:SOT-23", "DRV5032 (thumb-turn)", "DRV5032FBDBZR", {"1": "3V3", "2": "HALL_KNOB", "3": "GND"}, None),
    "J1": ("Connector_USB:USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal", "USB-C", "GCT USB4105-GF-A", {
        "A1": "GND", "A12": "GND", "B1": "GND", "B12": "GND", "S1": "GND",
        "A4": "VBUS", "A9": "VBUS", "B4": "VBUS", "B9": "VBUS",
        "A5": "CC1", "B5": "CC2", "A6": "USB_DP", "B6": "USB_DP", "A7": "USB_DM", "B7": "USB_DM"}, None),
    "J2": ("Connector_JST:JST_SH_SM02B-SRSS-TB_1x02-1MP_P1.00mm_Horizontal", "battery", "JST SM02B-SRSS-TB", {"1": "VBAT", "2": "GND", "MP": "GND"}, "U3"),
    "J3": ("Connector_JST:JST_SH_SM02B-SRSS-TB_1x02-1MP_P1.00mm_Horizontal", "motor", "JST SM02B-SRSS-TB", {"1": "MOT_A", "2": "MOT_B"}, "U2"),
    "SW1": ("Button_Switch_SMD:SW_SPST_EVQP7A", "button", "Panasonic EVQ-P7A01P", {"1": "BUTTON", "2": "GND"}, None),
    "D1": ("LED_SMD:LED_0603_1608Metric", "status", "LED 0603 white", {"1": "GND", "2": "LED_A"}, None),
    # ESP32-C6
    "C1": (C0603, "10uF", "CL10A106MQ8NNNC", {"1": "3V3", "2": "GND"}, "U1"),
    "C2": (C0402, "100nF", "CL05B104KO5NNNC", {"1": "3V3", "2": "GND"}, "U1"),
    "R1": (R0402, "10k", "0402WGF1002TCE", {"1": "3V3", "2": "EN"}, "U1"),
    "C3": (C0402, "1uF", "CL05A105KA5NQNC", {"1": "EN", "2": "GND"}, "U1"),
    "R2": (R0402, "10k", "0402WGF1002TCE", {"1": "3V3", "2": "STRAP_IO8"}, "U1"),
    "R3": (R0402, "10k", "0402WGF1002TCE", {"1": "3V3", "2": "BUTTON"}, "SW1"),
    "R4": (R0402, "1k", "0402WGF1001TCE", {"1": "LED", "2": "LED_A"}, "D1"),
    # Motor driver
    "C4": (C0603, "10uF", "CL10A106MQ8NNNC", {"1": "VBAT", "2": "GND"}, "U2"),
    "C5": (C0402, "100nF", "CL05B104KO5NNNC", {"1": "VBAT", "2": "GND"}, "U2"),
    "C6": (C0402, "10nF", "CL05B103KB5NNNC", {"1": "VCP", "2": "VBAT"}, "U2"),
    "C7": (C0402, "2.2uF", "CL05A225MQ5NSNC", {"1": "VINT", "2": "GND"}, "U2"),
    "R5": (R0805, "0.15R", "RL1220S-R15-F", {"1": "ISENSE", "2": "GND"}, "U2"),
    "R6": (R0402, "10k", "0402WGF1002TCE", {"1": "3V3", "2": "MOTOR_FAULT"}, "U2"),
    # Charger
    "C8": (C0603, "4.7uF", "CL10A475KO8NNNC", {"1": "VBUS", "2": "GND"}, "U3"),
    "C9": (C0603, "4.7uF", "CL10A475KO8NNNC", {"1": "VBAT", "2": "GND"}, "U3"),
    "R7": (R0402, "2k", "0402WGF2001TCE", {"1": "PROG", "2": "GND"}, "U3"),
    "R8": (R0402, "10k", "0402WGF1002TCE", {"1": "3V3", "2": "CHG_STAT"}, "U3"),
    "R9": (R0402, "5.1k", "0402WGF5101TCE", {"1": "CC1", "2": "GND"}, "J1"),
    "R10": (R0402, "5.1k", "0402WGF5101TCE", {"1": "CC2", "2": "GND"}, "J1"),
    # LDO
    "C10": (C0402, "1uF", "CL05A105KA5NQNC", {"1": "VBAT", "2": "GND"}, "U4"),
    "C11": (C0402, "1uF", "CL05A105KA5NQNC", {"1": "3V3", "2": "GND"}, "U4"),
    # Battery sense (1 M / 1 M: 2 uA)
    "R11": (R0402, "1M", "0402WGF1004TCE", {"1": "VBAT", "2": "VBAT_SENSE"}, "U1"),
    "R12": (R0402, "1M", "0402WGF1004TCE", {"1": "VBAT_SENSE", "2": "GND"}, "U1"),
    "C12": (C0402, "100nF", "CL05B104KO5NNNC", {"1": "VBAT_SENSE", "2": "GND"}, "U1"),
    # Hall sensors (bottom side, next to the sensor)
    "C13": (C0402, "100nF", "CL05B104KO5NNNC", {"1": "3V3", "2": "GND"}, "U5"),
    "C14": (C0402, "100nF", "CL05B104KO5NNNC", {"1": "3V3", "2": "GND"}, "U6"),
    # USB-powered version: USB 5 V straight onto the VBAT rail (the motor driver and the LDO are fine with 5 V)
    "R13": (R0805, "0R", "0805W8F0000T5E", {"1": "VBUS", "2": "VBAT"}, "U3"),
}

# Parts left off (DNP) in each version. Never fit R13 together with a battery: it would put 5 V on the cell.
DNP = {
    "battery": {"R13"},
    "usb": {"U3", "R7", "J2"},          # no charger, no battery connector
}

POWER_NETS = {"VBUS", "VBAT", "3V3", "GND", "MOT_A", "MOT_B", "ISENSE"}
WIDE = {"VBAT": 0.4, "MOT_A": 0.4, "MOT_B": 0.4, "ISENSE": 0.4, "GND": 0.4, "VBUS": 0.4, "3V3": 0.3}   # 0.4 mm carries the 1.33 A limit


def nets():
    out = {}
    for ref, (_, _, _, pads, _) in PARTS.items():
        for pad, net in pads.items():
            out.setdefault(net, []).append(f"{ref}.{pad}")
    return out
