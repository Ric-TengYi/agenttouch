#include "dashboard.h"
#include "config.h"
#include "pages.h"
#include <math.h>
#include <vector>
#include <esp_heap_caps.h>
struct Metric { int value=-1; bool partial=false; };
struct Summary { Metric running, unread; int quota=-1; uint32_t at=0, generation=0; bool quotaOk=false; };
struct TaskRow { String title, handle, kind, state; bool unread=false; };
static Summary summaries[2];
static int page=0, pageAgent=-1; // 1 quota, 2 catalogue, 4 selected conversation
static uint32_t serial=0, requested=0, requestedAt=0, selecting=0, voiceSerial=0;
static String cursor, error, token, fullTitle, status, previewText, previewRevision, voiceId, conversationText;
static std::vector<TaskRow> rows, incoming;
static bool commitPending=false, touchHeld=false, forceFull=true;
static uint32_t requestGeneration=0, fullFrames=0, partialFrames=0;
static std::vector<String> titleLines;
static int top=0, titleTop=0, readLimit=5;
static bool more=false, loading=false, fetchNext=false, canSend=false, voiceRecording=false, previewConsumed=false;
// Bounds follow the round panel, reserving 8 px inside its radius.
static const int PREVIEW_LINES=8, FOOTER_TOP=390;
static const int ROW_TOP=128, ROW_STEP=60, ROW_HEIGHT=52, ROW_LEFT=32, ROW_WIDTH=416;
static int inset(int top,int bottom) {
  int dy=max(abs(top-240),abs(bottom-240));
  return (int)ceilf(240-sqrtf(max(0.0f,232.0f*232.0f-dy*dy)));
}
static int lineY(int line) { return 114+line*32; }
static int lineLeft(int line) { return inset(lineY(line)-26,lineY(line)+3)+4; }
static int lineWidth(int line) { return 480-2*lineLeft(line); }
static void text(Arduino_Canvas* c,int x,int y,const String& s,uint16_t color=0xffff,
                 bool large=false,uint16_t bg=0) {
  if(large) almanacPrint(c,x,y,s.c_str(),color,bg);
  else almanacPrintSmall(c,x,y,s.c_str(),color,bg);
}
static int width(const String& s,bool large) {
  return large?almanacTextWidth(s.c_str()):almanacTextWidthSmall(s.c_str());
}
static void centered(Arduino_Canvas* c,int y,const String& s,uint16_t color=0xffff,bool large=true) {
  text(c,(480-width(s,large))/2,y,s,color,large);
}
static String fit(String s,int maxWidth,bool large=true) {
  s.replace("\n"," "); s.replace("\r"," ");
  if(width(s,large)<=maxWidth) return s;
  while(s.length() && width(s+"...",large)>maxWidth) {
    int i=s.length()-1;
    while(i>0 && (((uint8_t)s[i]&0xc0)==0x80)) --i;
    s.remove(i);
  }
  return s+"...";
}
static void wrapTitle() {
  titleLines.clear(); String line; const String& source=previewText.length()?previewText:conversationText;
  for(unsigned int i=0;i<source.length();) {
    unsigned int next=i+1;
    while(next<source.length() && (((uint8_t)source[next]&0xc0)==0x80)) ++next;
    String ch=source.substring(i,next);
    if(ch=="\n") { titleLines.push_back(line); line=""; }
    else {
      int maxWidth=lineWidth(titleLines.size()%PREVIEW_LINES);
      if(line.length() && width(line+ch,true)>maxWidth) { titleLines.push_back(line); line=""; }
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
  if(!next.length()) { incoming.clear(); commitPending=false; requestGeneration=summaries[pageAgent].generation; }
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
      incoming.clear(); cursor=""; error=""; requested=0; loading=false; fetchNext=true; commitPending=false;
    }
    s.generation=generation; s.running=metric(d["running"]); s.unread=metric(d["unread"]);
    s.quotaOk=strcmp(d["quota"]["quality"]|"", "ok")==0;
    s.quota=s.quotaOk && d["quota"]["remaining_pct"].is<float>() ?
      constrain((int)roundf(d["quota"]["remaining_pct"].as<float>()),0,100):-1;
    s.at=now;
  } else if(t=="tasks" && page==2 && pageAgent==idx && requested && String(d["request_id"]|"")==String(requested)) {
    loading=false; requested=0; error=d["error"]|"";
    if((d["generation"]|0)!=requestGeneration || requestGeneration!=summaries[idx].generation) error="changed";
    if(error.length()) { incoming.clear(); cursor=""; fetchNext=false; return; }
    cursor=d["next_cursor"]|""; more=d["has_more_read"]|false;
    for(JsonObjectConst row:d["list"].as<JsonArrayConst>()) {
      if(incoming.size()>=600) { error="limit"; fetchNext=false; cursor=""; return; }
      String handle=row["stable_handle"].is<const char*>()?String(row["stable_handle"].as<const char*>()):String(row["handle"]|"");
      incoming.push_back({String(row["title"]|""),handle,String(row["kind"]|"unknown"),String(row["state"]|"unknown"),row["unread"]|false});
    }
    fetchNext=cursor.length();
    if(!fetchNext) commitPending=true;
  } else if(t=="task_selected" && page==4 && pageAgent==idx && selecting && String(d["request_id"]|"")==String(selecting)) {
    previewText=""; previewRevision=""; voiceId=""; voiceRecording=false; canSend=false;
    conversationText="正在读取最近消息..."; selecting=0; token=d["token"]|""; fullTitle=d["title"]|""; error=d["error"]|"";
    status=error.length()?"任务已变化，请返回刷新":"正在打开对话";
    wrapTitle();
  } else if(t=="task_detail" && page==4 && pageAgent==idx && token.length() && String(d["token"]|"")==token) {
    String question=d["question"]|"", answer=d["answer"]|"";
    String next=String(d["error"]|"").length()?"消息暂不可用":question.length()?"你问：\n"+question+"\n\n助手：\n"+(answer.length()?answer:String("等待回复...")):String("暂无消息");
    if(d["clipped"]|false) next+="\n内容较长，完整内容请在Mac查看";
    if(next!=conversationText) { conversationText=next; if(!previewText.length()) { int oldTop=titleTop; wrapTitle(); titleTop=constrain(oldTop,0,max(0,((int)titleLines.size()-1)/PREVIEW_LINES*PREVIEW_LINES)); } }
  } else if(t=="task_status" && page==4 && pageAgent==idx && token.length() && String(d["token"]|"")==token) {
    String phase=d["phase"]|"";
    if(pageAgent==1 && phase!="selected" && String(d["voice_id"]|"")!=voiceId) return;
    if(pageAgent==1 && ((phase=="voice_start" && !voiceRecording) ||
        (phase=="voice_stop" && previewRevision.length()) ||
        ((phase=="preview_ready" || phase=="preview_wait") && (voiceRecording || previewConsumed)))) return;
    error=d["error"]|"";
    if(error.length()) {
      canSend=false; previewRevision="";
      if(error=="preview_changed") previewConsumed=false;
      if(pageAgent==1) { previewText=""; wrapTitle(); }
      status=error=="preview_changed"?"内容已变化，正在更新预览":error=="voice_not_ready"?"请等待转写和预览":error=="preview_too_long"?"内容过长，请在Mac确认发送":error=="send_on_mac"?"请在Codex输入框确认并发送":error=="composer_unavailable"?"请检查Codex输入框":error=="preview_empty"?"预览为空，请在Mac录入":error=="preview_unavailable"?(pageAgent==1?"未读取到草稿，请在Mac查看":"请检查Mac语音预览框"):error=="delivery_unconfirmed"?"发送未确认，请在Mac查看":"目标已变更，请返回刷新";
      canSend=pageAgent!=1 && error=="preview_empty";
    }
    else if(phase=="selected") status=pageAgent==1?"按住右键，在Codex录入":"按住右键说话，松开后发送";
    else if(phase=="voice_start") { previewText=""; previewRevision=""; wrapTitle(); status=pageAgent==1?"正在Codex输入框录入...":"正在录入..."; canSend=false; }
    else if(phase=="voice_stop") { status=pageAgent==1?"正在转写，请稍候...":"录入结束，点击发送"; canSend=pageAgent!=1; }
    else if(phase=="preview_ready" && pageAgent==1) {
      previewText=d["text"]|""; previewRevision=d["revision"]|""; wrapTitle();
      canSend=previewText.length() && previewRevision.length(); status="确认内容后点击发送";
    }
    else if(phase=="send_requested") { previewText=""; previewRevision=""; wrapTitle(); status="已触发发送，可继续说话"; canSend=false; }
    else if(phase=="sent") { previewText=""; previewRevision=""; wrapTitle(); status="已发送，可继续说话"; canSend=false; }
  }
}
static String count(Metric m) { return m.value<0?"--":String(m.value); }
bool dashboardOpen() { return page!=0; }
bool dashboardDetail() { return page==4; }
void dashboardVoiceBegin() {
  if(page!=4) return;
  voiceRecording=true; previewConsumed=false; voiceId=String(++voiceSerial);
  canSend=false; previewText=""; previewRevision=""; wrapTitle();
  status=pageAgent==1?"正在录音...":"正在录入...";
}
void dashboardVoiceEnd() { voiceRecording=false; }
String dashboardVoiceId() { return voiceId; }
String dashboardVoiceToken() { return page==4?token:String(""); }
void dashboardScroll(int direction) {
  if(page==2) top=constrain(top+direction,0,max(0,(int)rows.size()-4));
  if(page==4) titleTop=constrain(titleTop+direction*PREVIEW_LINES,0,max(0,((int)titleLines.size()-1)/PREVIEW_LINES*PREVIEW_LINES));
}
void dashboardTouchHeld(bool held) { touchHeld=held; }
void dashboardInvalidateFrame() { forceFull=true; }
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
    if(page==4) { token=""; canSend=false; conversationText="消息已过期，请返回刷新"; previewText=""; wrapTitle(); status="连接已过期，请返回刷新"; }
  }
  if(loading && (int32_t)(now-requestedAt)>10000) { loading=fetchNext=false; error="timeout"; requested=0; }
  if(selecting && (int32_t)(now-requestedAt)>10000) { selecting=0; status="选择超时，请返回刷新"; }
  if(page) {
    c->fillScreen(0);
    centered(c,64,page==1?"7日额度":page==4?fit(fullTitle,220):"任务");
    if(page==1) {
      for(int r=84;r<=90;++r) c->drawCircle(240,215,r,0x4208);
      if(s.quota>=0) for(int a=0;a<s.quota*360/100;++a) {
        float angle=(a-90)*0.017453293f;
        c->drawLine(240+84*cosf(angle),215+84*sinf(angle),240+90*cosf(angle),215+90*sinf(angle),AGENTS[idx].color);
      }
      String value=s.quota<0?"--":String(s.quota)+"%";
      c->setFont((const GFXfont*)nullptr); c->setTextSize(4); c->setTextColor(AGENTS[idx].color);
      c->setCursor(240-value.length()*12,201); c->print(value); c->setTextSize(1);
      centered(c,335,"缺失或过期时显示 --",0x8410,false);
    } else if(page==4) {
      for(int i=0;i<PREVIEW_LINES && titleTop+i<(int)titleLines.size();++i)
        text(c,lineLeft(i),lineY(i),titleLines[titleTop+i],0xffff,true);
      if(titleLines.size()>PREVIEW_LINES)
        centered(c,362,String(titleTop/PREVIEW_LINES+1)+"/"+String((titleLines.size()+PREVIEW_LINES-1)/PREVIEW_LINES)+"  上下滑动",0x8410,false);
      centered(c,386,fit(status,350,false),error.length()?0xfd20:0x8410,false);
    } else {
      for(int i=0;i<4 && top+i<(int)rows.size();++i) {
        const TaskRow& r=rows[top+i]; int y=ROW_TOP+i*ROW_STEP;
        int left=ROW_LEFT, boxWidth=ROW_WIDTH;
        uint16_t color=r.kind=="running"?0x114b:r.kind=="unread"?0x7b00:0x2945;
        c->fillRoundRect(left,y,boxWidth,ROW_HEIGHT,12,color);
        text(c,left+10,y+25,fit(r.title,boxWidth-20),0xffff,true,color);
        String label=r.state=="waiting"?"待确认":r.kind=="running"?"进行中":r.kind=="unread"?"未读":r.kind=="read"?"已读":"阅读状态未知";
        if(r.kind=="running" && r.unread) label+=" / 未读";
        text(c,left+10,y+47,label,0xce59,false,color);
      }
      if(rows.empty()) centered(c,215,error=="changed"?"数据已更新，请刷新":error.length()?"数据暂不可用":loading?"加载中":"暂无任务",0x8410);
      centered(c,386,more && !loading && !error.length()?"更多":loading?"加载中":"上下滑动查看任务",0x8410,false);
    }
    c->drawRoundRect(118,397,76,39,8,0x4208);
    text(c,130,424,"返回",0xffff,true);
    if(page!=1) {
      c->drawRoundRect(286,397,76,39,8,0x4208);
      text(c,298,424,"刷新",0xffff,true);
    }
    if(page==4 && canSend) {
      c->drawRoundRect(202,397,76,39,8,0x07e0);
      text(c,214,424,"发送",0x07e0,true);
    }
    return;
  }
  c->fillRect(48,76,384,76,0);
  for(int r=27;r<=30;++r) c->drawCircle(91,109,r,0x4208);
  if(s.quota>=0) for(int a=0;a<s.quota*360/100;++a) {
    float angle=(a-90)*0.017453293f;
    c->drawLine(91+27*cosf(angle),109+27*sinf(angle),91+30*cosf(angle),109+30*sinf(angle),AGENTS[idx].color);
  }
  String quota=s.quota<0?"--":String(s.quota);
  text(c,91-width(quota,false)/2,116,quota,AGENTS[idx].color);
  String summary="进行中: "+count(s.running)+"  未读: "+count(s.unread);
  text(c,138,118,summary,0xffff,width(summary,true)<=276);
}

