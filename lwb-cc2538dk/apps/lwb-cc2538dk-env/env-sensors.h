#ifndef ENV_SENSORS_H_
#define ENV_SENSORS_H_

#include <stdint.h>

/* Temp/RH sensor selection for ENV_TEMP_RH_SENSOR_CONF. */
#define ENV_TEMP_RH_SENSOR_AUTO      0
#define ENV_TEMP_RH_SENSOR_SI7021    1
#define ENV_TEMP_RH_SENSOR_HDC1080   2

void env_sensors_init(void);

/* Generic API used by application layer. */
uint8_t env_read_temp_rh(int16_t *t_x10, uint16_t *rh_x10);
uint16_t env_read_light_raw(void);
uint8_t env_read_bmp180(int16_t *t_x10, int32_t *p_pa);

/* Runtime information for OLED/debug. */
uint8_t env_temp_rh_sensor_type(void);
const char *env_temp_rh_sensor_name(void);

/* Backward-compatible alias for old application code. */
uint8_t env_read_hdc1080(int16_t *t_x10, uint16_t *rh_x10);

#endif /* ENV_SENSORS_H_ */
