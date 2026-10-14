#include <cassert>
#include "../src/clock_cards.h"
int main(){
 assert(clockCardStep(CV_CLOCK,1)==CV_NP);assert(clockCardStep(CV_NP,-1)==CV_CLOCK);
 assert(clockCardStep(CV_CLOCK,-1)==CV_POD);
 assert(clockCardStep(CV_NP,1)==CV_NP);assert(clockCardStep(CV_POD,-1)==CV_POD);
}
