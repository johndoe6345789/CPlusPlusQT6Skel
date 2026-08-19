pragma Singleton
import QtQuick
import QtCore

/**
 * ServerConfig.qml - the DBAL server URL, in one place.
 *
 * Twenty files instantiate their own DBALProvider, and DBALClient keeps a
 * separate baseUrl on the C++ side. Pointing the app at a different server
 * meant editing all of them, so nothing could be configured at runtime. They
 * all read from here instead, and this is what the settings dialog writes to.
 *
 * The chosen URL and any the user has typed are persisted, so the choice
 * survives a restart. The list is stored as JSON because QSettings round-trips
 * a string far more predictably than a QVariantList.
 */
QtObject {
    id: config

    // Servers offered out of the box. Kept separate from user entries so a
    // future release can change them without stranding what someone typed.
    readonly property var presets: [
        // nginx fronts DBAL at /api/dbal/ and strips that prefix before
        // proxying to the dbal container, so this is the base the app's
        // /health ping resolves against. The bare host:8080 hits the Next.js
        // app instead and every DBAL call 404s, which reads as "offline".
        "http://localhost:8080/api/dbal",
        "http://127.0.0.1:8080/api/dbal",
        "http://localhost:8080"
    ]

    property string url: presets[0]
    property var custom: []

    // What the dropdown shows: presets first, then anything the user added,
    // de-duplicated, and always including the current URL so a value loaded
    // from settings can never be missing from its own list.
    readonly property var options: {
        var seen = {}
        var out = []
        var all = presets.concat(custom)
        all.push(url)
        for (var i = 0; i < all.length; i++) {
            var u = (all[i] || "").trim()
            if (u.length && !seen[u]) {
                seen[u] = true
                out.push(u)
            }
        }
        return out
    }

    function isPreset(u) {
        return presets.indexOf((u || "").trim()) >= 0
    }

    // Accepts the URL and remembers it if it is not one we shipped.
    function use(u) {
        var v = (u || "").trim()
        if (!v.length)
            return false
        if (!isPreset(v) && custom.indexOf(v) < 0) {
            var next = custom.slice()
            next.push(v)
            custom = next
        }
        url = v
        return true
    }

    function forget(u) {
        var v = (u || "").trim()
        var i = custom.indexOf(v)
        if (i < 0)
            return
        var next = custom.slice()
        next.splice(i, 1)
        custom = next
        if (url === v)
            url = presets[0]
    }

    // Cheap sanity check for the dialog -- not validation of reachability,
    // just enough to catch an obviously malformed entry before saving.
    function looksValid(u) {
        return /^https?:\/\/[^\s/]+/.test((u || "").trim())
    }

    // Persisted form of `custom`. Declared here rather than inside Settings so
    // it is a real property of this object: a property declared inside the
    // Settings element is invisible to static analysis, and reading it back
    // trips qmllint even though it works at runtime.
    // QSettings round-trips a string far more predictably than a list.
    property string customJson: "[]"

    property Settings _store: Settings {
        category: "MetaBuilder.Server"
        property alias url: config.url
        property alias customJson: config.customJson
    }

    Component.onCompleted: {
        try {
            var parsed = JSON.parse(customJson)
            if (Array.isArray(parsed))
                custom = parsed
        } catch (e) {
            custom = []
        }
    }

    onCustomChanged: customJson = JSON.stringify(custom)
}
