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

// SPIFFS print timing
unsigned long lastSpiffsPrint = 0;
const unsigned long SPIFFS_PRINT_INTERVAL = 300000; // 5 minutes
bool spiffsContentChanged = false;

// Time tracking for backtracking
unsigned long bootTime = 0;        // Time when device booted (millis)
time_t bootEpoch = 0;              // Actual epoch time when we last had WiFi
bool timeSynced = false;           // Whether we have accurate time from NTP
unsigned long lastTimeSyncAttempt = 0;
const unsigned long TIME_SYNC_INTERVAL = 3600000; // Try to sync time every hour

// Structure to store failed requests with millis timestamp
struct FailedRequest {
  String name;
  String location;
  unsigned long scanMillis;  // millis() when scan occurred
};

// WiFi icon positions
const int WIFI_X = 200;
const int WIFI_Y = 5;
const int WIFI_SIZE = 8;

// Time
const char* ntpServer = "pool.ntp.org";
const long gmtOffset_sec = 3600; // GMT+1
const int daylightOffset_sec = 0;

Adafruit_ST7789 lcd = Adafruit_ST7789(LCD_CS, LCD_DC, LCD_RST);
MFRC522 rfid(SS_PIN, RST_PIN);
MFRC522::MIFARE_Key key;

void setup() {
  Serial.begin(9600);

  // SPIFFS init
  if(!SPIFFS.begin(true)) {
    Serial.println("SPIFFS Mount Failed");
  }

  SPI.begin(LCD_SCLK, MISO_PIN, LCD_MOSI, LCD_CS);
  lcd.init(135, 240);
  lcd.fillScreen(ST77XX_BLACK);
  lcd.setTextWrap(true);
  lcd.setTextSize(2);
  lcd.setTextColor(ST77XX_WHITE);

  rfid.PCD_Init();
  for (byte i = 0; i < 6; i++) key.keyByte[i] = 0xFF;

  bootTime = millis();  // Record boot time
  
  connectToWiFi();
  initTime();

  lcd.setCursor(10, 20);
  if (WRITE_MODE) {
    lcd.println("WRITE MODE");
    lcd.setCursor(10, 40);
    lcd.println("Scan RFID card...");
    Serial.println("WRITE MODE - Scan RFID card...");
  } else {
    lcd.println("READ MODE");
    lcd.setCursor(10, 40);
    lcd.println("Scan RFID card...");
    Serial.println("READ MODE - Scan RFID card...");
  }
}

void loop() {
  // Retry WiFi connection
  if (!wifiConnected && millis() - lastWifiAttempt >= WIFI_RETRY_INTERVAL) {
    connectToWiFi();
  }
  
  // Periodically try to sync time even if WiFi is connected
  if (wifiConnected && !timeSynced && millis() - lastTimeSyncAttempt >= TIME_SYNC_INTERVAL) {
    syncTime();
  }
  
  updateWifiStatus();

  // Retry failed SPIFFS sends
  if(wifiConnected && timeSynced) {
    retryFailedRequests();
  }

  // Print SPIFFS content every 5 minutes or when changed
  if (millis() - lastSpiffsPrint >= SPIFFS_PRINT_INTERVAL || spiffsContentChanged) {
    printSpiffsContent();
    lastSpiffsPrint = millis();
    spiffsContentChanged = false;
  }

  if (!rfid.PICC_IsNewCardPresent() || !rfid.PICC_ReadCardSerial()) return;

  // Build UID string
  String uidStr = "";
  for (byte i = 0; i < rfid.uid.size; i++) {
    if (rfid.uid.uidByte[i] < 0x10) uidStr += "0";
    uidStr += String(rfid.uid.uidByte[i], HEX);
  }
  uidStr.toUpperCase();

  lcd.fillScreen(ST77XX_BLACK);
  lcd.setCursor(10, 20);
  lcd.setTextColor(ST77XX_GREEN);
  lcd.println("Card UID:");
  lcd.println(uidStr);
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

  lcd.fillScreen(ST77XX_BLACK);
  lcd.setCursor(10, 20);
  lcd.setTextColor(ST77XX_WHITE);
  lcd.println(WRITE_MODE ? "WRITE MODE" : "READ MODE");
  lcd.setCursor(10, 40);
  lcd.println("Scan next card...");
  Serial.println("Scan next card...");

  delay(2000);
}

// ---------------------------- Card Functions ----------------------------

void writeToCard(byte safeBlocks[], const char* messages[]) {
  for (byte i = 0; i < 3; i++) {
    byte block = safeBlocks[i];
    MFRC522::StatusCode status = rfid.PCD_Authenticate(
      MFRC522::PICC_CMD_MF_AUTH_KEY_A, block, &key, &(rfid.uid));
    if (status != MFRC522::STATUS_OK) continue;

    byte buffer[16] = {0};
    const char* msg = messages[i];
    for (byte j = 0; j < strlen(msg) && j < 16; j++) buffer[j] = msg[j];

    rfid.MIFARE_Write(block, buffer, 16);
  }

  lcd.setCursor(10, 180);
  lcd.setTextColor(ST77XX_WHITE);
  lcd.println("Write complete!");
  delay(3000);
}

