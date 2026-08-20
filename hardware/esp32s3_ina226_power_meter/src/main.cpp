#include <Arduino.h>
#include <HardwareSerial.h>
#include <Preferences.h>
#include <Wire.h>
#include <esp_timer.h>
#include <math.h>
#include <stdarg.h>

#ifndef INA226_I2C_ADDRESS
#define INA226_I2C_ADDRESS 0x40
#endif
#ifndef INA226_SDA_PIN
#define INA226_SDA_PIN 4
#endif
#ifndef INA226_SCL_PIN
#define INA226_SCL_PIN 5
#endif
#ifndef INA226_SAMPLE_INTERVAL_MS
#define INA226_SAMPLE_INTERVAL_MS 10
#endif
#ifndef INA226_SHUNT_OHMS
#define INA226_SHUNT_OHMS 0.01f
#endif
#ifndef INA226_CURRENT_LSB_A
#define INA226_CURRENT_LSB_A 0.000125f
#endif
#ifndef INA226_INTEGRATION_GAP_MS
#define INA226_INTEGRATION_GAP_MS 30
#endif
#ifndef INA226_STATUS_INTERVAL_MS
#define INA226_STATUS_INTERVAL_MS 2000
#endif
#ifndef SHT31_I2C_ADDRESS
#define SHT31_I2C_ADDRESS 0x44
#endif
#ifndef SHT31_ENV_INTERVAL_MS
#define SHT31_ENV_INTERVAL_MS 1000
#endif
#ifndef RADXA_UART_RX_PIN
#define RADXA_UART_RX_PIN 10
#endif
#ifndef RADXA_UART_TX_PIN
#define RADXA_UART_TX_PIN 9
#endif
#ifndef RADXA_UART_BAUD
#define RADXA_UART_BAUD 115200
#endif

namespace {
constexpr uint8_t REG_CONFIG = 0x00;
constexpr uint8_t REG_SHUNT_VOLTAGE = 0x01;
constexpr uint8_t REG_BUS_VOLTAGE = 0x02;
constexpr uint8_t REG_POWER = 0x03;
constexpr uint8_t REG_CURRENT = 0x04;
constexpr uint8_t REG_CALIBRATION = 0x05;
constexpr uint8_t REG_MANUFACTURER_ID = 0xFE;
constexpr uint16_t EXPECTED_MANUFACTURER_ID = 0x5449;

// Preserve INA226 reserved reset value 0x4000; AVG=1, VBUSCT=1.1 ms,
// VSHCT=1.1 ms, continuous shunt+bus. One fresh conversion is about 2.2 ms,
// which supports the paper protocol's >=100 Hz power sampling requirement.
constexpr uint16_t CONFIG_VALUE = 0x4127;
constexpr float SHUNT_VOLTAGE_LSB_V = 2.5e-6f;
constexpr float BUS_VOLTAGE_LSB_V = 1.25e-3f;
constexpr float POWER_LSB_W = 25.0f * INA226_CURRENT_LSB_A;
constexpr uint32_t SERIAL_BAUD = 921600;
constexpr uint16_t CALIBRATION_SAMPLES = 64;
constexpr size_t OUTPUT_BUFFER_SIZE = 768;

Preferences preferences;
HardwareSerial radxaSerial(1);
bool streaming = false;
bool sensorReady = false;
bool sht31Ready = false;
bool runArmed = false;
uint64_t sequenceNumber = 0;
uint64_t lastSampleUs = 0;
uint64_t nextSampleUs = 0;
uint64_t runStartUs = 0;
double accumulatedEnergyJ = 0.0;
float previousPowerW = 0.0f;
float currentOffsetA = 0.0f;
float currentGain = 1.0f;
uint16_t manufacturerId = 0;
uint32_t nextStatusMs = 0;
uint32_t nextEnvironmentMs = 0;
uint32_t sensorRetryCount = 0;
String usbCommandBuffer;
String uartCommandBuffer;
String radxaCommandBuffer;
String activeRunId;

void outputRaw(const char *value) {
  Serial.print(value);
  Serial0.print(value);
}

void outputLine(const char *value) {
  outputRaw(value);
  outputRaw("\n");
}

void outputPrintf(const char *format, ...) {
  char buffer[OUTPUT_BUFFER_SIZE];
  va_list arguments;
  va_start(arguments, format);
  vsnprintf(buffer, sizeof(buffer), format, arguments);
  va_end(arguments);
  outputRaw(buffer);
}

void radxaPrintf(const char *format, ...) {
  char buffer[192];
  va_list arguments;
  va_start(arguments, format);
  vsnprintf(buffer, sizeof(buffer), format, arguments);
  va_end(arguments);
  radxaSerial.print(buffer);
}

uint16_t calibrationRegister() {
  const float value = 0.00512f / (INA226_CURRENT_LSB_A * INA226_SHUNT_OHMS);
  return static_cast<uint16_t>(lroundf(value));
}

bool writeRegister(uint8_t reg, uint16_t value) {
  Wire.beginTransmission(INA226_I2C_ADDRESS);
  Wire.write(reg);
  Wire.write(static_cast<uint8_t>(value >> 8));
  Wire.write(static_cast<uint8_t>(value & 0xFF));
  return Wire.endTransmission() == 0;
}

bool readRegister(uint8_t reg, uint16_t &value) {
  Wire.beginTransmission(INA226_I2C_ADDRESS);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) {
    return false;
  }
  if (Wire.requestFrom(static_cast<uint8_t>(INA226_I2C_ADDRESS),
                       static_cast<uint8_t>(2)) != 2) {
    return false;
  }
  value = (static_cast<uint16_t>(Wire.read()) << 8) | Wire.read();
  return true;
}

