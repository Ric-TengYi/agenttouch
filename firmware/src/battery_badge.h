#pragma once
#include <initializer_list>
constexpr int BATTERY_LEFT=332, BATTERY_TOP=69, BATTERY_WIDTH=76, BATTERY_HEIGHT=19;
inline int batteryPercent(int value) { return value>=0 && value<=100 ? value : -1; }
