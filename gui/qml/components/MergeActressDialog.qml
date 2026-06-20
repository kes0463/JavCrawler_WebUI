import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

Dialog {
    id: root

    property var actressModel: null
    property int keepActressId: 0
    property string keepActressName: ""
    property bool confirmingMerge: false
    property int mergeTargetId: 0
    property string mergeTargetName: ""

    signal merged(int keepId)

    title: root.confirmingMerge ? "합치기 확인" : "배우 합치기"
    modal: true
    width: 520
    height: root.confirmingMerge ? 220 : 480

    background: Rectangle {
        color: Theme.bgPrimary
        border.color: Theme.glassBorder
        radius: Theme.radiusMd
    }

    onOpened: {
        searchField.text = ""
        resultsModel.clear()
        root.confirmingMerge = false
        root.mergeTargetId = 0
        root.mergeTargetName = ""
    }

    ListModel { id: resultsModel }

    function _runSearch() {
        resultsModel.clear()
        if (!root.actressModel) return
        var rows = root.actressModel.searchActresses(searchField.text.trim())
        for (var i = 0; i < rows.length; i++) {
            if (rows[i].id === root.keepActressId) continue
            resultsModel.append(rows[i])
        }
    }

    function _startMerge(id, name) {
        root.mergeTargetId = id
        root.mergeTargetName = name
        root.confirmingMerge = true
    }

    function _doMerge() {
        if (root.actressModel && root.keepActressId > 0 && root.mergeTargetId > 0) {
            if (root.actressModel.mergeActresses(root.keepActressId, root.mergeTargetId)) {
                root.merged(root.keepActressId)
                root.close()
            }
        }
    }

    contentItem: Item {
        implicitWidth: 480
        implicitHeight: root.confirmingMerge ? 120 : 360

        ColumnLayout {
            visible: !root.confirmingMerge
            anchors.fill: parent
            spacing: Theme.spacingMd

            Text {
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                color: Theme.textSecondary
                font.pixelSize: 13
                text: "현재 프로필 「" + root.keepActressName + "」에 다른 배우 기록을 합칩니다.\n합칠 배우는 삭제되고 별명·사진·정보가 현재 프로필로 이동합니다."
            }

            SearchBar {
                id: searchField
                Layout.fillWidth: true
                placeholderText: "합칠 배우 검색 (이름·별명)"
                onTextChanged: root._runSearch()
            }

            ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true

                ListView {
                    model: resultsModel
                    spacing: 4
                    delegate: Rectangle {
                        width: ListView.view.width
                        height: 44
                        radius: 6
                        color: rowMa.containsMouse ? Theme.surfaceLight : "transparent"
                        border.color: Theme.glassBorder

                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 8
                            Text {
                                text: (model.name_ko || "") + (model.name_ja ? "  (" + model.name_ja + ")" : "")
                                color: Theme.textPrimary
                                Layout.fillWidth: true
                                elide: Text.ElideRight
                            }
                            ActionButton {
                                text: "합치기"
                                primary: true
                                onClicked: root._startMerge(model.id, model.name_ko || model.name_ja)
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

        ColumnLayout {
            visible: root.confirmingMerge
            anchors.fill: parent
            spacing: Theme.spacingMd

            Text {
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                color: Theme.textPrimary
                font.pixelSize: 14
                text: "「" + root.mergeTargetName + "」를\n「" + root.keepActressName + "」에 합치시겠습니까?\n이 작업은 되돌릴 수 없습니다."
            }

            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                ActionButton {
                    text: "취소"
                    onClicked: root.confirmingMerge = false
                }
                ActionButton {
                    text: "합치기"
                    primary: true
                    onClicked: root._doMerge()
                }
            }
        }
    }

    footer: RowLayout {
        visible: !root.confirmingMerge
        Item { Layout.fillWidth: true }
        ActionButton {
            text: "닫기"
            onClicked: root.close()
        }
    }
}
