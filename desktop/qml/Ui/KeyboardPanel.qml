import QtQuick
import QtQuick.Window
import qs.Commons
import qs.Commons as Commons

// GNOME has no layer-shell: use an XWayland tool window for the original card.
Window {
    id: root
    property Item anchorItem
    property Item owner
    property QtObject bar
    property Item focusTarget
    property bool open: false
    property real contentWidth: 300
    property real contentHeight: 0
    default property alias contents: content.data
    function fittedContentWidth(value) { return Math.min(value, Screen.width - 48) }
    function fittedContentHeight(value) { return value }
    title: "AirDrop — Owly"
    transientParent: null
    flags: Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
    color: Commons.Color.background
    width: contentWidth + 36
    height: Math.min(contentHeight + 36, Screen.height - 80)
    x: Screen.virtualX + Screen.width - width - 16
    y: Screen.virtualY + 40
    visible: open
    onVisibleChanged: if (visible) {
        requestActivate()
        Qt.callLater(function() { if (focusTarget) focusTarget.forceActiveFocus() })
    }
    onActiveChanged: if (!active && visible && owner) owner.close()
    onClosing: function(event) {
        event.accepted = false
        owner.close()
    }
    Rectangle {
        anchors.fill: parent
        color: "transparent"
        border.color: Qt.darker(Commons.Color.foreground, 2.0)
        border.width: 1
    }
    Flickable {
        anchors.fill: parent
        anchors.margins: 18
        contentWidth: width
        contentHeight: root.contentHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        Item {
            id: content
            width: root.contentWidth
            height: root.contentHeight
        }
    }
}
