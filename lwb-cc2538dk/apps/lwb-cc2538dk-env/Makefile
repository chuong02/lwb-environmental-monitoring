CONTIKI_PROJECT = lwb-cc2538dk-env
all: $(CONTIKI_PROJECT)
CONTIKI ?= ../../../../..
NODEID ?= 1
ROLE ?= 0
HOST_ID ?= 1
RUN_ID ?= 1
PACKETS ?= 100
IPI ?= 5
SOURCE_IDS ?= 2
MAX_NODE_ID ?= 6
START_DELAY ?= 20
JOIN_TIMEOUT ?= 120
REPORT_WAIT ?= 15
DRAIN_TIMEOUT ?= 60
REPORT_REPEAT ?= 3
SUMMARY_PERIOD ?= 30
MAX_DELAY_S ?= 120
SAMPLE_PERIOD ?= 1
OLED ?= 1
HOST_LOCAL_SENSOR ?= 0
USE_TEMP_RH ?= 1
USE_LIGHT ?= 1
USE_BMP ?= 1
TEMP_RH_SENSOR ?= 0
I2C_SCL ?= 3
I2C_SDA ?= 4
CHANNEL ?= 26
TX_POWER_DBM ?= 7
DATA_BUFFERS ?= 16
N_SYNC ?= 3
N_DATA_TX ?= 3
# GEN_MODE: 0 = legacy etimer IPI; 1 = packet generation phase-aligned to the LWB round
# (enqueue GEN_LEAD_MS before the next round starts; the sensors are read just before the
# enqueue when SENSOR_BUDGET_MS + 30 ms of idle time remain, the OLED right after a round).
GEN_MODE ?= 0
GEN_LEAD_MS ?= 250
SENSOR_BUDGET_MS ?= 150
# FRESH_ONLY: 1 = no packet while unsynced / without stream ack; a stale queued packet is
# replaced by the new one. Follows GEN_MODE unless given explicitly.
FRESH_ONLY ?= $(GEN_MODE)
# PACKETS=0 (continuous): SOURCE sends a cumulative REPORT after every REPORT_EVERY DATA packets.
REPORT_EVERY ?= 60
# RADIO_STATS: 1 = software radio duty cycle (Glossy start/stop timestamps) printed as PERF_RADIO every
# RADIO_STATS_PERIOD rounds. 0 = no code, glossy.c is compiled as before.
RADIO_STATS ?= 0
RADIO_STATS_PERIOD ?= 12
# 1 = append *HH (XOR checksum) to every UART line; gateway drops corrupted lines
UART_CHECKSUM ?= 1
CONTIKI_WITH_RIME = 1
override DEFINES += PROJECT_CONF_H=\"project-conf.h\"
override DEFINES += LWB_CUSTOM_CONF_H=\"lwb-custom-conf.h\"
override DEFINES += NODE_ID_CONF=$(NODEID) LWB_CONF_NULL_NETSTACK=1
override DEFINES += UP_ROLE=$(ROLE) UP_HOST_ID=$(HOST_ID) UP_RUN_ID=$(RUN_ID)UL
override DEFINES += UP_PACKETS=$(PACKETS) UP_IPI=$(IPI) UP_MAX_NODE_ID=$(MAX_NODE_ID)
# Colon separated, without spaces: SOURCE_IDS=2:3:4
override DEFINES += UP_SOURCE_IDS=\"$(SOURCE_IDS)\"
override DEFINES += UP_START_DELAY=$(START_DELAY) UP_JOIN_TIMEOUT=$(JOIN_TIMEOUT)
override DEFINES += UP_REPORT_WAIT=$(REPORT_WAIT) UP_DRAIN_TIMEOUT=$(DRAIN_TIMEOUT)
override DEFINES += UP_REPORT_REPEAT=$(REPORT_REPEAT) UP_SUMMARY_PERIOD=$(SUMMARY_PERIOD)
override DEFINES += UP_MAX_DELAY_S=$(MAX_DELAY_S) UP_SAMPLE_PERIOD=$(SAMPLE_PERIOD)
override DEFINES += LWB_ENV_OLED_CONF=$(OLED) LWB_ENV_HOST_LOCAL_SENSOR_CONF=$(HOST_LOCAL_SENSOR)
override DEFINES += ENV_USE_TEMP_RH_CONF=$(USE_TEMP_RH) ENV_USE_LIGHT_CONF=$(USE_LIGHT)
override DEFINES += ENV_USE_BMP180_CONF=$(USE_BMP) ENV_TEMP_RH_SENSOR_CONF=$(TEMP_RH_SENSOR)
override DEFINES += I2C_SW_SCL_PIN_CONF=$(I2C_SCL) I2C_SW_SDA_PIN_CONF=$(I2C_SDA)
override DEFINES += CC2538_RF_CONF_CHANNEL=$(CHANNEL) CC2592_CONF_TX_POWER_DBM=$(TX_POWER_DBM)
override DEFINES += LWB_CONF_MAX_DATA_BUF_ELEMENTS=$(DATA_BUFFERS)
override DEFINES += LWB_CONF_N_SYNC=$(N_SYNC) LWB_CONF_N_RR=$(N_DATA_TX)
override DEFINES += UP_GEN_MODE=$(GEN_MODE) UP_GEN_LEAD_MS=$(GEN_LEAD_MS)
override DEFINES += UP_SENSOR_BUDGET_MS=$(SENSOR_BUDGET_MS)
override DEFINES += UP_FRESH_ONLY=$(FRESH_ONLY) UP_REPORT_EVERY=$(REPORT_EVERY)
override DEFINES += UP_RADIO_STATS=$(RADIO_STATS) UP_RADIO_STATS_PERIOD=$(RADIO_STATS_PERIOD)
# The accounting hooks in net/glossy/glossy.c are compiled only for RADIO_STATS=1.
override DEFINES += GLOSSY_RADIO_STATS_CONF=$(RADIO_STATS)
# lwb_get_next_round_ticks() is compiled into net/lwb only for GEN_MODE=1.
override DEFINES += LWB_ROUND_TIMING_CONF=$(GEN_MODE)
# Continuous mode prints PERF_SUMMARY with 32-bit counters (~520-550 chars worst case);
# uart-checksum.c truncates (and poisons the checksum of) lines >= UART_LINE_BUF_LEN (512).
ifeq ($(strip $(PACKETS)),0)
override DEFINES += UART_LINE_BUF_LEN=768
endif
# Legacy Contiki common symbols; also supported by GCC 4.9.3.
CFLAGS += -fcommon
PROJECTDIRS += ../deployment drivers
PROJECT_SOURCEFILES += deployment.c env-sensors.c env-oled.c
PROJECT_SOURCEFILES += i2c_sw.c si7021.c hdc1080.c tsl2561.c bmp180.c ssd1306.c
ifeq ($(UART_CHECKSUM),1)
PROJECT_SOURCEFILES += uart-checksum.c
CFLAGS += -fno-builtin-printf
LDFLAGS += -Wl,--wrap=printf
endif
include ../../Makefile.lwb
include $(CONTIKI)/Makefile.include
