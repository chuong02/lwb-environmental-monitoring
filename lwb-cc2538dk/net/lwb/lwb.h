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

#ifndef __LWB_H__
#define __LWB_H__

/**
 * @file lwb.h
 * @brief Application header file for LWB
 */

#include "lwb-common.h"

#ifndef LWB_HOP_TO_ROOT_CONF
#define LWB_HOP_TO_ROOT_CONF 0
#endif

/* 1 = export lwb_get_next_round_ticks() (read-only; used by the ENV app's
 * phase-aligned packet generation). 0 = net/lwb compiles exactly as before. */
#ifndef LWB_ROUND_TIMING_CONF
#define LWB_ROUND_TIMING_CONF 0
#endif

/**
 * @brief Initialize LWB.
 * @param mode The mode of LWB. @see lwb_mode_t
 * @param callbacks A pointer to callback functions
 * @return Non-zero if initialization is successful.
 */
uint8_t lwb_init(lwb_mode_t mode, lwb_callbacks_t *callbacks);

/**
 * @brief Stop LWB
 */
void lwb_stop(void);

/**
 * @brief Get the run state of LWB
 * @return
 */
lwb_run_state_t lwb_get_run_state(void);

/**
 * @brief Queue packet to be sent over LWB.
 * @param data A pointer to the data buffer.
 * @param len The length of data.
 * @param dst_node_id The ID of the destination node
 * @return Non-zero if queuing is successful.
 */
uint8_t lwb_queue_packet(uint8_t* data, uint8_t len, uint16_t dst_node_id);

/**
 * @brief Get the time of LWB in seconds from when host is started.
 */
uint32_t lwb_get_host_time();

/**
 * @brief Get fine-grained synchronized LWB network time in RTIMER ticks.
 *
 * Host and synchronized Sources use the same LWB schedule/Glossy reference
 * as the time anchor. The value wraps modulo 2^32, so elapsed time must be
 * computed with unsigned subtraction.
 *
 * @return Synchronized network time in RTIMER ticks, or 0 while invalid.
 */
uint32_t lwb_get_network_time_ticks(void);

/* Strict measurement validity: Host anchored, or Source freshly SYNCED.
 * Zero is a valid numeric timestamp; use this validity API separately. */
uint8_t lwb_time_is_fresh(void);
/* Enough idle time before the next round for a bounded background task. */
uint8_t lwb_background_allowed(uint16_t budget_ms);
#if LWB_ROUND_TIMING_CONF
/* Local RTIMER time (ticks, modulo 2^32) at which the NEXT round begins, as
 * LWB itself computes it (round start + round period + skew correction - sync
 * guard on a SOURCE). Valid only between rounds: returns 0 and leaves *out
 * untouched while a round is running, before the first schedule is received
 * (SOURCE bootstrap) or after lwb_stop(). Returns 1 and sets *out otherwise. */
uint8_t lwb_get_next_round_ticks(uint32_t *out);
#endif
/* Returns metadata for the SAME packet, only inside on_data(). */
uint8_t lwb_get_last_rx_metadata(lwb_rx_metadata_t *out);
uint8_t lwb_get_tx_queue_len(void);
/* Call only in a guarded idle period, after measurement deadline. */
uint8_t lwb_drop_tx_queue(void);
void lwb_set_tx_observer(lwb_tx_observer_t observer);

/**
 * @brief Request from LWB host to add a stream for the node.
 * @param ipi Inter-packet interval in seconds.
 * @param t_offset The time offset when the slot should be allocated.
 * @return The ID of the stream
 */
uint8_t lwb_request_stream_add(uint16_t ipi, uint16_t t_offset);

/**
 * @brief Request from LWB host to delete a stream for the node
 * @param id The stream ID
 */
void lwb_request_stream_del(uint8_t id);

/**
 * @brief Request from LWB host to modify a stream request.
 * @param id The ID of the stream to be modified.
 * @param ipi New inter-packet interval
 */
void lwb_request_stream_mod(uint8_t id, uint16_t ipi);

/**
 * @brief Return number of slots belong to the node
 * @return Number of slots
 */
uint8_t lwb_get_n_my_slots();

/**
 * @brief Get LWB joining state
 * @return one of the states from @link lwb_joining_state_t
 */
lwb_joining_state_t lwb_get_joining_state();

/**
 * @brief Get a propagation estimate from the latest Host schedule flood.
 *
 * The value comes from the relay counter of the most recently received
 * schedule/synchronization flood. In this CC2538 port the Host initiates
 * the relay counter at 0, therefore hop_to_root = relay_cnt + 1.
 *
 * Delayed reception/retransmissions can inflate this value. It is not a
 * routing distance or evidence of the shortest physical path.
 * @return Raw relay counter + 1, or 0 if unavailable.
 */
#if LWB_HOP_TO_ROOT_CONF
uint8_t lwb_get_hop_count_to_host(void);
#endif

#endif /* __LWB_H__ */