uint8_t scanI2cBus() {
  uint8_t foundCount = 0;
  bool ina226Found = false;
  bool sht31Found = false;
  outputRaw("{\"type\":\"i2c_scan\",\"addresses\":[");
  for (uint8_t address = 0x03; address <= 0x77; ++address) {
    Wire.beginTransmission(address);
    const uint8_t error = Wire.endTransmission();
    if (error != 0) {
      continue;
    }
    if (foundCount != 0) {
      outputRaw(",");
    }
    outputPrintf("\"0x%02X\"", address);
    ++foundCount;
    ina226Found = ina226Found || address == INA226_I2C_ADDRESS;
    sht31Found = sht31Found || address == SHT31_I2C_ADDRESS;
  }
  outputPrintf(
      "],\"count\":%u,\"ina226_address\":\"0x%02X\"," 
      "\"ina226_found\":%s,\"sht31_address\":\"0x%02X\"," 
      "\"sht31_found\":%s,\"sda\":%d,\"scl\":%d}\n",
      foundCount, INA226_I2C_ADDRESS, ina226Found ? "true" : "false",
      SHT31_I2C_ADDRESS, sht31Found ? "true" : "false", INA226_SDA_PIN,
      INA226_SCL_PIN);
  return foundCount;
}

bool configureSensor() {
  uint16_t readback = 0;
  uint16_t calibrationReadback = 0;
  manufacturerId = 0;
  if (!readRegister(REG_MANUFACTURER_ID, manufacturerId) ||
      manufacturerId != EXPECTED_MANUFACTURER_ID) {
    return false;
  }
  if (!writeRegister(REG_CONFIG, CONFIG_VALUE)) {
    return false;
  }
  if (!writeRegister(REG_CALIBRATION, calibrationRegister())) {
    return false;
  }
  return readRegister(REG_CONFIG, readback) && readback == CONFIG_VALUE &&
         readRegister(REG_CALIBRATION, calibrationReadback) &&
         calibrationReadback == calibrationRegister();
}

struct Measurement {
  bool valid = false;
  float busV = 0.0f;
  float shuntMv = 0.0f;
  float rawCurrentA = 0.0f;
  float currentA = 0.0f;
  float powerW = 0.0f;
  float chipPowerW = 0.0f;
  bool currentSaturated = false;
  bool shuntNearLimit = false;
  bool undervoltage = false;
};

