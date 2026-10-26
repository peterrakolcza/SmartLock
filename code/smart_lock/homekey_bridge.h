// HomeKey bridge
//
// Connects the lock to a HomeKey-ESP32 reader (https://github.com/rednblkx/HomeKey-ESP32).
// The reader is the native Apple Home accessory (HomeKit + Home Key NFC), this lock is the
// mechanism. They talk MQTT, using the reader's default topic layout:
//
//   <prefix>/homekit/state              reader -> lock   0 unlocked, 1 locked, 4 unlocking, 5 locking
//   <prefix>/homekit/set_state          lock -> reader   0 / 1, real state of the lock (sets current + target)
//   <prefix>/homekit/set_current_state  lock -> reader   2 = jammed (Apple Home shows a jam alert)
//
// HOMEKEY_MODE (set in smart_lock.ino):
//   0  disabled, the lock works standalone (HTTP API + button)
//   1  built-in broker: the reader connects directly to the lock on port 1883, no extra server needed
//   2  external broker: lock and reader both connect to Mosquitto / Home Assistant / ...

#pragma once

#include <ESP8266WiFi.h>

#ifndef HOMEKEY_MODE
#define HOMEKEY_MODE 0
#endif

typedef void (*HomeKeyCommandHandler)(bool lock);

static HomeKeyCommandHandler homekeyOnCommand = nullptr;
static const String homekeyStateTopic = String(HOMEKEY_TOPIC_PREFIX) + "/homekit/state";
static const String homekeySetStateTopic = String(HOMEKEY_TOPIC_PREFIX) + "/homekit/set_state";
static const String homekeyCurrentStateTopic = String(HOMEKEY_TOPIC_PREFIX) + "/homekit/set_current_state";

// HomeKey-ESP32 lock states
#define HK_UNLOCKED 0
#define HK_LOCKED 1
#define HK_JAMMED 2
#define HK_UNLOCKING 4
#define HK_LOCKING 5

__attribute__((unused)) static void homekeyHandleMessage(const String& topic, const char* payload, unsigned int length) {
  if (topic != homekeyStateTopic || length == 0 || homekeyOnCommand == nullptr) return;

  // The reader announces a pending transition, settled states (0 / 1) are only echoes of our own reports
  int state = atoi(String(payload).substring(0, length).c_str());
  if (state == HK_UNLOCKING) {
    Serial.println("HomeKey: unlock requested");
    homekeyOnCommand(false);
  } else if (state == HK_LOCKING) {
    Serial.println("HomeKey: lock requested");
    homekeyOnCommand(true);
  }
}

#if HOMEKEY_MODE == 1
//#############################################################################################################################################
//###                                                                   ###
//###                     BUILT-IN MQTT BROKER (single client)          ###
//###                                                                   ###
//#############################################################################################################################################
// Just enough of MQTT 3.1.1 for one HomeKey reader: CONNECT, SUBSCRIBE, PUBLISH (QoS 0-2), PING, DISCONNECT.
// Messages from the reader are handed to the lock, messages from the lock are sent to the reader.

#define MQTT_BUFFER_SIZE 1024
#define MQTT_MAX_SUBSCRIPTIONS 8
#define MQTT_MAX_RETAINED 4

class MiniMqttBroker {
public:
  MiniMqttBroker(uint16_t port) : server(port) {}

  void begin() { server.begin(); }

  void loop() {
    if (server.hasClient()) {
      // A new connection always replaces the old one, e.g. after the reader rebooted
      if (peer.connected()) peer.stop();
      peer = server.accept();
      peer.setNoDelay(true);
      connected = false;
      subscriptionCount = 0;
      lastSeen = millis();
      Serial.println("HomeKey: reader connecting from " + peer.remoteIP().toString());
    }

    if (!peer.connected()) {
      connected = false;
      return;
    }

    while (peer.available() > 0) {
      if (!readPacket()) {
        Serial.println("HomeKey: invalid MQTT packet, dropping reader");
        peer.stop();
        return;
      }
      lastSeen = millis();
    }

    if (keepAlive > 0 && millis() - lastSeen > keepAlive * 1500UL) {
      Serial.println("HomeKey: reader timed out");
      peer.stop();
    }
  }

