CONTIKI_PROJECT = lwb-test

all: $(CONTIKI_PROJECT)

CONTIKI = ../../../../..
NODEID ?= 1

CONTIKI_WITH_RIME = 1

override DEFINES += PROJECT_CONF_H=\"project-conf.h\"
override DEFINES += LWB_CUSTOM_CONF_H=\"lwb-custom-conf.h\"
override DEFINES += NODE_ID_CONF=$(NODEID)
override DEFINES += LWB_CONF_NULL_NETSTACK=1

PROJECTDIRS += ../deployment
PROJECT_SOURCEFILES += deployment.c lwb-debug-print.c

include ../../Makefile.lwb
include $(CONTIKI)/Makefile.include
