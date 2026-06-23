import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

GlassCard {
    id: root
    autoSize: false
    clip: true

    property string messagesJson: "[]"
    property string memoryJson: "{}"
    property string tonePreset: "recommend"
    property bool running: false
    property var messages: []
    property var streamTarget: null
    property bool streamingActive: false
    property bool memoryPanelOpen: false
    readonly property int chatMessageFontSize: Theme.fontBody + 1

    signal sendRequested(string message)
    signal clearRequested()
    signal cancelRequested()
    signal tonePresetSelected(string preset)
    signal productCodeLinkActivated(string productCode)
    signal memoryNoteRemoveRequested(string category, int index)

    function parseMessages() {
        try {
            var parsed = JSON.parse(root.messagesJson || "[]")
            root.messages = Array.isArray(parsed) ? parsed : []
        } catch (e) {
            root.messages = []
        }
    }

    function parseMemory() {
        try {
            return JSON.parse(root.memoryJson || "{}")
        } catch (e) {
            return {}
        }
    }

    function formatMessageHtml(text) {
        if (!text)
            return ""
        var escaped = String(text)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
        escaped = escaped.replace(
            /\*\*([A-Z0-9][A-Z0-9\-]*\d{2,7})\*\*/g,
            "$1"
        )
        escaped = escaped.replace(
            /\b([A-Z]{1,8}[-_\s]?\d{2,7})\b/g,
            function(match) {
                var code = match.replace(/[\s_]/g, "-").toUpperCase()
                return '<a href="javstory://product/' + code + '" style="color:#00e5ff;text-decoration:none;">' + match + '</a>'
            }
        )
        return escaped.replace(/\n/g, "<br>")
    }

    function sendCurrent() {
        var text = input.text.trim()
        if (!text || root.running)
            return
        root.streamingActive = true
        root.sendRequested(text)
        input.text = ""
    }

    function appendStreamingToken(token) {
        if (!token)
            return
        root.streamingActive = true
        var next = root.messages.slice()
        if (next.length > 0 && next[next.length - 1].role === "assistant") {
            var last = Object.assign({}, next[next.length - 1])
            last.content = (last.content || "") + token
            last.status = "streaming"
            next[next.length - 1] = last
        } else {
            next.push({ "role": "assistant", "content": token, "status": "streaming" })
        }
        root.messages = next
        Qt.callLater(function() {
            chatList.positionViewAtEnd()
        })
    }

    function hasValidProductCodes(text) {
        return /\b[A-Z]{1,8}-\d{2,7}\b/i.test(text || "")
    }

    function isLikelyHallucinatedRecommendation(text) {
        if (!text)
            return false
        if (hasValidProductCodes(text))
            return false
        if (/^\s*\d+\.\s*\d{2,5}\s*[:：]/m.test(text))
            return true
        if (/첫째로/.test(text) && /둘째로/.test(text))
            return true
        if (/추천/.test(text) && /^\s*\d+\./m.test(text) && !hasValidProductCodes(text))
            return true
        return false
    }

    function completeStreamingResponse(content) {
        root.streamingActive = false
        var next = root.messages.slice()
        var finalContent = content || "응답이 비어 있어서 표시할 내용이 없었어요. 같은 질문을 한 번만 다시 보내주세요."
        if (next.length > 0 && next[next.length - 1].role === "assistant") {
            var last = Object.assign({}, next[next.length - 1])
            last.content = finalContent
            last.status = "ok"
            next[next.length - 1] = last
        } else {
            next.push({ "role": "assistant", "content": finalContent, "status": "ok" })
        }
        root.messages = next
        Qt.callLater(function() {
            chatList.positionViewAtEnd()
        })
    }

    function handleCancelled() {
        root.streamingActive = false
    }

    function showStreamingError() {
        root.streamingActive = false
        var next = root.messages.slice()
        next.push({
            "role": "assistant",
            "content": "응답 생성 중 오류가 발생했습니다.",
            "status": "error"
        })
        root.messages = next
        Qt.callLater(function() {
            chatList.positionViewAtEnd()
        })
    }

    onMessagesJsonChanged: {
        parseMessages()
        if (!root.running)
            root.streamingActive = false
        Qt.callLater(function() {
            chatList.positionViewAtEnd()
        })
    }

    Component.onCompleted: parseMessages()

    Connections {
        target: root.streamTarget
        ignoreUnknownSignals: true
        function onPersonaChatTokenReceived(token) {
            root.appendStreamingToken(token)
        }
        function onPersonaChatResponseCompleted(content) {
            root.completeStreamingResponse(content)
        }
        function onPersonaChatErrorOccurred(_message) {
            root.showStreamingError()
        }
        function onPersonaChatCancelledOccurred() {
            root.handleCancelled()
        }
    }

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
                    text: root.running ? "Gemma 페르소나가 답변 중입니다..." : "품번 클릭 시 상세로 이동 · 취향·추천·평점 목록"
                    font.pixelSize: Theme.fontCaption
                    color: Theme.textMuted
                    elide: Text.ElideRight
                }
            }

            ComboBox {
                id: toneCombo
                Layout.preferredWidth: 112
                enabled: !root.running
                model: [
                    { label: "분석형", value: "analysis" },
                    { label: "추천형", value: "recommend" },
                    { label: "도발형", value: "intense" }
                ]
                textRole: "label"
                valueRole: "value"
                currentIndex: Math.max(0, ["analysis", "recommend", "intense"].indexOf(root.tonePreset))

                onActivated: function(idx) {
                    var value = model[idx].value
                    if (value && value !== root.tonePreset)
                        root.tonePresetSelected(value)
                }
            }

            ActionButton {
                text: root.memoryPanelOpen ? "기억 닫기" : "기억 보기"
                primary: false
                height: 32
                enabled: !root.running
                onClicked: root.memoryPanelOpen = !root.memoryPanelOpen
            }

            ActionButton {
                text: "초기화"
                primary: false
                height: 32
                enabled: !root.running && root.messages.length > 0
                onClicked: root.clearRequested()
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: memoryPanel.implicitHeight + Theme.spacingSm * 2
            visible: root.memoryPanelOpen
            radius: Theme.radiusSm
            color: Theme.surfaceLight
            border.color: Theme.glassBorder
            clip: true

            ColumnLayout {
                id: memoryPanel
                anchors.fill: parent
                anchors.margins: Theme.spacingSm
                spacing: Theme.spacingXs

                Text {
                    text: "지금 기억하는 내 취향"
                    font.pixelSize: Theme.fontCaption
                    font.weight: Font.DemiBold
                    color: Theme.textPrimary
                }

                Repeater {
                    model: {
                        var mem = root.parseMemory()
                        var rows = []
                        function pushRows(key, label) {
                            var items = mem[key] || []
                            for (var i = 0; i < items.length; i++) {
                                rows.push({
                                    category: key === "preference_notes" ? "preference"
                                        : key === "strong_reaction_notes" ? "strong_reaction"
                                        : key === "negative_feedback_notes" ? "negative_feedback"
                                        : key === "correction_notes" ? "correction"
                                        : key === "style_notes" ? "style" : "",
                                    index: i,
                                    label: label,
                                    text: String(items[i].text || "")
                                })
                            }
                        }
                        pushRows("preference_notes", "취향")
                        pushRows("strong_reaction_notes", "강한 반응")
                        pushRows("negative_feedback_notes", "비선호")
                        pushRows("correction_notes", "교정")
                        pushRows("style_notes", "말투")
                        return rows
                    }

                    delegate: RowLayout {
                        Layout.fillWidth: true
                        spacing: Theme.spacingXs

                        Text {
                            Layout.fillWidth: true
                            text: (modelData.label || "") + ": " + (modelData.text || "")
                            wrapMode: Text.Wrap
                            font.pixelSize: Theme.fontCaption
                            color: Theme.textSecondary
                        }

                        ActionButton {
                            text: "삭제"
                            primary: false
                            height: 24
                            enabled: !root.running
                            onClicked: root.memoryNoteRemoveRequested(modelData.category, modelData.index)
                        }
                    }
                }

                Text {
                    visible: {
                        var mem = root.parseMemory()
                        return !(mem.preference_notes || []).length
                            && !(mem.strong_reaction_notes || []).length
                            && !(mem.negative_feedback_notes || []).length
                            && !(mem.correction_notes || []).length
                            && !(mem.style_notes || []).length
                    }
                    text: "아직 저장된 대화 기억이 없습니다."
                    font.pixelSize: Theme.fontCaption
                    color: Theme.textMuted
                }
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
                height: bubble.height + Theme.spacingXs

                readonly property bool userMessage: modelData.role === "user"
                readonly property bool errorMessage: modelData.status === "error"

                Rectangle {
                    id: bubble
                    readonly property int bubblePadding: Theme.spacingSm
                    width: Math.min(parent.width * 0.82, Math.max(180, parent.width * 0.55))
                    implicitHeight: bubbleContent.implicitHeight + bubblePadding * 2 + 4
                    height: implicitHeight
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
                        width: parent.width - bubble.bubblePadding * 2

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
                            height: contentHeight + 6
                            text: userMessage ? (modelData.content || "") : root.formatMessageHtml(modelData.content || "")
                            readOnly: true
                            selectByMouse: true
                            persistentSelection: true
                            textFormat: userMessage ? TextEdit.PlainText : TextEdit.RichText
                            wrapMode: TextEdit.Wrap
                            font.pixelSize: root.chatMessageFontSize
                            color: errorMessage ? Theme.error : Theme.textSecondary
                            selectedTextColor: "#000000"
                            selectionColor: Theme.accentNeon
                            activeFocusOnPress: true

                            onLinkActivated: function(link) {
                                if (!link || userMessage)
                                    return
                                var prefix = "javstory://product/"
                                if (link.indexOf(prefix) === 0)
                                    root.productCodeLinkActivated(link.substring(prefix.length))
                            }
                        }
                    }
                }
            }

            footer: Item {
                width: chatList.width
                height: (root.running && root.streamingActive) ? 32 : 0
                visible: root.running && root.streamingActive
                Row {
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 4

                    Text {
                        text: "타이핑 중"
                        font.pixelSize: Theme.fontBody
                        color: Theme.textMuted
                    }

                    Repeater {
                        model: 3
                        Text {
                            text: "."
                            font.pixelSize: Theme.fontBody
                            color: Theme.textMuted
                            opacity: 0.25

                            SequentialAnimation on opacity {
                                loops: Animation.Infinite
                                PauseAnimation { duration: index * 160 }
                                NumberAnimation { to: 1.0; duration: 180 }
                                NumberAnimation { to: 0.25; duration: 360 }
                                PauseAnimation { duration: 480 - index * 120 }
                            }
                        }
                    }
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
                placeholderText: "예: 내가 점수 준 작품 리스트 알려줘"
                wrapMode: TextEdit.Wrap
                color: Theme.textPrimary
                selectedTextColor: "#000000"
                selectionColor: Theme.accentNeon
                font.pixelSize: root.chatMessageFontSize
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
                visible: root.running
                text: "취소"
                danger: true
                height: 42
                onClicked: root.cancelRequested()
            }

            ActionButton {
                visible: !root.running
                text: "전송"
                primary: true
                height: 42
                enabled: input.text.trim().length > 0
                onClicked: root.sendCurrent()
            }
        }
    }
}
