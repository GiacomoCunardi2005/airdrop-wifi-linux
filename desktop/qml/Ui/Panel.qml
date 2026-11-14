import QtQuick
import qs.Commons as Commons

// GNOME hosts the original Omdrop panel without Omarchy's bar/controller.
Item {
    id: root
    property QtObject bar: null
    property string moduleName: ""
    property string ipcTarget: ""
    property bool manageIpc: false
    property var settings: ({})
    property alias controller: controller
    readonly property bool opened: controller.open
    readonly property color barForeground: Commons.Color.foreground
    function setting(name, fallback) { return settings[name] ?? fallback }
    function open() { controller.show() }
    function close() { controller.hide() }
    function toggle() { controller.toggle() }
    PanelController { id: controller }
}
