CONTIKI_PROJECT = glossy-test

all: $(CONTIKI_PROJECT)

CONTIKI = ../../../../..
NODEID ?= 1

CONTIKI_WITH_RIME = 1

override DEFINES += PROJECT_CONF_H=\"project-conf.h\"
override DEFINES += NODE_ID_CONF=$(NODEID)
override DEFINES += LWB_CONF_NULL_NETSTACK=1

PROJECTDIRS += ../deployment
PROJECT_SOURCEFILES += deployment.c

include ../../Makefile.lwb
include $(CONTIKI)/Makefile.include
