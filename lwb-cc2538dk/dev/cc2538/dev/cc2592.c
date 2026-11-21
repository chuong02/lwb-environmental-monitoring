#include "contiki.h"
#include "cc2592.h"
#include "cc2538-rf.h"

#include "dev/gpio.h"
#include "dev/ioc.h"
#include "dev/rfcore.h"
#include "dev/cctest.h"
#include "reg.h"

#include <stdio.h>

#ifndef CC2592_CONF_ENABLE
#define CC2592_CONF_ENABLE 1
#endif

#ifndef CC2592_CONF_HIGH_GAIN
#define CC2592_CONF_HIGH_GAIN 1
#endif

#ifndef CC2592_CONF_TX_POWER_DBM
#define CC2592_CONF_TX_POWER_DBM 7
#endif

/* Reference-design pin mapping. */
#define CC2592_PA_EN_PORT       GPIO_C_NUM
#define CC2592_PA_EN_PIN        3
#define CC2592_LNA_EN_PORT      GPIO_C_NUM
#define CC2592_LNA_EN_PIN       2
#define CC2592_HGM_PORT         GPIO_D_NUM
#define CC2592_HGM_PIN          2

#define CC2592_PA_EN_BASE       GPIO_PORT_TO_BASE(CC2592_PA_EN_PORT)
#define CC2592_LNA_EN_BASE      GPIO_PORT_TO_BASE(CC2592_LNA_EN_PORT)
#define CC2592_HGM_BASE         GPIO_PORT_TO_BASE(CC2592_HGM_PORT)

#define CC2592_PA_EN_MASK       GPIO_PIN_MASK(CC2592_PA_EN_PIN)
#define CC2592_LNA_EN_MASK      GPIO_PIN_MASK(CC2592_LNA_EN_PIN)
#define CC2592_HGM_MASK         GPIO_PIN_MASK(CC2592_HGM_PIN)

/* RF-core observable signal selection.
 * RFC_OBS_POL (bit 6) is set because pa_pd/lna_pd are power-down signals,
 * while CC2592 PA_EN/LNA_EN are active-high enable inputs.
 */
#define CC2592_RFC_OBS_POL      0x40
#define CC2592_RFC_OBS_PA_PD    0x28
#define CC2592_RFC_OBS_LNA_PD   0x2A

#define CC2592_RFC_OBS_PA_EN    (CC2592_RFC_OBS_POL | CC2592_RFC_OBS_PA_PD)
#define CC2592_RFC_OBS_LNA_EN   (CC2592_RFC_OBS_POL | CC2592_RFC_OBS_LNA_PD)

/* CCTEST_OBSSELx SEL values: 0 -> rfc_obs_sig0, 1 -> rfc_obs_sig1. */
#define CC2592_OBS_SIG0         0
#define CC2592_OBS_SIG1         1

void
cc2592_set_high_gain(uint8_t enable)
{
#if CC2592_CONF_ENABLE
  if(enable) {
    GPIO_SET_PIN(CC2592_HGM_BASE, CC2592_HGM_MASK);
  } else {
    GPIO_CLR_PIN(CC2592_HGM_BASE, CC2592_HGM_MASK);
  }
#else
  (void)enable;
#endif
}

void
cc2592_init(void)
{
#if CC2592_CONF_ENABLE
  /*
   * PC3 / PA_EN: automatic active-high TX enable.
   * PC2 / LNA_EN: automatic active-high RX enable.
   * Observation output control overrides normal GPIO data while enabled.
   */
  GPIO_SET_OUTPUT(CC2592_PA_EN_BASE, CC2592_PA_EN_MASK);
  GPIO_SET_OUTPUT(CC2592_LNA_EN_BASE, CC2592_LNA_EN_MASK);
  GPIO_PERIPHERAL_CONTROL(CC2592_PA_EN_BASE, CC2592_PA_EN_MASK);
  GPIO_PERIPHERAL_CONTROL(CC2592_LNA_EN_BASE, CC2592_LNA_EN_MASK);
  ioc_set_over(CC2592_PA_EN_PORT, CC2592_PA_EN_PIN, IOC_OVERRIDE_OE);
  ioc_set_over(CC2592_LNA_EN_PORT, CC2592_LNA_EN_PIN, IOC_OVERRIDE_OE);

  /* rfc_obs_sig0 = NOT pa_pd -> PA_EN on PC3. */
  REG(RFCORE_XREG_RFC_OBS_CTRL0) = CC2592_RFC_OBS_PA_EN;
  REG(CCTEST_OBSSEL3) = CCTEST_OBSSEL_EN | CC2592_OBS_SIG0;

  /* rfc_obs_sig1 = NOT lna_pd -> LNA_EN on PC2. */
  REG(RFCORE_XREG_RFC_OBS_CTRL1) = CC2592_RFC_OBS_LNA_EN;
  REG(CCTEST_OBSSEL2) = CCTEST_OBSSEL_EN | CC2592_OBS_SIG1;

  /* PD2 / HGM is a software-controlled output. */
  GPIO_SOFTWARE_CONTROL(CC2592_HGM_BASE, CC2592_HGM_MASK);
  GPIO_SET_OUTPUT(CC2592_HGM_BASE, CC2592_HGM_MASK);
  ioc_set_over(CC2592_HGM_PORT, CC2592_HGM_PIN, IOC_OVERRIDE_OE);
  cc2592_set_high_gain(CC2592_CONF_HIGH_GAIN);

  /* Configure the CC2538 drive level feeding the CC2592. */
  cc2538_rf_set_tx_power(CC2592_CONF_TX_POWER_DBM);

  printf("CC2592,enabled,PA_EN,PC3,LNA_EN,PC2,HGM,PD2,%u,tx_drive_dbm,%d\r\n",
         (unsigned)CC2592_CONF_HIGH_GAIN,
         (int)cc2538_rf_get_tx_power());
#else
  printf("CC2592,disabled\r\n");
#endif
}

void
cc2592_disable(void)
{
#if CC2592_CONF_ENABLE
  /* Disable RF observation routing first. */
  REG(CCTEST_OBSSEL3) = 0;
  REG(CCTEST_OBSSEL2) = 0;

  /* Return PA_EN and LNA_EN to software GPIO and force power-down. */
  GPIO_SOFTWARE_CONTROL(CC2592_PA_EN_BASE, CC2592_PA_EN_MASK);
  GPIO_SOFTWARE_CONTROL(CC2592_LNA_EN_BASE, CC2592_LNA_EN_MASK);
  GPIO_SET_OUTPUT(CC2592_PA_EN_BASE, CC2592_PA_EN_MASK);
  GPIO_SET_OUTPUT(CC2592_LNA_EN_BASE, CC2592_LNA_EN_MASK);
  GPIO_CLR_PIN(CC2592_PA_EN_BASE, CC2592_PA_EN_MASK);
  GPIO_CLR_PIN(CC2592_LNA_EN_BASE, CC2592_LNA_EN_MASK);

  cc2592_set_high_gain(0);
#endif
}