Measurement readMeasurement() {
  uint16_t busRaw = 0;
  uint16_t shuntRawUnsigned = 0;
  uint16_t currentRawUnsigned = 0;
  uint16_t powerRaw = 0;
  Measurement result;
  if (!readRegister(REG_BUS_VOLTAGE, busRaw) ||
      !readRegister(REG_SHUNT_VOLTAGE, shuntRawUnsigned) ||
      !readRegister(REG_CURRENT, currentRawUnsigned) ||
      !readRegister(REG_POWER, powerRaw)) {
    return result;
  }
  const int16_t shuntRaw = static_cast<int16_t>(shuntRawUnsigned);
  const int16_t currentRaw = static_cast<int16_t>(currentRawUnsigned);
  result.busV = busRaw * BUS_VOLTAGE_LSB_V;
  result.shuntMv = shuntRaw * SHUNT_VOLTAGE_LSB_V * 1000.0f;
  result.rawCurrentA = currentRaw * INA226_CURRENT_LSB_A;
  result.currentA = (result.rawCurrentA - currentOffsetA) * currentGain;
  result.powerW = result.busV * result.currentA;
  result.chipPowerW = powerRaw * POWER_LSB_W;
  result.currentSaturated = currentRaw >= 32700 || currentRaw <= -32700;
  result.shuntNearLimit = fabsf(result.shuntMv) >= 75.0f;
  result.undervoltage = result.busV > 0.2f && result.busV < 4.75f;
  result.valid = isfinite(result.busV) && isfinite(result.currentA) &&
                 isfinite(result.powerW);
  return result;
}

uint8_t sht31Crc(const uint8_t *data, size_t length) {
  uint8_t crc = 0xFF;
  for (size_t index = 0; index < length; ++index) {
    crc ^= data[index];
    for (uint8_t bit = 0; bit < 8; ++bit) {
      crc = (crc & 0x80) ? static_cast<uint8_t>((crc << 1) ^ 0x31)
                         : static_cast<uint8_t>(crc << 1);
    }
  }
  return crc;
}

bool probeSht31() {
  Wire.beginTransmission(SHT31_I2C_ADDRESS);
  return Wire.endTransmission() == 0;
}

struct EnvironmentMeasurement {
  bool valid = false;
  float temperatureC = 0.0f;
  float relativeHumidityPct = 0.0f;
};

EnvironmentMeasurement readEnvironment() {
  EnvironmentMeasurement result;
  Wire.beginTransmission(SHT31_I2C_ADDRESS);
  Wire.write(0x24);  // Single shot, low repeatability, no clock stretching.
  Wire.write(0x16);
  if (Wire.endTransmission() != 0) {
    return result;
  }
  delay(5);
  if (Wire.requestFrom(static_cast<uint8_t>(SHT31_I2C_ADDRESS),
                       static_cast<uint8_t>(6)) != 6) {
    return result;
  }
  uint8_t raw[6];
  for (uint8_t index = 0; index < 6; ++index) {
    raw[index] = static_cast<uint8_t>(Wire.read());
  }
  if (sht31Crc(raw, 2) != raw[2] || sht31Crc(raw + 3, 2) != raw[5]) {
    return result;
  }
  const uint16_t temperatureRaw =
      (static_cast<uint16_t>(raw[0]) << 8) | raw[1];
  const uint16_t humidityRaw =
      (static_cast<uint16_t>(raw[3]) << 8) | raw[4];
  result.temperatureC =
      -45.0f + 175.0f * static_cast<float>(temperatureRaw) / 65535.0f;
  result.relativeHumidityPct =
      100.0f * static_cast<float>(humidityRaw) / 65535.0f;
  result.relativeHumidityPct =
      fminf(100.0f, fmaxf(0.0f, result.relativeHumidityPct));
  result.valid = isfinite(result.temperatureC) &&
                 isfinite(result.relativeHumidityPct);
  return result;
}

