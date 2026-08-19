import QtQuick
import QtQuick.Layouts
import QmlComponents 1.0

/**
 * CServerConfigDialog.qml - pick or enter the DBAL server URL.
 *
 * Edits a local draft and only writes to ServerConfig on Save, so dismissing
 * the dialog leaves a working app pointed where it was. Emits applied() so the
 * caller can re-ping without this component knowing anything about DBAL.
 */
CDialog {
    id: root
    objectName: "dialog_server_config"
    title: "Server"

    property string draft: ServerConfig.url
    readonly property bool draftValid: ServerConfig.looksValid(draft)
    readonly property bool draftIsCustom:
        draft.length > 0 && !ServerConfig.isPreset(draft)

    signal applied(string url)

    // Reseed each time it opens: the draft must reflect the live setting, not
    // whatever was typed and abandoned last time.
    onOpened: draft = ServerConfig.url

    ColumnLayout {
        spacing: 12
        width: 360

        CText {
            variant: "caption"
            text: "Known servers"
            Layout.fillWidth: true
        }
        CSelect {
            id: picker
            Layout.fillWidth: true
            model: ServerConfig.options
            currentIndex: Math.max(0,
                ServerConfig.options.indexOf(root.draft))
            Accessible.role: Accessible.ComboBox
            Accessible.name: "Known servers"
            onActivated: root.draft = ServerConfig.options[currentIndex]
        }

        CText {
            variant: "caption"
            text: "Server URL"
            Layout.fillWidth: true
        }
        CTextField {
            Layout.fillWidth: true
            placeholderText: "http://localhost:8080"
            text: root.draft
            // Guard against the binding loop between this field and the
            // dropdown: both write draft, and draft writes back here.
            onTextChanged: if (text !== root.draft) root.draft = text
            Accessible.role: Accessible.EditableText
            Accessible.name: "Server URL"
        }

        CText {
            Layout.fillWidth: true
            variant: "caption"
            wrapMode: Text.Wrap
            color: root.draftValid ? Theme.textSecondary : Theme.error
            text: root.draftValid
                ? "Applies to every view; saved for next launch."
                : "Enter a full URL, e.g. http://localhost:8080"
        }

        FlexRow {
            Layout.fillWidth: true
            spacing: 12

            CButton {
                text: "Forget"
                variant: "ghost"
                visible: root.draftIsCustom
                    && ServerConfig.custom.indexOf(root.draft) >= 0
                Accessible.role: Accessible.Button
                Accessible.name: "Forget this server"
                onClicked: {
                    ServerConfig.forget(root.draft)
                    root.draft = ServerConfig.url
                }
            }
            Item { Layout.fillWidth: true }
            CButton {
                text: "Cancel"
                variant: "ghost"
                Accessible.role: Accessible.Button
                Accessible.name: "Cancel"
                Keys.onReturnPressed: root.close()
                Keys.onSpacePressed: root.close()
                onClicked: root.close()
            }
            CButton {
                text: "Save"
                variant: "primary"
                enabled: root.draftValid
                Accessible.role: Accessible.Button
                Accessible.name: "Save server URL"
                Keys.onReturnPressed: root.save()
                Keys.onSpacePressed: root.save()
                onClicked: root.save()
            }
        }
    }

    function save() {
        if (!draftValid)
            return
        if (ServerConfig.use(draft)) {
            // Keep the C++ client in step; it holds its own baseUrl.
            if (typeof DBALClient !== "undefined" && DBALClient)
                DBALClient.baseUrl = ServerConfig.url
            applied(ServerConfig.url)
        }
        close()
    }
}
