#include "dashboard.h"
#include "config.h"
#include "pages.h"
#include <math.h>
struct Metric { int value=-1; bool partial=false; };
struct Summary { Metric running, unread; int quota=-1; uint32_t at=0, generation=0; bool quotaOk=false; };
static Summary summaries[2];
static int page=0, pageAgent=-1; // 1 quota, 2 running, 3 unread
static uint32_t serial=0, requested=0, requestedAt=0;
static String cursor, error;
static String titles[4], labels[4];
static int rows=0;
static bool complete=false, loading=false;
static void text(Arduino_Canvas* c,int x,int y,const String& s,uint16_t color=0xffff) {
  almanacPrintSmall(c,x,y,s.c_str(),color,0);
}
static String fit(String s,int width) {
  bool clipped=false;
  while(s.length() && almanacTextWidthSmall(s.c_str())>width) {
    int i=s.length()-1;
    while(i>0 && (((uint8_t)s[i]&0xc0)==0x80)) --i;
    s.remove(i); clipped=true;
  }
  return s+(clipped?"...":"");
}
static Metric metric(JsonVariantConst v) {
  Metric m;
  const char* q=v["quality"]|"unavailable";
  if(strcmp(q,"ok")==0 || strcmp(q,"partial")==0) {
    if(v["value"].is<int>()) m.value=v["value"].as<int>();
    m.partial=strcmp(q,"partial")==0;
  }
  return m;
}
void dashboardHandle(JsonDocument& d,int idx,uint32_t now) {
  if(idx<0 || idx>1 || (d["v"]|0)!=1) return;
  const char* t=d["t"]|"";
  if(strcmp(t,"dashboard")==0) {
    Summary& s=summaries[idx];
    uint32_t generation=d["generation"]|0;
    if(pageAgent==idx && page>1 && generation!=s.generation) {
      rows=0; cursor=""; error="changed"; requested=0; loading=false;
    }
    s.generation=generation;
    s.running=metric(d["running"]); s.unread=metric(d["unread"]);
    s.quotaOk=strcmp(d["quota"]["quality"]|"", "ok")==0;
    s.quota=s.quotaOk && d["quota"]["remaining_pct"].is<float>() ?
      constrain((int)roundf(d["quota"]["remaining_pct"].as<float>()),0,100):-1;
    s.at=now;
  } else if(strcmp(t,"tasks")==0 && pageAgent==idx && requested && String(d["request_id"]|"")==String(requested) &&
            (d["generation"]|0)==summaries[idx].generation) {
    loading=false; rows=0; cursor=d["next_cursor"]|""; error=d["error"]|"";
    complete=d["complete"]|false;
    for(JsonObjectConst row:d["list"].as<JsonArrayConst>()) {
      if(rows>=4) break;
      titles[rows]=String(row["title"]|"");
      labels[rows]=String(row["host_label"]|"")+" / "+String(row["state"]|"");
      ++rows;
    }
  }
}
static String count(Metric m) { return m.value<0?"--":String(m.value); }
void dashboardDraw(Arduino_Canvas* c,int idx,bool blocked,uint32_t now) {
  if(blocked || idx!=pageAgent) { if(blocked || idx!=pageAgent) page=0; }
  if(idx<0 || idx>1 || blocked) return;
  Summary s=summaries[idx];
  if(!s.at || (int32_t)(now-s.at)>30000) { s.quota=-1; s.running.value=s.unread.value=-1; rows=0; cursor=""; error="stale"; requested=0; }
  if(loading && (int32_t)(now-requestedAt)>10000) { loading=false; error="timeout"; requested=0; }
  if(page) {
    c->fillScreen(0);
    text(c,120,85,page==1?"7日剩余额度":page==2?"已确认进行中":"原生未读（本地）");
    if(page==1) {
      text(c,200,205,s.quota<0?"--":String(s.quota)+"%",AGENTS[idx].color);
      text(c,100,280,"缺失或过期时显示 --",0x8410);
    } else {
      for(int i=0;i<rows;++i) {
        text(c,82,145+i*55,fit(titles[i],305));
        text(c,82,166+i*55,fit(labels[i],305),0x8410);
      }
      if(!rows) text(c,105,200,error=="changed"?"数据已更新，请刷新":error.length()?"数据暂不可用":loading?"加载中":"暂无已确认任务",0x8410);
      text(c,116,365,complete?"本地会话":"仅已确认部分",0x8410);
      text(c,215,401,"刷新");
      if(cursor.length()) text(c,295,401,"下一页");
    }
    text(c,110,401,"返回");
    return;
  }
  c->fillRect(74,76,332,76,0);
  for(int r=25;r<=28;++r) c->drawCircle(108,107,r,0x4208);
  if(s.quota>=0) for(int a=0;a<s.quota*360/100;++a) {
    float angle=(a-90)*0.017453293f;
    c->drawLine(108+25*cosf(angle),107+25*sinf(angle),108+28*cosf(angle),107+28*sinf(angle),AGENTS[idx].color);
  }
  text(c,93,115,s.quota<0?"--":String(s.quota),AGENTS[idx].color);
  text(c,155,114,"进行中: "+count(s.running)+"  未读: "+count(s.unread));
}
static void query(JsonDocument& d,int idx,const String& next) {
  requested=++serial; requestedAt=millis(); rows=0; error=""; loading=true;
  d["t"]="tasks_get"; d["v"]=1; d["agent"]=AGENTS[idx].id;
  d["filter"]=page==2?"running":"unread";
  d["cursor"]=next; d["request_id"]=String(requested);
}
bool dashboardTap(int x,int y,int idx,JsonDocument& request) {
  if(idx<0 || idx>1) return false;
  if(page && pageAgent==idx) {
    if(y>375 && page>1 && x>=180 && x<=260) query(request,idx,"");
    else if(y>375 && x>260 && cursor.length()) query(request,idx,cursor);
    else if(y>375) { page=0; cursor=""; }
    return true;
  }
  if(y<76 || y>153 || x<74 || x>405) return false;
  pageAgent=idx; cursor=""; rows=0; requested=0;
  page=x<150?1:x<280?2:3;
  if(page>1) query(request,idx,"");
  return true;
}