void emitEnvironment(const char *phase) {
  const uint64_t nowUs = esp_timer_get_time();
  const EnvironmentMeasurement value = readEnvironment();
  sht31Ready = value.valid;
  if (!value.valid) {
    outputPrintf(
        "{\"type\":\"environment\",\"schema\":\"sht31-environment-v1.0\"," 
        "\"run_id\":\"%s\",\"phase\":\"%s\",\"device_us\":%llu," 
        "\"valid\":false}\n",
        activeRunId.c_str(), phase, static_cast<unsigned long long>(nowUs));
    return;
  }
  outputPrintf(
      "{\"type\":\"environment\",\"schema\":\"sht31-environment-v1.0\"," 
      "\"run_id\":\"%s\",\"phase\":\"%s\",\"device_us\":%llu," 
      "\"ambient_temperature_c\":%.4f," 
      "\"ambient_relative_humidity_pct\":%.4f,\"valid\":true}\n",
      activeRunId.c_str(), phase, static_cast<unsigned long long>(nowUs),
      value.temperatureC, value.relativeHumidityPct);
}

String safeToken(const String &input) {
  String output;
  for (size_t index = 0; index < input.length() && output.length() < 80; ++index) {
    const char value = input[index];
    if (isalnum(static_cast<unsigned char>(value)) || value == '_' ||
        value == '-' || value == '.' || value == ':') {
      output += value;
    }
  }
  return output;
}

bool validRunId(const String &value) {
  return !value.isEmpty() && value.length() <= 80 && safeToken(value) == value;
}

void resetMeasurementState() {
  accumulatedEnergyJ = 0.0;
  previousPowerW = 0.0f;
  lastSampleUs = 0;
  sequenceNumber = 0;
  nextSampleUs = esp_timer_get_time();
}

void printMeta() {
  outputPrintf(
      "{\"type\":\"meta\",\"schema\":\"power-environment-meter-v2.0\"," 
      "\"firmware\":\"esp32s3-ina226-sht31-v2.0\",\"address\":\"0x%02X\"," 
      "\"sda\":%d,\"scl\":%d,\"sample_interval_ms\":%d," 
      "\"power_sample_rate_hz\":%.3f," 
      "\"shunt_ohms\":%.8f,\"current_lsb_a\":%.9f," 
      "\"calibration_register\":%u,\"offset_a\":%.9f,\"gain\":%.9f," 
      "\"config_register\":\"0x%04X\",\"manufacturer_id\":\"0x%04X\"," 
      "\"sensor_ready\":%s,\"serial_baud\":%u," 
      "\"integration_gap_limit_ms\":%u," 
      "\"sht31_address\":\"0x%02X\",\"sht31_ready\":%s," 
      "\"environment_interval_ms\":%u," 
      "\"radxa_uart_baud\":%u,\"radxa_rx\":%d,\"radxa_tx\":%d," 
      "\"transport\":\"usb_cdc+uart0+radxa_uart1\"}\n",
      INA226_I2C_ADDRESS, INA226_SDA_PIN, INA226_SCL_PIN,
      INA226_SAMPLE_INTERVAL_MS, 1000.0f / INA226_SAMPLE_INTERVAL_MS,
      INA226_SHUNT_OHMS,
      INA226_CURRENT_LSB_A, calibrationRegister(), currentOffsetA,
      currentGain, CONFIG_VALUE, manufacturerId,
      sensorReady ? "true" : "false", SERIAL_BAUD,
      INA226_INTEGRATION_GAP_MS, SHT31_I2C_ADDRESS,
      sht31Ready ? "true" : "false", SHT31_ENV_INTERVAL_MS,
      RADXA_UART_BAUD, RADXA_UART_RX_PIN, RADXA_UART_TX_PIN);
}

