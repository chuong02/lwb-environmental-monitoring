CONTIKI_PROJECT = deployment-test

all: $(CONTIKI_PROJECT)

CONTIKI = ../../../../..

NODEID ?= 1

override DEFINES += PROJECT_CONF_H=\"project-conf.h\"
override DEFINES += NODE_ID_CONF=$(NODEID)

PROJECT_SOURCEFILES += deployment.c
PROJECTDIRS += ../../platform/cc2538dk-lwb
PROJECT_SOURCEFILES += node-id.c

include $(CONTIKI)/Makefile.include
