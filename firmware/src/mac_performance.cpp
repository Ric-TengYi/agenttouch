#include "mac_performance.h"
#include "pages.h"
#include "face.h"
#include <esp_heap_caps.h>
#include <math.h>
struct Perf {
 double cpu=-1,mem=-1,used=-1,total=-1,free=-1,diskTotal=-1,rx=-1,tx=-1,read=-1,write=-1;
 String status="unavailable";uint32_t at=0;
} static perf;
static bool active=false;
static double metric(JsonVariantConst v,bool percent=false) {
 if(v.is<bool>() || !v.is<double>())return -1;
 double value=v.as<double>();return isfinite(value) && value>=0 && (!percent || value<=100)?value:-1;
}
void macPerformanceHandle(JsonDocument& d,uint32_t now) {
 if((d["v"]|0)!=1)return;
 perf.cpu=metric(d["cpu_pct"],true);perf.mem=metric(d["memory_pct"],true);
 perf.used=metric(d["memory_used"]);perf.total=metric(d["memory_total"]);
 perf.free=metric(d["disk_free"]);perf.diskTotal=metric(d["disk_total"]);
 perf.rx=metric(d["net_rx"]);perf.tx=metric(d["net_tx"]);
 perf.read=metric(d["disk_read"]);perf.write=metric(d["disk_write"]);
 perf.status=d["status"]|"unavailable";perf.at=now;
}
void macPerformanceInvalidate(){active=false;}
static String amount(double value,bool speed=false) {
 if(value<0)return "--";
 char s[32];
 if(speed) {
  if(value>=1048576)snprintf(s,sizeof(s),"%.1fM/s",value/1048576);
  else snprintf(s,sizeof(s),"%.0fK/s",value/1024);
 } else snprintf(s,sizeof(s),"%.1f GB",value/1073741824);
 return String(s);
}
static void label(Arduino_Canvas* c,int x,int y,const String& s,bool big=false,uint16_t color=0xffff) {
 if(big)almanacPrint(c,x,y,s.c_str(),color,0);else almanacPrintSmall(c,x,y,s.c_str(),color,0);
}
static void centered(Arduino_Canvas* c,int y,const String& s,bool big=false,uint16_t color=0xffff) {
 int w=big?almanacTextWidth(s.c_str()):almanacTextWidthSmall(s.c_str());label(c,(480-w)/2,y,s,big,color);
}
static void bar(Arduino_Canvas* c,int x,int y,int width,double pct) {
 c->fillRoundRect(x,y,width,9,4,0x2945);
 if(pct>=0)c->fillRoundRect(x,y,max(1,(int)(width*pct/100)),9,4,pct>=85?0xfd20:0x4dff);
}
void macPerformanceRender(Arduino_Canvas* c,Arduino_GFX* output,uint32_t now,int rotation,
                         int battery,bool charging,bool pinned,bool bright,uint16_t accent,
                         const char* toast,float toastK) {
 static String previous;static uint16_t* shown=nullptr;
 bool stale=perf.at && (int32_t)(now-perf.at)>10000;
 bool valid=perf.at && !stale;
 String key=String(rotation)+":"+String(perf.at)+":"+String(stale)+":"+String(battery)+String(charging)+String(pinned)+String(bright)+String(toastK,2)+String(toast);
 if(active && key==previous)return;
 c->setRotation(rotation);c->fillScreen(0);
 centered(c,64,"Mac 性能",true);
 double cpu=valid?perf.cpu:-1,mem=valid?perf.mem:-1;
 label(c,76,126,"CPU",true);label(c,320,126,cpu<0?String("--"):String(cpu,0)+"%",true,cpu>=85?0xfd20:0xffff);
 bar(c,76,138,328,cpu);
 label(c,76,183,"内存",true);label(c,320,183,mem<0?String("--"):String(mem,0)+"%",true,mem>=85?0xfd20:0xffff);
 bar(c,76,195,328,mem);
 centered(c,229,valid?amount(perf.used)+" / "+amount(perf.total):String("-- / --"));
 centered(c,270,"磁盘剩余 "+(valid?amount(perf.free)+" / "+amount(perf.diskTotal):String("--")));
 centered(c,310,"网络 上 "+amount(valid?perf.tx:-1,true)+"  下 "+amount(valid?perf.rx:-1,true));
 centered(c,350,"磁盘 读 "+amount(valid?perf.read:-1,true)+"  写 "+amount(valid?perf.write:-1,true));
 String status=!perf.at?"等待 Mac 数据":stale?"数据已过期":perf.status=="ok"?"实时 · 每2秒更新":perf.status=="warming"?"首次采样中...":perf.status=="partial"?"部分数据暂不可用":"数据暂不可用";
 centered(c,393,status,false,stale?0xfd20:0x8410);
 centered(c,421,"左右滑动切换 Agent",false,0x8410);

 if(pinned)drawPagePin(c,bright,accent);
 drawPillToast(c,toast,toastK,368);
 drawBatteryBadge(c,battery,charging);
 c->setRotation(0);
 if(!shown)shown=(uint16_t*)heap_caps_malloc(480*480*2,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
 uint16_t* pixels=c->getFramebuffer();
 if(!active || !shown)c->flush();
 else for(int y=0;y<480;) {
  if(memcmp(pixels+y*480,shown+y*480,960)==0){++y;continue;}
  int first=y++;while(y<480 && memcmp(pixels+y*480,shown+y*480,960)!=0)++y;
  output->draw16bitRGBBitmap(0,first,pixels+first*480,480,y-first);
 }
 if(shown)memcpy(shown,pixels,480*480*2);
 previous=key;active=true;
}
