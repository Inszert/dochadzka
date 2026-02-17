#include <SPI.h>
#include <MFRC522.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ST7789.h>
#include <WiFi.h>
#include <HTTPClient.h>

// Configuration
#define WRITE_MODE false  // true = Write to cards, false = Read from cards
#define WIFI_SSID "Asda"
#define WIFI_PASS "12345678"

// API endpoint
#define API_URL "https://fuzzy-trina-prenako-sro-b1bc9170.koyeb.app/api/shift_by_name"
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

Adafruit_ST7789 lcd = Adafruit_ST7789(LCD_CS, LCD_DC, LCD_RST);
MFRC522 rfid(SS_PIN, RST_PIN);
MFRC522::MIFARE_Key key;

// WiFi variables
bool wifiConnected = false;
unsigned long lastWifiAttempt = 0;
const unsigned long WIFI_RETRY_INTERVAL = 300000; // 5 minutes

// WiFi icon positions
const int WIFI_X = 200;
const int WIFI_Y = 5;
const int WIFI_SIZE = 8;

void setup() {
  Serial.begin(9600);

  SPI.begin(LCD_SCLK, MISO_PIN, LCD_MOSI, LCD_CS);

  lcd.init(135, 240);
  lcd.fillScreen(ST77XX_BLACK);
  lcd.setTextWrap(true);
  lcd.setTextSize(2);
  lcd.setTextColor(ST77XX_WHITE);

  rfid.PCD_Init();
  for (byte i = 0; i < 6; i++) key.keyByte[i] = 0xFF;

  connectToWiFi();

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
  if (!wifiConnected && millis() - lastWifiAttempt >= WIFI_RETRY_INTERVAL) {
    connectToWiFi();
  }

  updateWifiStatus();

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
  const char* messages[] = {"HELLO", "WORLD", "ESP32"};

  if (WRITE_MODE) {
    writeToCard(safeBlocks, messages);
  } else {
    readFromCard(safeBlocks, uidStr);
  }

  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();

  lcd.fillScreen(ST77XX_BLACK);
  lcd.setCursor(10, 20);
  lcd.setTextColor(ST77XX_WHITE);
  if (WRITE_MODE) lcd.println("WRITE MODE");
  else lcd.println("READ MODE");

  lcd.setCursor(10, 40);
  lcd.println("Scan next card...");
  Serial.println("Scan next card...");
  
  delay(2000);
}

void writeToCard(byte safeBlocks[], const char* messages[]) {
  for (byte i = 0; i < 3; i++) {
    byte block = safeBlocks[i];
    MFRC522::StatusCode status = rfid.PCD_Authenticate(
      MFRC522::PICC_CMD_MF_AUTH_KEY_A, block, &key, &(rfid.uid));

    if (status != MFRC522::STATUS_OK) {
      Serial.print("Auth failed for block "); Serial.println(block);
      lcd.setCursor(10, 140);
      lcd.setTextColor(ST77XX_RED);
      lcd.print("Auth failed block "); lcd.println(block);
      continue;
    }

    byte buffer[16] = {0};
    const char* msg = messages[i];
    for (byte j = 0; j < strlen(msg) && j < 16; j++) buffer[j] = msg[j];

    status = rfid.MIFARE_Write(block, buffer, 16);
    if (status != MFRC522::STATUS_OK) {
      Serial.print("Write failed for block "); Serial.println(block);
      lcd.setCursor(10, 160);
      lcd.setTextColor(ST77XX_RED);
      lcd.print("Write failed block "); lcd.println(block);
    } else {
      Serial.print("Message written to block "); Serial.println(block);
      lcd.setCursor(10, 160);
      lcd.setTextColor(ST77XX_YELLOW);
      lcd.print("Written block "); lcd.println(block);
    }
  }

  Serial.println("Waiting 3 seconds before reading...");
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

    if (status != MFRC522::STATUS_OK) {
      Serial.print("Auth failed for read block "); Serial.println(block);
      continue;
    }

    byte buffer[18];
    byte size = sizeof(buffer);
    status = rfid.MIFARE_Read(block, buffer, &size);

    if (status != MFRC522::STATUS_OK) {
      Serial.print("Read failed for block "); Serial.println(block);
      continue;
    }

    Serial.print("Block "); Serial.print(block); Serial.print(": ");
    lcd.setCursor(10, 100 + i * 20);
    lcd.setTextColor(ST77XX_CYAN);
    lcd.print("Block "); lcd.print(block); lcd.print(": ");

    String blockData = "";
    for (byte j = 0; j < 16; j++) {
      char c = buffer[j];
      if (c >= 32 && c <= 126) {
        Serial.print(c);
        lcd.print(c);
        blockData += c;
      } else {
        Serial.print(".");
        lcd.print(".");
      }
    }
    Serial.println();

    if (i < 2) {  // Only blocks 4 and 8 count for name
      blockData.trim();
      if (employeeName.length() > 0) employeeName += " ";
      employeeName += blockData;
    }
  }

  employeeName.trim();
  Serial.println("Employee name: " + employeeName);

  sendShiftRequest(employeeName);
}

