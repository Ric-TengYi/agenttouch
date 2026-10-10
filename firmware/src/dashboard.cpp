#include "dashboard.h"
#include "config.h"
#include "pages.h"
#include <math.h>
#include <vector>
struct Metric { int value=-1; bool partial=false; };
struct Summary { Metric running, unread; int quota=-1; uint32_t at=0, generation=0; bool quotaOk=false; };
struct TaskRow { String title, handle, kind, state; bool unread=false; };
static Summary summaries[2];
static int page=0, pageAgent=-1; // 1 quota, 2 catalogue, 4 selected conversation
static uint32_t serial=0, requested=0, requestedAt=0, selecting=0;
static String cursor, error, token, fullTitle, status;
static std::vector<TaskRow> rows;
static std::vector<String> titleLines;
static int top=0, titleTop=0, readLimit=5;
static bool more=false, loading=false, fetchNext=false, canSend=false;
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
static void wrapTitle() {
  titleLines.clear(); String line;
  for(unsigned int i=0;i<fullTitle.length();) {
    unsigned int next=i+1;
    while(next<fullTitle.length() && (((uint8_t)fullTitle[next]&0xc0)==0x80)) ++next;
    String ch=fullTitle.substring(i,next);
    if(ch=="\n") { titleLines.push_back(line); line=""; }
    else {
      if(line.length() && almanacTextWidthSmall((line+ch).c_str())>305) { titleLines.push_back(line); line=""; }
      line+=ch;
    }
    i=next;
  }
  if(line.length()) titleLines.push_back(line);
  titleTop=0;
}
static Metric metric(JsonVariantConst v) {
  Metric m; const char* q=v["quality"]|"unavailable";
  if(strcmp(q,"ok")==0 || strcmp(q,"partial")==0) {
    if(v["value"].is<int>()) m.value=v["value"].as<int>();
    m.partial=strcmp(q,"partial")==0;
  }
  return m;
}
static void query(JsonDocument& d,const String& next) {
  requested=++serial; requestedAt=millis(); error=""; loading=true; fetchNext=false;
  if(!next.length()) rows.clear();
  d["t"]="tasks_get"; d["v"]=1; d["agent"]=AGENTS[pageAgent].id;
  d["filter"]="catalog"; d["read_limit"]=readLimit;
  d["cursor"]=next; d["request_id"]=String(requested);
}
void dashboardHandle(JsonDocument& d,int idx,uint32_t now) {
  if(idx<0 || idx>1 || (d["v"]|0)!=1) return;
  String t=d["t"]|"";
  if(t=="dashboard") {
    Summary& s=summaries[idx]; uint32_t generation=d["generation"]|0;
    if(pageAgent==idx && page==2 && generation!=s.generation) {
      rows.clear(); cursor=""; error=""; requested=0; loading=false; fetchNext=true;
    }
    s.generation=generation; s.running=metric(d["running"]); s.unread=metric(d["unread"]);
    s.quotaOk=strcmp(d["quota"]["quality"]|"", "ok")==0;
    s.quota=s.quotaOk && d["quota"]["remaining_pct"].is<float>() ?
      constrain((int)roundf(d["quota"]["remaining_pct"].as<float>()),0,100):-1;
    s.at=now;
  } else if(t=="tasks" && page==2 && pageAgent==idx && requested && String(d["request_id"]|"")==String(requested)) {
    loading=false; requested=0; error=d["error"]|"";
    if((d["generation"]|0)!=summaries[idx].generation) error="changed";
    if(error.length()) { rows.clear(); cursor=""; fetchNext=false; return; }
    cursor=d["next_cursor"]|""; more=d["has_more_read"]|false;
    for(JsonObjectConst row:d["list"].as<JsonArrayConst>()) {
      if(rows.size()>=600) { error="limit"; fetchNext=false; cursor=""; return; }
      rows.push_back({String(row["title"]|""),String(row["handle"]|""),String(row["kind"]|"unknown"),String(row["state"]|"unknown"),row["unread"]|false});
    }
    fetchNext=cursor.length();
    if(!fetchNext) top=constrain(top,0,max(0,(int)rows.size()-4));
  } else if(t=="task_selected" && page==4 && pageAgent==idx && selecting && String(d["request_id"]|"")==String(selecting)) {
    selecting=0; token=d["token"]|""; fullTitle=d["title"]|""; error=d["error"]|"";
    status=error.length()?"任务已变化，请返回刷新":"正在打开对话";
    wrapTitle();
    if(d["title_clipped"]|false) titleLines.push_back("标题过长，完整内容请在Mac查看");
  } else if(t=="task_status" && page==4 && pageAgent==idx && token.length() && String(d["token"]|"")==token) {
    String phase=d["phase"]|""; error=d["error"]|"";
    if(error.length()) { status="无法确认目标，请在Mac查看"; canSend=false; }
    else if(phase=="selected") status="按住右键说话，松开后发送";
    else if(phase=="voice_start") { status="正在录入..."; canSend=false; }
    else if(phase=="voice_stop") { status="录入结束，点击发送"; canSend=true; }
    else if(phase=="sent") { status="已发送"; canSend=false; }
  }
}
static String count(Metric m) { return m.value<0?"--":String(m.value); }
bool dashboardOpen() { return page!=0; }
bool dashboardDetail() { return page==4; }
String dashboardVoiceToken() { return page==4?token:String(""); }
void dashboardScroll(int direction) {
  if(page==2) top=constrain(top+direction*3,0,max(0,(int)rows.size()-4));
  if(page==4) titleTop=constrain(titleTop+direction*4,0,max(0,(int)titleLines.size()-7));
}
bool dashboardPoll(JsonDocument& request) {
  if(page==2 && fetchNext && !loading) { query(request,cursor); return true; }
  return false;
}
void dashboardDraw(Arduino_Canvas* c,int idx,bool blocked,uint32_t now) {
  if(blocked || idx!=pageAgent) { page=0; token=""; canSend=false; fetchNext=false; }
  if(idx<0 || idx>1 || blocked) return;
  Summary s=summaries[idx];
  if(!s.at || (int32_t)(now-s.at)>30000) {
    s.quota=-1; s.running.value=s.unread.value=-1;
    rows.clear(); cursor=""; error="stale"; requested=0; fetchNext=false;
    if(page==4) { token=""; canSend=false; status="连接已过期，请返回刷新"; }
  }
  if(loading && (int32_t)(now-requestedAt)>10000) { loading=fetchNext=false; error="timeout"; requested=0; }
  if(selecting && (int32_t)(now-requestedAt)>10000) { selecting=0; status="选择超时，请返回刷新"; }
  if(page) {
    c->fillScreen(0); text(c,185,85,page==1?"7日额度":page==4?"对话":"任务");
    if(page==1) {
      text(c,200,205,s.quota<0?"--":String(s.quota)+"%",AGENTS[idx].color);
      text(c,100,280,"缺失或过期时显示 --",0x8410);
    } else if(page==4) {
      for(int i=0;i<7 && titleTop+i<(int)titleLines.size();++i) text(c,82,130+i*25,titleLines[titleTop+i]);
      if(titleLines.size()>7) text(c,150,315,"上下滑动查看标题",0x8410);
      text(c,82,350,status, error.length()?0xfd20:0x8410);
      if(canSend) text(c,215,401,"发送",0x07e0);
      text(c,315,401,"刷新");
    } else {
      for(int i=0;i<4 && top+i<(int)rows.size();++i) {
        const TaskRow& r=rows[top+i]; int y=112+i*56;
        uint16_t color=r.kind=="running"?0x114b:r.kind=="unread"?0x7b00:0x2945;
        c->fillRoundRect(74,y,332,51,6,color);
        text(c,82,y+21,fit(r.title,303));
        String label=r.state=="waiting"?"待确认":r.kind=="running"?"进行中":r.kind=="unread"?"未读":r.kind=="read"?"已读":"阅读状态未知";
        if(r.kind=="running" && r.unread) label+=" / 未读";
        text(c,82,y+43,label,0xce59);
      }
      if(rows.empty()) text(c,95,205,error=="changed"?"数据已更新，请刷新":error.length()?"数据暂不可用":loading?"加载中":"暂无任务",0x8410);
      if(more && !loading && !error.length()) text(c,215,365,"更多");
      else text(c,140,365,loading?"加载中":"上下滑动查看任务",0x8410);
      text(c,315,401,"刷新");
    }
    text(c,110,401,"返回"); return;
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
bool dashboardTap(int x,int y,int idx,JsonDocument& request) {
  if(idx<0 || idx>1) return false;
  if(page && pageAgent==idx) {
    if(page==4) {
      if(y>375 && x>=180 && x<285 && canSend && token.length()) {
        request["t"]="key"; request["k"]="enter"; request["target"]=token; request["agent"]=AGENTS[idx].id;
        canSend=false; status="正在发送...";
      } else if(y>375 && x>=285 && token.length()) {
        selecting=++serial; requestedAt=millis(); status="正在刷新..."; canSend=false;
        request["t"]="task_select"; request["target"]=token; request["agent"]=AGENTS[idx].id; request["request_id"]=String(selecting); token="";
      } else if(y>375 && (x<180 || (x>=285 && !token.length()))) {
        request["t"]="task_cancel"; token=""; canSend=false; selecting=0; page=2; top=0; rows.clear(); cursor=""; fetchNext=true;
      }
    } else if(y>375 && x>=285 && page==2) { top=0; query(request,""); }
    else if(y>375 && x<180) { page=0; cursor=""; fetchNext=false; }
    else if(page==2 && y>=345 && y<=375 && more && !loading && !error.length()) { readLimit+=5; query(request,""); }
    else if(page==2 && y>=112 && y<336 && !loading && !error.length()) {
      int index=top+(y-112)/56;
      if(index<(int)rows.size()) {
        page=4; token=""; canSend=false; fullTitle=rows[index].title; wrapTitle(); status="正在选择...";
        selecting=++serial; requestedAt=millis();
        request["t"]="task_select"; request["agent"]=AGENTS[idx].id; request["handle"]=rows[index].handle; request["request_id"]=String(selecting);
      }
    }
    return true;
  }
  if(y<76 || y>153 || x<74 || x>405) return false;
  pageAgent=idx; cursor=""; rows.clear(); requested=0; top=0; readLimit=5; token="";
  page=x<150?1:2;
  if(page==2) query(request,"");
  return true;
}

void dashboardInspect(JsonDocument& response) {
  response["t"]="dashboard_state"; response["page"]=page; response["rows"]=(int)rows.size();
  response["read_limit"]=readLimit; response["top"]=top; response["more"]=more;
  response["loading"]=loading || fetchNext; response["error"]=error;
}
