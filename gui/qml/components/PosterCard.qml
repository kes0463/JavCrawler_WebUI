import QtQuick
import QtQuick.Controls
import Qt5Compat.GraphicalEffects
import ".."

Rectangle {
    id: root

    property string productCode: ""
    property string titleKo: ""
    property string actorsKo: ""
    property int sceneCount: 0
    property string coverPath: ""
    property string previewPath: ""
    property string pipelineStage: "none"
    property bool hasCanonical: false
    property int partCount: 1
    property bool hasJaSrt: false
    property bool hasKoSrt: false
    property bool lampHardcoded: false
    property bool lampMopa: false
    property bool selectionMode: false
    property bool selected: false

    signal clicked(string sku)
    signal playRequested(string sku, rect startRect)
    signal selectionToggled(string sku, bool selected)
    signal pressAndHold(string sku)

    width: 200
    height: 300
    property int margin: 6
    radius: Theme.radiusMd
    color: Theme.surface
    border.color: root.selected ? Theme.accentNeon : (mouseArea.containsMouse ? Theme.glassBorderHover : Theme.glassBorder)
    border.width: root.selected ? 3 : 1
    clip: true

    scale: mouseArea.containsMouse ? 1.03 : (root.selected ? 0.98 : 1.0)
    Behavior on scale { NumberAnimation { duration: Theme.animFast; easing.type: Easing.OutCubic } }
    Behavior on border.color { ColorAnimation { duration: Theme.animFast } }

    MouseArea {
        id: mouseArea
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onEntered: previewDelay.restart()
        onExited: {
            previewDelay.stop()
            previewLoader.active = false
        }
        onClicked: {
            if (root.selectionMode) {
                root.selected = !root.selected
                root.selectionToggled(root.productCode, root.selected)
            } else {
                root.clicked(root.productCode)
            }
        }
        onPressAndHold: {
            if (!root.selectionMode) {
                root.pressAndHold(root.productCode)
            }
        }
    }

    Column {
        anchors.fill: parent
        anchors.margins: root.margin
        spacing: 0

        Timer {
            id: previewDelay
            interval: 180
            repeat: false
            onTriggered: {
                // 짧은 스침(hover)에서는 프리뷰 디코딩을 안 켜서 스파이크를 줄임
                if (mouseArea.containsMouse && !!root.previewPath)
                    previewLoader.active = true
            }
        }

        // 커버 이미지
        Rectangle {
            width: parent.width
            height: parent.height * 0.68 // 고정 200 대신 전체의 약 68% 할당
            color: Theme.bgSecondary
            clip: true

            Image {
                anchors.fill: parent
                source: root.coverPath ? Theme.pathToUrl(root.coverPath) : ""
                fillMode: Image.PreserveAspectCrop
                asynchronous: true
                // 라이브러리 표지 선명도 개선(과도한 메모리/디코딩을 막기 위해 상한을 둠)
                sourceSize.width: Math.min(720, Math.round(root.width * 3))
                visible: status === Image.Ready && (!previewLoader.active)
            }

            Loader {
                id: previewLoader
                anchors.fill: parent
                active: false
                sourceComponent: AnimatedImage {
                    source: root.previewPath ? Theme.pathToUrl(root.previewPath) : ""
                    fillMode: Image.PreserveAspectCrop
                    playing: true
                    cache: false
                }
            }

            // [삭제됨] 이전의 전체 커버 재생 오버레이 제거

            Text {
                anchors.centerIn: parent
                text: root.productCode
                font.pixelSize: Theme.fontSubtitle
                font.weight: Font.Bold
                color: Theme.textMuted
                visible: !root.coverPath
            }

            // 선택 모드 체크 오버레이
            Rectangle {
                visible: root.selectionMode
                width: 28
                height: 28
                radius: 14
                color: root.selected ? Theme.accentNeon : Theme.surfaceLight
                border.color: root.selected ? "transparent" : Theme.glassBorderHover
                border.width: 1
                anchors.top: parent.top
                anchors.right: parent.right
                anchors.margins: 8

                Text {
                    anchors.centerIn: parent
                    text: root.selected ? "✓" : ""
                    font.pixelSize: 16
                    font.weight: Font.ExtraBold
                    color: Theme.isDark ? "#0A0E1A" : "#FFFFFF"
                }
            }
        }

        // 정보 영역
        Column {
            width: parent.width
            padding: Theme.spacingSm
            spacing: 4

            Text {
                text: root.productCode
                font.pixelSize: Theme.fontCaption
                font.weight: Font.Bold
                color: Theme.accentNeon
                width: parent.width - Theme.spacingSm * 2
            }

            Text {
                text: root.titleKo || "제목 없음"
                font.pixelSize: Theme.fontCaption
                color: Theme.textPrimary
                width: parent.width - Theme.spacingSm * 2
                elide: Text.ElideRight
                maximumLineCount: 1
            }

            Text {
                text: root.actorsKo || ""
                font.pixelSize: Theme.fontCaption - 1
                color: Theme.textSecondary
                width: parent.width - Theme.spacingSm * 2
                elide: Text.ElideRight
                maximumLineCount: 1
                visible: root.actorsKo !== ""
            }

            Row {
                spacing: 4

                StatusBadge {
                    visible: root.hasJaSrt
                    status: "transcription"
                    label: "S"
                }

                StatusBadge {
                    visible: root.hasKoSrt
                    status: "translation"
                    label: "B"
                }

                StatusBadge {
                    visible: root.lampHardcoded
                    status: "canonical"
                    label: "자"
                }

                StatusBadge {
                    visible: root.lampMopa
                    status: "canonical"
                    label: "모파"
                }

                StatusBadge {
                    visible: root.partCount > 1
                    status: "queued"
                    label: "P" + root.partCount
                }

                Text {
                    visible: root.sceneCount > 0
                    text: root.sceneCount + " scenes"
                    font.pixelSize: Theme.fontCaption - 2
                    color: Theme.textMuted
                    anchors.verticalCenter: parent.verticalCenter
                }
            }
        }
    }

    // [신규] 카드 우측 하단 재생 버튼
    Rectangle {
        id: playBtn
        width: 32; height: 32; radius: 16
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: 10
        color: playMa.containsMouse ? Theme.accentNeon : Qt.rgba(0, 0, 0, 0.6)
        border.color: Theme.accentNeon
        border.width: 1
        visible: !root.selectionMode && !!root.previewPath
        z: 10
        
        layer.enabled: true
        layer.effect: DropShadow {
            transparentBorder: true
            radius: 4
            samples: 9
            color: "#80000000"
        }

        Text {
            anchors.centerIn: parent
            text: "▶"
            font.pixelSize: 14
            color: playMa.containsMouse ? "#000" : "#FFF"
            leftPadding: 2
        }

        MouseArea {
            id: playMa
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: {
                var globalPos = root.mapToItem(null, 0, 0)
                root.playRequested(root.productCode, Qt.rect(globalPos.x, globalPos.y, root.width, root.height))
            }
        }
    }
}