/*
 * The status bar's left side a little nearer the screen edge (user, 2026-11-13: "the carrier name or the time ...
 * can go a bit more to the left, just a tiny bit"). With island=1 iOS lays the status bar out with
 * _UIStatusBarVisualProvider_DynamicSplit (the 14 Pro's); its -edgeInsets' leading value is the gap at the left.
 * That gap is made smaller by `lead` points (default 3). The status bar is drawn in SpringBoard (home screen) and
 * in every app, so this is included by libredwood-sb (inject_sb.c) and libredwood (inject.c).
 *   /var/jb/etc/redwood-statusbar.conf: "lead=N" (points; 0 = Apple's). Read at process start: respring / reopen apps.
 */
#include <CoreFoundation/CoreFoundation.h>
#include <dispatch/dispatch.h>
#include <dlfcn.h>
#include <objc/message.h>
#include <objc/runtime.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/sysctl.h>
#include <unistd.h>

struct sbs_insets { double top, leading, bottom, trailing; };   /* NSDirectionalEdgeInsets */
static double sbs_lead = 0;      /* Apple's place (the user, 2026-11-15: reset; "lead=N" in the conf moves the time N/2 pt left) */
static double sbs_icons = 1.08;  /* "icons=F": the status bar icons (signal, Wi-Fi, battery) F times Apple's size (the user, 2026-11-15: "just a little big"); icons=1: Apple's */
static int sbs_bolt = 0;         /* "bolt=1": keep the bolt's animation on island phones too (default: no animation; the island animates charging) */
static struct sbs_insets (*sbs_orig)(id, SEL);

static void
sbs_log(const char *fmt, double a, double b)
{
	FILE *f = fopen("/var/mobile/Library/Logs/redwood-statusbar.log", "a");

	if (f != NULL) {
		fprintf(f, "statusbar: pid %d ", getpid());
		fprintf(f, fmt, a, b);
		fputc('\n', f);
		fclose(f);
	}
}

static struct sbs_insets
sbs_edge_insets(id self, SEL cmd)
{
	struct sbs_insets v = sbs_orig(self, cmd);

	/* (allowed below 0: the time is centred in the left area, so the area's start must go past the edge for the
	 * time to move by more than half of what is taken off -- user 2026-11-13: "push it further left") */
	{
		static int told;
		if (told++ < 2) {
			sbs_log("edgeInsets leading %.1f -> %.1f", v.leading, v.leading - sbs_lead);
		}
	}
	v.leading -= sbs_lead;
	return v;
}

/*
 * The cutout the status bar lays itself out around (user 2026-11-13: "still has padding to the left"). The time is
 * centred in the area between the left edge and the island; with the S20's small punch-hole pill (21 pt) that area
 * is far wider than a 14 Pro's, so the time sat near the middle of it. The cutout width the status bar uses is held
 * at least `cut` points (default 125, Apple's pill; "cut=0" in the conf: as iOS computes it), which puts the time
 * where an iPhone has it; `lead` then moves it further left. Only the status bar's layout: the island is untouched.
 */
struct sbs_rect { double x, y, w, h; };
static double sbs_cut = 0;
static bool (*sbs_orig_avoid)(id, SEL, struct sbs_rect, double *, double *);

static bool
sbs_avoid(id self, SEL cmd, struct sbs_rect frame, double *offset, double *width)
{
	bool changed = sbs_orig_avoid(self, cmd, frame, offset, width);

	static int told;

	if (width != NULL && *width > 0 && *width < sbs_cut) {
		if (told < 3 && getpid() > 0) {
			FILE *f = fopen("/var/mobile/Library/Logs/redwood-statusbar.log", "a");   /* (apps' sandbox: fails, fine) */
			if (f != NULL) {
				fprintf(f, "statusbar: pid %d cutout %.1f -> %.1f (lead %.1f)\n", getpid(), *width, sbs_cut, sbs_lead);
				fclose(f);
			}
			told++;
		}
		*width = sbs_cut;
		changed = true;
	}
	return changed;
}

/*
 * At boot the status bar creates its cutout-width constraint straight from the island's size and only goes through
 * _needsUpdateOfConstraintsForAvoidanceFrame: when the island later changes (2026-11-13: the log stayed empty after a
 * boot and the time sat at Apple's place). So the constraint is also widened when it is handed over.
 */
static void (*sbs_orig_set_cut)(id, SEL, id);

