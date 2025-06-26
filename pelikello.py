import board
import busio
import adafruit_ssd1306
import RPi.GPIO as GPIO
import time
import numpy as np
import sounddevice as sd
from PIL import Image, ImageDraw

# I2C OLED
i2c = busio.I2C(board.SCL, board.SDA)
display = adafruit_ssd1306.SSD1306_I2C(128, 64, i2c)

# GPIO setup
GPIO.setmode(GPIO.BCM)
ENCODER_BTN_PIN = 17
ENCODER_A_PIN = 15
ENCODER_B_PIN = 14
VIEW_BUTTON_PIN = 18  # Changed from BACK_BUTTON_PIN
CONFIRM_BUTTON_PIN = 27
for pin in [ENCODER_BTN_PIN, ENCODER_A_PIN, ENCODER_B_PIN, VIEW_BUTTON_PIN, CONFIRM_BUTTON_PIN]:
    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# Variables
current_view = "equalizer"  # Can be "equalizer", "pelikello", or "settings"
last_view_state = GPIO.input(VIEW_BUTTON_PIN)
last_confirm_state = GPIO.input(CONFIRM_BUTTON_PIN)
last_encoder_state = GPIO.input(ENCODER_A_PIN)
menu_option = 0
setting_values = ["EQ Mode", "Sensitivity", "Piip Duration", "Monitor Freq", "Tolerance", "Threshold"]

# Audio settings
SAMPLE_RATE = 96000
DURATION = 0.02
FFT_SIZE = 2048

# Adjustable settings
lower_freq_limit = 2000
upper_freq_limit = 30000
sensitivity = 8

MONITOR_FREQ = 19000
FREQ_TOLERANCE = 2000
THRESHOLD = 0.2
piip_duration = 0.1
piip_display_duration = 0.5
eq_mode = "raw"  # Can be "normalized", "raw", or "logarithmic"

# Visual setup
bar_width = 2
spacing = 1
num_bars = 60
volumes = [0] * num_bars

# Piip state
show_piip = False
last_piip_time = 0
piip_candidate_start = None

# Game clock
COUNTDOWN_DURATION = 15 * 60
clock_running = False
clock_start_time = None
elapsed_paused_time = 0
pause_start_time = 0
# Add at the top of your file (with other global vars)
last_timer_text = None
last_settings_image = None



# Display buffers
eq_image = Image.new("1", (display.width, display.height))
eq_draw = ImageDraw.Draw(eq_image)

def calculate_volumes(bar_values):
    if eq_mode == "normalized":
        max_value = np.max(bar_values)
        if max_value == 0 or np.isnan(max_value):
            max_value = 1.0
        return [min(v * sensitivity/20 / max_value, 1.0) for v in bar_values]
    elif eq_mode == "raw":
        return [min(v * sensitivity, 1.0) for v in bar_values]
    elif eq_mode == "logarithmic":
        return [min(np.log10(v * sensitivity + 1) / np.log10(sensitivity + 1), 1.0) for v in bar_values]
    else:
        return [0] * len(bar_values)

def draw_equalizer(volumes):
    eq_draw.rectangle((0, 0, display.width, display.height), fill=0)
    max_height = display.height - 16

    threshold_y = display.height - int(THRESHOLD * max_height)
    eq_draw.line((0, threshold_y, display.width, threshold_y), fill=1)

    for i, vol in enumerate(volumes):
        x = i * (bar_width + spacing)
        bar_height = int(vol * max_height)
        y = display.height - bar_height
        if x + bar_width <= display.width:
            eq_draw.rectangle((x, y, x + bar_width - 1, display.height), fill=1)

    freq_per_bar = (upper_freq_limit - lower_freq_limit) / num_bars
    lower_bound = MONITOR_FREQ - FREQ_TOLERANCE
    upper_bound = MONITOR_FREQ + FREQ_TOLERANCE
    lower_bar_idx = int((lower_bound - lower_freq_limit) / freq_per_bar)
    upper_bar_idx = int((upper_bound - lower_freq_limit) / freq_per_bar)
    lower_x = lower_bar_idx * (bar_width + spacing)
    upper_x = upper_bar_idx * (bar_width + spacing)

    if 0 <= lower_x < display.width:
        eq_draw.line((lower_x, 16, lower_x, display.height), fill=1)
    if 0 <= upper_x < display.width:
        eq_draw.line((upper_x, 16, upper_x, display.height), fill=1)

    eq_draw.text((0, 0), f"EQ: {eq_mode[:4]}", fill=1)  # Updated text
    if show_piip:
        eq_draw.text((80, 0), "piip!", fill=1)

    display.image(eq_image)
    display.show()

    time.sleep(0.05)

