#pragma once
#include <Arduino_GFX_Library.h>
#include <ArduinoJson.h>
void macPerformanceHandle(JsonDocument& d,uint32_t now);
void macPerformanceInvalidate();
void macPerformanceRender(Arduino_Canvas* c,Arduino_GFX* output,uint32_t now,int rotation,
                         int battery,bool charging,bool pinned,bool bright,uint16_t accent,
                         const char* toast,float toastK);