  // The last retained message per topic is replayed whenever the reader (re)subscribes
  void publish(const String& topic, const String& payload, bool retain) {
    if (retain) {
      uint8_t slot = 0;
      while (slot < MQTT_MAX_RETAINED - 1 && retainedTopic[slot].length() > 0 && retainedTopic[slot] != topic) slot++;
      retainedTopic[slot] = topic;
      retainedPayload[slot] = payload;
    }
    if (connected && isSubscribed(topic)) sendPublish(topic, payload, false);
  }

  bool isConnected() { return connected && peer.connected(); }

private:
  WiFiServer server;
  WiFiClient peer;
  bool connected = false;
  uint16_t keepAlive = 0;
  unsigned long lastSeen = 0;
  uint8_t buffer[MQTT_BUFFER_SIZE];
  String subscriptions[MQTT_MAX_SUBSCRIPTIONS];
  uint8_t subscriptionCount = 0;
  String retainedTopic[MQTT_MAX_RETAINED];
  String retainedPayload[MQTT_MAX_RETAINED];

  int readByte() {
    unsigned long start = millis();
    while (!peer.available()) {
      if (!peer.connected() || millis() - start > 2000) return -1;
      delay(1);
    }
    return peer.read();
  }

  bool readPacket() {
    int header = readByte();
    if (header < 0) return false;

    // Remaining length, variable length encoding
    uint32_t length = 0;
    uint32_t multiplier = 1;
    for (int i = 0; i < 4; i++) {
      int b = readByte();
      if (b < 0) return false;
      length += (b & 0x7F) * multiplier;
      multiplier *= 128;
      if ((b & 0x80) == 0) break;
      if (i == 3) return false;
    }

    // Oversized packets (e.g. Home Assistant discovery) are read partially, the head holds topic + packet id
    uint32_t stored = 0;
    for (uint32_t i = 0; i < length; i++) {
      int b = readByte();
      if (b < 0) return false;
      if (stored < MQTT_BUFFER_SIZE) buffer[stored++] = b;
    }

    uint8_t type = header >> 4;
    if (!connected && type != 1) return false;

    switch (type) {
      case 1: return handleConnect(stored);
      case 3: return handlePublish(header, stored, length);
      case 6: return sendAck(0x70, stored);  // PUBREL -> PUBCOMP
      case 8: return handleSubscribe(stored);
      case 10: return sendAck(0xB0, stored); // UNSUBSCRIBE -> UNSUBACK
      case 12: {                             // PINGREQ
        uint8_t pong[] = {0xD0, 0x00};
        peer.write(pong, sizeof(pong));
        return true;
      }
      case 14:                               // DISCONNECT
        peer.stop();
        connected = false;
        return true;
      default:                               // PUBACK etc. from the client, nothing to do
        return true;
    }
  }

  uint16_t readU16(uint32_t pos) { return (buffer[pos] << 8) | buffer[pos + 1]; }

  bool readString(uint32_t& pos, uint32_t stored, String& out) {
    if (pos + 2 > stored) return false;
    uint16_t len = readU16(pos);
    pos += 2;
    if (pos + len > stored) return false;
    out = "";
    out.reserve(len);
    for (uint16_t i = 0; i < len; i++) out += (char)buffer[pos + i];
    pos += len;
    return true;
  }

  bool handleConnect(uint32_t stored) {
    uint32_t pos = 0;
    String protocol, clientId, unused, username, password;
    if (!readString(pos, stored, protocol) || pos + 4 > stored) return false;
    pos++; // protocol level
    uint8_t flags = buffer[pos++];
    keepAlive = readU16(pos);
    pos += 2;
    if (!readString(pos, stored, clientId)) return false;
    if (flags & 0x04) { // will topic + message
      if (!readString(pos, stored, unused) || !readString(pos, stored, unused)) return false;
    }
    if (flags & 0x80) readString(pos, stored, username);
    if (flags & 0x40) readString(pos, stored, password);

    bool authorized = String(MQTT_USER).length() == 0 || (username == MQTT_USER && password == MQTT_PASS);
    uint8_t connack[] = {0x20, 0x02, 0x00, (uint8_t)(authorized ? 0x00 : 0x05)};
    peer.write(connack, sizeof(connack));
    if (!authorized) {
      Serial.println("HomeKey: reader rejected, wrong MQTT username / password");
      peer.stop();
      return true;
    }

    connected = true;
    Serial.println("HomeKey: reader connected as " + clientId);
    return true;
  }

