#ifndef PROJECT_CONF_H_
#define PROJECT_CONF_H_

/* Energy accounting */
#define ENERGEST_CONF_ON              1

/* CC2538 clock setup */
#define SYS_CTRL_CONF_SYS_DIV         SYS_CTRL_CLOCK_CTRL_SYS_DIV_32MHZ
#define SYS_CTRL_CONF_IO_DIV          SYS_CTRL_CLOCK_CTRL_IO_DIV_32MHZ

/* RF channel for Glossy/LWB */
#ifndef CC2538_RF_CONF_CHANNEL
#define CC2538_RF_CONF_CHANNEL        26
#endif

/* CC2592 external RF front-end
 * Reference mapping: PC3=PA_EN, PC2=LNA_EN, PD2=HGM.
 */
#define CC2592_CONF_ENABLE            1
#define CC2592_CONF_HIGH_GAIN         1
#ifndef CC2592_CONF_TX_POWER_DBM
#define CC2592_CONF_TX_POWER_DBM      7
#endif
#define CC2538_RF_CONF_TX_POWER       0xFF

/* Default software I2C pins: SCL=PB3, SDA=PB4. */
#ifndef I2C_SW_SCL_PIN_CONF
#define I2C_SW_SCL_PIN_CONF          3
#endif

#ifndef I2C_SW_SDA_PIN_CONF
#define I2C_SW_SDA_PIN_CONF          4
#endif

/* 0=auto, 1=SI7021, 2=HDC1080 */
#ifndef ENV_TEMP_RH_SENSOR_CONF
#define ENV_TEMP_RH_SENSOR_CONF      0
#endif

#ifndef ENV_USE_TEMP_RH_CONF
#define ENV_USE_TEMP_RH_CONF         1
#endif

#ifndef ENV_USE_LIGHT_CONF
#define ENV_USE_LIGHT_CONF           1
#endif

#ifndef ENV_USE_BMP180_CONF
#define ENV_USE_BMP180_CONF          1
#endif

/* OLED refresh every 1 second; LWB transmits every 5 seconds. */
#ifndef SENSOR_SAMPLE_PERIOD_CONF
#define SENSOR_SAMPLE_PERIOD_CONF    1
#endif

#ifndef STREAM_IPI_CONF
#define STREAM_IPI_CONF              5
#endif

/* Queue configuration */
#ifndef LWB_CONF_MAX_DATA_BUF_ELEMENTS
#define LWB_CONF_MAX_DATA_BUF_ELEMENTS 16
#endif

/* Disable Coffee FS */
#define COFFEE_CONF_SIZE             0

#endif /* PROJECT_CONF_H_ */
