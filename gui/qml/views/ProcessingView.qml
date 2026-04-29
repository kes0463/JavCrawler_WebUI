import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."
import "../components"

Item {
    id: root

    property string selectedVideoPath: ""

    function _urlToLocalPath(u) {
        // QML DropArea urls: e.g. "file:///D:/Foo/Bar" or "file:///C:/..."
        var s = "" + u
        if (s.indexOf("file://") === 0) {
            s = s.replace("file://", "")
            // Windows 드라이브 경로는 file:///D:/... → /D:/... 형태가 될 수 있음
            if (s.length >= 3 && s[0] === "/" && s[2] === ":") {
                s = s.slice(1)
            }
        }
        try { s = decodeURIComponent(s) } catch (e) {}
        return s
    }

    function _isVideoPath(p) {
        var s = (p || "").toLowerCase()
        return s.endsWith(".mp4")
            || s.endsWith(".mkv")
            || s.endsWith(".avi")
            || s.endsWith(".mov")
            || s.endsWith(".webm")
            || s.endsWith(".m4v")
    }

    Connections {
        target: ProcessingModel
        function onToastMessage(msg, level) { window.showToast(msg, level); }
    }

    DropArea {
        id: dropArea
        anchors.fill: parent
        // Windows 탐색기 드롭은 keys 매칭이 불안정할 수 있어 제한하지 않는다.
        onEntered: function(drag) {
            if (drag && drag.hasUrls) drag.acceptProposedAction()
        }
        onDropped: function(drop) {
            if (drop) drop.acceptProposedAction()
            if (!drop || !drop.urls || drop.urls.length === 0) return;
            var paths = []
            for (var i = 0; i < drop.urls.length; i++) {
                var p = root._urlToLocalPath(drop.urls[i])
                if (p && root._isVideoPath(p)) paths.push(p)
            }
            if (paths.length === 0) {
                window.showToast("드롭된 영상 파일이 없습니다. (mp4/mkv/avi/mov/webm/m4v)", "info")
                return
            }
            ProcessingModel.addFiles(paths)
            if (!root.selectedVideoPath) root.selectedVideoPath = paths[0]
            window.showToast("전사 큐에 추가됨: " + paths.length + "개", "success")
        }
    }

    Rectangle {
        anchors.fill: parent
        visible: dropArea.containsDrag
        color: Qt.rgba(0, 0, 0, 0.25)
        z: 999

        Rectangle {
            anchors.centerIn: parent
            width: Math.min(parent.width - 80, 560)
            height: 140
            radius: Theme.radiusMd
            color: Theme.surface
            border.color: Theme.accentNeon
            border.width: 2

            Column {
                anchors.centerIn: parent
                spacing: 8

                Text {
                    text: "영상 파일을 여기로 드롭하면 전사 큐에 추가됩니다"
                    font.pixelSize: Theme.fontSubtitle
                    font.weight: Font.DemiBold
                    color: Theme.textPrimary
                    horizontalAlignment: Text.AlignHCenter
                    width: parent.width
                }
                Text {
                    text: "추가 후 「STT 시작」을 눌러 실행하세요"
                    font.pixelSize: Theme.fontCaption
                    color: Theme.textMuted
                    horizontalAlignment: Text.AlignHCenter
                    width: parent.width
                }
            }
        }
    }

    ColumnLayout {
        id: mainLayout
        anchors.fill: parent
        anchors.margins: Theme.spacingLg
        spacing: Theme.spacingLg

        // ── 헤더 ────────────────────────────────────
        Column {
            Layout.fillWidth: true
            spacing: 4
            Text {
                text: "전사 & 자막 (Processing)"
                font.pixelSize: Theme.fontTitle
                font.weight: Font.ExtraBold
                color: Theme.textPrimary
            }
            Text {
                text: ProcessingModel.currentFile || "영상을 선택하거나 큐를 사용하여 자막을 생성하세요."
                font.pixelSize: Theme.fontBody
                color: Theme.textSecondary
            }
        }

        // ── 전체 진행률 ─────────────────────────────
        ProgressIndicator {
            Layout.fillWidth: true
            value: ProcessingModel.progressPercent / 100
            barHeight: 6
        }

        // ── 파일 선택 + 멀티파트 ────────────────────
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingMd

            GlassCard {
                Layout.fillWidth: true
                Layout.preferredHeight: 110

                Text {
                    id: videoLabel
                    text: "영상 파일"
                    font.pixelSize: Theme.fontBody
                    font.weight: Font.DemiBold
                    color: Theme.textSecondary
                    anchors.top: parent.top
                    anchors.left: parent.left
                    anchors.topMargin: Theme.spacingSm
                    anchors.leftMargin: Theme.spacingMd
                }

                RowLayout {
                    anchors.top: videoLabel.bottom
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    anchors.margins: Theme.spacingMd
                    anchors.topMargin: 0
                    spacing: Theme.spacingSm

                    ActionButton {
                        text: "파일 선택"
                        primary: false
                        enabled: !ProcessingModel.isRunning
                        Layout.alignment: Qt.AlignVCenter
                        onClicked: {
                            var f = SettingsModel.browseFile();
                            if (f) {
                                root.selectedVideoPath = f;
                                ProcessingModel.addFile(f);
                            }
                        }
                    }

                    Text {
                        text: root.selectedVideoPath ? root.selectedVideoPath.split("/").pop().split("\\").pop() : "선택 없음"
                        font.pixelSize: Theme.fontCaption
                        color: Theme.textMuted
                        elide: Text.ElideMiddle
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignVCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                }
            }

            GlassCard {
                Layout.fillWidth: true
                Layout.preferredHeight: 110

                Text {
                    id: multiLabel
                    text: "멀티파트"
                    font.pixelSize: Theme.fontBody
                    font.weight: Font.DemiBold
                    color: Theme.textSecondary
                    anchors.top: parent.top
                    anchors.left: parent.left
                    anchors.topMargin: Theme.spacingSm
                    anchors.leftMargin: Theme.spacingMd
                }

                RowLayout {
                    anchors.top: multiLabel.bottom
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    anchors.margins: Theme.spacingMd
                    anchors.topMargin: 0

                    ActionButton {
                        text: "멀티파트 SRT 합성..."
                        primary: false
                        enabled: !ProcessingModel.isRunning
                        Layout.alignment: Qt.AlignVCenter
                    }
                }
            }
        }

        // ── 전사 큐 ─────────────────────────────────
        GlassCard {
            id: queueCard
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 200
            clip: true

            Column {
                anchors.fill: parent
                anchors.margins: Theme.spacingMd
                spacing: Theme.spacingSm

                Text {
                    id: queueTitle
                    text: "전사 큐"
                    font.pixelSize: Theme.fontSubtitle
                    font.weight: Font.DemiBold
                    color: Theme.textPrimary
                }

                ListView {
                    id: queueView
                    width: parent.width
                    height: parent.height - queueTitle.height - Theme.spacingSm
                    clip: true
                    model: ProcessingModel.queue
                    boundsBehavior: Theme.boundsBehavior
                    flickDeceleration: Theme.flickDeceleration
                    maximumFlickVelocity: Theme.maxVelocity
                    spacing: 2

                    ScrollBar.vertical: ScrollBar {
                        policy: ScrollBar.AsNeeded
                    }

                    delegate: Item {
                        id: delegateRoot
                        width: queueView.width
                        height: 48
                        
                        Rectangle {
                            anchors.fill: parent
                            anchors.margins: 2
                            radius: Theme.radiusSm
                            color: rowArea.containsMouse ? Theme.navHover : "transparent"
                            visible: rowArea.containsMouse
                        }

                        CheckBox {
                            id: cb
                            checked: model.checked
                            onToggled: ProcessingModel.toggleCheck(index, checked)
                            anchors.left: parent.left
                            anchors.leftMargin: Theme.spacingMd
                            anchors.verticalCenter: parent.verticalCenter
                            padding: 0
                            
                            indicator: Rectangle {
                                implicitWidth: 20
                                implicitHeight: 20
                                radius: 4
                                color: cb.checked ? Theme.accentNeon : "transparent"
                                border.color: cb.checked ? Theme.accentNeon : Theme.textMuted
                                border.width: 1.5

                                Text {
                                    text: "✓"
                                    anchors.centerIn: parent
                                    color: Theme.isDark ? "#0A0E1A" : "white"
                                    font.pixelSize: 14
                                    font.bold: true
                                    visible: cb.checked
                                }
                            }
                        }

                        Text {
                            id: fileNameText
                            text: model.fileName
                            font.pixelSize: Theme.fontBody - 1
                            font.weight: Font.Medium
                            color: Theme.textPrimary
                            elide: Text.ElideMiddle
                            anchors.left: cb.right
                            anchors.leftMargin: Theme.spacingMd
                            anchors.right: badgeContainer.left
                            anchors.rightMargin: Theme.spacingMd
                            anchors.verticalCenter: parent.verticalCenter
                            verticalAlignment: Text.AlignVCenter
                        }

                        StatusBadge {
                            id: badgeContainer
                            status: model.status === "done" ? "canonical"
                                  : model.status === "error" ? "error"
                                  : model.status === "running" ? "running"
                                  : model.status === "pending" ? "queued"
                                  : "none"
                            label: model.status
                            anchors.right: trashContainer.left
                            anchors.rightMargin: Theme.spacingMd
                            anchors.verticalCenter: parent.verticalCenter
                        }

                        Item {
                            id: trashContainer
                            width: 32; height: 32
                            anchors.right: parent.right
                            anchors.rightMargin: Theme.spacingMd
                            anchors.verticalCenter: parent.verticalCenter

                            Text {
                                anchors.centerIn: parent
                                text: "🗑"
                                font.pixelSize: 18
                                color: delArea.containsMouse ? Theme.error : Theme.textPrimary
                                opacity: delArea.containsMouse ? 1.0 : 0.65
                                Behavior on color { ColorAnimation { duration: 150 } }
                                Behavior on opacity { NumberAnimation { duration: 150 } }
                            }

                            MouseArea {
                                id: delArea
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: ProcessingModel.removeQueueItem(index)
                            }
                        }

                        MouseArea {
                            id: rowArea
                            anchors.fill: parent
                            hoverEnabled: true
                            acceptedButtons: Qt.NoButton
                            z: -1
                        }
                    }

                    Text {
                        visible: queueView.count === 0
                        anchors.centerIn: parent
                        text: "큐가 비어 있습니다. 파일을 추가하세요."
                        font.pixelSize: Theme.fontBody
                        color: Theme.textMuted
                    }
                }
            }
        }

        // ── 컨트롤 버튼 ─────────────────────────────
        Row {
            Layout.fillWidth: true
            spacing: Theme.spacingSm

            ActionButton {
                text: "STT 시작"
                primary: true
                neonGlow: true
                enabled: !ProcessingModel.isRunning
                onClicked: {
                    ProcessingModel.startQueueStt();
                }
            }

            ActionButton {
                text: "자막 생성"
                primary: false
                enabled: !ProcessingModel.isRunning
                onClicked: {
                    ProcessingModel.startQueueSubtitle();
                }
            }

            ActionButton {
                text: "중지"
                primary: false
                enabled: ProcessingModel.isRunning
                onClicked: ProcessingModel.stop()
            }
        }

        // ── 진행 상태 ───────────────────────────────
        GlassCard {
            visible: ProcessingModel.isRunning || ProcessingModel.progressPercent > 0
            Layout.fillWidth: true
            Layout.preferredHeight: 80

            Row {
                anchors.fill: parent
                anchors.margins: Theme.spacingMd
                spacing: Theme.spacingMd

                ProgressIndicator {
                    circular: true
                    width: 48; height: 48
                    value: ProcessingModel.progressPercent / 100
                    anchors.verticalCenter: parent.verticalCenter
                }

                Column {
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 4

                    Text {
                        text: ProcessingModel.progressMessage || "대기 중..."
                        font.pixelSize: Theme.fontBody
                        color: Theme.textPrimary
                    }
                    Text {
                        text: ProcessingModel.progressPercent + "%"
                        font.pixelSize: Theme.fontCaption
                        color: Theme.textSecondary
                    }
                }
            }
        }

        // ── 로그 패널 ───────────────────────────────
        LogPanel {
            id: procLog
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 160

            Connections {
                target: ProcessingModel
                function onLogMessage(msg) { procLog.append(msg); }
            }
        }
    }
}