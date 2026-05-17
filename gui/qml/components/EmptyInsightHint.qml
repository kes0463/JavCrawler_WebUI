import QtQuick
import QtQuick.Layouts
import ".."

ColumnLayout {
    id: root
    Layout.fillWidth: true
    spacing: Theme.spacingSm

    property string icon: "📭"
    property string message: "데이터가 없습니다."
    property string hint: ""

    Text {
        text: root.icon
        font.pixelSize: 28
        Layout.alignment: Qt.AlignHCenter
    }
    Text {
        text: root.message
        font.pixelSize: Theme.fontCaption
        color: Theme.textMuted
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.Wrap
        Layout.fillWidth: true
        Layout.alignment: Qt.AlignHCenter
    }
    Text {
        visible: root.hint.length > 0
        text: root.hint
        font.pixelSize: Theme.fontCaption
        color: Theme.textMuted
        opacity: 0.85
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.Wrap
        Layout.fillWidth: true
        Layout.alignment: Qt.AlignHCenter
    }
}
