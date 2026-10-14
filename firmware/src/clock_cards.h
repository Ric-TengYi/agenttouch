#pragma once
#include <stdint.h>
enum ClockView : uint8_t { CV_POD=0, CV_CLOCK=1, CV_NP=2 };
inline uint8_t clockCardStep(uint8_t current,int direction) {
 const uint8_t cards[]={CV_POD,CV_CLOCK,CV_NP};
 int at=1;for(int i=0;i<3;++i) if(cards[i]==current) at=i;
 int next=at+direction;if(next<0)next=0;if(next>2)next=2;return cards[next];
}