static void
sbs_widen(id constraint, const char *why)
{
	SEL get = sel_registerName("constant"), set = sel_registerName("setConstant:");
	double c;

	if (constraint == nil || sbs_cut <= 0 || !class_respondsToSelector(object_getClass(constraint), get)) {
		return;
	}
	c = ((double (*)(id, SEL))objc_msgSend)(constraint, get);
	{
		static int told;
		if (told++ < 4) {
			sbs_log("cutout constraint constant %.1f (cut %.1f)", c, sbs_cut);
		}
	}
	if (c > 0 && c < sbs_cut) {
		((void (*)(id, SEL, double))objc_msgSend)(constraint, set, sbs_cut);
		FILE *f = fopen("/var/mobile/Library/Logs/redwood-statusbar.log", "a");
		if (f != NULL) {
			fprintf(f, "statusbar: pid %d %s %.1f -> %.1f\n", getpid(), why, c, sbs_cut);
			fclose(f);
		}
	}
}

static void
sbs_set_cut(id self, SEL cmd, id constraint)
{
	sbs_orig_set_cut(self, cmd, constraint);
	sbs_widen(constraint, "cutout constraint");
}

static id (*sbs_orig_setup)(id, SEL, id);

static id
sbs_setup(id self, SEL cmd, id container)
{
	id r = sbs_orig_setup(self, cmd, container);
	id c = ((id (*)(id, SEL))objc_msgSend)(self, sel_registerName("cutoutWidthConstraint"));

	sbs_widen(c, "setup");
	return r;
}

/*
 * The layout this phone really uses (2026-11-13, found by logging: DynamicSplit's methods were never called): the
 * screen is the iPhone X's (1125 px), so UIKit picks _UIStatusBarVisualProvider_Split1125, the notch layout, even with
 * the island on. It centres the time in the 83 pt left of a 209 pt notch, nudged by +leadingCenteringOffset
 * (-0.667). That nudge is moved left by lead/2 (the same feel `lead` had: lead=20 -> about 10 pt left).
 */
static double sbs_notch_shift;
static double (*sbs_orig_lco)(id, SEL);

static double
sbs_lco(id self, SEL cmd)
{
	double v = sbs_orig_lco(self, cmd), r = v - sbs_lead / 2 - sbs_notch_shift;
	static int told;

	if (told++ < 2) {
		sbs_log("Split1125 leadingCenteringOffset %.2f -> %.2f", v, r);
	}
	return r;
}

/*
 * UIKit derives the right side from the left: trailingCenteringEdgeInset = leadingCenteringEdgeInset +
 * +trailingCenteringOffset (UIKitCore 0x189ab0cd0). Moving the time left therefore pushed the battery side right by
 * the same amount (user 2026-11-13: "the battery ... too much to the right"). It is given back here, plus `trail`
 * points more inward (conf trail=, default 0). Added on Split1125's own metaclass (the method is inherited).
 */
static double sbs_trail = 0;
static double (*sbs_orig_tco)(id, SEL);

static double
sbs_tco(id self, SEL cmd)
{
	double v = sbs_orig_tco(self, cmd), r = v + sbs_lead / 2 + sbs_trail;    /* (no notch shift: it is derived from the left, already corrected) */
	static int told;

	if (told++ < 2) {
		sbs_log("Split1125 trailingCenteringOffset %.2f -> %.2f", v, r);
	}
	return r;
}

/*
 * The side areas are (screen width - notchSize.width) / 2 wide (UIKitCore 0x189ab1044): with the iPhone X's 209 pt
 * notch the left one is ~83 pt, so a longer carrier text ("... | Jio" on the lock screen) scrolled although the S20's
 * hole is small (user 2026-11-13). +notchSize's width is reported as `notch` (conf notch=, default 125; 0 = Apple's).
 * The centring points move inward by (209 - notch) / 4 with it (leadingCenteringEdgeInset = notchRect.x / 2 + ...),
 * so lco/tco take that back: the time and the battery stay where lead/trail put them.
 */
struct sbs_size { double w, h; };
static double sbs_notch = 0;
static struct sbs_size (*sbs_orig_notch)(id, SEL);


static struct sbs_size
sbs_notch_size(id self, SEL cmd)
{
	struct sbs_size v = sbs_orig_notch(self, cmd);

	if (sbs_notch > 0 && sbs_notch < v.w) {
		sbs_notch_shift = (v.w - sbs_notch) / 4;
		v.w = sbs_notch;
	}
	return v;
}