void sendShiftRequest(String employeeName) {
  if (!wifiConnected) {
    Serial.println("No WiFi - cannot send API request");
    lcd.setCursor(10, 180);
    lcd.setTextColor(ST77XX_RED);
    lcd.println("WiFi not connected!");
    return;
  }

  HTTPClient http;
  http.begin(API_URL);
  http.addHeader("Content-Type", "application/json");

  String payload = "{ \"employee_name\": \"" + employeeName + "\", \"work_location\": \"" + String(WORK_LOCATION) + "\" }";

  Serial.println("Sending request:");
  Serial.println(payload);

  int httpResponseCode = http.POST(payload);

  if (httpResponseCode > 0) {
    String response = http.getString();
    Serial.println("Response: " + response);
    lcd.fillScreen(ST77XX_BLACK);
    lcd.setCursor(10, 20);
    lcd.setTextColor(ST77XX_GREEN);
    lcd.println("Shift update:");
    lcd.setCursor(10, 50);
    lcd.setTextColor(ST77XX_WHITE);
    lcd.println(response.substring(0, 100));
  } else {
    Serial.print("HTTP error: ");
    Serial.println(httpResponseCode);
    lcd.setCursor(10, 160);
    lcd.setTextColor(ST77XX_RED);
    lcd.println("HTTP Error!");
  }

  http.end();
}

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
  
  if (WiFi.status() == WL_CONNECTED) {
    wifiConnected = true;
    Serial.println("\nWiFi connected!");
    Serial.print("IP address: ");
    Serial.println(WiFi.localIP());
    lcd.setCursor(10, 60);
    lcd.setTextColor(ST77XX_GREEN);
    lcd.print("WiFi: Connected!   ");
  } else {
    wifiConnected = false;
    Serial.println("\nWiFi connection failed");
    lcd.setCursor(10, 60);
    lcd.setTextColor(ST77XX_RED);
    lcd.print("WiFi: Failed!     ");
  }
  
  delay(2000);
}

void updateWifiStatus() {
  bool currentStatus = (WiFi.status() == WL_CONNECTED);
  if (currentStatus != wifiConnected) {
    wifiConnected = currentStatus;
    if (wifiConnected) {
      lastWifiAttempt = millis();
    }
  }
  
  lcd.fillRect(WIFI_X, WIFI_Y, WIFI_SIZE + 4, WIFI_SIZE + 4, ST77XX_BLACK);
  
  if (wifiConnected) {
    lcd.fillRect(WIFI_X, WIFI_Y + 6, 2, 2, ST77XX_GREEN);
    lcd.fillRect(WIFI_X - 1, WIFI_Y + 4, 4, 2, ST77XX_GREEN);
    lcd.fillRect(WIFI_X - 2, WIFI_Y + 2, 6, 2, ST77XX_GREEN);
    lcd.fillRect(WIFI_X - 3, WIFI_Y, 8, 2, ST77XX_GREEN);
  } else {
    lcd.drawLine(WIFI_X, WIFI_Y, WIFI_X + WIFI_SIZE, WIFI_Y + WIFI_SIZE, ST77XX_RED);
    lcd.drawLine(WIFI_X + WIFI_SIZE, WIFI_Y, WIFI_X, WIFI_Y + WIFI_SIZE, ST77XX_RED);
  }
}

