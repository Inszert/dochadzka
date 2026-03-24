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
#define WORK_LOCATION "Bufet"

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
bool immediateRetryNeeded = false;

// Last entry tracking
String lastEntryName = "---";
String lastEntryNameLine1 = "---";
String lastEntryNameLine2 = "";
String lastEntryTime = "--:--:--";
String lastEntryISOTime = "";

// Time tracking
bool timeSynced = false;
unsigned long lastTimeSyncAttempt = 0;
const unsigned long TIME_SYNC_INTERVAL = 3600000;

// Offline time tracking
unsigned long bootMinutes = 0;  // Minutes since boot (for display)
unsigned long totalOfflineMinutes = 0;  // Total offline minutes across resets
unsigned long lastMinuteTick = 0;
unsigned long lastSavedMinute = 0;
bool minuteIncremented = false;

// Base reference for offline time
time_t offlineBaseTime = 0;  // Will be set when we first get time sync
bool offlineBaseSet = false;

// Display update
unsigned long lastDisplayUpdate = 0;
const unsigned long DISPLAY_UPDATE_INTERVAL = 1000; // Update time every second

// Time
const char* ntpServer = "pool.ntp.org";
const long gmtOffset_sec = 3600; // GMT+1 (CET)
const int daylightOffset_sec = 0; // +1 hour for daylight saving (CEST)

Adafruit_ST7789 lcd = Adafruit_ST7789(LCD_CS, LCD_DC, LCD_RST);
MFRC522 rfid(SS_PIN, RST_PIN);
MFRC522::MIFARE_Key key;

void setup() {
  Serial.begin(9600);

  // SPIFFS init
  if(!SPIFFS.begin(true)) {
    Serial.println("SPIFFS Mount Failed");
  }
  
  // Load total offline minutes
  loadOfflineMinutes();
  
  // Record boot time for minute calculation
  bootMinutes = 0;
  lastMinuteTick = millis();
  
  // Clean up invalid entries on startup
  cleanupSpiffs();
  updateSpiffsEntryCount();

  SPI.begin(LCD_SCLK, MISO_PIN, LCD_MOSI, LCD_CS);
  lcd.init(135, 240);
  lcd.setRotation(2);
  lcd.fillScreen(ST77XX_BLACK);
  lcd.setTextWrap(true);
  lcd.setTextSize(2);

  rfid.PCD_Init();
  for (byte i = 0; i < 6; i++) key.keyByte[i] = 0xFF;

  connectToWiFi();
  initTime();

  updateMainDisplay();
}

