import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

Drawer {
    id: root

    /** parent-owned ListModel: productCode, oldPath, candidatesJson (후보 배열은 JSON 문자열) */
    property var inboxModel: null

    signal detailRequested(string productCode, string oldPath, var candidates)

    function parseCandidatesJson(s) {
        try {
            var x = JSON.parse(s || "[]")
            return Array.isArray(x) ? x : []
        } catch (e) {
            return []
        }
    }
    signal removeRequested(string productCode)
    signal clearRequested()

    edge: Qt.RightEdge
    width: Math.min(440, parent ? parent.width * 0.92 : 440)
    height: parent ? parent.height : implicitHeight

    background: Rectangle {
        color: Theme.bgPrimary
        border.color: Theme.glassBorder
        border.width: 1
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.spacingMd
        spacing: Theme.spacingSm

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingSm

            Text {
                text: "폴더 연결 알림"
                font.pixelSize: Theme.fontSubtitle
                font.weight: Font.DemiBold
                color: Theme.textPrimary
                Layout.fillWidth: true
            }

            ActionButton {
                visible: root.inboxModel && root.inboxModel.count > 0
                text: "모두 지우기"
                primary: false
                onClicked: root.clearRequested()
            }
        }

        Text {
            text: "저장된 폴더가 없어진 작품입니다. 목록에서 항목을 열어 후보 경로를 고르거나 폴더를 지정하세요."
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
            color: Theme.textSecondary
            font.pixelSize: Theme.fontCaption
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            radius: Theme.radiusMd
            color: Theme.bgSecondary
            border.color: Theme.glassBorder
            border.width: 1
            clip: true

            ListView {
                boundsBehavior: Theme.boundsBehavior
                id: listView
                anchors.fill: parent
                anchors.margins: Theme.spacingSm
                spacing: Theme.spacingSm
                clip: true
                model: root.inboxModel
                visible: root.inboxModel && root.inboxModel.count > 0

                delegate: Rectangle {
                    width: ListView.view.width
                    radius: Theme.radiusSm
                    color: Theme.surfaceLight
                    border.color: Theme.glassBorder
                    border.width: 1
                    implicitHeight: delegateCol.implicitHeight + Theme.spacingSm * 2

                    readonly property string pc: model.productCode || ""
                    readonly property string op: model.oldPath || ""
                    readonly property string candJson: model.candidatesJson !== undefined ? model.candidatesJson : "[]"
                    readonly property var cands: root.parseCandidatesJson(candJson)

                    ColumnLayout {
                        id: delegateCol
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.margins: Theme.spacingSm
                        spacing: 4

                        Text {
                            text: "<b>" + pc + "</b>"
                            textFormat: Text.RichText
                            Layout.fillWidth: true
                            color: Theme.textPrimary
                            font.pixelSize: Theme.fontBody
                            wrapMode: Text.WrapAnywhere
                        }

                        Text {
                            text: op || ""
                            Layout.fillWidth: true
                            color: Theme.textSecondary
                            font.pixelSize: Theme.fontCaption
                            wrapMode: Text.WrapAnywhere
                            maximumLineCount: 3
                            elide: Text.ElideRight
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Theme.spacingSm

                            ActionButton {
                                text: "열기"
                                primary: true
                                Layout.fillWidth: false
                                onClicked: root.detailRequested(pc, op, cands)
                            }

                            ActionButton {
                                text: "목록 제거"
                                primary: false
                                Layout.fillWidth: false
                                onClicked: root.removeRequested(pc)
                            }

                            Text {
                                visible: cands && cands.length > 0
                                text: "후보 " + cands.length + "건"
                                color: Theme.textMuted
                                font.pixelSize: Theme.fontCaption
                                Layout.fillWidth: true
                                horizontalAlignment: Text.AlignRight
                                elide: Text.ElideRight
                            }
                        }
                    }
                }
            }

            Label {
                anchors.centerIn: parent
                visible: !root.inboxModel || root.inboxModel.count === 0
                text: "대기 중인 폴더 알림이 없습니다."
                color: Theme.textMuted
                font.pixelSize: Theme.fontBody
            }
        }
    }
}