void printStatus() {
  outputPrintf(
      "{\"type\":\"status\",\"schema\":\"ina226-meter-v1.0\"," 
      "\"sensor_ready\":%s,\"sht31_ready\":%s," 
      "\"streaming\":%s,\"armed\":%s," 
      "\"run_id\":\"%s\"," 
      "\"manufacturer_id\":\"0x%04X\",\"retry_count\":%u," 
      "\"device_us\":%llu}\n",
      sensorReady ? "true" : "false", sht31Ready ? "true" : "false",
      streaming ? "true" : "false",
      runArmed ? "true" : "false", activeRunId.c_str(), manufacturerId,
      sensorRetryCount,
      static_cast<unsigned long long>(esp_timer_get_time()));
}

float averageRawCurrent(uint16_t count) {
  double sum = 0.0;
  uint16_t accepted = 0;
  for (uint16_t index = 0; index < count; ++index) {
    const Measurement value = readMeasurement();
    if (value.valid) {
      sum += value.rawCurrentA;
      ++accepted;
    }
    delay(INA226_SAMPLE_INTERVAL_MS);
  }
  return accepted ? static_cast<float>(sum / accepted) : NAN;
}

void handleCommand(String command) {
  command.trim();
  if (command.isEmpty()) {
    return;
  }
  if (command == "PING") {
    outputPrintf(
        "{\"type\":\"pong\",\"sensor_ready\":%s," 
        "\"streaming\":%s,\"device_us\":%llu}\n",
        sensorReady ? "true" : "false", streaming ? "true" : "false",
        static_cast<unsigned long long>(esp_timer_get_time()));
  } else if (command == "SCAN") {
    scanI2cBus();
  } else if (command == "META") {
    printMeta();
  } else if (command == "STATUS") {
    printStatus();
  } else if (command == "ENV") {
    emitEnvironment("manual");
  } else if (command == "START") {
    activeRunId = "";
    runArmed = false;
    runStartUs = esp_timer_get_time();
    resetMeasurementState();
    emitEnvironment("run_start");
    nextEnvironmentMs = millis() + SHT31_ENV_INTERVAL_MS;
    streaming = true;
    outputPrintf(
        "{\"type\":\"state\",\"streaming\":true,\"device_us\":%llu}\n",
        static_cast<unsigned long long>(esp_timer_get_time()));
  } else if (command == "STOP") {
    streaming = false;
    emitEnvironment("run_end");
    outputPrintf(
        "{\"type\":\"state\",\"streaming\":false,\"device_us\":%llu," 
        "\"energy_j\":%.9f}\n",
        static_cast<unsigned long long>(esp_timer_get_time()),
      accumulatedEnergyJ);
    activeRunId = "";
    runArmed = false;
  } else if (command == "ZERO") {
    const bool wasStreaming = streaming;
    streaming = false;
    const float value = averageRawCurrent(CALIBRATION_SAMPLES);
    if (isfinite(value)) {
      currentOffsetA = value;
      preferences.putFloat("offset_a", currentOffsetA);
      outputPrintf(
          "{\"type\":\"calibration\",\"action\":\"zero\",\"ok\":true,"
          "\"offset_a\":%.9f,\"samples\":%u}\n",
          currentOffsetA, CALIBRATION_SAMPLES);
    } else {
      outputLine(
          "{\"type\":\"calibration\",\"action\":\"zero\",\"ok\":false}");
    }
    streaming = wasStreaming;
  } else if (command.startsWith("CAL ")) {
    const float referenceA = command.substring(4).toFloat();
    const bool wasStreaming = streaming;
    streaming = false;
    const float measuredA = averageRawCurrent(CALIBRATION_SAMPLES) - currentOffsetA;
    const float candidateGain =
        fabsf(measuredA) > 0.05f ? referenceA / measuredA : NAN;
    if (isfinite(candidateGain) && candidateGain >= 0.5f &&
        candidateGain <= 1.5f) {
      currentGain = candidateGain;
      preferences.putFloat("gain", currentGain);
      outputPrintf(
          "{\"type\":\"calibration\",\"action\":\"gain\",\"ok\":true,"
          "\"reference_a\":%.9f,\"measured_a\":%.9f,\"gain\":%.9f,"
          "\"samples\":%u}\n",
          referenceA, measuredA, currentGain, CALIBRATION_SAMPLES);
    } else {
      outputPrintf(
          "{\"type\":\"calibration\",\"action\":\"gain\",\"ok\":false,"
          "\"reference_a\":%.9f,\"measured_a\":%.9f}\n",
          referenceA, measuredA);
    }
    streaming = wasStreaming;
  } else if (command == "RESET_CAL") {
    currentOffsetA = 0.0f;
    currentGain = 1.0f;
    preferences.putFloat("offset_a", currentOffsetA);
    preferences.putFloat("gain", currentGain);
    outputLine(
        "{\"type\":\"calibration\",\"action\":\"reset\",\"ok\":true}");
  } else if (command.startsWith("SYNC ")) {
    const String hostNs = safeToken(command.substring(5));
    outputPrintf(
        "{\"type\":\"sync_ack\",\"host_epoch_ns\":\"%s\","
        "\"device_us\":%llu}\n",
        hostNs.c_str(),
        static_cast<unsigned long long>(esp_timer_get_time()));
  } else if (command.startsWith("MARK ")) {
    const String marker = safeToken(command.substring(5));
    outputPrintf(
        "{\"type\":\"firmware_marker\",\"marker\":\"%s\","
        "\"device_us\":%llu,\"energy_j\":%.9f}\n",
        marker.c_str(),
        static_cast<unsigned long long>(esp_timer_get_time()),
        accumulatedEnergyJ);
  } else {
    outputPrintf(
        "{\"type\":\"error\",\"reason\":\"unknown_command\"," 
        "\"command\":\"%s\"}\n",
        safeToken(command).c_str());
  }
}

