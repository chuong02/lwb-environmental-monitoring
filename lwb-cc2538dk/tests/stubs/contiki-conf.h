#ifndef TEST_CONTIKI_CONF_H
#define TEST_CONTIKI_CONF_H
/* Host-side tests use real Contiki list/memb and LWB codec/scheduler code. */
#define CC_CONF_INLINE inline
#define CC_CONF_FUNCTION_POINTER_ARGS 1
#endif