bool dashboardTap(int x,int y,int idx,JsonDocument& request) {
  if(idx<0 || idx>1) return false;
  if(page && pageAgent==idx) {
    if(page==4) {
      if(y>=FOOTER_TOP && y<=455 && x>=196 && x<284 && canSend && !voiceRecording && token.length()) {
        request["t"]="key"; request["k"]="enter"; request["revision"]=previewRevision; request["voice_id"]=voiceId; request["target"]=token; request["agent"]=AGENTS[idx].id;
        canSend=false; previewConsumed=true; status="正在发送...";
      } else if(y>=FOOTER_TOP && y<=455 && x>=284 && token.length()) {
        selecting=++serial; requestedAt=millis(); status="正在刷新..."; canSend=false;
        request["t"]="task_select"; request["target"]=token; request["agent"]=AGENTS[idx].id; request["request_id"]=String(selecting); token="";
      } else if(y>=FOOTER_TOP && y<=455 && (x<196 || (x>=284 && !token.length()))) {
        request["t"]="task_cancel"; token=""; canSend=false; selecting=0; page=2; top=0; rows.clear(); cursor=""; fetchNext=true;
      }
    } else if(y>=FOOTER_TOP && y<=455 && x>=284 && page==2) { top=0; forceFull=true; query(request,""); }
    else if(y>=FOOTER_TOP && y<=455 && x<196) { page=0; cursor=""; fetchNext=false; }
    else if(page==2 && y>=370 && y<FOOTER_TOP && more && !loading && !error.length()) { readLimit+=5; query(request,""); }
    else if(page==2 && x>=ROW_LEFT && x<ROW_LEFT+ROW_WIDTH && y>=ROW_TOP && y<ROW_TOP+3*ROW_STEP+ROW_HEIGHT) {
      int index=top+(y-ROW_TOP)/ROW_STEP;
      if((y-ROW_TOP)%ROW_STEP>=ROW_HEIGHT) return true;
      if(index<(int)rows.size()) {
        page=4; token=""; canSend=false; previewText=""; previewRevision=""; fullTitle=rows[index].title; conversationText="正在读取最近消息..."; wrapTitle(); status="正在选择...";
        selecting=++serial; requestedAt=millis();
        request["t"]="task_select"; request["agent"]=AGENTS[idx].id; request["handle"]=rows[index].handle; request["request_id"]=String(selecting);
      }
    }
    return true;
  }
  if(y<76 || y>153 || x<48 || x>431) return false;
  pageAgent=idx; cursor=""; rows.clear(); requested=0; top=0; readLimit=5; token="";
  page=x<130?1:2;
  if(page==2) query(request,"");
  return true;
}