static void
sbs_hook(void *unused)
{
	{
		Class sc = objc_getClass("_UIStatusBarVisualProvider_Split1125");
		Method nm = sc ? class_getClassMethod(sc, sel_registerName("notchSize")) : NULL;
		if (nm != NULL && sbs_orig_notch == NULL && sbs_notch > 0) {
			sbs_orig_notch = (struct sbs_size (*)(id, SEL))method_getImplementation(nm);
			struct sbs_size o = sbs_orig_notch((id)sc, sel_registerName("notchSize"));
			if (sbs_notch < o.w) {
				sbs_notch_shift = (o.w - sbs_notch) / 4;
			}
			if (!class_addMethod(object_getClass((id)sc), sel_registerName("notchSize"), (IMP)sbs_notch_size,
			    method_getTypeEncoding(nm))) {
				method_setImplementation(nm, (IMP)sbs_notch_size);
			}
		}
	}
	{
		Class sc = objc_getClass("_UIStatusBarVisualProvider_Split1125");
		SEL ts = sel_registerName("trailingCenteringOffset");
		Method tm = sc ? class_getClassMethod(sc, ts) : NULL;
		if (tm != NULL && sbs_orig_tco == NULL && (sbs_lead > 0 || sbs_trail != 0)) {
			sbs_orig_tco = (double (*)(id, SEL))method_getImplementation(tm);
			if (!class_addMethod(object_getClass((id)sc), ts, (IMP)sbs_tco, method_getTypeEncoding(tm))) {
				method_setImplementation(class_getClassMethod(sc, ts), (IMP)sbs_tco);   /* (it was Split1125's own) */
			}
		}
	}
	{
		Class sc = objc_getClass("_UIStatusBarVisualProvider_Split1125");
		Method lm = sc ? class_getClassMethod(sc, sel_registerName("leadingCenteringOffset")) : NULL;
		if (lm != NULL && sbs_orig_lco == NULL && sbs_lead > 0) {
			sbs_orig_lco = (double (*)(id, SEL))method_setImplementation(lm, (IMP)sbs_lco);
		}
	}
	{
		Class dc = objc_getClass("_UIStatusBarVisualProvider_DynamicSplit");
		Method um = dc ? class_getInstanceMethod(dc, sel_registerName("setupInContainerView:")) : NULL;
		if (um != NULL && sbs_orig_setup == NULL && sbs_cut > 0) {
			sbs_orig_setup = (id (*)(id, SEL, id))method_setImplementation(um, (IMP)sbs_setup);
		}
	}
	{
		Class dc = objc_getClass("_UIStatusBarVisualProvider_DynamicSplit");
		Method sm = dc ? class_getInstanceMethod(dc, sel_registerName("setCutoutWidthConstraint:")) : NULL;
		if (sm != NULL && sbs_orig_set_cut == NULL && sbs_cut > 0) {
			sbs_orig_set_cut = (void (*)(id, SEL, id))method_setImplementation(sm, (IMP)sbs_set_cut);
		}
	}
	{
		Class dc = objc_getClass("_UIStatusBarVisualProvider_DynamicSplit");
		Method am = dc ? class_getInstanceMethod(dc,
		    sel_registerName("_needsUpdateOfConstraintsForAvoidanceFrame:cutoutOffset:cutoutWidth:")) : NULL;
		if (am != NULL && sbs_orig_avoid == NULL && sbs_cut > 0) {
			sbs_orig_avoid = (bool (*)(id, SEL, struct sbs_rect, double *, double *))method_setImplementation(am,
			    (IMP)sbs_avoid);
		}
	}
	Class c = objc_getClass("_UIStatusBarVisualProvider_DynamicSplit");
	Method m = c ? class_getInstanceMethod(c, sel_registerName("edgeInsets")) : NULL;

	(void)unused;
	if (m != NULL && sbs_orig == NULL) {
		sbs_orig = (struct sbs_insets (*)(id, SEL))method_setImplementation(m, (IMP)sbs_edge_insets);
		sbs_log("hooks: edgeInsets %.0f, avoidance/setup/constraint %.0f", 1, sbs_orig_avoid && sbs_orig_setup && sbs_orig_set_cut);
	} else if (m == NULL) {
		static int told;
		if (told++ < 1) {
			sbs_log("hooks: DynamicSplit not there yet (%.0f %.0f)", unused != NULL, 0);
		}
	}
}

