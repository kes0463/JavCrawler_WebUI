import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

GlassCard {
    id: root
    autoSize: false
    clip: true

    property string messagesJson: "[]"
    property bool running: false
    property var messages: []

    signal sendRequested(string message)
    signal clearRequested()

    function parseMessages() {
        try {
            var parsed = JSON.parse(root.messagesJson || "[]")
            root.messages = Array.isArray(parsed) ? parsed : []
        } catch (e) {
            root.messages = []
        }
    }

    function sendCurrent() {
        var text = input.text.trim()
        if (!text || root.running)
            return
        root.sendRequested(text)
        input.text = ""
    }

    onMessagesJsonChanged: {
        parseMessages()
        Qt.callLater(function() {
            chatList.positionViewAtEnd()
        })
    }

    Component.onCompleted: parseMessages()

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.spacingMd
        spacing: Theme.spacingSm

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingSm

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2

                Text {
                    Layout.fillWidth: true
                    text: "페르소나 챗"
                    font.pixelSize: Theme.fontBody
                    font.weight: Font.DemiBold
                    color: Theme.textPrimary
                }

                Text {
                    Layout.fillWidth: true
                    text: root.running ? "Gemma 페르소나가 답변 중입니다..." : "품번이나 취향을 던지면 바로 분석합니다."
                    font.pixelSize: Theme.fontCaption
                    color: Theme.textMuted
                    elide: Text.ElideRight
                }
            }

            ActionButton {
                text: "초기화"
                primary: false
                height: 32
                enabled: !root.running && root.messages.length > 0
                onClicked: root.clearRequested()
            }
        }

        ListView {
            id: chatList
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            spacing: Theme.spacingSm
            model: root.messages
            boundsBehavior: Flickable.StopAtBounds

            delegate: Item {
                width: chatList.width
                height: bubble.implicitHeight

                readonly property bool userMessage: modelData.role === "user"
                readonly property bool errorMessage: modelData.status === "error"

                TextMetrics {
                    id: messageMetrics
                    text: modelData.content || ""
                    font.pixelSize: Theme.fontCaption
                }

                Rectangle {
                    id: bubble
                    readonly property int bubblePadding: Theme.spacingSm
                    width: Math.min(parent.width * 0.82, Math.max(180, messageMetrics.width + bubblePadding * 2))
                    implicitHeight: copyRow.implicitHeight + messageText.contentHeight + bubbleContent.spacing + bubblePadding * 2 + 4
                    anchors.right: userMessage ? parent.right : undefined
                    anchors.left: userMessage ? undefined : parent.left
                    radius: Theme.radiusMd
                    color: {
                        if (errorMessage)
                            return Qt.rgba(239/255, 68/255, 68/255, 0.16)
                        return userMessage
                            ? Qt.rgba(0, 229/255, 255/255, 0.16)
                            : Qt.rgba(244/255, 114/255, 182/255, 0.12)
                    }
                    border.color: userMessage ? Theme.accentNeon : Theme.glassBorder

                    Column {
                        id: bubbleContent
                        anchors.fill: parent
                        anchors.margins: bubble.bubblePadding
                        spacing: 4

                        Row {
                            id: copyRow
                            width: parent.width
                            height: copyText.implicitHeight

                            Item {
                                width: parent.width - copyText.implicitWidth
                                height: 1
                            }

                            Text {
                                id: copyText
                                text: "복사"
                                font.pixelSize: Math.max(10, Theme.fontCaption - 2)
                                color: copyMouse.containsMouse ? Theme.accentNeon : Theme.textMuted

                                MouseArea {
                                    id: copyMouse
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        messageText.forceActiveFocus()
                                        messageText.selectAll()
                                        messageText.copy()
                                        messageText.deselect()
                                    }
                                }
                            }
                        }

                        TextEdit {
                            id: messageText
                            width: parent.width
                            height: contentHeight + 2
                            text: modelData.content || ""
                            readOnly: true
                            selectByMouse: true
                            persistentSelection: true
                            textFormat: TextEdit.PlainText
                            wrapMode: TextEdit.Wrap
                            font.pixelSize: Theme.fontCaption
                            color: errorMessage ? Theme.error : Theme.textSecondary
                            selectedTextColor: "#000000"
                            selectionColor: Theme.accentNeon
                            activeFocusOnPress: true
                        }
                    }
                }
            }

            footer: Item {
                width: chatList.width
                height: root.running ? 28 : 0
                visible: root.running
                Text {
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    text: "답변 생성 중..."
                    font.pixelSize: Theme.fontCaption
                    color: Theme.textMuted
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingSm

            TextArea {
                id: input
                Layout.fillWidth: true
                Layout.preferredHeight: 66
                enabled: !root.running
                placeholderText: "예: HBAD-509가 왜 내 취향인지 말해줘"
                wrapMode: TextEdit.Wrap
                color: Theme.textPrimary
                selectedTextColor: "#000000"
                selectionColor: Theme.accentNeon
                font.pixelSize: Theme.fontBody
                Keys.onPressed: function(event) {
                    if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter)
                            && (event.modifiers & Qt.ControlModifier)) {
                        root.sendCurrent()
                        event.accepted = true
                    }
                }
                background: Rectangle {
                    radius: Theme.radiusSm
                    color: Theme.surfaceLight
                    border.color: input.activeFocus ? Theme.accentNeon : Theme.glassBorder
                    border.width: input.activeFocus ? 2 : 1
                }
            }

            ActionButton {
                text: root.running ? "생성 중" : "전송"
                primary: true
                height: 42
                enabled: !root.running && input.text.trim().length > 0
                onClicked: root.sendCurrent()
            }
        }
    }
}
