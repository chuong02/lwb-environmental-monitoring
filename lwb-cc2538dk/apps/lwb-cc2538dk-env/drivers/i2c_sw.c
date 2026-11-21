#include "contiki.h"
#include "i2c_sw.h"
#include "dev/gpio.h"
#include "dev/ioc.h"
#include "clock.h"

#ifndef I2C_SW_SCL_PIN_CONF
#define I2C_SW_SCL_PIN_CONF 3
#endif

#ifndef I2C_SW_SDA_PIN_CONF
#define I2C_SW_SDA_PIN_CONF 4
#endif

#ifndef I2C_SW_DELAY_US_CONF
#define I2C_SW_DELAY_US_CONF 5
#endif

#define SCL_PORT_NUM GPIO_B_NUM
#define SDA_PORT_NUM GPIO_B_NUM
#define SCL_PIN      I2C_SW_SCL_PIN_CONF
#define SDA_PIN      I2C_SW_SDA_PIN_CONF
#define GPIO_BASE    GPIO_B_BASE

#define SCL_0()     GPIO_CLR_PIN(GPIO_BASE, 1 << SCL_PIN)
#define SCL_1()     GPIO_SET_PIN(GPIO_BASE, 1 << SCL_PIN)
#define SDA_0()     GPIO_CLR_PIN(GPIO_BASE, 1 << SDA_PIN)
#define SDA_1()     GPIO_SET_PIN(GPIO_BASE, 1 << SDA_PIN)
#define SDA_READ()  (GPIO_READ_PIN(GPIO_BASE, 1 << SDA_PIN) != 0)
#define SDA_OUT()   GPIO_SET_OUTPUT(GPIO_BASE, 1 << SDA_PIN)
#define SDA_IN()    GPIO_SET_INPUT(GPIO_BASE, 1 << SDA_PIN)

static void
i2c_delay(void)
{
  clock_delay_usec(I2C_SW_DELAY_US_CONF);
}

void
i2c_sw_init(void)
{
  GPIO_SET_OUTPUT(GPIO_BASE, 1 << SCL_PIN);
  ioc_set_over(SCL_PORT_NUM, SCL_PIN, IOC_OVERRIDE_PUE);
  ioc_set_over(SDA_PORT_NUM, SDA_PIN, IOC_OVERRIDE_PUE);

  SDA_OUT();
  SDA_1();
  SCL_1();
  i2c_delay();

  /* Release a slave that may have been left mid-transaction after reset. */
  i2c_sw_recover();
}

void
i2c_sw_recover(void)
{
  uint8_t i;

  SDA_IN();
  SCL_1();
  i2c_delay();

  for(i = 0; i < 9; i++) {
    SCL_0();
    i2c_delay();
    SCL_1();
    i2c_delay();
  }

  /* Generate STOP. */
  SDA_OUT();
  SDA_0();
  i2c_delay();
  SCL_1();
  i2c_delay();
  SDA_1();
  i2c_delay();
}

void
i2c_sw_start(void)
{
  SDA_OUT();
  SDA_1();
  SCL_1();
  i2c_delay();
  SDA_0();
  i2c_delay();
  SCL_0();
  i2c_delay();
}

void
i2c_sw_stop(void)
{
  SDA_OUT();
  SDA_0();
  i2c_delay();
  SCL_1();
  i2c_delay();
  SDA_1();
  i2c_delay();
}

int
i2c_sw_write(uint8_t data)
{
  uint8_t i;
  int ack;

  SDA_OUT();
  for(i = 0; i < 8; i++) {
    if(data & 0x80) {
      SDA_1();
    } else {
      SDA_0();
    }

    i2c_delay();
    SCL_1();
    i2c_delay();
    SCL_0();
    i2c_delay();
    data <<= 1;
  }

  SDA_IN();
  SCL_1();
  i2c_delay();
  ack = !SDA_READ();
  SCL_0();
  i2c_delay();
  SDA_OUT();

  return ack;
}

uint8_t
i2c_sw_read(int ack)
{
  uint8_t data;
  uint8_t i;

  data = 0;
  SDA_IN();

  for(i = 0; i < 8; i++) {
    data <<= 1;
    SCL_1();
    i2c_delay();

    if(SDA_READ()) {
      data |= 1;
    }

    SCL_0();
    i2c_delay();
  }

  SDA_OUT();
  if(ack) {
    SDA_0();
  } else {
    SDA_1();
  }

  SCL_1();
  i2c_delay();
  SCL_0();
  i2c_delay();
  SDA_1();

  return data;
}
