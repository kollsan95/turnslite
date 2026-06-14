# ============================================================================
# File: main.py (Consolidated Maintenance Terminal Core)
# Role: Independent hardware register flasher and system diagnostics console.
# Description: Integrates network profile context matrices, dynamic baud rate
#              alignment handlers, and structural sys.stdin command routers.
# ============================================================================

import board
import busio
import digitalio
import microcontroller
import sys
import supervisor
from time import sleep

# ============================================================================
# SECTION 1: GLOBAL PLATFORM PROPERTIES (Formerly ch9120_config.py)
# ============================================================================
# Physical RP2040 hardware pin assignments mapping
UART_TX = "GP20"  # UART Data Transmission Line (TX RP2040 -> RX CH9120)
UART_RX = "GP21"  # UART Data Reception Line (RX RP2040 -> TX CH9120)
PIN_CFG = "GP18"  # Configuration Mode Latch Line (LOW=Command, HIGH=Transparent)
PIN_RST = "GP19"  # Physical Chip Hardware Reset Line (Active LOW)

# Central structural dictionary tracking current operational profiles state
net_settings = {
    "mode": 0,             # Socket execution profile (0:TCP Server, 1:TCP Client)
    "dhcp": 0,             # Dynamic address lease allocation assignment flag
    "local_ip": "0.0.0.0", # Device endpoints routing IPv4 matrix string
    "subnet_mask": "0.0.0.0", 
    "gateway": "0.0.0.0",  
    "local_port": 0,       
    "target_ip": "0.0.0.0", 
    "target_port": 0,      
    "baudrate": 9600,      # Default baseline communications rate
    "bits": 8,             
    "stop": 1,             
    "parity": "None"       
}

# ============================================================================
# SECTION 2: HARDWARE LOW-LEVEL DRIVER (Formerly ch9120_lib.py)
# ============================================================================
# Initialize system serial bus structures targeting baseline 9600 command loops
uart = busio.UART(
    getattr(board, UART_TX), 
    getattr(board, UART_RX), 
    baudrate=9600, 
    timeout=1.0
)

# Instantiate physical status control pins lines
cfg = digitalio.DigitalInOut(getattr(board, PIN_CFG))
cfg.switch_to_output(value=True)

rst = digitalio.DigitalInOut(getattr(board, PIN_RST))
rst.switch_to_output(value=True)


def _enter_config():
    """
    Forces the physical control states layout to capture the command context.
    DOCUMENTATION COMPLIANCE: CFG line pulled LOW BEFORE RST line transitions HIGH.
    """
    uart.baudrate = 9600                # Hardware rule: commands require 9600 baud
    sleep(0.05)
    cfg.value = False                  # Step 1: Force CFG line to ground (LOW)
    sleep(0.05)
    rst.value = False                  # Step 2: Force RESET line to ground (LOW)
    sleep(0.1)                         # Step 3: Hardware reset pulse duration window
    rst.value = True                   # Step 4: Release RESET (transceiver samples LOW on CFG)
    sleep(0.5)                         # Step 5: Wait for internal firmware boot sequence
    uart.reset_input_buffer()          # Flush transitional electrical switching noise

def _exit_config_and_save():
    """Commits active operational registers array back to permanent chip EEPROM."""
    for cmd in (b'\x57\xab\x0D', b'\x57\xab\x0E', b'\x57\xab\x5E'):
        uart.write(cmd) 
        sleep(0.1)      
    cfg.value = True    # Release CFG line to HIGH (return to transparent mode)
    sleep(0.2)
    
    # Realign the host microcontroller serial bus speed with the working speed of the chip
    uart.baudrate = net_settings.get("baudrate", 9600)
    sleep(0.1)

def _query_pure(cmd_bytes):
    """Pushes explicit read registry directives and returns the raw transceiver responses."""
    uart.write(b'\x57\xab' + cmd_bytes) 
    sleep(0.1)                         
    if uart.in_waiting > 0:
        return uart.read(uart.in_waiting) 
    return b'\x00'                     

def _ip_to_bytes(ip_str): 
    """Converts classic dot-notation string IPv4 arrays to literal 4-byte structures."""
    return bytes(int(x) for x in ip_str.split('.'))


