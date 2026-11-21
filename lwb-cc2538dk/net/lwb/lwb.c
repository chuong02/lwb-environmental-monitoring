/*
 * Copyright (c) 2016, Uppsala University, Sweden.
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions
 * are met:
 * 1. Redistributions of source code must retain the above copyright
 *    notice, this list of conditions and the following disclaimer.
 * 2. Redistributions in binary form must reproduce the above copyright
 *    notice, this list of conditions and the following disclaimer in the
 *    documentation and/or other materials provided with the distribution.
 *
 * 3. Neither the name of the copyright holder nor the names of its
 *    contributors may be used to endorse or promote products derived
 *    from this software without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
 * ``AS IS'' AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
 * LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
 * FOR A PARTICULAR PURPOSE ARE DISCLAIMED.  IN NO EVENT SHALL THE
 * COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
 * INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
 * (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
 * SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
 * HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT,
 * STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
 * ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED
 * OF THE POSSIBILITY OF SUCH DAMAGE.
 *
 * Author:  Kasun Hewage
 *          
 */

#include <string.h>
#include <stdio.h>
#include <inttypes.h>

#include "contiki.h"

#include "glossy.h"
#include "lwb-common.h"
#include "lwb-macros.h"
#include "lwb.h"
#include "lwb-g-sync.h"
#include "lwb-g-rr.h"
#include "lwb-scheduler.h"

PROCESS(lwb_main_process, "lwb main");

lwb_context_t lwb_context;
static struct process *init_process;
/*------------------------------------------------------------------------------------------------*/
uint8_t lwb_init(lwb_mode_t mode, lwb_callbacks_t *callbacks)
{

#if LWB_DEBUG_GPIO
  LWB_DEBUG_GPIO_PIN_1_INIT();
  LWB_DEBUG_GPIO_PIN_2_INIT();
#endif

  memset(&lwb_context, 0, sizeof(lwb_context_t));

  lwb_context.lwb_mode = mode;
  lwb_context.p_callbacks = callbacks;
  lwb_context.enc = GLOSSY_ENC_OFF;
  lwb_context.next_round_ticks = RTIMER_NOW() + RTIMER_SECOND;

  glossy_init();
  lwb_g_rr_init();
  lwb_g_sync_init();
  
  init_process = PROCESS_CURRENT();

  process_start(&lwb_main_process, NULL);

  return LWB_STATUS_SUCCESS;
}

/*------------------------------------------------------------------------------------------------*/
void lwb_stop(void)
{
  lwb_g_sync_stop();
}

/*------------------------------------------------------------------------------------------------*/
lwb_run_state_t lwb_get_run_state(void)
{
  return lwb_context.run_state;
}

/*------------------------------------------------------------------------------------------------*/
uint8_t lwb_queue_packet(uint8_t* data, uint8_t len, uint16_t dst_node_id)
{
  return lwb_g_rr_queue_packet(data, len, dst_node_id);
}

/*------------------------------------------------------------------------------------------------*/
uint8_t lwb_request_stream_add(uint16_t ipi, uint16_t t_offset)
{
  return lwb_g_rr_stream_add(ipi, t_offset);
}

/*------------------------------------------------------------------------------------------------*/
void lwb_request_stream_del(uint8_t id)
{
  lwb_g_rr_stream_del(id);
}

/*------------------------------------------------------------------------------------------------*/
void lwb_request_stream_mod(uint8_t id, uint16_t ipi)
{
  lwb_g_rr_stream_mod(id, ipi);
}

/*------------------------------------------------------------------------------------------------*/
uint8_t lwb_get_n_my_slots()
{
  return lwb_context.n_my_slots;
}

/*------------------------------------------------------------------------------------------------*/
uint8_t lwb_get_joining_state()
{
  return lwb_context.joining_state;
}

/*------------------------------------------------------------------------------------------------*/
PROCESS_THREAD(lwb_main_process, ev, data)
{
  PROCESS_BEGIN();

  while (1) {

    PROCESS_WAIT_EVENT_UNTIL(ev == PROCESS_EVENT_POLL);

    if (LWB_IS_SET_POLL_FLAG(LWB_POLL_FLAGS_DATA)) {
      PROCESS_CONTEXT_BEGIN(init_process);
      lwb_g_rr_data_output();
      PROCESS_CONTEXT_END(init_process);
      LWB_UNSET_POLL_FLAG(LWB_POLL_FLAGS_DATA);
    }

    if (LWB_IS_SET_POLL_FLAG(LWB_POLL_FLAGS_SCHED_END)
        && lwb_context.p_callbacks && lwb_context.p_callbacks->p_on_sched_end) {
      PROCESS_CONTEXT_BEGIN(init_process);
      lwb_context.p_callbacks->p_on_sched_end();
      PROCESS_CONTEXT_END(init_process);
      LWB_UNSET_POLL_FLAG(LWB_POLL_FLAGS_SCHED_END);
    }
  }

  PROCESS_END();

  return PT_ENDED;
}

/*------------------------------------------------------------------------------------------------*/
uint32_t lwb_get_host_time()
{
  return lwb_context.time;
}

