#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <arduinoFFT.h>

#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define NUM_BARS 20
#define BAR_WIDTH 5
#define BAR_SPACING 1
#define MIC_PIN 36
#define BUTTON_PIN 0
#define LED_PIN 2  
#define SAMPLES 128  
#define SAMPLING_FREQUENCY 60000  

int minAmplitudeThreshold = 350;  // Default amplitude threshold
int interval = 800;  // Time between two valid sounds for "STOP"
int duration = 50;  // Minimum time a sound must be above the threshold
int freqRangeLow = 10000;  // Default low frequency range
int freqRangeHigh = 15000; // Default high frequency range
float micSensitivity = 2.0;  // Default sensitivity

unsigned long firstPeakTime = 0;
unsigned long soundStartTime = 0;
bool firstPeakDetected = false;
bool secondPeakDetected = false;
bool soundActive = false;
bool ledActive = false;
unsigned long ledStartTime = 0;

double vReal[SAMPLES];
double vImag[SAMPLES];
ArduinoFFT<double> FFT = ArduinoFFT<double>(vReal, vImag, SAMPLES, SAMPLING_FREQUENCY);

Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);

bool inSettingsMenu = false;
int selectedSetting = 0;
int currentSettingsScreen = 0;  // 0 = Screen 1, 1 = Screen 2
unsigned long buttonPressStart = 0;
bool buttonHeld = false;

const char* settingNamesScreen1[] = { "Threshold", "Duration", "Range Low", "Range High", "Interval" };
const char* settingNamesScreen2[] = { "Sensitivity", "Exit" };
const int numSettingsScreen1 = 5;  // Number of settings in Screen 1
const int numSettingsScreen2 = 2;  // Number of settings in Screen 2

float lastDetectedFrequency = 0;  // Stores the frequency of the last detected sound

void setup() {
    Serial.begin(115200);
    pinMode(BUTTON_PIN, INPUT_PULLUP);
    pinMode(LED_PIN, OUTPUT);
    
    if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
        Serial.println(F("SSD1306 allocation failed"));
        for (;;);
    }
    analogReadResolution(12);
}

void loop() {
    handleButtonPress();
    display.clearDisplay();

    if (inSettingsMenu) {
        drawSettingsMenu();
    } else {
        sampleAudio();
        int levels[NUM_BARS];
        getEqualizerLevels(levels);
        unsigned long currentTime = millis();

        bool freqInRange = checkFrequencyRange();

        if (freqInRange) {
            if (!soundActive) {
                soundStartTime = currentTime;
                soundActive = true;
                Serial.println("Sound detected, starting timer.");
            }

            if (soundActive && currentTime - soundStartTime >= duration) {
                if (!firstPeakDetected) {
                    firstPeakTime = currentTime;
                    firstPeakDetected = true;
                    Serial.println("First peak detected.");
                } else if (currentTime - firstPeakTime <= interval) {
                    secondPeakDetected = true;
                    Serial.println("Second peak detected!");
                }
            }
        } else {
            soundActive = false;
        }

        // Handle LED logic
        if (secondPeakDetected) {
            digitalWrite(LED_PIN, HIGH);
            ledActive = true;
            ledStartTime = millis();
            Serial.println("LED turned ON.");
            secondPeakDetected = false;  // Reset for next detection
        }

        if (ledActive && millis() - ledStartTime >= 1000) {  // LED stays on for 1 second
            digitalWrite(LED_PIN, LOW);
            ledActive = false;
            firstPeakDetected = false;
            Serial.println("LED turned OFF. Resetting detection.");
        }

        // Display status
        display.setTextSize(1);
        display.setTextColor(SSD1306_WHITE);
        display.setCursor(50, 0);

        if (secondPeakDetected) {
            display.print("STOP");
        } else if (firstPeakDetected && millis() - firstPeakTime <= interval) {
            display.print("START");
        }

        // Display the frequency of the last detected sound
        display.setCursor(0, 0);  // Position for frequency display
        display.print((int)lastDetectedFrequency);  // Cast to int to remove decimals
        display.print(" Hz");

        drawEqualizer(levels);
    }
    
    display.display();
    delay(30);
}

void drawEqualizer(int *levels) {
    // Draw the bars
    for (int i = 1; i < NUM_BARS; i++) {  
        int x = i * (BAR_WIDTH + BAR_SPACING) + 2;
        int barHeight = map(levels[i], 0, 4095, 2, SCREEN_HEIGHT - 15);
        barHeight = constrain(barHeight, 2, SCREEN_HEIGHT - 15);
        display.fillRect(x, SCREEN_HEIGHT - barHeight, BAR_WIDTH, barHeight, SSD1306_WHITE);
    }

    // Draw the vertical lines representing the frequency range limits
    int boxLeft = map(freqRangeLow, 0, SAMPLING_FREQUENCY / 2, 0, SCREEN_WIDTH); // Map freqRangeLow to x-axis
    int boxRight = map(freqRangeHigh, 0, SAMPLING_FREQUENCY / 2, 0, SCREEN_WIDTH); // Map freqRangeHigh to x-axis

    // Define the height of the vertical lines (adjust these values to change the length)
    int verticalLineTop = 10;  // Top y-coordinate of the vertical lines (increase to make lines shorter)
    int verticalLineBottom = SCREEN_HEIGHT - 10;  // Bottom y-coordinate of the vertical lines (decrease to make lines shorter)

    // Draw the left vertical line (shorter)
    display.drawLine(boxLeft, verticalLineTop, boxLeft, verticalLineBottom, SSD1306_WHITE);

    // Draw the right vertical line (shorter)
    display.drawLine(boxRight, verticalLineTop, boxRight, verticalLineBottom, SSD1306_WHITE);

    // Draw the horizontal line representing the amplitude threshold
    int thresholdY = map(minAmplitudeThreshold, 0, 4095, SCREEN_HEIGHT - 1, 0); // Map threshold to y-axis
    display.drawLine(0, thresholdY, SCREEN_WIDTH - 1, thresholdY, SSD1306_WHITE);
}

