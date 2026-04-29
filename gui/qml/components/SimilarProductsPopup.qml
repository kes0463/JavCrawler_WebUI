import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Effects
import ".."

Popup {
    id: root
    width: Math.min(1000, parent.width * 0.9)
    height: Math.min(720, parent.height * 0.85)
    anchors.centerIn: parent
    modal: true
    focus: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

    property string queryProductCode: ""
    property alias model: resultsList.model
    property bool isLoading: false

    signal productClicked(string sku)

    background: Rectangle {
        color: Theme.surface
        radius: Theme.radiusLg
        border.color: Theme.glassBorder
        border.width: 1
        
        // 투명도/블러 효과 (앱 전체 스타일 유지)
        layer.enabled: true
        layer.effect: MultiEffect {
            blurEnabled: true
            blur: 0.1
        }
    }

    contentItem: Item {
        clip: true

        Column {
            anchors.fill: parent
            anchors.margins: Theme.spacingLg
            spacing: Theme.spacingMd

            // 헤더
            RowLayout {
                width: parent.width
                spacing: Theme.spacingSm
                
                Rectangle {
                    width: 4
                    Layout.preferredHeight: titleText.height
                    color: Theme.accentNeon
                    radius: 2
                    Layout.alignment: Qt.AlignVCenter
                }

                Text {
                    id: titleText
                    text: "AI 유사 작품 추천"
                    font.pixelSize: Theme.fontSubtitle
                    font.weight: Font.Bold
                    color: Theme.textPrimary
                }

                Text {
                    text: " - " + root.queryProductCode
                    font.pixelSize: Theme.fontSubtitle
                    color: Theme.textMuted
                    visible: !!root.queryProductCode
                }

                Item { Layout.fillWidth: true } // spacer

                ActionButton {
                    text: "✕"
                    primary: false
                    Layout.preferredWidth: 32
                    Layout.preferredHeight: 32
                    onClicked: root.close()
                }
            }

            // 로딩 상태
            Item {
                width: parent.width
                height: 300
                visible: root.isLoading

                Column {
                    anchors.centerIn: parent
                    spacing: 16

                    BusyIndicator {
                        anchors.horizontalCenter: parent.horizontalCenter
                        running: root.isLoading
                    }

                    Text {
                        text: "벡터 공간에서 문맥을 분석 중입니다..."
                        color: Theme.textSecondary
                        font.pixelSize: Theme.fontBody
                    }
                }
            }

            // 결과 없음
            Item {
                width: parent.width
                height: 300
                visible: !root.isLoading && resultsList.count === 0

                Text {
                    anchors.centerIn: parent
                    text: "유사한 작품을 찾을 수 없습니다.\n(다른 작품들의 임베딩이 생성되어 있어야 합니다)"
                    horizontalAlignment: Text.AlignHCenter
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontBody
                    lineHeight: 1.4
                }
            }

            // 결과 리스트 (Grid)
            AppScrollView {
                width: parent.width
                height: parent.height - titleText.height - Theme.spacingLg * 2
                visible: !root.isLoading && resultsList.count > 0
                clip: true

                GridView {
                    boundsBehavior: Theme.boundsBehavior
                    id: resultsList
                    width: parent.width
                    cellWidth: 200
                    cellHeight: 340

                    delegate: Item {
                        width: resultsList.cellWidth
                        height: resultsList.cellHeight

                        Column {
                            anchors.centerIn: parent
                            spacing: 8

                            PosterCard {
                                width: 170
                                height: 260
                                
                                productCode: modelData.product_code || ""
                                titleKo: modelData.title_ko || ""
                                actorsKo: modelData.actors_ko || ""
                                coverPath: modelData.cover_effective_path || ""
                                sceneCount: modelData.scene_count || 0
                                pipelineStage: modelData.pipeline_stage || "none"
                                hasJaSrt: modelData.has_ja_srt || false
                                hasKoSrt: modelData.has_ko_srt || false
                                lampHardcoded: modelData.lamp_hardcoded || false
                                lampMopa: modelData.lamp_mopa || false

                                onClicked: function(sku) {
                                    root.productClicked(sku)
                                    root.close()
                                }

                                // 유사도 점수 표시 배지
                                Rectangle {
                                    anchors.top: parent.top
                                    anchors.left: parent.left
                                    anchors.margins: 8
                                    height: 20
                                    width: scoreText.width + 12
                                    radius: 10
                                    color: Qt.rgba(0, 0, 0, 0.65)
                                    border.color: Qt.rgba(Theme.accentNeon.r, Theme.accentNeon.g, Theme.accentNeon.b, 0.4)
                                    border.width: 1

                                    Text {
                                        id: scoreText
                                        anchors.centerIn: parent
                                        text: Math.round((modelData.similarity_score || 0) * 100) + "% 일치"
                                        font.pixelSize: 10
                                        font.weight: Font.Bold
                                        color: Theme.accentNeon
                                    }
                                }
                            }

                            // 추천 사유 표시
                            Rectangle {
                                width: 170
                                height: reasonText.implicitHeight + 8
                                color: Qt.rgba(Theme.accentNeon.r, Theme.accentNeon.g, Theme.accentNeon.b, 0.05)
                                radius: 4
                                visible: !!modelData.reasoning

                                Text {
                                    id: reasonText
                                    width: parent.width - 12
                                    anchors.centerIn: parent
                                    text: modelData.reasoning || ""
                                    font.pixelSize: 11
                                    color: Theme.textSecondary
                                    horizontalAlignment: Text.AlignHCenter
                                    elide: Text.ElideRight
                                    maximumLineCount: 2
                                    wrapMode: Text.WordWrap
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}