def read_network_settings():
    _enter_config()
    res = {}
    cmd_list = (
        ("ip", b'\x61'), ("mask", b'\x62'), ("gateway", b'\x63'), ("mode", b'\x60'), 
        ("l_port", b'\x64'), ("r_ip", b'\x65'), ("r_port", b'\x66'), ("baud", b'\x71'), 
        ("uart_p", b'\x22'), ("dhcp", b'\x73')
    )
    for key, cmd in cmd_list:
        res[key] = _query_pure(cmd)
    cfg.value = True
    sleep(0.2)

    s = net_settings
    s["local_ip"] = ".".join(str(x) for x in res["ip"][-4:])
    s["subnet_mask"] = ".".join(str(x) for x in res["mask"][-4:])
    s["gateway"] = ".".join(str(x) for x in res["gateway"][-4:])
    s["target_ip"] = ".".join(str(x) for x in res["r_ip"][-4:])
    s["mode"] = int(res["mode"][-1])
    s["local_port"] = int.from_bytes(res["l_port"][-2:], "little")
    s["target_port"] = int.from_bytes(res["r_port"][-2:], "little")
    s["baudrate"] = int.from_bytes(res["baud"][-4:], "little")
    s["dhcp"] = 1 if microcontroller.nvm[0] == 1 else 0

    r_uart = res["uart_p"]
    if len(r_uart) >= 3:
        s["stop"] = 1 if r_uart[-3] == 0x01 else 2
        s["parity"] = {4: "None", 0: "Even", 1: "Odd", 2: "Mark", 3: "Space"}.get(r_uart[-2], "None")
        s["bits"] = r_uart[-1]


def write_network_settings(ip, mask, gw, lp):
    _enter_config()
    uart.write(b'\x57\xab\x33\x00')
    sleep(0.1)
    uart.write(b'\x57\xab\x11' + _ip_to_bytes(ip)); sleep(0.1)
    uart.write(b'\x57\xab\x12' + _ip_to_bytes(mask)); sleep(0.1)
    uart.write(b'\x57\xab\x13' + _ip_to_bytes(gw)); sleep(0.1)
    uart.write(b'\x57\xab\x14' + int(lp).to_bytes(2, "little")); sleep(0.1)
    microcontroller.nvm[0] = 0
    _exit_config_and_save()
    
def set_dhcp(enable):
    _enter_config()
    val = b'\x01' if enable else b'\x00'
    uart.write(b'\x57\xab\x11\x00\x00\x00\x00'); sleep(0.1)
    uart.write(b'\x57\xab\x33' + val); sleep(0.1)
    microcontroller.nvm[0] = 1 if enable else 0
    _exit_config_and_save()

def set_mode(mode_val):
    """Alters structural operating socket profile vectors maps parameters."""
    _enter_config()
    uart.write(b'\x57\xab\x10' + bytes([mode_val]))
    sleep(0.1)
    _exit_config_and_save()

def set_baudrate(baud_val):
    """Modifies default serial interface communication speed properties registers."""
    _enter_config()
    uart.write(b'\x57\xab\x21' + int(baud_val).to_bytes(4, "little"))
    sleep(0.1)
    net_settings["baudrate"] = int(baud_val)
    _exit_config_and_save()

def reset_to_factory():
    """Dispatches structural hardware hex code 0x0F to erase internal EEPROM layout."""
    _enter_config()
    uart.write(b'\x57\xab\x0F')
    sleep(0.1)
    _exit_config_and_save()

# ============================================================================
# SECTION 3: HUMAN CONSOLE SHELL ENGINE
# ============================================================================
def print_help():
    """Displays comprehensive interactive operational menu choices parameters."""
    print("\n=== Самостоятельная консоль CH9120 ===")
    print("  read       - Вычитать текущие параметры сети из чипа")
    print("  dhcp on    - Включить DHCP и перезагрузить трансивер")
    print("  dhcp off   - Отключить DHCP и перезагрузить трансивер")
    print("  mode 0     - Переключить в режим TCP Server (для Веб-страницы)")
    print("  mode 1     - Переключить в режим TCP Client")
    print("  set_net    - Записать локальную сеть (IP, Маска, Шлюз, Порт)")
    print("  set_target - Записать настройки сервера (Конечный IP и Порт)")
    print("  set_baud   - Установить скорость UART трансивера")
    print("  reset      - ПОЛНЫЙ СБРОС всех настроек чипа на ЗАВОДСКИЕ (0x0F)")
    print("  exit       - Полностью ЗАВЕРШИТЬ работу этой программы")
    print("======================================")

