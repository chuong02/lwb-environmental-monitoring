/* UART line checksum (NMEA style) for every printf on the node.
 *
 * Each text line leaving the UART becomes:   <line>*HH\r\n
 * HH = XOR of every byte of <line> (bytes before '*'), two upper-case hex digits.
 * The gateway recomputes HH and rejects corrupted lines, so UART loss is
 * counted separately from radio (LWB/Glossy) loss.
 *
 * Enabled by linking with -Wl,--wrap=printf (see Makefile, UART_CHECKSUM=1).
 * printf is only used from process context in this application; a nested
 * call (e.g. from an interrupt) is dropped instead of corrupting the buffer.
 */
#include <stdarg.h>
#include <stdio.h>
#include <stdint.h>

/* Older newlib (e.g. GCC 4.9.3 toolchain) defines putchar(x) as a macro for
 * putc(x, stdout), which pulls newlib stdio and fails to link (_write, _read...).
 * Use Contiki's putchar() from cpu/cc2538/dbg.c instead, as dbg.c itself does. */
#undef putchar
int putchar(int c);

#ifndef UART_LINE_BUF_LEN
#define UART_LINE_BUF_LEN 512
#endif

int __real_printf(const char *fmt, ...);

static char line_buf[UART_LINE_BUF_LEN];
static uint8_t line_cs;          /* running XOR of the current line */
static uint8_t line_active;      /* at least one payload byte since last EOL */
static volatile uint8_t busy;

static const char hex[] = "0123456789ABCDEF";

static void
emit_checksum(void)
{
  putchar('*');
  putchar(hex[(line_cs >> 4) & 0x0f]);
  putchar(hex[line_cs & 0x0f]);
  line_cs = 0;
  line_active = 0;
}

int
__wrap_printf(const char *fmt, ...)
{
  va_list ap;
  int n, i, len;

  if(busy) {
    return 0;
  }
  busy = 1;

  va_start(ap, fmt);
  n = vsnprintf(line_buf, sizeof(line_buf), fmt, ap);
  va_end(ap);

  if(n < 0) {
    busy = 0;
    return n;
  }
  len = n < (int)sizeof(line_buf) ? n : (int)sizeof(line_buf) - 1;

  for(i = 0; i < len; i++) {
    char c = line_buf[i];
    if(c == '\r' || c == '\n') {
      if(line_active) {
        emit_checksum();
      }
      putchar(c);
    } else {
      line_cs ^= (uint8_t)c;
      line_active = 1;
      putchar(c);
    }
  }

  if(n >= (int)sizeof(line_buf)) {
    /* Output was truncated: poison the checksum so the gateway drops it. */
    line_cs ^= 0x5a;
    putchar('~');
  }

  busy = 0;
  return len;
}
