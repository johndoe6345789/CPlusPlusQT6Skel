import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

import "MaterialPalette.qml" as MaterialPalette

Rectangle {
    id: skeleton
    property bool animated: true
    property color baseColor: MaterialPalette.surfaceVariant
    property color highlightColor: MaterialPalette.surface
    radius: 8
    color: baseColor
    implicitWidth: 120
    implicitHeight: 20

    Rectangle {
        id: shimmer
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: Qt.rgba(highlightColor.r,
                highlightColor.g, highlightColor.b, 0) }
            GradientStop { position: 0.5; color: highlightColor }
            GradientStop { position: 1.0; color: Qt.rgba(highlightColor.r,
                highlightColor.g, highlightColor.b, 0) }
        }
        // The shimmer below loops forever, which repaints the scene at
        // display refresh for as long as it runs. Skeletons are
        // placeholders in views that may never be shown, so tie it to
        // actual visibility rather than leaving it always on.
        readonly property bool shimmering: animated && visible
        opacity: shimmering ? 1 : 0
        NumberAnimation on x {
            running: parent.shimmering
            duration: 1100
            from: -width
            to: width
            loops: Animation.Infinite
            easing.type: Easing.InOutQuad
        }
    }
}
