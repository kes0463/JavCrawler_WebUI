import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."
import "../components"

Item {
    id: root

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

    Connections {
        target: HarvestModel
        function onToastMessage(msg, level) { window.showToast(msg, level); }
    }

    DropArea {
        id: dropArea
        anchors.fill: parent
        // Windows 탐색기 드롭은 keys 매칭이 불안정할 수 있어 제한하지 않는다.
        // keys: ["text/uri-list"]
        onEntered: function(drag) {
            if (drag && drag.hasUrls) drag.acceptProposedAction()
        }
        onDropped: function(drop) {
            if (drop) drop.acceptProposedAction()
            if (!drop || !drop.urls || drop.urls.length === 0) return;
            var paths = []
            for (var i = 0; i < drop.urls.length; i++) {
                var p = root._urlToLocalPath(drop.urls[i])
                if (p) paths.push(p)
            }
            if (paths.length > 0) {
                HarvestModel.queueFolders(paths)
                window.showToast("드롭됨: " + paths.length + "개 경로를 큐에 추가 요청", "info")
            }
        }
    }

    Rectangle {
        anchors.fill: parent
        visible: dropArea.containsDrag
        color: Qt.rgba(0, 0, 0, 0.25)
        z: 999

        Rectangle {
            anchors.centerIn: parent
            width: Math.min(parent.width - 80, 520)
            height: 140
            radius: Theme.radiusMd
            color: Theme.surface
            border.color: Theme.accentNeon
            border.width: 2

            Column {
                anchors.centerIn: parent
                spacing: 8

                Text {
                    text: "폴더를 여기로 드롭하면 큐에 추가됩니다"
                    font.pixelSize: Theme.fontSubtitle
                    font.weight: Font.DemiBold
                    color: Theme.textPrimary
                    horizontalAlignment: Text.AlignHCenter
                    width: parent.width
                }
                Text {
                    text: "추가 후 「큐 수집 시작」을 눌러 실행하세요"
                    font.pixelSize: Theme.fontCaption
                    color: Theme.textMuted
                    horizontalAlignment: Text.AlignHCenter
                    width: parent.width
                }
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.spacingLg
        spacing: Theme.spacingLg

        // ── 헤더 + Grok 토글 ────────────────────────
        RowLayout {
            Layout.fillWidth: true

            Column {
                spacing: 4
                Text {
                    text: "수집 (Harvest)"
                    font.pixelSize: Theme.fontTitle
                    font.weight: Font.ExtraBold
                    color: Theme.textPrimary
                }
                Text {
                    text: "크롤링 · 다국어 번역 · DB 저장 · Grok 스토리 맥락"
                    font.pixelSize: Theme.fontBody
                    color: Theme.textSecondary
                }
            }

            Item { Layout.fillWidth: true }

            Row {
                spacing: Theme.spacingSm
                Text {
                    text: "Grok 스토리"
                    font.pixelSize: Theme.fontCaption
                    color: Theme.textSecondary
                    anchors.verticalCenter: parent.verticalCenter
                }
                Switch {
                    checked: HarvestModel.grokEnabled
                    onToggled: HarvestModel.grokEnabled = checked
                }
            }
        }

        // ── 검색창 ──────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingSm

            SearchBar {
                id: searchBar
                placeholderText: "품번 입력 (예: STAR-471, MIDE-123)"
                Layout.preferredWidth: 350
                Layout.preferredHeight: 40
                onAccepted: function(q) {
                    var val = q.trim();
                    if (val) {
                        HarvestModel.addTask(val);
                        searchBar.text = "";
                    }
                }
            }

            Flickable {
                id: buttonFlick
                Layout.fillWidth: true
                Layout.preferredHeight: 40
                contentWidth: buttonRow.implicitWidth
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                flickableDirection: Flickable.HorizontalFlick

                Row {
                    id: buttonRow
                    spacing: Theme.spacingSm
                    height: 40

                    ActionButton {
                        text: "수집 시작"
                        iconSource: "🚀"
                        primary: true
                        height: 40
                        onClicked: {
                            var val = searchBar.text.trim();
                            if (val) {
                                HarvestModel.addTask(val);
                                searchBar.text = "";
                            }
                        }
                    }

                    ActionButton {
                        text: "폴더 찾아보기"
                        primary: false
                        height: 40
                        onClicked: {
                            var paths = SettingsModel.browseFolders();
                            if (paths && paths.length > 0)
                                HarvestModel.queueFolders(paths);
                        }
                    }

                    ActionButton {
                        text: "폴더 수집"
                        primary: false
                        height: 40
                        onClicked: {
                            var path = SettingsModel.browseFolder();
                            if (path) HarvestModel.queueFolder(path);
                        }
                    }

                    ActionButton {
                        text: "상위 폴더 일괄"
                        primary: false
                        height: 40
                        onClicked: {
                            var path = SettingsModel.browseFolder();
                            if (path) HarvestModel.queueParentFolder(path);
                        }
                    }

                    Item { width: Theme.spacingSm; height: 40 }

                    ActionButton {
                        text: "큐 수집 시작 (" + HarvestModel.queuedCount + ")"
                        primary: true
                        neonGlow: true
                        enabled: HarvestModel.queuedCount > 0
                        height: 40
                        onClicked: HarvestModel.startQueued()
                    }

                    ActionButton {
                        text: "큐 비우기"
                        primary: false
                        enabled: HarvestModel.queuedCount > 0
                        height: 40
                        onClicked: HarvestModel.clearQueued()
                    }

                    ActionButton {
                        text: "완료 제거 (" + HarvestModel.finishedCount + ")"
                        primary: false
                        enabled: HarvestModel.finishedCount > 0
                        height: 40
                        onClicked: HarvestModel.removeFinished()
                    }
                }
                
                // 마우스 휠 스크롤 지원
                MouseArea {
                    anchors.fill: parent
                    acceptedButtons: Qt.NoButton
                    onWheel: function(wheel) {
                        buttonFlick.contentX = Math.max(0, Math.min(buttonFlick.contentWidth - buttonFlick.width, 
                                                                  buttonFlick.contentX - wheel.angleDelta.y));
                    }
                }
            }
        }


        // ── 카드(상단) + 로그(하단) 분할 ────────────────
        SplitView {
            id: harvestSplit
            Layout.fillWidth: true
            Layout.fillHeight: true
            orientation: Qt.Vertical

            // ── 수집 카드 그리드(메인) ──
            AppScrollView {
                SplitView.fillWidth: true
                SplitView.fillHeight: true
                SplitView.preferredHeight: 520
                contentWidth: availableWidth
                clip: true

                Flow {
                    id: taskGrid
                    width: parent.width
                    spacing: Theme.spacingSm + 4

                    Repeater {
                        model: HarvestModel.tasks

                        GlassCard {
                            width: 280
                            height: 128
                            hoverGlow: true

                            opacity: 0
                            Component.onCompleted: opacity = 1
                            Behavior on opacity { NumberAnimation { duration: Theme.animNormal } }

                            // ── 개별 삭제 버튼 (완료/에러 상태만 표시) ──
                            Item {
                                id: cardDeleteBtn
                                width: 22; height: 22
                                anchors.right: parent.right
                                anchors.top: parent.top
                                anchors.rightMargin: 6
                                anchors.topMargin: 6
                                z: 10
                                visible: model.status === "done" || model.status === "error"

                                Rectangle {
                                    anchors.fill: parent
                                    radius: 4
                                    color: delMouse.containsMouse ? Qt.rgba(1, 0, 0, 0.15) : "transparent"
                                    Behavior on color { ColorAnimation { duration: 100 } }

                                    Text {
                                        anchors.centerIn: parent
                                        text: "✕"
                                        font.pixelSize: 13
                                        color: delMouse.containsMouse ? Theme.error : Theme.textMuted
                                        Behavior on color { ColorAnimation { duration: 100 } }
                                    }
                                }

                                MouseArea {
                                    id: delMouse
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: HarvestModel.removeTask(model.sku)
                                }
                            }

                            Column {
                                anchors.fill: parent
                                anchors.margins: Theme.spacingSm
                                spacing: 8

                                RowLayout {
                                    width: parent.width

                                    Text {
                                        text: model.sku
                                        font.pixelSize: Theme.fontBody
                                        font.weight: Font.Bold
                                        color: Theme.accentNeon
                                        Layout.fillWidth: true
                                        elide: Text.ElideRight
                                    }

                                    StatusBadge {
                                        status: (model.message === "큐 대기" || model.status === "waiting") ? "queued"
                                              : model.status === "done" ? "canonical"
                                              : model.status === "error" ? "error"
                                              : model.status === "running" ? "running"
                                              : "none"
                                        label: (model.message === "큐 대기" || model.status === "waiting") ? "QUEUED" : model.status
                                    }
                                }

                                RowLayout {
                                    width: parent.width
                                    spacing: Theme.spacingSm

                                    ProgressIndicator {
                                        Layout.fillWidth: true
                                        value: (model.progress || 0) / 100
                                        barColor: (model.message === "큐 대기" || model.status === "waiting") ? Theme.warning
                                                : model.status === "error" ? Theme.error
                                                : Theme.accentNeon
                                    }

                                    Text {
                                        text: (model.status === "running" ? ((model.progress || 0) + "%") : "")
                                        visible: model.status === "running"
                                        font.pixelSize: Theme.fontCaption
                                        font.weight: Font.DemiBold
                                        color: Theme.accentNeon
                                    }
                                }

                                Text {
                                    text: model.message || ""
                                    font.pixelSize: Theme.fontCaption
                                    color: Theme.textMuted
                                    elide: Text.ElideRight
                                    width: parent.width
                                    maximumLineCount: 2
                                    wrapMode: Text.Wrap
                                }
                            }
                        }
                    }
                }
            }

            // ── 로그 패널(기본은 작게, 사용자 조절 가능) ──
            LogPanel {
                id: harvestLog
                SplitView.fillWidth: true
                SplitView.fillHeight: true
                SplitView.preferredHeight: 180

                Connections {
                    target: HarvestModel
                    function onLogMessage(msg) { harvestLog.append(msg); }
                }
            }
        }
    }
}