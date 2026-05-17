import QtQuick
import QtQuick.Layouts
import ".."

RowLayout {
    id: root
    Layout.fillWidth: true
    spacing: Theme.spacingSm

    property string title: ""
    property string subtitle: ""
    property string icon: ""

    Text {
        visible: root.icon.length > 0
        text: root.icon
        font.pixelSize: Theme.fontBody
        Layout.alignment: Qt.AlignVCenter
    }
    Text {
        text: root.title
        font.pixelSize: Theme.fontBody
        font.weight: Font.DemiBold
        color: Theme.textPrimary
        Layout.alignment: Qt.AlignVCenter
    }
    Text {
        visible: root.subtitle.length > 0
        text: root.subtitle
        font.pixelSize: Theme.fontCaption
        color: Theme.textMuted
        leftPadding: Theme.spacingSm
        Layout.alignment: Qt.AlignVCenter
        elide: Text.ElideRight
        Layout.fillWidth: true
    }
    Item { Layout.fillWidth: true; visible: root.subtitle.length === 0 }
}