void handleRadxaCommand(String command) {
  command.trim();
  if (command.isEmpty()) {
    return;
  }
  if (command == "HELLO") {
    outputPrintf(
        "{\"type\":\"radxa_rx\",\"command\":\"HELLO\"," 
        "\"device_us\":%llu}\n",
        static_cast<unsigned long long>(esp_timer_get_time()));
    radxaPrintf("ACK,HELLO\n");
    return;
  }

  const int separator = command.indexOf(',');
  String action = separator >= 0 ? command.substring(0, separator) : command;
  String runId = separator >= 0 ? command.substring(separator + 1) : "";
  action.trim();
  action.toUpperCase();
  runId.trim();
  if (!validRunId(runId)) {
    radxaPrintf("ERROR,INVALID_RUN_ID\n");
    outputPrintf(
        "{\"type\":\"radxa_protocol_error\"," 
        "\"reason\":\"invalid_run_id\",\"device_us\":%llu}\n",
        static_cast<unsigned long long>(esp_timer_get_time()));
    return;
  }

  outputPrintf(
      "{\"type\":\"radxa_rx\",\"command\":\"%s\"," 
      "\"run_id\":\"%s\",\"device_us\":%llu}\n",
      action.c_str(), runId.c_str(),
      static_cast<unsigned long long>(esp_timer_get_time()));

  if (action == "ARM") {
    if (!sensorReady) {
      radxaPrintf("ERROR,SENSOR_NOT_READY,%s\n", runId.c_str());
      return;
    }
    if (streaming) {
      radxaPrintf("ERROR,BUSY,%s\n", runId.c_str());
      return;
    }
    activeRunId = runId;
    runArmed = true;
    runStartUs = 0;
    resetMeasurementState();
    outputPrintf(
        "{\"type\":\"run_armed\",\"run_id\":\"%s\"," 
        "\"sensor_ready\":true,\"device_us\":%llu}\n",
        activeRunId.c_str(),
        static_cast<unsigned long long>(esp_timer_get_time()));
    radxaPrintf("READY,%s\n", activeRunId.c_str());
    return;
  }

  if (action == "START") {
    if (!sensorReady) {
      radxaPrintf("ERROR,SENSOR_NOT_READY,%s\n", runId.c_str());
      return;
    }
    if (!runArmed) {
      radxaPrintf("ERROR,NOT_ARMED,%s\n", runId.c_str());
      return;
    }
    if (activeRunId != runId) {
      radxaPrintf("ERROR,RUN_ID_MISMATCH,%s\n", runId.c_str());
      return;
    }
    if (streaming) {
      radxaPrintf("ERROR,ALREADY_STREAMING,%s\n", runId.c_str());
      return;
    }
    resetMeasurementState();
    emitEnvironment("run_start");
    nextEnvironmentMs = millis() + SHT31_ENV_INTERVAL_MS;
    runStartUs = esp_timer_get_time();
    streaming = true;
    outputPrintf(
        "{\"type\":\"run_start\",\"run_id\":\"%s\"," 
        "\"device_us\":%llu}\n",
        activeRunId.c_str(), static_cast<unsigned long long>(runStartUs));
    radxaPrintf("ACK_START,%s\n", activeRunId.c_str());
    return;
  }

  if (action == "STOP") {
    if (!streaming) {
      radxaPrintf("ERROR,NOT_STREAMING,%s\n", runId.c_str());
      return;
    }
    if (activeRunId != runId) {
      radxaPrintf("ERROR,RUN_ID_MISMATCH,%s\n", runId.c_str());
      return;
    }
    const uint64_t stopUs = esp_timer_get_time();
    streaming = false;
    emitEnvironment("run_end");
    outputPrintf(
        "{\"type\":\"run_end\",\"run_id\":\"%s\"," 
        "\"device_us\":%llu,\"duration_us\":%llu,\"samples\":%llu," 
        "\"energy_j\":%.9f}\n",
        activeRunId.c_str(), static_cast<unsigned long long>(stopUs),
        static_cast<unsigned long long>(stopUs - runStartUs),
        static_cast<unsigned long long>(sequenceNumber), accumulatedEnergyJ);
    radxaPrintf("DONE,%s\n", activeRunId.c_str());
    runArmed = false;
    activeRunId = "";
    return;
  }

  radxaPrintf("ERROR,UNKNOWN_COMMAND,%s\n", action.c_str());
  outputPrintf(
      "{\"type\":\"radxa_protocol_error\",\"reason\":\"unknown_command\"," 
      "\"command\":\"%s\",\"run_id\":\"%s\",\"device_us\":%llu}\n",
      action.c_str(), runId.c_str(),
      static_cast<unsigned long long>(esp_timer_get_time()));
}

