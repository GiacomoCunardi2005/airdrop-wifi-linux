import QtQuick

// The GNOME indicator supplies the bar icon; the QML button stays hidden.
Item {
    property QtObject bar: null
    property Component iconComponent
    signal pressed(int buttonCode)
    visible: false
}
