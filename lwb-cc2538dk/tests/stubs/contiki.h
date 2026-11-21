#ifndef TEST_CONTIKI_H
#define TEST_CONTIKI_H
#include <stdint.h>
typedef uint32_t rtimer_clock_t;
struct rtimer { uint32_t time; };
#define RTIMER_SECOND 32768UL
#define MIN(a,b) ((a) < (b) ? (a) : (b))
#define MAX(a,b) ((a) > (b) ? (a) : (b))
#endif
