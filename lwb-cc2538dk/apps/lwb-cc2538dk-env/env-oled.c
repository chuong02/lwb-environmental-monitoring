#include "contiki.h"
#include "env-oled.h"
#include "env-sensors.h"
#include "ssd1306.h"

#include <stdio.h>
#include <stdlib.h>

static void
draw_line(uint8_t y, const char *s)
{
  ssd1306_draw_text(0, y, s, 1);
}

void
env_oled_clear(void)
{
  ssd1306_clear();
  ssd1306_display();
}

void
env_oled_init(void)
{
  ssd1306_init();
  env_oled_show_text("LWB ENV", "OLED OK", "WAIT SENSOR");
}

void
env_oled_show_text(const char *line0, const char *line1, const char *line2)
{
  ssd1306_clear();
  draw_line(0, line0);
  draw_line(16, line1);
  draw_line(32, line2);
  ssd1306_display();
}

void
env_oled_show_status(uint16_t node_id, uint8_t is_host)
{
  char line[24];

  ssd1306_clear();
  snprintf(line, sizeof(line), "NODE:%u", (unsigned)node_id);
  draw_line(0, line);
  draw_line(16, is_host ? "MODE:HOST" : "MODE:SOURCE");
  draw_line(32, "WAIT SENSOR");
  ssd1306_display();
}

void
env_oled_show_env(const env_packet_t *p)
{
  char line[24];
  const char *temp_rh_name;
  long pressure_hpa_x10;
  int32_t temp_value;

  temp_rh_name = env_temp_rh_sensor_name();
  ssd1306_clear();

  /* Line 1: selected Temp/RH sensor, auto-detected at runtime. */
  if(p->hdc_temp_x10 == ENV_INVALID_TEMP_X10 ||
     p->hdc_hum_x10 == ENV_INVALID_U16) {
    snprintf(line, sizeof(line), "%s:--", temp_rh_name);
  } else {
    temp_value = p->hdc_temp_x10;

    if(temp_value < 0) {
      temp_value = -temp_value;
      snprintf(line, sizeof(line), "%s:-%ld.%ldC %u.%u%%",
               temp_rh_name,
               (long)(temp_value / 10),
               (long)(temp_value % 10),
               p->hdc_hum_x10 / 10,
               p->hdc_hum_x10 % 10);
    } else {
      snprintf(line, sizeof(line), "%s:%ld.%ldC %u.%u%%",
               temp_rh_name,
               (long)(temp_value / 10),
               (long)(temp_value % 10),
               p->hdc_hum_x10 / 10,
               p->hdc_hum_x10 % 10);
    }
  }
  draw_line(0, line);

  /* Line 2: light. */
  if(p->light_raw == ENV_INVALID_U16) {
    snprintf(line, sizeof(line), "TSL2561:--");
  } else {
    snprintf(line, sizeof(line), "TSL2561:%u", p->light_raw);
  }
  draw_line(16, line);

  /* Line 3: pressure. */
  if(p->pressure_pa == ENV_INVALID_PRESSURE_PA) {
    snprintf(line, sizeof(line), "BMP180:--");
  } else {
    pressure_hpa_x10 = p->pressure_pa / 10;
    snprintf(line, sizeof(line), "BMP180:%ld.%ldhPa",
             pressure_hpa_x10 / 10,
             labs(pressure_hpa_x10 % 10));
  }
  draw_line(32, line);

  /* Line 4: show node only. Packet sequence remains in UART/payload. */
  snprintf(line, sizeof(line), "NODE:%u", (unsigned)p->node_id);
  draw_line(48, line);

  ssd1306_display();
}
