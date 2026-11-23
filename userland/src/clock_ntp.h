/* SNTP unicast reply validation (RFC 4330 section 5). No system clock dependencies. */
#ifndef REDWOOD_CLOCK_NTP_H
#define REDWOOD_CLOCK_NTP_H
#include <stdint.h>
#include <string.h>
#include "clock_policy.h"

static inline uint32_t
clock_u32(const unsigned char *p)
{
	return (uint32_t)p[0] << 24 | (uint32_t)p[1] << 16 | (uint32_t)p[2] << 8 | p[3];
}

static inline int
clock_ntp_reply(const unsigned char *p, unsigned long length, const unsigned char *nonce, long *seconds, long *usec)
{
	if (length < 48 || p[0] >> 6 == 3 || ((p[0] >> 3) & 7) < 3 ||
	    ((p[0] >> 3) & 7) > 4 || (p[0] & 7) != 4 || p[1] == 0 || p[1] > 15 ||
	    memcmp(p + 24, nonce, 8) != 0 || clock_u32(p + 32) == 0) {
		return -1;
	}
	uint64_t ntp = clock_u32(p + 40);
	/* Unfold the NTP era for 2023..2099, including the February 2036 wrap. */
	if (ntp < 2208988800ULL) ntp += 1ULL << 32;
	long unix_time = (long)(ntp - 2208988800ULL);
	if (!clock_valid(unix_time)) return -1;
	*seconds = unix_time;
	*usec = (long)(((uint64_t)clock_u32(p + 44) * 1000000) >> 32);
	return 0;
}
#endif