void readCommandsFrom(Stream &port, String &buffer) {
  while (port.available()) {
    const char value = static_cast<char>(port.read());
    if (value == '\n' || value == '\r') {
      if (!buffer.isEmpty()) {
        handleCommand(buffer);
        buffer = "";
      }
    } else if (buffer.length() < 160) {
      buffer += value;
    }
  }
}

void readCommands() {
  readCommandsFrom(Serial, usbCommandBuffer);
  readCommandsFrom(Serial0, uartCommandBuffer);
  while (radxaSerial.available()) {
    const char value = static_cast<char>(radxaSerial.read());
    if (value == '\n' || value == '\r') {
      if (!radxaCommandBuffer.isEmpty()) {
        handleRadxaCommand(radxaCommandBuffer);
        radxaCommandBuffer = "";
      }
    } else if (radxaCommandBuffer.length() < 160) {
      radxaCommandBuffer += value;
    }
  }
}

void emitSample() {
  const uint64_t nowUs = esp_timer_get_time();
  const Measurement value = readMeasurement();
  if (!value.valid) {
    outputPrintf(
        "{\"type\":\"error\",\"reason\":\"i2c_read_failed\","
        "\"device_us\":%llu}\n",
        static_cast<unsigned long long>(nowUs));
    sensorReady = configureSensor();
    return;
  }
  bool integrationGap = false;
  if (lastSampleUs != 0) {
    const double deltaSeconds = (nowUs - lastSampleUs) / 1000000.0;
    const double maximumGapSeconds = INA226_INTEGRATION_GAP_MS / 1000.0;
    if (deltaSeconds > 0.0 && deltaSeconds <= maximumGapSeconds) {
      accumulatedEnergyJ +=
          0.5 * (previousPowerW + value.powerW) * deltaSeconds;
    } else {
      integrationGap = true;
    }
  }
  lastSampleUs = nowUs;
  previousPowerW = value.powerW;
  outputPrintf(
      "{\"type\":\"sample\",\"schema\":\"ina226-meter-v1.0\"," 
      "\"run_id\":\"%s\",\"seq\":%llu,\"device_us\":%llu," 
      "\"bus_v\":%.6f,"
      "\"shunt_mv\":%.6f,\"raw_current_a\":%.6f,"
      "\"current_a\":%.6f,\"power_w\":%.6f,\"chip_power_w\":%.6f,"
      "\"energy_j\":%.9f,\"current_saturated\":%s,"
      "\"shunt_near_limit\":%s,\"undervoltage\":%s,"
      "\"integration_gap\":%s}\n",
      activeRunId.c_str(), static_cast<unsigned long long>(sequenceNumber++),
      static_cast<unsigned long long>(nowUs), value.busV, value.shuntMv,
      value.rawCurrentA, value.currentA, value.powerW, value.chipPowerW,
      accumulatedEnergyJ, value.currentSaturated ? "true" : "false",
      value.shuntNearLimit ? "true" : "false",
      value.undervoltage ? "true" : "false",
      integrationGap ? "true" : "false");
}
}  // namespace

