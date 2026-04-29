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
    /** Overlay 미연결 타이밍(중첩 팝업 등)에서 Overlay.overlay 가 null 이면 width 접근 시 TypeError 방지 */
    readonly property real _innerMaxW: {
        var o = Overlay.overlay
        if (o === null || o.width <= 0)
            return 392
        return Math.max(120, o.width - 48)
    }
    width: Math.min(440, _innerMaxW)

    property string pickerMode: "maker" // maker | genre | actress
    // maker는 단일 선택(선택 즉시 닫기), genre/actress는 연속 추가 UX(저장/완료로 닫기)
    readonly property bool multiPick: pickerMode !== "maker"

    readonly property color fieldBg: Theme.isDark ? "#161E34" : "#FFFFFF"

    ListModel { id: pickModel }

    function refresh() {
        var q = searchField.text
        var arr = []
        try {
            if (pickerMode === "maker")
                arr = LibraryModel.searchMakers(q) || []
            else if (pickerMode === "genre")
                arr = LibraryModel.searchGenres(q) || []
            else
                arr = LibraryModel.searchActresses(q) || []
        } catch (e) {
            arr = []
        }

        pickModel.clear()
        for (var i = 0; i < arr.length; i++) {
            var o = arr[i]
            pickModel.append({
                line: pickerMode === "maker"
                    ? ((o.japanese || "") + " — " + (o.korean || "") + " — " + (o.english || ""))
                    : (pickerMode === "genre"
                        ? ((o.japanese || "") + " — " + (o.korean || ""))
                        : ((o.japanese || "") + " — " + (o.korean || "") + " — " + (o.romaji || ""))),
                jp: o.japanese || "",
                ko: o.korean || "",
                en: o.english || "",
                romaji: o.romaji || ""
            })
        }
    }

    onOpened: {
        searchField.text = ""
        refresh()
    }

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
            text: pickerMode === "maker" ? "메이커 선택"
                : (pickerMode === "genre" ? "장르 선택" : "배우 선택")
            font.pixelSize: Theme.fontSubtitle
            font.weight: Font.DemiBold
            color: Theme.textPrimary
            Layout.fillWidth: true
        }

        TextField {
            id: searchField
            Layout.fillWidth: true
            placeholderText: "검색…"
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
            onTextChanged: debounce.restart()
        }

        Timer {
            id: debounce
            interval: 200
            repeat: false
            onTriggered: root.refresh()
        }

        AppScrollView {
            id: pickScroll
            Layout.fillWidth: true
            Layout.preferredHeight: 280
            clip: true
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

            ListView {
                boundsBehavior: Theme.boundsBehavior
                id: pickList
                width: Math.max(1, pickScroll.availableWidth > 8
                    ? pickScroll.availableWidth
                    : (root.width - 2 * root.padding))
                implicitHeight: contentHeight
                spacing: 4
                clip: true
                model: pickModel

                delegate: Rectangle {
                    width: pickList.width
                    implicitHeight: Math.max(lbl.implicitHeight + 20, 44)
                    radius: Theme.radiusSm
                    color: pickMa.containsMouse || pickMa.pressed ? Theme.navHover : "transparent"
                    border.color: Theme.glassBorder
                    border.width: 1

                    Label {
                        id: lbl
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.margins: 10
                        text: model.line
                        wrapMode: Text.WordWrap
                        color: Theme.textPrimary
                        font.pixelSize: Theme.fontBody
                    }

                    MouseArea {
                        id: pickMa
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            if (pickerMode === "maker") {
                                LibraryModel.applyMakerFields(model.jp, model.ko, model.en)
                            } else if (pickerMode === "genre") {
                                LibraryModel.appendGenreKo(model.ko || model.jp)
                            } else {
                                LibraryModel.appendActorFromPick(
                                    model.ko || model.jp,
                                    model.jp,
                                    model.romaji || "")
                            }
                            if (!root.multiPick) {
                                root.close()
                            } else {
                                // 다음 항목을 계속 추가할 수 있도록 팝업 유지 + 검색창 포커스 복귀
                                Qt.callLater(function () {
                                    try { searchField.forceActiveFocus() } catch (e) {}
                                })
                            }
                        }
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingMd
            ActionButton {
                text: pickerMode === "maker" ? "새 메이커 추가…"
                    : (pickerMode === "genre" ? "새 장르 추가…" : "새 배우 추가…")
                primary: false
                onClicked: {
                    njJa.text = ""
                    njKo.text = ""
                    njEn.text = ""
                    newEntryPopup.open()
                }
            }
            Item { Layout.fillWidth: true }
            ActionButton {
                visible: root.multiPick
                text: "닫기"
                primary: false
                onClicked: root.close()
            }
            ActionButton {
                text: root.multiPick ? "저장" : "닫기"
                primary: root.multiPick
                neonGlow: root.multiPick
                onClicked: root.close()
            }
        }
    }

    Popup {
        id: newEntryPopup
        modal: true
        dim: true
        focus: true
        padding: Theme.spacingMd
        parent: Overlay.overlay
        anchors.centerIn: Overlay.overlay
        width: Math.min(400, root._innerMaxW)
        z: root.z + 1

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
                text: pickerMode === "maker" ? "새 메이커" : (pickerMode === "genre" ? "새 장르" : "새 배우")
                font.pixelSize: Theme.fontSubtitle
                font.weight: Font.DemiBold
                color: Theme.textPrimary
            }

            Label { text: "일본어"; color: Theme.textMuted; font.pixelSize: Theme.fontCaption }
            TextField {
                id: njJa
                Layout.fillWidth: true
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

            Label { text: "한국어"; color: Theme.textMuted; font.pixelSize: Theme.fontCaption }
            TextField {
                id: njKo
                Layout.fillWidth: true
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

            Label {
                visible: pickerMode === "maker"
                text: "영어 (slug)"
                color: Theme.textMuted
                font.pixelSize: Theme.fontCaption
            }
            TextField {
                id: njEn
                visible: pickerMode === "maker"
                Layout.fillWidth: true
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

            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                ActionButton {
                    text: "취소"
                    primary: false
                    onClicked: newEntryPopup.close()
                }
                ActionButton {
                    text: "추가"
                    onClicked: {
                        if (pickerMode === "maker") {
                            LibraryModel.insertNewMaker(njJa.text, njKo.text, njEn.text)
                        } else if (pickerMode === "genre") {
                            LibraryModel.insertNewGenre(njJa.text, njKo.text)
                        } else {
                            LibraryModel.insertNewActress(njJa.text, njKo.text)
                        }
                        newEntryPopup.close()
                        root.refresh()
                    }
                }
            }
        }
    }
}