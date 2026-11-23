/* Bootstrap UTC as soon as networking works; persist it independently of the debug log server. */
#if defined(__APPLE__)
#define _DARWIN_C_SOURCE 1
#else
#ifndef _DEFAULT_SOURCE
#define _DEFAULT_SOURCE
#endif
#ifndef _POSIX_C_SOURCE
#define _POSIX_C_SOURCE 200809L
#endif
#endif
#include <errno.h>
#include <fcntl.h>
#include <netdb.h>
#include <netinet/in.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <time.h>
#include <unistd.h>
#include "clock_ntp.h"

static double
monotonic_seconds(void)
{
	struct timespec ts;
	if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0) return -1;
	return (double)ts.tv_sec + (double)ts.tv_nsec / 1e9;
}

static int
query_clock(const struct addrinfo *address, struct timeval *utc)
{
	unsigned char request[48] = { 0x23 }, reply[512]; /* NTPv4 client. */
	struct timeval timeout = { 3, 0 };
	int fd = socket(address->ai_family, SOCK_DGRAM, IPPROTO_UDP);
	if (fd < 0) return -1;
	int result = -1;
	arc4random_buf(request + 40, 8); /* Echoed originate timestamp binds this reply to this request. */
	double start = monotonic_seconds();
	if (start >= 0 && setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout)) == 0 &&
	    connect(fd, address->ai_addr, address->ai_addrlen) == 0 && send(fd, request, sizeof(request), 0) == sizeof(request)) {
		ssize_t n = recv(fd, reply, sizeof(reply), 0);
		double elapsed = monotonic_seconds() - start;
		long seconds, usec;
		if (n >= 48 && elapsed >= 0 && elapsed <= 3 &&
		    clock_ntp_reply(reply, (unsigned long)n, request + 40, &seconds, &usec) == 0) {
			long correction = (long)(elapsed * 500000);
			utc->tv_sec = seconds + (usec + correction) / 1000000;
			utc->tv_usec = (usec + correction) % 1000000;
			result = clock_valid(utc->tv_sec) ? 0 : -1;
		}
	}
	close(fd);
	return result;
}

static int
network_clock(void)
{
	static const char *const servers[] = { "time.apple.com", "time.cloudflare.com", "pool.ntp.org" };
	struct addrinfo hints = { .ai_family = AF_UNSPEC, .ai_socktype = SOCK_DGRAM, .ai_protocol = IPPROTO_UDP };
	for (unsigned i = 0; i < sizeof(servers) / sizeof(servers[0]); i++) {
		struct addrinfo *addresses = NULL;
		if (getaddrinfo(servers[i], "123", &hints, &addresses) != 0) continue;
		int synced = 0, attempts = 0;
		for (struct addrinfo *a = addresses; a != NULL && attempts++ < 2; a = a->ai_next) {
			struct timeval utc;
			if (query_clock(a, &utc) == 0 && settimeofday(&utc, NULL) == 0) {
				printf("clockd: UTC synchronized from %s: %ld\n", servers[i], (long)utc.tv_sec);
				fflush(stdout);
				synced = 1;
				break;
			}
		}
		freeaddrinfo(addresses);
		if (synced) return 0;
	}
	return -1;
}

static int
save_clock(const char *path, long seconds)
{
	char text[32], temporary[256];
	if (!clock_valid(seconds) || snprintf(temporary, sizeof(temporary), "%s.tmp", path) >= (int)sizeof(temporary)) return -1;
	int length = snprintf(text, sizeof(text), "%ld\n", seconds);
	int fd = open(temporary, O_WRONLY | O_CREAT | O_TRUNC | O_NOFOLLOW, 0644);
	if (fd < 0) return -1;
	int result = write(fd, text, (size_t)length) == length && fsync(fd) == 0 ? 0 : -1;
	if (close(fd) != 0) result = -1;
	if (result == 0) result = rename(temporary, path);
	if (result != 0) unlink(temporary);
	return result;
}

int
main(void)
{
	int synced = 0;
	double next_save = 0, next_query = 0;
	for (;;) {
		double now = monotonic_seconds();
		if (!synced && now >= next_query) {
			synced = network_clock() == 0;
			next_query = monotonic_seconds() + 60;
			if (synced) next_save = 0;
		}
		if (now >= next_save) {
			if (save_clock(TIME_MARK, (long)time(NULL)) == 0) next_save = now + 60;
		}
		/* One successful bootstrap per boot leaves later manual corrections alone. */
		sleep(5);
	}
}
