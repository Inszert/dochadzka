#include <SPI.h>
#include <MFRC522.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ST7789.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <SPIFFS.h>
#include "time.h"
#include <vector>

// Configuration
#define WRITE_MODE false  // true = Write to cards, false = Read from cards
#define WIFI_SSID "Asda"
#define WIFI_PASS "12345678"

// API endpoints
#define API_URL "https://fuzzy-trina-prenako-sro-b1bc9170.koyeb.app/api/shift_by_name"
#define API_RETRY_URL "https://fuzzy-trina-prenako-sro-b1bc9170.koyeb.app/api/shift_by_name_with_time"
#define WORK_LOCATION "Zoo"

// Pin definitions
#define LCD_MOSI 23
#define LCD_SCLK 18
#define LCD_CS   15
#define LCD_DC    2
#define LCD_RST   4
#define LCD_BLK  32

#define RST_PIN  21
#define SS_PIN   12
#define MISO_PIN 13

// WiFi variables
bool wifiConnected = false;
unsigned long lastWifiAttempt = 0;
const unsigned long WIFI_RETRY_INTERVAL = 300000; // 5 minutes

// SPIFFS variables
unsigned long lastSpiffsPrint = 0;
const unsigned long SPIFFS_PRINT_INTERVAL = 300000; // 5 minutes
bool spiffsContentChanged = false;
int spiffsEntryCount = 0;
unsigned long lastRetryAttempt = 0;
const unsigned long RETRY_INTERVAL = 10000; // Try to retry every 10 seconds when conditions are met
bool isRetrying = false;
bool immediateRetryNeeded = false; // Flag for immediate retry after WiFi connection

// Time tracking for backtracking
unsigned long bootTime = 0;
time_t bootEpoch = 0;
bool timeSynced = false;
unsigned long lastTimeSyncAttempt = 0;
const unsigned long TIME_SYNC_INTERVAL = 3600000;
time_t lastKnownTime = 0; // Store last known time for drift calculation
unsigned long lastTimeCheck = 0; // When we last checked the time

// Display update
unsigned long lastDisplayUpdate = 0;
const unsigned long DISPLAY_UPDATE_INTERVAL = 1000; // Update time every second

// Time
const char* ntpServer = "pool.ntp.org";
const long gmtOffset_sec = 3600; // GMT+1 (CET)
const int daylightOffset_sec = 3600; // +1 hour for daylight saving (CEST)

Adafruit_ST7789 lcd = Adafruit_ST7789(LCD_CS, LCD_DC, LCD_RST);
MFRC522 rfid(SS_PIN, RST_PIN);
MFRC522::MIFARE_Key key;

void setup() {
  Serial.begin(9600);

  // SPIFFS init
  if(!SPIFFS.begin(true)) {
    Serial.println("SPIFFS Mount Failed");
  }
  
  // Clean up invalid entries on startup
  cleanupSpiffs();
  updateSpiffsEntryCount();

  SPI.begin(LCD_SCLK, MISO_PIN, LCD_MOSI, LCD_CS);
  lcd.init(135, 240);
  lcd.setRotation(2); // Rotate display 180 degrees (upside down)
  lcd.fillScreen(ST77XX_BLACK);
  lcd.setTextWrap(true);
  lcd.setTextSize(2);

  rfid.PCD_Init();
  for (byte i = 0; i < 6; i++) key.keyByte[i] = 0xFF;

  bootTime = millis();
  
  connectToWiFi();
  initTime();

  updateMainDisplay();
}