def draw_pelikello():
    global last_timer_text  # Access the global timer cache

    if clock_start_time is not None:
        if clock_running:
            elapsed = time.time() - clock_start_time - elapsed_paused_time
        else:
            elapsed = pause_start_time - clock_start_time - elapsed_paused_time
    else:
        elapsed = 0

    remaining = max(0, COUNTDOWN_DURATION - elapsed)
    minutes = int(remaining // 60)
    seconds = int(remaining % 60)
    timer_text = f"{minutes:02d}:{seconds:02d}"

    if timer_text != last_timer_text:
        image = Image.new("1", (display.width, display.height))
        draw = ImageDraw.Draw(image)

        if show_piip:
            draw.text((80, 0), "piip!", fill=255)

        draw.text((0, 0), "Game Clock", fill=255)
        draw.text((30, 20), "Game Clock", fill=255)
        draw.text((35, 40), timer_text, fill=255)

        display.image(image)
        display.show()
        last_timer_text = timer_text

    time.sleep(0.05)


def draw_settings_menu():
    global last_settings_image

    image = Image.new("1", (display.width, display.height))
    draw = ImageDraw.Draw(image)

    if show_piip:
        draw.text((80, 0), "piip!", fill=255)

    for idx, name in enumerate(setting_values):
        prefix = ">" if idx == menu_option else " "
        value = ""
        if name == "EQ Mode":
            value = eq_mode
        elif name == "Sensitivity":
            value = f"{sensitivity:.2f}"
        elif name == "Piip Duration":
            value = f"{piip_duration:.2f}s"
        elif name == "Monitor Freq":
            value = f"{MONITOR_FREQ}Hz"
        elif name == "Tolerance":
            value = f"{FREQ_TOLERANCE}Hz"
        elif name == "Threshold":
            value = f"{THRESHOLD:.2f}"
        draw.text((0, 10 + idx * 10), f"{prefix} {name}: {value}", fill=255)

    if last_settings_image is None or image.tobytes() != last_settings_image.tobytes():
        display.image(image)
        display.show()
        last_settings_image = image

    time.sleep(0.05)

    
def audio_callback(indata, frames, time_info, status):
    global volumes, show_piip, last_piip_time, piip_candidate_start

    samples = indata[:, 0]
    fft = np.abs(np.fft.rfft(samples, n=FFT_SIZE))
    freqs = np.fft.rfftfreq(FFT_SIZE, 1 / SAMPLE_RATE)

    freq_edges = np.linspace(lower_freq_limit, upper_freq_limit, num_bars + 1)

    bar_values = []
    for i in range(num_bars):
        mask = (freqs >= freq_edges[i]) & (freqs < freq_edges[i + 1])
        bar = fft[mask]
        bar_values.append(np.mean(bar) if len(bar) > 0 else 0.0)

    volumes[:] = calculate_volumes(bar_values)

    # Use same index range as EQ bars
    freq_per_bar = (upper_freq_limit - lower_freq_limit) / num_bars
    lower_bound = MONITOR_FREQ - FREQ_TOLERANCE
    upper_bound = MONITOR_FREQ + FREQ_TOLERANCE
    lower_bar_idx = int((lower_bound - lower_freq_limit) / freq_per_bar)
    upper_bar_idx = int((upper_bound - lower_freq_limit) / freq_per_bar)

    if 0 <= lower_bar_idx <= upper_bar_idx < len(volumes):
        monitored_volume = np.mean(volumes[lower_bar_idx:upper_bar_idx+1])
        if monitored_volume > THRESHOLD:
            if piip_candidate_start is None:
                piip_candidate_start = time.time()
            elif (time.time() - piip_candidate_start) >= piip_duration:
                show_piip = True
                last_piip_time = time.time()
                piip_candidate_start = None
        else:
            piip_candidate_start = None

# Audio stream
stream = sd.InputStream(callback=audio_callback,
                      channels=1,
                      samplerate=SAMPLE_RATE,
                      blocksize=int(SAMPLE_RATE * DURATION),
                      #device=3)
                      device=None)

stream.start()

try:
    while True:
        view_state = GPIO.input(VIEW_BUTTON_PIN)  # Changed from back_state
        confirm_state = GPIO.input(CONFIRM_BUTTON_PIN)
        encoder_a = GPIO.input(ENCODER_A_PIN)
        encoder_b = GPIO.input(ENCODER_B_PIN)

        # Handle piip-triggered clock start/stop
        if show_piip:
            if not clock_running:
                if clock_start_time is None:
                    clock_start_time = time.time()
                else:
                    elapsed_paused_time += time.time() - pause_start_time
                clock_running = True
            else:
                pause_start_time = time.time()
                clock_running = False

        # View switching (between EQ and Game Clock)
        if view_state == GPIO.LOW and last_view_state == GPIO.HIGH:
            current_view = {"equalizer": "pelikello", "pelikello": "equalizer", "settings": "equalizer"}[current_view]
            time.sleep(0.2)
        last_view_state = view_state

        # Settings access
        if confirm_state == GPIO.LOW and last_confirm_state == GPIO.HIGH:
            current_view = "settings" if current_view in ["equalizer", "pelikello"] else "equalizer"
            time.sleep(0.2)
        last_confirm_state = confirm_state

        # Encoder navigation
        if encoder_a != last_encoder_state:
            if current_view == "settings":
                if GPIO.input(ENCODER_B_PIN) == GPIO.HIGH:
                    menu_option = (menu_option + 1) % len(setting_values)
                else:
                    menu_option = (menu_option - 1) % len(setting_values)
            time.sleep(0.1)
        last_encoder_state = encoder_a

        # Encoder button press (settings adjustment)
        if GPIO.input(ENCODER_BTN_PIN) == GPIO.LOW:
            if current_view == "settings":
                current_setting = setting_values[menu_option]
                if current_setting == "EQ Mode":
                    modes = ["normalized", "raw", "logarithmic"]
                    current_index = modes.index(eq_mode)
                    eq_mode = modes[(current_index + 1) % len(modes)]
                elif current_setting == "Sensitivity":
                    sensitivity = 0.1 if sensitivity > 10.0 else sensitivity + 0.1
                elif current_setting == "Piip Duration":
                    piip_duration = 0.01 if piip_duration > 2.0 else piip_duration + 0.05
                elif current_setting == "Monitor Freq":
                    MONITOR_FREQ = 100 if MONITOR_FREQ > 20000 else MONITOR_FREQ + 50
                elif current_setting == "Tolerance":
                    FREQ_TOLERANCE = 10 if FREQ_TOLERANCE > 1000 else FREQ_TOLERANCE + 10
                elif current_setting == "Threshold":
                    THRESHOLD = 0.05 if THRESHOLD > 1.0 else THRESHOLD + 0.05
                time.sleep(0.2)

        # Draw current view
        if current_view == "equalizer":
            draw_equalizer(volumes)
        elif current_view == "pelikello":
            draw_pelikello()
        elif current_view == "settings":
            draw_settings_menu()

        # Reset piip after display duration
        if show_piip and (time.time() - last_piip_time) >= piip_display_duration:
            show_piip = False

        time.sleep(0.005)

except KeyboardInterrupt:
    print("Program interrupted")
finally:
    GPIO.cleanup()
    stream.stop()
    stream.close()