#include <cassert>
#include "../src/battery_badge.h"
int main() {
 assert(batteryPercent(-1)==-1); assert(batteryPercent(255)==-1);
 assert(batteryPercent(0)==0); assert(batteryPercent(100)==100);
 for(int x:{BATTERY_LEFT,BATTERY_LEFT+BATTERY_WIDTH})
  for(int y:{BATTERY_TOP,BATTERY_TOP+BATTERY_HEIGHT})
   assert((x-240)*(x-240)+(y-240)*(y-240)<=240*240);
}
