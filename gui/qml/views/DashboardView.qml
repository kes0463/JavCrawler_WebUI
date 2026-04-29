import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"
import ".."
import "."

Item {
    id: root
    
    // ── 삭제 확인 팝업 ──────────────────────────────────
    Rectangle {
        id: deleteConfirmPopup
        anchors.fill: parent
        color: "#CC000000"
        visible: false
        z: 100
        property string targetSku: ""
        MouseArea { anchors.fill: parent; onClicked: {} }
        GlassCard {
            width: 320; height: 180; anchors.centerIn: parent
            Column {
                anchors.centerIn: parent; spacing: Theme.spacingLg; width: parent.width - 40
                Text { text: "작업 취소"; color: Theme.textPrimary; font.pixelSize: Theme.fontSubtitle; font.weight: Font.Bold; anchors.horizontalCenter: parent.horizontalCenter }
                Text {
                    text: deleteConfirmPopup.targetSku + "\n작업을 대기열에서 삭제하시겠습니까?"
                    color: Theme.textSecondary; font.pixelSize: Theme.fontBody; horizontalAlignment: Text.AlignHCenter; anchors.horizontalCenter: parent.horizontalCenter; width: parent.width; wrapMode: Text.WordWrap
                }
                Row {
                    anchors.horizontalCenter: parent.horizontalCenter; spacing: Theme.spacingMd
                    ActionButton { text: "아니오"; primary: false; onClicked: deleteConfirmPopup.visible = false }
                    ActionButton {
                        text: "예, 삭제합니다"; primary: true
                        onClicked: { DashboardModel.cancelPending(deleteConfirmPopup.targetSku); deleteConfirmPopup.visible = false }
                    }
                }
            }
        }
    }

    // ── 재사용 가능한 삭제 버튼 ──────────────────────────────
    component DeleteButton : Item {
        id: delBtnRoot
        width: 24; height: 24
        signal clicked()
        Rectangle {
            anchors.fill: parent; radius: 4; color: mouseArea.containsMouse ? Qt.rgba(1, 0, 0, 0.1) : "transparent"
            Text { anchors.centerIn: parent; text: "✕"; font.pixelSize: 14; color: mouseArea.containsMouse ? Theme.error : Theme.textMuted }
        }
        MouseArea { id: mouseArea; anchors.fill: parent; hoverEnabled: true; onClicked: delBtnRoot.clicked() }
    }

    // ── 메인 레이아웃 ──────────────────────────────────────
    AppScrollView {
        anchors.fill: parent
        contentWidth: availableWidth
        clip: true

        ColumnLayout {
            id: layout
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: Theme.spacingLg
            spacing: Theme.spacingLg

            // ── 시스템 리소스 ──────────────────────────────
            RowLayout {
                Layout.fillWidth: true; spacing: Theme.spacingLg
                
                GlassCard {
                    autoSize: false
                    Layout.fillWidth: true; Layout.preferredHeight: 120
                    RowLayout {
                        width: parent.width - Theme.spacingMd * 2
                        anchors.horizontalCenter: parent.horizontalCenter
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: Theme.spacingLg
                        ProgressIndicator {
                            Layout.preferredWidth: 80; Layout.preferredHeight: 80
                            value: DashboardModel.gpuUsed / DashboardModel.gpuTotal; circular: true; barColor: Theme.accentNeon
                        }
                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 4
                            Text { 
                                text: "GPU VRAM"; color: Theme.textPrimary
                                font.pixelSize: Theme.fontSubtitle; font.weight: Font.DemiBold 
                            }
                            Text { 
                                text: DashboardModel.gpuName || "GPU 미감지"
                                font.pixelSize: Theme.fontCaption; color: Theme.textSecondary
                                elide: Text.ElideRight; Layout.fillWidth: true 
                            }
                            Text { 
                                text: DashboardModel.gpuUsed.toFixed(1) + " / " + DashboardModel.gpuTotal.toFixed(1) + " GB"
                                font.pixelSize: Theme.fontBody; font.weight: Font.DemiBold; color: Theme.textPrimary 
                            }
                        }
                    }
                }

                GlassCard {
                    autoSize: false
                    Layout.fillWidth: true; Layout.preferredHeight: 120
                    ColumnLayout {
                        width: parent.width - Theme.spacingMd * 2
                        anchors.horizontalCenter: parent.horizontalCenter
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: Theme.spacingSm
                        Text { 
                            text: "시스템 정보"; color: Theme.textPrimary
                            font.pixelSize: Theme.fontSubtitle; font.weight: Font.DemiBold 
                        }
                        
                        RowLayout {
                            Layout.fillWidth: true; spacing: Theme.spacingMd
                            Text { 
                                text: "CPU"; Layout.preferredWidth: 40
                                font.pixelSize: Theme.fontCaption; color: Theme.textSecondary 
                            }
                            ProgressIndicator { 
                                Layout.fillWidth: true; value: DashboardModel.cpuPercent / 100; barColor: Theme.primaryBlue 
                            }
                            Text { 
                                text: DashboardModel.cpuPercent + "%"
                                Layout.preferredWidth: 40; horizontalAlignment: Text.AlignRight
                                font.pixelSize: Theme.fontCaption; font.weight: Font.DemiBold; color: Theme.textPrimary 
                            }
                        }
                        
                        RowLayout {
                            Layout.fillWidth: true; spacing: Theme.spacingMd
                            Text { 
                                text: "MEM"; Layout.preferredWidth: 40
                                font.pixelSize: Theme.fontCaption; color: Theme.textSecondary 
                            }
                            ProgressIndicator { 
                                Layout.fillWidth: true; value: DashboardModel.memUsed / DashboardModel.memTotal; barColor: Theme.primaryBlue 
                            }
                            Text { 
                                text: DashboardModel.memUsed.toFixed(1) + " / " + DashboardModel.memTotal.toFixed(1) + " GB"
                                font.pixelSize: Theme.fontCaption; font.weight: Font.DemiBold; color: Theme.textPrimary 
                            }
                        }
                    }
                }
            }

            // ── 작업 큐 리스트 (고정 헤더 정렬 구조) ──

            // 1. 대기 큐
            QueueAccordionCard {
                id: pendingCard
                title: "대기 큐"
                badgeStatus: DashboardModel.pendingCount > 0 ? "running" : "none"
                badgeLabel: DashboardModel.pendingCount + "건"
                emptyText: "대기 중인 항목이 없습니다."
                model: DashboardModel.pendingQueue

                ActionButton {
                    implicitWidth: Theme.queueHeaderButtonMinWidth
                    Layout.preferredWidth: Theme.queueHeaderButtonMinWidth
                    fixedWidthMode: true
                    fixedWidth: Theme.queueHeaderButtonMinWidth
                    text: "큐 비우기"
                    primary: false
                    height: 32
                    enabled: DashboardModel.pendingCount > 0
                    onClicked: DashboardModel.clearAllPending()
                }

                delegate: QueueItemRow {
                    width: ListView.view.width
                    codeText: model.sku
                    titleText: model.title
                    progressValue: -1
                    highlightCode: true
                    showDelete: true
                    onDeleteClicked: DashboardModel.cancelPending(model.sku)
                }
            }

            // 2. 번역 큐 (기본 펼침: 수집 워커가 메인 스레드가 아닌 곳에서 enqueue 해도
            //   리스트는 메인에서만 갱신 — 펼쳤을 때 뷰포트를 넉넉히)
            QueueAccordionCard {
                id: translationCard
                title: "번역 큐 (AI)"
                expanded: false
                expandedHeight: 580
                badgeStatus: (TranslationQueue.runningCount > 0) ? "running" : (TranslationQueue.queuedCount > 0 ? "queued" : "none")
                badgeLabel: TranslationQueue.summaryLabel.length > 0 ? TranslationQueue.summaryLabel : "0건"
                emptyText: "대기 중인 번역 작업이 없습니다."
                model: TranslationQueue

                ActionButton {
                    implicitWidth: Theme.queueHeaderButtonMinWidth
                    Layout.preferredWidth: Theme.queueHeaderButtonMinWidth
                    fixedWidthMode: true
                    fixedWidth: Theme.queueHeaderButtonMinWidth
                    text: "이어서 하기"
                    primary: false
                    height: 32
                    enabled: TranslationQueue.count > 0
                    onClicked: TranslationQueue.resume()
                }
                ActionButton {
                    implicitWidth: Theme.queueHeaderButtonMinWidth
                    Layout.preferredWidth: Theme.queueHeaderButtonMinWidth
                    fixedWidthMode: true
                    fixedWidth: Theme.queueHeaderButtonMinWidth
                    text: "완료 제거"
                    primary: false
                    height: 32
                    enabled: TranslationQueue.count > 0
                    onClicked: TranslationQueue.clearFinished()
                }

                delegate: QueueItemRow {
                    width: ListView.view.width
                    codeText: model.sku || ""
                    titleText: (model.status === "running" ? "⏳ [번역 중] " : (model.status === "queued" ? "대기 · " : "")) + (model.video_path || "")
                    // queued는 바 숨김(0% 막대 제거), running은 인디터미너트
                    progressValue: -1
                    progressIndeterminate: model.status === "running"
                    highlightCode: true
                }
            }

            // 3. 하이라이트 큐
            QueueAccordionCard {
                id: highlightCard
                title: "하이라이트 큐"
                badgeStatus: HighlightQueue.pendingCount > 0 ? "running" : "none"
                badgeLabel: HighlightQueue.runningCount + " 실행 / " + HighlightQueue.pendingCount + " 대기"
                emptyText: "처리 중인 항목이 없습니다."
                model: HighlightQueue.queue

                ActionButton {
                    implicitWidth: Theme.queueHeaderButtonMinWidth
                    Layout.preferredWidth: Theme.queueHeaderButtonMinWidth
                    fixedWidthMode: true
                    fixedWidth: Theme.queueHeaderButtonMinWidth
                    text: "이어서 하기"
                    primary: false
                    height: 32
                    enabled: HighlightQueue.pendingCount > 0
                    onClicked: HighlightQueue.resume()
                }
                ActionButton {
                    implicitWidth: Theme.queueHeaderButtonMinWidth
                    Layout.preferredWidth: Theme.queueHeaderButtonMinWidth
                    fixedWidthMode: true
                    fixedWidth: Theme.queueHeaderButtonMinWidth
                    text: "완료 제거"
                    primary: false
                    height: 32
                    onClicked: HighlightQueue.clearFinished()
                }

                delegate: QueueItemRow {
                    width: ListView.view.width
                    codeText: model.productCode || ""
                    titleText: model.videoName || ""
                    progressValue: ((model.progress || 0) / 100)
                    progressText: model.message || ""
                    highlightCode: true
                    showDelete: true
                    onDeleteClicked: HighlightQueue.removeJob(model.jobId)
                }
            }

            // 3. 프리뷰 큐
            QueueAccordionCard {
                id: previewCard
                title: "프리뷰 큐"
                badgeStatus: PreviewQueue.pendingCount > 0 ? "running" : "none"
                badgeLabel: PreviewQueue.runningCount + " 실행 / " + PreviewQueue.pendingCount + " 대기"
                emptyText: "처리 중인 항목이 없습니다."
                model: PreviewQueue.queue

                ActionButton {
                    implicitWidth: Theme.queueHeaderButtonMinWidth
                    Layout.preferredWidth: Theme.queueHeaderButtonMinWidth
                    fixedWidthMode: true
                    fixedWidth: Theme.queueHeaderButtonMinWidth
                    text: "이어서 하기"
                    primary: false
                    height: 32
                    enabled: PreviewQueue.pendingCount > 0
                    onClicked: PreviewQueue.resume()
                }
                ActionButton { implicitWidth: Theme.queueHeaderButtonMinWidth; Layout.preferredWidth: Theme.queueHeaderButtonMinWidth; fixedWidthMode: true; fixedWidth: Theme.queueHeaderButtonMinWidth; text: "백필"; primary: false; height: 32; onClicked: PreviewQueue.enqueueMissingPreviews() }
                ActionButton { implicitWidth: Theme.queueHeaderButtonMinWidth; Layout.preferredWidth: Theme.queueHeaderButtonMinWidth; fixedWidthMode: true; fixedWidth: Theme.queueHeaderButtonMinWidth; text: "재생성"; primary: false; height: 32; onClicked: PreviewQueue.enqueueAllPreviewsForce() }
                ActionButton { implicitWidth: Theme.queueHeaderButtonMinWidth; Layout.preferredWidth: Theme.queueHeaderButtonMinWidth; fixedWidthMode: true; fixedWidth: Theme.queueHeaderButtonMinWidth; text: "완료 제거"; primary: false; height: 32; onClicked: PreviewQueue.clearFinished() }

                delegate: QueueItemRow {
                    width: ListView.view.width
                    codeText: model.productCode || ""
                    titleText: model.videoName || ""
                    progressValue: ((model.progress || 0) / 100)
                    progressText: model.message || ""
                    highlightCode: true
                    showDelete: true
                    onDeleteClicked: PreviewQueue.removeJob(model.jobId)
                }
            }

            // 4. 몽타주 큐
            QueueAccordionCard {
                id: montageCard
                title: "몽타주 큐"
                badgeStatus: MontageQueue.pendingCount > 0 ? "running" : "none"
                badgeLabel: MontageQueue.runningCount + " 실행 / " + MontageQueue.pendingCount + " 대기"
                emptyText: "처리 중인 항목이 없습니다."
                model: MontageQueue.queue

                ActionButton {
                    implicitWidth: Theme.queueHeaderButtonMinWidth
                    Layout.preferredWidth: Theme.queueHeaderButtonMinWidth
                    fixedWidthMode: true
                    fixedWidth: Theme.queueHeaderButtonMinWidth
                    text: "이어서 하기"
                    primary: false
                    height: 32
                    enabled: MontageQueue.pendingCount > 0
                    onClicked: MontageQueue.resume()
                }
                ActionButton {
                    implicitWidth: Theme.queueHeaderButtonMinWidth
                    Layout.preferredWidth: Theme.queueHeaderButtonMinWidth
                    fixedWidthMode: true
                    fixedWidth: Theme.queueHeaderButtonMinWidth
                    text: "완료 제거"
                    primary: false
                    height: 32
                    onClicked: MontageQueue.clearFinished()
                }

                delegate: QueueItemRow {
                    width: ListView.view.width
                    codeText: model.productCode || ""
                    titleText: model.videoName || ""
                    progressValue: ((model.progress || 0) / 100)
                    highlightCode: true
                    showDelete: true
                    onDeleteClicked: MontageQueue.removeJob(model.jobId)
                }
            }

            // 5. 모자이크 제거 큐
            QueueAccordionCard {
                id: mosaicCard
                title: "모자이크 제거 큐 (LADA)"
                badgeStatus: (MosaicQueue.runningCount > 0 || MosaicQueue.notStartedCount > 0) ? "running" : "none"
                badgeLabel: MosaicQueue.runningCount + " 실행 / " + MosaicQueue.notStartedCount + " 대기"
                emptyText: "처리 중인 항목이 없습니다."
                model: MosaicQueue.queue

                ActionButton {
                    implicitWidth: Theme.queueHeaderButtonMinWidth
                    Layout.preferredWidth: Theme.queueHeaderButtonMinWidth
                    fixedWidthMode: true
                    fixedWidth: Theme.queueHeaderButtonMinWidth
                    text: "이어서 하기"
                    primary: false
                    height: 32
                    enabled: MosaicQueue.notStartedCount > 0
                    onClicked: MosaicQueue.resume()
                }
                ActionButton {
                    implicitWidth: Theme.queueHeaderButtonMinWidth
                    Layout.preferredWidth: Theme.queueHeaderButtonMinWidth
                    fixedWidthMode: true
                    fixedWidth: Theme.queueHeaderButtonMinWidth
                    text: MosaicQueue.processingEnabled ? "처리 중" : "시작"
                    primary: true
                    height: 32
                    enabled: !MosaicQueue.processingEnabled && MosaicQueue.notStartedCount > 0
                    onClicked: MosaicQueue.startQueue()
                }
                ActionButton {
                    implicitWidth: Theme.queueHeaderButtonMinWidth
                    Layout.preferredWidth: Theme.queueHeaderButtonMinWidth
                    fixedWidthMode: true
                    fixedWidth: Theme.queueHeaderButtonMinWidth
                    text: "완료 제거"
                    primary: false
                    height: 32
                    onClicked: MosaicQueue.clearFinished()
                }

                delegate: QueueItemRow {
                    width: ListView.view.width
                    codeText: model.productCode || ""
                    titleText: model.videoName || ""
                    progressValue: ((model.progress || 0) / 100)
                    progressIndeterminate: (model.status === "running") && (!model.progress || model.progress === 0)
                    progressText: model.message || ""
                    highlightCode: true
                    showDelete: true
                    onDeleteClicked: MosaicQueue.removeJob(model.jobId)
                }
            }
        }
    }
}