void loop() {
  // Update WiFi status
  checkWifiStatus();
  
  // Retry WiFi connection if needed
  if (!wifiConnected && millis() - lastWifiAttempt >= WIFI_RETRY_INTERVAL) {
    connectToWiFi();
  }
  
  // Periodically try to sync time (only if WiFi is connected)
  if (wifiConnected && !timeSynced && millis() - lastTimeSyncAttempt >= TIME_SYNC_INTERVAL) {
    syncTime();
  }
  
  // Update time on display every second
  if (millis() - lastDisplayUpdate >= DISPLAY_UPDATE_INTERVAL) {
    updateTimeOnDisplay();
    lastDisplayUpdate = millis();
  }

  // Retry failed SPIFFS sends - with priority after WiFi connect
  if (wifiConnected && timeSynced && spiffsEntryCount > 0 && !isRetrying) {
    // Check if we need immediate retry (right after WiFi connect) or if enough time has passed
    if (immediateRetryNeeded || millis() - lastRetryAttempt >= RETRY_INTERVAL) {
      retryFailedRequests();
      immediateRetryNeeded = false;
    }
  }

  // Update SPIFFS count if changed
  if (spiffsContentChanged) {
    updateSpiffsEntryCount();
    updateSpiffsCountOnDisplay();
    spiffsContentChanged = false;
  }

  // Check for new RFID card
  if (rfid.PICC_IsNewCardPresent() && rfid.PICC_ReadCardSerial()) {
    handleCardScan();
  }

  delay(50); // Small delay to prevent CPU hogging
}

// ---------------------------- Display Functions ----------------------------

void updateMainDisplay() {
  lcd.fillScreen(ST77XX_BLACK);
  lcd.setTextSize(2);
  
  // Time at the top
  updateTimeOnDisplay();
  
  // "Scan card" text
  lcd.setCursor(10, 40);
  lcd.setTextColor(ST77XX_WHITE);
  lcd.println("Scan card");
  
  // WiFi status line
  updateWifiStatusOnDisplay();
  
  // SPIFFS entry count
  updateSpiffsCountOnDisplay();
}

void updateTimeOnDisplay() {
  // Clear previous time area (first line)
  lcd.fillRect(0, 0, 240, 20, ST77XX_BLACK);
  
  lcd.setCursor(10, 0);
  lcd.setTextColor(timeSynced ? ST77XX_GREEN : ST77XX_YELLOW);
  
  if (timeSynced) {
    time_t now = getCurrentTime();
    struct tm timeinfo;
    localtime_r(&now, &timeinfo);
    
    char buf[30];
    strftime(buf, sizeof(buf), "%H:%M:%S", &timeinfo);
    lcd.print(buf);
  } else {
    lcd.print("--:--:--");
  }
}

void updateWifiStatusOnDisplay() {
  lcd.setCursor(10, 70);
  
  if (wifiConnected) {
    if (timeSynced) {
      lcd.setTextColor(ST77XX_GREEN);
      lcd.print("WiFi: Connected");
    } else {
      lcd.setTextColor(ST77XX_ORANGE);
      lcd.print("WiFi: No Time");
    }
  } else {
    lcd.setTextColor(ST77XX_RED);
    lcd.print("WiFi: Offline");
  }
}

void updateSpiffsCountOnDisplay() {
  lcd.setCursor(10, 100);
  lcd.setTextColor(ST77XX_WHITE);
  lcd.print("Saved: ");
  lcd.print(spiffsEntryCount);
}

void updateSpiffsEntryCount() {
  spiffsEntryCount = 0;
  if (!SPIFFS.exists("/failed.txt")) return;

  File file = SPIFFS.open("/failed.txt", FILE_READ);
  if (!file) return;

  while (file.available()) {
    String line = file.readStringUntil('\n');
    line.trim();
    if (line.length() > 0) {
      spiffsEntryCount++;
    }
  }
  file.close();
}

void blinkScreen(uint16_t color, int duration) {
  lcd.fillScreen(color);
  delay(duration);
  updateMainDisplay();
}

void showResultAndReturn(String message, uint16_t color, int duration) {
  lcd.fillScreen(color);
  lcd.setCursor(10, 60);
  lcd.setTextColor(ST77XX_BLACK);
  lcd.setTextSize(2);
  lcd.println(message);
  delay(duration);
  updateMainDisplay();
}

// ---------------------------- SPIFFS Management ----------------------------

