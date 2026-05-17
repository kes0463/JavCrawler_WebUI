import QtQuick
import QtQuick.Layouts
import ".."

Item {
    id: root

    property var collection: ({})
    property bool hasData: collection.has_data === true
    property var actors: collection.actors || []

    implicitWidth: 320
    implicitHeight: contentCol.implicitHeight

    ColumnLayout {
        id: contentCol
        width: parent.width
        spacing: Theme.spacingSm

        Text {
            Layout.fillWidth: true
            visible: !root.hasData
            text: collection.empty_message || "배우별 완독 데이터가 없습니다."
            font.pixelSize: Theme.fontCaption
            color: Theme.textMuted
            wrapMode: Text.Wrap
        }

        Repeater {
            model: root.hasData ? root.actors : []

            Item {
                Layout.fillWidth: true
                implicitHeight: actorRow.implicitHeight

                RowLayout {
                    id: actorRow
                    anchors.fill: parent
                    spacing: Theme.spacingSm

                    Text {
                        text: modelData.name || ""
                        font.pixelSize: Theme.fontCaption
                        color: rowMa.containsMouse ? Theme.accentNeon : Theme.textPrimary
                        Layout.preferredWidth: 88
                        elide: Text.ElideRight
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        height: 10
                        radius: 5
                        color: Qt.rgba(1, 1, 1, 0.08)

                        Rectangle {
                            width: parent.width * Math.max(0, Math.min(1, modelData.completion_rate || 0))
                            height: parent.height
                            radius: 5
                            color: modelData.is_complete
                                ? Qt.rgba(1, 200/255, 80/255, 0.95)
                                : Theme.accentNeon
                        }
                    }

                    Text {
                        text: (modelData.completed || 0) + "/" + (modelData.total || 0)
                        font.pixelSize: 10
                        font.weight: Font.Bold
                        color: Theme.textSecondary
                        Layout.preferredWidth: 36
                        horizontalAlignment: Text.AlignRight
                    }

                    Text {
                        visible: modelData.is_complete === true
                        text: "🏆"
                        font.pixelSize: 12
                    }

                    Text {
                        visible: !modelData.is_complete && (modelData.remaining || 0) > 0
                        text: modelData.hint || ""
                        font.pixelSize: 10
                        color: Theme.textMuted
                        Layout.preferredWidth: 52
                        elide: Text.ElideRight
                    }
                }

                MouseArea {
                    id: rowMa
                    anchors.fill: parent
                    hoverEnabled: true
                    acceptedButtons: Qt.NoButton
                }
            }
        }
    }
}
