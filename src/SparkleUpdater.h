#ifndef SPARKLEUPDATER_H
#define SPARKLEUPDATER_H

// Thin C++ facade over Sparkle, which is Objective-C. Implemented in
// SparkleUpdater.mm and compiled only when the sparkle feature is enabled;
// the no-op fallback below keeps main.cpp free of #ifdefs on other platforms.
namespace updater {

// Starts the Sparkle updater. Safe to call once, after QGuiApplication is
// constructed. Reads SUFeedURL and SUPublicEDKey from the bundle Info.plist,
// so an unsigned or unbundled build simply does nothing.
void start();

// User-initiated "Check for Updates…" -- shows UI even when up to date.
void checkNow();

} // namespace updater

#endif // SPARKLEUPDATER_H