/*
 * The notch layout at 2x (A, 2026-11-14). At 720 x 1600 the kernel has iOS draw at 2 pixels a point (750 x 1624,
 * MiniIOMobileFramebuffer); UIKit picks the status bar's layout by the screen's pixels and has none for an iPhone X
 * at 750, so it fell back to its debug bar (red, "rdar:45025538"). Whatever it picks that is not a notch layout
 * ("Split") becomes the one the 3x screen had, _UIStatusBarVisualProvider_Split1125 (same 375 x 812 points).
 */
static Class (*sbs_orig_vps)(id, SEL, id, id);

static Class
sbs_vps(id self, SEL cmd, id screen, id info)
{
	Class c = sbs_orig_vps(self, cmd, screen, info);
	Class split = objc_getClass("_UIStatusBarVisualProvider_Split1125");
	static int told;

	if (split != NULL && (c == NULL || strstr(class_getName(c), "Split") == NULL)) {
		if (!told) {
			told = 1;
			FILE *f = fopen("/var/mobile/Library/Logs/redwood-statusbar.log", "a");
			if (f != NULL) {
				fprintf(f, "statusbar: pid %d provider %s -> Split1125\n", getpid(), c ? class_getName(c) : "nil");
				fclose(f);
			}
		}
		return split;
	}
	return c;
}

static void
sbs_provider_hook(void *unused)
{
	Class ic = objc_getClass("_UIStatusBarVisualProvider_iOS");
	SEL sel = sel_registerName("visualProviderSubclassForScreen:visualProviderInfo:");
	Method m = ic ? class_getClassMethod(ic, sel) : NULL;

	(void)unused;
	if (m != NULL && sbs_orig_vps == NULL) {
		sbs_orig_vps = (Class (*)(id, SEL, id, id))method_setImplementation(m, (IMP)sbs_vps);
	}
}

/*
 * Island phones (A, 2026-11-15). The status bar keeps the iPhone X notch layout (Split1125, see above), and a notch
 * layout shows background activity -- a call, the microphone recording, navigation -- as a coloured pill around the
 * time. An iPhone with a Dynamic Island shows those in the island and leaves the time plain (user 2026-11-15: "when
 * the dynamic island is present it should be regular time"; the pill is for phones without one). So when MobileGestalt
 * says this is an island phone (ArtworkDeviceSubType 2556 or 2796, what island=1 sets in the device tree) the status
 * bar's background-activity entry reads as disabled. Without the island (island=0, other devices) nothing is hooked
 * and the pill stays, as on a notch iPhone. The island itself is SpringBoard's SystemAperture and is not touched.
 * (Hooked on the entry's own class only; if that class has no isEnabled, the data's backgroundActivityEntry getter
 * answers nil instead. Log: which one, in redwood-statusbar.log.)
 */
/* (2026-11-15) MobileGestalt answers ArtworkDeviceSubType to entitled processes only (nil in apps and SpringBoard's
 * libraries here), so the device tree's /product artwork-device-subtype is read first -- the very property island=1
 * sets (xnuloader/loader.c), readable by any process. MobileGestalt stays as a second opinion. */
extern unsigned int IORegistryEntryFromPath(unsigned int, const char *);
extern CFTypeRef IORegistryEntryCreateCFProperty(unsigned int, CFStringRef, CFAllocatorRef, unsigned int);
extern int IOObjectRelease(unsigned int);

/* On y2s the payload boot arg is authoritative: a status bar that cannot read IOKit (or reads it
 * before the product node is published) must still behave like an island phone. Gate on the
 * y2s-only cam_s20_y2s arg so x1slte's IOKit-only behaviour is exactly as before. */
static bool
sbs_boot_arg_is_one(const char *name)
{
	char args[1024], value[64];
	size_t size = sizeof(args) - 1, n = strlen(name);
	const char *p;

	if (sysctlbyname("kern.bootargs", args, &size, NULL, 0) != 0) {
		return false;
	}
	args[size < sizeof(args) ? size : sizeof(args) - 1] = 0;
	for (p = args; *p != 0;) {
		while (*p == ' ') {
			p++;
		}
		if (strncmp(p, name, n) == 0 && p[n] == '=') {
			size_t i = 0;

			for (p += n + 1; *p != 0 && *p != ' ' && i + 1 < sizeof(value); p++) {
				value[i++] = *p;
			}
			value[i] = 0;
			return strcmp(value, "1") == 0;
		}
		while (*p != 0 && *p != ' ') {
			p++;
		}
	}
	return false;
}