void readFromCard(byte safeBlocks[], String uidStr) {
  String employeeName = "";

  for (byte i = 0; i < 3; i++) {
    byte block = safeBlocks[i];
    MFRC522::StatusCode status = rfid.PCD_Authenticate(
      MFRC522::PICC_CMD_MF_AUTH_KEY_A, block, &key, &(rfid.uid));
    if (status != MFRC522::STATUS_OK) continue;

    byte buffer[18];
    byte size = sizeof(buffer);
    status = rfid.MIFARE_Read(block, buffer, &size);
    if (status != MFRC522::STATUS_OK) continue;

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
  Serial.println("Employee name: " + employeeName);

  sendShiftRequest(employeeName);
}

// ---------------------------- HTTP + SPIFFS ----------------------------

void sendShiftRequest(String employeeName) {
  unsigned long scanTime = millis();  // Record when the scan happened
  
  if (!wifiConnected || !timeSynced) {
    Serial.println("Cannot send immediately - saving request for later");
    saveFailedRequest(employeeName, WORK_LOCATION, scanTime);
    return;
  }

  // We have WiFi and time sync, try to send immediately
  String timestamp = millisToISO(scanTime);
  
  HTTPClient http;
  http.begin(API_URL);
  http.addHeader("Content-Type", "application/json");

  String payload = "{ \"employee_name\": \"" + employeeName + "\", \"work_location\": \"" + String(WORK_LOCATION) + "\" }";

  int httpResponseCode = http.POST(payload);
  String response = httpResponseCode > 0 ? http.getString() : "";

  Serial.println("Sent: " + payload);
  Serial.println("Response: " + response);

  if (httpResponseCode <= 0 || response.indexOf("\"success\":true") == -1) {
    // If immediate send fails, save for retry
    saveFailedRequest(employeeName, WORK_LOCATION, scanTime);
  }

  http.end();
}

// Retry unsent requests from SPIFFS on WiFi reconnect
void retryFailedRequests() {
  if (!SPIFFS.exists("/failed.txt") || !timeSynced) return;

  File file = SPIFFS.open("/failed.txt", FILE_READ);
  if (!file) return;

  std::vector<String> remainingLines;
  bool anySent = false;

  while (file.available()) {
    String line = file.readStringUntil('\n');
    line.trim();
    if (line.length() == 0) continue;

    int first = line.indexOf('|');
    int second = line.indexOf('|', first + 1);
    if(first == -1 || second == -1) continue;

    String name = line.substring(0, first);
    String location = line.substring(first + 1, second);
    unsigned long scanMillis = line.substring(second + 1).toInt();

    // Convert the stored millis to proper ISO timestamp using current bootEpoch
    String timestamp = millisToISO(scanMillis);

    HTTPClient http;
    http.begin(API_RETRY_URL);
    http.addHeader("Content-Type", "application/json");

    String payload = "{ \"employee_name\": \"" + name + "\", \"work_location\": \"" + location + "\", \"timestamp\": \"" + timestamp + "\" }";

    int code = http.POST(payload);
    String resp = code > 0 ? http.getString() : "";

    Serial.println("Sending retry with backtracked time: " + payload);
    Serial.println("Response: " + resp);

    if (code <= 0 || resp.indexOf("\"success\":true") == -1) {
      remainingLines.push_back(line); // keep for later if failed
    } else {
      Serial.println("Successfully sent: " + name + " with timestamp: " + timestamp);
      anySent = true;
    }

    http.end();
    delay(100); // Small delay between requests
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

  // Mark SPIFFS as changed if we successfully sent any requests
  if (anySent) {
    spiffsContentChanged = true;
  }
}

// Save failed requests to SPIFFS (store millis timestamp)
void saveFailedRequest(String name, String location, unsigned long scanMillis) {
  File file = SPIFFS.open("/failed.txt", FILE_APPEND);
  if(file) {
    file.println(name + "|" + location + "|" + String(scanMillis));
    file.close();
    Serial.println("Saved failed request: " + name + " at millis: " + String(scanMillis));
    spiffsContentChanged = true;
  }
}

// Print SPIFFS content
void printSpiffsContent() {
  Serial.println("\n---- SPIFFS saved requests (5 min report) ----");
  
  if (!SPIFFS.exists("/failed.txt")) {
    Serial.println("No failed requests stored");
    Serial.println("--------------------------------------------\n");
    return;
  }

  File file = SPIFFS.open("/failed.txt", FILE_READ);
  if (!file) {
    Serial.println("Error opening file");
    Serial.println("--------------------------------------------\n");
    return;
  }

  int count = 0;
  while (file.available()) {
    String line = file.readStringUntil('\n');
    line.trim();
    if (line.length() > 0) {
      Serial.println(line);
      count++;
    }
  }
  
  file.close();
  
  Serial.println("Total records: " + String(count));
  Serial.println("--------------------------------------------\n");
}

// ---------------------------- Time with Backtracking ----------------------------

void initTime() {
  if (WiFi.status() == WL_CONNECTED) {
    configTime(gmtOffset_sec, daylightOffset_sec, ntpServer);
    Serial.println("Fetching time from NTP...");
    int attempts = 0;
    while(attempts < 10 && !timeSynced) {
      time_t now = time(nullptr);
      if (now > 100000) { // Valid time (after year 1973)
        timeSynced = true;
        // Calculate boot epoch: current time minus elapsed seconds since boot
        bootEpoch = now - ((millis() - bootTime) / 1000);
        Serial.println("Time synchronized successfully");
        Serial.println("Current time: " + String(now));
        Serial.println("Boot epoch: " + String(bootEpoch));
        Serial.println("Elapsed seconds: " + String((millis() - bootTime) / 1000));
        break;
      }
      delay(500);
      attempts++;
    }
    lastTimeSyncAttempt = millis();
  }
}

void syncTime() {
  if (WiFi.status() == WL_CONNECTED) {
    configTime(gmtOffset_sec, daylightOffset_sec, ntpServer);
    int attempts = 0;
    while(attempts < 5 && !timeSynced) {
      time_t now = time(nullptr);
      if (now > 100000) {
        timeSynced = true;
        // Recalculate boot epoch based on current time
        bootEpoch = now - ((millis() - bootTime) / 1000);
        Serial.println("Time resynchronized at: " + String(now));
        Serial.println("Updated boot epoch: " + String(bootEpoch));
        break;
      }
      delay(500);
      attempts++;
    }
    lastTimeSyncAttempt = millis();
  }
}

String millisToISO(unsigned long scanMillis) {
  if (!timeSynced || bootEpoch == 0) {
    return "";  // Return empty if we can't calculate proper time
  }
  
  // Calculate the actual time when the scan occurred
  // scanMillis is the millis() value at scan time
  // elapsedSeconds is how many seconds after boot the scan happened
  unsigned long elapsedSeconds = (scanMillis - bootTime) / 1000;
  time_t scanTime = bootEpoch + elapsedSeconds;
  
  struct tm timeinfo;
  localtime_r(&scanTime, &timeinfo);
  
  char buf[25];
  snprintf(buf, sizeof(buf), "%04d-%02d-%02dT%02d:%02d:%02d",
           timeinfo.tm_year + 1900, timeinfo.tm_mon + 1, timeinfo.tm_mday,
           timeinfo.tm_hour, timeinfo.tm_min, timeinfo.tm_sec);
  return String(buf);
}

// ---------------------------- WiFi ----------------------------

void connectToWiFi() {
  Serial.print("Connecting to WiFi");
  lcd.setCursor(10, 60);
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

  lcd.setCursor(10, 60);
  lcd.setTextColor(wifiConnected ? ST77XX_GREEN : ST77XX_RED);
  lcd.print(wifiConnected ? "WiFi: Connected!   " : "WiFi: Failed!     ");

  Serial.println(wifiConnected ? "\nWiFi connected!" : "\nWiFi connection failed");
  
  // If we just connected to WiFi, try to sync time
  if (wifiConnected) {
    syncTime();
  }
  
  delay(2000);
}

void updateWifiStatus() {
  bool currentStatus = (WiFi.status() == WL_CONNECTED);
  if (currentStatus != wifiConnected) {
    wifiConnected = currentStatus;
    if (wifiConnected) {
      lastWifiAttempt = millis();
      // Try to sync time when WiFi connects
      syncTime();
    }
  }

  lcd.fillRect(WIFI_X, WIFI_Y, WIFI_SIZE + 4, WIFI_SIZE + 4, ST77XX_BLACK);

  if (wifiConnected) {
    lcd.fillRect(WIFI_X, WIFI_Y + 6, 2, 2, ST77XX_GREEN);
    lcd.fillRect(WIFI_X - 1, WIFI_Y + 4, 4, 2, ST77XX_GREEN);
    lcd.fillRect(WIFI_X - 2, WIFI_Y + 2, 6, 2, ST77XX_GREEN);
    lcd.fillRect(WIFI_X - 3, WIFI_Y, 8, 2, ST77XX_GREEN);
    
    // Add a small indicator if time is synced
    if (timeSynced) {
      lcd.fillCircle(WIFI_X + WIFI_SIZE + 4, WIFI_Y + 4, 2, ST77XX_GREEN);
    }
  } else {
    lcd.drawLine(WIFI_X, WIFI_Y, WIFI_X + WIFI_SIZE, WIFI_Y + WIFI_SIZE, ST77XX_RED);
    lcd.drawLine(WIFI_X + WIFI_SIZE, WIFI_Y, WIFI_X, WIFI_Y + WIFI_SIZE, ST77XX_RED);
  }
}