void drawSettingsMenu() {
    display.setTextSize(1);
    display.setTextColor(SSD1306_WHITE);

    int startY = 5;
    if (currentSettingsScreen == 0) {
        // Draw Screen 1 settings
        for (int i = 0; i < numSettingsScreen1; i++) {
            int yPosition = startY + (i * 12);
            if (i == selectedSetting) {
                display.fillRect(10, yPosition, 108, 10, SSD1306_WHITE);
                display.setTextColor(SSD1306_BLACK);
            } else {
                display.setTextColor(SSD1306_WHITE);
            }
            display.setCursor(15, yPosition + 2);
            display.print(settingNamesScreen1[i]);
            display.print(": ");
            switch (i) {
                case 0: display.print(minAmplitudeThreshold); break;
                case 1: display.print(duration); break;
                case 2: display.print(freqRangeLow); break;
                case 3: display.print(freqRangeHigh); break;
                case 4: display.print(interval); break;
            }
        }
    } else {
        // Draw Screen 2 settings
        for (int i = 0; i < numSettingsScreen2; i++) {
            int yPosition = startY + (i * 12);
            if (i == selectedSetting) {
                display.fillRect(10, yPosition, 108, 10, SSD1306_WHITE);
                display.setTextColor(SSD1306_BLACK);
            } else {
                display.setTextColor(SSD1306_WHITE);
            }
            display.setCursor(15, yPosition + 2);
            display.print(settingNamesScreen2[i]);
            display.print(": ");
            switch (i) {
                case 0: display.print(micSensitivity); break;
            }
        }
    }
}

void handleButtonPress() {
    if (digitalRead(BUTTON_PIN) == LOW) {
        if (!buttonHeld) {
            buttonHeld = true;
            buttonPressStart = millis();
        }

        if (millis() - buttonPressStart >= 1000) {
            if (!inSettingsMenu) {
                inSettingsMenu = true;
                selectedSetting = 0;
                currentSettingsScreen = 0;  // Reset to Screen 1 when entering settings
            } else {
                selectedSetting++;
                if (currentSettingsScreen == 0 && selectedSetting >= numSettingsScreen1) {
                    // Switch to Screen 2
                    currentSettingsScreen = 1;
                    selectedSetting = 0;
                } else if (currentSettingsScreen == 1 && selectedSetting >= numSettingsScreen2) {
                    // Switch back to Screen 1
                    currentSettingsScreen = 0;
                    selectedSetting = 0;
                }
            }
            delay(500);
        }
    } else {
        if (buttonHeld && millis() - buttonPressStart < 1000) {
            if (inSettingsMenu) {
                if (currentSettingsScreen == 0) {
                    // Handle Screen 1 settings
                    switch (selectedSetting) {
                        case 0: 
                            minAmplitudeThreshold += 50;
                            if (minAmplitudeThreshold > 900) minAmplitudeThreshold = 100;
                            break;
                        case 1:
                            duration += 10;
                            if (duration > 200) duration = 0;
                            break;
                        case 2:
                            freqRangeLow += 100; 
                            if (freqRangeLow > freqRangeHigh) freqRangeLow = 0; 
                            break;
                        case 3:
                            freqRangeHigh += 100;
                            if (freqRangeHigh > 20000) freqRangeHigh = freqRangeLow;
                            break;
                        case 4:
                            interval += 100;
                            if (interval > 2000) interval = 100;
                            break;
                    }
                } else {
                    // Handle Screen 2 settings
                    switch (selectedSetting) {
                        case 0:  // Sensitivity setting
                            micSensitivity += 0.1;
                            if (micSensitivity > 5.0) micSensitivity = 1.0;
                            break;
                        case 1:  // Exit
                            inSettingsMenu = false;
                            break;
                    }
                }
            }
        }
        buttonHeld = false;
    }
}

void sampleAudio() {
    for (int i = 0; i < SAMPLES; i++) {
        int rawValue = analogRead(MIC_PIN);
        vReal[i] = rawValue * micSensitivity;  // Apply sensitivity
        vImag[i] = 0;
        delayMicroseconds(1000000 / SAMPLING_FREQUENCY);
    }
    FFT.windowing(FFTWindow::Hamming, FFTDirection::Forward);
    FFT.compute(FFTDirection::Forward);
    FFT.complexToMagnitude();
}

void getEqualizerLevels(int *levels) {
    int binSize = (SAMPLES / 2) / NUM_BARS;
    for (int i = 0; i < NUM_BARS; i++) {
        double avg = 0;
        for (int j = 0; j < binSize; j++) {
            avg += vReal[i * binSize + j];
        }
        levels[i] = avg / binSize;
    }
}

bool checkFrequencyRange() {
    bool detected = false;
    float maxMagnitude = 0;
    int maxBin = 0;

    for (int i = 0; i < (SAMPLES / 2); i++) {
        float frequency = (i * (SAMPLING_FREQUENCY / 2)) / (SAMPLES / 2);
        if (frequency >= freqRangeLow && frequency <= freqRangeHigh && vReal[i] > minAmplitudeThreshold) {
            detected = true;
            if (vReal[i] > maxMagnitude) {
                maxMagnitude = vReal[i];
                maxBin = i;
            }
        }
    }

    if (detected) {
        // Calculate the frequency of the detected sound
        lastDetectedFrequency = (maxBin * (SAMPLING_FREQUENCY / 2)) / (SAMPLES / 2);
    }

    return detected;
}