static bool
sbs_island_present(void)
{
	static int cached = -1;

	if (cached < 0) {
		const bool boot_island = sbs_boot_arg_is_one("cam_s20_y2s") &&
		    sbs_boot_arg_is_one("island");
		int subtype = 0;
		unsigned int e = IORegistryEntryFromPath(0, "IODeviceTree:/product");

		if (e != 0) {
			CFTypeRef v = IORegistryEntryCreateCFProperty(e, CFSTR("artwork-device-subtype"), NULL, 0);
			if (v != NULL) {
				if (CFGetTypeID(v) == CFDataGetTypeID() && CFDataGetLength((CFDataRef)v) >= 4) {
					const unsigned char *p = CFDataGetBytePtr((CFDataRef)v);
					subtype = p[0] | p[1] << 8 | p[2] << 16 | p[3] << 24;
				}
				CFRelease(v);
			}
			IOObjectRelease(e);
		}
		if (subtype == 0) {
			void *mg = dlopen("/usr/lib/libMobileGestalt.dylib", RTLD_LAZY);
			CFTypeRef (*copy)(CFStringRef, CFDictionaryRef) = mg ? (CFTypeRef (*)(CFStringRef, CFDictionaryRef))dlsym(mg, "MGCopyAnswer") : NULL;
			CFTypeRef v = copy ? copy(CFSTR("ArtworkDeviceSubType"), NULL) : NULL;
			if (v != NULL) {
				if (CFGetTypeID(v) == CFNumberGetTypeID()) {
					CFNumberGetValue((CFNumberRef)v, kCFNumberIntType, &subtype);
				}
				CFRelease(v);
			}
		}
		cached = boot_island || subtype == 2556 || subtype == 2796;
		/* Keep the two-number log line: show 2556 when the boot arg is the reason. */
		sbs_log("island: artwork subtype %.0f (island %.0f)", boot_island && subtype != 2556 &&
		    subtype != 2796 ? 2556.0 : (double)subtype, (double)cached);
	}
	return cached == 1;
}
/*
 * The bolt next to the battery (2026-11-15): with the percentage shown inside the battery, iOS 16 draws the charging
 * bolt as a separate display item of _UIStatusBarBatteryItem (+chargingDisplayIdentifier), not through _UIBatteryView's
 * _shouldShowBolt. The bolt is kept (the user: the symbol stays, only the animation is redundant with the island's):
 * the animation iOS returns for that display item is dropped, so it appears and goes without animating.
 */
static id (*sbs_orig_battery_apply)(id, SEL, id, id);
static id
sbs_battery_apply(id self, SEL cmd, id update, id item)
{
	id r = sbs_orig_battery_apply(self, cmd, update, item);
	static id charging_id;

	if (charging_id == nil) {
		charging_id = ((id (*)(id, SEL))objc_msgSend)((id)objc_getClass("_UIStatusBarBatteryItem"), sel_registerName("chargingDisplayIdentifier"));
	}
	id ident = item != nil ? ((id (*)(id, SEL))objc_msgSend)(item, sel_registerName("identifier")) : nil;
	if (charging_id != nil && ident != nil && ((bool (*)(id, SEL, id))objc_msgSend)(ident, sel_registerName("isEqual:"), charging_id)) {
		return nil;     /* the bolt stays; only its appear/disappear animation goes (the island animates charging) */
	}
	return r;
}
static bool
sbs_bg_disabled(id self, SEL cmd)
{
	(void)self; (void)cmd;
	return false;
}
static id
sbs_bg_none(id self, SEL cmd)
{
	(void)self; (void)cmd;
	return nil;
}
static void
sbs_island_hook(void *unused)
{
	static int done;
	Class ec = objc_getClass("_UIStatusBarDataBackgroundActivityEntry");
	SEL es = sel_registerName("isEnabled");
	Method em = ec ? class_getInstanceMethod(ec, es) : NULL;

	(void)unused;
	if (done || !sbs_island_present()) {
		return;
	}
	if (!sbs_bolt) {
		/* the bolt beside the battery (every process: SpringBoard's status bar and apps') */
		Class ic = objc_getClass("_UIStatusBarBatteryItem");
		Method am = ic ? class_getInstanceMethod(ic, sel_registerName("applyUpdate:toDisplayItem:")) : NULL;
		if (am != NULL && sbs_orig_battery_apply == NULL) {
			sbs_orig_battery_apply = (id (*)(id, SEL, id, id))method_setImplementation(am, (IMP)sbs_battery_apply);
			sbs_log("island: charging bolt animation off%.0f%.0f", 0, 0);
		}
	}
	if (em != NULL) {
		if (!class_addMethod(ec, es, (IMP)sbs_bg_disabled, method_getTypeEncoding(em))) {
			method_setImplementation(em, (IMP)sbs_bg_disabled);         /* (the class's own method) */
		}
		done = 1;
		sbs_log("island: background-activity pill off (entry isEnabled)%.0f%.0f", 0, 0);
		return;
	}
	Class dc = objc_getClass("_UIStatusBarData");
	SEL gs = sel_registerName("backgroundActivityEntry");
	Method gm = dc ? class_getInstanceMethod(dc, gs) : NULL;
	if (gm != NULL) {
		method_setImplementation(gm, (IMP)sbs_bg_none);
		done = 1;
		sbs_log("island: background-activity pill off (data getter)%.0f%.0f", 0, 0);
	}
}