void loop() {
  // Update minute counter every 60 seconds
  if (millis() - lastMinuteTick >= 60000) {
    bootMinutes++;
    totalOfflineMinutes++;
    lastMinuteTick = millis();
    minuteIncremented = true;
    
    // Save total offline minutes every 5 minutes or when changed
    if (bootMinutes % 5 == 0 || minuteIncremented) {
      saveOfflineMinutes();
      minuteIncremented = false;
    }
    
    Serial.println("Boot minutes: " + String(bootMinutes) + ", Total offline: " + String(totalOfflineMinutes));
  }
  
  // Update WiFi status
  checkWifiStatus();
  
  // Retry WiFi connection if needed
  if (!wifiConnected && millis() - lastWifiAttempt >= WIFI_RETRY_INTERVAL) {
    connectToWiFi();
  }
  
  // Periodically try to sync time
  if (wifiConnected && !timeSynced && millis() - lastTimeSyncAttempt >= TIME_SYNC_INTERVAL) {
    syncTime();
  }
  
  // Update time on display every second
  if (millis() - lastDisplayUpdate >= DISPLAY_UPDATE_INTERVAL) {
    updateTimeOnDisplay();
    lastDisplayUpdate = millis();
  }

  // Retry failed SPIFFS sends
  if (wifiConnected && timeSynced && spiffsEntryCount > 0 && !isRetrying) {
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

  delay(50);
}

// ---------------------------- Offline Minutes Persistence ----------------------------

void saveOfflineMinutes() {
  File file = SPIFFS.open("/minutes.txt", FILE_WRITE);
  if (file) {
    file.println(String(totalOfflineMinutes));
    file.close();
    Serial.println("Saved total offline minutes: " + String(totalOfflineMinutes));
  }
}

void loadOfflineMinutes() {
  if (!SPIFFS.exists("/minutes.txt")) {
    totalOfflineMinutes = 0;
    return;
  }
  
  File file = SPIFFS.open("/minutes.txt", FILE_READ);
  if (file) {
    String minutesStr = file.readStringUntil('\n');
    minutesStr.trim();
    totalOfflineMinutes = minutesStr.toInt();
    file.close();
    Serial.println("Loaded total offline minutes: " + String(totalOfflineMinutes));
  }
}

// ---------------------------- Time Conversion ----------------------------

void setOfflineBaseTime() {
  if (timeSynced && !offlineBaseSet) {
    // When we first get time sync, record the base time
    time_t now = time(nullptr);
    // Calculate what time it was when offline minutes started (0 minutes)
    offlineBaseTime = now - (totalOfflineMinutes * 60);
    offlineBaseSet = true;
    Serial.println("Set offline base time to: " + String(offlineBaseTime));
    
    // Format for display
    struct tm timeinfo;
    localtime_r(&offlineBaseTime, &timeinfo);
    char buf[30];
    strftime(buf, sizeof(buf), "%Y-%m-%d %H:%M:%S", &timeinfo);
    Serial.println("This means offline start was: " + String(buf));
  }
}

String offlineMinutesToISO(unsigned long offlineMinutes) {
  if (!timeSynced || !offlineBaseSet) {
    return "";
  }
  
  // Calculate actual time: base time + (offlineMinutes * 60 seconds)
  time_t scanTime = offlineBaseTime + (offlineMinutes * 60);
  
  struct tm timeinfo;
  localtime_r(&scanTime, &timeinfo);
  
  char buf[25];
  snprintf(buf, sizeof(buf), "%04d-%02d-%02dT%02d:%02d:%02d",
           timeinfo.tm_year + 1900, timeinfo.tm_mon + 1, timeinfo.tm_mday,
           timeinfo.tm_hour, timeinfo.tm_min, timeinfo.tm_sec);
  return String(buf);
}

// ---------------------------- Display Functions ----------------------------

void updateMainDisplay() {
  lcd.fillScreen(ST77XX_BLACK);
  lcd.setTextSize(2);
  
  // Line 0: Time at the top
  updateTimeOnDisplay();
  
  // Line 1: "Scan card" text
  lcd.setCursor(10, 30);
  lcd.setTextColor(ST77XX_WHITE);
  lcd.println("Scan card");
  
  // Line 2: WiFi status
  updateWifiStatusOnDisplay();
  
  // Line 3: "Saved:" text
  lcd.setCursor(10, 90);
  lcd.setTextColor(ST77XX_WHITE);
  lcd.print("Saved:");
  
  // Line 4: SPIFFS entry count
  updateSpiffsCountOnDisplay();
  
  // Line 5: "Last:" text
  lcd.setCursor(10, 140);
  lcd.setTextColor(ST77XX_WHITE);
  lcd.print("Last:");
  
  // Line 6: Last entry name - first line
  lcd.setCursor(10, 160);
  lcd.setTextColor(ST77XX_CYAN);
  lcd.print(lastEntryNameLine1);
  
  // Line 7: Last entry name - second line
  lcd.setCursor(10, 180);
  lcd.setTextColor(ST77XX_CYAN);
  lcd.print(lastEntryNameLine2);
  
  // Line 8: Last entry time
  lcd.setCursor(10, 210);
  lcd.setTextColor(ST77XX_CYAN);
  lcd.print(lastEntryTime);
}

void updateTimeOnDisplay() {
  lcd.fillRect(0, 0, 240, 20, ST77XX_BLACK);
  lcd.setCursor(10, 0);
  
  if (timeSynced) {
    lcd.setTextColor(ST77XX_GREEN);
    time_t now = time(nullptr);
    struct tm timeinfo;
    localtime_r(&now, &timeinfo);
    char buf[30];
    strftime(buf, sizeof(buf), "%H:%M:%S", &timeinfo);
    lcd.print(buf);
  } else {
    lcd.setTextColor(ST77XX_YELLOW);
    // Show total minutes since boot in HH:MM format
    unsigned long hours = bootMinutes / 60;
    unsigned long minutes = bootMinutes % 60;
    
    lcd.print("OFF ");
    if (hours < 10) lcd.print("0");
    lcd.print(hours);
    lcd.print(":");
    if (minutes < 10) lcd.print("0");
    lcd.print(minutes);
  }
}

void updateWifiStatusOnDisplay() {
  lcd.setCursor(10, 60);
  
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
  lcd.fillRect(10, 110, 220, 20, ST77XX_BLACK);
  lcd.setCursor(10, 110);
  lcd.setTextColor(ST77XX_WHITE);
  lcd.print(spiffsEntryCount);
}

void updateLastEntryOnDisplay() {
  lcd.fillRect(10, 160, 220, 50, ST77XX_BLACK);
  
  lcd.setCursor(10, 160);
  lcd.setTextColor(ST77XX_CYAN);
  lcd.print(lastEntryNameLine1);
  
  lcd.setCursor(10, 180);
  lcd.setTextColor(ST77XX_CYAN);
  lcd.print(lastEntryNameLine2);
  
  lcd.setCursor(10, 210);
  lcd.setTextColor(ST77XX_CYAN);
  lcd.print(lastEntryTime);
}

void splitNameIntoLines(String fullName) {
  lastEntryNameLine1 = "";
  lastEntryNameLine2 = "";
  
  if (fullName.length() == 0 || fullName == "---") {
    lastEntryNameLine1 = "---";
    return;
  }
  
  int spaceIndex = fullName.indexOf(' ');
  if (spaceIndex > 0 && spaceIndex < 12) {
    lastEntryNameLine1 = fullName.substring(0, spaceIndex);
    lastEntryNameLine2 = fullName.substring(spaceIndex + 1);
    
    if (lastEntryNameLine1.length() > 12) {
      lastEntryNameLine1 = lastEntryNameLine1.substring(0, 10) + "..";
    }
    if (lastEntryNameLine2.length() > 12) {
      lastEntryNameLine2 = lastEntryNameLine2.substring(0, 10) + "..";
    }
  } else {
    if (fullName.length() <= 12) {
      lastEntryNameLine1 = fullName;
    } else if (fullName.length() <= 24) {
      lastEntryNameLine1 = fullName.substring(0, 12);
      lastEntryNameLine2 = fullName.substring(12);
    } else {
      lastEntryNameLine1 = fullName.substring(0, 10) + "..";
      lastEntryNameLine2 = fullName.substring(12, 22) + "..";
    }
  }
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
    int third = line.indexOf('|', second + 1);
    int fourth = line.indexOf('|', third + 1);
    
    if (first == -1 || second == -1 || third == -1 || fourth == -1) {
      removedCount++;
      continue;
    }
    
    String name = line.substring(0, first);
    String location = line.substring(first + 1, second);
    String type = line.substring(second + 1, third);  // "OFFLINE" or "ONLINE"
    String minutes = line.substring(third + 1, fourth); // minutes for OFFLINE, or timestamp for ONLINE
    String displayTime = line.substring(fourth + 1);
    
    if (name.length() == 0 || name == " " || location.length() == 0) {
      removedCount++;
      continue;
    }
    
    validLines.push_back(line);
  }
  file.close();
  
  if (removedCount > 0) {
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
  String uidStr = "";
  for (byte i = 0; i < rfid.uid.size; i++) {
    if (rfid.uid.uidByte[i] < 0x10) uidStr += "0";
    uidStr += String(rfid.uid.uidByte[i], HEX);
  }
  uidStr.toUpperCase();

  Serial.println("Card UID: " + uidStr);

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
  if (employeeName.length() == 0 || employeeName == " ") {
    Serial.println("Error: Attempted to send request with empty employee name");
    showResultAndReturn("Invalid Name", ST77XX_RED, 3000);
    return;
  }
  
  if (!wifiConnected) {
    // No WiFi - save with offline minutes
    String offlineMinutes_str = String(totalOfflineMinutes);
    String displayTime = "OFF:" + String(bootMinutes) + "m";
    
    Serial.println("No WiFi - saving request with offline minutes: " + offlineMinutes_str);
    // Format: name|location|OFFLINE|minutes|displayTime
    saveFailedRequest(employeeName, WORK_LOCATION, "OFFLINE", offlineMinutes_str, displayTime);
    
    lastEntryName = employeeName;
    splitNameIntoLines(employeeName);
    lastEntryTime = displayTime;
    updateLastEntryOnDisplay();
    
    showResultAndReturn("Saved to SPIFFS", ST77XX_ORANGE, 3000);
    return;
  }

  // We have WiFi, try to send immediately
  if (!timeSynced) {
    // WiFi but no time sync - save with offline minutes
    String offlineMinutes_str = String(totalOfflineMinutes);
    String displayTime = "OFF:" + String(bootMinutes) + "m";
    
    Serial.println("WiFi but no time - saving request with offline minutes: " + offlineMinutes_str);
    saveFailedRequest(employeeName, WORK_LOCATION, "OFFLINE", offlineMinutes_str, displayTime);
    
    lastEntryName = employeeName;
    splitNameIntoLines(employeeName);
    lastEntryTime = displayTime;
    updateLastEntryOnDisplay();
    
    showResultAndReturn("No Time Sync", ST77XX_ORANGE, 3000);
    return;
  }

  // We have both WiFi and time sync
  time_t now = time(nullptr);
  struct tm timeinfo;
  localtime_r(&now, &timeinfo);
  
  char buf[25];
  snprintf(buf, sizeof(buf), "%04d-%02d-%02dT%02d:%02d:%02d",
           timeinfo.tm_year + 1900, timeinfo.tm_mon + 1, timeinfo.tm_mday,
           timeinfo.tm_hour, timeinfo.tm_min, timeinfo.tm_sec);
  String timestamp = String(buf);
  String isoTime = timestamp.substring(11, 19);

  HTTPClient http;
  http.begin(API_URL);
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(10000);

  String payload = "{ \"employee_name\": \"" + employeeName + "\", \"work_location\": \"" + String(WORK_LOCATION) + "\" }";

  int httpResponseCode = http.POST(payload);
  String response = httpResponseCode > 0 ? http.getString() : "";

  Serial.println("Sent: " + payload);
  Serial.println("Response code: " + String(httpResponseCode));

  // Extract time from response if available
  String responseTime = extractTimeFromResponse(response);
  
  lastEntryName = employeeName;
  splitNameIntoLines(employeeName);
  
  if (responseTime.length() > 0) {
    lastEntryTime = responseTime;
  } else {
    lastEntryTime = isoTime;
  }
  updateLastEntryOnDisplay();

  if (httpResponseCode > 0 && response.indexOf("\"success\":true") != -1) {
    showResultAndReturn("Success!", ST77XX_GREEN, 3000);
  } else {
    // Save for retry with the actual timestamp
    saveFailedRequest(employeeName, WORK_LOCATION, "ONLINE", timestamp, isoTime);
    showResultAndReturn("Saved for retry", ST77XX_ORANGE, 3000);
  }

  http.end();
}

String extractTimeFromResponse(String response) {
  int startIdx = response.indexOf("\"start_time\":\"");
  if (startIdx > 0) {
    startIdx += 13;
    int endIdx = response.indexOf("\"", startIdx);
    if (endIdx > startIdx) {
      return response.substring(startIdx, endIdx);
    }
  }
  
  startIdx = response.indexOf("\"end_time\":\"");
  if (startIdx > 0) {
    startIdx += 11;
    int endIdx = response.indexOf("\"", startIdx);
    if (endIdx > startIdx) {
      return response.substring(startIdx, endIdx);
    }
  }
  
  return "";
}

void retryFailedRequests() {
  if (!wifiConnected || !timeSynced || spiffsEntryCount == 0 || isRetrying) {
    return;
  }
  
  // Set offline base time if not set yet
  setOfflineBaseTime();
  
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

  file = SPIFFS.open("/failed.txt", FILE_READ);
  
  while (file.available()) {
    String line = file.readStringUntil('\n');
    line.trim();
    if (line.length() == 0) continue;

    int first = line.indexOf('|');
    int second = line.indexOf('|', first + 1);
    int third = line.indexOf('|', second + 1);
    int fourth = line.indexOf('|', third + 1);
    
    if(first == -1 || second == -1 || third == -1 || fourth == -1) {
      invalidCount++;
      continue;
    }

    String name = line.substring(0, first);
    String location = line.substring(first + 1, second);
    String type = line.substring(second + 1, third);
    String value = line.substring(third + 1, fourth);  // minutes for OFFLINE, timestamp for ONLINE
    String displayTime = line.substring(fourth + 1);

    if (name.length() == 0 || name == " ") {
      invalidCount++;
      continue;
    }

    String finalTimestamp;
    
    if (type == "OFFLINE") {
      // Convert offline minutes to actual timestamp
      unsigned long offlineMinutes = value.toInt();
      finalTimestamp = offlineMinutesToISO(offlineMinutes);
      
      if (finalTimestamp.length() == 0) {
        // Can't convert yet, keep for later
        remainingLines.push_back(line);
        continue;
      }
      
      // Update display time
      displayTime = finalTimestamp.substring(11, 19);
    } else {
      // ONLINE entry - use the stored timestamp
      finalTimestamp = value;
    }

    HTTPClient http;
    http.begin(API_RETRY_URL);
    http.addHeader("Content-Type", "application/json");
    http.setTimeout(10000);

    String payload = "{ \"employee_name\": \"" + name + "\", \"work_location\": \"" + location + "\", \"timestamp\": \"" + finalTimestamp + "\" }";

    blinkScreen(ST77XX_BLUE, 200);
    
    int code = http.POST(payload);
    String resp = code > 0 ? http.getString() : "";

    Serial.println("Sending retry: " + payload);
    Serial.println("Response code: " + String(code));

    if (code > 0 && resp.indexOf("\"success\":true") != -1) {
      sentCount++;
      anySent = true;
      Serial.println("Successfully sent: " + name);
      
      lastEntryName = name;
      splitNameIntoLines(name);
      lastEntryTime = displayTime;
      updateLastEntryOnDisplay();
    } else {
      // Keep the original line
      remainingLines.push_back(line);
      Serial.println("Failed to send, keeping for later");
    }

    http.end();
    delay(200);
  }
  file.close();

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
  Serial.println("Retry attempt completed. Sent: " + String(sentCount));
}

void saveFailedRequest(String name, String location, String type, String value, String displayTime) {
  if (name.length() == 0 || name == " ") {
    Serial.println("Error: Attempted to save empty employee name to SPIFFS");
    return;
  }
  
  File file = SPIFFS.open("/failed.txt", FILE_APPEND);
  if(file) {
    // Format: name|location|type|value|displayTime
    // type: "OFFLINE" or "ONLINE"
    // value: minutes for OFFLINE, timestamp string for ONLINE
    file.println(name + "|" + location + "|" + type + "|" + value + "|" + displayTime);
    file.close();
    Serial.println("Saved failed request: " + name + " type: " + type + " value: " + value);
    spiffsContentChanged = true;
  }
}

// ---------------------------- Time Functions ----------------------------

void initTime() {
  if (WiFi.status() == WL_CONNECTED) {
    configTime(gmtOffset_sec, daylightOffset_sec, ntpServer);
    Serial.println("Fetching time from NTP...");
    
    int attempts = 0;
    while(attempts < 20) {
      time_t now = time(nullptr);
      struct tm timeinfo;
      localtime_r(&now, &timeinfo);
      
      if (timeinfo.tm_year > 120) {
        timeSynced = true;
        setOfflineBaseTime();
        
        char buf[30];
        strftime(buf, sizeof(buf), "%Y-%m-%d %H:%M:%S", &timeinfo);
        Serial.println("Time synchronized successfully");
        Serial.println("Current time: " + String(buf));
        break;
      }
      delay(500);
      attempts++;
    }
    lastTimeSyncAttempt = millis();
    updateMainDisplay();
    
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
        setOfflineBaseTime();
        
        char buf[30];
        strftime(buf, sizeof(buf), "%Y-%m-%d %H:%M:%S", &timeinfo);
        Serial.println("Time resynchronized at: " + String(buf));
        break;
      }
      delay(500);
      attempts++;
    }
    lastTimeSyncAttempt = millis();
    updateMainDisplay();
    
    if (spiffsEntryCount > 0) {
      immediateRetryNeeded = true;
    }
  }
}

// ---------------------------- WiFi Functions ----------------------------

void checkWifiStatus() {
  bool currentStatus = (WiFi.status() == WL_CONNECTED);
  if (currentStatus != wifiConnected) {
    wifiConnected = currentStatus;
    if (wifiConnected) {
      Serial.println("WiFi connected!");
      lastWifiAttempt = millis();
      syncTime();
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
    syncTime();
  }
  
  updateMainDisplay();
}
