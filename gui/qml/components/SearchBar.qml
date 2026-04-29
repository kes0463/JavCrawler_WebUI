import QtQuick
import QtQuick.Controls
import Qt5Compat.GraphicalEffects
import ".."

Rectangle {
    id: root

    property alias text: input.text
    property string placeholderText: ""
    signal accepted(string query)
    /// 키보드 세로 체인(라이브러리 목록): ↑ 검색 위 컨트롤, ↓ 아래 컨트롤
    signal navigateUp()
    signal navigateDown()
    /// 커서가 줄 맨 앞일 때 ← 왼쪽: 옆 컨트롤(예: 필터 버튼)
    signal navigateLeft()
    /// 커서가 줄 끝일 때 → 오른쪽: 옆 컨트롤(예: 정렬 ComboBox)
    signal navigateRight()

    function focusSearchInput() {
        input.forceActiveFocus()
    }

    /// 포커스가 검색 입력에 있는지(라이브러리 키 내비)
    property bool hasInputFocus: input.activeFocus

    implicitWidth: 400
    implicitHeight: 40
    radius: Theme.radiusSm
    color: Theme.surfaceLight
    border.color: input.activeFocus ? Theme.accentNeon : Theme.glassBorder
    border.width: 1

    Behavior on border.color { ColorAnimation { duration: Theme.animFast } }

    // 포커스 글로우
    property real _focusGlow: input.activeFocus ? 1.0 : 0.0
    Behavior on _focusGlow { NumberAnimation { duration: Theme.animFast } }

    layer.enabled: true
    layer.effect: DropShadow {
        transparentBorder: true
        horizontalOffset: 0
        verticalOffset: 0
        radius: root._focusGlow * 10
        samples: 21
        color: Qt.rgba(Theme.accentNeon.r, Theme.accentNeon.g, Theme.accentNeon.b, root._focusGlow * 0.30)
    }

    Row {
        anchors.fill: parent
        anchors.leftMargin: Theme.spacingSm
        anchors.rightMargin: Theme.spacingSm
        spacing: Theme.spacingSm

        Text {
            text: "\uD83D\uDD0D"
            anchors.verticalCenter: parent.verticalCenter
            font.pixelSize: Theme.fontBody
            color: Theme.textMuted
        }

        TextInput {
            id: input
            anchors.verticalCenter: parent.verticalCenter
            width: parent.width - 60
            font.pixelSize: Theme.fontBody
            color: Theme.textPrimary
            selectionColor: Theme.accentNeon
            clip: true

            Keys.onPressed: function(event) {
                if (event.key === Qt.Key_Left && input.cursorPosition === 0
                        && input.selectionStart === input.selectionEnd
                        && !(event.modifiers & (Qt.ShiftModifier | Qt.ControlModifier | Qt.AltModifier))) {
                    root.navigateLeft()
                    event.accepted = true
                    return
                }
                if (event.key === Qt.Key_Up && input.cursorPosition === 0
                        && input.selectionStart === input.selectionEnd
                        && !(event.modifiers & (Qt.ShiftModifier | Qt.ControlModifier | Qt.AltModifier))) {
                    root.navigateUp()
                    event.accepted = true
                    return
                }
                if (event.key === Qt.Key_Down
                        && !(event.modifiers & (Qt.ShiftModifier | Qt.ControlModifier | Qt.AltModifier))) {
                    root.navigateDown()
                    event.accepted = true
                    return
                }
                if (event.key === Qt.Key_Right
                        && input.cursorPosition === input.length
                        && input.selectionStart === input.selectionEnd
                        && !(event.modifiers & (Qt.ShiftModifier | Qt.ControlModifier | Qt.AltModifier))) {
                    root.navigateRight()
                    event.accepted = true
                    return
                }
            }

            Text {
                visible: !input.text && !input.activeFocus
                text: root.placeholderText
                font: input.font
                color: Theme.textMuted
                anchors.verticalCenter: parent.verticalCenter
            }

            onAccepted: root.accepted(text)
        }

        Text {
            text: "\u2715"
            visible: input.text.length > 0
            anchors.verticalCenter: parent.verticalCenter
            font.pixelSize: Theme.fontBody
            color: Theme.textMuted

            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: { input.text = ""; root.accepted(""); }
            }
        }
    }
}