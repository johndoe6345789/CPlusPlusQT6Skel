import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QmlComponents 1.0

Rectangle {
    id: root
    objectName: "section_hero"
    Accessible.role: Accessible.Pane
    Accessible.name: "MetaBuilder Hero"

    property string platformVersion: "0.9.1"
    property bool isDark: false

    signal getStarted()
    signal openStorybook()
    signal openPackages()

    readonly property color accentBlue: "#6366F1"
    readonly property color primaryContainer:
        isDark
            ? Qt.rgba(accentBlue.r,
                accentBlue.g, accentBlue.b, 0.15)
            : Qt.rgba(accentBlue.r,
                accentBlue.g, accentBlue.b, 0.12)
    readonly property color onSurface: Theme.text
    readonly property color onSurfaceVariant: Theme.textSecondary

    // Below this the three call-to-action buttons no longer fit on one row
    // and the 52px display type overflows the window.
    readonly property bool compact: width < 640

    color: "transparent"
    // Height has to follow the content once things stack, otherwise the
    // buttons are pushed outside the section and get clipped by the strip
    // below. Keep the roomy fixed height on desktop.
    implicitHeight: compact
        ? content.implicitHeight + 48
        : 400

    Rectangle {
        anchors.fill: parent; gradient: Gradient {
            GradientStop {
                position: 0.0
                color: isDark
                    ? Qt.rgba(0.39,0.4,0.95,0.06)
                    : Qt.rgba(0.30,0.40,0.90,0.12)
            }
            GradientStop {
                position: 0.7
                color: isDark
                    ? "transparent"
                    : Qt.rgba(0.35,0.45,0.88,0.04)
            }
            GradientStop { position: 1.0; color: "transparent" }
    } }

    ColumnLayout {
        id: content
        anchors.horizontalCenter: parent.horizontalCenter
        // Centring a content-sized column lets it spill past the section's
        // top edge, where the ScrollView clips it. Pin to the top instead
        // once the section is only as tall as its content.
        anchors.top: root.compact ? parent.top : undefined
        anchors.topMargin: root.compact ? 24 : 0
        anchors.verticalCenter: root.compact
            ? undefined : parent.verticalCenter
        anchors.verticalCenterOffset: root.compact ? 0 : 16
        width: Math.min(parent.width - (root.compact ? 32 : 80), 720)
        spacing: root.compact ? 12 : 16

        CVersionPill {
            Layout.alignment: Qt.AlignHCenter
            version: platformVersion
            accent: accentBlue
            containerColor: primaryContainer
        }

        CText {
            text: "MetaBuilder"
            // Scale with the window instead of clipping; the lower bound
            // keeps it legible on a phone, the upper keeps the desktop look.
            font.pixelSize: Math.max(30, Math.min(52, root.width * 0.11))
            font.weight: Font.Black
            font.letterSpacing: root.compact ? -1 : -2
            color: onSurface
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            horizontalAlignment: Text.AlignHCenter
        }

        CText {
            text: "The universal platform for"
                + " building data-driven"
                + " applications."
            font.pixelSize: root.compact ? 15 : 17
            color: onSurfaceVariant
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            horizontalAlignment: Text.AlignHCenter
        }

        CText {
            // The interpuncts read as one long unbreakable run on a narrow
            // screen, so break onto separate lines instead of overflowing.
            text: root.compact
                ? "95% JSON config\n"
                    + "5% infrastructure\n"
                    + "Desktop + Web + CLI"
                : "95% JSON config  ·  "
                    + "5% infrastructure  ·  "
                    + "Desktop + Web + CLI"
            font.pixelSize: root.compact ? 12 : 13
            font.family: "monospace"
            color: onSurfaceVariant
            opacity: isDark ? 0.4 : 0.55
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            horizontalAlignment: Text.AlignHCenter
        }

        GridLayout {
            Layout.fillWidth: true
            Layout.topMargin: root.compact ? 12 : 20
            // Stack into a single full-width column rather than letting the
            // row run off the edge.
            columns: root.compact ? 1 : 3
            columnSpacing: 12
            rowSpacing: 8

            CButton {
                text: "Get Started"
                variant: "primary"; size: "lg"
                Layout.fillWidth: root.compact
                Layout.alignment: Qt.AlignHCenter
                activeFocusOnTab: true
                Accessible.role: Accessible.Button
                Accessible.name: "Get Started"
                Keys.onReturnPressed: root.getStarted()
                Keys.onSpacePressed: root.getStarted()
                onClicked: root.getStarted()
            }
            CButton {
                text: "Storybook"
                variant: "ghost"; size: "lg"
                Layout.fillWidth: root.compact
                Layout.alignment: Qt.AlignHCenter
                activeFocusOnTab: true
                Accessible.role: Accessible.Button
                Accessible.name: "Open Storybook"
                Keys.onReturnPressed:
                    root.openStorybook()
                Keys.onSpacePressed:
                    root.openStorybook()
                onClicked: root.openStorybook()
            }
            CButton {
                text: "Packages"
                variant: "ghost"; size: "lg"
                Layout.fillWidth: root.compact
                Layout.alignment: Qt.AlignHCenter
                activeFocusOnTab: true
                Accessible.role: Accessible.Button
                Accessible.name: "Open Packages"
                Keys.onReturnPressed:
                    root.openPackages()
                Keys.onSpacePressed:
                    root.openPackages()
                onClicked: root.openPackages()
            }
        }
    }
}