void cleanupSpiffs() {
  if (!SPIFFS.exists("/failed.txt")) return;
  
  File file = SPIFFS.open("/failed.txt", FILE_READ);
  if (!file) return;
  
  std::vector<String> validLines;
  int removedCount = 0;
  
  while (file.available()) {
    String line = file.readStringUntil('\n');
    line.trim();
    if (line.length() == 0) continue;
    
    int first = line.indexOf('|');
    int second = line.indexOf('|', first + 1);
    
    if (first == -1 || second == -1) {
      removedCount++;
      continue; // Skip invalid format
    }
    
    String name = line.substring(0, first);
    String location = line.substring(first + 1, second);
    String millisStr = line.substring(second + 1);
    
    // Validate fields
    if (name.length() == 0 || name == " " || 
        location.length() == 0 || 
        millisStr.length() == 0 || millisStr.toInt() == 0) {
      removedCount++;
      continue; // Skip invalid data
    }
    
    validLines.push_back(line);
  }
  file.close();
  
  // Rewrite file with only valid lines
  if (removedCount > 0 || validLines.size() != spiffsEntryCount) {
    File f = SPIFFS.open("/failed.txt", FILE_WRITE);
    if (f) {
      for (auto &l : validLines) {
        f.println(l);
      }
      f.close();
    }
    Serial.println("Cleaned up SPIFFS: removed " + String(removedCount) + " invalid entries");
    spiffsContentChanged = true;
  }
}

// ---------------------------- Card Functions ----------------------------

void handleCardScan() {
  // Build UID string
  String uidStr = "";
  for (byte i = 0; i < rfid.uid.size; i++) {
    if (rfid.uid.uidByte[i] < 0x10) uidStr += "0";
    uidStr += String(rfid.uid.uidByte[i], HEX);
  }
  uidStr.toUpperCase();

  Serial.println("Card UID:");
  Serial.println(uidStr);

  byte safeBlocks[] = {4, 8, 12};

  if (WRITE_MODE) {
    const char* messages[] = {"HELLO", "WORLD", "ESP32"};
    writeToCard(safeBlocks, messages);
  } else {
    readFromCard(safeBlocks, uidStr);
  }

  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();
}

void writeToCard(byte safeBlocks[], const char* messages[]) {
  bool success = true;
  
  for (byte i = 0; i < 3; i++) {
    byte block = safeBlocks[i];
    MFRC522::StatusCode status = rfid.PCD_Authenticate(
      MFRC522::PICC_CMD_MF_AUTH_KEY_A, block, &key, &(rfid.uid));
    if (status != MFRC522::STATUS_OK) {
      success = false;
      continue;
    }

    byte buffer[16] = {0};
    const char* msg = messages[i];
    for (byte j = 0; j < strlen(msg) && j < 16; j++) buffer[j] = msg[j];

    status = rfid.MIFARE_Write(block, buffer, 16);
    if (status != MFRC522::STATUS_OK) {
      success = false;
    }
  }

  if (success) {
    showResultAndReturn("Write OK!", ST77XX_GREEN, 3000);
  } else {
    showResultAndReturn("Write Failed", ST77XX_RED, 3000);
  }
}

void readFromCard(byte safeBlocks[], String uidStr) {
  String employeeName = "";
  bool readSuccess = true;

  for (byte i = 0; i < 3; i++) {
    byte block = safeBlocks[i];
    MFRC522::StatusCode status = rfid.PCD_Authenticate(
      MFRC522::PICC_CMD_MF_AUTH_KEY_A, block, &key, &(rfid.uid));
    if (status != MFRC522::STATUS_OK) {
      readSuccess = false;
      continue;
    }

    byte buffer[18];
    byte size = sizeof(buffer);
    status = rfid.MIFARE_Read(block, buffer, &size);
    if (status != MFRC522::STATUS_OK) {
      readSuccess = false;
      continue;
    }

    String blockData = "";
    for (byte j = 0; j < 16; j++) {
      char c = buffer[j];
      if (c >= 32 && c <= 126) blockData += c;
    }

    if (i < 2) {
      if (employeeName.length() > 0) employeeName += " ";
      employeeName += blockData;
    }
  }

  employeeName.trim();
  
  // Validate employee name
  if (employeeName.length() == 0 || employeeName == " " || readSuccess == false) {
    Serial.println("Failed to read valid employee name from card!");
    showResultAndReturn("Read Failed", ST77XX_RED, 3000);
    return;
  }
  
  Serial.println("Employee name: " + employeeName);
  sendShiftRequest(employeeName);
}

// ---------------------------- HTTP + SPIFFS ----------------------------

