import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QmlComponents 1.0

/**
 * CScrollPage.qml - scrollable page body that is sized correctly by
 * construction.
 *
 * Exists because the hand-rolled equivalent has a trap that has bitten this
 * codebase repeatedly:
 *
 *     ScrollView {                 // no contentWidth
 *         ColumnLayout {
 *             width: parent.width  // parent is the content item, whose width
 *         }                        // comes from the content -- circular, so
 *     }                            // it settles on an implicit width and
 *                                  // clips at ~half the window.
 *
 * Here contentWidth is bound to availableWidth and the content column is
 * driven from the same value, so the cycle cannot form. Use `padding` for
 * insets rather than anchors.margins -- padding reduces availableWidth, so
 * the column stays in step with it.
 *
 * Usage:
 *     CScrollPage {
 *         padding: 24
 *         CText { text: "Title" }
 *         SomeCard { Layout.fillWidth: true }
 *     }
 *
 * Children are placed in a ColumnLayout, so size them with Layout.* attached
 * properties -- not anchors.
 */
ScrollView {
    id: page

    default property alias content: column.data
    property alias spacing: column.spacing

    clip: true
    // The single line every open-coded ScrollView in this repo omitted.
    contentWidth: availableWidth

    ColumnLayout {
        id: column
        width: page.availableWidth
        spacing: 20
    }
}