def run_console():
    """Spawns the continuous human interaction loop routing text instructions."""
    print_help()
    s = net_settings
    
    while True:
        try:
            raw_input = input("\nCH9120_Console> ")
            cmd = raw_input.strip().lower()
            
            if cmd == "help":
                print_help()
                
            elif cmd == "read":
                print("Считывание физических параметров с трансивера...")
                read_network_settings()
                m_text = {0: "TCP Server", 1: "TCP Client", 2: "UDP Server", 3: "UDP Client"}.get(s["mode"], "Unknown")
                
                print("\n[АКТУАЛЬНЫЕ НАСТРОЙКИ CH9120]:")
                print(f"  Режим сокета : {s['mode']} ({m_text})")
                print(f"  Статус DHCP  : {'ВКЛЮЧЕН (1)' if s['dhcp'] == 1 else 'ВЫКЛЮЧЕН (0)'}")
                print(f"  Локальный IP : {s['local_ip']} | Маска: {s['subnet_mask']} | Шлюз: {s['gateway']}")
                print(f"  Локальный Порт: {s['local_port']} -> Удаленный Порт: {s['target_port']}")
                print(f"  Удаленный IP : {s['target_ip']}")
                print(f"  Физика UART  : {s['baudrate']} бод, {s['bits']}-{s['parity']}-{s['stop']}")
                
            elif cmd == "dhcp on": 
                print("Включение DHCP..."); set_dhcp(True)
                print("Параметры сохранены. Перезагрузи плату и подожди 10 сек")
                
            elif cmd == "dhcp off": 
                print("Отключение DHCP..."); set_dhcp(False)
                print("Параметры сохранены. Перезагрузи плату и подожди 10 сек")
                
            elif cmd == "mode 0": 
                print("Переключение в TCP Server..."); set_mode(0)
                print("Режим TCP Server применен.")
                
            elif cmd == "mode 1": 
                print("Переключение в TCP Client..."); set_mode(1)
                print("Режим TCP Client применен.")
                
            elif cmd == "set_net":
                print("\n--- Настройка статических параметров локальной сети ---")
                ip = input("Введите Локальный IP: ").strip()
                mask = input("Введите Маску подсети: ").strip()
                gw = input("Введите Шлюз: ").strip()
                lp = input("Введите Локальный порт: ").strip()
                print("Запись параметров сети и автоматический перезапуск чипа...")
                write_network_settings(ip, mask, gw, lp)
                print("Параметры успешно применились!")
                
            elif cmd == "set_target":
                print("\n--- Настройка параметров удаленного сервера ---")
                tip = input("Введите Удаленный IP (Target IP): ").strip()
                tport = input("Введите Удаленный порт (Target Port): ").strip()
                print("Запись настроек сервера и перезапуск чипа...")
                _enter_config()
                uart.write(b'\x57\xab\x15' + _ip_to_bytes(tip)); sleep(0.1)
                uart.write(b'\x57\xab\x16' + int(tport).to_bytes(2, "little")); sleep(0.1)
                _exit_config_and_save()
                print("Настройки сервера успешно сохранены!")
                
            elif cmd == "set_baud":
                print("\n--- Изменение битрейта трансивера CH9120 ---")
                baud_val = input("Введите новую скорость UART: ").strip()
                print("Запись новой скорости и перезапуск...")
                set_baudrate(baud_val)
                print("Скорость успешно изменена!")
                
            elif cmd == "reset":
                print("\n⚠️ ВНИМАНИЕ: Запуск процедуры полного сброса памяти CH9120...")
                print("Стирание конфигурационных регистров и EEPROM через команду 0x0F...")
                reset_to_factory()
                
                net_settings.clear()
                net_settings.update({
                    "mode": 0, "dhcp": 0, "local_ip": "192.168.1.200", "subnet_mask": "255.255.255.0",
                    "gateway": "192.168.1.1", "local_port": 1000, "target_ip": "192.168.1.200",
                    "target_port": 1000, "baudrate": 9600, "bits": 8, "stop": 1, "parity": "None"
                })
                print("✅ Чип CH9120 успешно сброшен к заводским настройкам и перезапущен!")
                
            elif cmd == "exit":
                print("\nЗавершение работы консоли конфигуратора. До свидания!")
                sys.exit()
                
            elif cmd == "":
                pass
            else:
                print(f"Неизвестная команда: '{cmd}'. Введите 'help' или 'exit'")
        except KeyboardInterrupt:
            print("\n🛑 Breakout transaction caught. Type 'exit' to cleanly terminate execution threads.")

# ============================================================================
# RUNTIME ENTRY EXECUTION POINT
# ============================================================================
if __name__ == "__main__":
    run_console()
