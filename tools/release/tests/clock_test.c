/* Host-only: no call to settimeofday or the daemon's main loop. */
#define main clockd_main_unused
#include "../../../userland/src/clockd.c"
#undef main
#include <assert.h>
#include <sys/wait.h>

static void put32(unsigned char *p, uint32_t value) {
	p[0] = value >> 24; p[1] = value >> 16; p[2] = value >> 8; p[3] = value;
}

static void test_network(void) {
	int server = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
	assert(server >= 0);
	struct sockaddr_in local = { .sin_family = AF_INET, .sin_addr.s_addr = htonl(INADDR_LOOPBACK) };
	assert(bind(server, (struct sockaddr *)&local, sizeof(local)) == 0);
	socklen_t size = sizeof(local);
	assert(getsockname(server, (struct sockaddr *)&local, &size) == 0);
	pid_t child = fork();
	assert(child >= 0);
	if (child == 0) {
		unsigned char request[48], response[48] = { 0x24, 2 };
		struct sockaddr_in peer;
		socklen_t peer_size = sizeof(peer);
		struct timeval timeout = { 5, 0 };
		setsockopt(server, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
		assert(recvfrom(server, request, sizeof(request), 0, (struct sockaddr *)&peer, &peer_size) == 48);
		assert(request[0] == 0x23);
		memcpy(response + 24, request + 40, 8);
		put32(response + 32, (uint32_t)(1795392000ULL + 2208988800ULL));
		put32(response + 40, (uint32_t)(1795392000ULL + 2208988800ULL));
		assert(sendto(server, response, sizeof(response), 0, (struct sockaddr *)&peer, peer_size) == 48);
		close(server);
		_exit(0);
	}
	struct addrinfo address = { .ai_family = AF_INET, .ai_addr = (struct sockaddr *)&local, .ai_addrlen = sizeof(local) };
	struct timeval utc;
	assert(query_clock(&address, &utc) == 0);
	assert(utc.tv_sec == 1795392000 && utc.tv_usec >= 0 && utc.tv_usec < 1000000);
	int status;
	assert(waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0);
	close(server);
	puts("PASS: local UDP time exchange (host clock unchanged)");
}

int main(int argc, char **argv) {
	if (argc == 2 && strcmp(argv[1], "--network") == 0) {
		test_network();
		return 0;
	}
	assert(clock_boot_time(0, 0, 1795392000) == 1795392000);
	assert(clock_boot_time(0, 1795478400, 1795392000) == 1795478400);
	assert(clock_boot_time(0, 1700000000, 1795392000) == 1795392000);
	assert(clock_boot_time(1795305600, 1795478400, 1795392000) == 1795305600);
	assert(clock_boot_time(0, 0, 0) == 0);
	assert(clock_parse("1795392000\n", 11) == 1795392000);
	assert(clock_parse("1795392000", 10) == 1795392000);
	assert(clock_parse("1795392000junk", 14) == 0);
	assert(clock_parse("99999999999999999999999", 23) == 0);
	assert(clock_parse("-1", 2) == 0);
	assert(clock_parse("0\n", 2) == 0);

	unsigned char nonce[8] = { 1, 2, 3, 4, 5, 6, 7, 8 };
	unsigned char p[48] = { 0x24, 2 };
	memcpy(p + 24, nonce, 8);
	put32(p + 32, 4000000000U);
	put32(p + 40, (uint32_t)(1795392000ULL + 2208988800ULL));
	put32(p + 44, 0x80000000U);
	long sec, usec;
	assert(clock_ntp_reply(p, 48, nonce, &sec, &usec) == 0 && sec == 1795392000 && usec == 500000);
	assert(clock_ntp_reply(p, 47, nonce, &sec, &usec) != 0);
	p[24] ^= 1;
	assert(clock_ntp_reply(p, 48, nonce, &sec, &usec) != 0);
	p[24] ^= 1;
	p[0] = 0xe4; /* unsynchronized server */
	assert(clock_ntp_reply(p, 48, nonce, &sec, &usec) != 0);
	p[0] = 0x23; /* a reflected client request is not a server response */
	assert(clock_ntp_reply(p, 48, nonce, &sec, &usec) != 0);
	p[0] = 0x24;
	p[1] = 0; /* kiss-of-death */
	assert(clock_ntp_reply(p, 48, nonce, &sec, &usec) != 0);
	p[1] = 16;
	assert(clock_ntp_reply(p, 48, nonce, &sec, &usec) != 0);
	p[1] = 2;
	put32(p + 40, (uint32_t)(2208988800ULL + 2208988800ULL)); /* 2040, NTP era 1 */
	assert(clock_ntp_reply(p, 48, nonce, &sec, &usec) == 0 && sec == 2208988800L);
	put32(p + 40, (uint32_t)(1600000000ULL + 2208988800ULL)); /* implausibly old */
	assert(clock_ntp_reply(p, 48, nonce, &sec, &usec) != 0);

	char directory[] = "/tmp/jesvi-clock-test-XXXXXX", path[256], temporary[256], text[32];
	assert(mkdtemp(directory) != NULL);
	snprintf(path, sizeof(path), "%s/time", directory);
	snprintf(temporary, sizeof(temporary), "%s/time.tmp", directory);
	assert(save_clock(path, 1795392000) == 0);
	assert(save_clock(path, 0) != 0); /* bad time must not destroy last valid snapshot */
	FILE *f = fopen(path, "r");
	assert(f != NULL && fgets(text, sizeof(text), f) != NULL);
	fclose(f);
	assert(strcmp(text, "1795392000\n") == 0);
	assert(symlink(path, temporary) == 0);
	assert(save_clock(path, 1795478400) != 0);
	unlink(temporary);
	unlink(path);
	rmdir(directory);
	puts("PASS: fresh/offline boot clock, saved-time validation, SNTP rejection/2036 rollover, atomic persistence");
	return 0;
}
