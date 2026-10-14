#include <cassert>
#include "../src/agent_cards.h"
int main(){
 bool on[]={true,true,false,false,false};
 assert(agentCardStep(0,1,on,5,false)==1);
 assert(agentCardStep(1,1,on,5,false)==5);
 assert(agentCardStep(5,1,on,5,false)==0);
 assert(agentCardStep(0,-1,on,5,false)==5);
 assert(agentCardStep(5,-1,on,5,false)==1);
 assert(agentCardStep(4,1,on,5,true)==5);
 bool one[]={false,true,false,false,false};
 assert(agentCardStep(1,1,one,5,false)==5);
 assert(agentCardStep(5,1,one,5,false)==1);
 bool off[]={false,false,false,false,false};
 assert(agentCardStep(4,1,off,5,false)==5);
 assert(agentCardStep(5,1,off,5,false)==0);
}
