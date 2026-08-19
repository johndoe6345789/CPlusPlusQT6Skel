#import <Sparkle/Sparkle.h>
#import <Foundation/Foundation.h>

#include "SparkleUpdater.h"

namespace {

// Retained for the lifetime of the process: Sparkle stops checking if the
// controller is deallocated.
SPUStandardUpdaterController *g_controller = nil;

} // namespace

namespace updater {

void start()
{
    if (g_controller)
        return;

    // Sparkle refuses to run without a feed URL and a public key, and an
    // ad-hoc signed build cannot install updates past Gatekeeper anyway.
    // Bail out quietly rather than surfacing an error the user cannot act on.
    NSDictionary *info = [[NSBundle mainBundle] infoDictionary];
    if (!info[@"SUFeedURL"] || !info[@"SUPublicEDKey"])
        return;

    g_controller =
        [[SPUStandardUpdaterController alloc] initWithStartingUpdater:YES
                                                     updaterDelegate:nil
                                                  userDriverDelegate:nil];
}

void checkNow()
{
    if (g_controller)
        [g_controller checkForUpdates:nil];
}

} // namespace updater
