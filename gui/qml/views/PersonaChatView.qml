import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"
import ".."

Item {
    id: root

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            Layout.fillWidth: true
            height: 64
            color: "transparent"

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: Theme.spacingLg
                anchors.rightMargin: Theme.spacingLg
                spacing: Theme.spacingMd

                Text {
                    text: "💬"
                    font.pixelSize: 28
                    Layout.alignment: Qt.AlignVCenter
                }

                Text {
                    text: "페르소나 챗"
                    font.pixelSize: Theme.fontTitle
                    font.weight: Font.ExtraBold
                    color: Theme.textPrimary
                    Layout.alignment: Qt.AlignVCenter
                }

                Text {
                    text: "취향·품번·추천을 대화형으로 분석합니다."
                    font.pixelSize: Theme.fontCaption
                    color: Theme.textMuted
                    Layout.alignment: Qt.AlignVCenter
                }

                Item { Layout.fillWidth: true }
            }
        }

        PersonaChatWidget {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.margins: Theme.spacingLg
            messagesJson: InsightModel.personaChatMessages
            running: InsightModel.isPersonaChatRunning
            streamTarget: InsightModel
            onSendRequested: function(message) {
                InsightModel.sendPersonaChatMessage(message, true)
            }
            onClearRequested: InsightModel.clearPersonaChat()
            onCancelRequested: InsightModel.cancelPersonaChat()
        }
    }
}
