import QtQuick
import QtQuick.Controls
import ".."

GlassCard {
    id: root
    autoSize: false

    property alias model: logView.model
    property int maxLines: 500

    function append(text) {
        logListModel.append({"line": text});
        if (logListModel.count > maxLines)
            logListModel.remove(0);
        logView.positionViewAtEnd();
    }

    function clear() {
        logListModel.clear();
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

    ListView {
        boundsBehavior: Theme.boundsBehavior
        id: logView
        anchors.top: headerLabel.bottom
        anchors.topMargin: 4
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        clip: true
        model: logListModel

        ScrollBar.vertical: ScrollBar {
            policy: ScrollBar.AsNeeded
        }

        delegate: Text {
            width: logView.width
            text: model.line
            wrapMode: Text.Wrap
            font.pixelSize: Theme.fontCaption
            font.family: "Consolas"
            color: {
                if (model.line.indexOf("[에러]") >= 0 || model.line.indexOf("실패") >= 0)
                    return Theme.error;
                if (model.line.indexOf("[성공]") >= 0 || model.line.indexOf("완료") >= 0)
                    return Theme.success;
                if (model.line.indexOf("[경고]") >= 0)
                    return Theme.warning;
                return Theme.textMuted;
            }
            padding: 1
        }
    }
}