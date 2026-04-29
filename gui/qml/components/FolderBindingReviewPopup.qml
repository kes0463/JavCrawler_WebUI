import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import ".."
import "."

Popup {
    id: root
    modal: true
    dim: true
    focus: true
    /** 바깥 클릭으로 닫히면 알림 맥락이 사라져 인박스로 모으는 흐름과 충돌하므로 ESC·닫기만 허용 */
    closePolicy: Popup.CloseOnEscape
    padding: Theme.spacingMd
    parent: Overlay.overlay
    anchors.centerIn: Overlay.overlay
    width: Math.min(560, Overlay.overlay.width - 48)
    z: 150

    signal resolved(string productCode)

    property string productCode: ""
    property string oldPath: ""
    /** Python list[str] → QML 배열 */
    property var candidates: []

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
            text: "폴더 연결 확인"
            font.pixelSize: Theme.fontSubtitle
            font.weight: Font.DemiBold
            color: Theme.textPrimary
            Layout.fillWidth: true
        }

        Text {
            text: "라이브러리·미디어 설정 경로 아래에서 품번이 폴더 이름에 포함된 위치를 검색했습니다. 목록에서 고르거나, 아래에서 탐색기로 직접 폴더를 지정할 수 있습니다."
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
            color: Theme.textSecondary
            font.pixelSize: Theme.fontCaption
        }

        Text {
            text: "<b>품번</b> " + root.productCode
            textFormat: Text.RichText
            Layout.fillWidth: true
            color: Theme.textPrimary
            font.pixelSize: Theme.fontBody
            wrapMode: Text.WrapAnywhere
        }

        Text {
            text: "<b>저장된 경로</b> " + root.oldPath
            textFormat: Text.RichText
            Layout.fillWidth: true
            color: Theme.textPrimary
            font.pixelSize: Theme.fontBody
            wrapMode: Text.WrapAnywhere
        }

        Text {
            visible: !root.candidates || root.candidates.length === 0
            text: "자동으로 찾은 후보 경로가 없습니다. 라이브러리에서 해당 작품을 열고 폴더를 직접 연결해 주세요."
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
            color: Theme.warning
            font.pixelSize: Theme.fontCaption
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingSm

            ActionButton {
                text: "후보 다시 검색"
                primary: false
                Layout.fillWidth: false
                onClicked: {
                    root.candidates = LibraryModel.searchFolderBindingCandidates(
                        root.productCode,
                        root.oldPath
                    )
                }
            }

            ActionButton {
                text: "폴더 직접 지정…"
                primary: false
                Layout.fillWidth: false
                onClicked: root.openManualFolderPicker()
            }

            Text {
                text: root.candidates && root.candidates.length > 0
                    ? ("후보 " + root.candidates.length + "건 (유사 순)")
                    : ""
                color: Theme.textMuted
                font.pixelSize: Theme.fontCaption
                Layout.fillWidth: true
                elide: Text.ElideRight
            }
        }

        AppScrollView {
            id: candScroll
            Layout.fillWidth: true
            Layout.preferredHeight: 260
            visible: root.candidates && root.candidates.length > 0
            clip: true
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

            Column {
                spacing: Theme.spacingSm
                width: Math.max(1, candScroll.availableWidth > 8
                    ? candScroll.availableWidth
                    : (root.width - 2 * root.padding))

                Repeater {
                    model: root.candidates || []
                    delegate: ActionButton {
                        required property int index
                        required property string modelData
                        width: parent.width
                        text: (index + 1) + ". 연결 → " + modelData
                        primary: false
                        onClicked: {
                            if (LibraryModel.bindFolderForced(root.productCode, modelData, true)) {
                                root.resolved(root.productCode)
                                root.close()
                            }
                        }
                    }
                }
            }
        }

        RowLayout {
            Layout.alignment: Qt.AlignRight
            spacing: Theme.spacingSm

            ActionButton {
                text: "닫기"
                primary: false
                onClicked: root.close()
            }
        }
    }

    /** 저장 경로의 상위 폴더를 탐색기 시작 위치로 (드라이브 루트 예외 처리) */
    function pickerStartFolderUrl() {
        var p = root.oldPath
        if (!p || p.length === 0)
            return undefined
        var s = String(p).replace(/\\/g, "/").replace(/\/+$/, "")
        var i = s.lastIndexOf("/")
        var parent = ""
        if (i > 0)
            parent = s.substring(0, i)
        else
            return undefined
        if (parent.length === 2 && parent.charAt(1) === ":")
            parent = parent + "/"
        return Qt.resolvedUrl("file:///" + parent)
    }

    function openManualFolderPicker() {
        var u = root.pickerStartFolderUrl()
        if (u !== undefined)
            folderPickDialog.currentFolder = u
        folderPickDialog.open()
    }

    FolderDialog {
        id: folderPickDialog
        title: "작품(" + root.productCode + ") 폴더 연결"
        onAccepted: {
            var path = selectedFolder.toString()
            if (path.startsWith("file:///"))
                path = path.replace("file:///", "")
            path = decodeURIComponent(path)
            if (LibraryModel.bindFolderForced(root.productCode, path, true)) {
                root.resolved(root.productCode)
                root.close()
            }
        }
    }
}