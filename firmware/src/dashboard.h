#pragma once
#include <Arduino.h>
#include <ArduinoJson.h>
#include <Arduino_GFX_Library.h>
void dashboardHandle(JsonDocument& d, int idx, uint32_t now);
void dashboardDraw(Arduino_Canvas* c, int idx, bool blocked, uint32_t now);
bool dashboardTap(int x, int y, int idx, JsonDocument& request);
bool dashboardPoll(JsonDocument& request);
bool dashboardOpen();
bool dashboardDetail();
void dashboardScroll(int direction);
String dashboardVoiceToken();
void dashboardInspect(JsonDocument& response);