void sendShiftRequest(String employeeName) {
  // Double-check that employee name is valid
  if (employeeName.length() == 0 || employeeName == " ") {
    Serial.println("Error: Attempted to send request with empty employee name");
    showResultAndReturn("Invalid Name", ST77XX_RED, 3000);
    return;
  }
  
  unsigned long scanTime = millis();
  
  if (!wifiConnected || !timeSynced) {
    Serial.println("Cannot send immediately - saving request for later");
    saveFailedRequest(employeeName, WORK_LOCATION, scanTime);
    showResultAndReturn("Saved to SPIFFS", ST77XX_ORANGE, 3000);
    return;
  }

  // We have WiFi and time sync, try to send immediately
  String timestamp = millisToISO(scanTime);
  
  // Validate timestamp
  if (timestamp.length() == 0) {
    Serial.println("Invalid timestamp, saving for later");
    saveFailedRequest(employeeName, WORK_LOCATION, scanTime);
    showResultAndReturn("Time Error", ST77XX_ORANGE, 3000);
    return;
  }
  
  HTTPClient http;
  http.begin(API_URL);
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(10000);

  String payload = "{ \"employee_name\": \"" + employeeName + "\", \"work_location\": \"" + String(WORK_LOCATION) + "\" }";

  int httpResponseCode = http.POST(payload);
  String response = httpResponseCode > 0 ? http.getString() : "";

  Serial.println("Sent: " + payload);
  Serial.println("Response code: " + String(httpResponseCode));
  if (response.length() > 0) {
    Serial.println("Response: " + response);
  }

  if (httpResponseCode > 0 && response.indexOf("\"success\":true") != -1) {
    showResultAndReturn("Success!", ST77XX_GREEN, 3000);
  } else {
    // If immediate send fails, save for retry
    saveFailedRequest(employeeName, WORK_LOCATION, scanTime);
    showResultAndReturn("Saved for retry", ST77XX_ORANGE, 3000);
  }

  http.end();
}

void retryFailedRequests() {
  // Double-check conditions before starting retry
  if (!wifiConnected || !timeSynced || spiffsEntryCount == 0 || isRetrying) {
    return;
  }
  
  isRetrying = true;
  lastRetryAttempt = millis();
  
  Serial.println("Starting retry of failed requests...");
  
  if (!SPIFFS.exists("/failed.txt")) {
    isRetrying = false;
    return;
  }

  File file = SPIFFS.open("/failed.txt", FILE_READ);
  if (!file) {
    isRetrying = false;
    return;
  }

  std::vector<String> remainingLines;
  bool anySent = false;
  int totalToSend = 0;
  int sentCount = 0;
  int invalidCount = 0;

  // First count total to send
  while (file.available()) {
    String line = file.readStringUntil('\n');
    line.trim();
    if (line.length() > 0) totalToSend++;
  }
  file.close();

  if (totalToSend == 0) {
    isRetrying = false;
    return;
  }

  // Now process each line
  file = SPIFFS.open("/failed.txt", FILE_READ);
  
  while (file.available()) {
    String line = file.readStringUntil('\n');
    line.trim();
    if (line.length() == 0) continue;

    int first = line.indexOf('|');
    int second = line.indexOf('|', first + 1);
    if(first == -1 || second == -1) {
      invalidCount++;
      continue; // Skip invalid lines
    }

    String name = line.substring(0, first);
    String location = line.substring(first + 1, second);
    unsigned long scanMillis = line.substring(second + 1).toInt();

    // Validate employee name
    if (name.length() == 0 || name == " ") {
      Serial.println("Skipping invalid entry with empty name");
      invalidCount++;
      continue; // Skip entries with empty names
    }

    String timestamp = millisToISO(scanMillis);
    
    // Check if timestamp is valid
    if (timestamp.length() == 0) {
      Serial.println("Invalid timestamp, keeping for later");
      remainingLines.push_back(line);
      continue;
    }

    HTTPClient http;
    http.begin(API_RETRY_URL);
    http.addHeader("Content-Type", "application/json");
    http.setTimeout(10000);

    String payload = "{ \"employee_name\": \"" + name + "\", \"work_location\": \"" + location + "\", \"timestamp\": \"" + timestamp + "\" }";

    // Blink blue for each retry attempt
    blinkScreen(ST77XX_BLUE, 200);
    
    int code = http.POST(payload);
    String resp = code > 0 ? http.getString() : "";

    Serial.println("Sending retry: " + payload);
    Serial.println("Response code: " + String(code));

    if (code > 0 && resp.indexOf("\"success\":true") != -1) {
      sentCount++;
      anySent = true;
      Serial.println("Successfully sent: " + name);
    } else {
      remainingLines.push_back(line);
      Serial.println("Failed to send, keeping for later");
    }

    http.end();
    delay(200);
  }
  file.close();

  // Rewrite file with remaining unsent lines
  File f = SPIFFS.open("/failed.txt", FILE_WRITE);
  if (f) {
    for (auto &l : remainingLines) {
      f.println(l);
    }
    f.close();
  }

  if (anySent || invalidCount > 0) {
    spiffsContentChanged = true;
    
    if (sentCount > 0) {
      lcd.fillScreen(ST77XX_BLUE);
      lcd.setCursor(10, 40);
      lcd.setTextColor(ST77XX_WHITE);
      lcd.setTextSize(2);
      lcd.print("Sent: ");
      lcd.print(sentCount);
      lcd.print("/");
      lcd.println(totalToSend - invalidCount);
      
      if (invalidCount > 0) {
        lcd.setCursor(10, 70);
        lcd.print("Invalid: ");
        lcd.print(invalidCount);
      }
      delay(3000);
      updateMainDisplay();
    }
  }
  
  isRetrying = false;
  Serial.println("Retry attempt completed. Sent: " + String(sentCount) + 
                 ", Kept: " + String(remainingLines.size()) + 
                 ", Invalid: " + String(invalidCount));
}

