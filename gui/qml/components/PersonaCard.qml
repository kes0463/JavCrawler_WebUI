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
    property string driftNote: ""
    property var affinities: []
    property var evidence: []
    property string generatedAt: ""
    property string sourceLabel: ""
    property string coverageLabel: ""
    property bool regenerating: false

    signal regenerateRequested()

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
                    visible: root.driftNote.length > 0
                    text: "📈 " + root.driftNote
                    font.pixelSize: Theme.fontCaption
                    color: Theme.textPrimary
                    wrapMode: Text.Wrap
                    font.italic: true
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
                    visible: (root.evidence || []).length > 0
                    Text {
                        text: "근거 (샘플 작품)"
                        font.pixelSize: Theme.fontCaption
                        color: Theme.textMuted
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
