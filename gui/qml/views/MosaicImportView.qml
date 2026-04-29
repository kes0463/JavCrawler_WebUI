import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."
import "../components"

Item {
    id: root

    property bool recursiveScan: true

    Column {
        anchors.fill: parent
        anchors.margins: Theme.spacingLg
        spacing: Theme.spacingLg

        Text {
            text: "모자이크 제거 (폴더/드래그&드롭)"
            font.pixelSize: Theme.fontTitle
            font.weight: Font.ExtraBold
            color: Theme.textPrimary
        }

        GlassCard {
            width: parent.width

            Column {
                width: parent.width
                spacing: Theme.spacingSm

                Text {
                    text: "폴더를 선택하거나, 아래 영역에 폴더/파일을 드롭하면 큐에만 추가됩니다. 대시보드 또는 이 화면의 '시작'을 눌러 실행하세요."
                    font.pixelSize: Theme.fontBody
                    color: Theme.textSecondary
                    wrapMode: Text.Wrap
                }

                Row {
                    spacing: Theme.spacingSm
                    width: parent.width

                    ActionButton {
                        text: MosaicQueue.processingEnabled ? "처리 중" : "시작"
                        primary: true
                        enabled: !MosaicQueue.processingEnabled && MosaicQueue.notStartedCount > 0
                        onClicked: MosaicQueue.startQueue()
                    }
                    Text {
                        text: (!MosaicQueue.processingEnabled && MosaicQueue.notStartedCount > 0)
                              ? (MosaicQueue.notStartedCount + "건 대기")
                              : ""
                        font.pixelSize: Theme.fontCaption
                        color: Theme.textMuted
                        anchors.verticalCenter: parent.verticalCenter
                    }

                    Switch {
                        id: recursiveSwitch
                        checked: root.recursiveScan
                        onToggled: root.recursiveScan = checked
                    }
                    Text {
                        text: "하위 폴더까지 스캔"
                        font.pixelSize: Theme.fontBody
                        color: Theme.textSecondary
                        anchors.verticalCenter: parent.verticalCenter
                    }

                    Item { width: 12; height: 1 }

                    ActionButton {
                        text: "폴더 선택"
                        onClicked: {
                            var p = SettingsModel.browseFolder()
                            if (p) {
                                MosaicQueue.enqueueFolder(p, root.recursiveScan)
                            }
                        }
                    }
                }
            }
        }

        Rectangle {
            id: dropZone
            width: parent.width
            height: Math.max(260, parent.height - 260)
            radius: Theme.radiusMd
            color: Theme.surfaceLight
            border.width: 2
            border.color: dropArea.containsDrag ? Theme.accentNeon : Theme.glassBorder

            Text {
                anchors.centerIn: parent
                text: dropArea.containsDrag ? "여기에 놓기" : "여기로 폴더/동영상 파일을 드래그&드롭"
                font.pixelSize: Theme.fontSubtitle
                font.weight: Font.DemiBold
                color: Theme.textMuted
            }

            DropArea {
                id: dropArea
                anchors.fill: parent
                onDropped: function(drop) {
                    if (!drop || !drop.urls)
                        return
                    for (var i = 0; i < drop.urls.length; i++) {
                        MosaicQueue.enqueueUrl(drop.urls[i].toString())
                    }
                }
            }
        }
    }
}