  bool handlePublish(uint8_t header, uint32_t stored, uint32_t length) {
    uint8_t qos = (header >> 1) & 0x03;
    uint32_t pos = 0;
    String topic;
    if (!readString(pos, stored, topic)) return false;

    uint16_t packetId = 0;
    if (qos > 0) {
      if (pos + 2 > stored) return false;
      packetId = readU16(pos);
      pos += 2;
    }

    if (length <= MQTT_BUFFER_SIZE) {
      // Null terminate the payload for the handler
      uint32_t payloadLength = stored - pos;
      static char payload[MQTT_BUFFER_SIZE + 1];
      memcpy(payload, buffer + pos, payloadLength);
      payload[payloadLength] = 0;
      homekeyHandleMessage(topic, payload, payloadLength);
    }

    if (qos > 0) {
      uint8_t ack[] = {(uint8_t)(qos == 1 ? 0x40 : 0x50), 0x02, (uint8_t)(packetId >> 8), (uint8_t)(packetId & 0xFF)};
      peer.write(ack, sizeof(ack));
    }
    return true;
  }

  bool handleSubscribe(uint32_t stored) {
    if (stored < 2) return false;
    uint16_t packetId = readU16(0);
    uint32_t pos = 2;
    uint8_t granted[MQTT_MAX_SUBSCRIPTIONS];
    uint8_t count = 0;
    bool wantsRetained[MQTT_MAX_RETAINED] = {};
    while (pos < stored && count < MQTT_MAX_SUBSCRIPTIONS) {
      String filter;
      if (!readString(pos, stored, filter) || pos >= stored) return false;
      pos++; // requested QoS, everything is delivered with QoS 0
      if (subscriptionCount < MQTT_MAX_SUBSCRIPTIONS) subscriptions[subscriptionCount++] = filter;
      for (uint8_t i = 0; i < MQTT_MAX_RETAINED; i++) {
        if (retainedTopic[i].length() > 0 && topicMatches(filter, retainedTopic[i])) wantsRetained[i] = true;
      }
      granted[count++] = 0x00;
    }

    uint8_t suback[4 + MQTT_MAX_SUBSCRIPTIONS] = {0x90, (uint8_t)(2 + count), (uint8_t)(packetId >> 8), (uint8_t)(packetId & 0xFF)};
    memcpy(suback + 4, granted, count);
    peer.write(suback, 4 + count);

    for (uint8_t i = 0; i < MQTT_MAX_RETAINED; i++) {
      if (wantsRetained[i]) sendPublish(retainedTopic[i], retainedPayload[i], true);
    }
    return true;
  }

  bool sendAck(uint8_t type, uint32_t stored) {
    if (stored < 2) return false;
    uint8_t ack[] = {type, 0x02, buffer[0], buffer[1]};
    peer.write(ack, sizeof(ack));
    return true;
  }

  static bool topicMatches(const String& filter, const String& topic) {
    if (filter == "#" || filter == topic) return true;
    int f = 0, t = 0;
    while (f < (int)filter.length() && t <= (int)topic.length()) {
      if (filter[f] == '#') return true;
      if (filter[f] == '+') {
        while (t < (int)topic.length() && topic[t] != '/') t++;
        f++;
        continue;
      }
      if (t >= (int)topic.length() || filter[f] != topic[t]) return false;
      f++;
      t++;
    }
    return f == (int)filter.length() && t == (int)topic.length();
  }