void setup() {
  Serial.begin(SERIAL_BAUD);
  Serial0.begin(SERIAL_BAUD);
  radxaSerial.begin(RADXA_UART_BAUD, SERIAL_8N1, RADXA_UART_RX_PIN,
                    RADXA_UART_TX_PIN);
  delay(1000);
  preferences.begin("ina226", false);
  currentOffsetA = preferences.getFloat("offset_a", 0.0f);
  currentGain = preferences.getFloat("gain", 1.0f);
  Wire.begin(INA226_SDA_PIN, INA226_SCL_PIN, 400000);
  scanI2cBus();
  sensorReady = configureSensor();
  sht31Ready = probeSht31();
  outputPrintf(
      "{\"type\":\"boot\",\"ok\":%s,\"device_us\":%llu}\n",
      sensorReady ? "true" : "false",
      static_cast<unsigned long long>(esp_timer_get_time()));
  printMeta();
  nextSampleUs = esp_timer_get_time();
  nextStatusMs = millis() + INA226_STATUS_INTERVAL_MS;
  nextEnvironmentMs = millis() + SHT31_ENV_INTERVAL_MS;
}

void loop() {
  readCommands();
  if (!sensorReady) {
    const uint32_t nowMs = millis();
    if (static_cast<int32_t>(nowMs - nextStatusMs) >= 0) {
      ++sensorRetryCount;
      sensorReady = configureSensor();
      printStatus();
      if (sensorReady) {
        printMeta();
      }
      nextStatusMs = nowMs + INA226_STATUS_INTERVAL_MS;
    }
    delay(10);
    return;
  }
  const uint32_t nowMs = millis();
  if (!streaming && static_cast<int32_t>(nowMs - nextStatusMs) >= 0) {
    printStatus();
    nextStatusMs = nowMs + INA226_STATUS_INTERVAL_MS;
  }
  const uint64_t nowUs = esp_timer_get_time();
  if (streaming && nowUs >= nextSampleUs) {
    emitSample();
    nextSampleUs = nowUs + INA226_SAMPLE_INTERVAL_MS * 1000ULL;
  }
  if (streaming && static_cast<int32_t>(nowMs - nextEnvironmentMs) >= 0) {
    emitEnvironment("periodic");
    nextEnvironmentMs = millis() + SHT31_ENV_INTERVAL_MS;
  }
  delay(1);
}
