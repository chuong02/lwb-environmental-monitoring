/*
 * Minimal node-id implementation for CC2538DK LWB examples.
 * This replaces the original platform/zoul/node-id.c dependency.
 */

#include "sys/node-id.h"
#include "contiki-conf.h"

#if WITH_TINYOS_AUTO_IDS
unsigned short TOS_NODE_ID = 0x1122;
#endif

unsigned short node_id = 0;

void
node_id_restore(void)
{
#if WITH_TINYOS_AUTO_IDS
  node_id = TOS_NODE_ID;
#endif
}

void
node_id_burn(unsigned short id)
{
  node_id = id;
}
