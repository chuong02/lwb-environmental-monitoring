#ifndef ENV_OLED_H_
#define ENV_OLED_H_

#include <stdint.h>
#include "env-packet.h"

void env_oled_init(void);
void env_oled_clear(void);
void env_oled_show_text(const char *line0, const char *line1, const char *line2);
void env_oled_show_status(uint16_t node_id, uint8_t is_host);
void env_oled_show_env(const env_packet_t *p);

#endif /* ENV_OLED_H_ */