/*------------------------------------------------------------------------------------------------*/
uint32_t lwb_get_network_time_ticks(void)
{
  /*
   * The offset is refreshed from the schedule time / Glossy T_REF pair.
   * Unsigned arithmetic intentionally provides modulo-2^32 wrap handling.
   */
  if(!lwb_context.network_time_valid) {
    return 0;
  }

  if(lwb_context.lwb_mode == LWB_MODE_SOURCE &&
     lwb_context.sync_state == LWB_SYNC_STATE_BOOTSTRAP) {
    return 0;
  }

  return (uint32_t)RTIMER_NOW() + lwb_context.network_time_offset_ticks;
}

/*------------------------------------------------------------------------------------------------*/
void lwb_save_energest()
{
    /* This function should be called before starting Glossy for schedules, stream requests and
     * stream acknowledgments
     */ 
#if LWB_CTRL_ENERGEST_ON || LWB_SLOT_ENERGEST_ON
    lwb_context.en_rx = energest_type_time(ENERGEST_TYPE_LISTEN);
    lwb_context.en_tx = energest_type_time(ENERGEST_TYPE_TRANSMIT);
#endif // LWB_CTRL_ENERGEST_ON
}

/*------------------------------------------------------------------------------------------------*/
void lwb_update_ctrl_energest()
{
    /* This function should be called after Glossy finishes for schedules, stream requests and
     * stream acknowledgments
     */ 
#if LWB_CTRL_ENERGEST_ON
    lwb_context.en_control += (energest_type_time(ENERGEST_TYPE_LISTEN) - lwb_context.en_rx) +
                                    (energest_type_time(ENERGEST_TYPE_TRANSMIT) - lwb_context.en_tx);
#endif // LWB_CONTROL_DC
}

/*------------------------------------------------------------------------------------------------*/
void lwb_reset_slot_energest()
{
#if LWB_SLOT_ENERGEST_ON
  lwb_context.n_en_slots = 0;
#endif /* LWB_SLOT_ENERGEST_ON */
}

/*------------------------------------------------------------------------------------------------*/
void lwb_update_slot_energest()
{
#if LWB_SLOT_ENERGEST_ON
  if (lwb_context.n_en_slots < LWB_SCHED_MAX_SLOTS) {
    lwb_context.en_slots[lwb_context.n_en_slots++] = (energest_type_time(ENERGEST_TYPE_LISTEN) - lwb_context.en_rx)
                                                     + (energest_type_time(ENERGEST_TYPE_TRANSMIT) - lwb_context.en_tx);
  }
#endif /* LWB_SLOT_ENERGEST_ON */
}

/*------------------------------------------------------------------------------------------------*/
#if LWB_HOP_TO_ROOT_CONF
uint8_t
lwb_get_hop_count_to_host(void)
{
  uint8_t relay_cnt;

  /*
   * Hop-to-root is meaningful only at non-host nodes after at least one
   * schedule/synchronization flood has been received. The Host starts the
   * Glossy relay counter at 0 in this CC2538 port, so a direct Source->Host
   * first direct reception normally has relay_cnt=0 => estimate=1. A late
   * reception can give a larger value even with a direct physical link.
   */
  if(lwb_context.lwb_mode != LWB_MODE_SOURCE ||
     lwb_context.sync_state == LWB_SYNC_STATE_BOOTSTRAP ||
     lwb_context.sync_stats.n_rx == 0) {
    return 0;
  }

  relay_cnt = lwb_context.sync_stats.relay_cnt_first_rx;

  /* 0xff is reserved here as unavailable/invalid metadata. */
  if(relay_cnt == 0xff) {
    return 0;
  }

  return (uint8_t)(relay_cnt + 1u);
}
#endif /* LWB_HOP_TO_ROOT_CONF */

uint8_t lwb_time_is_fresh(void)
{
  return lwb_context.network_time_valid &&
    (lwb_context.lwb_mode == LWB_MODE_HOST ||
     lwb_context.sync_state == LWB_SYNC_STATE_SYNCED);
}

uint8_t lwb_background_allowed(uint16_t budget_ms)
{
  uint32_t left;
  uint32_t required = ((uint32_t)budget_ms * RTIMER_SECOND) / 1000UL;
  if(lwb_context.round_active) return 0;
  left = (uint32_t)(lwb_context.next_round_ticks - RTIMER_NOW());
  return left < 0x80000000UL && left > required;
}

#if LWB_ROUND_TIMING_CONF
uint8_t lwb_get_next_round_ticks(uint32_t *out)
{
  if(!out || lwb_context.round_active ||
     lwb_context.run_state != LWB_RUN_STATE_ACTIVE) return 0;
  /* A SOURCE has no round timeline until its first schedule is received. */
  if(lwb_context.lwb_mode == LWB_MODE_SOURCE &&
     lwb_context.sync_state == LWB_SYNC_STATE_BOOTSTRAP) return 0;
  *out = (uint32_t)lwb_context.next_round_ticks;
  return 1;
}
#endif