void saveFailedRequest(String name, String location, unsigned long scanMillis) {
  // Validate before saving
  if (name.length() == 0 || name == " ") {
    Serial.println("Error: Attempted to save empty employee name to SPIFFS");
    return;
  }
  
  File file = SPIFFS.open("/failed.txt", FILE_APPEND);
  if(file) {
    file.println(name + "|" + location + "|" + String(scanMillis));
    file.close();
    Serial.println("Saved failed request: " + name + " at millis: " + String(scanMillis));
    spiffsContentChanged = true;
  } else {
    Serial.println("Error: Failed to open SPIFFS file for writing");
  }
}

// ---------------------------- Time Functions with Proper Backtracking ----------------------------

time_t getCurrentTime() {
  if (timeSynced && bootEpoch > 0) {
    // Calculate current time based on boot epoch and elapsed time
    unsigned long elapsedSeconds = (millis() - bootTime) / 1000;
    return bootEpoch + elapsedSeconds;
  }
  return 0;
}

void initTime() {
  if (WiFi.status() == WL_CONNECTED) {
    configTime(gmtOffset_sec, daylightOffset_sec, ntpServer);
    Serial.println("Fetching time from NTP...");
    
    int attempts = 0;
    while(attempts < 20) {
      time_t now = time(nullptr);
      struct tm timeinfo;
      localtime_r(&now, &timeinfo);
      
      if (timeinfo.tm_year > 120) { // Year > 2020
        timeSynced = true;
        // CRITICAL FIX: Calculate boot epoch correctly
        // bootEpoch = current time - time since boot
        unsigned long elapsedSeconds = (millis() - bootTime) / 1000;
        bootEpoch = now - elapsedSeconds;
        
        lastKnownTime = now;
        lastTimeCheck = millis();
        
        char buf[30];
        strftime(buf, sizeof(buf), "%Y-%m-%d %H:%M:%S", &timeinfo);
        Serial.println("Time synchronized successfully");
        Serial.println("Current time: " + String(buf));
        Serial.println("Boot epoch: " + String(bootEpoch));
        Serial.println("Elapsed seconds: " + String(elapsedSeconds));
        break;
      }
      delay(500);
      attempts++;
    }
    lastTimeSyncAttempt = millis();
    updateMainDisplay();
    
    // If we just got time sync, trigger immediate retry
    if (timeSynced && spiffsEntryCount > 0) {
      immediateRetryNeeded = true;
    }
  }
}

