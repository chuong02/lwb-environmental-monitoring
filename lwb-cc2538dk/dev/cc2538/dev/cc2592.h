#ifndef CC2592_H_
#define CC2592_H_

#include <stdint.h>

/*
 * CC2592 front-end mapping used by the CC2538 + CC2592 reference design:
 *   PC3 -> PA_EN
 *   PC2 -> LNA_EN
 *   PD2 -> HGM
 *
 * PA_EN and LNA_EN are driven automatically from RF-core observation
 * signals. HGM is controlled as a normal GPIO.
 */

void cc2592_init(void);
void cc2592_set_high_gain(uint8_t enable);
void cc2592_disable(void);

#endif /* CC2592_H_ */