/* the icons' size: the notch layout's normalIconScale times `icons` (Split1125's own instance method) */
static double (*sbs_orig_icon_scale)(id, SEL);
static double
sbs_icon_scale(id self, SEL cmd)
{
	return sbs_orig_icon_scale(self, cmd) * sbs_icons;
}
static void
sbs_icons_hook(void *unused)
{
	Class sc = objc_getClass("_UIStatusBarVisualProvider_Split1125");
	SEL s = sel_registerName("normalIconScale");
	Method m = sc ? class_getInstanceMethod(sc, s) : NULL;

	(void)unused;
	if (m == NULL || sbs_orig_icon_scale != NULL || sbs_icons <= 0.5 || sbs_icons >= 2 || sbs_icons == 1) {
		return;
	}
	sbs_orig_icon_scale = (double (*)(id, SEL))method_getImplementation(m);
	if (!class_addMethod(sc, s, (IMP)sbs_icon_scale, method_getTypeEncoding(m))) {
		method_setImplementation(m, (IMP)sbs_icon_scale);      /* (Split1125's own) */
	}
	sbs_log("icons: x%.2f (%.0f)", sbs_icons, 0);
}

static void
statusbar_shift_start(void)
{
	FILE *f = fopen("/var/jb/etc/redwood-statusbar.conf", "r");
	char b[128];

	sbs_provider_hook(NULL);                /* always (cheap: one class method, only acts off the notch layouts) */
	dispatch_async_f(dispatch_get_main_queue(), NULL, sbs_provider_hook);

	if (f != NULL) {
		size_t n = fread(b, 1, sizeof(b) - 1, f);
		fclose(f);
		b[n] = 0;
		char *p = strstr(b, "lead=");
		if (p != NULL) {
			sbs_lead = atof(p + 5);
		}
		p = strstr(b, "notch=");
		if (p != NULL) {
			sbs_notch = atof(p + 6);
		}
		p = strstr(b, "trail=");
		if (p != NULL) {
			sbs_trail = atof(p + 6);
		}
		p = strstr(b, "icons=");
		if (p != NULL) {
			sbs_icons = atof(p + 6);
		}
		p = strstr(b, "bolt=");
		if (p != NULL) {
			sbs_bolt = atoi(p + 5);
		}
		p = strstr(b, "cut=");
		if (p != NULL) {
			sbs_cut = atof(p + 4);
		}
	}
	sbs_icons_hook(NULL);                   /* every phone: the icons' size */
	dispatch_async_f(dispatch_get_main_queue(), NULL, sbs_icons_hook);
	sbs_island_hook(NULL);                  /* island phones only: plain time and no bolt, the island shows those */
	dispatch_async_f(dispatch_get_main_queue(), NULL, sbs_island_hook);
	if (sbs_lead <= 0 && sbs_cut <= 0 && sbs_trail == 0 && sbs_notch <= 0) {
		return;                         /* the default: Apple's status bar, nothing hooked */
	}
	/*
	 * At once, from the library's constructor: UIKitCore is mapped (a dependency of every UI process) and its classes
	 * are registered before any constructor runs. (2026-11-13: hooked from the main queue only, the status bar could
	 * be laid out first; the cutout is only re-measured when the island changes, so after a boot the time stayed at
	 * Apple's place until a Live Activity came and went.) The main queue again as a fallback.
	 */
	sbs_hook(NULL);
	dispatch_async_f(dispatch_get_main_queue(), NULL, sbs_hook);
}
