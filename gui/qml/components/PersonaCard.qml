import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

GlassCard {
    id: root
    autoSize: false
    clip: false

    property string title: "나의 취향 페르소나"
    property string personaType: ""
    property string summary: ""
    property string body: ""
    property string sensualSummary: ""
    property string driftNote: ""
    property var affinities: []
    property var turnOns: []
    property var avoidances: []
    property var evidence: []
    property var semanticMatches: []
    property string generatedAt: ""
    property string sourceLabel: ""
    property string coverageLabel: ""
    property string feedbackState: ""
    property bool regenerating: false

    signal regenerateRequested()
    signal feedbackSubmitted(string feedback)

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.spacingMd
        spacing: Theme.spacingSm

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingSm

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2
                Text {
                    text: "🎭 " + root.title
                    font.pixelSize: Theme.fontBody
                    font.weight: Font.DemiBold
                    color: Theme.textPrimary
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
                Text {
                    visible: root.personaType.length > 0
                    text: root.personaType
                    font.pixelSize: Theme.fontSubtitle
                    font.weight: Font.ExtraBold
                    color: Theme.accentNeon
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                }
            }

            ActionButton {
                text: root.regenerating ? "생성 중…" : "재생성"
                primary: false
                enabled: !root.regenerating
                height: 34
                onClicked: root.regenerateRequested()
            }
        }

        AppScrollView {
            id: personaScroll
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            ScrollBar.vertical.policy: ScrollBar.AsNeeded

            ColumnLayout {
                width: personaScroll.availableWidth > 0 ? personaScroll.availableWidth : parent.width
                spacing: Theme.spacingSm

                Text {
                    Layout.fillWidth: true
                    text: root.summary || root.body || "취향 데이터를 분석 중입니다…"
                    font.pixelSize: Theme.fontBody
                    color: Theme.textSecondary
                    wrapMode: Text.Wrap
                    lineHeight: 1.35
                }

                Text {
                    Layout.fillWidth: true
                    visible: root.sensualSummary.length > 0 && root.sensualSummary !== root.summary
                    text: root.sensualSummary
                    font.pixelSize: Theme.fontBody
                    color: Theme.textPrimary
                    wrapMode: Text.Wrap
                    lineHeight: 1.35
                }

                Text {
                    Layout.fillWidth: true
                    visible: root.driftNote.length > 0
                    text: "📈 " + root.driftNote
                    font.pixelSize: Theme.fontCaption
                    color: Theme.textPrimary
                    wrapMode: Text.Wrap
                    font.italic: true
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 4
                    visible: (root.turnOns || []).length > 0
                    Text {
                        text: "끌리는 포인트"
                        font.pixelSize: Theme.fontCaption
                        color: Theme.textMuted
                    }
                    Flow {
                        Layout.fillWidth: true
                        spacing: Theme.spacingXs
                        Repeater {
                            model: root.turnOns || []
                            Rectangle {
                                radius: Theme.radiusSm
                                color: Qt.rgba(244/255, 114/255, 182/255, 0.14)
                                border.color: Qt.rgba(244/255, 114/255, 182/255, 0.35)
                                height: 24
                                width: turnOnChip.implicitWidth + 16
                                Text {
                                    id: turnOnChip
                                    anchors.centerIn: parent
                                    text: modelData
                                    font.pixelSize: Theme.fontCaption
                                    color: "#f9a8d4"
                                }
                            }
                        }
                    }
                }

                Flow {
                    Layout.fillWidth: true
                    spacing: Theme.spacingXs
                    visible: (root.affinities || []).length > 0
                    Repeater {
                        model: root.affinities || []
                        Rectangle {
                            radius: Theme.radiusSm
                            color: Qt.rgba(0, 229/255, 255/255, 0.12)
                            border.color: Theme.glassBorder
                            height: 24
                            width: affChip.implicitWidth + 16
                            Text {
                                id: affChip
                                anchors.centerIn: parent
                                text: modelData
                                font.pixelSize: Theme.fontCaption
                                color: Theme.accentNeon
                            }
                        }
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 4
                    visible: (root.avoidances || []).length > 0
                    Text {
                        text: "덜 맞는 패턴"
                        font.pixelSize: Theme.fontCaption
                        color: Theme.textMuted
                    }
                    Repeater {
                        model: root.avoidances || []
                        Text {
                            Layout.fillWidth: true
                            text: "· " + modelData
                            font.pixelSize: Theme.fontCaption
                            color: Theme.textSecondary
                            wrapMode: Text.Wrap
                        }
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 4
                    visible: (root.evidence || []).length > 0 || (root.summary || root.body).length > 0
                    Text {
                        text: "근거 (샘플 작품)"
                        font.pixelSize: Theme.fontCaption
                        color: Theme.textMuted
                    }
                    Text {
                        Layout.fillWidth: true
                        visible: (root.evidence || []).length <= 0
                        text: "근거 샘플이 아직 부족합니다. 시청 기록과 분석 캐시가 쌓이면 표시됩니다."
                        font.pixelSize: Theme.fontCaption
                        color: Theme.textMuted
                        wrapMode: Text.Wrap
                    }
                    Repeater {
                        model: Math.min(3, (root.evidence || []).length)
                        Text {
                            Layout.fillWidth: true
                            property var ev: (root.evidence || [])[index]
                            text: (ev && ev.product_code ? ev.product_code + ": " : "") + (ev && ev.reason ? ev.reason : "")
                            font.pixelSize: Theme.fontCaption
                            color: Theme.textSecondary
                            wrapMode: Text.Wrap
                            elide: Text.ElideRight
                            maximumLineCount: 2
                        }
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 4
                    visible: (root.semanticMatches || []).length > 0 || (root.summary || root.body).length > 0
                    Text {
                        text: "의미 기반 근접작"
                        font.pixelSize: Theme.fontCaption
                        color: Theme.textMuted
                    }
                    Text {
                        Layout.fillWidth: true
                        visible: (root.semanticMatches || []).length <= 0
                        text: "임베딩 분석 후 취향 벡터와 가까운 미시청 작품이 표시됩니다."
                        font.pixelSize: Theme.fontCaption
                        color: Theme.textMuted
                        wrapMode: Text.Wrap
                    }
                    Repeater {
                        model: Math.min(3, (root.semanticMatches || []).length)
                        Text {
                            Layout.fillWidth: true
                            property var match: (root.semanticMatches || [])[index]
                            text: (match && match.product_code ? match.product_code : "")
                                + (match && match.score ? (" · " + Math.round(match.score * 100) + "%") : "")
                            font.pixelSize: Theme.fontCaption
                            color: Theme.textSecondary
                            wrapMode: Text.Wrap
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    height: 1
                    color: Theme.glassBorder
                    visible: (root.summary || root.body).length > 0
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.spacingSm
                    visible: (root.summary || root.body).length > 0

                    Text {
                        text: root.feedbackState.length > 0 ? "피드백 저장됨" : "이 분석이 맞나요?"
                        font.pixelSize: Theme.fontCaption
                        color: root.feedbackState.length > 0 ? Theme.accentNeon : Theme.textMuted
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                    }

                    ActionButton {
                        text: "맞아요"
                        primary: root.feedbackState === "positive"
                        enabled: root.feedbackState !== "positive"
                        height: 30
                        horizontalPadding: Theme.spacingMd
                        onClicked: {
                            root.feedbackState = "positive"
                            root.feedbackSubmitted("positive")
                        }
                    }

                    ActionButton {
                        text: "아니에요"
                        primary: false
                        enabled: root.feedbackState !== "negative"
                        height: 30
                        horizontalPadding: Theme.spacingMd
                        onClicked: {
                            root.feedbackState = "negative"
                            root.feedbackSubmitted("negative")
                        }
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingMd
            Text {
                visible: root.coverageLabel.length > 0
                text: root.coverageLabel
                font.pixelSize: Theme.fontCaption
                color: Theme.textMuted
                Layout.fillWidth: true
                elide: Text.ElideRight
            }
            Text {
                visible: root.sourceLabel.length > 0
                text: root.sourceLabel
                font.pixelSize: Theme.fontCaption
                color: Theme.textMuted
            }
        }
    }
}