  bool isSubscribed(const String& topic) {
    for (uint8_t i = 0; i < subscriptionCount; i++) {
      if (topicMatches(subscriptions[i], topic)) return true;
    }
    return false;
  }

  void sendPublish(const String& topic, const String& payload, bool retain) {
    uint32_t length = 2 + topic.length() + payload.length();
    uint8_t header[5] = {(uint8_t)(0x30 | (retain ? 0x01 : 0x00))};
    uint8_t headerLength = 1;
    do {
      uint8_t b = length % 128;
      length /= 128;
      if (length > 0) b |= 0x80;
      header[headerLength++] = b;
    } while (length > 0);
    uint8_t topicLength[] = {(uint8_t)(topic.length() >> 8), (uint8_t)(topic.length() & 0xFF)};

    peer.write(header, headerLength);
    peer.write(topicLength, 2);
    peer.write(topic.c_str(), topic.length());
    peer.write(payload.c_str(), payload.length());
  }
};

static MiniMqttBroker homekeyBroker(MQTT_PORT);

void homekeyBegin(HomeKeyCommandHandler onCommand) {
  homekeyOnCommand = onCommand;
  homekeyBroker.begin();
  MDNS.addService("mqtt", "tcp", MQTT_PORT);
  Serial.println("HomeKey: built-in MQTT broker listening on port " + String(MQTT_PORT));
}

void homekeyLoop() { homekeyBroker.loop(); }

void homekeyReportState(bool isLocked) {
  homekeyBroker.publish(homekeySetStateTopic, isLocked ? "1" : "0", true);
}

void homekeyReportJammed() {
  homekeyBroker.publish(homekeyCurrentStateTopic, String(HK_JAMMED), false);
}

bool homekeyConnected() { return homekeyBroker.isConnected(); }

#elif HOMEKEY_MODE == 2
//#############################################################################################################################################
//###                                                                   ###
//###                     EXTERNAL MQTT BROKER                          ###
//###                                                                   ###
//#############################################################################################################################################

#include <PubSubClient.h>

static WiFiClient homekeyWifiClient;
static PubSubClient homekeyMqtt(homekeyWifiClient);
static unsigned long homekeyLastReconnect = 0;
static int homekeyLastReported = -1;

static void homekeyMqttCallback(char* topic, byte* payload, unsigned int length) {
  homekeyHandleMessage(String(topic), (const char*)payload, length);
}

void homekeyBegin(HomeKeyCommandHandler onCommand) {
  homekeyOnCommand = onCommand;
  homekeyMqtt.setServer(MQTT_HOST, MQTT_PORT);
  homekeyMqtt.setCallback(homekeyMqttCallback);
}

void homekeyReportState(bool isLocked) {
  homekeyLastReported = isLocked ? 1 : 0;
  if (homekeyMqtt.connected()) homekeyMqtt.publish(homekeySetStateTopic.c_str(), isLocked ? "1" : "0", true);
}

void homekeyLoop() {
  if (!homekeyMqtt.connected() && millis() - homekeyLastReconnect > 5000) {
    homekeyLastReconnect = millis();
    bool ok = String(MQTT_USER).length() > 0
      ? homekeyMqtt.connect("smartlock", MQTT_USER, MQTT_PASS)
      : homekeyMqtt.connect("smartlock");
    if (ok) {
      Serial.println("HomeKey: connected to MQTT broker " + String(MQTT_HOST));
      homekeyMqtt.subscribe(homekeyStateTopic.c_str());
      if (homekeyLastReported >= 0) homekeyReportState(homekeyLastReported == 1);
    }
  }
  homekeyMqtt.loop();
}

void homekeyReportJammed() {
  if (homekeyMqtt.connected()) homekeyMqtt.publish(homekeyCurrentStateTopic.c_str(), String(HK_JAMMED).c_str());
}

bool homekeyConnected() { return homekeyMqtt.connected(); }

#else

void homekeyBegin(HomeKeyCommandHandler) {}
void homekeyLoop() {}
void homekeyReportState(bool) {}
void homekeyReportJammed() {}
bool homekeyConnected() { return false; }

#endif
