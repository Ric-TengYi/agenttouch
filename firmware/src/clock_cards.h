#pragma once
#include <stdint.h>
enum ClockView : uint8_t { CV_POD=0, CV_CLOCK=1, CV_NP=2, CV_PERF=3 };
inline uint8_t clockCardStep(uint8_t current,int direction) {
 const uint8_t cards[]={CV_POD,CV_CLOCK,CV_PERF,CV_NP};
 int at=1;for(int i=0;i<4;++i) if(cards[i]==current) at=i;
 int next=at+direction;if(next<0)next=0;if(next>3)next=3;return cards[next];
}
