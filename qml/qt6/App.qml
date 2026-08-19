import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtCore
import QmlComponents 1.0
import "qmllib/dbal"
import "qmllib/MetaBuilder"
import "qmllib/MetaBuilder/AppLogic.js" as Logic

ApplicationWindow {
    id: appWindow
    objectName: "appWindow"
    visible: true; width: 1400; height: 900
    // Floor matches the narrowest layout the views are designed for;
    // below this the grids have nowhere left to reflow to.
    minimumWidth: 360
    minimumHeight: 480
    title: "MetaBuilder Observatory"
    color: Theme.background

    DBALProvider { id: dbalProvider }

    property var appConfig: null
    property string currentTheme: "dark"
    property bool dbalConnected:
        dbalProvider.connected
    property int currentLevel: 1
    property string currentUser: ""
    property string currentRole: "public"
    property bool loggedIn: false
    property string authToken: ""
    property string currentView: "frontpage"
    readonly property var staticViews:
        appConfig ? appConfig.staticViews : []
    readonly property bool isDark:
        Theme.mode === "dark"

    function logout() {
        Logic.logout(appWindow, dbalProvider)
    }
    function viewIndex(v) {
        return Logic.viewIndex(appWindow)
    }
    function packageViewName(pkg) {
        return Logic.packageViewName(pkg)
    }

    header: CAppBar {
        objectName: "appBar"
        height: 48
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 16
            anchors.rightMargin: 12; spacing: 6
            CText {
                text: "MetaBuilder"
                font.pixelSize: 15
                font.weight: Font.Bold
                font.letterSpacing: -0.5
            }
            Rectangle {
                Layout.preferredWidth: 6; height: 6; radius: 3
                color: dbalProvider.connected
                    ? "#22C55E" : "#F43F5E"
                Layout.leftMargin: 2
            }
            Item { Layout.fillWidth: true }
            CNavBar {
                currentView: appWindow.currentView
                currentLevel: appWindow.currentLevel
                onNavigate: function(view) {
                    appWindow.currentView = view
                }
            }
            Item { Layout.fillWidth: true }
            Item { width: 4 }
            CLanguageSelector {
                visible: loggedIn
                isDark: appWindow.isDark
            }
            CNotificationBell {
                visible: loggedIn
                isDark: appWindow.isDark
                hasNotifications: true
            }
            CButton {
                visible: !loggedIn; text: "Login"
                variant: "primary"; size: "sm"
                activeFocusOnTab: true
                Accessible.role: Accessible.Button
                Accessible.name: "Login"
                Accessible.description: "Open login"
                Keys.onReturnPressed: currentView = "login"
                Keys.onSpacePressed: currentView = "login"
                onClicked: currentView = "login"
            }
            CUserMenu {
                visible: loggedIn
                username: currentUser
                level: currentLevel
                role: currentRole
                isDark: appWindow.isDark
                onNavigateTo: function(view) {
                    appWindow.currentView = view
                }
                onSignOut: logout()
            }
        }
    }

    Rectangle {
        id: dbalBanner; visible: !dbalConnected
        anchors {
            top: parent.top
            left: parent.left
            right: parent.right
        }
        height: 28; color: "#e65100"; z: 10
        CText {
            anchors.centerIn: parent
            variant: "caption"; color: "#fff"
            text: "DBAL Offline \u2014 "
                + "showing cached data"
        }
    }

    // Only ever visible in a release build: UpdateCheck.enabled is false for a
    // source build, where rebuilding is the update mechanism.
    Rectangle {
        id: updateBanner
        visible: UpdateCheck.enabled && UpdateCheck.updateAvailable
        anchors {
            top: dbalBanner.visible
                ? dbalBanner.bottom : parent.top
            left: parent.left
            right: parent.right
        }
        // Tall enough for a tappable control; a 28px band clipped the action.
        height: 34; color: "#1E7A3C"; z: 10

        readonly property bool compact: width < 420

        RowLayout {
            anchors.centerIn: parent
            width: Math.min(parent.width - 24, implicitWidth)
            spacing: 10

            CText {
                Layout.fillWidth: true
                variant: "caption"; color: "#fff"
                elide: Text.ElideRight
                horizontalAlignment: Text.AlignRight
                text: UpdateCheck.downloading
                    ? (updateBanner.compact
                        ? UpdateCheck.downloadPercent + "%"
                        : "Downloading " + UpdateCheck.latestVersion
                            + "\u2026 " + UpdateCheck.downloadPercent + "%")
                    : (updateBanner.compact
                        ? "v" + UpdateCheck.latestVersion + " available"
                        : "Version " + UpdateCheck.latestVersion
                            + " is available")
            }

            // Built from primitives rather than CButton: the native macOS
            // style discards a Control's custom background and contentItem,
            // which is what left the action mis-coloured and overflowing.
            Rectangle {
                id: updateAction
                visible: !UpdateCheck.downloading
                implicitWidth: actionLabel.implicitWidth + 20
                implicitHeight: 22
                radius: 11
                color: actionMouse.containsMouse
                    ? Qt.rgba(1, 1, 1, 0.28)
                    : Qt.rgba(1, 1, 1, 0.16)
                border.width: 1
                border.color: Qt.rgba(1, 1, 1, 0.45)

                Accessible.role: Accessible.Button
                Accessible.name: "Download update "
                    + UpdateCheck.latestVersion
                Accessible.onPressAction: UpdateCheck.download()

                Text {
                    id: actionLabel
                    anchors.centerIn: parent
                    text: "Download"
                    color: "#fff"
                    font.pixelSize: 11
                    font.weight: Font.DemiBold
                }
                MouseArea {
                    id: actionMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: UpdateCheck.download()
                }
            }
        }
    }

    RowLayout {
        anchors.fill: parent; spacing: 0
        // Bind to the banners' actual heights; a hardcoded offset silently
        // desynchronises the moment either banner changes size.
        anchors.topMargin:
            (dbalBanner.visible ? dbalBanner.height : 0)
            + (updateBanner.visible ? updateBanner.height : 0)
        CSidebar {
            objectName: "sidebar"
            currentView: appWindow.currentView
            currentLevel: appWindow.currentLevel
            loggedIn: appWindow.loggedIn
            Layout.preferredWidth: 220
            Layout.fillHeight: true
            packageViewName:
                appWindow.packageViewName
            onNavigate: function(view) {
                appWindow.currentView = view
            }
        }
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: "transparent"
            StackLayout {
                objectName: "mainContent"
                anchors.fill: parent
                currentIndex:
                    viewIndex(currentView)
                FrontPage {}
                LoginView {}
                DashboardView {}
                ProfileView {}
                ModeratorView {}
                AdminView {}
                GodPanel {}
                SuperGodPanel {}
                SettingsView {}
                CommentsView {}
                Repeater {
                    model: PackageLoader
                        ? PackageLoader.routablePackages()
                        : []
                    delegate: PackageViewLoader {
                        packageId:
                            modelData.packageId
                    }
                }
            }
        }
    }

    Settings {
        id: windowSettings
        category: "MetaBuilder"
        property alias windowWidth:
            appWindow.width
        property alias windowHeight:
            appWindow.height
        property alias windowX: appWindow.x
        property alias windowY: appWindow.y
        property alias theme:
            appWindow.currentTheme
        property alias authToken:
            appWindow.authToken
    }

    onCurrentThemeChanged: {
        if (typeof Theme.setTheme === "function")
            Theme.setTheme(currentTheme)
    }
    Component.onCompleted:
        Logic.autoLogin(appWindow, dbalProvider)
    CKeyboardShortcuts { appWindow: appWindow }
}
