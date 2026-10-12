#pragma once
#include <Arduino.h>
#include <ArduinoJson.h>
#include <Arduino_GFX_Library.h>
void dashboardHandle(JsonDocument& d, int idx, uint32_t now);
void dashboardDraw(Arduino_Canvas* c, int idx, bool blocked, uint32_t now);
bool dashboardTap(int x, int y, int idx, JsonDocument& request);
bool dashboardPoll(JsonDocument& request);
bool dashboardBack(int idx, JsonDocument& request);
bool dashboardOpen();
bool dashboardDetail();
void dashboardVoiceBegin();
void dashboardVoiceEnd();
String dashboardVoiceId();
void dashboardScroll(int direction);
String dashboardVoiceToken();
void dashboardInspect(JsonDocument& response);

void dashboardTouchHeld(bool held);
void dashboardInvalidateFrame();
bool dashboardRenderPage(Arduino_Canvas* c, Arduino_GFX* output, int idx, bool blocked, uint32_t now, int rotation, int batteryPct, bool charging);
