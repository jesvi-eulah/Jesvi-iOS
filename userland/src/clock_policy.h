/* Shared by static init and the network clock service. UTC Unix seconds. */
#ifndef REDWOOD_CLOCK_POLICY_H
#define REDWOOD_CLOCK_POLICY_H

#define CLOCK_MIN 1700000000L
#define CLOCK_MAX 4102444800L /* 2100-01-01; reject corrupt saved/network values. */
#define TIME_MARK "/private/var/db/redwood-time"

static inline int
clock_valid(long seconds)
{
	return seconds >= CLOCK_MIN && seconds < CLOCK_MAX;
}

static inline long
clock_parse(const char *text, unsigned long length)
{
	long value = 0;
	unsigned long i = 0;
	while (i < length && text[i] >= '0' && text[i] <= '9') {
		if (value > (CLOCK_MAX - (text[i] - '0')) / 10) {
			return 0;
		}
		value = value * 10 + (text[i++] - '0');
	}
	if (i < length && text[i] == '\n') {
		i++;
	}
	return i == length && clock_valid(value) ? value : 0;
}

static inline long
clock_boot_time(long current, long saved, long built)
{
	if (clock_valid(current)) {
		return current;
	}
	if (!clock_valid(saved)) saved = 0;
	if (!clock_valid(built)) built = 0;
	return saved > built ? saved : built;
}
#endif
