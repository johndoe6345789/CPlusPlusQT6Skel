import QtQuick
import QtQuick.Layouts
import QmlComponents 1.0

Rectangle {
    id: root

    property var stats: ({ users: "0", packages: "0", workflows: "0",
        backends: "0" })
    property color accentColor: "#6366F1"
    property bool isDark: false

    readonly property color onSurfaceVariant: Theme.textSecondary
    readonly property color outlineVariant: isDark
        ? Qt.rgba(1, 1, 1, 0.06) : Qt.rgba(0, 0, 0, 0.08)

    // A value and its label sit side by side in roughly 150px. With the 60px
    // side margins that means four across needs ~720px; below that the cells
    // start eliding the numbers themselves ("1,2... USE...") which is worse
    // than wrapping. Reflow to 2x2 and stack each value over its label.
    readonly property bool compact: width < 720
    readonly property int columnCount: compact ? 2 : 4

    implicitHeight: compact ? 148 : 88
    color: isDark ? Qt.rgba(1, 1, 1, 0.05) : Qt.rgba(0.31, 0.31, 0.44, 0.06)

    GridLayout {
        anchors.fill: parent
        anchors.leftMargin: compact ? 12 : 60
        anchors.rightMargin: compact ? 12 : 60
        columns: root.columnCount
        columnSpacing: 0
        rowSpacing: 0

        Repeater {
            model: [
                { label: "USERS",     value: stats.users },
                { label: "PACKAGES",  value: stats.packages },
                { label: "WORKFLOWS", value: stats.workflows },
                { label: "BACKENDS",  value: stats.backends }
            ]
            delegate: Item {
                Layout.fillWidth: true
                Layout.fillHeight: true

                GridLayout {
                    anchors.centerIn: parent
                    width: parent.width - 8
                    columns: root.compact ? 1 : 2
                    columnSpacing: 10
                    rowSpacing: 1

                    CText {
                        text: modelData.value
                        font.pixelSize: root.compact ? 20 : 24
                        font.weight: Font.Bold
                        font.family: "monospace"
                        color: root.accentColor
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                        horizontalAlignment: root.compact
                            ? Text.AlignHCenter : Text.AlignRight
                    }
                    CText {
                        text: modelData.label
                        font.pixelSize: 10
                        font.family: "monospace"
                        font.letterSpacing: root.compact ? 1 : 2
                        color: onSurfaceVariant
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                        horizontalAlignment: root.compact
                            ? Text.AlignHCenter : Text.AlignLeft
                    }
                }

                // Divider between columns only -- never after the last cell
                // in a row, or it hangs off the edge of the strip.
                Rectangle {
                    visible: (index % root.columnCount)
                        < root.columnCount - 1
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    width: 1
                    height: 32
                    color: outlineVariant
                }
            }
        }
    }
}