bool dashboardBack(int idx,JsonDocument& request) {
  if(!page || pageAgent!=idx || voiceRecording) return false;
  return dashboardTap(156,424,idx,request);
}

void dashboardInspect(JsonDocument& response) {
  response["t"]="dashboard_state"; response["page"]=page; response["rows"]=(int)rows.size();
  response["read_limit"]=readLimit; response["top"]=top; response["more"]=more;
  response["loading"]=loading || fetchNext; response["error"]=error;
  response["full_frames"]=fullFrames; response["partial_frames"]=partialFrames;
  response["preview"]=previewText.length()>0;
}

// Dashboard pages own their canvas; the animated face must not repaint beneath
// them. Compare native framebuffer rows after rendering so rotations also work.
bool dashboardRenderPage(Arduino_Canvas* c,Arduino_GFX* output,int idx,bool blocked,uint32_t now,int rotation,int batteryPct,bool charging) {
  static bool active=false; static String previous;
  static uint16_t* shown=nullptr;
  if(!page || blocked || idx!=pageAgent) { active=false; previous=""; return false; }
  if(page==2 && commitPending && !touchHeld) {
    rows.swap(incoming); incoming.clear(); commitPending=false;
    top=constrain(top,0,max(0,(int)rows.size()-4));
  }
  String key=String(page)+":"+String(idx)+":"+String(rotation)+":"+String(top)+":"+String(titleTop)+":"+
    String(loading)+":"+String(fetchNext)+":"+String(more)+":"+String(canSend)+":"+error+":"+status+":"+previewText+":"+fullTitle+":"+conversationText;
  key+=":"+String(batteryPct)+":"+String(charging);
  const Summary& sum=summaries[idx];
  key+=":"+String(sum.quota)+":"+String(sum.running.value)+":"+String(sum.unread.value)+":"+String((int32_t)(now-sum.at)>30000);
  key+=":"+String(loading && (int32_t)(now-requestedAt)>10000)+":"+String(selecting && (int32_t)(now-requestedAt)>10000);
  if(page==2) for(int i=top;i<top+4 && i<(int)rows.size();++i) {
    const auto& row=rows[i]; key+="\n"+row.title+"\t"+row.kind+"\t"+row.state+String(row.unread);
  }
  if(active && !forceFull && key==previous) return true;
  c->setRotation(rotation); dashboardDraw(c,idx,blocked,now); drawBatteryBadge(c,batteryPct,charging); c->setRotation(0);
  if(!shown) shown=(uint16_t*)heap_caps_malloc(480*480*sizeof(uint16_t),MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
  uint16_t* pixels=c->getFramebuffer();
  if(!active || forceFull || !shown) { c->flush(); ++fullFrames; }
  else {
    bool changed=false;
    for(int y=0;y<480;) {
      if(memcmp(pixels+y*480,shown+y*480,960)==0) { ++y; continue; }
      int first=y++;
      while(y<480 && memcmp(pixels+y*480,shown+y*480,960)!=0) ++y;
      output->draw16bitRGBBitmap(0,first,pixels+first*480,480,y-first); changed=true;
    }
    if(changed) ++partialFrames;
  }
  if(shown) memcpy(shown,pixels,480*480*sizeof(uint16_t));
  active=true; forceFull=false; previous=key; return true;
}
