import QtQuick
import QtQuick.Controls
import ".."

GlassCard {
    id: root
    autoSize: false

    property int maxLines: 500
    property string copyText: ""

    function append(text) {
        logListModel.append({"line": text});
        if (logListModel.count > maxLines)
            logListModel.remove(0);
        // keep copyText in sync for selection/copy
        var lines = [];
        for (var i = 0; i < logListModel.count; i++) {
            lines.push(logListModel.get(i).line);
        }
        copyText = lines.join("\n");
        logArea.cursorPosition = logArea.length
    }

    function clear() {
        logListModel.clear();
        copyText = "";
    }

    implicitHeight: 200

    ListModel { id: logListModel }

    Text {
        id: headerLabel
        text: "로그"
        font.pixelSize: Theme.fontCaption
        font.weight: Font.DemiBold
        color: Theme.textSecondary
    }

    ScrollView {
        anchors.top: headerLabel.bottom
        anchors.topMargin: 4
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        clip: true

        ScrollBar.vertical.policy: ScrollBar.AsNeeded

        TextArea {
            id: logArea
            width: parent.width
            text: root.copyText
            readOnly: true
            selectByMouse: true
            wrapMode: TextArea.Wrap
            color: Theme.textMuted
            selectedTextColor: Theme.textPrimary
            selectionColor: Theme.accentNeon
            font.pixelSize: Theme.fontCaption
            font.family: "Consolas"
            background: null
        }
    }
}