#pragma once
#include <cstdlib>

struct TouchReportState {
  bool down=false;
  bool update(bool freshReport,bool pressed) {
    if(freshReport) down=pressed;
    return down;
  }
};

inline void dashboardPoint(int x,int y,int rotation,int& px,int& py) {
  switch(rotation&3) {
    case 1: px=y; py=479-x; break;
    case 2: px=479-x; py=479-y; break;
    case 3: px=479-y; py=x; break;
    default: px=x; py=y; break;
  }
}

// Coordinates are in the dashboard's displayed frame, not legacy face axes.
struct DashboardGesture {
  int startX=0, startY=0, anchorY=0;
  bool consumed=false, dragging=false;
  void begin(int x,int y) { startX=x; startY=anchorY=y; consumed=dragging=false; }
  bool back(int x,int y) const {
    int dx=x-startX, dy=y-startY;
    return !dragging && dx>=80 && dx>=2*std::abs(dy);
  }
  int move(int x,int y) {
    int dx=x-startX, dy=y-startY;
    if(std::abs(dx)>12 || std::abs(dy)>12) consumed=true;
    if(!dragging) {
      if(std::abs(dy)<24 || 5*std::abs(dy)<6*std::abs(dx)) return 0;
      dragging=true; anchorY=y; return dy<0?1:-1;
    }
    int travel=y-anchorY;
    if(std::abs(travel)<40) return 0;
    int steps=-travel/40; anchorY-=steps*40; return steps;
  }
};
