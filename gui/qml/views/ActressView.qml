import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."
import "../components"

Item {
    id: root

    property var actressModel: null
    property int selectedActressId: 0
    property bool showingDetail: false


    AddActressDialog {
        id: addActressDialog
        actressModel: root.actressModel
        onActressAdded: function(newId) {
            root.selectedActressId = newId
            if (root.actressModel) root.actressModel.loadProfile(newId)
            root.showingDetail = true
        }
    }

    MergeActressDialog {
        id: mergeActressDialog
        actressModel: root.actressModel
        onMerged: function(keepId) {
            root.selectedActressId = keepId
            root.showingDetail = true
        }
    }

    onActressModelChanged: {
        if (actressModel) actressModel.reload()
    }

    Component.onCompleted: {
        if (actressModel) actressModel.reload()
    }

    StackLayout {
        anchors.fill: parent
        currentIndex: root.showingDetail ? 1 : 0

        // ── 목록 ─────────────────────────────────────
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: Theme.spacingMd
                spacing: Theme.spacingMd

                RowLayout {
                    Layout.fillWidth: true
                    Text {
                        text: "배우 프로필"
                        font.pixelSize: Theme.fontSubtitle
                        color: Theme.textPrimary
                        font.bold: true
                        Layout.fillWidth: true
                    }
                    ActionButton {
                        text: "새 배우 추가"
                        primary: true
                        onClicked: addActressDialog.open()
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.spacingSm

                    SearchBar {
                        Layout.fillWidth: true
                        placeholderText: "이름 · 장르 · 별명 검색"
                        onTextChanged: {
                            if (root.actressModel) root.actressModel.filterList(text)
                        }
                    }

                    ComboBox {
                        id: sortCombo
                        implicitWidth: 110
                        model: ["이름순", "즐겨찾기", "점수순", "최근추가"]
                        currentIndex: 0
                        background: Rectangle {
                            color: Theme.surfaceLight
                            radius: 6
                            border.color: Theme.glassBorder
                        }
                        contentItem: Text {
                            leftPadding: 8
                            text: sortCombo.displayText
                            color: Theme.textPrimary
                            font.pixelSize: 13
                            verticalAlignment: Text.AlignVCenter
                        }
                        onCurrentIndexChanged: {
                            if (!root.actressModel) return
                            var keys = ["name", "favorite", "score", "recent"]
                            root.actressModel.reloadSorted(keys[currentIndex])
                        }
                    }
                }

                GridView {
                    id: gridView
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    cellWidth: 230
                    cellHeight: 340
                    model: actressModel ? actressModel.listModel : 0

                    delegate: Item {
                        width: gridView.cellWidth
                        height: gridView.cellHeight

                        ActressProfileCard {
                            anchors.centerIn: parent
                            width: parent.width - 12
                            height: parent.height - 12
                            actressId: model.id || 0
                            nameKo: model.nameKo || ""
                            nameJa: model.nameJa || ""
                            profileImage: model.profileImage || ""
                            userScore: model.userScore || 0.0
                            isFavorite: model.isFavorite || false
                            genres: model.genres || ""
                            selected: root.selectedActressId === model.id

                            onClicked: function(id) {
                                root.selectedActressId = id
                                if (root.actressModel) root.actressModel.loadProfile(id)
                                root.showingDetail = true
                            }
                        }
                    }

                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                }
            }
        }

        // ── 상세 ─────────────────────────────────────
        ActressDetailPanel {
            Layout.fillWidth: true
            Layout.fillHeight: true
            actressModel: root.actressModel
            onBack: root.showingDetail = false
            onRequestMerge: {
                if (!actressModel || !actressModel.currentProfile.id) return
                mergeActressDialog.keepActressId = actressModel.currentProfile.id
                mergeActressDialog.keepActressName = actressModel.currentProfile.name_ko || actressModel.currentProfile.name_ja || ""
                mergeActressDialog.open()
            }
        }
    }
}
