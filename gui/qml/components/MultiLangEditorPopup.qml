import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."
import "."

Popup {
    id: root
    modal: true
    dim: true
    focus: true
    padding: Theme.spacingMd
    parent: Overlay.overlay
    anchors.centerIn: Overlay.overlay
    width: Math.min(editMode === "synopsis" ? 640 : 580, Overlay.overlay.width - 48)

    property string editMode: "title" // "title" | "synopsis"

    /** 텍스트 필드 배경 — Theme.surfaceLight는 Mica 모드에서 알파가 있어 패널과 구분이 약함 */
    readonly property color fieldBg: Theme.isDark ? "#161E34" : "#FFFFFF"

    function reloadFields() {
        if (editMode === "title") {
            tfKo.text = LibraryModel.editDraft.titleKo
            tfJa.text = LibraryModel.editDraft.titleJa
            tfEn.text = LibraryModel.editDraft.titleEn
            tfZhc.text = LibraryModel.editDraft.titleZhCn
            tfZht.text = LibraryModel.editDraft.titleZhTw
        } else {
            tfKo.text = LibraryModel.editDraft.synopsisKo
            tfJa.text = LibraryModel.editDraft.synopsisJa
            tfEn.text = LibraryModel.editDraft.synopsisEn
            tfZhc.text = LibraryModel.editDraft.synopsisZhCn
            tfZht.text = LibraryModel.editDraft.synopsisZhTw
        }
    }

    function applyAndClose() {
        if (editMode === "title") {
            LibraryModel.setDraftTitles(tfKo.text, tfJa.text, tfEn.text, tfZhc.text, tfZht.text)
        } else {
            LibraryModel.setDraftSynopses(tfKo.text, tfJa.text, tfEn.text, tfZhc.text, tfZht.text)
        }
        close()
    }

    onOpened: reloadFields()

    // Win11(Mica) 모드에서 Theme.surface는 반투명이라 뒤 화면이 비치고 글자 대비가 깨짐 → 불투명 패널 사용
    background: Rectangle {
        radius: Theme.radiusMd
        color: Theme.bgSecondary
        border.color: Theme.glassBorder
        border.width: 1
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.spacingSm

        Text {
            text: editMode === "title" ? "제목 (다국어)" : "시놉시스 (다국어)"
            font.pixelSize: Theme.fontSubtitle
            font.weight: Font.DemiBold
            color: Theme.textPrimary
            Layout.fillWidth: true
        }

        AppScrollView {
            id: langScroll
            Layout.fillWidth: true
            Layout.preferredHeight: editMode === "synopsis" ? 460 : 380
            clip: true
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

            ColumnLayout {
                // availableWidth가 0이면 Column이 지나치게 좁아 긴 제목이 한 글자씩 세로로 꺾임
                width: Math.max(1, langScroll.availableWidth > 8
                    ? langScroll.availableWidth
                    : (root.width - 2 * root.padding))
                spacing: Theme.spacingSm

                Label { text: "한국어"; color: Theme.textMuted; font.pixelSize: Theme.fontCaption }
                TextArea {
                    id: tfKo
                    Layout.fillWidth: true
                    Layout.preferredHeight: editMode === "title" ? 88 : 160
                    wrapMode: TextArea.Wrap
                    selectByMouse: true
                    color: Theme.textPrimary
                    placeholderTextColor: Theme.textMuted
                    font.pixelSize: Theme.fontBody
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: root.fieldBg
                        border.color: Theme.glassBorder
                        border.width: 1
                    }
                }

                Label { text: "일본어"; color: Theme.textMuted; font.pixelSize: Theme.fontCaption }
                TextArea {
                    id: tfJa
                    Layout.fillWidth: true
                    Layout.preferredHeight: editMode === "title" ? 88 : 160
                    wrapMode: TextArea.Wrap
                    selectByMouse: true
                    color: Theme.textPrimary
                    placeholderTextColor: Theme.textMuted
                    font.pixelSize: Theme.fontBody
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: root.fieldBg
                        border.color: Theme.glassBorder
                        border.width: 1
                    }
                }

                Label { text: "영어"; color: Theme.textMuted; font.pixelSize: Theme.fontCaption }
                TextArea {
                    id: tfEn
                    Layout.fillWidth: true
                    Layout.preferredHeight: editMode === "title" ? 88 : 160
                    wrapMode: TextArea.Wrap
                    selectByMouse: true
                    color: Theme.textPrimary
                    placeholderTextColor: Theme.textMuted
                    font.pixelSize: Theme.fontBody
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: root.fieldBg
                        border.color: Theme.glassBorder
                        border.width: 1
                    }
                }

                Label { text: "중국어 간체"; color: Theme.textMuted; font.pixelSize: Theme.fontCaption }
                TextArea {
                    id: tfZhc
                    Layout.fillWidth: true
                    Layout.preferredHeight: editMode === "title" ? 88 : 160
                    wrapMode: TextArea.Wrap
                    selectByMouse: true
                    color: Theme.textPrimary
                    placeholderTextColor: Theme.textMuted
                    font.pixelSize: Theme.fontBody
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: root.fieldBg
                        border.color: Theme.glassBorder
                        border.width: 1
                    }
                }

                Label { text: "중국어 번체"; color: Theme.textMuted; font.pixelSize: Theme.fontCaption }
                TextArea {
                    id: tfZht
                    Layout.fillWidth: true
                    Layout.preferredHeight: editMode === "title" ? 88 : 160
                    wrapMode: TextArea.Wrap
                    selectByMouse: true
                    color: Theme.textPrimary
                    placeholderTextColor: Theme.textMuted
                    font.pixelSize: Theme.fontBody
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: root.fieldBg
                        border.color: Theme.glassBorder
                        border.width: 1
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingMd
            Item { Layout.fillWidth: true }
            ActionButton {
                text: "취소"
                primary: false
                onClicked: root.close()
            }
            ActionButton {
                text: "확인"
                onClicked: root.applyAndClose()
            }
        }
    }
}