void syncTime() {
  if (WiFi.status() == WL_CONNECTED) {
    configTime(gmtOffset_sec, daylightOffset_sec, ntpServer);
    
    int attempts = 0;
    while(attempts < 10) {
      time_t now = time(nullptr);
      struct tm timeinfo;
      localtime_r(&now, &timeinfo);
      
      if (timeinfo.tm_year > 120) {
        timeSynced = true;
        // CRITICAL FIX: Recalculate boot epoch based on current time
        // This ensures all past timestamps are calculated correctly
        unsigned long elapsedSeconds = (millis() - bootTime) / 1000;
        bootEpoch = now - elapsedSeconds;
        
        lastKnownTime = now;
        lastTimeCheck = millis();
        
        char buf[30];
        strftime(buf, sizeof(buf), "%Y-%m-%d %H:%M:%S", &timeinfo);
        Serial.println("Time resynchronized at: " + String(buf));
        Serial.println("Updated boot epoch: " + String(bootEpoch));
        break;
      }
      delay(500);
      attempts++;
    }
    lastTimeSyncAttempt = millis();
    updateMainDisplay();
    
    // Trigger immediate retry after time sync
    if (spiffsEntryCount > 0) {
      immediateRetryNeeded = true;
    }
  }
}

String millisToISO(unsigned long scanMillis) {
  if (!timeSynced || bootEpoch == 0) {
    return "";
  }
  
  // CRITICAL FIX: Ensure we're going backwards in time for past events
  // scanMillis is when the scan happened (in millis() counter)
  // bootTime is when the device booted
  // The difference (scanMillis - bootTime) is how many ms after boot the scan occurred
  // This should ALWAYS be a positive number and represents time in the past
  
  if (scanMillis < bootTime) {
    // This shouldn't happen, but just in case
    scanMillis = bootTime;
  }
  
  unsigned long elapsedSeconds = (scanMillis - bootTime) / 1000;
  
  // The scan happened 'elapsedSeconds' after boot
  // So the actual time = bootEpoch + elapsedSeconds
  time_t scanTime = bootEpoch + elapsedSeconds;
  
  // Validate that we're not creating future timestamps
  time_t currentTime = bootEpoch + ((millis() - bootTime) / 1000);
  if (scanTime > currentTime) {
    // If calculated time is in the future, clamp to current time
    scanTime = currentTime;
    Serial.println("Warning: Scan time was in future, clamping to current");
  }
  
  struct tm timeinfo;
  localtime_r(&scanTime, &timeinfo);
  
  // Validate year
  if (timeinfo.tm_year < 100) { // Year less than 2000
    Serial.println("Warning: Invalid year in timestamp");
    return "";
  }
  
  char buf[25];
  snprintf(buf, sizeof(buf), "%04d-%02d-%02dT%02d:%02d:%02d",
           timeinfo.tm_year + 1900, timeinfo.tm_mon + 1, timeinfo.tm_mday,
           timeinfo.tm_hour, timeinfo.tm_min, timeinfo.tm_sec);
  return String(buf);
}

// ---------------------------- WiFi Functions ----------------------------

void checkWifiStatus() {
  bool currentStatus = (WiFi.status() == WL_CONNECTED);
  if (currentStatus != wifiConnected) {
    wifiConnected = currentStatus;
    if (wifiConnected) {
      Serial.println("WiFi connected!");
      lastWifiAttempt = millis();
      syncTime(); // This will set immediateRetryNeeded if there are entries
    } else {
      Serial.println("WiFi disconnected!");
    }
    updateWifiStatusOnDisplay();
  }
}

void connectToWiFi() {
  if (wifiConnected) return;
  
  Serial.print("Connecting to WiFi");
  
  lcd.fillRect(0, 70, 240, 20, ST77XX_BLACK);
  lcd.setCursor(10, 70);
  lcd.setTextColor(ST77XX_YELLOW);
  lcd.print("WiFi: Connecting...");

  WiFi.begin(WIFI_SSID, WIFI_PASS);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  lastWifiAttempt = millis();
  wifiConnected = WiFi.status() == WL_CONNECTED;

  Serial.println(wifiConnected ? "\nWiFi connected!" : "\nWiFi connection failed");
  
  if (wifiConnected) {
    syncTime(); // This will set immediateRetryNeeded if there are entries
  }
  
  updateMainDisplay();
}
