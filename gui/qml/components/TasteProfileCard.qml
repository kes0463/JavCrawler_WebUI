import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

GlassCard {
    id: root
    autoSize: false
    clip: false

    property var profile: ({})
    property bool hasData: profile.has_data === true
    property int watchedCount: profile.watched_count || 0

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.spacingMd
        spacing: Theme.spacingMd

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            Text {
                text: "📊 시청 취향 프로필"
                font.pixelSize: Theme.fontBody
                font.weight: Font.DemiBold
                color: Theme.textPrimary
            }
            Text {
                visible: root.hasData
                text: "실제로 본 " + root.watchedCount + "편 기준 · 막대가 길수록 해당 성향이 강함"
                font.pixelSize: Theme.fontCaption
                color: Theme.textMuted
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }
        }

        Text {
            Layout.fillWidth: true
            visible: !root.hasData
            text: root.profile.empty_message || "시청 데이터가 없습니다."
            font.pixelSize: Theme.fontBody
            color: Theme.textMuted
            wrapMode: Text.Wrap
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingSm
            visible: root.hasData

            Repeater {
                model: profile.axes || []

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 4

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Theme.spacingSm
                        Text {
                            text: modelData.label || ""
                            font.pixelSize: Theme.fontCaption
                            color: Theme.textSecondary
                            Layout.preferredWidth: 72
                        }
                        Rectangle {
                            Layout.fillWidth: true
                            height: 8
                            radius: 4
                            color: Qt.rgba(1, 1, 1, 0.08)
                            Rectangle {
                                width: parent.width * Math.max(0, Math.min(1, modelData.value || 0))
                                height: parent.height
                                radius: 4
                                color: Theme.accentNeon
                            }
                        }
                        Text {
                            text: (modelData.pct !== undefined ? modelData.pct : Math.round((modelData.value || 0) * 100)) + "%"
                            font.pixelSize: Theme.fontCaption
                            font.weight: Font.Bold
                            color: Theme.accentNeon
                            Layout.preferredWidth: 36
                            horizontalAlignment: Text.AlignRight
                        }
                    }
                    Text {
                        Layout.fillWidth: true
                        leftPadding: 80
                        text: modelData.hint || ""
                        font.pixelSize: Theme.fontCaption
                        color: Theme.textMuted
                        wrapMode: Text.Wrap
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            height: 1
            color: Theme.glassBorder
            visible: root.hasData
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingMd
            visible: root.hasData && ((profile.top_genres || []).length > 0 || (profile.top_actors || []).length > 0)

            ColumnLayout {
                Layout.fillWidth: true
                Layout.preferredWidth: 1
                spacing: Theme.spacingXs
                Text {
                    text: "많이 본 장르"
                    font.pixelSize: Theme.fontCaption
                    font.weight: Font.DemiBold
                    color: Theme.textSecondary
                }
                Repeater {
                    model: (profile.top_genres || []).slice(0, 5)
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 6
                        Text {
                            text: modelData.name || ""
                            font.pixelSize: Theme.fontCaption
                            color: Theme.textPrimary
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                        }
                        Text {
                            text: modelData.share_pct + "%"
                            font.pixelSize: Theme.fontCaption
                            color: "#FF9F43"
                            font.weight: Font.Bold
                        }
                    }
                }
            }

            Rectangle {
                width: 1
                Layout.fillHeight: true
                color: Theme.glassBorder
                visible: (profile.top_genres || []).length > 0 && (profile.top_actors || []).length > 0
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.preferredWidth: 1
                spacing: Theme.spacingXs
                Text {
                    text: "많이 본 배우"
                    font.pixelSize: Theme.fontCaption
                    font.weight: Font.DemiBold
                    color: Theme.textSecondary
                }
                Repeater {
                    model: (profile.top_actors || []).slice(0, 5)
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 6
                        Text {
                            text: modelData.name || ""
                            font.pixelSize: Theme.fontCaption
                            color: Theme.textPrimary
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                        }
                        Text {
                            text: modelData.share_pct + "%"
                            font.pixelSize: Theme.fontCaption
                            color: Theme.accentNeon
                            font.weight: Font.Bold
                        }
                    }
                }
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingXs
            visible: root.hasData && (profile.scene_tags || []).length > 0

            Text {
                text: "씬 태그 (Grok 캐시 · 최근 시청 샘플)"
                font.pixelSize: Theme.fontCaption
                font.weight: Font.DemiBold
                color: Theme.textSecondary
            }
            Flow {
                Layout.fillWidth: true
                spacing: Theme.spacingXs
                Repeater {
                    model: (profile.scene_tags || []).slice(0, 8)
                    Rectangle {
                        radius: Theme.radiusSm
                        color: Qt.rgba(0, 229/255, 255/255, 0.1)
                        border.color: Theme.glassBorder
                        height: 22
                        width: sceneChip.implicitWidth + 12
                        Text {
                            id: sceneChip
                            anchors.centerIn: parent
                            text: (modelData.name || "") + (modelData.count ? " (" + modelData.count + ")" : "")
                            font.pixelSize: 11
                            color: Theme.textSecondary
                        }
                    }
                }
            }
        }
    }
}
