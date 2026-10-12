#include <cassert>
#include "../src/dashboard_gesture.h"
int main() {
 TouchReportState touch;
 assert(!touch.update(false,false));
 assert(touch.update(true,true));
 // Once the chip ACK has been consumed, an idle poll is not a release.
 for(int i=0;i<100;++i) assert(touch.update(false,false));
 assert(touch.update(true,true));
 assert(!touch.update(true,false));
 assert(!touch.update(false,true));
 DashboardGesture g;
 g.begin(200,300); assert(g.move(201,295)==0 && !g.consumed);
 assert(g.move(202,270)==1 && g.consumed);
 assert(g.move(202,230)==1); assert(g.move(202,232)==0);
 assert(g.move(202,280)==-1);
 g.begin(200,200); assert(g.move(245,204)==0 && g.consumed);
 g.begin(200,200); assert(g.move(200,220)==0 && g.consumed);
 assert(g.move(200,230)==-1);
 g.begin(120,200); g.move(210,205); assert(g.back(210,205));
 assert(!g.back(190,205)); assert(!g.back(210,260));
 assert(!g.back(20,200));
 g.begin(120,200); g.move(120,150); assert(!g.back(260,150));
 // The same physical viewed-up gesture must scroll toward later rows in
 // every orientation, including both quarter turns.
 int native[][4]={{240,240,240,180},{239,240,299,240},
                 {239,239,239,299},{240,239,180,239}};
 for(int rot=0;rot<4;++rot) {
   int sx,sy,ex,ey;
   dashboardPoint(native[rot][0],native[rot][1],rot,sx,sy);
   dashboardPoint(native[rot][2],native[rot][3],rot,ex,ey);
   g.begin(sx,sy); assert(g.move(ex,ey)==1);
 }
}
