#pragma once
// The extra card is local UI only; never use its index for agent arrays or wire IDs.
inline int agentCardStep(int current,int direction,const bool* enabled,int count,bool showOff) {
 bool any=false;for(int i=0;i<count;++i)any=any||enabled[i];
 int n=current;
 for(int i=0;i<=count;++i) {
  n=(n+(direction>0?1:count))%(count+1);
  if(n==count || showOff || !any || enabled[n])return n;
 }
 return count;
}
